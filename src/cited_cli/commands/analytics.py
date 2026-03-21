from __future__ import annotations

from typing import Annotated

import typer

from cited_cli.output.formatter import OutputContext, print_error, print_result
from cited_cli.output.tables import render_kv
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error
from cited_core.api import endpoints
from cited_core.api.client import CitedClient
from cited_core.auth.store import TokenStore
from cited_core.config.manager import ConfigManager

analytics_app = typer.Typer(name="analytics", help="Analytics and trend data.")


def _get_client(ctx: typer.Context) -> tuple[OutputContext, CitedClient]:
    obj = ctx.obj or {}
    out: OutputContext = obj.get("output", OutputContext())
    cfg: ConfigManager = obj.get("config", ConfigManager())
    profile = obj.get("profile", "default")
    env = cfg.get_environment(profile, obj.get("env_override"))
    api_url = cfg.get_api_url(profile, obj.get("env_override"))

    store = TokenStore()
    token = store.get_token(env)
    if not token:
        print_error(f"Not logged in to {env}. Run: cited login", out)
        raise typer.Exit(ExitCode.AUTH_ERROR)

    return out, CitedClient(base_url=api_url, token=token)


@analytics_app.command("compare")
def analytics_compare(
    ctx: typer.Context,
    audit_id: Annotated[str, typer.Argument(help="Audit ID to compare against baseline")],
) -> None:
    """Compare an audit against its baseline."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.ANALYTICS_COMPARISON.format(audit_id=audit_id)
        data = client.get(path)
        print_result(data, out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@analytics_app.command("trends")
def analytics_trends(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """Show KPI trends over time."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.ANALYTICS_TRENDS.format(business_id=business_id)
        data = client.get(path)
        print_result(data, out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@analytics_app.command("summary")
def analytics_summary(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """Get analytics summary for a business."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.ANALYTICS_SUMMARY.format(business_id=business_id)
        data = client.get(path)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Analytics Summary", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()
