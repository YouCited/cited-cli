"""Pay-as-you-go credits: prices, balance, purchases, vouchers, refunds, auto-refill,
quotes.

1 credit = $1. A standard audit costs 10 credits. Purchases happen in Stripe
Checkout: these tools only create checkout links for the human to open, and
never complete a payment themselves.
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
    _truncate_response,
    log_tool_call,
)

_CHECKOUT_INSTRUCTIONS = (
    "Show checkout_url to the human as a clickable link and ask them to pay there. "
    "Nothing has been charged yet, so do not say the purchase is done. After they "
    "pay, call get_credits to confirm the new balance."
)


@mcp.tool(
    title="Get Prices",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_prices(ctx: Context[Any, CitedContext, Any]) -> Any:
    """Get Cited's pay-as-you-go prices. No login needed.

    Prices are in credits; 1 credit = $1. A standard audit is 10 credits and
    covers up to 5 questions with each engine's included models; each further
    5 questions is another 10, each extra model 2. A one-off audit costs $15
    (10 credits) and works for any account, including an unclaimed agent
    account. Credit packs (pack_20, pack_50, pack_100; bigger packs add bonus
    credits) need a claimed account. Credits expire 12 months after purchase
    and unused credits bought in the last 30 days can be refunded.

    Returns ``audit``, ``single_audit``, ``packs`` [{id, price_usd, credits,
    bonus_percent}], ``credits_expire_after_months``, ``refund_window_days``
    and ``auto_refill``.
    """
    cited_ctx = _get_ctx(ctx)
    try:
        return cited_ctx.client.get(endpoints.BILLING_PRICES)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Credits",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def get_credits(ctx: Context[Any, CitedContext, Any]) -> Any:
    """Get the account's credit balance (1 credit = $1).

    Returns ``balance``, ``has_purchased`` (recommendations, solutions, crawls
    and question regeneration need at least one purchase), ``unclaimed`` (an
    agent account a person has not claimed yet), ``lots`` (each purchase with
    credits_remaining, expires_at and refundable_usd), ``saved_card`` and
    ``auto_refill``.

    When to call: before starting an audit (a standard audit is 10 credits),
    after the human says they paid, or when an error says
    ``insufficient_credits``.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.BILLING_CREDITS)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Credit History",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def credit_history(ctx: Context[Any, CitedContext, Any], limit: int = 50) -> Any:
    """List credit transactions, newest first.

    Each entry has ``delta`` (credits added or removed), ``kind`` (purchase,
    grant, spend, return, refund, expire), ``reference_type`` /
    ``reference_id`` (e.g. the audit a spend paid for), ``note`` and
    ``created_at``. Failed or cancelled audits show up as a ``return``.

    Args:
        ctx: MCP context
        limit: Number of transactions to return (default 50)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return _truncate_response(
            cited_ctx.client.get(endpoints.BILLING_CREDIT_TRANSACTIONS, params={"limit": limit})
        )
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Buy Credits",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),  # noqa: E501
)
@log_tool_call
async def buy_credits(
    ctx: Context[Any, CitedContext, Any],
    pack_id: str,
    save_card: bool = True,
) -> Any:
    """Create a Stripe checkout link for a credit pack, for the human to pay.

    Packs: pack_20 ($20, 20 credits), pack_50 ($50, 55 credits), pack_100
    ($100, 120 credits); see get_prices for current values. 1 credit = $1 and
    a standard audit is 10 credits. Packs need a claimed account: an
    unclaimed agent account gets a ``claim_required`` error and should use
    buy_audit ($15 for one audit) instead.

    Returns ``checkout_url``. Show it to the human as a link; nothing is
    charged until they pay there. Never tell them the purchase is complete
    until get_credits shows the new balance.

    Args:
        ctx: MCP context
        pack_id: Pack to buy: pack_20, pack_50 or pack_100
        save_card: Save the card for auto-refill and later purchases (default true)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        result = cited_ctx.client.post(
            endpoints.BILLING_CREDITS_CHECKOUT,
            json={"pack_id": pack_id, "save_card": save_card},
        )
    except CitedAPIError as e:
        return _api_error_response(e)
    if isinstance(result, dict):
        result["instructions"] = _CHECKOUT_INSTRUCTIONS
    return result


