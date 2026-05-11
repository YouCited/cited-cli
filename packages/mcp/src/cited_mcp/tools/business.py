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
    log_tool_call,
)


@mcp.tool(
    title="List Businesses",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
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
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
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
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def create_business(
    ctx: Context[Any, CitedContext, Any],
    name: str,
    website: str,
    description: str | None = None,
    industry: str = "technology",
    one_line_description: str | None = None,
    primary_customer: str | None = None,
    problem_solved: str | None = None,
    offering_type: str | None = None,
    primary_market: str | None = None,
    service_areas: str | None = None,
    headquarters_country: str | None = None,
    goals: list[str] | None = None,
    discovery_channels: list[str] | None = None,
    success_definition: str | None = None,
) -> Any:
    """Create a new business with the full onboarding profile.

    IMPORTANT: Business creation is subject to plan limits. Use 'check_auth_status'
    first to see the current plan and how many businesses already exist. If at the
    limit, consider upgrading or updating an existing business instead.

    Either provide ``description`` (10+ words) or supply the structured onboarding
    fields (``problem_solved``, ``primary_customer``, etc.) and the server will
    compose ``description`` for you. Providing both is fine — the explicit
    description wins.

    Args:
        ctx: MCP context
        name: Business name (2-255 chars).
        website: Business website (must be a publicly DNS-resolvable domain —
            fabricated domains like example.com will be rejected with a 422 error).
        description: Optional full business description (10-500 words). Omit
            to have the server compose one from the structured fields below.
        industry: One of: automotive, beauty, consulting, education, entertainment,
            finance, fitness, government, healthcare, home_services, hospitality,
            legal, manufacturing, non_profit, real_estate, restaurant, retail,
            technology, other. Defaults to "technology".
        one_line_description: Short tagline (max 140 chars).
        primary_customer: Who the business serves (max 255 chars,
            e.g. "Enterprise CTOs", "Local homeowners").
        problem_solved: The pain the business addresses (max 300 chars).
        offering_type: One of "product", "service", "both".
        primary_market: One of "global", "national", "regional", "local".
            Used to scope visibility questions. Pair with ``service_areas`` for
            local/regional businesses.
        service_areas: Cities, metros, or regions to monitor (max 2000 chars).
            Only meaningful when primary_market is "local" or "regional".
        headquarters_country: ISO 3166-1 alpha-2 country code (e.g. "US", "GB").
            Resolves "national" primary_market to a concrete country and anchors
            regional/local markets in question generation.
        goals: List of business goals (max 20 items, each ≤120 chars).
        discovery_channels: How customers find the business (max 20 items, each
            ≤120 chars).
        success_definition: What success looks like in 6 months (max 300 chars).
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    payload: dict[str, Any] = {
        "name": name,
        "website": website,
        "industry": industry,
    }
    optional_fields = {
        "description": description,
        "one_line_description": one_line_description,
        "primary_customer": primary_customer,
        "problem_solved": problem_solved,
        "offering_type": offering_type,
        "primary_market": primary_market,
        "service_areas": service_areas,
        "headquarters_country": headquarters_country,
        "goals": goals,
        "discovery_channels": discovery_channels,
        "success_definition": success_definition,
    }
    for key, value in optional_fields.items():
        if value is not None:
            payload[key] = value
    try:
        return cited_ctx.client.post(endpoints.BUSINESSES, json=payload)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Update Business",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def update_business(
    ctx: Context[Any, CitedContext, Any],
    business_id: str,
    name: str | None = None,
    website: str | None = None,
    description: str | None = None,
    industry: str | None = None,
    one_line_description: str | None = None,
    primary_customer: str | None = None,
    problem_solved: str | None = None,
    offering_type: str | None = None,
    primary_market: str | None = None,
    service_areas: str | None = None,
    headquarters_country: str | None = None,
    goals: list[str] | None = None,
    discovery_channels: list[str] | None = None,
    success_definition: str | None = None,
    address: str | None = None,
    city: str | None = None,
    region: str | None = None,
    country: str | None = None,
) -> Any:
    """Update an existing business. Only provided fields are changed.

    Covers the full editable business profile — basic info, market scope,
    structured identity, goals/channels, and primary location. Pass only the
    fields the user wants to change.

    Args:
        ctx: MCP context
        business_id: Business ID to update.
        name: New business name (2-255 chars).
        website: New website URL (must be DNS-resolvable).
        description: New full description (10-500 words).
        industry: New industry — same allowed values as ``create_business``.
        one_line_description: Short tagline (max 140 chars).
        primary_customer: Who the business serves (max 255 chars).
        problem_solved: The pain it addresses (max 300 chars).
        offering_type: One of "product", "service", "both".
        primary_market: One of "global", "national", "regional", "local".
        service_areas: Cities, metros, or regions (max 2000 chars; only
            meaningful for local/regional markets).
        headquarters_country: ISO 3166-1 alpha-2 country code (e.g. "US").
        goals: List of business goals (max 20 items, each ≤120 chars).
        discovery_channels: How customers find the business (max 20 items).
        success_definition: What success looks like in 6 months (max 300 chars).
        address: Primary street address (max 500 chars).
        city: Primary city (max 120 chars).
        region: Primary state/region (max 120 chars).
        country: Primary country (max 120 chars; the human-readable name —
            for the ISO code that anchors market scope, use
            ``headquarters_country``).
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    payload: dict[str, Any] = {}
    optional_fields = {
        "name": name,
        "website": website,
        "description": description,
        "industry": industry,
        "one_line_description": one_line_description,
        "primary_customer": primary_customer,
        "problem_solved": problem_solved,
        "offering_type": offering_type,
        "primary_market": primary_market,
        "service_areas": service_areas,
        "headquarters_country": headquarters_country,
        "goals": goals,
        "discovery_channels": discovery_channels,
        "success_definition": success_definition,
        "address": address,
        "city": city,
        "region": region,
        "country": country,
    }
    for key, value in optional_fields.items():
        if value is not None:
            payload[key] = value
    try:
        return cited_ctx.client.patch(
            endpoints.BUSINESS.format(business_id=business_id), json=payload
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Delete Business",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),  # noqa: E501
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
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),  # noqa: E501
)
@log_tool_call
async def crawl_business(ctx: Context[Any, CitedContext, Any], business_id: str) -> Any:
    """Crawl a business's website to gather content and brand signals.

    When to call: optionally after creating a business, or when the
    website has changed significantly and you want fresh data before
    an audit. Note: audits and solutions will trigger a crawl
    automatically if one is needed, so explicit crawling is not
    required for the standard workflow.

    Side effect: a successful crawl will auto-fill empty business-profile
    fields from JSON-LD / meta tags it finds on the homepage (e.g.
    description, founding year, NAICS, social links). User-supplied values
    are never overwritten — only blank fields get populated. After the
    crawl finishes, call ``get_business`` to see what was filled in.

    Returns a job_id to poll with get_job_status. Typical time: 1-3 min.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.post(endpoints.CRAWL_START.format(business_id=business_id))
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Health Scores",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
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
    title="List Profile Competitors",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def list_profile_competitors(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """List the competitors the user has explicitly declared on their business profile.

    Returns a list of ``{id, name, website}``. These are competitors that
    bypass third-party citation-only filtering during audits and
    head-to-head comparisons — declared rivals are always analysed and
    rank ahead of citation-only picks.

    When to call: the user asks "who are we tracking as competitors?",
    or before recommending ``set_profile_competitors`` so you can show
    them the current list and append/replace intentionally. If the list
    is empty and the user has complained about an obviously-relevant
    rival missing from H2H comparisons, suggest adding it via
    ``set_profile_competitors``.

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
            endpoints.PROFILE_COMPETITORS.format(business_id=business_id)
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Set Profile Competitors",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def set_profile_competitors(
    ctx: Context[Any, CitedContext, Any],
    competitors: list[dict[str, str]],
    business_id: str | None = None,
) -> Any:
    """Replace the full list of profile competitors (max 10).

    This is a REPLACE operation, not append — pass the entire desired list.
    To add one competitor without losing existing ones, call
    ``list_profile_competitors`` first, append to that list, then pass the
    combined list here. To remove all, pass an empty list.

    Profile competitors bypass third-party domain filtering and are ranked
    ahead of citation-only picks in head-to-head comparisons. Add a
    competitor here when an obviously-relevant rival isn't appearing in
    audit results because they don't have enough citation signal.

    Args:
        ctx: MCP context
        competitors: List of ``{"name": str, "website": str}`` dicts.
            ``name`` is 2-255 chars; ``website`` must be a valid HTTP/HTTPS
            URL. Maximum 10 entries.
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}
    if not isinstance(competitors, list):
        return {
            "error": True,
            "message": "competitors must be a list of {name, website} dicts.",
        }
    if len(competitors) > 10:
        return {
            "error": True,
            "message": (
                f"Maximum 10 profile competitors per business — got {len(competitors)}."
            ),
        }
    try:
        return cited_ctx.client.put(
            endpoints.PROFILE_COMPETITORS.format(business_id=business_id),
            json={"competitors": competitors},
        )
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

    On a ``payment_required: true`` response, surface ``upgrade_url`` and
    ``required_tier`` (with ``upgrade_price_usd``) to the user before any
    fallback — they may want to upgrade.
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
