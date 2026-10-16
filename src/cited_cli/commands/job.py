from __future__ import annotations

from typing import Annotated

import typer

from cited_cli.output.formatter import OutputContext, print_error, print_result, print_success
from cited_cli.output.progress import watch_job
from cited_cli.output.tables import render_kv
from cited_cli.utils.client import get_authed_client
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error
from cited_cli.utils.interactive import confirm_action
from cited_core.api.client import CitedClient

job_app = typer.Typer(name="job", help="Monitor and manage background jobs.")


def _get_client(ctx: typer.Context) -> tuple[OutputContext, CitedClient]:
    out, client, _ = get_authed_client(ctx)
    return out, client


def _guess_job_type(job_id: str, client: CitedClient) -> str:
    """Try to determine job type by probing status endpoints."""
    for prefix in ["/audit", "/recommendations", "/solutions"]:
        try:
            client.get(f"{prefix}/{job_id}/status")
            return prefix.strip("/")
        except CitedAPIError:
            continue
    return "audit"  # default fallback


@job_app.command("watch")
def job_watch(
    ctx: typer.Context,
    job_id: Annotated[str, typer.Argument(help="Job ID to watch")],
    job_type: Annotated[
        str,
        typer.Option("--type", "-t", help="Job type: audit, recommendations, solutions"),
    ] = "",
    interval: Annotated[
        float,
        typer.Option("--interval", "-i", help="Poll interval in seconds"),
    ] = 2.0,
) -> None:
    """Watch a job's progress until completion."""
    out, client = _get_client(ctx)
    try:
        if not job_type:
            job_type = _guess_job_type(job_id, client)

        status_path = f"/{job_type}/{job_id}/status"
        result = watch_job(client, status_path, out.console, poll_interval=interval)

        status = result.get("status", "unknown")
        if status in ("completed", "complete", "done"):
            print_success(f"Job {job_id[:8]} completed", out)
        elif status in ("failed", "error"):
            print_error(f"Job {job_id[:8]} failed: {result.get('error', '')}", out)
            raise typer.Exit(ExitCode.ERROR)
        else:
            print_result(result, out, human_formatter=lambda d, c: render_kv("Job Result", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@job_app.command("cancel")
def job_cancel(
    ctx: typer.Context,
    job_id: Annotated[str, typer.Argument(help="Job ID to cancel")],
    job_type: Annotated[
        str,
        typer.Option("--type", "-t", help="Job type: audit, recommendations, solutions"),
    ] = "",
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Cancel a running job."""
    out, client = _get_client(ctx)
    confirm_action(f"Cancel job {job_id[:8]}?", out, skip=yes)
    try:
        if not job_type:
            job_type = _guess_job_type(job_id, client)

        cancel_path = f"/{job_type}/{job_id}/cancel"
        client.post(cancel_path)
        print_success(f"Cancelled job {job_id[:8]}", out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()
