"""MCP tools for prioritised GEO action plans.

These tools compose from the existing HQ_PRIORITY backend endpoint
to give users a simple, ranked checklist of what to do next.
"""

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

# ---------------------------------------------------------------------------
# Effort label helpers (mirrors frontend getEffortLabel logic)
# ---------------------------------------------------------------------------

_EFFORT_LABELS: dict[str, str] = {
    "schema_patch": "Easy (< 1 hour)",
    "faq_block": "Easy (< 1 hour)",
    "trust_signal_fix": "Easy (< 1 hour)",
    "content_update": "Medium (1-4 hours)",
    "conversion_path_fix": "Medium (1-4 hours)",
    "content_new_page": "Hard (4+ hours)",
    "inventory_missing_page": "Hard (4+ hours)",
}

_EFFORT_RANK: dict[str, int] = {
    "easy": 1,
    "medium": 2,
    "hard": 3,
}


def _effort_label(action_type: str) -> str:
    return _EFFORT_LABELS.get(action_type, "Medium (1-4 hours)")


def _effort_bucket(action_type: str) -> str:
    label = _effort_label(action_type)
    if label.startswith("Easy"):
        return "easy"
    if label.startswith("Hard"):
        return "hard"
    return "medium"


def _simplify_action(action: dict[str, Any], rank: int) -> dict[str, Any]:
    """Reduce a full PriorityActionResponse to a checklist-friendly shape."""
    action_type = action.get("action_type", "")
    components = action.get("components", {})
    forecast = action.get("forecast") or {}
    return {
        "rank": rank,
        "id": action.get("id"),
        "title": action.get("title", ""),
        "description": action.get("description", ""),
        "action_type": action_type,
        "effort": _effort_label(action_type),
        "effort_bucket": _effort_bucket(action_type),
        "impact_score": components.get("impact", action.get("impact_score", 0)),
        "priority_score": action.get("priority_score", 0),
        "source_type": action.get("source_type", ""),
        "status": action.get("status", "pending"),
        "forecast_summary": forecast.get("rationale", ""),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Get Action Plan",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
@log_tool_call
async def get_action_plan(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
    limit: int = 10,
    effort_filter: str | None = None,
    source_filter: str | None = None,
) -> Any:
    """Get a prioritised action plan — a ranked checklist of what to do next to improve GEO.

    Returns the top actions sorted by priority score. Each action includes an
    effort estimate, impact score, and a brief forecast of expected improvement.

    Use this when the user asks "What should I do to improve my GEO?" or
    "Give me a checklist of next steps."

    Args:
        ctx: MCP context
        business_id: Business ID (uses default if omitted)
        limit: Maximum actions to return (default 10)
        effort_filter: Filter by effort level: "easy", "medium", or "hard"
        source_filter: Filter by source. One of:
            "recommendation", "intent", "inventory", "trust_signal", "agentic_path"
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}

    try:
        # Fetch more than requested so we can filter client-side
        fetch_limit = max(limit * 3, 30)
        path = endpoints.HQ_PRIORITY.format(business_id=business_id)
        actions = cited_ctx.client.get(path, params={"limit": fetch_limit})
    except CitedAPIError as e:
        return _api_error_response(e)

    if not isinstance(actions, list):
        actions = []

    # Apply filters
    if effort_filter:
        bucket = effort_filter.lower().strip()
        actions = [a for a in actions if _effort_bucket(a.get("action_type", "")) == bucket]

    if source_filter:
        sf = source_filter.lower().strip()
        actions = [a for a in actions if a.get("source_type", "").lower() == sf]

    # Limit and simplify
    actions = actions[:limit]
    simplified = [_simplify_action(a, rank=i + 1) for i, a in enumerate(actions)]

    return _truncate_response({
        "total_actions": len(simplified),
        "actions": simplified,
        "_checklist_hint": (
            "Present these as a numbered checklist. For each item show: "
            "the rank, title, effort level (Easy/Medium/Hard), and a one-line "
            "description. Group by effort level if the user asks for quick wins."
        ),
    })


@mcp.tool(
    title="Get Quick Wins",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
@log_tool_call
async def get_quick_wins(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
    max_results: int = 5,
) -> Any:
    """Get quick wins — low-effort, high-impact GEO improvements to tackle first.

    Filters priority actions to find items that are easy to implement but have
    high expected impact. Perfect for "what can I do right now?" conversations.

    Args:
        ctx: MCP context
        business_id: Business ID (uses default if omitted)
        max_results: Maximum quick wins to return (default 5)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}

    try:
        path = endpoints.HQ_PRIORITY.format(business_id=business_id)
        actions = cited_ctx.client.get(path, params={"limit": 30})
    except CitedAPIError as e:
        return _api_error_response(e)

    if not isinstance(actions, list):
        actions = []

    # Quick wins: low effort (effort_score <= 40) AND high impact (impact_score >= 60)
    quick_wins = [
        a for a in actions
        if a.get("effort_score", 50) <= 40 and a.get("impact_score", 0) >= 60
    ]

    # Fallback: if no actions pass the filter, return top N by priority_score
    if not quick_wins:
        # Filter to at least easy/medium effort
        quick_wins = [
            a for a in actions
            if _effort_bucket(a.get("action_type", "")) in ("easy", "medium")
        ]
        if not quick_wins:
            quick_wins = actions  # ultimate fallback: just top by priority

    quick_wins = quick_wins[:max_results]
    simplified = [_simplify_action(a, rank=i + 1) for i, a in enumerate(quick_wins)]

    return _truncate_response({
        "total_quick_wins": len(simplified),
        "actions": simplified,
        "_checklist_hint": (
            "These are quick wins — actions that are easy to implement with high "
            "expected impact. Present as a numbered checklist with effort estimates "
            "and briefly explain why each one matters."
        ),
    })


