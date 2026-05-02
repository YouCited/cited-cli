from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from cited_core.api import endpoints
from cited_core.errors import CitedAPIError
from cited_mcp.context import CitedContext
from cited_mcp.plan_gating import tools_unlocked_between
from cited_mcp.server import mcp
from cited_mcp.tools._helpers import (
    _api_error_response,
    _extract_user,
    _get_ctx,
    _resolve_token,
    log_tool_call,
)

logger = logging.getLogger("cited_mcp.usage")


@mcp.tool(
    title="Get Pricing",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_pricing(ctx: Context[Any, CitedContext, Any]) -> Any:
    """Get available subscription plans and pricing.

    Returns plan tiers (Growth, Scale, Pro) with monthly prices,
    capabilities, and limits. Use this to show the user their
    upgrade options before calling upgrade_plan.
    """
    cited_ctx = _get_ctx(ctx)
    try:
        return cited_ctx.client.get(endpoints.BILLING_PRICING)
    except CitedAPIError as e:
        return _api_error_response(e)


_RECONNECT_HINT = (
    "Disconnect and reconnect the Cited connector in your Claude Desktop or "
    "Claude.ai connector settings to access the new tools."
)


def _build_tools_unlocked(
    old_tier: str | None, new_tier: str | None
) -> list[dict[str, str]]:
    """Build [{name, description}] entries for tools unlocked by the tier change.

    Looks up live descriptions from the registered MCP tool surface so each
    entry stays accurate as docstrings evolve.
    """
    unlocked_names = tools_unlocked_between(old_tier, new_tier)
    if not unlocked_names:
        return []
    descriptions: dict[str, str] = {
        tool.name: tool.description or ""
        for tool in mcp._tool_manager.list_tools()
    }
    return [
        {"name": name, "description": descriptions.get(name, "")}
        for name in sorted(unlocked_names)
    ]


def _pending_action_for(action: str | None, checkout_url: str | None) -> str | None:
    """Map the backend's `action` field to a pending_action string.

    Always returns a value or None — never branches the *presence* of the field
    in the response. Per direction: agent code is easier to write against an
    always-present nullable field than against a conditional branch.
    """
    if action == "checkout_required":
        if checkout_url:
            return (
                f"Open {checkout_url} to complete checkout, then disconnect "
                f"and reconnect the Cited connector to access the new tools."
            )
        return (
            "Complete checkout (no checkout_url returned — see message field), "
            "then disconnect and reconnect the Cited connector."
        )
    if action == "upgraded":
        return _RECONNECT_HINT
    # already_on_plan or unknown action: no pending action
    return None


async def _safe_send_list_changed(
    ctx: Context[Any, CitedContext, Any],
    *,
    tool_name: str,
    user: str,
) -> None:
    """Send tools/list_changed; swallow + log on failure.

    Compatible clients refresh their tool list immediately and the user sees
    the new tools without reconnecting. Incompatible clients ignore it and
    fall back to the `pending_action` field's reconnect hint.
    """
    try:
        await ctx.session.send_tool_list_changed()
    except Exception as e:  # noqa: BLE001 — we explicitly want to swallow
        request_id = getattr(
            getattr(ctx, "request_context", None), "request_id", None
        )
        logger.info(
            json.dumps(
                {
                    "event": "tools_list_changed_send_failed",
                    "tool": tool_name,
                    "user": user,
                    "session_id": str(request_id) if request_id else None,
                    "error_type": type(e).__name__,
                    "error_message": str(e)[:200],
                }
            )
        )


@mcp.tool(
    title="Upgrade Plan",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def upgrade_plan(
    ctx: Context[Any, CitedContext, Any],
    target_tier: str,
) -> Any:
    """Upgrade the user's subscription plan to unlock more tools.

    Returns the backend response augmented with two always-present fields:

      * ``tools_unlocked`` — list of ``{name, description}`` for tools that
        become available at the new tier. Empty when no tier change took
        effect (already_on_plan or checkout_required).
      * ``pending_action`` — nullable string describing what the user needs
        to do next. ``null`` when nothing is pending; for ``upgraded`` it
        instructs disconnect/reconnect to pick up the new tools; for
        ``checkout_required`` it points at the checkout URL.

    For users with a payment method on file the upgrade takes effect
    immediately. For first-time subscribers the response includes a
    ``checkout_url`` that must be opened once.

    On a successful immediate upgrade the server also emits a
    ``notifications/tools/list_changed`` MCP notification on the per-request
    SSE stream — clients that honor it refresh their tool list automatically
    and the user sees the new tools without needing to reconnect. Clients
    that don't honor it fall back to ``pending_action``.

    Args:
        ctx: MCP context
        target_tier: Target plan: growth ($39/mo), scale ($99/mo), or pro
            ($299/mo)
    """
    cited_ctx = _get_ctx(ctx)
    token = _resolve_token(ctx)
    user = _extract_user(token) if token else "anonymous"

    # Read current tier directly. We bypass the tier cache here because we
    # want a fresh value for THIS request so the tools_unlocked diff is
    # accurate to what the user actually had a moment ago, not whatever was
    # cached up to 5 minutes earlier.
    old_tier: str | None
    try:
        me_before = cited_ctx.client.get(endpoints.ME)
        old_tier = str(me_before.get("subscription_tier") or "free")
    except CitedAPIError:
        old_tier = None

    try:
        backend = cited_ctx.client.post(
            endpoints.BILLING_AGENT_UPGRADE,
            json={"target_tier": target_tier},
        )
    except CitedAPIError as e:
        return _api_error_response(e)

    if not isinstance(backend, dict):
        # Unexpected shape — pass through unchanged so callers can debug.
        return backend

    action = backend.get("action")
    # For checkout_required the upgrade hasn't taken effect yet, so the
    # effective new_tier is the old_tier (no tools unlocked yet).
    new_tier = backend.get("tier") if action != "checkout_required" else old_tier

    tools_unlocked = (
        _build_tools_unlocked(old_tier, new_tier) if action == "upgraded" else []
    )
    pending_action = _pending_action_for(action, backend.get("checkout_url"))

    response = dict(backend)
    response["tools_unlocked"] = tools_unlocked
    response["pending_action"] = pending_action

    # Belt-and-suspenders: send the protocol notification too. Failures are
    # swallowed and structured-logged so we can see in production whether
    # any clients ever surface a deliverable session.
    if action == "upgraded" and tools_unlocked:
        await _safe_send_list_changed(ctx, tool_name="upgrade_plan", user=user)

    return response
