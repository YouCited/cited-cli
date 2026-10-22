from __future__ import annotations

import sys
from typing import Annotated

import typer

from cited_cli import __version__
from cited_cli.commands.account import credits_app
from cited_cli.commands.account import status as account_status
from cited_cli.commands.agent import agent_app
from cited_cli.commands.audit import audit_app
from cited_cli.commands.auth import auth_app, do_login, do_logout, do_register
from cited_cli.commands.business import business_app
from cited_cli.commands.config_cmd import config_app
from cited_cli.commands.docs import docs_app
from cited_cli.commands.fix import fix_app
from cited_cli.commands.mcp_cmd import mcp_app
from cited_cli.commands.recommend import recommend_app
from cited_cli.commands.tools_cmd import tools_app
from cited_cli.output.formatter import OutputContext, print_result
from cited_core.config.manager import ConfigManager

app = typer.Typer(
    name="cited",
    help="CLI for the Cited GEO platform.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Each data command runs one of Cited's agent tools (see utils/tools.py), so
# the CLI, cited-mcp and the hosted MCP server behave the same.
app.add_typer(auth_app, name="auth")
app.add_typer(config_app, name="config")
app.add_typer(agent_app, name="agent")
app.add_typer(credits_app, name="credits")
app.add_typer(business_app, name="business")
app.add_typer(audit_app, name="audit")
app.add_typer(recommend_app, name="recommend")
app.add_typer(fix_app, name="fix")
app.add_typer(docs_app, name="docs")
app.add_typer(tools_app, name="tools")
app.add_typer(mcp_app, name="mcp")


def _version_callback(value: bool) -> None:
    if value:
        print(f"cited-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    ctx: typer.Context,
    version: Annotated[
        bool | None,
        typer.Option("--version", "-V", help="Show version and exit", callback=_version_callback,
                     is_eager=True),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help="Output as JSON")
    ] = False,
    text_output: Annotated[
        bool, typer.Option("--text", "-t", help="Output as human-readable text (overrides config)")
    ] = False,
    env: Annotated[
        str | None, typer.Option("--env", "-e", help="Target environment (dev, prod, local)")
    ] = None,
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Config profile to use")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Verbose output")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Minimal output")
    ] = False,
    no_color: Annotated[
        bool, typer.Option("--no-color", help="Disable colored output")
    ] = False,
) -> None:
    """Cited GEO platform CLI."""
    # Auto-detect non-TTY for color
    if not sys.stdout.isatty():
        no_color = True

    config = ConfigManager()
    profile_name = profile or "default"

    # Resolve output format: --json/--text flags take precedence, then config, then default (text)
    if json_output:
        use_json = True
    elif text_output:
        use_json = False
    else:
        use_json = config.get("output", profile_name) == "json"

    output_ctx = OutputContext(
        json_mode=use_json,
        quiet=quiet,
        no_color=no_color,
    )

    ctx.ensure_object(dict)
    ctx.obj["output"] = output_ctx
    ctx.obj["config"] = config
    ctx.obj["profile"] = profile_name
    ctx.obj["env_override"] = env
    ctx.obj["verbose"] = verbose


@app.command()
def version(ctx: typer.Context) -> None:
    """Show the CLI version."""
    obj = ctx.obj or {}
    out: OutputContext = obj.get("output", OutputContext())
    print_result(
        {"version": __version__, "name": "cited-cli"},
        out,
        human_formatter=lambda d, c: c.print(f"cited-cli {d['version']}"),
    )


app.command("status")(account_status)


@app.command()
def login(
    ctx: typer.Context,
    email: Annotated[str | None, typer.Option(help="Email address")] = None,
    password: Annotated[
        str | None, typer.Option(help="Password", hide_input=True)
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option(help="OAuth provider: google, microsoft, github"),
    ] = None,
) -> None:
    """Log in to Cited. Opens browser by default, or use --email for password login."""
    do_login(ctx, email, password, provider)


@app.command()
def logout(ctx: typer.Context) -> None:
    """Log out and clear stored credentials."""
    do_logout(ctx)


@app.command()
def register(
    ctx: typer.Context,
    email: Annotated[str | None, typer.Option(help="Email address")] = None,
    name: Annotated[str | None, typer.Option(help="Full name")] = None,
    password: Annotated[
        str | None, typer.Option(help="Password", hide_input=True)
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option(help="OAuth provider: google, microsoft, github"),
    ] = None,
) -> None:
    """Register a new Cited account. Opens browser or use --email."""
    do_register(ctx, email, name, password, provider)


def main() -> None:
    app()
