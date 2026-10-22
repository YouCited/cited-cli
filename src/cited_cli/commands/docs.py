"""`cited docs`: search_docs."""

from __future__ import annotations

from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markdown import Markdown

from cited_cli.output.tables import render_table
from cited_cli.utils.tools import run

docs_app = typer.Typer(help="Search and read the Cited docs (no login).", no_args_is_help=True)


def _results(data: dict[str, Any], console: Console) -> None:
    results = data.get("results") or []
    if not results:
        console.print(str(data.get("next_step") or "No docs matched."), markup=False)
        return
    render_table(
        f"Docs matching '{data.get('query')}'",
        ["path", "title", "description"],
        [[r.get("path"), r.get("title"), r.get("description") or ""] for r in results],
        console,
    )
    console.print("Read one with: cited docs get <path>")


def _doc(data: dict[str, Any], console: Console) -> None:
    console.print(Markdown(str(data.get("content") or "")))
    console.print(f"\n{data.get('url')}", style="dim", markup=False)


@docs_app.command("search")
def search(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="What to look for")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 5,
) -> None:
    """Search the Cited docs."""
    run(ctx, "search_docs", {"query": query, "limit": limit}, _results)


@docs_app.command("get")
def get(
    ctx: typer.Context,
    path: Annotated[str, typer.Argument(help="A doc path from search, e.g. billing/credits")],
) -> None:
    """Read one doc."""
    run(ctx, "search_docs", {"path": path}, _doc)
