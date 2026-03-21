from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from cited_cli.output.formatter import OutputContext, print_error, print_result
from cited_cli.output.tables import render_kv, render_table
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error
from cited_cli.utils.interactive import prompt_choice, prompt_if_missing
from cited_core.api import endpoints
from cited_core.api.client import LONG_TIMEOUT, CitedClient
from cited_core.auth.store import TokenStore
from cited_core.config.constants import VALID_SOURCE_TYPES
from cited_core.config.manager import ConfigManager

solution_app = typer.Typer(name="solution", help="Generate and manage content solutions.")


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


@solution_app.command("start")
def solution_start(
    ctx: typer.Context,
    recommendation_job_id: Annotated[
        str | None,
        typer.Argument(help="Recommendation job ID"),
    ] = None,
    source_type: Annotated[
        str | None,
        typer.Option(
            "--type", "-t",
            help="Source type: question_insight, head_to_head, strengthening_tip, priority_action",
        ),
    ] = None,
    source_id: Annotated[
        str | None,
        typer.Option("--source", "-s", help="Source ID from 'cited recommend insights'"),
    ] = None,
) -> None:
    """Generate a content solution from a recommendation insight."""
    out, client, env = _get_client(ctx)
    recommendation_job_id = prompt_if_missing(
        recommendation_job_id, "RECOMMENDATION_JOB_ID", "Recommendation job ID", out
    )
    source_type = prompt_choice(
        source_type, "--type", "Select source type:", VALID_SOURCE_TYPES, out
    )
    source_id = prompt_if_missing(source_id, "--source", "Source ID", out)
    try:
        data = client.post(
            endpoints.SOLUTION_REQUEST,
            json={
                "recommendation_job_id": recommendation_job_id,
                "source_type": source_type,
                "source_id": source_id,
            },
            timeout=LONG_TIMEOUT,
        )
        job_id = data.get("job_id", data.get("id", ""))
        print_result(data, out, human_formatter=lambda d, c: render_kv("Solution Started", d, c))
        if not out.json_mode and job_id:
            out.console.print(f"\nTrack progress: [bold]cited job watch {job_id}[/bold]")
            web_base = f"https://{env}.youcited.com" if env != "prod" else "https://youcited.com"
            out.console.print(f"View artifacts: [bold]{web_base}/solutions/{job_id}[/bold]")
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@solution_app.command("status")
def solution_status(
    ctx: typer.Context,
    job_id: Annotated[str, typer.Argument(help="Solution job ID")],
) -> None:
    """Check solution job status."""
    out, client, _ = _get_client(ctx)
    try:
        path = endpoints.SOLUTION_STATUS.format(job_id=job_id)
        data = client.get(path)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Solution Status", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@solution_app.command("result")
def solution_result(
    ctx: typer.Context,
    job_id: Annotated[str, typer.Argument(help="Solution job ID")],
) -> None:
    """Get solution results."""
    out, client, _ = _get_client(ctx)
    try:
        path = endpoints.SOLUTION_RESULT.format(job_id=job_id)
        data = client.get(path)
        print_result(data, out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@solution_app.command("list")
def solution_list(
    ctx: typer.Context,
    business_id: Annotated[
        str | None,
        typer.Option("--business", "-b", help="Filter by business ID"),
    ] = None,
) -> None:
    """List solution history."""
    out, client, _ = _get_client(ctx)
    try:
        params = {}
        if business_id:
            params["business_id"] = business_id
        data = client.get(endpoints.SOLUTION_HISTORY, params=params or None)
        solutions = data if isinstance(data, list) else data.get("solutions", data.get("items", []))

        def _human(d: object, console: Console) -> None:
            items = d if isinstance(d, list) else []
            rows = []
            for s in items:
                rows.append([
                    s.get("job_id", s.get("id", ""))[:8],
                    s.get("status", ""),
                    s.get("created_at", "")[:19] if s.get("created_at") else "",
                ])
            render_table("Solutions", ["Job ID", "Status", "Created"], rows, console)

        print_result(solutions, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()
