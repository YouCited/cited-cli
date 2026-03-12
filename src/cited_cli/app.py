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
from cited_cli.commands.auth import auth_app
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


@app.callback()
def main_callback(
    ctx: typer.Context,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help="Output as JSON")
    ] = False,
    env: Annotated[
        str | None, typer.Option("--env", "-e", help="Target environment (dev, uat, prod, local)")
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

    output_ctx = OutputContext(
        json_mode=json_output,
        quiet=quiet,
        no_color=no_color,
    )
    config = ConfigManager()

    ctx.ensure_object(dict)
    ctx.obj["output"] = output_ctx
    ctx.obj["config"] = config
    ctx.obj["profile"] = profile or "default"
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
        data = client.get(endpoints.HEALTH)
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


def main() -> None:
    app()
