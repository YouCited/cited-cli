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
    _truncate_response,
    log_tool_call,
)


@mcp.tool(
    title="Start Recommendations",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def start_recommendation(ctx: Context[Any, CitedContext, Any], audit_job_id: str) -> Any:
    """Start a recommendation job based on a completed audit.

    Args:
        ctx: MCP context
        audit_job_id: The completed audit job ID to generate recommendations for
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.post(
            endpoints.RECOMMEND_START,
            json={"audit_job_id": audit_job_id},
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Recommendation Status",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_recommendation_status(ctx: Context[Any, CitedContext, Any], job_id: str) -> Any:
    """Check the status of a recommendation job."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.RECOMMEND_STATUS.format(job_id=job_id))
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Recommendation Results",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_recommendation_result(ctx: Context[Any, CitedContext, Any], job_id: str) -> Any:
    """Get the full results of a completed recommendation job."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        result = cited_ctx.client.get(
            endpoints.RECOMMEND_RESULT.format(job_id=job_id)
        )
        return _truncate_response(result)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Recommendation Insights",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_recommendation_insights(ctx: Context[Any, CitedContext, Any], job_id: str) -> Any:
    """Get actionable insights from a recommendation, with source_type and source_id for solutions.

    Returns question_insights, head_to_head_comparisons, strengthening_tips, and
    priority_actions, each annotated with the source_type and source_id needed to
    start a solution via start_solution.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        result = cited_ctx.client.get(endpoints.RECOMMEND_RESULT.format(job_id=job_id))
    except CitedAPIError as e:
        return _api_error_response(e)

    insights: dict[str, Any] = {}

    for item in result.get("question_insights", []):
        item["source_type"] = "question_insight"
        item["source_id"] = item.get("question_id", "")
    insights["question_insights"] = result.get("question_insights", [])

    for item in result.get("head_to_head_comparisons", []):
        item["source_type"] = "head_to_head"
        item["source_id"] = item.get("competitor_domain", "")
    insights["head_to_head_comparisons"] = result.get("head_to_head_comparisons", [])

    for item in result.get("strengthening_tips", []):
        item["source_type"] = "strengthening_tip"
        item["source_id"] = item.get("category", "")
    insights["strengthening_tips"] = result.get("strengthening_tips", [])

    for item in result.get("priority_actions", []):
        item["source_type"] = "priority_action"
        item["source_id"] = item.get("id", item.get("category", ""))
    insights["priority_actions"] = result.get("priority_actions", [])

    return _truncate_response(insights)


@mcp.tool(
    title="List Recommendations",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def list_recommendations(
    ctx: Context[Any, CitedContext, Any],
    audit_job_id: str,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """List recommendation history for a specific audit.

    Args:
        ctx: MCP context
        audit_job_id: The audit job ID to list recommendations for
        limit: Maximum number of results (default 50)
        offset: Number of results to skip (default 0)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        return cited_ctx.client.get(
            endpoints.RECOMMEND_HISTORY.format(audit_job_id=audit_job_id),
            params=params,
        )
    except CitedAPIError as e:
        return _api_error_response(e)


# ---------------------------------------------------------------------------
# Validation Engine — verify recommendation completion deterministically
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Get Recommendation Check Status",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),  # noqa: E501
)
@log_tool_call
async def get_recommendation_check_status(
    ctx: Context[Any, CitedContext, Any],
    recommendation_job_id: str,
    mode: str = "cache",
) -> Any:
    """Run all 62 deterministic GEO/SEO checks against the business linked to a recommendation job.

    Returns ``counts`` (valid / invalid / inconclusive) plus per-check
    ``results`` with check_id, category, domain, status, message,
    template_title, template_priority. Complementary to the AI-citation
    audit — these are deterministic site checks (schema, llms.txt,
    technical SEO, content, social) that verify whether a fix actually
    landed.

    When to call: the user wants a deeper diagnostic of what's
    detectable on their site, or asks "what's still broken after my
    fixes." Use ``mode="cache"`` to read from the most recent crawl
    (fast, no live HTTP); ``mode="fresh"`` to run live HTTP fetches
    against the user's site (slower, ~30+ seconds, more accurate).

    Args:
        ctx: MCP context
        recommendation_job_id: The ARQ recommendation job ID
        mode: "cache" (default — read from recent crawl) or "fresh"
            (live HTTP fetches)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    if mode not in ("cache", "fresh"):
        return {
            "error": True,
            "message": "mode must be 'cache' or 'fresh'",
        }
    try:
        return _truncate_response(
            cited_ctx.client.get(
                endpoints.RECOMMEND_CHECK_STATUS.format(job_id=recommendation_job_id),
                params={"mode": mode},
            )
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Validate Recommendation",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),  # noqa: E501
)
@log_tool_call
async def validate_recommendation(
    ctx: Context[Any, CitedContext, Any],
    recommendation_id: str,
) -> Any:
    """Re-run the deterministic check for a single recommendation.

    Returns ``{job_id, recommendation_id, check_id, mode}``. The
    validation runs asynchronously on the worker; poll the returned
    ``job_id`` (it's an ARQ job id, but lives outside the audit/recommend/
    solution job-type set so ``get_job_status`` won't probe it cleanly —
    instead, fetch the result via ``get_recommendation_validation_latest``
    after a few seconds). The server picks ``mode`` (fresh vs. cache)
    based on a feature flag; the request body has no mode parameter.

    When to call: the user just told you they made a fix
    ("added the FAQ schema", "fixed the canonical tag") and wants to
    confirm it's live. Cheaper than re-running the full audit.

    Args:
        ctx: MCP context
        recommendation_id: The recommendation row ID (not the audit
            job ID — get this from ``get_recommendation_result`` or
            from the ``priority_actions`` list inside ``get_business_hq``).
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.post(
            endpoints.RECOMMEND_VALIDATE.format(recommendation_id=recommendation_id)
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Recommendation Validation (Latest)",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_recommendation_validation_latest(
    ctx: Context[Any, CitedContext, Any],
    recommendation_id: str,
) -> Any:
    """Fetch the most recent stored validation result for a recommendation.

    Returns ``{id, recommendation_id, check_id, status, trigger,
    evidence, fetched_at, created_at}``. ``status`` is the headline:
    ``"valid"`` (the fix is live), ``"invalid"`` (still missing),
    ``"inconclusive"`` (couldn't verify, often because the check needed
    a live fetch and got blocked).

    When to call: avoid re-running the check; just read the latest
    stored result. Pair with ``validate_recommendation`` — call validate
    first, wait a few seconds for the worker to finish, then read here.

    Args:
        ctx: MCP context
        recommendation_id: The recommendation row ID
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(
            endpoints.RECOMMEND_VALIDATE_LATEST.format(
                recommendation_id=recommendation_id
            )
        )
    except CitedAPIError as e:
        return _api_error_response(e)
