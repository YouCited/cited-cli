from __future__ import annotations

from typing import Annotated

import typer

from cited_cli.api import endpoints
from cited_cli.api.client import CitedClient
from cited_cli.auth.store import TokenStore
from cited_cli.config.manager import ConfigManager
from cited_cli.output.formatter import OutputContext, print_error, print_result, print_success
from cited_cli.output.tables import render_bar, render_kv, render_table
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error

business_app = typer.Typer(name="business", help="Manage businesses.")


def _get_client(ctx: typer.Context) -> tuple[OutputContext, CitedClient, str]:
    obj = ctx.obj or {}
    out: OutputContext = obj.get("output", OutputContext())
    cfg: ConfigManager = obj.get("config", ConfigManager())
    profile = obj.get("profile", "default")
    env = cfg.get_environment(profile, obj.get("env_override"))
    api_url = cfg.get_api_url(profile, obj.get("env_override"))

    store = TokenStore()
    token = store.get_token(env)
    if not token:
        print_error(f"Not logged in to {env}. Run: cited auth login", out)
        raise typer.Exit(ExitCode.AUTH_ERROR)

    return out, CitedClient(base_url=api_url, token=token), env


@business_app.command("list")
def business_list(ctx: typer.Context) -> None:
    """List all businesses."""
    out, client, _ = _get_client(ctx)
    try:
        data = client.get(endpoints.BUSINESSES)
        businesses = (
            data if isinstance(data, list)
            else data.get("businesses", data.get("items", [data]))
        )

        def _human(d: list, console) -> None:  # type: ignore[no-untyped-def]
            rows = []
            for b in d:
                rows.append([
                    b.get("id", "")[:8],
                    b.get("name", ""),
                    b.get("website", ""),
                    b.get("industry", ""),
                ])
            render_table("Businesses", ["ID", "Name", "Website", "Industry"], rows, console)

        print_result(businesses, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@business_app.command("get")
def business_get(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """Get business details."""
    out, client, _ = _get_client(ctx)
    try:
        path = endpoints.BUSINESS.format(business_id=business_id)
        data = client.get(path)
        print_result(
            data,
            out,
            human_formatter=lambda d, c: render_kv(
                d.get("name", "Business"),
                {k: v for k, v in d.items() if v is not None and k != "id"},
                c,
            ),
        )
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@business_app.command("create")
def business_create(
    ctx: typer.Context,
    name: Annotated[str, typer.Option(help="Business name")],
    website: Annotated[str, typer.Option(help="Business website URL")],
    industry: Annotated[str | None, typer.Option(help="Industry")] = None,
) -> None:
    """Create a new business."""
    out, client, _ = _get_client(ctx)
    try:
        payload: dict = {"name": name, "website": website}
        if industry:
            payload["industry"] = industry
        data = client.post(endpoints.BUSINESSES, json=payload)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Created Business", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@business_app.command("update")
def business_update(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    name: Annotated[str | None, typer.Option(help="New name")] = None,
    website: Annotated[str | None, typer.Option(help="New website")] = None,
    industry: Annotated[str | None, typer.Option(help="New industry")] = None,
) -> None:
    """Update a business."""
    out, client, _ = _get_client(ctx)
    try:
        payload: dict = {}
        if name is not None:
            payload["name"] = name
        if website is not None:
            payload["website"] = website
        if industry is not None:
            payload["industry"] = industry
        if not payload:
            print_error("No fields to update. Use --name, --website, or --industry.", out)
            raise typer.Exit(ExitCode.VALIDATION_ERROR)
        path = endpoints.BUSINESS.format(business_id=business_id)
        data = client.patch(path, json=payload)
        print_success(f"Updated business {business_id[:8]}", out)
        print_result(data, out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@business_app.command("delete")
def business_delete(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Delete a business."""
    out, client, _ = _get_client(ctx)
    if not yes and not out.json_mode:
        typer.confirm(f"Delete business {business_id}?", abort=True)
    try:
        path = endpoints.BUSINESS.format(business_id=business_id)
        client.delete(path)
        print_success(f"Deleted business {business_id[:8]}", out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@business_app.command("health")
def business_health(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """Show health scores for a business."""
    out, client, _ = _get_client(ctx)
    try:
        path = endpoints.HEALTH_SCORES.format(business_id=business_id)
        data = client.get(path)

        def _human(d: dict, console) -> None:  # type: ignore[no-untyped-def]
            console.print()
            console.print("[bold]Health Scores[/bold]")
            console.print("─" * 50)
            scores = d.get("scores", d)
            if isinstance(scores, dict):
                for label, value in scores.items():
                    if isinstance(value, (int, float)):
                        render_bar(label.replace("_", " ").title(), value, console=console)
            console.print()

        print_result(data, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@business_app.command("crawl")
def business_crawl(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """Trigger a website crawl for a business."""
    out, client, _ = _get_client(ctx)
    try:
        path = endpoints.CRAWL_START.format(business_id=business_id)
        data = client.post(path, timeout=60.0)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Crawl Started", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()
