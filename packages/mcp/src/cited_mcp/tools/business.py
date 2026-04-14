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
    log_tool_call,
)


@mcp.tool(
    title="List Businesses",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def list_businesses(
    ctx: Context[Any, CitedContext, Any],
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """List all businesses for the authenticated user.

    Args:
        ctx: MCP context
        limit: Maximum number of results (default 50)
        offset: Number of results to skip (default 0)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        result = cited_ctx.client.get(endpoints.BUSINESSES, params=params)
        # Auto-set default business when there's exactly one
        lc: CitedContext = ctx.request_context.lifespan_context
        if isinstance(result, list) and len(result) == 1:
            lc.default_business_id = result[0].get("id")
        return result
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Business Details",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def get_business(ctx: Context[Any, CitedContext, Any], business_id: str) -> Any:
    """Get details for a specific business by ID."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.BUSINESS.format(business_id=business_id))
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Create Business",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
@log_tool_call
async def create_business(
    ctx: Context[Any, CitedContext, Any],
    name: str,
    website: str,
    description: str,
    industry: str = "technology",
) -> Any:
    """Create a new business.

    IMPORTANT: Business creation is subject to plan limits. Use 'check_auth_status'
    first to see the current plan and how many businesses already exist. If at the
    limit, consider upgrading or updating an existing business instead.

    Args:
        ctx: MCP context
        name: Business name
        website: Business website (must be a publicly DNS-resolvable domain —
            fabricated domains like example.com will be rejected with a 422 error)
        description: Business description (minimum ~50 characters)
        industry: One of: automotive, beauty, consulting, education, entertainment,
            finance, fitness, government, healthcare, home_services, hospitality,
            legal, manufacturing, non_profit, real_estate, restaurant, retail,
            technology, other
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.post(
            endpoints.BUSINESSES,
            json={
                "name": name,
                "website": website,
                "description": description,
                "industry": industry,
            },
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Update Business",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def update_business(
    ctx: Context[Any, CitedContext, Any],
    business_id: str,
    name: str | None = None,
    website: str | None = None,
    description: str | None = None,
    industry: str | None = None,
) -> Any:
    """Update an existing business. Only provided fields are changed.

    Args:
        ctx: MCP context
        business_id: Business ID to update
        name: New business name
        website: New website URL
        description: New description
        industry: New industry value
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if website is not None:
        payload["website"] = website
    if description is not None:
        payload["description"] = description
    if industry is not None:
        payload["industry"] = industry
    try:
        return cited_ctx.client.put(
            endpoints.BUSINESS.format(business_id=business_id), json=payload
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Delete Business",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def delete_business(ctx: Context[Any, CitedContext, Any], business_id: str) -> Any:
    """Delete a business and all its associated data.

    NOTE: Business deletion may not be available on all plans. If deletion fails
    with a 403 error, the user may need to upgrade their plan. Use 'check_auth_status'
    to verify plan capabilities.

    Args:
        ctx: MCP context
        business_id: Business ID to delete
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        cited_ctx.client.delete(endpoints.BUSINESS.format(business_id=business_id))
        return {"success": True, "message": f"Business {business_id} deleted"}
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Crawl Business Website",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
@log_tool_call
async def crawl_business(ctx: Context[Any, CitedContext, Any], business_id: str) -> Any:
    """Start a crawl job for a business. Returns a job_id you can poll with get_job_status."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.post(endpoints.CRAWL_START.format(business_id=business_id))
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Health Scores",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def get_health_scores(ctx: Context[Any, CitedContext, Any], business_id: str) -> Any:
    """Get GEO health scores for a business."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.HEALTH_SCORES.format(business_id=business_id))
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Usage Stats",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
@log_tool_call
async def get_usage_stats(ctx: Context[Any, CitedContext, Any]) -> Any:
    """Get account usage statistics: plan info, business count, and audit count.

    Useful for checking plan utilization before starting new operations.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err

    stats: dict[str, Any] = {}
    try:
        user = cited_ctx.client.get(endpoints.ME)
        stats["plan"] = user.get("plan", "unknown")
        stats["email"] = user.get("email")
    except CitedAPIError:
        stats["plan"] = "unknown"

    try:
        businesses = cited_ctx.client.get(endpoints.BUSINESSES)
        stats["business_count"] = (
            len(businesses) if isinstance(businesses, list) else 0
        )
    except CitedAPIError:
        stats["business_count"] = None

    try:
        audits = cited_ctx.client.get(
            endpoints.AUDIT_HISTORY, params={"limit": 100}
        )
        stats["audit_count"] = (
            len(audits) if isinstance(audits, list) else 0
        )
    except CitedAPIError:
        stats["audit_count"] = None

    return stats
