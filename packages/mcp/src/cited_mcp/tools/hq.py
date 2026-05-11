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
    include_agentic_readiness: bool = False,
    include_trust_signals: bool = False,
    full: bool = False,
) -> Any:
    """Get the Business HQ dashboard — a comprehensive overview of a business's GEO health.

    Returns health scores, and optionally personas, products, buyer intents,
    priority actions, agentic-readiness, and trust signals. Use full=True
    to get everything (heavy payload) in one call.

    When to call: the user wants a one-shot snapshot of an account —
    health scores, recent audits, recommendations, competitive position,
    top action items. Reach for ``full=True`` when summarizing an account
    holistically; use the targeted ``include_*`` flags when you only need
    a few sections. Tip: for a tighter "what should I focus on right now?"
    answer, prefer ``get_agent_brief`` — it's smaller and pre-prioritised.

    On a ``payment_required: true`` response, surface ``upgrade_url`` and
    ``required_tier`` (with ``upgrade_price_usd``) to the user before any
    fallback — they may want to upgrade.

    Args:
        ctx: MCP context
        business_id: Business ID (uses default if omitted)
        include_personas: Include target personas (with linked offerings,
            performance summary, and improvement actions per persona)
        include_products: Include products/services
        include_intents: Include buyer intent data
        include_actions: Include priority action items
        include_agentic_readiness: Include agentic-readiness summary
            (whether the site is structured for autonomous-agent navigation)
        include_trust_signals: Include trust-signal evidence (reviews,
            certifications, sameAs links)
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
            if include_agentic_readiness:
                data["agentic_readiness"] = cited_ctx.client.get(
                    endpoints.AGENTIC_READINESS.format(business_id=business_id)
                )
            if include_trust_signals:
                data["trust_signals"] = cited_ctx.client.get(
                    endpoints.TRUST_SIGNALS.format(business_id=business_id)
                )

        return _truncate_response(data)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Agent Brief",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def get_agent_brief(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """Single-call summary answering "what should I focus on right now?".

    Composes top priority actions, quick wins, the highest-priority failing
    deterministic checks, and recent citation-rate movement into one
    payload designed for an LLM to reason over without 4-5 chained calls.

    When to call: the opening turn of a "help me improve my GEO" conversation,
    or any time the user asks an open-ended "what should I work on?" question.
    Prefer this over chaining ``get_business_hq`` + ``get_quick_wins`` +
    ``get_recommendation_check_status`` — the brief is composed server-side,
    cheaper, and pre-prioritised.

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
            cited_ctx.client.get(endpoints.HQ_AGENT_BRIEF.format(business_id=business_id))
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Recompute Health Scores",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def recompute_health_scores(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """Force a fresh recomputation of the business's health scores.

    Returns the recomputed ``BusinessHealthScoresResponse``. Use this after
    making profile or HQ edits (personas, products, profile competitors)
    when you want the dashboard scores to reflect the new state immediately
    instead of waiting for the next scheduled refresh.

    Doesn't trigger a website crawl or audit — just recomputes from data
    already collected. Cheap; safe to call after bulk edits.

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
        return cited_ctx.client.post(
            endpoints.HQ_RECOMPUTE.format(business_id=business_id)
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Refresh Business Overview",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),  # noqa: E501
)
@log_tool_call
async def refresh_business_overview(
    ctx: Context[Any, CitedContext, Any],
    scope: str = "all",
    business_id: str | None = None,
) -> Any:
    """Refresh the cached audit / recommendations / overview data for a business.

    Doesn't run new audits or recommendations — re-pulls the most recent
    artifacts and updates the HQ overview projection. Faster than
    re-running an audit when the underlying data is already current but the
    dashboard view is stale.

    Args:
        ctx: MCP context
        scope: One of ``"audit"`` (refresh audit-derived overview only),
            ``"recommendations"`` (refresh recommendation-derived overview),
            or ``"all"`` (default — both).
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}
    scope_norm = (scope or "all").lower().strip()
    if scope_norm == "audit":
        path = endpoints.HQ_OVERVIEW_REFRESH_AUDIT.format(business_id=business_id)
    elif scope_norm in ("recommendations", "rec", "recs"):
        path = endpoints.HQ_OVERVIEW_REFRESH_RECS.format(business_id=business_id)
    elif scope_norm == "all":
        path = endpoints.HQ_OVERVIEW_REFRESH_ALL.format(business_id=business_id)
    else:
        return {
            "error": True,
            "message": "scope must be one of: 'audit', 'recommendations', 'all'",
        }
    try:
        return cited_ctx.client.post(path)
    except CitedAPIError as e:
        return _api_error_response(e)


# ---------------------------------------------------------------------------
# Persona / Product / Buyer-Intent CRUD
# ---------------------------------------------------------------------------


@mcp.tool(
    title="List Personas",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def list_personas(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """List buyer personas declared on the business profile.

    Returns ``[{id, name, role, description, goals, pain_points, ...}]``.
    The ``id`` is what ``update_persona`` and ``delete_persona`` need.

    When to call: before any persona update/delete (the agent has no other
    way to discover persona_ids), or when the user asks "what personas am
    I tracking?" or wants to inspect / reorder them.

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
        return cited_ctx.client.get(
            endpoints.PERSONAS.format(business_id=business_id)
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Create Persona",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def create_persona(
    ctx: Context[Any, CitedContext, Any],
    name: str,
    description: str | None = None,
    role: str | None = None,
    goals: list[str] | None = None,
    pain_points: list[str] | None = None,
    business_id: str | None = None,
) -> Any:
    """Create a target buyer persona for the business.

    Personas drive question-targeting in audits and inform recommendation
    priorities. After creation, audits will start mapping buyer questions
    to this persona; the HQ dashboard will surface persona-level coverage
    once at least one audit has run.

    Args:
        ctx: MCP context
        name: Display name (e.g. "Mid-market RevOps lead")
        description: Free-text persona description
        role: Job title or role
        goals: List of goals/jobs-to-be-done
        pain_points: List of pain points
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}
    payload: dict[str, Any] = {"name": name}
    if description is not None:
        payload["description"] = description
    if role is not None:
        payload["role"] = role
    if goals is not None:
        payload["goals"] = goals
    if pain_points is not None:
        payload["pain_points"] = pain_points
    try:
        return cited_ctx.client.post(
            endpoints.PERSONAS.format(business_id=business_id), json=payload
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Update Persona",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def update_persona(
    ctx: Context[Any, CitedContext, Any],
    persona_id: str,
    name: str | None = None,
    description: str | None = None,
    role: str | None = None,
    goals: list[str] | None = None,
    pain_points: list[str] | None = None,
    business_id: str | None = None,
) -> Any:
    """Update a persona. Only provided fields are changed.

    Args:
        ctx: MCP context
        persona_id: Persona to update
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if role is not None:
        payload["role"] = role
    if goals is not None:
        payload["goals"] = goals
    if pain_points is not None:
        payload["pain_points"] = pain_points
    if not payload:
        return {"error": True, "message": "At least one field must be provided."}
    try:
        return cited_ctx.client.patch(
            endpoints.PERSONA.format(business_id=business_id, persona_id=persona_id),
            json=payload,
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Delete Persona",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def delete_persona(
    ctx: Context[Any, CitedContext, Any],
    persona_id: str,
    business_id: str | None = None,
) -> Any:
    """Delete a persona.

    Removes persona-to-question mappings as well; audits run after delete
    won't attribute coverage to this persona. Confirm with the user before
    calling — there's no undo.

    Args:
        ctx: MCP context
        persona_id: Persona to delete
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}
    try:
        cited_ctx.client.delete(
            endpoints.PERSONA.format(business_id=business_id, persona_id=persona_id)
        )
        return {"success": True, "persona_id": persona_id, "deleted": True}
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="List Products",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def list_products(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """List products and service offerings declared on the business profile.

    Returns ``[{id, name, description, url, category, ...}]``. The ``id`` is
    what ``update_product`` and ``delete_product`` need.

    When to call: before any product update/delete (the agent has no other
    way to discover product_ids), or when the user asks "what products are
    we tracking?".

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
        return cited_ctx.client.get(
            endpoints.PRODUCTS.format(business_id=business_id)
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Create Product",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def create_product(
    ctx: Context[Any, CitedContext, Any],
    name: str,
    description: str | None = None,
    url: str | None = None,
    category: str | None = None,
    business_id: str | None = None,
) -> Any:
    """Create a product or service offering for the business.

    Products are linked to personas via buyer-intent mapping — adding
    products lets the HQ dashboard show per-product coverage once at
    least one audit has run.

    Args:
        ctx: MCP context
        name: Product/service name
        description: Free-text description
        url: Canonical landing page URL
        category: Product category label
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}
    payload: dict[str, Any] = {"name": name}
    if description is not None:
        payload["description"] = description
    if url is not None:
        payload["url"] = url
    if category is not None:
        payload["category"] = category
    try:
        return cited_ctx.client.post(
            endpoints.PRODUCTS.format(business_id=business_id), json=payload
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Update Product",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def update_product(
    ctx: Context[Any, CitedContext, Any],
    product_id: str,
    name: str | None = None,
    description: str | None = None,
    url: str | None = None,
    category: str | None = None,
    business_id: str | None = None,
) -> Any:
    """Update a product. Only provided fields are changed.

    Args:
        ctx: MCP context
        product_id: Product to update
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if url is not None:
        payload["url"] = url
    if category is not None:
        payload["category"] = category
    if not payload:
        return {"error": True, "message": "At least one field must be provided."}
    try:
        return cited_ctx.client.patch(
            endpoints.PRODUCT.format(business_id=business_id, product_id=product_id),
            json=payload,
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Delete Product",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def delete_product(
    ctx: Context[Any, CitedContext, Any],
    product_id: str,
    business_id: str | None = None,
) -> Any:
    """Delete a product.

    Removes product-to-persona mappings as well. Confirm with the user
    before calling — there's no undo.

    Args:
        ctx: MCP context
        product_id: Product to delete
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}
    try:
        cited_ctx.client.delete(
            endpoints.PRODUCT.format(business_id=business_id, product_id=product_id)
        )
        return {"success": True, "product_id": product_id, "deleted": True}
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="List Buyer Intents",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def list_buyer_intents(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """List buyer-intent entries declared on the business profile.

    Returns ``[{id, intent, description, persona_ids, product_ids, ...}]``.
    Buyer intents tie a persona's search/decision goal to the products that
    address it, which drives audit question generation.

    When to call: when the user asks "what intents are we tracking?" or
    before recommending a new ``create_buyer_intent`` (so you can show the
    existing list and suggest non-overlapping additions).

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
        return cited_ctx.client.get(
            endpoints.BUYER_INTENTS.format(business_id=business_id)
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Create Buyer Intent",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def create_buyer_intent(
    ctx: Context[Any, CitedContext, Any],
    intent: str,
    description: str | None = None,
    persona_ids: list[str] | None = None,
    product_ids: list[str] | None = None,
    business_id: str | None = None,
) -> Any:
    """Create a buyer-intent entry — the search/decision goal a persona is acting on.

    Buyer intents tie personas to products through specific decision
    moments ("evaluating subscription billing platforms", "comparing CRM
    pricing tiers"). They drive audit question generation and per-intent
    coverage scoring on the HQ dashboard.

    Args:
        ctx: MCP context
        intent: Short label for the intent (e.g. "evaluating CRM pricing")
        description: Optional longer description
        persona_ids: Persona IDs that exhibit this intent
        product_ids: Product IDs relevant to satisfying this intent
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}
    payload: dict[str, Any] = {"intent": intent}
    if description is not None:
        payload["description"] = description
    if persona_ids is not None:
        payload["persona_ids"] = persona_ids
    if product_ids is not None:
        payload["product_ids"] = product_ids
    try:
        return cited_ctx.client.post(
            endpoints.BUYER_INTENTS.format(business_id=business_id), json=payload
        )
    except CitedAPIError as e:
        return _api_error_response(e)
