from __future__ import annotations

from typing import Annotated

import typer

from cited_cli.output.formatter import OutputContext, print_result
from cited_cli.output.tables import render_kv
from cited_cli.utils.client import get_authed_client
from cited_cli.utils.errors import CitedAPIError, handle_api_error
from cited_core.api import endpoints
from cited_core.api.client import CitedClient

analytics_app = typer.Typer(name="analytics", help="Analytics and trend data.")


def _get_client(ctx: typer.Context) -> tuple[OutputContext, CitedClient]:
    out, client, _ = get_authed_client(ctx)
    return out, client


@analytics_app.command("compare")
def analytics_compare(
    ctx: typer.Context,
    audit_id: Annotated[str, typer.Argument(help="Current audit ID")],
    baseline_id: Annotated[
        str, typer.Argument(help="Prior audit ID to compare against")
    ],
) -> None:
    """Compare two audits and show what changed."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.ANALYTICS_COMPARE.format(
            audit_id=audit_id, baseline_id=baseline_id
        )
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


@analytics_app.command("dashboard")
def analytics_dashboard(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """Get the combined analytics dashboard for a business."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.ANALYTICS_DASHBOARD.format(business_id=business_id)
        data = client.get(path)
        print_result(
            data, out, human_formatter=lambda d, c: render_kv("Analytics Dashboard", d, c)
        )
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()
