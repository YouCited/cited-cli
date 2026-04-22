from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import time
import uuid
from collections import deque
from typing import Any

import httpx
import jwt as pyjwt
from mcp.server.fastmcp import Context

from cited_core.api.client import CitedClient
from cited_core.errors import CitedAPIError
from cited_mcp.context import CitedContext

logger = logging.getLogger("cited_mcp.usage")

# ---------------------------------------------------------------------------
# Response size guardrails
# ---------------------------------------------------------------------------

_MAX_RESPONSE_BYTES = 75_000  # ~25k tokens, with margin


def _truncate_response(data: Any, max_bytes: int = _MAX_RESPONSE_BYTES) -> Any:
    """Truncate a tool response if its JSON serialisation exceeds *max_bytes*.

    For dict responses: repeatedly halves the longest top-level list until the
    payload fits.  For list responses: slices the list to fit.  Adds metadata
    fields so the caller knows data was trimmed.
    """
    raw = json.dumps(data, default=str)
    if len(raw.encode()) <= max_bytes:
        return data

    if isinstance(data, list):
        total = len(data)
        while len(json.dumps(data, default=str).encode()) > max_bytes and len(data) > 1:
            data = data[: len(data) // 2]
        return {
            "data": data,
            "_truncated": True,
            "_total_count": total,
            "_hint": f"Showing {len(data)} of {total} items. Use limit/offset for pagination.",
        }

    if isinstance(data, dict):
        # Find list-valued fields and iteratively shrink the longest
        list_fields = {
            k: v for k, v in data.items() if isinstance(v, list) and len(v) > 0
        }
        truncated_fields: list[str] = []
        attempts = 0
        while (
            len(json.dumps(data, default=str).encode()) > max_bytes
            and list_fields
            and attempts < 20
        ):
            longest_key = max(list_fields, key=lambda k: len(list_fields[k]))
            original_len = len(list_fields[longest_key])
            new_len = max(1, original_len // 2)
            data[longest_key] = list_fields[longest_key][:new_len]
            list_fields[longest_key] = data[longest_key]
            if longest_key not in truncated_fields:
                truncated_fields.append(longest_key)
            if new_len <= 1:
                del list_fields[longest_key]
            attempts += 1
        if truncated_fields:
            data["_truncated"] = True
            data["_truncated_fields"] = truncated_fields
        return data

    return data


# ---------------------------------------------------------------------------
# Per-user rate limiting
# ---------------------------------------------------------------------------

_RATE_LIMIT = int(os.environ.get("CITED_RATE_LIMIT", "60"))
_RATE_WINDOW = 60  # seconds
_rate_limits: dict[str, deque[float]] = {}


def _check_rate_limit(user: str) -> dict[str, Any] | None:
    """Return an error dict if *user* has exceeded the rate limit, else None."""
    if _RATE_LIMIT <= 0:
        return None
    now = time.monotonic()
    window = _rate_limits.setdefault(user, deque())
    # Evict expired entries
    while window and now - window[0] >= _RATE_WINDOW:
        window.popleft()
    if len(window) >= _RATE_LIMIT:
        retry_after = int(_RATE_WINDOW - (now - window[0])) + 1
        return {
            "error": True,
            "message": "Rate limited. Please wait before making more requests.",
            "retry_after_seconds": retry_after,
        }
    window.append(now)
    return None


def _get_ctx(ctx: Context[Any, CitedContext, Any]) -> CitedContext:
    """Extract CitedContext from MCP lifespan context.

    For remote transport (OAuth), replaces the lifespan client with a per-request
    client that carries the authenticated user's JWT.
    Also checks for a pending login that may have completed in the background.
    """
    lc: CitedContext = ctx.request_context.lifespan_context

    # Check if a pending login flow completed (non-blocking)
    if not lc.client.token:
        try:
            from cited_mcp.tools.auth import _check_pending_login

            _check_pending_login(lc)
        except ImportError:
            pass

    # If lifespan client already has a token (stdio transport), return as-is
    if lc.client.token:
        return lc

    # Remote transport: try to get user JWT from OAuth access token
    try:
        from mcp.server.auth.middleware.auth_context import get_access_token

        from cited_mcp.auth_provider import CitedAccessToken

        access_token = get_access_token()
        if access_token and isinstance(access_token, CitedAccessToken):
            user_client = CitedClient(
                base_url=lc.api_url,
                token=access_token.user_jwt,
            )
            return CitedContext(
                client=user_client,
                env=lc.env,
                api_url=lc.api_url,
                default_business_id=lc.default_business_id,
            )
    except ImportError:
        pass

    return lc


def _auth_check(cited_ctx: CitedContext) -> dict[str, Any] | None:
    """Return error dict if not authenticated, else None."""
    if cited_ctx.client.token is None:
        return {
            "error": True,
            "message": "Not authenticated. Use the 'login' tool or set CITED_TOKEN env var.",
        }
    return None


def _resolve_business_id(
    cited_ctx: CitedContext, business_id: str | None
) -> str | None:
    """Return *business_id* if provided, else the session default."""
    return business_id or cited_ctx.default_business_id


_ERROR_HINTS: list[tuple[int, str | None, str]] = [
    (
        403,
        "plan",
        "This account's plan may not allow this operation. "
        "Check plan limits with 'check_auth_status'. "
        "Consider upgrading at https://app.youcited.com/settings/billing, "
        "or use 'logout' then 'login' to switch to a different account.",
    ),
    (
        403,
        None,
        "This action is not allowed. Check your plan limits with 'check_auth_status', "
        "or use 'logout' then 'login' to switch accounts.",
    ),
    (
        422,
        None,
        "The request was rejected due to validation errors. "
        "Check that all fields meet requirements (e.g., website must be a real "
        "DNS-resolvable domain, description must be at least ~50 characters).",
    ),
    (
        401,
        None,
        "Authentication has expired or is invalid. "
        "Use 'login' with force=True to re-authenticate, "
        "or 'logout' then 'login' to switch accounts.",
    ),
    (
        429,
        None,
        "Rate limited. Wait a moment before retrying this request.",
    ),
]


def _resolve_token(
    ctx: Context[Any, CitedContext, Any],
) -> str | None:
    """Extract the user JWT from either stdio or remote transport."""
    lc: CitedContext = ctx.request_context.lifespan_context
    if lc.client.token:
        return lc.client.token
    try:
        from mcp.server.auth.middleware.auth_context import get_access_token

        from cited_mcp.auth_provider import CitedAccessToken

        access_token = get_access_token()
        if access_token and isinstance(access_token, CitedAccessToken):
            return access_token.user_jwt
    except ImportError:
        pass
    return None


def _rate_limit_key(token: str | None) -> str:
    """Derive a tamper-proof rate-limit key from the raw token."""
    if not token:
        return "anonymous"
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _extract_user(token: str | None) -> str:
    """Decode user email from a JWT without verifying signature (for logging only)."""
    if not token:
        return "anonymous"
    try:
        payload = pyjwt.decode(
            token, options={"verify_signature": False}
        )
        return payload.get("email", payload.get("sub", "unknown"))
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Per-user tier cache (avoids /auth/me call on every tool invocation)
# ---------------------------------------------------------------------------

_TIER_CACHE_TTL = 300  # 5 minutes
_tier_cache: dict[str, tuple[str, float]] = {}  # rl_key -> (tier, expires_at)


def _get_user_tier(cited_ctx: CitedContext, cache_key: str) -> str | None:
    """Return the user's subscription tier, using a short-lived cache.

    Falls back to None (treated as free) if the API call fails.
    """
    now = time.monotonic()
    cached = _tier_cache.get(cache_key)
    if cached and now < cached[1]:
        return cached[0]

    try:
        user = cited_ctx.client.get("/auth/me")
        tier = user.get("subscription_tier", "free")
        _tier_cache[cache_key] = (tier, now + _TIER_CACHE_TTL)
        return tier
    except Exception:
        # If /auth/me fails, use cached value (even if stale) or default to None
        if cached:
            return cached[0]
        return None


def log_tool_call(func):  # noqa: ANN001, ANN201
    """Decorator: rate-limits, logs, and catches transport errors per tool call."""

    @functools.wraps(func)
    async def wrapper(
        ctx: Context[Any, CitedContext, Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        tool_name = func.__name__
        token = _resolve_token(ctx)
        rl_key = _rate_limit_key(token)
        user = _extract_user(token)
        request_id = uuid.uuid4().hex[:12]
        start = time.monotonic()

        # Rate limit check
        if rl_err := _check_rate_limit(rl_key):
            logger.info(
                json.dumps(
                    {
                        "event": "rate_limited",
                        "request_id": request_id,
                        "tool": tool_name,
                        "user": user,
                    }
                )
            )
            rl_err["_request_id"] = request_id
            return rl_err

        # Plan gating check (skip for auth tools — must always be accessible)
        from cited_mcp.plan_gating import is_tool_allowed, upgrade_message

        _AUTH_TOOLS = {"check_auth_status", "login", "logout"}
        if tool_name not in _AUTH_TOOLS and token:
            cited_ctx = _get_ctx(ctx)
            if cited_ctx.client.token:
                user_tier = _get_user_tier(cited_ctx, rl_key)
                if not is_tool_allowed(tool_name, user_tier):
                    gate_err = upgrade_message(tool_name, user_tier)
                    gate_err["_request_id"] = request_id
                    logger.info(
                        json.dumps(
                            {
                                "event": "plan_gated",
                                "request_id": request_id,
                                "tool": tool_name,
                                "user": user,
                                "current_tier": user_tier,
                                "required_tier": gate_err["required_tier"],
                            }
                        )
                    )
                    return gate_err

        try:
            result = await func(ctx, *args, **kwargs)
            duration_ms = int((time.monotonic() - start) * 1000)
            is_error = isinstance(result, dict) and result.get(
                "error"
            ) is True
            logger.info(
                json.dumps(
                    {
                        "event": "tool_call",
                        "request_id": request_id,
                        "tool": tool_name,
                        "user": user,
                        "duration_ms": duration_ms,
                        "success": not is_error,
                    }
                )
            )
            # Inject request_id into response
            if isinstance(result, dict):
                result["_request_id"] = request_id
            elif isinstance(result, list):
                result = {
                    "data": result,
                    "_request_id": request_id,
                }
            return result

        except httpx.TimeoutException:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                json.dumps(
                    {
                        "event": "tool_call",
                        "request_id": request_id,
                        "tool": tool_name,
                        "user": user,
                        "duration_ms": duration_ms,
                        "success": False,
                        "error_type": "timeout",
                    }
                )
            )
            return {
                "error": True,
                "message": (
                    "The request timed out. The Cited API may be "
                    "temporarily slow — please try again in a moment."
                ),
                "_request_id": request_id,
            }

        except httpx.ConnectError:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                json.dumps(
                    {
                        "event": "tool_call",
                        "request_id": request_id,
                        "tool": tool_name,
                        "user": user,
                        "duration_ms": duration_ms,
                        "success": False,
                        "error_type": "connection_error",
                    }
                )
            )
            return {
                "error": True,
                "message": (
                    "Could not connect to the Cited API. "
                    "The service may be temporarily unavailable."
                ),
                "_request_id": request_id,
            }

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                json.dumps(
                    {
                        "event": "tool_call",
                        "request_id": request_id,
                        "tool": tool_name,
                        "user": user,
                        "duration_ms": duration_ms,
                        "success": False,
                        "error_type": type(exc).__name__,
                    }
                )
            )
            raise

    return wrapper


def _api_error_response(e: CitedAPIError) -> dict[str, Any]:
    """Convert CitedAPIError to a structured error dict with actionable hints."""
    response: dict[str, Any] = {
        "error": True,
        "status_code": e.status_code,
        "message": e.message,
    }

    for code, substring, hint in _ERROR_HINTS:
        if e.status_code == code and (
            substring is None
            or (e.message and substring.lower() in e.message.lower())
        ):
            response["hint"] = hint
            break

    return response
