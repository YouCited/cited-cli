from __future__ import annotations

from typing import Annotated, Any

import typer
from rich.console import Console

from cited_cli.output.formatter import OutputContext, print_error, print_result
from cited_cli.output.tables import render_kv, render_table
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error
from cited_cli.utils.interactive import prompt_if_missing
from cited_core.api import endpoints
from cited_core.api.client import LONG_TIMEOUT, CitedClient
from cited_core.auth.store import TokenStore
from cited_core.config.manager import ConfigManager

recommend_app = typer.Typer(name="recommend", help="Generate and manage recommendations.")


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


@recommend_app.command("start")
def recommend_start(
    ctx: typer.Context,
    audit_job_id: Annotated[
        str | None,
        typer.Argument(help="Audit job ID to generate recommendations from"),
    ] = None,
) -> None:
    """Generate recommendations from an audit."""
    out, client = _get_client(ctx)
    audit_job_id = prompt_if_missing(audit_job_id, "AUDIT_JOB_ID", "Audit job ID", out)
    try:
        data = client.post(
            endpoints.RECOMMEND_START,
            json={"audit_job_id": audit_job_id},
            timeout=LONG_TIMEOUT,
        )
        job_id = data.get("job_id", data.get("id", ""))
        print_result(
            data,
            out,
            human_formatter=lambda d, c: render_kv("Recommendations Started", d, c),
        )
        if not out.json_mode and job_id:
            out.console.print(f"\nTrack progress: [bold]cited job watch {job_id}[/bold]")
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@recommend_app.command("status")
def recommend_status(
    ctx: typer.Context,
    job_id: Annotated[str, typer.Argument(help="Recommendation job ID")],
) -> None:
    """Check recommendation job status."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.RECOMMEND_STATUS.format(job_id=job_id)
        data = client.get(path)
        print_result(
            data,
            out,
            human_formatter=lambda d, c: render_kv("Recommendation Status", d, c),
        )
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@recommend_app.command("result")
def recommend_result(
    ctx: typer.Context,
    job_id: Annotated[str, typer.Argument(help="Recommendation job ID")],
) -> None:
    """Get recommendation results."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.RECOMMEND_RESULT.format(job_id=job_id)
        data = client.get(path)
        print_result(data, out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@recommend_app.command("insights")
def recommend_insights(
    ctx: typer.Context,
    job_id: Annotated[str, typer.Argument(help="Recommendation job ID")],
) -> None:
    """List solution-ready insights from a recommendation job."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.RECOMMEND_RESULT.format(job_id=job_id)
        data = client.get(path)

        def _human(d: object, console: Console) -> None:
            if not isinstance(d, dict):
                console.print(d)
                return
            data: dict[str, Any] = d
            rows: list[list[object]] = []

            # question_insights: id=question_id, desc=question_text
            for item in data.get("question_insights", []):
                if not isinstance(item, dict):
                    continue
                source_id = item.get("question_id", item.get("id", ""))
                desc = str(item.get("question_text", item.get("question", "")))
                rows.append([str(len(rows) + 1), "question_insight", source_id, desc[:60]])

            # head_to_head_comparisons: id=competitor_domain
            for item in data.get("head_to_head_comparisons", data.get("head_to_head", [])):
                if not isinstance(item, dict):
                    continue
                source_id = item.get("competitor_domain", item.get("id", ""))
                desc = str(item.get("competitor_domain", item.get("description", "")))
                rows.append([str(len(rows) + 1), "head_to_head", source_id, desc[:60]])

            # strengthening_tips: id=category (no uuid), desc=title
            for item in data.get("strengthening_tips", []):
                if not isinstance(item, dict):
                    continue
                source_id = item.get("category", item.get("id", item.get("source_id", "")))
                desc = str(item.get("title", item.get("description", "")))
                rows.append([str(len(rows) + 1), "strengthening_tip", source_id, desc[:60]])

            # priority_actions: id=id or category
            for item in data.get("priority_actions", []):
                if not isinstance(item, dict):
                    continue
                source_id = item.get("id", item.get("category", item.get("source_id", "")))
                desc = str(item.get("title", item.get("description", item.get("action", ""))))
                rows.append([str(len(rows) + 1), "priority_action", source_id, desc[:60]])

            render_table(
                "Available Insights",
                ["#", "Type", "Source ID", "Description"],
                rows,
                console,
            )
            if rows:
                console.print(
                    "\nRun a solution: [bold]cited solution start "
                    f"{job_id} --type <type> --source <source_id>[/bold]"
                )

        print_result(data, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@recommend_app.command("list")
def recommend_list(
    ctx: typer.Context,
    audit_job_id: Annotated[
        str | None,
        typer.Option("--audit", "-a", help="Filter by audit job ID"),
    ] = None,
) -> None:
    """List recommendation history."""
    out, client = _get_client(ctx)
    try:
        if audit_job_id:
            path = endpoints.RECOMMEND_HISTORY.format(audit_job_id=audit_job_id)
            data = client.get(path)
        else:
            data = client.get("/recommendations/history/bulk")
        recs = (
            data if isinstance(data, list)
            else data.get("recommendations", data.get("items", []))
        )

        def _human(d: object, console: Console) -> None:
            items = d if isinstance(d, list) else []
            rows = []
            for r in items:
                rows.append([
                    r.get("job_id", r.get("id", ""))[:8],
                    r.get("status", ""),
                    r.get("created_at", "")[:19] if r.get("created_at") else "",
                ])
            render_table("Recommendations", ["Job ID", "Status", "Created"], rows, console)

        print_result(recs, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()
