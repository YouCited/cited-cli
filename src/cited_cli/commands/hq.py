from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from cited_cli.output.formatter import OutputContext, print_error, print_result, print_success
from cited_cli.output.tables import render_bar, render_kv, render_table
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error
from cited_core.api import endpoints
from cited_core.api.client import CitedClient
from cited_core.auth.store import TokenStore
from cited_core.config.manager import ConfigManager

hq_app = typer.Typer(name="hq", help="Business HQ dashboard.", invoke_without_command=True)
persona_app = typer.Typer(name="persona", help="Manage buyer personas.")
product_app = typer.Typer(name="product", help="Manage products and services.")
intent_app = typer.Typer(name="intent", help="Manage buyer intents.")


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


@hq_app.callback(invoke_without_command=True)
def hq_dashboard(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    full: Annotated[bool, typer.Option("--full", help="Include all data (heavy)")] = False,
    personas: Annotated[bool, typer.Option("--personas", help="Include personas")] = False,
    products: Annotated[bool, typer.Option("--products", help="Include products")] = False,
    intents: Annotated[bool, typer.Option("--intents", help="Include buyer intents")] = False,
    actions: Annotated[bool, typer.Option("--actions", help="Include priority actions")] = False,
) -> None:
    """Show the Business HQ dashboard."""
    if ctx.invoked_subcommand is not None:
        return

    out, client = _get_client(ctx)
    try:
        # Fetch base HQ data
        if full:
            path = endpoints.HQ_HEAVY.format(business_id=business_id)
        else:
            path = endpoints.HQ.format(business_id=business_id)
        data = client.get(path)

        # Fetch additional sections if requested
        if personas and not full:
            data["personas"] = client.get(endpoints.PERSONAS.format(business_id=business_id))
        if products and not full:
            data["products"] = client.get(endpoints.PRODUCTS.format(business_id=business_id))
        if intents and not full:
            path = endpoints.BUYER_INTENTS.format(business_id=business_id)
            data["buyer_intents"] = client.get(path)
        if actions and not full:
            path = endpoints.HQ_PRIORITY.format(business_id=business_id)
            data["priority_actions"] = client.get(path)

        def _human(d: object, console: Console) -> None:
            if not isinstance(d, dict):
                return
            name = d.get("business", {}).get("name", d.get("name", "Business HQ"))
            console.print()
            console.rule(f"[bold]{name}[/bold]")

            # Health scores
            scores = d.get("health_scores", d.get("scores", {}))
            if scores:
                console.print("\n[bold]Health Scores[/bold]")
                if isinstance(scores, dict):
                    for label, val in scores.items():
                        if isinstance(val, (int, float)):
                            render_bar(label.replace("_", " ").title(), val, console=console)

            # Personas
            if d.get("personas"):
                console.print("\n[bold]Personas[/bold]")
                p_list = (
                    d["personas"] if isinstance(d["personas"], list)
                    else d["personas"].get("items", [])
                )
                for p in p_list:
                    console.print(f"  - {p.get('name', 'Unknown')}")

            # Products
            if d.get("products"):
                console.print("\n[bold]Products[/bold]")
                prod_list = (
                    d["products"] if isinstance(d["products"], list)
                    else d["products"].get("items", [])
                )
                for p in prod_list:
                    console.print(f"  - {p.get('name', 'Unknown')}")

            # Priority actions
            if d.get("priority_actions"):
                console.print("\n[bold]Priority Actions[/bold]")
                pa = d["priority_actions"]
                act_list = (
                    pa if isinstance(pa, list)
                    else pa.get("items", [])
                )
                for a in act_list:
                    label = a.get('title', a.get('description', ''))
                    console.print(f"  [{a.get('priority', '?')}] {label}")

            console.print()

        print_result(data, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@hq_app.command("brief")
def hq_brief(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """Show the agent brief — top priority actions, quick wins, failing checks, citation trend."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.HQ_AGENT_BRIEF.format(business_id=business_id)
        data = client.get(path)

        def _human(d: object, console: Console) -> None:
            if not isinstance(d, dict):
                return
            console.rule("[bold]Agent Brief[/bold]")
            for section_key, label in [
                ("priority_actions", "Top Priority Actions"),
                ("quick_wins", "Quick Wins"),
                ("failing_checks", "Failing Checks"),
            ]:
                items = d.get(section_key) or []
                if not items:
                    continue
                console.print(f"\n[bold]{label}[/bold]")
                for item in items[:10] if isinstance(items, list) else []:
                    title = item.get("title") or item.get("message") or item.get("name", "")
                    console.print(f"  - {title}")
            trend = d.get("citation_trend") or d.get("trend")
            if trend:
                console.print("\n[bold]Citation Trend[/bold]")
                if isinstance(trend, dict):
                    for k, v in trend.items():
                        console.print(f"  {k}: {v}")

        print_result(data, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@hq_app.command("recompute")
def hq_recompute(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """Force a fresh recomputation of health scores."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.HQ_RECOMPUTE.format(business_id=business_id)
        data = client.post(path)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Recomputed Scores", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@hq_app.command("refresh")
def hq_refresh(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    scope: Annotated[
        str,
        typer.Option(
            "--scope", "-s", help="audit | recommendations | all (default all)"
        ),
    ] = "all",
) -> None:
    """Refresh cached audit / recommendation overview data."""
    out, client = _get_client(ctx)
    scope_norm = scope.lower().strip()
    if scope_norm == "audit":
        path = endpoints.HQ_OVERVIEW_REFRESH_AUDIT.format(business_id=business_id)
    elif scope_norm in ("recommendations", "rec", "recs"):
        path = endpoints.HQ_OVERVIEW_REFRESH_RECS.format(business_id=business_id)
    elif scope_norm == "all":
        path = endpoints.HQ_OVERVIEW_REFRESH_ALL.format(business_id=business_id)
    else:
        print_error("--scope must be one of: audit, recommendations, all", out)
        raise typer.Exit(ExitCode.VALIDATION_ERROR)
    try:
        data = client.post(path)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Refreshed", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Persona CRUD
# ---------------------------------------------------------------------------


@persona_app.command("list")
def persona_list(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """List buyer personas for the business."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.PERSONAS.format(business_id=business_id)
        data = client.get(path)
        items = data if isinstance(data, list) else []

        def _human(d: object, console: Console) -> None:
            rows: list[list[str]] = []
            for p in items:
                rows.append([
                    str(p.get("id", ""))[:8],
                    str(p.get("name", "")),
                    str(p.get("role", "") or ""),
                ])
            render_table("Personas", ["ID", "Name", "Role"], rows, console)

        print_result(items, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@persona_app.command("create")
def persona_create(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    name: Annotated[str, typer.Option("--name", help="Persona name")],
    description: Annotated[str | None, typer.Option("--description")] = None,
    role: Annotated[str | None, typer.Option("--role")] = None,
) -> None:
    """Create a buyer persona."""
    out, client = _get_client(ctx)
    payload: dict[str, object] = {"name": name}
    if description is not None:
        payload["description"] = description
    if role is not None:
        payload["role"] = role
    try:
        path = endpoints.PERSONAS.format(business_id=business_id)
        data = client.post(path, json=payload)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Created Persona", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@persona_app.command("update")
def persona_update(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    persona_id: Annotated[str, typer.Argument(help="Persona ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    role: Annotated[str | None, typer.Option("--role")] = None,
) -> None:
    """Update a persona."""
    out, client = _get_client(ctx)
    payload: dict[str, object] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if role is not None:
        payload["role"] = role
    if not payload:
        print_error("No fields to update.", out)
        raise typer.Exit(ExitCode.VALIDATION_ERROR)
    try:
        path = endpoints.PERSONA.format(business_id=business_id, persona_id=persona_id)
        data = client.patch(path, json=payload)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Updated Persona", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@persona_app.command("delete")
def persona_delete(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    persona_id: Annotated[str, typer.Argument(help="Persona ID")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Delete a persona."""
    out, client = _get_client(ctx)
    if not yes and not out.json_mode:
        typer.confirm(f"Delete persona {persona_id}?", abort=True)
    try:
        path = endpoints.PERSONA.format(business_id=business_id, persona_id=persona_id)
        client.delete(path)
        print_success(f"Deleted persona {persona_id[:8]}", out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Product CRUD
# ---------------------------------------------------------------------------


@product_app.command("list")
def product_list(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """List products/services for the business."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.PRODUCTS.format(business_id=business_id)
        data = client.get(path)
        items = data if isinstance(data, list) else []

        def _human(d: object, console: Console) -> None:
            rows: list[list[str]] = []
            for p in items:
                rows.append([
                    str(p.get("id", ""))[:8],
                    str(p.get("name", "")),
                    str(p.get("category", "") or ""),
                    str(p.get("url", "") or ""),
                ])
            render_table("Products", ["ID", "Name", "Category", "URL"], rows, console)

        print_result(items, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@product_app.command("create")
def product_create(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    name: Annotated[str, typer.Option("--name", help="Product name")],
    description: Annotated[str | None, typer.Option("--description")] = None,
    url: Annotated[str | None, typer.Option("--url", help="Landing page URL")] = None,
    category: Annotated[str | None, typer.Option("--category")] = None,
) -> None:
    """Create a product/service."""
    out, client = _get_client(ctx)
    payload: dict[str, object] = {"name": name}
    if description is not None:
        payload["description"] = description
    if url is not None:
        payload["url"] = url
    if category is not None:
        payload["category"] = category
    try:
        path = endpoints.PRODUCTS.format(business_id=business_id)
        data = client.post(path, json=payload)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Created Product", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@product_app.command("update")
def product_update(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    product_id: Annotated[str, typer.Argument(help="Product ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    url: Annotated[str | None, typer.Option("--url")] = None,
    category: Annotated[str | None, typer.Option("--category")] = None,
) -> None:
    """Update a product."""
    out, client = _get_client(ctx)
    payload: dict[str, object] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if url is not None:
        payload["url"] = url
    if category is not None:
        payload["category"] = category
    if not payload:
        print_error("No fields to update.", out)
        raise typer.Exit(ExitCode.VALIDATION_ERROR)
    try:
        path = endpoints.PRODUCT.format(business_id=business_id, product_id=product_id)
        data = client.patch(path, json=payload)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Updated Product", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@product_app.command("delete")
def product_delete(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    product_id: Annotated[str, typer.Argument(help="Product ID")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Delete a product."""
    out, client = _get_client(ctx)
    if not yes and not out.json_mode:
        typer.confirm(f"Delete product {product_id}?", abort=True)
    try:
        path = endpoints.PRODUCT.format(business_id=business_id, product_id=product_id)
        client.delete(path)
        print_success(f"Deleted product {product_id[:8]}", out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Buyer-intent
# ---------------------------------------------------------------------------


@intent_app.command("list")
def intent_list(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """List buyer intents for the business."""
    out, client = _get_client(ctx)
    try:
        path = endpoints.BUYER_INTENTS.format(business_id=business_id)
        data = client.get(path)
        items = data if isinstance(data, list) else []

        def _human(d: object, console: Console) -> None:
            rows: list[list[str]] = []
            for i in items:
                personas = i.get("persona_ids") or []
                products = i.get("product_ids") or []
                rows.append([
                    str(i.get("id", ""))[:8],
                    str(i.get("intent", "")),
                    str(len(personas)),
                    str(len(products)),
                ])
            render_table(
                "Buyer Intents",
                ["ID", "Intent", "# Personas", "# Products"],
                rows,
                console,
            )

        print_result(items, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@intent_app.command("create")
def intent_create(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    intent: Annotated[str, typer.Option("--intent", help="Intent label")],
    description: Annotated[str | None, typer.Option("--description")] = None,
) -> None:
    """Create a buyer intent."""
    out, client = _get_client(ctx)
    payload: dict[str, object] = {"intent": intent}
    if description is not None:
        payload["description"] = description
    try:
        path = endpoints.BUYER_INTENTS.format(business_id=business_id)
        data = client.post(path, json=payload)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Created Intent", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@intent_app.command("update")
def intent_update(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    intent_id: Annotated[str, typer.Argument(help="Intent ID")],
    question: Annotated[str | None, typer.Option("--question")] = None,
    intent_type: Annotated[str | None, typer.Option("--intent-type")] = None,
    priority: Annotated[str | None, typer.Option("--priority")] = None,
    is_answered: Annotated[bool | None, typer.Option("--is-answered/--not-answered")] = None,
    answering_page_url: Annotated[str | None, typer.Option("--answering-page-url")] = None,
) -> None:
    """Update a buyer intent."""
    out, client = _get_client(ctx)
    payload: dict[str, object] = {}
    if question is not None:
        payload["question"] = question
    if intent_type is not None:
        payload["intent_type"] = intent_type
    if priority is not None:
        payload["priority"] = priority
    if is_answered is not None:
        payload["is_answered"] = is_answered
    if answering_page_url is not None:
        payload["answering_page_url"] = answering_page_url
    if not payload:
        print_error("No fields to update.", out)
        raise typer.Exit(ExitCode.VALIDATION_ERROR)
    try:
        path = endpoints.BUYER_INTENT.format(
            business_id=business_id, intent_id=intent_id
        )
        data = client.patch(path, json=payload)
        print_result(data, out, human_formatter=lambda d, c: render_kv("Updated Intent", d, c))
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@intent_app.command("delete")
def intent_delete(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
    intent_id: Annotated[str, typer.Argument(help="Intent ID")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Delete a buyer intent."""
    out, client = _get_client(ctx)
    if not yes and not out.json_mode:
        typer.confirm(f"Delete buyer intent {intent_id}?", abort=True)
    try:
        path = endpoints.BUYER_INTENT.format(
            business_id=business_id, intent_id=intent_id
        )
        client.delete(path)
        print_success(f"Deleted buyer intent {intent_id[:8]}", out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


hq_app.add_typer(persona_app, name="persona")
hq_app.add_typer(product_app, name="product")
hq_app.add_typer(intent_app, name="intent")
