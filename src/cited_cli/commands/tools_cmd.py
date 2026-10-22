"""`cited tools`: the raw tool list and calls, for scripts and debugging."""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer
from rich.console import Console

from cited_cli.output.formatter import print_result
from cited_cli.output.tables import render_table
from cited_cli.utils.tools import run, tool_client
from cited_core.tools import fetch_manifest

tools_app = typer.Typer(help="List and call Cited's agent tools directly.", no_args_is_help=True)


def _manifest(data: dict[str, Any], console: Console) -> None:
    render_table(
        f"Cited tools ({data.get('version')})",
        ["name", "login", "description"],
        [[t["name"], "yes" if t.get("requires_login") else "no",
          str(t.get("description", ""))[:90]] for t in data.get("tools") or []],
        console,
    )


@tools_app.command("list")
def list_tools(ctx: typer.Context) -> None:
    """The tools, as the API serves them (the same list the MCP servers show)."""
    out, client, _ = tool_client(ctx)
    try:
        manifest = fetch_manifest(client)
    finally:
        client.close()
    print_result(manifest, out, human_formatter=_manifest)


@tools_app.command("call")
def call_tool(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Tool name")],
    arguments: Annotated[
        str, typer.Argument(help="Arguments as a JSON object")
    ] = "{}",
) -> None:
    """Call one tool with JSON arguments, e.g. cited tools call get_audit '{"limit": 5}'."""
    try:
        args = json.loads(arguments)
    except ValueError as e:
        raise typer.BadParameter(f"Not valid JSON: {e}") from e
    if not isinstance(args, dict):
        raise typer.BadParameter("Arguments must be a JSON object")
    run(ctx, name, args)
