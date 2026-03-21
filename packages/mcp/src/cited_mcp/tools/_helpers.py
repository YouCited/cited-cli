from __future__ import annotations

from typing import Any

from cited_core.errors import CitedAPIError
from mcp.server.fastmcp import Context

from cited_mcp.context import CitedContext


def _get_ctx(ctx: Context[Any, CitedContext, Any]) -> CitedContext:
    """Extract CitedContext from MCP lifespan context."""
    lc: CitedContext = ctx.request_context.lifespan_context
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
