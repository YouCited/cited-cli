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

    Returns ``name``, ``summary``, ``locations``, ``products``, ``facts``
    plus source metadata.

    When to call: the user asks "what does Cited know about [business]" or
    you need structured intel without running a fresh audit. Cheap, no
    plan-budget impact. If ``summary`` is null and ``facts`` is empty the
    fact graph is thin — recommend ``crawl_business`` to populate.

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

    When to call: auditing brand truth-in-advertising, or surfacing claims
    that need stronger evidence before they appear in AI summaries —
    typically when the user is prepping a product page, press kit, or
    landing page review.

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

    Returns ``competitors``, ``strengths``, ``weaknesses``, and
    ``market_intelligence`` from the existing competitive analysis.

    When to call: mid-conversation, the user asks "how do we stack up
    against X" or wants positioning context. Doesn't run new prompts —
    pulls from data already collected.

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

    Returns ``entity_grounding``, ``schema_coverage``, ``faq_coverage``,
    ``claim_evidence_coverage``, and ``trust_signals``.

    When to call: the user asks what to fix to be more discoverable to AI
    engines. Returns structured diagnostics rather than free-text advice
    — surface the lowest-coverage area first as the priority fix.

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
    buyer: str,
    business_id: str | None = None,
    constraints: list[dict[str, Any]] | None = None,
    limit: int = 5,
) -> Any:
    """Run a buyer-fit simulation against a business's products and fit signals.

    Returns ordered ``recommendations`` (product/fit matches) plus echoed
    request fields and source attribution metadata.

    When to call: ad-hoc "would AI recommend us for X" probes — testing
    positioning before committing to a full audit, or evaluating a new
    buyer profile. Faster and cheaper than a full audit; doesn't update the
    business record. If recommendations look weak, suggest a full audit
    with a template tuned for this buyer's queries.

    On a ``payment_required: true`` response, surface ``upgrade_url`` and
    ``required_tier`` (with ``upgrade_price_usd``) to the user before any
    fallback — they may want to upgrade.

    Args:
        ctx: MCP context
        buyer: Buyer profile or query (2-200 chars). e.g.
            "fintech CTO evaluating subscription billing platforms".
        business_id: Business to score against. Required by the backend; the
            tool will fall back to the default business if available.
        constraints: Optional list of constraint dicts narrowing the match.
        limit: Max number of recommendations to return (1-20, default 5).
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {
            "error": True,
            "message": "business_id is required. Call list_businesses first.",
        }
    payload: dict[str, Any] = {
        "business_id": business_id,
        "buyer": buyer,
        "constraints": constraints or [],
        "limit": limit,
    }
    try:
        return _truncate_response(
            cited_ctx.client.post(endpoints.AGENT_BUYER_FIT, json=payload)
        )
    except CitedAPIError as e:
        return _api_error_response(e)
