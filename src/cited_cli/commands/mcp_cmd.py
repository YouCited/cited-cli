from __future__ import annotations

import os
import sys
from typing import Annotated

import typer

mcp_app = typer.Typer(help="MCP server for AI agent integration.", no_args_is_help=True)


@mcp_app.command("serve")
def mcp_serve(
    env: Annotated[
        str | None,
        typer.Option("--env", "-e", help="Target environment (dev, prod, local)"),
    ] = None,
) -> None:
    """Start the MCP server (stdio transport) for AI agent tool calls."""
    try:
        from cited_mcp.server import run_server
    except ImportError:
        print(
            'MCP dependencies not installed. Run: pip install "cited-cli[mcp]"',
            file=sys.stderr,
        )
        raise typer.Exit(1)  # noqa: B904
    if env:
        os.environ["CITED_ENV"] = env
    run_server()
