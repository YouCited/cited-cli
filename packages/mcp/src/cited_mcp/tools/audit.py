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
    title="List Audit Templates",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def list_audit_templates(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """List all audit templates (named audits) for the user.

    Args:
        ctx: MCP context
        business_id: Optional business ID to filter templates by
        limit: Maximum number of results (default 50)
        offset: Number of results to skip (default 0)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if business_id is not None:
            params["business_id"] = business_id
        return cited_ctx.client.get(endpoints.NAMED_AUDITS, params=params)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Audit Template",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def get_audit_template(ctx: Context[Any, CitedContext, Any], named_audit_id: str) -> Any:
    """Get a specific audit template by ID."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(
            endpoints.NAMED_AUDIT.format(named_audit_id=named_audit_id)
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Create Audit Template",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
@log_tool_call
async def create_audit_template(
    ctx: Context[Any, CitedContext, Any],
    name: str,
    business_id: str,
    description: str | None = None,
    questions: list[str] | None = None,
) -> Any:
    """Create a new audit template.

    Args:
        ctx: MCP context
        name: Template name
        business_id: Business ID to associate with
        description: Optional template description
        questions: Optional list of audit questions
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    payload: dict[str, Any] = {"name": name, "business_id": business_id}
    if description is not None:
        payload["description"] = description
    if questions is not None:
        payload["questions"] = [{"question": q} for q in questions]
    try:
        return cited_ctx.client.post(endpoints.NAMED_AUDITS, json=payload)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Update Audit Template",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def update_audit_template(
    ctx: Context[Any, CitedContext, Any],
    named_audit_id: str,
    name: str | None = None,
    description: str | None = None,
    questions: list[str] | None = None,
) -> Any:
    """Update an audit template. Questions replace ALL existing questions if provided.

    Args:
        ctx: MCP context
        named_audit_id: Template ID to update
        name: New template name
        description: New description
        questions: New list of questions (replaces all existing questions). Omit to keep existing.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if questions is not None:
        payload["questions"] = [{"question": q} for q in questions]
    try:
        return cited_ctx.client.put(
            endpoints.NAMED_AUDIT.format(named_audit_id=named_audit_id), json=payload
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Delete Audit Template",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def delete_audit_template(
    ctx: Context[Any, CitedContext, Any], named_audit_id: str
) -> Any:
    """Delete an audit template.

    Args:
        ctx: MCP context
        named_audit_id: Template ID to delete
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        cited_ctx.client.delete(
            endpoints.NAMED_AUDIT.format(named_audit_id=named_audit_id)
        )
        return {"success": True, "message": f"Template {named_audit_id} deleted"}
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Start Audit",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
@log_tool_call
async def start_audit(
    ctx: Context[Any, CitedContext, Any],
    named_audit_id: str,
    business_id: str | None = None,
    providers: list[str] | None = None,
) -> Any:
    """Start an audit using a template. Returns a job_id to poll for status.

    Args:
        ctx: MCP context
        named_audit_id: The audit template ID to run
        business_id: Optional business ID override
        providers: Optional list of citation providers to use (e.g. chatgpt, perplexity, gemini)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    payload: dict[str, Any] = {"named_audit_id": named_audit_id}
    if business_id is not None:
        payload["business_id"] = business_id
    if providers is not None:
        payload["providers"] = providers
    try:
        return cited_ctx.client.post(endpoints.AUDIT_START, json=payload)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Audit Status",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def get_audit_status(ctx: Context[Any, CitedContext, Any], job_id: str) -> Any:
    """Check the status of a running audit job."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.AUDIT_STATUS.format(job_id=job_id))
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Audit Results",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def get_audit_result(ctx: Context[Any, CitedContext, Any], job_id: str) -> Any:
    """Get the results of a completed audit job."""
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        result = cited_ctx.client.get(endpoints.AUDIT_RESULT.format(job_id=job_id))
        return _truncate_response(result)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Export Audit PDF",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def export_audit(ctx: Context[Any, CitedContext, Any], job_id: str) -> Any:
    """Export a completed audit as a PDF report. Returns the download URL.

    Args:
        ctx: MCP context
        job_id: The completed audit job ID
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        result = cited_ctx.client.get(endpoints.AUDIT_EXPORT_PDF.format(job_id=job_id))
        return result
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="List Audits",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
@log_tool_call
async def list_audits(
    ctx: Context[Any, CitedContext, Any],
    business_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """List audit history.

    Args:
        ctx: MCP context
        business_id: Optional business ID to filter audits by
        limit: Maximum number of results (default 50)
        offset: Number of results to skip (default 0)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if business_id is not None:
            params["business_id"] = business_id
        return cited_ctx.client.get(endpoints.AUDIT_HISTORY, params=params)
    except CitedAPIError as e:
        return _api_error_response(e)
