from __future__ import annotations

import time
from contextlib import nullcontext
from typing import Annotated, Any

import typer
from rich.console import Console

from cited_cli.output.formatter import OutputContext, print_result, print_success
from cited_cli.output.tables import render_kv, render_table
from cited_cli.utils.client import get_authed_client
from cited_cli.utils.errors import CitedAPIError, handle_api_error
from cited_cli.utils.interactive import prompt_if_missing
from cited_core.api import endpoints
from cited_core.api.client import LONG_TIMEOUT, CitedClient
from cited_core.config.manager import ConfigManager
from cited_core.free_audit import check_free_audit, is_finished

audit_app = typer.Typer(name="audit", help="Run and manage audits.")


def _get_client(ctx: typer.Context) -> tuple[OutputContext, CitedClient, str]:
    return get_authed_client(ctx)


FREE_AUDIT_POLL_SECONDS = 15
FREE_AUDIT_MAX_WAIT_SECONDS = 15 * 60


def _render_free_audit(data: dict[str, Any], console: Console) -> None:
    if data.get("status") != "completed":
        render_kv(
            "Free Audit",
            {
                "Domain": data.get("domain", ""),
                "Status": data.get("status", ""),
                "Progress": f"{data.get('progress', 0)}%",
                "Report": data.get("report_url", ""),
            },
            console,
        )
        if data.get("error"):
            console.print(f"[red]{data['error']}[/red]")
        return

    summary = data.get("summary", {})
    render_kv(
        f"Free Audit: {data.get('domain', '')}",
        {
            "Your site cited in": (
                f"{summary.get('questions_where_brand_cited', 0)} of "
                f"{summary.get('questions_checked', 0)} questions"
            ),
            "High-risk questions": summary.get("high_risk_questions", 0),
            "Share of voice": f"{summary.get('share_of_voice') or 0:.0f}%",
            "AI providers": ", ".join(data.get("providers_used") or []),
            "Full report": data.get("share_url", ""),
        },
        console,
    )
    render_table(
        "Questions",
        ["Question", "Risk", "You cited", "AI cited instead"],
        [
            [
                q.get("question", ""),
                q.get("risk_level") or "",
                "yes" if q.get("brand_cited") else "no",
                ", ".join(q.get("cited_domains") or []),
            ]
            for q in data.get("questions", [])
        ],
        console,
    )
    console.print("\nFor more questions and fixes, create an account: [bold]cited register[/bold]")


@audit_app.command("free")
def audit_free(
    ctx: typer.Context,
    url: Annotated[str | None, typer.Argument(help="Website to audit, e.g. example.com")] = None,
    wait: Annotated[
        bool,
        typer.Option("--wait/--no-wait", help="Wait for the audit to finish (2-4 minutes)"),
    ] = True,
) -> None:
    """Run a free GEO visibility audit for any website. No login needed."""
    obj = ctx.obj or {}
    out: OutputContext = obj.get("output", OutputContext())
    cfg: ConfigManager = obj.get("config", ConfigManager())
    api_url = cfg.get_api_url(obj.get("profile", "default"), obj.get("env_override"))
    url = prompt_if_missing(url, "URL", "Website to audit", out)

    client = CitedClient(base_url=api_url)
    try:
        deadline = time.monotonic() + FREE_AUDIT_MAX_WAIT_SECONDS
        # No spinner in JSON mode: stdout must carry only the JSON document.
        status = nullcontext() if out.json_mode else out.console.status("Running free audit...")
        with status as spinner:
            data = check_free_audit(client, url)
            while wait and not is_finished(data) and time.monotonic() < deadline:
                if spinner is not None:
                    spinner.update(f"Running free audit... {data.get('progress', 0)}%")
                time.sleep(FREE_AUDIT_POLL_SECONDS)
                data = check_free_audit(client, url)
        print_result(data, out, human_formatter=_render_free_audit)
        if not out.json_mode and not is_finished(data):
            out.console.print(f"\nCheck again later: [bold]cited audit free {url}[/bold]")
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


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
    models: Annotated[
        list[str] | None,
        typer.Option(
            "--model",
            "-m",
            help=(
                "Model to compare, as provider:model, e.g. anthropic:claude-opus-5-5 "
                "(repeatable; see `cited audit models`)"
            ),
        ),
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
        if models:
            payload["models"] = models
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


@audit_app.command("quote")
def audit_quote(
    ctx: typer.Context,
    named_audit_id: Annotated[str, typer.Argument(help="Audit template (named audit) ID")],
    models: Annotated[
        list[str] | None,
        typer.Option(
            "--model",
            "-m",
            help="Model to include, as provider:model (repeatable; see `cited audit models`)",
        ),
    ] = None,
) -> None:
    """Show how many credits an audit will cost before starting it."""
    from cited_cli.commands.credits import render_quote

    out, client, _ = _get_client(ctx)
    try:
        payload: dict[str, object] = {"named_audit_id": named_audit_id}
        if models:
            payload["models"] = models
        data = client.post(endpoints.BILLING_AUDIT_QUOTE, json=payload)
        print_result(data, out, human_formatter=render_quote)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@audit_app.command("models")
def audit_models(
    ctx: typer.Context,
    job_id: Annotated[
        str | None,
        typer.Argument(help="Audit job ID; omit to list the models an audit can compare"),
    ] = None,
) -> None:
    """Compare AI models for an audit, or list the models you can choose from."""
    out, client, _ = _get_client(ctx)
    try:
        if job_id is None:
            data = client.get(endpoints.AUDIT_MODELS)

            def _human_catalog(d: dict[str, Any], console: Console) -> None:
                extra = d.get("extra_model_credits")
                rows = [
                    [
                        m.get("id", ""),
                        "included" if m.get("included") else f"+{extra or '?'} credits",
                    ]
                    for m in d.get("models", [])
                ]
                render_table("Models you can compare", ["Model", "Cost"], rows, console)
                limit = d.get("max_models_per_audit")
                if limit:
                    console.print(
                        f"\nUse up to {limit} with: cited audit start <template> "
                        "--model provider:model"
                    )

            print_result(data, out, human_formatter=_human_catalog)
            return

        data = client.get(endpoints.AUDIT_MODEL_RESULTS.format(job_id=job_id))

        def _human_results(d: dict[str, Any], console: Console) -> None:
            models = d.get("models", [])
            if not models:
                console.print(f"No per-model results yet (status: {d.get('status', '?')}).")
                return
            rows = [
                [
                    m.get("id", ""),
                    f"{m.get('questions_cited', 0)}/{m.get('questions_answered', 0)}",
                    f"{(m.get('citation_rate') or 0) * 100:.0f}%",
                    f"{(m.get('share_of_citations') or 0) * 100:.0f}%",
                    str(m.get("questions_failed", 0)),
                ]
                for m in models
            ]
            render_table(
                "Citations by model",
                ["Model", "Questions cited", "Citation rate", "Share of citations", "Failed"],
                rows,
                console,
            )

        print_result(data, out, human_formatter=_human_results)
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
