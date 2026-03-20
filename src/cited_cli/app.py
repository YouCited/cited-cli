from __future__ import annotations

import sys
from typing import Annotated

import typer

from cited_cli import __version__
from cited_cli.api import endpoints
from cited_cli.api.client import CitedClient
from cited_cli.commands.agent import agent_app
from cited_cli.commands.analytics import analytics_app
from cited_cli.commands.audit import audit_app
from cited_cli.commands.named_audit import named_audit_app
from cited_cli.commands.auth import auth_app, do_login, do_logout, do_register
from cited_cli.commands.business import business_app
from cited_cli.commands.config_cmd import config_app
from cited_cli.commands.hq import hq_app
from cited_cli.commands.job import job_app
from cited_cli.commands.recommend import recommend_app
from cited_cli.commands.solution import solution_app
from cited_cli.config.manager import ConfigManager
from cited_cli.output.formatter import OutputContext, print_error, print_result
from cited_cli.output.tables import render_kv
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error

app = typer.Typer(
    name="cited",
    help="CLI for the Cited GEO platform.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Register nested subcommand groups
audit_app.add_typer(named_audit_app, name="template")

# Register subcommand groups
app.add_typer(auth_app, name="auth")
app.add_typer(config_app, name="config")
app.add_typer(business_app, name="business")
app.add_typer(audit_app, name="audit")
app.add_typer(recommend_app, name="recommend")
app.add_typer(solution_app, name="solution")
app.add_typer(hq_app, name="hq")
app.add_typer(analytics_app, name="analytics")
app.add_typer(agent_app, name="agent")
app.add_typer(job_app, name="job")


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


@app.command()
def status(ctx: typer.Context) -> None:
    """Check API health."""
    obj = ctx.obj or {}
    out: OutputContext = obj.get("output", OutputContext())
    cfg: ConfigManager = obj.get("config", ConfigManager())
    profile = obj.get("profile", "default")
    api_url = cfg.get_api_url(profile, obj.get("env_override"))
    env = cfg.get_environment(profile, obj.get("env_override"))

    client = CitedClient(base_url=api_url, timeout=10.0)
    try:
        data = client.get(endpoints.HEALTH_READY)
        data["environment"] = env
        data["api_url"] = api_url
        print_result(
            data,
            out,
            human_formatter=lambda d, c: render_kv("API Status", d, c),
        )
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    except Exception as e:
        print_error(f"Cannot reach API at {api_url}: {e}", out)
        raise typer.Exit(ExitCode.ERROR) from e
    finally:
        client.close()


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
