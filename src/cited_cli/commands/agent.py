from __future__ import annotations

from typing import Annotated

import typer

from cited_cli.api import endpoints
from cited_cli.api.client import CitedClient
from cited_cli.config.manager import ConfigManager
from cited_cli.output.formatter import OutputContext, print_error, print_result
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error
from cited_cli.utils.interactive import prompt_if_missing

agent_app = typer.Typer(
    name="agent",
    help="Agent API (v1) — structured business data for AI agents.",
)


def _get_agent_client(ctx: typer.Context) -> tuple[OutputContext, CitedClient]:
    obj = ctx.obj or {}
    out: OutputContext = obj.get("output", OutputContext())
    cfg: ConfigManager = obj.get("config", ConfigManager())
    profile = obj.get("profile", "default")
    api_url = cfg.get_api_url(profile, obj.get("env_override"))

    import os

    api_key = cfg.get("agent_api_key", profile) or os.environ.get("CITED_AGENT_API_KEY")
    if not api_key:
        print_error(
            "Agent API key required. Set via: cited config set agent_api_key <key>\n"
            "Or set CITED_AGENT_API_KEY environment variable.",
            out,
        )
        raise typer.Exit(ExitCode.AUTH_ERROR)

    return out, CitedClient(base_url=api_url, agent_api_key=api_key)


@agent_app.command("facts")
def agent_facts(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """Get structured business facts."""
    out, client = _get_agent_client(ctx)
    try:
        path = endpoints.AGENT_FACTS.format(business_id=business_id)
        data = client.get(path)
        print_result(data, out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@agent_app.command("claims")
def agent_claims(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """Get verifiable claims about a business."""
    out, client = _get_agent_client(ctx)
    try:
        path = endpoints.AGENT_CLAIMS.format(business_id=business_id)
        data = client.get(path)
        print_result(data, out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@agent_app.command("comparison")
def agent_comparison(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """Get competitive comparison data."""
    out, client = _get_agent_client(ctx)
    try:
        path = endpoints.AGENT_COMPARISON.format(business_id=business_id)
        data = client.get(path)
        print_result(data, out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@agent_app.command("semantic-health")
def agent_semantic_health(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="Business ID")],
) -> None:
    """Get semantic readiness signals."""
    out, client = _get_agent_client(ctx)
    try:
        path = endpoints.AGENT_SEMANTIC_HEALTH.format(business_id=business_id)
        data = client.get(path)
        print_result(data, out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@agent_app.command("buyer-fit")
def agent_buyer_fit(
    ctx: typer.Context,
    query: Annotated[
        str | None, typer.Option("--query", "-q", help="Buyer query to simulate")
    ] = None,
    business_id: Annotated[str | None, typer.Option("--business", "-b", help="Business ID")] = None,
) -> None:
    """Run a buyer-fit simulation query."""
    out, client = _get_agent_client(ctx)
    query = prompt_if_missing(query, "--query", "Buyer query", out)
    try:
        payload: dict[str, str] = {"query": query}
        if business_id:
            payload["business_id"] = business_id
        data = client.post(endpoints.AGENT_BUYER_FIT, json=payload)
        print_result(data, out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()
