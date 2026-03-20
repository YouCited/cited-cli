from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from cited_cli.api import endpoints
from cited_cli.api.client import CitedClient
from cited_cli.auth.store import TokenStore
from cited_cli.config.manager import ConfigManager
from cited_cli.output.formatter import OutputContext, print_error, print_result, print_success
from cited_cli.output.tables import render_kv, render_table
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error
from cited_cli.utils.interactive import can_prompt, prompt_if_missing

named_audit_app = typer.Typer(name="template", help="Manage audit templates.")


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


@named_audit_app.command("list")
def template_list(
    ctx: typer.Context,
    business_id: Annotated[
        str | None,
        typer.Option("--business", "-b", help="Filter by business ID"),
    ] = None,
) -> None:
    """List audit templates."""
    out, client = _get_client(ctx)
    try:
        params = {}
        if business_id:
            params["business_id"] = business_id
        data = client.get(endpoints.NAMED_AUDITS, params=params or None)
        templates = (
            data if isinstance(data, list)
            else data.get("named_audits", data.get("items", []))
        )

        def _human(d: object, console: Console) -> None:
            items = d if isinstance(d, list) else []
            rows = []
            for t in items:
                questions = t.get("questions", [])
                rows.append([
                    t.get("id", "")[:8],
                    t.get("name", ""),
                    t.get("business_name", t.get("business_id", "")),
                    str(len(questions)),
                    t.get("created_at", "")[:19] if t.get("created_at") else "",
                ])
            render_table(
                "Audit Templates",
                ["ID", "Name", "Business", "Questions", "Created"],
                rows,
                console,
            )

        print_result(templates, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@named_audit_app.command("get")
def template_get(
    ctx: typer.Context,
    named_audit_id: Annotated[str, typer.Argument(help="Audit template ID")],
) -> None:
    """Get audit template details."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.NAMED_AUDIT.format(named_audit_id=named_audit_id)
        data = client.get(path)

        def _human(d: object, console: Console) -> None:
            if not isinstance(d, dict):
                console.print(d)
                return
            questions = d.pop("questions", [])
            render_kv("Audit Template", d, console)
            if questions:
                console.print("\n[bold]Questions:[/bold]")
                for i, q in enumerate(questions, 1):
                    text = q.get("question", q) if isinstance(q, dict) else q
                    console.print(f"  {i}. {text}")

        print_result(data, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@named_audit_app.command("create")
def template_create(
    ctx: typer.Context,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Template name")] = None,
    business_id: Annotated[str | None, typer.Option("--business", "-b", help="Business ID")] = None,
    description: Annotated[
        str | None, typer.Option("--description", "-d", help="Template description")
    ] = None,
    questions: Annotated[
        list[str] | None,
        typer.Option("--question", "-q", help="Question to include (repeatable)"),
    ] = None,
) -> None:
    """Create a new audit template."""
    out, client = _get_client(ctx)
    name = prompt_if_missing(name, "--name", "Template name", out)
    business_id = prompt_if_missing(business_id, "--business", "Business ID", out)
    if not questions and can_prompt(out):
        out.console.print("\n[bold]Enter questions (one per line, empty line to finish):[/bold]")
        entered: list[str] = []
        while True:
            q = typer.prompt(f"  Q{len(entered) + 1}", default="")
            if not q:
                break
            entered.append(q)
        if entered:
            questions = entered
    try:
        payload: dict = {
            "name": name,
            "business_id": business_id,
        }
        if description:
            payload["description"] = description
        if questions:
            payload["questions"] = [{"question": q} for q in questions]

        data = client.post(endpoints.NAMED_AUDITS, json=payload)
        template_id = data.get("id", "")
        print_result(data, out, human_formatter=lambda d, c: render_kv("Template Created", d, c))
        if not out.json_mode and template_id:
            out.console.print(
                f"\nTemplate ID: [bold]{template_id}[/bold]"
                f"\nRun audit:   [bold]cited audit start {template_id}"
                f" --business {business_id}[/bold]"
            )
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@named_audit_app.command("update")
def template_update(
    ctx: typer.Context,
    named_audit_id: Annotated[str, typer.Argument(help="Audit template ID to update")],
    name: Annotated[
        str | None, typer.Option("--name", "-n", help="New template name")
    ] = None,
    description: Annotated[
        str | None, typer.Option("--description", "-d", help="New description")
    ] = None,
    questions: Annotated[
        list[str] | None,
        typer.Option(
            "--question", "-q",
            help="Replacement question (repeatable — replaces all existing)",
        ),
    ] = None,
) -> None:
    """Update an audit template's name, description, or questions.

    When --question flags are provided, they replace ALL existing questions.
    Omit --question to keep existing questions unchanged.
    """
    out, client = _get_client(ctx)
    try:
        payload: dict = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if questions is not None:
            payload["questions"] = [{"question": q} for q in questions]

        if not payload:
            print_error("Nothing to update. Provide --name, --description, or --question.", out)
            raise typer.Exit(ExitCode.VALIDATION_ERROR)

        path = endpoints.NAMED_AUDIT.format(named_audit_id=named_audit_id)
        data = client.put(path, json=payload)

        def _human(d: object, console: Console) -> None:
            if not isinstance(d, dict):
                console.print(d)
                return
            questions_list = d.pop("questions", [])
            render_kv("Template Updated", d, console)
            if questions_list:
                console.print("\n[bold]Questions:[/bold]")
                for i, q in enumerate(questions_list, 1):
                    text = q.get("question", q) if isinstance(q, dict) else q
                    console.print(f"  {i}. {text}")

        print_result(data, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@named_audit_app.command("delete")
def template_delete(
    ctx: typer.Context,
    named_audit_id: Annotated[str, typer.Argument(help="Audit template ID to delete")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Delete an audit template."""
    out, client = _get_client(ctx)
    try:
        if not yes:
            confirmed = typer.confirm(f"Delete template {named_audit_id}?")
            if not confirmed:
                raise typer.Abort()

        path = endpoints.NAMED_AUDIT.format(named_audit_id=named_audit_id)
        client.delete(path)
        print_success(f"Template {named_audit_id} deleted.", out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()
