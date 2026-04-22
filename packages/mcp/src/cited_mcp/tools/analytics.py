from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from cited_core.api import endpoints
from cited_core.errors import CitedAPIError
from cited_mcp.context import CitedContext
from cited_mcp.server import mcp
from cited_mcp.tools._helpers import (
    _api_error_response,
    _auth_check,
    _get_ctx,
    _resolve_business_id,
    _truncate_response,
    log_tool_call,
)


@mcp.tool(
    title="Get Analytics Trends",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def get_analytics_trends(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """Get KPI trends over time for a business — citation rates, visibility scores, and more.

    Args:
        ctx: MCP context
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}
    try:
        return _truncate_response(
            cited_ctx.client.get(endpoints.ANALYTICS_TRENDS.format(business_id=business_id))
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Analytics Summary",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def get_analytics_summary(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """Get an analytics summary for a business — aggregated metrics and insights.

    Args:
        ctx: MCP context
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}
    try:
        return _truncate_response(
            cited_ctx.client.get(endpoints.ANALYTICS_SUMMARY.format(business_id=business_id))
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Compare Audits",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def compare_audits(
    ctx: Context[Any, CitedContext, Any],
    audit_id: str,
) -> Any:
    """Compare an audit against its baseline — shows what improved and what regressed.

    Args:
        ctx: MCP context
        audit_id: The audit job ID to compare against its baseline
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return _truncate_response(
            cited_ctx.client.get(endpoints.ANALYTICS_COMPARISON.format(audit_id=audit_id))
        )
    except CitedAPIError as e:
        return _api_error_response(e)
