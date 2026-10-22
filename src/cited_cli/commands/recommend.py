"""`cited recommend`: get_recommendations and update_recommendation."""

from __future__ import annotations

from typing import Annotated, Any

import typer
from rich.console import Console

from cited_cli.output.tables import render_table
from cited_cli.utils.tools import as_commands, clean, run

recommend_app = typer.Typer(help="What to change so AI cites you.", no_args_is_help=True)

AuditOpt = Annotated[
    str | None, typer.Option("--audit", "-a", help="Audit id (default: the newest)")
]
BusinessOpt = Annotated[
    str | None, typer.Option("--business", "-b", help="Use this business's newest audit")
]


def _list(data: dict[str, Any], console: Console) -> None:
    if data.get("status") and not data.get("items"):
        console.print(as_commands(str(data.get("next_step") or data["status"])), markup=False)
        return
    if data.get("headline"):
        console.print(f"[bold]{data['headline']}[/bold]")
    if data.get("summary"):
        console.print(str(data["summary"]), markup=False)
    rows = []
    for item in data.get("items") or []:
        fix = item.get("fix") or {}
        rows.append(
            [
                item.get("item_key"),
                item.get("title"),
                item.get("risk_level") or item.get("priority") or "",
                item.get("status"),
                fix.get("state") or "",
            ]
        )
    render_table("Recommendations", ["item_key", "what", "priority", "status", "fix"], rows,
                 console)
    price = data.get("fix_price") or {}
    if price:
        console.print(
            f"Fixes: {price.get('included_left')} still included, then "
            f"{price.get('credits_each')} credits each.",
            markup=False,
        )
    console.print("Make fixes: cited fix generate ITEM_KEY... (or --all)")


@recommend_app.command("list")
def list_recommendations(
    ctx: typer.Context,
    audit: AuditOpt = None,
    business: BusinessOpt = None,
    run_id: Annotated[
        str | None, typer.Option("--run", help="A recommendations id")
    ] = None,
    all_items: Annotated[
        bool, typer.Option("--all", help="Include done and dismissed")
    ] = False,
) -> None:
    """The recommendations from an audit, with their status and fixes."""
    args = clean(
        {"audit_id": audit, "business_id": business, "recommendations_id": run_id,
         "include_closed": all_items}
    )
    run(ctx, "get_recommendations", args, _list)


@recommend_app.command("set")
def set_status(
    ctx: typer.Context,
    item_key: Annotated[str, typer.Argument(help="From cited recommend list")],
    status: Annotated[str, typer.Argument(help="open, done or dismissed")],
    audit: AuditOpt = None,
    business: BusinessOpt = None,
) -> None:
    """Mark a recommendation done or dismissed, or open it again."""
    args = clean(
        {"item_key": item_key, "status": status, "audit_id": audit, "business_id": business}
    )
    run(ctx, "update_recommendation", args)
