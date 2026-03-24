from __future__ import annotations

import webbrowser
from typing import Any

import anyio
from mcp.server.fastmcp import Context

from cited_core.api import endpoints
from cited_core.auth.oauth_server import OAuthCallbackServer
from cited_core.auth.store import TokenStore
from cited_core.config.constants import FRONTEND_URLS
from cited_core.errors import CitedAPIError
from cited_mcp.context import CitedContext
from cited_mcp.server import mcp
from cited_mcp.tools._helpers import _api_error_response, _auth_check, _get_ctx


@mcp.tool()
async def check_auth_status(ctx: Context[Any, CitedContext, Any]) -> Any:
    """Check if the user is authenticated and return their account info."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.ME)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool()
async def login(ctx: Context[Any, CitedContext, Any], env: str | None = None) -> Any:
    """Log in to Cited by opening a browser window for OAuth authentication.

    In remote mode (HTTP transport), authentication is handled automatically via
    OAuth — this tool is only needed for stdio transport.

    Args:
        ctx: MCP context
        env: Optional environment override (dev, prod, local)
    """
    cited_ctx = _get_ctx(ctx)

    # If already authenticated (e.g. remote mode with OAuth), skip login
    if cited_ctx.client.token:
        try:
            user = cited_ctx.client.get(endpoints.ME)
            return {
                "success": True,
                "message": f"Already authenticated as {user.get('email', 'unknown')}",
            }
        except CitedAPIError:
            pass  # Token invalid, proceed with login flow

    target_env = env or cited_ctx.env

    callback_server = OAuthCallbackServer(timeout=120.0)
    callback_server.start()

    frontend = FRONTEND_URLS.get(target_env, FRONTEND_URLS["prod"])
    login_url = f"{frontend}/login?callback={callback_server.redirect_uri}"

    webbrowser.open(login_url)

    token = await anyio.to_thread.run_sync(callback_server.wait_for_token)
    callback_server.shutdown()

    if not token:
        return {"error": True, "message": "Login timed out. Please try again."}

    TokenStore().save_token(target_env, token)
    cited_ctx.client.token = token

    return {"success": True, "message": f"Logged in successfully (env: {target_env})"}