@mcp.tool(
    title="Buy One Audit",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),  # noqa: E501
)
@log_tool_call
async def buy_audit(ctx: Context[Any, CitedContext, Any]) -> Any:
    """Create a $15 Stripe checkout link that pays for one audit (10 credits).

    Works for every account, including an unclaimed agent account from
    agent_signup. Returns ``checkout_url``, ``price_usd``, ``credits`` and
    ``expires_at``. Show checkout_url to the human; once they pay, the 10
    credits appear in get_credits and you can call start_audit.

    Nothing is charged by this call. Never say the payment happened until
    get_credits confirms it.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        result = cited_ctx.client.post(endpoints.BILLING_AUDIT_CHECKOUT, json={})
    except CitedAPIError as e:
        return _api_error_response(e)
    if isinstance(result, dict):
        result["instructions"] = _CHECKOUT_INSTRUCTIONS
    return result


@mcp.tool(
    title="Redeem Voucher",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def redeem_voucher(ctx: Context[Any, CitedContext, Any], code: str) -> Any:
    """Redeem a voucher code the human gave you, adding its free credits.

    Each account can redeem a code once. Voucher credits expire 12 months
    after redemption like a pack, can't be refunded, and unlock the extras
    that need a purchase. Needs a claimed account: an unclaimed agent account
    gets ``claim_required`` with a ``claim_url`` to show the human first.

    Returns ``code``, ``name``, ``credits_added``, ``expires_at`` and the new
    ``balance``. Errors: ``voucher_not_found``, ``voucher_expired``,
    ``voucher_used_up``, ``voucher_already_redeemed``.

    Args:
        ctx: MCP context
        code: The voucher code (case doesn't matter)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.post(endpoints.BILLING_CREDITS_REDEEM, json={"code": code})
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Request Refund",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True),  # noqa: E501
)
@log_tool_call
async def request_refund(
    ctx: Context[Any, CitedContext, Any],
    confirm: bool = False,
) -> Any:
    """Refund unused credits bought in the last 30 days, pro rata to price paid.

    Call first with ``confirm=False`` (the default): nothing is refunded and
    you get the refundable amount per purchase. Tell the human the amount and
    only call again with ``confirm=True`` after they explicitly agree. The
    refunded credits are removed from the balance. Credits from older
    purchases are not refundable (``nothing_to_refund`` when there are none).

    Args:
        ctx: MCP context
        confirm: True to actually request the refund, after the human agreed
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        if not confirm:
            credits = cited_ctx.client.get(endpoints.BILLING_CREDITS)
            lots = [
                {
                    "id": lot.get("id"),
                    "source": lot.get("source"),
                    "purchased_at": lot.get("purchased_at"),
                    "credits_remaining": lot.get("credits_remaining"),
                    "refundable_usd": lot.get("refundable_usd"),
                }
                for lot in credits.get("lots") or []
                if lot.get("refundable_usd")
            ]
            total = round(sum(float(lot["refundable_usd"]) for lot in lots), 2)
            return {
                "confirmation_required": True,
                "refundable_usd": total,
                "lots": lots,
                "message": (
                    f"${total:.2f} can be refunded. Ask the human to confirm, then call "
                    "request_refund(confirm=True)."
                    if total
                    else "Nothing to refund: no unused credits bought in the last 30 days."
                ),
            }
        return cited_ctx.client.post(endpoints.BILLING_CREDITS_REFUND, json={})
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Set Auto-Refill",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True),  # noqa: E501
)
@log_tool_call
async def set_auto_refill(
    ctx: Context[Any, CitedContext, Any],
    enabled: bool,
    pack_id: str | None = None,
    monthly_cap_usd: float | None = None,
    confirm: bool = False,
) -> Any:
    """Turn auto-refill on or off.

    When on, Cited buys the chosen pack (with a 20% bonus) on the saved card
    whenever the balance drops below 10 credits, up to a monthly ceiling
    (default $200). It pauses at the ceiling or if the card fails; saving the
    settings again clears a pause. Needs a claimed account and a saved card
    (``no_saved_card`` otherwise: have the human buy a pack with save_card
    first). Only change this when the human asked for it.

    Turning it on charges the saved card later, so it needs ``confirm=True``:
    without it nothing changes and you get ``confirmation_required``. Tell the
    human the pack and ceiling and confirm only after they agree. Turning it
    off needs no confirmation.

    Returns the same body as get_credits.

    Args:
        ctx: MCP context
        enabled: True to turn auto-refill on, False to turn it off
        pack_id: Pack to buy on each refill (pack_20, pack_50, pack_100)
        monthly_cap_usd: Monthly spending ceiling in USD
        confirm: True to turn auto-refill on, after the human agreed
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    if enabled and not confirm:
        return {
            "confirmation_required": True,
            "pack_id": pack_id,
            "monthly_cap_usd": monthly_cap_usd,
            "message": (
                "Auto-refill buys this pack on the saved card whenever the balance "
                "drops below 10 credits, up to the monthly ceiling (default $200). "
                "Ask the human to confirm, then call set_auto_refill again with "
                "confirm=True."
            ),
        }
    payload: dict[str, Any] = {"enabled": enabled}
    if pack_id is not None:
        payload["pack_id"] = pack_id
    if monthly_cap_usd is not None:
        payload["monthly_cap_usd"] = monthly_cap_usd
    try:
        return cited_ctx.client.put(endpoints.BILLING_AUTO_REFILL, json=payload)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Quote Audit",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def quote_audit(
    ctx: Context[Any, CitedContext, Any],
    named_audit_id: str,
    models: list[str] | None = None,
) -> Any:
    """Price an audit in credits before starting it (1 credit = $1).

    A standard audit is 10 credits for up to 5 questions with each engine's
    included models; each further 5 questions adds 10 and each extra model 2.
    Returns ``credits`` (the cost), ``balance``, ``enough``,
    ``question_count`` and ``extra_models``. When ``enough`` is false, offer
    buy_audit ($15, one audit) or buy_credits (claimed accounts) and show the
    human the checkout link.

    Args:
        ctx: MCP context
        named_audit_id: Audit template ID (from list_audit_templates)
        models: Optional "provider:model" ids you plan to pass to start_audit
            (see get_audit_models; models not marked included cost extra)
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    payload: dict[str, Any] = {"named_audit_id": named_audit_id}
    if models:
        payload["models"] = models
    try:
        return cited_ctx.client.post(endpoints.BILLING_AUDIT_QUOTE, json=payload)
    except CitedAPIError as e:
        return _api_error_response(e)
