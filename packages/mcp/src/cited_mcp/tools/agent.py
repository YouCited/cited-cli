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
    title="Get Business Facts",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_business_facts(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """Get structured business facts — key data points extracted from crawl and audit data.

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
            cited_ctx.client.get(endpoints.AGENT_FACTS.format(business_id=business_id))
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Business Claims",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_business_claims(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """Get verifiable claims about a business that can be fact-checked.

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
            cited_ctx.client.get(endpoints.AGENT_CLAIMS.format(business_id=business_id))
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Competitive Comparison",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_competitive_comparison(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """Get competitive comparison — how the business stacks up against competitors.

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
            cited_ctx.client.get(endpoints.AGENT_COMPARISON.format(business_id=business_id))
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Semantic Health",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_semantic_health(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """Get semantic readiness signals for AI understanding of business content.

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
            cited_ctx.client.get(endpoints.AGENT_SEMANTIC_HEALTH.format(business_id=business_id))
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Buyer Fit Query",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=True),  # noqa: E501
)
@log_tool_call
async def buyer_fit_query(
    ctx: Context[Any, CitedContext, Any],
    query: str,
    business_id: str | None = None,
) -> Any:
    """Run a buyer-fit simulation — test how well a business matches a buyer's search query.

    Args:
        ctx: MCP context
        query: The buyer query to simulate (e.g., "best GEO platform for e-commerce")
        business_id: Optional business ID to scope the query to a specific business
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    payload: dict[str, str] = {"query": query}
    if business_id:
        payload["business_id"] = business_id
    try:
        return _truncate_response(
            cited_ctx.client.post(endpoints.AGENT_BUYER_FIT, json=payload)
        )
    except CitedAPIError as e:
        return _api_error_response(e)
