from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from cited_cli.output.formatter import OutputContext, print_error, print_result, print_success
from cited_cli.output.tables import render_kv, render_table
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error
from cited_cli.utils.interactive import prompt_if_missing
from cited_core.api import endpoints
from cited_core.api.client import LONG_TIMEOUT, CitedClient
from cited_core.auth.store import TokenStore
from cited_core.config.manager import ConfigManager

audit_app = typer.Typer(name="audit", help="Run and manage audits.")


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
        print_error(f"Not logged in to {env}. Run: cited login", out)
        raise typer.Exit(ExitCode.AUTH_ERROR)

    return out, CitedClient(base_url=api_url, token=token), env


@audit_app.command("start")
def audit_start(
    ctx: typer.Context,
    named_audit_id: Annotated[
        str | None, typer.Argument(help="Audit template (named audit) ID")
    ] = None,
    business_id: Annotated[
        str | None,
        typer.Option("--business", "-b", help="Business ID override"),
    ] = None,
    providers: Annotated[
        list[str] | None,
        typer.Option("--provider", help="Citation provider to use (repeatable)"),
    ] = None,
) -> None:
    """Start a new audit job from a template."""
    out, client, _ = _get_client(ctx)
    named_audit_id = prompt_if_missing(
        named_audit_id, "NAMED_AUDIT_ID", "Audit template ID", out
    )
    try:
        payload: dict[str, object] = {"named_audit_id": named_audit_id}
        if business_id:
            payload["business_id"] = business_id
        if providers:
            payload["providers"] = providers
        data = client.post(
            endpoints.AUDIT_START,
            json=payload,
            timeout=LONG_TIMEOUT,
        )
        job_id = data.get("job_id", data.get("id", ""))
        print_result(data, out, human_formatter=lambda d, c: render_kv("Audit Started", d, c))
        if not out.json_mode and job_id:
            out.console.print(f"\nTrack progress: [bold]cited job watch {job_id}[/bold]")
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@audit_app.command("status")
def audit_status(
    ctx: typer.Context,
    job_id: Annotated[str, typer.Argument(help="Audit job ID")],
) -> None:
    """Check audit job status."""
    out, client, _ = _get_client(ctx)
    try:
        path = endpoints.AUDIT_STATUS.format(job_id=job_id)
        data = client.get(path)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Audit Status", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@audit_app.command("result")
def audit_result(
    ctx: typer.Context,
    job_id: Annotated[str, typer.Argument(help="Audit job ID")],
) -> None:
    """Get full audit results."""
    out, client, _ = _get_client(ctx)
    try:
        path = endpoints.AUDIT_RESULT.format(job_id=job_id)
        data = client.get(path)
        print_result(data, out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@audit_app.command("list")
def audit_list(
    ctx: typer.Context,
    business_id: Annotated[
        str | None,
        typer.Option("--business", "-b", help="Filter by business ID"),
    ] = None,
) -> None:
    """List audit history."""
    out, client, _ = _get_client(ctx)
    try:
        params = {}
        if business_id:
            params["business_id"] = business_id
        data = client.get(endpoints.AUDIT_HISTORY, params=params or None)
        audits = data if isinstance(data, list) else data.get("audits", data.get("items", []))

        def _human(d: object, console: Console) -> None:
            items = d if isinstance(d, list) else []
            rows = []
            for a in items:
                rows.append([
                    a.get("job_id", a.get("id", ""))[:8],
                    a.get("business_name", ""),
                    a.get("status", ""),
                    a.get("created_at", "")[:19] if a.get("created_at") else "",
                ])
            render_table(
                "Audit History",
                ["Job ID", "Business", "Status", "Created"],
                rows,
                console,
            )

        print_result(audits, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@audit_app.command("export")
def audit_export(
    ctx: typer.Context,
    job_id: Annotated[str, typer.Argument(help="Audit job ID")],
    output_path: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Output file path"),
    ] = None,
) -> None:
    """Export audit as PDF."""
    out, client, _ = _get_client(ctx)
    try:
        path = endpoints.AUDIT_EXPORT_PDF.format(job_id=job_id)
        response = client.post_raw(path, timeout=LONG_TIMEOUT)
        if not response.is_success:
            raise CitedAPIError(response.status_code, f"Export failed ({response.status_code})")

        filename = output_path or f"audit-{job_id[:8]}.pdf"
        with open(filename, "wb") as f:
            f.write(response.content)
        print_success(f"Exported to {filename}", out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()
