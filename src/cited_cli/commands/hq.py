from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from cited_cli.api import endpoints
from cited_cli.api.client import CitedClient
from cited_cli.auth.store import TokenStore
from cited_cli.config.manager import ConfigManager
from cited_cli.output.formatter import OutputContext, print_error, print_result
from cited_cli.output.tables import render_bar
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error

hq_app = typer.Typer(name="hq", help="Business HQ dashboard.", invoke_without_command=True)


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
