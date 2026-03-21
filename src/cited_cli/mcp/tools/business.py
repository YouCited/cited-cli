from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from cited_cli.api import endpoints
from cited_cli.mcp.context import CitedContext
from cited_cli.mcp.server import mcp
from cited_cli.mcp.tools._helpers import _api_error_response, _auth_check, _get_ctx
from cited_cli.utils.errors import CitedAPIError


@mcp.tool()
async def list_businesses(ctx: Context[Any, CitedContext, Any]) -> Any:
    """List all businesses for the authenticated user."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.BUSINESSES)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool()
async def get_business(ctx: Context[Any, CitedContext, Any], business_id: str) -> Any:
    """Get details for a specific business by ID."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.BUSINESS.format(business_id=business_id))
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool()
async def create_business(
    ctx: Context[Any, CitedContext, Any],
    name: str,
    website: str,
    description: str,
    industry: str = "technology",
) -> Any:
    """Create a new business.

    Args:
        ctx: MCP context
        name: Business name
        website: Business website (must be a publicly DNS-resolvable domain)
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


@mcp.tool()
async def crawl_business(ctx: Context[Any, CitedContext, Any], business_id: str) -> Any:
    """Start a crawl job for a business. Returns a job_id you can poll with get_job_status."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.post(endpoints.CRAWL_START.format(business_id=business_id))
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool()
async def get_health_scores(ctx: Context[Any, CitedContext, Any], business_id: str) -> Any:
    """Get GEO health scores for a business."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.HEALTH_SCORES.format(business_id=business_id))
    except CitedAPIError as e:
        return _api_error_response(e)
