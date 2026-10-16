from __future__ import annotations

import webbrowser
from typing import Any
from urllib.parse import urlencode

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from cited_core.api import endpoints
from cited_core.api.client import AGENT_KEY_HEADER
from cited_core.auth.oauth_server import OAuthCallbackServer
from cited_core.auth.store import TokenStore
from cited_core.errors import CitedAPIError
from cited_mcp.context import CitedContext
from cited_mcp.server import mcp
from cited_mcp.tools._helpers import (
    _api_error_response,
    _auth_check,
    _get_ctx,
    _has_agent_key,
    log_tool_call,
)

# ---------------------------------------------------------------------------
# Pending login state (module-level, persists across tool calls)
# ---------------------------------------------------------------------------

_pending_login: OAuthCallbackServer | None = None
_pending_login_env: str | None = None


def _check_pending_login(cited_ctx: CitedContext) -> bool:
    """Check if a pending login flow has completed. If so, store the token.

    Returns True if a token was captured and applied.
    """
    global _pending_login, _pending_login_env

    if _pending_login is None:
        return False

    token = _pending_login.token
    if not token:
        return False

    # Token captured — finalize login
    env = _pending_login_env or cited_ctx.env
    _pending_login.shutdown()
    _pending_login = None
    _pending_login_env = None

    TokenStore().save_token(env, token)
    _apply_token(cited_ctx, token)
    return True


def _apply_token(cited_ctx: CitedContext, token: str) -> None:
    """Use a session token from now on; it takes precedence over any agent key."""
    cited_ctx.client.token = token
    cited_ctx.client._client.cookies.set("advgeo_session", token)
    cited_ctx.client._client.headers.pop(AGENT_KEY_HEADER, None)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Ping",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
async def ping(ctx: Context[Any, CitedContext, Any]) -> Any:
    """Lightweight readiness check — no auth required, no API calls.

    Returns server identity, version, and a fingerprint over the registered
    tool surface (name + description + input schema). Agent skills can stash
    `tools_fingerprint` and re-check it later in the conversation to detect
    when an MCP client has a stale tool cache after a Cited release; if the
    fingerprint differs from a prior value, call `whats_new(since_fingerprint=
    <prior>)` to see what changed.
    """
    from cited_core import __version__
    from cited_mcp.server import get_tools_count, get_tools_fingerprint

    return {
        "status": "ok",
        "server": "cited-mcp",
        "server_version": __version__,
        "tools_fingerprint": get_tools_fingerprint(),
        "tools_count": get_tools_count(),
    }


