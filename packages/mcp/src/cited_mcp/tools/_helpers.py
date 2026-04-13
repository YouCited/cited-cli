from __future__ import annotations

import functools
import json
import logging
import time
from typing import Any

import jwt as pyjwt
from mcp.server.fastmcp import Context

from cited_core.api.client import CitedClient
from cited_core.errors import CitedAPIError
from cited_mcp.context import CitedContext

logger = logging.getLogger("cited_mcp.usage")


def _get_ctx(ctx: Context[Any, CitedContext, Any]) -> CitedContext:
    """Extract CitedContext from MCP lifespan context.

    For remote transport (OAuth), replaces the lifespan client with a per-request
    client that carries the authenticated user's JWT.
    """
    lc: CitedContext = ctx.request_context.lifespan_context

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
            return CitedContext(client=user_client, env=lc.env, api_url=lc.api_url)
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


def _extract_user(token: str | None) -> str:
    """Decode user email from a JWT without verifying signature."""
    if not token:
        return "anonymous"
    try:
        payload = pyjwt.decode(
            token, options={"verify_signature": False}
        )
        return payload.get("email", payload.get("sub", "unknown"))
    except Exception:
        return "unknown"


def log_tool_call(func):  # noqa: ANN001, ANN201
    """Decorator that emits a structured JSON log line per tool call."""

    @functools.wraps(func)
    async def wrapper(
        ctx: Context[Any, CitedContext, Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        tool_name = func.__name__
        token = _resolve_token(ctx)
        user = _extract_user(token)
        start = time.monotonic()
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
                        "tool": tool_name,
                        "user": user,
                        "duration_ms": duration_ms,
                        "success": not is_error,
                    }
                )
            )
            return result
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                json.dumps(
                    {
                        "event": "tool_call",
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
