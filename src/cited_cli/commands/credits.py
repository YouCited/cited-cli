from __future__ import annotations

from typing import Annotated, Any

import typer
from rich.console import Console

from cited_cli.output.formatter import print_error, print_result
from cited_cli.output.tables import render_kv, render_table
from cited_cli.utils.client import get_authed_client, get_public_client
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error
from cited_cli.utils.interactive import can_prompt
from cited_core.api import endpoints

credits_app = typer.Typer(
    name="credits",
    help="Pay-as-you-go credits: prices, balance, purchases, refunds, auto-refill.",
)


def _usd(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value or "")


def _render_prices(d: dict[str, Any], console: Console) -> None:
    audit = d.get("audit") or {}
    single = d.get("single_audit") or {}
    refill = d.get("auto_refill") or {}
    render_kv(
        "Cited Prices (1 credit = $1)",
        {
            "Standard audit": (
                f"{audit.get('credits', '?')} credits "
                f"(up to {audit.get('questions_included', '?')} questions)"
            ),
            "Each extra model": f"{audit.get('extra_model_credits', '?')} credits",
            "One-off audit": (
                f"{_usd(single.get('price_usd'))} for {single.get('credits', '?')} credits "
                "(no account claim needed)"
            ),
            "Credits expire after": f"{d.get('credits_expire_after_months', '?')} months",
            "Refund window": f"{d.get('refund_window_days', '?')} days (unused credits)",
            "Auto-refill bonus": f"{refill.get('bonus_percent', '?')}%",
        },
        console,
    )
    rows = [
        [
            p.get("id", ""),
            _usd(p.get("price_usd")),
            str(p.get("credits", "")),
            f"{p.get('bonus_percent', 0)}%",
        ]
        for p in d.get("packs", [])
    ]
    render_table("Credit packs", ["Pack", "Price", "Credits", "Bonus"], rows, console)
    console.print("\nBuy a pack: [bold]cited credits buy <pack>[/bold]")


@credits_app.command("prices")
def credits_prices(ctx: typer.Context) -> None:
    """Show credit prices and packs. No login needed."""
    out, client = get_public_client(ctx)
    try:
        data = client.get(endpoints.BILLING_PRICES)
        print_result(data, out, human_formatter=_render_prices)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


def _render_balance(d: dict[str, Any], console: Console) -> None:
    card = d.get("saved_card")
    card_text = f"{card.get('brand', '')} ****{card.get('last4', '')}" if card else "none"
    refill = d.get("auto_refill") or {}
    if refill.get("enabled"):
        refill_text = (
            f"on ({refill.get('pack_id')}, cap {_usd(refill.get('monthly_cap_usd'))}/month, "
            f"spent {_usd(refill.get('spent_this_month_usd'))})"
        )
        if refill.get("paused"):
            refill_text += f" - PAUSED: {refill.get('pause_reason') or 'see billing page'}"
    else:
        refill_text = "off"
    render_kv(
        "Credits",
        {
            "Balance": f"{d.get('balance', 0)} credits",
            "Has purchased": "yes" if d.get("has_purchased") else "no",
            "Account": "unclaimed agent account" if d.get("unclaimed") else "claimed",
            "Saved card": card_text,
            "Auto-refill": refill_text,
        },
        console,
    )
    lots = d.get("lots") or []
    if lots:
        rows = [
            [
                lot.get("source", ""),
                f"{lot.get('credits_remaining', 0)}/{lot.get('credits_granted', 0)}",
                _usd(lot.get("paid_usd")),
                str(lot.get("expires_at", ""))[:10],
                _usd(lot.get("refundable_usd")),
            ]
            for lot in lots
        ]
        render_table(
            "Credit lots (soonest-expiring spent first)",
            ["Source", "Remaining", "Paid", "Expires", "Refundable"],
            rows,
            console,
        )


@credits_app.command("balance")
def credits_balance(ctx: typer.Context) -> None:
    """Show your credit balance, lots, saved card and auto-refill settings."""
    out, client, _ = get_authed_client(ctx)
    try:
        data = client.get(endpoints.BILLING_CREDITS)
        print_result(data, out, human_formatter=_render_balance)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@credits_app.command("history")
