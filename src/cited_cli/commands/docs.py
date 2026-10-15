from __future__ import annotations

from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape

from cited_cli.output.formatter import OutputContext, print_result
from cited_cli.utils.errors import CitedAPIError, handle_api_error
from cited_core import docs as cited_docs

docs_app = typer.Typer(
    name="docs",
    help="Search and read the public Cited documentation (no login needed).",
    no_args_is_help=True,
)


def _get_out(ctx: typer.Context) -> OutputContext:
    obj = ctx.obj or {}
    out: OutputContext = obj.get("output", OutputContext())
    return out


def _render_results(data: dict[str, Any], console: Console) -> None:
    results = data.get("results") or []
    if not results:
        console.print(f"No docs matched [bold]{escape(data.get('query', ''))}[/bold].")
        console.print(f"[dim]{escape(data.get('hint', ''))}[/dim]")
        return
    console.print(f"[bold]Docs matching '{escape(data.get('query', ''))}'[/bold]\n")
    for r in results:
        console.print(f"[bold cyan]{escape(r['title'])}[/bold cyan]  [dim]{r['path']}[/dim]",
                      soft_wrap=True)
        if r.get("description"):
            console.print(f"  {escape(r['description'])}")
    console.print("\n[dim]Read one with: cited docs get <path>[/dim]")


def _render_doc(data: dict[str, Any], console: Console) -> None:
    console.print(Markdown(data.get("content", "")))
    console.print(f"\n[dim]{data.get('url', '')}[/dim]")


@docs_app.command("search")
def docs_search(
    ctx: typer.Context,
    query: Annotated[list[str], typer.Argument(help="Keywords or a question")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 5,
) -> None:
    """Search the Cited docs by keyword."""
    out = _get_out(ctx)
    try:
        data = cited_docs.search_docs(" ".join(query), limit)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
        return
    print_result(data, out, human_formatter=_render_results)


@docs_app.command("get")
def docs_get(
    ctx: typer.Context,
    path: Annotated[
        str, typer.Argument(help="Doc path 'category/slug' (from docs search) or a docs URL")
    ],
) -> None:
    """Show one doc as markdown."""
    out = _get_out(ctx)
    try:
        data = cited_docs.get_doc(path)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
        return
    print_result(data, out, human_formatter=_render_doc)
