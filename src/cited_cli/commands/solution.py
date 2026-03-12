from __future__ import annotations

from typing import Annotated

import typer

from cited_cli.api import endpoints
from cited_cli.api.client import LONG_TIMEOUT, CitedClient
from cited_cli.auth.store import TokenStore
from cited_cli.config.manager import ConfigManager
from cited_cli.output.formatter import OutputContext, print_error, print_result
from cited_cli.output.tables import render_kv, render_table
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error

solution_app = typer.Typer(name="solution", help="Generate and manage content solutions.")


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
        print_error(f"Not logged in to {env}. Run: cited auth login", out)
        raise typer.Exit(ExitCode.AUTH_ERROR)

    return out, CitedClient(base_url=api_url, token=token)


@solution_app.command("start")
def solution_start(
    ctx: typer.Context,
    recommendation_id: Annotated[
        str,
        typer.Argument(help="Recommendation ID to generate solution from"),
    ],
) -> None:
    """Generate a content solution from a recommendation."""
    out, client = _get_client(ctx)
    try:
        data = client.post(
            endpoints.SOLUTION_CREATE,
            json={"recommendation_id": recommendation_id},
            timeout=LONG_TIMEOUT,
        )
        job_id = data.get("job_id", data.get("id", ""))
        print_result(data, out, human_formatter=lambda d, c: render_kv("Solution Started", d, c))
        if not out.json_mode and job_id:
            out.console.print(f"\nTrack progress: [bold]cited job watch {job_id}[/bold]")
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
    out, client = _get_client(ctx)
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
    out, client = _get_client(ctx)
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
    out, client = _get_client(ctx)
    try:
        params = {}
        if business_id:
            params["business_id"] = business_id
        data = client.get(endpoints.SOLUTION_HISTORY, params=params or None)
        solutions = data if isinstance(data, list) else data.get("solutions", data.get("items", []))

        def _human(d: list, console) -> None:  # type: ignore[no-untyped-def]
            rows = []
            for s in d:
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
