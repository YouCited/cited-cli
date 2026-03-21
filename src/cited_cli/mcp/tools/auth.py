from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from cited_cli.api import endpoints
from cited_cli.mcp.context import CitedContext
from cited_cli.mcp.server import mcp
from cited_cli.mcp.tools._helpers import _api_error_response, _auth_check, _get_ctx
from cited_cli.utils.errors import CitedAPIError


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