# ---------------------------------------------------------------------------
# Progress tracking tools
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Mark Action Done",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
@log_tool_call
async def mark_action_done(
    ctx: Context[Any, CitedContext, Any],
    action_id: str,
    business_id: str | None = None,
) -> Any:
    """Mark a priority action as completed.

    Use this when the user says they've implemented a recommendation,
    e.g. "I added the FAQ schema" or "I've done item #3".

    Args:
        ctx: MCP context
        action_id: The action ID to mark as completed
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}

    try:
        path = endpoints.HQ_PRIORITY_STATUS.format(
            business_id=business_id, action_id=action_id
        )
        result = cited_ctx.client.patch(path, json={"status": "completed"})
        return {"success": True, "action_id": action_id, "status": "completed", **result}
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Dismiss Action",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
@log_tool_call
async def dismiss_action(
    ctx: Context[Any, CitedContext, Any],
    action_id: str,
    business_id: str | None = None,
) -> Any:
    """Dismiss a priority action (not applicable or already handled outside the platform).

    Args:
        ctx: MCP context
        action_id: The action ID to dismiss
        business_id: Business ID (uses default if omitted)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    business_id = _resolve_business_id(cited_ctx, business_id)
    if not business_id:
        return {"error": True, "message": "business_id is required. Call list_businesses first."}

    try:
        path = endpoints.HQ_PRIORITY_STATUS.format(
            business_id=business_id, action_id=action_id
        )
        result = cited_ctx.client.patch(path, json={"status": "dismissed"})
        return {"success": True, "action_id": action_id, "status": "dismissed", **result}
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Action Progress",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
@log_tool_call
async def get_action_progress(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
) -> Any:
    """Get progress summary — how many actions are completed vs remaining.

    Use this when the user asks "how am I doing?" or "what's my progress?"

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
        path = endpoints.HQ_PRIORITY_SUMMARY.format(business_id=business_id)
        summary = cited_ctx.client.get(path)
        total = summary.get("total", 0)
        completed = summary.get("completed", 0)
        remaining = total - completed - summary.get("dismissed", 0)
        pct = round((completed / total) * 100) if total > 0 else 0
        return {
            **summary,
            "remaining": remaining,
            "completion_pct": pct,
            "_progress_hint": (
                f"You've completed {completed} of {total} actions ({pct}%). "
                f"{remaining} remaining. "
                "Use get_action_plan to see what's next."
            ),
        }
    except CitedAPIError as e:
        return _api_error_response(e)