def credits_history(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of entries")] = 50,
) -> None:
    """Show credit transactions (purchases, spends, returns, refunds, expiries)."""
    out, client, _ = get_authed_client(ctx)
    try:
        data = client.get(endpoints.BILLING_CREDIT_TRANSACTIONS, params={"limit": limit})

        def _human(d: dict[str, Any], console: Console) -> None:
            rows = [
                [
                    str(t.get("created_at", ""))[:19],
                    t.get("kind", ""),
                    f"{t.get('delta', 0):+}" if isinstance(t.get("delta"), int) else "",
                    t.get("note") or t.get("reference_type") or "",
                ]
                for t in d.get("transactions", [])
            ]
            render_table("Credit history", ["When", "Kind", "Credits", "Note"], rows, console)

        print_result(data, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


def _print_checkout(d: dict[str, Any], console: Console, what: str) -> None:
    console.print(f"\n[bold]Open this link to pay for {what}:[/bold]")
    console.print(f"  [bold cyan]{d.get('checkout_url', '')}[/bold cyan]\n")
    console.print(
        "Nothing has been charged yet. After payment the credits appear in: "
        "[bold]cited credits balance[/bold]"
    )


@credits_app.command("buy")
def credits_buy(
    ctx: typer.Context,
    pack_id: Annotated[str, typer.Argument(help="Pack ID, e.g. pack_20, pack_50, pack_100")],
    save_card: Annotated[
        bool,
        typer.Option("--save-card/--no-save-card", help="Save the card for auto-refill"),
    ] = True,
) -> None:
    """Get a checkout link for a credit pack (needs a claimed account)."""
    out, client, _ = get_authed_client(ctx)
    try:
        data = client.post(
            endpoints.BILLING_CREDITS_CHECKOUT,
            json={"pack_id": pack_id, "save_card": save_card},
        )
        print_result(data, out, human_formatter=lambda d, c: _print_checkout(d, c, pack_id))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@credits_app.command("buy-audit")
def credits_buy_audit(ctx: typer.Context) -> None:
    """Get a $15 checkout link for one audit (10 credits). Works for unclaimed accounts."""
    out, client, _ = get_authed_client(ctx)
    try:
        data = client.post(endpoints.BILLING_AUDIT_CHECKOUT, json={})
        print_result(data, out, human_formatter=lambda d, c: _print_checkout(d, c, "one audit"))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@credits_app.command("refund")
def credits_refund(
    ctx: typer.Context,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Refund unused credits bought in the last 30 days (pro rata to price)."""
    out, client, _ = get_authed_client(ctx)
    try:
        if not yes:
            if not can_prompt(out):
                print_error("Refunds need confirmation. Re-run with --yes.", out)
                raise typer.Exit(ExitCode.VALIDATION_ERROR)
            balance = client.get(endpoints.BILLING_CREDITS)
            refundable = sum(
                float(lot.get("refundable_usd") or 0) for lot in balance.get("lots") or []
            )
            typer.confirm(
                f"Refund {_usd(refundable)} and remove the unused credits it covers?",
                abort=True,
            )
        data = client.post(endpoints.BILLING_CREDITS_REFUND, json={})
        print_result(
            data,
            out,
            human_formatter=lambda d, c: render_kv(
                "Refund",
                {
                    "Refunded": _usd(d.get("refunded_usd")),
                    "Credits removed": d.get("credits_removed", 0),
                    "Lots": len(d.get("lots") or []),
                },
                c,
            ),
        )
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@credits_app.command("auto-refill")
def credits_auto_refill(
    ctx: typer.Context,
    enabled: Annotated[
        bool,
        typer.Option("--on/--off", help="Turn auto-refill on or off"),
    ],
    pack_id: Annotated[
        str | None, typer.Option("--pack", help="Pack to buy when the balance drops below 10")
    ] = None,
    monthly_cap_usd: Annotated[
        float | None, typer.Option("--cap", help="Monthly spending ceiling in USD")
    ] = None,
) -> None:
    """Turn auto-refill on or off (needs a saved card and a claimed account)."""
    out, client, _ = get_authed_client(ctx)
    payload: dict[str, Any] = {"enabled": enabled}
    if pack_id is not None:
        payload["pack_id"] = pack_id
    if monthly_cap_usd is not None:
        payload["monthly_cap_usd"] = monthly_cap_usd
    try:
        data = client.put(endpoints.BILLING_AUTO_REFILL, json=payload)
        print_result(data, out, human_formatter=_render_balance)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


def render_quote(d: dict[str, Any], console: Console) -> None:
    render_kv(
        "Audit quote",
        {
            "Cost": f"{d.get('credits', '?')} credits",
            "Questions": d.get("question_count", "?"),
            "Extra models": ", ".join(d.get("extra_models") or []) or "none",
            "Balance": f"{d.get('balance', '?')} credits",
            "Enough credits": "yes" if d.get("enough") else "no",
        },
        console,
    )
    if not d.get("enough"):
        console.print(
            "\nTop up with [bold]cited credits buy <pack>[/bold] "
            "or [bold]cited credits buy-audit[/bold]."
        )

