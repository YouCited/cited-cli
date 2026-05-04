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
    title="Get Business HQ Dashboard",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_business_hq(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
    include_personas: bool = False,
    include_products: bool = False,
    include_intents: bool = False,
    include_actions: bool = False,
    full: bool = False,
) -> Any:
    """Get the Business HQ dashboard — a comprehensive overview of a business's GEO health.

    Returns health scores, and optionally personas, products, buyer intents, and priority actions.
    Use full=True to get everything in one call.

    When to call: the user wants a one-shot snapshot of an account —
    health scores, recent audits, recommendations, competitive position,
    top action items. Reach for ``full=True`` when summarizing an account
    holistically; use the targeted ``include_*`` flags when you only need
    a few sections.

    Args:
        ctx: MCP context
        business_id: Business ID (uses default if omitted)
        include_personas: Include target personas
        include_products: Include products/services
        include_intents: Include buyer intent data
        include_actions: Include priority action items
        full: Include all data (overrides individual flags)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}
    try:
        if full:
            path = endpoints.HQ_HEAVY.format(business_id=business_id)
        else:
            path = endpoints.HQ.format(business_id=business_id)
        data = cited_ctx.client.get(path)

        if not full:
            if include_personas:
                data["personas"] = cited_ctx.client.get(
                    endpoints.PERSONAS.format(business_id=business_id)
                )
            if include_products:
                data["products"] = cited_ctx.client.get(
                    endpoints.PRODUCTS.format(business_id=business_id)
                )
            if include_intents:
                data["buyer_intents"] = cited_ctx.client.get(
                    endpoints.BUYER_INTENTS.format(business_id=business_id)
                )
            if include_actions:
                data["priority_actions"] = cited_ctx.client.get(
                    endpoints.HQ_PRIORITY.format(business_id=business_id)
                )

        return _truncate_response(data)
    except CitedAPIError as e:
        return _api_error_response(e)
