"""`cited fix`: generate_fixes, get_fixes and update_fix."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markdown import Markdown

from cited_cli.commands.audit import _confirm_and_rerun
from cited_cli.output.formatter import print_result, print_success
from cited_cli.output.tables import render_table
from cited_cli.utils.tools import call, clean, render, run

fix_app = typer.Typer(help="Fix files for recommendations, and checking them live.",
                      no_args_is_help=True)

AuditOpt = Annotated[
    str | None, typer.Option("--audit", "-a", help="Audit id (default: the newest)")
]


@fix_app.command("generate")
def generate(
    ctx: typer.Context,
    item_keys: Annotated[
        list[str] | None, typer.Argument(help="Recommendation item keys (up to 10)")
    ] = None,
    all_items: Annotated[bool, typer.Option("--all", help="Every open item")] = False,
    audit: AuditOpt = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Spend without asking")] = False,
) -> None:
    """Write the fix files and steps for recommendations. Asks before spending."""
    args = clean({"item_keys": item_keys, "all": all_items, "audit_id": audit})
    result, out = _confirm_and_rerun(ctx, "generate_fixes", args, yes)
    print_result(result, out, human_formatter=render)


def _list(data: dict[str, Any], console: Console) -> None:
    render_table(
        "Fixes",
        ["fix_id", "state", "item", "files", "created_at"],
        [[f.get("fix_id"), f.get("state"), f.get("item"), f.get("files"), f.get("created_at")]
         for f in data.get("fixes") or []],
        console,
    )
    console.print("Files and steps: cited fix get FIX_ID")


@fix_app.command("list")
def list_fixes(
    ctx: typer.Context,
    audit: AuditOpt = None,
    business: Annotated[str | None, typer.Option("--business", "-b")] = None,
    state: Annotated[
        str | None,
        typer.Option("--state", help="generating, ready, done, verified, working, failed"),
    ] = None,
) -> None:
    """Fixes and their state."""
    run(ctx, "get_fixes", clean({"audit_id": audit, "business_id": business, "state": state}),
        _list)


def _fix(data: dict[str, Any], console: Console) -> None:
    console.print(f"[bold]{data.get('item')}[/bold] ({data.get('state')})")
    steps = data.get("steps")
    if isinstance(steps, dict):
        for key in ("summary", "overview", "instructions"):
            if isinstance(steps.get(key), str):
                console.print(Markdown(steps[key]))
    for f in data.get("files") or []:
        target = f" -> {f['target_page']}" if f.get("target_page") else ""
        console.print(f"\n[bold]{f.get('file_name')}[/bold]{target}")
        if f.get("description"):
            console.print(str(f["description"]), markup=False)
    console.print("\nSave the files: cited fix get FIX_ID --save DIR")
    console.print("When it's live: cited fix done FIX_ID, then cited fix verify FIX_ID")


@fix_app.command("get")
def get(
    ctx: typer.Context,
    fix_id: Annotated[str, typer.Argument(help="From cited fix list")],
    save: Annotated[
        Path | None, typer.Option("--save", help="Write the fix files to this folder")
    ] = None,
) -> None:
    """A fix's files, where each goes, and the steps."""
    result, out = call(ctx, "get_fixes", {"fix_id": fix_id})
    if save is not None:
        save.mkdir(parents=True, exist_ok=True)
        written = []
        for f in result.get("files") or []:
            if f.get("content") is None or not f.get("file_name"):
                continue
            path = save / Path(str(f["file_name"])).name
            path.write_text(str(f["content"]), encoding="utf-8")
            written.append(str(path))
        result["saved"] = written
        if not out.json_mode:
            print_success(f"Saved {len(written)} files to {save}", out)
    print_result(result, out, human_formatter=_fix)


def _update(action: str) -> Any:
    def command(
        ctx: typer.Context,
        fix_id: Annotated[str, typer.Argument(help="From cited fix list")],
    ) -> None:
        run(ctx, "update_fix", {"fix_id": fix_id, "action": action})

    return command


fix_app.command("done", help="Mark a fix as put on the site.")(_update("done"))
fix_app.command("undo", help="Move a fix back to ready.")(_update("undo"))
fix_app.command("verify", help="Re-check the live site for a fix (free).")(_update("verify"))