@mcp.tool(
    title="Check Auth Status",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def check_auth_status(ctx: Context[Any, CitedContext, Any]) -> Any:
    """Check if the user is authenticated and return their account info.

    Returns the user's profile, including ``credits_balance`` (1 credit = $1;
    a standard audit is 10), ``unclaimed`` (an agent account a person has not
    claimed yet) and ``business_count``, plus ``auth_method`` (``session`` or
    ``agent_key``).

    When authenticated by an agent key, also returns ``agent_key`` (from
    key_status: expiry dates, days left, notice, and how to connect with
    OAuth). If the key has an expiry or the account is unclaimed, tell the
    human: an unclaimed account is deleted unless claimed, and a claimed
    account's key expires 90 days after the claim, while OAuth through the
    hosted MCP does not expire.
    """
    cited_ctx = _get_ctx(ctx)

    # Check if a pending login completed in the background
    _check_pending_login(cited_ctx)

    if err := _auth_check(cited_ctx):
        return err
    try:
        user = cited_ctx.client.get(endpoints.ME)
    except CitedAPIError as e:
        return _api_error_response(e)

    # Enrich with business count (unclaimed agent accounts are limited to 1)
    try:
        businesses = cited_ctx.client.get(endpoints.BUSINESSES)
        user["business_count"] = len(businesses) if isinstance(businesses, list) else 0
    except CitedAPIError:
        user["business_count"] = None

    if _has_agent_key(cited_ctx):
        user["auth_method"] = "agent_key"
        try:
            status = cited_ctx.client.get(endpoints.AGENT_KEY_STATUS)
        except CitedAPIError as e:
            status = _api_error_response(e)
        user["agent_key"] = status
        oauth = status.get("oauth") if isinstance(status, dict) else None
        mcp_url = (oauth or {}).get("mcp_url") or "the hosted Cited MCP server"
        if isinstance(status, dict) and status.get("unclaimed"):
            user["auth_note"] = (
                f"Unclaimed agent account, deleted on {status.get('account_expires_at')} "
                "unless the human claims it with the link and code from agent_signup."
            )
        elif isinstance(status, dict) and status.get("key_expires_at"):
            user["auth_note"] = (
                f"This agent key expires on {status.get('key_expires_at')} "
                f"({status.get('days_left')} days left). For access that does not "
                f"expire, have the human connect {mcp_url} with OAuth."
            )
    else:
        user["auth_method"] = "session"

    return user


def _clear_session(cited_ctx: CitedContext, env: str) -> None:
    """Clear stored token and in-memory session state."""
    TokenStore().delete_token(env)
    cited_ctx.client.token = None
    cited_ctx.client._client.cookies.delete("advgeo_session")
    # Fall back to a configured agent key, if any.
    if _has_agent_key(cited_ctx):
        cited_ctx.client._client.headers[AGENT_KEY_HEADER] = str(cited_ctx.client.agent_api_key)


@mcp.tool(
    title="Log In",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def login(
    ctx: Context[Any, CitedContext, Any],
    env: str | None = None,
    force: bool = False,
) -> Any:
    """Log in to Cited by opening a browser window for OAuth authentication.

    This is a two-step process:
    1. First call: returns a login URL. Present it to the user as a clickable link.
    2. After the user authenticates in their browser, call this tool again to confirm.

    In remote mode (HTTP transport), authentication is handled automatically via
    OAuth — this tool is only needed for stdio transport.

    Args:
        ctx: MCP context
        env: Optional environment override (dev, prod, local)
        force: If True, clear existing token and force a new login
            (useful for switching accounts)
    """
    global _pending_login, _pending_login_env

    # Access lifespan context directly — do NOT use _get_ctx() here because
    # it calls _check_pending_login() which would consume the pending login
    # before we can handle it with proper user feedback.
    cited_ctx: CitedContext = ctx.request_context.lifespan_context
    target_env = env or cited_ctx.env

    # --- Step 2: Check if a pending login completed ---
    if _pending_login is not None:
        token = _pending_login.token
        if token:
            # Success! Token was captured by the callback server.
            _pending_login.shutdown()
            _pending_login = None
            _pending_login_env = None

            TokenStore().save_token(target_env, token)
            _apply_token(cited_ctx, token)

            # Verify the token works
            try:
                user = cited_ctx.client.get(endpoints.ME)
                email = user.get("email", "unknown")
                return {
                    "success": True,
                    "message": f"Successfully logged in as {email}",
                }
            except CitedAPIError:
                return {
                    "success": True,
                    "message": f"Logged in successfully (env: {target_env})",
                }
        else:
            # Still waiting — remind the user
            params = urlencode({
                "callback": _pending_login.redirect_uri,
                "app_name": "cited-mcp",
            })
            login_url = f"{cited_ctx.api_url}{endpoints.AUTHORIZE_APP}?{params}"
            return {
                "waiting": True,
                "message": (
                    "Still waiting for you to complete login. "
                    "Please click the link below and sign in with your browser."
                ),
                "login_url": login_url,
                "instructions": (
                    "After signing in, come back here and I'll confirm your login. "
                    "If the link expired, ask me to log in again with force=True."
                ),
            }

    # --- Handle force re-login ---
    if force:
        _clear_session(cited_ctx, target_env)
        # Also clean up any stale pending login
        if _pending_login is not None:
            _pending_login.shutdown()
            _pending_login = None
            _pending_login_env = None

    # --- Already authenticated? ---
    if not force and cited_ctx.client.token:
        try:
            user = cited_ctx.client.get(endpoints.ME)
            return {
                "success": True,
                "message": f"Already authenticated as {user.get('email', 'unknown')}",
            }
        except CitedAPIError:
            pass  # Token invalid, proceed with login flow

    # --- Step 1: Start the login flow (non-blocking) ---
    callback_server = OAuthCallbackServer(timeout=300.0)
    callback_server.start()
    _pending_login = callback_server
    _pending_login_env = target_env

    # Use the API's authorize-app endpoint (same as CLI) — it handles
    # OAuth consent and redirects back to localhost with the token.
    params = urlencode({
        "callback": callback_server.redirect_uri,
        "app_name": "cited-mcp",
    })
    login_url = f"{cited_ctx.api_url}{endpoints.AUTHORIZE_APP}?{params}"

    # Best-effort browser open (may not work in all environments)
    try:
        webbrowser.open(login_url)
        browser_opened = True
    except Exception:
        browser_opened = False

    response: dict[str, Any] = {
        "action_required": True,
        "login_url": login_url,
        "instructions": (
            "Please click the link above to sign in with your browser. "
            "Once you've signed in, ask me to confirm your login "
            "(or just try any command — I'll detect it automatically)."
        ),
    }

    if browser_opened:
        response["message"] = (
            "I've opened your browser to the login page. "
            "Please sign in there, then come back and I'll confirm your login."
        )
    else:
        response["message"] = (
            "Please open the link below in your browser to sign in."
        )

    return response


@mcp.tool(
    title="Log Out",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def logout(ctx: Context[Any, CitedContext, Any]) -> Any:
    """Log out of Cited by clearing the stored authentication token.

    In remote mode (HTTP transport), authentication is managed by the connector —
    disconnect and reconnect to switch accounts. This tool is for stdio transport.
    """
    global _pending_login, _pending_login_env

    lc: CitedContext = ctx.request_context.lifespan_context

    # Agent signed up with agent_signup: logging out forgets its saved key.
    if not lc.client.token and _has_agent_key(lc):
        TokenStore().delete_agent_key(lc.env)
        lc.client.set_agent_api_key(None)
        return {
            "success": True,
            "message": (
                f"Removed the saved agent key (env: {lc.env}). It still works until "
                "revoked; use revoke_api_key first if it should stop working."
            ),
        }

    # Remote mode: lifespan client has no token; auth is via OAuth connector
    if not lc.client.token:
        return {
            "success": False,
            "message": (
                "Authentication is managed by your Claude connector. "
                "To switch accounts, disconnect and reconnect the Cited connector."
            ),
        }

    env = lc.env
    _clear_session(lc, env)

    # Clean up any pending login
    if _pending_login is not None:
        _pending_login.shutdown()
        _pending_login = None
        _pending_login_env = None

    return {"success": True, "message": f"Logged out successfully (env: {env})"}
