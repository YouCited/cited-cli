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
    title="Compare Audits",
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),  # noqa: E501
)
@log_tool_call
async def compare_audits(
    ctx: Context[Any, CitedContext, Any],
    audit_id: str,
    baseline_id: str,
) -> Any:
    """Compare two audits and return per-question changes plus aggregate deltas.

    When to call: the user asks "what changed since the last audit" / "are
    we improving" / "show me the week-over-week delta." Compute the diff
    here instead of summarizing two audit reports back to back. Doesn't run
    a new audit — cheap and idempotent.

    Use ``list_audits`` to find a prior completed audit on the same template
    and pass its job_id as ``baseline_id``.

    Error handling: failures return a structured ``detail`` body with
    ``error_type`` and (where applicable) ``offending_id`` so you can tell
    the user which audit caused the problem. Possible ``error_type`` values:

    - ``audit_not_found`` (404) — the current audit doesn't exist; the id
      may have been deleted or mistyped.
    - ``baseline_not_found`` (404) — the baseline audit doesn't exist.
    - ``audit_access_denied`` (403) — the current audit belongs to a
      different account; the user can't compare across accounts.
    - ``baseline_access_denied`` (403) — same as above for the baseline.
    - ``same_audit`` (422) — both ids are identical; ask for a different
      ``baseline_id``.
    - ``mismatched_named_audits`` (422) — the two audits use different
      named-audit templates and aren't comparable.

    On a ``payment_required: true`` response (HTTP 402), show the user
    ``buy_url`` (or a checkout link from buy_audit / buy_credits) and retry
    after they pay.

    Args:
        ctx: MCP context
        audit_id: The current audit job ID
        baseline_id: A prior completed audit job ID to compare against. Must
            be a different job than ``audit_id``.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return _truncate_response(
            cited_ctx.client.get(
                endpoints.ANALYTICS_COMPARE.format(audit_id=audit_id, baseline_id=baseline_id)
            )
        )
    except CitedAPIError as e:
        return _api_error_response(e)
