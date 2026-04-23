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
    _get_ctx,
    log_tool_call,
)


@mcp.tool(
    title="Get Pricing",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_pricing(ctx: Context[Any, CitedContext, Any]) -> Any:
    """Get available subscription plans and pricing.

    Returns plan tiers (Growth, Scale, Pro) with monthly prices,
    capabilities, and limits. Use this to show the user their
    upgrade options before calling upgrade_plan.
    """
    cited_ctx = _get_ctx(ctx)
    try:
        return cited_ctx.client.get(endpoints.BILLING_PRICING)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Upgrade Plan",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def upgrade_plan(
    ctx: Context[Any, CitedContext, Any],
    target_tier: str,
) -> Any:
    """Upgrade the user's subscription plan to unlock more tools.

    For users with a payment method on file, the upgrade takes effect
    immediately (card is charged the prorated difference). For first-time
    subscribers, returns a checkout URL that must be opened once.

    Args:
        ctx: MCP context
        target_tier: Target plan: growth ($39/mo), scale ($99/mo),
            or pro ($299/mo)
    """
    cited_ctx = _get_ctx(ctx)
    try:
        return cited_ctx.client.post(
            endpoints.BILLING_AGENT_UPGRADE,
            json={"target_tier": target_tier},
        )
    except CitedAPIError as e:
        return _api_error_response(e)
