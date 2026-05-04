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
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_analytics_trends(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """Get KPI trends over time for a business — citation rates, visibility scores, and more.

    When to call: you only need the KPI time-series — for a chart, a custom
    trend computation, or a tight summary. Cheaper than get_analytics_dashboard
    if you don't need question performance, benchmarks, or citation trends.

    On a ``payment_required: true`` response, surface ``upgrade_url`` and
    ``required_tier`` (with ``upgrade_price_usd``) to the user before any
    fallback — they may want to upgrade.

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
    title="Get Analytics Dashboard",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_analytics_dashboard(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """Get the combined analytics dashboard for a business.

    Returns kpi_trends, question_performance, citation_trends, benchmarks,
    and domain_benchmarks in a single payload — the same data backing the
    web Analytics page.

    When to call: the user asks for an overview of AI search performance —
    KPIs, trends, top/declining questions, citation patterns, benchmarks —
    in one shot. Reach for get_analytics_trends instead if you only need
    the time-series.

    On a ``payment_required: true`` response, surface ``upgrade_url`` and
    ``required_tier`` (with ``upgrade_price_usd``) to the user before any
    fallback — they may want to upgrade.

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
            cited_ctx.client.get(
                endpoints.ANALYTICS_DASHBOARD.format(business_id=business_id)
            )
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Compare Audits",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def compare_audits(
    ctx: Context[Any, CitedContext, Any],
    audit_id: str,
    baseline_id: str,
) -> Any:
    """Compare two audits and return per-question changes plus aggregate deltas.

    When to call: the user asks "what changed since the last audit" / "are
    we improving" / "show me the week-over-week delta." Compute the diff
    here instead of summarizing two audit reports back to back. Doesn't run
    a new audit — cheap and idempotent.

    Use ``list_audits`` to find a prior completed audit on the same template
    and pass its job_id as ``baseline_id``.

    On a ``payment_required: true`` response, surface ``upgrade_url`` and
    ``required_tier`` (with ``upgrade_price_usd``) to the user before any
    fallback — they may want to upgrade.

    Args:
        ctx: MCP context
        audit_id: The current audit job ID
        baseline_id: A prior completed audit job ID to compare against. Must
            be a different job than ``audit_id``.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return _truncate_response(
            cited_ctx.client.get(
                endpoints.ANALYTICS_COMPARE.format(
                    audit_id=audit_id, baseline_id=baseline_id
                )
            )
        )
    except CitedAPIError as e:
        return _api_error_response(e)
