from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from cited_cli.config.constants import ENVIRONMENTS
from cited_cli.config.manager import VALID_KEYS, VALID_OUTPUT_VALUES, ConfigManager
from cited_cli.output.formatter import OutputContext, print_error, print_result, print_success
from cited_cli.output.tables import render_kv, render_table
from cited_cli.utils.errors import ExitCode
from cited_cli.utils.interactive import prompt_choice, prompt_if_missing

config_app = typer.Typer(name="config", help="Manage CLI configuration.")


def _get_ctx(ctx: typer.Context) -> tuple[OutputContext, ConfigManager, str]:
    obj = ctx.obj or {}
    out = obj.get("output", OutputContext())
    cfg = obj.get("config", ConfigManager())
    profile = obj.get("profile", "default")
    return out, cfg, profile


@config_app.command("set")
def config_set(
    ctx: typer.Context,
    key: Annotated[str | None, typer.Argument(help="Config key to set")] = None,
    value: Annotated[str | None, typer.Argument(help="Value to set")] = None,
) -> None:
    """Set a configuration value."""
    out, cfg, profile = _get_ctx(ctx)
    key = prompt_choice(key, "KEY", "Select config key:", sorted(VALID_KEYS), out)

    if key not in VALID_KEYS:
        print_error(f"Unknown config key: {key}. Valid keys: {', '.join(sorted(VALID_KEYS))}", out)
        raise typer.Exit(ExitCode.VALIDATION_ERROR)

    if key == "environment":
        value = prompt_choice(value, "VALUE", "Select environment:", list(ENVIRONMENTS.keys()), out)
    elif key == "output":
        value = prompt_choice(
            value, "VALUE", "Select output format:",
            sorted(VALID_OUTPUT_VALUES), out,
        )
    else:
        value = prompt_if_missing(value, "VALUE", f"Value for {key}", out)

    if key == "environment" and value not in ENVIRONMENTS:
        print_error(
            f"Unknown environment: {value}. Valid: {', '.join(ENVIRONMENTS.keys())}", out
        )
        raise typer.Exit(ExitCode.VALIDATION_ERROR)

    if key == "output" and value not in VALID_OUTPUT_VALUES:
        print_error(
            f"Unknown output format: {value}. Valid: {', '.join(sorted(VALID_OUTPUT_VALUES))}", out
        )
        raise typer.Exit(ExitCode.VALIDATION_ERROR)

    cfg.set(key, value, profile)
    suffix = f" (profile: {profile})" if profile != "default" else ""
    print_success(f"Set {key} = {value}{suffix}", out)


@config_app.command("get")
def config_get(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Config key to read")],
) -> None:
    """Get a configuration value."""
    out, cfg, profile = _get_ctx(ctx)
    value = cfg.get(key, profile)
    if value is None:
        print_error(f"Key '{key}' is not set", out)
        raise typer.Exit(ExitCode.NOT_FOUND)
    print_result({key: value}, out, human_formatter=lambda d, c: c.print(value))


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Show all configuration values."""
    out, cfg, profile = _get_ctx(ctx)
    data = cfg.get_all(profile)
    if not data:
        print_error("No configuration set", out)
        raise typer.Exit(ExitCode.NOT_FOUND)
    print_result(
        data,
        out,
        human_formatter=lambda d, c: render_kv(f"Config ({profile})", d, c),
    )


@config_app.command("environments")
def config_environments(ctx: typer.Context) -> None:
    """List available environments and their API URLs."""
    out, cfg, profile = _get_ctx(ctx)
    current_env = cfg.get_environment(profile, (ctx.obj or {}).get("env_override"))
    rows = []
    env_data = {}
    for name, url in ENVIRONMENTS.items():
        active = "→" if name == current_env else ""
        rows.append([active, name, url])
        env_data[name] = {"url": url, "active": name == current_env}

    def _human(data: dict[str, object], console: Console) -> None:
        render_table("Environments", ["", "Name", "API URL"], rows, console)

    print_result(env_data, out, human_formatter=_human)
