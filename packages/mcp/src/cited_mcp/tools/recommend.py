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
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
    ),  # noqa: E501
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
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
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
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def get_recommendation_result(ctx: Context[Any, CitedContext, Any], job_id: str) -> Any:
    """Get the full results of a completed recommendation job."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        result = cited_ctx.client.get(endpoints.RECOMMEND_RESULT.format(job_id=job_id))
        return _truncate_response(result)
    except CitedAPIError as e:
        return _api_error_response(e)


# Maps source_type -> (response_key, source_id_field, label_field) so summary
# projection and detail lookup share a single contract. Order matches the
# response key order returned by the backend.
_INSIGHT_CATEGORIES: list[tuple[str, str, str, str]] = [
    ("question_insight", "question_insights", "question_id", "question_text"),
    ("head_to_head", "head_to_head_comparisons", "competitor_domain", "competitor_domain"),
    ("strengthening_tip", "strengthening_tips", "category", "title"),
    ("priority_action", "priority_actions", "id", "title"),
]


def _annotate_insight(item: dict[str, Any], source_type: str, source_id_field: str) -> None:
    """Stamp source_type + source_id on an insight so callers can pass it
    straight into start_solution without remembering the per-category id field."""
    item["source_type"] = source_type
    if source_type == "priority_action":
        # priority_actions historically fall back to category when id is absent.
        item["source_id"] = item.get("id") or item.get("category", "")
    else:
        item["source_id"] = item.get(source_id_field, "")


@mcp.tool(
    title="Get Recommendation Insights",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def get_recommendation_insights(
    ctx: Context[Any, CitedContext, Any],
    job_id: str,
    full: bool = False,
) -> Any:
    """Get actionable insights from a recommendation, with source_type and source_id for solutions.

    By default returns a **summary** with per-category counts and light
    rows (``source_type``, ``source_id``, ``label``, plus a single key
    metric per category — ``risk_level`` for question insights,
    ``overall_winner`` for head-to-heads, ``priority`` for tips/actions).
    Use ``full=True`` to retrieve the complete payload — citations,
    coverage scores, full priority-action descriptions — which can be
    sizeable.

    Categories returned: ``question_insights``,
    ``head_to_head_comparisons``, ``strengthening_tips``,
    ``priority_actions``. Every item carries ``source_type`` and
    ``source_id`` so you can hand it straight to ``start_solution``.

    When to call:
    - Default (summary) — to find the right ``source_id`` to act on
      (``start_solution``) without flooding context.
    - ``full=True`` — only when the user asks to see the underlying
      detail (full question text, full action descriptions, etc.). For
      a single insight, prefer ``get_recommendation_insight_detail``
      instead.

    Args:
        ctx: MCP context
        job_id: The completed recommendation job ID
        full: If True, return the full payload. Default is summary.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        result = cited_ctx.client.get(endpoints.RECOMMEND_RESULT.format(job_id=job_id))
    except CitedAPIError as e:
        return _api_error_response(e)

    if not isinstance(result, dict):
        return result

    if full:
        full_insights: dict[str, Any] = {}
        for source_type, key, id_field, _label_field in _INSIGHT_CATEGORIES:
            items = result.get(key, []) or []
            for item in items:
                if isinstance(item, dict):
                    _annotate_insight(item, source_type, id_field)
            full_insights[key] = items
        return _truncate_response(full_insights)

    summary: dict[str, Any] = {"counts": {}}
    for source_type, key, id_field, label_field in _INSIGHT_CATEGORIES:
        items = result.get(key, []) or []
        rows: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            _annotate_insight(item, source_type, id_field)
            row: dict[str, Any] = {
                "source_type": source_type,
                "source_id": item["source_id"],
                "label": str(item.get(label_field, "") or ""),
            }
            if source_type == "question_insight":
                row["risk_level"] = item.get("risk_level")
            elif source_type == "head_to_head":
                row["overall_winner"] = item.get("overall_winner")
            elif source_type in ("strengthening_tip", "priority_action"):
                row["priority"] = item.get("priority")
            rows.append(row)
        summary[key] = rows
        summary["counts"][key] = len(rows)
    summary["_note"] = (
        "Summary view. Call get_recommendation_insights with full=True for "
        "the complete payload, or get_recommendation_insight_detail with "
        "(job_id, source_type, source_id) to drill into one insight."
    )
    return _truncate_response(summary)


@mcp.tool(
    title="Get Recommendation Insight Detail",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def get_recommendation_insight_detail(
    ctx: Context[Any, CitedContext, Any],
    job_id: str,
    source_type: str,
    source_id: str,
) -> Any:
    """Get the full detail for a single insight from a recommendation.

    Use after ``get_recommendation_insights`` (summary mode) to drill
    into one specific insight. ``source_type`` and ``source_id`` come
    straight from the summary rows.

    Returns the matching item (with its original fields, plus
    ``source_type`` and ``source_id``) wrapped in
    ``{"source_type", "source_id", "insight"}``. If no insight matches,
    returns ``{"error": True, "error_type": "insight_not_found", ...}``
    with the available source_ids for that category so the caller can
    self-correct.

    Args:
        ctx: MCP context
        job_id: The recommendation job ID
        source_type: One of ``question_insight``, ``head_to_head``,
            ``strengthening_tip``, ``priority_action``.
        source_id: The source_id of the insight, from the summary's
            rows array.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err

    category = next((c for c in _INSIGHT_CATEGORIES if c[0] == source_type), None)
    if category is None:
        return {
            "error": True,
            "error_type": "invalid_source_type",
            "message": (
                f"Unknown source_type '{source_type}'. Expected one of: "
                + ", ".join(c[0] for c in _INSIGHT_CATEGORIES)
            ),
            "valid_source_types": [c[0] for c in _INSIGHT_CATEGORIES],
        }
    _, key, id_field, _ = category

    try:
        result = cited_ctx.client.get(endpoints.RECOMMEND_RESULT.format(job_id=job_id))
    except CitedAPIError as e:
        return _api_error_response(e)

    if not isinstance(result, dict):
        return result

    items = result.get(key, []) or []
    available_ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        _annotate_insight(item, source_type, id_field)
        available_ids.append(str(item.get("source_id", "")))
        if str(item.get("source_id", "")) == source_id:
            return _truncate_response(
                {
                    "source_type": source_type,
                    "source_id": source_id,
                    "insight": item,
                }
            )

    return {
        "error": True,
        "error_type": "insight_not_found",
        "message": (
            f"No {source_type} with source_id '{source_id}' on this "
            "recommendation. Call get_recommendation_insights to see "
            "available source_ids."
        ),
        "source_type": source_type,
        "source_id": source_id,
        "available_source_ids": available_ids,
    }


@mcp.tool(
    title="List Recommendations",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
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
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
    ),  # noqa: E501
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
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),  # noqa: E501
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
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
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
            endpoints.RECOMMEND_VALIDATE_LATEST.format(recommendation_id=recommendation_id)
        )
    except CitedAPIError as e:
        return _api_error_response(e)
