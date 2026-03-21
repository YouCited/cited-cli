from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from cited_core.api.client import CitedClient
from cited_core.errors import CitedAPIError
from cited_mcp.context import CitedContext


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


def _api_error_response(e: CitedAPIError) -> dict[str, Any]:
    """Convert CitedAPIError to a structured error dict."""
    return {
        "error": True,
        "status_code": e.status_code,
        "message": e.message,
    }
