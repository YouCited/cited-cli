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
    log_tool_call,
)


@mcp.tool(
    title="Start Recommendations",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
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
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
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
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def get_recommendation_result(ctx: Context[Any, CitedContext, Any], job_id: str) -> Any:
    """Get the full results of a completed recommendation job."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.RECOMMEND_RESULT.format(job_id=job_id))
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Recommendation Insights",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
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

    return insights


@mcp.tool(
    title="List Recommendations",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def list_recommendations(
    ctx: Context[Any, CitedContext, Any], audit_job_id: str
) -> Any:
    """List recommendation history for a specific audit.

    Args:
        ctx: MCP context
        audit_job_id: The audit job ID to list recommendations for
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(
            endpoints.RECOMMEND_HISTORY.format(audit_job_id=audit_job_id)
        )
    except CitedAPIError as e:
        return _api_error_response(e)
