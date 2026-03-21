from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from cited_cli.api import endpoints
from cited_cli.mcp.context import CitedContext
from cited_cli.mcp.server import mcp
from cited_cli.mcp.tools._helpers import _api_error_response, _auth_check, _get_ctx
from cited_cli.utils.errors import CitedAPIError


@mcp.tool()
async def start_solution(
    ctx: Context[Any, CitedContext, Any],
    recommendation_job_id: str,
    source_type: str,
    source_id: str,
) -> Any:
    """Start generating a solution for a specific recommendation insight.

    Args:
        ctx: MCP context
        recommendation_job_id: The recommendation job ID
        source_type: One of: question_insight, head_to_head, strengthening_tip, priority_action
        source_id: The source identifier (question_id, competitor_domain, category, etc.)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.post(
            endpoints.SOLUTION_REQUEST,
            json={
                "recommendation_job_id": recommendation_job_id,
                "source_type": source_type,
                "source_id": source_id,
            },
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool()
async def get_solution_status(ctx: Context[Any, CitedContext, Any], job_id: str) -> Any:
    """Check the status of a solution generation job."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.SOLUTION_STATUS.format(job_id=job_id))
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool()
async def get_solution_result(ctx: Context[Any, CitedContext, Any], job_id: str) -> Any:
    """Get the results of a completed solution generation job."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.SOLUTION_RESULT.format(job_id=job_id))
    except CitedAPIError as e:
        return _api_error_response(e)
