from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from cited_core.api import endpoints
from cited_core.errors import CitedAPIError
from cited_mcp.context import CitedContext
from cited_mcp.server import mcp
from cited_mcp.tools._helpers import _api_error_response, _auth_check, _get_ctx

_STATUS_ENDPOINTS = {
    "audit": endpoints.AUDIT_STATUS,
    "recommendation": endpoints.RECOMMEND_STATUS,
    "solution": endpoints.SOLUTION_STATUS,
}


@mcp.tool(
    title="Get Job Status",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def get_job_status(
    ctx: Context[Any, CitedContext, Any],
    job_id: str,
    job_type: str | None = None,
) -> Any:
    """Get the status of any job by ID.

    Args:
        ctx: MCP context
        job_id: The job ID to check
        job_type: Optional job type hint: audit, recommendation, or solution.
            If not provided, will probe each type until one responds.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err

    if job_type and job_type in _STATUS_ENDPOINTS:
        try:
            result = cited_ctx.client.get(
                _STATUS_ENDPOINTS[job_type].format(job_id=job_id)
            )
            result["job_type"] = job_type
            return result
        except CitedAPIError as e:
            return _api_error_response(e)

    # Probe each type
    for jtype, endpoint_tpl in _STATUS_ENDPOINTS.items():
        try:
            result = cited_ctx.client.get(endpoint_tpl.format(job_id=job_id))
            result["job_type"] = jtype
            return result
        except CitedAPIError:
            continue

    return {"error": True, "message": f"No job found with ID: {job_id}"}
