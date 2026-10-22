"""`cited status` and `cited credits buy`: account_status and buy_credits."""

from __future__ import annotations

from typing import Annotated, Any

import typer
from rich.console import Console

from cited_cli.output.tables import render_kv, render_table
from cited_cli.utils.tools import as_commands, clean, render, run

credits_app = typer.Typer(help="Buy credits or redeem a voucher.", no_args_is_help=True)


def _status(data: dict[str, Any], console: Console) -> None:
    if not data.get("signed_in"):
        console.print("Not signed in.")
        console.print(as_commands(str(data.get("next_step") or "")), markup=False)
        console.print("Sign in with: cited login (or, for an AI agent: cited agent signup)")
        return
    account = {k: v for k, v in (data.get("account") or {}).items() if v not in (None, "")}
    render_kv("Account", account, console)
    credits = data.get("credits") or {}
    render_kv("Credits", {k: v for k, v in credits.items() if v is not None}, console)
    businesses = data.get("businesses") or []
    if businesses:
        render_table(
            "Businesses",
            ["id", "name", "website"],
            [[b.get("id"), b.get("name"), b.get("website")] for b in businesses],
            console,
        )
    if data.get("notice"):
        console.print(f"→ {data['notice']}", style="yellow", markup=False)
    console.print(f"→ {as_commands(str(data.get('next_step') or ''))}", markup=False)


def status(ctx: typer.Context) -> None:
    """Who is signed in, the credit balance, businesses, prices and the next step."""
    run(ctx, "account_status", {}, _status)


@credits_app.command("buy")
def buy(
    ctx: typer.Context,
    pack_id: Annotated[
        str | None, typer.Argument(help="Credit pack id (run without arguments to list them)")
    ] = None,
    one_audit: Annotated[
        bool, typer.Option("--one-audit", help="Checkout for a single audit instead of a pack")
    ] = False,
    voucher: Annotated[str | None, typer.Option("--voucher", help="Redeem a voucher code")] = None,
    no_save_card: Annotated[
        bool, typer.Option("--no-save-card", help="Don't save the card for later packs")
    ] = False,
) -> None:
    """Get a checkout link for credits or one audit, or redeem a voucher.

    A link only starts a purchase: pay in the browser, then check `cited status`.
    """
    args = clean({"pack_id": pack_id, "one_audit": one_audit, "voucher_code": voucher})
    if no_save_card:
        args["save_card"] = False
    run(ctx, "buy_credits", args, render)
