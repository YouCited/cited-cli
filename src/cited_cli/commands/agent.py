from __future__ import annotations

from typing import Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel

from cited_cli.commands.agent_setup import agent_setup
from cited_cli.output.formatter import OutputContext, print_error, print_result, print_success
from cited_cli.output.tables import render_kv, render_table
from cited_cli.utils.client import get_authed_client, get_env_and_url, get_output
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error
from cited_cli.utils.interactive import confirm_action, prompt_if_missing
from cited_core.api import endpoints
from cited_core.api.client import CitedClient
from cited_core.auth.store import TokenStore

agent_app = typer.Typer(
    name="agent",
    help=(
        "Connect AI agents to Cited: setup, agent signup and keys, and the Agent API (v1)."
    ),
)

agent_app.command("setup")(agent_setup)


def _get_agent_client(ctx: typer.Context) -> tuple[OutputContext, CitedClient]:
    out, client, _ = get_authed_client(ctx)
    return out, client


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


# ---------------------------------------------------------------------------
# Agent signup and per-user agent keys
# ---------------------------------------------------------------------------


def _render_signup(d: dict[str, Any], console: Console) -> None:
    claim = d.get("claim") or {}
    account = d.get("account") or {}
    limits = account.get("limits") or {}
    console.print(
        Panel(
            f"Claim link: [bold cyan]{claim.get('url', '')}[/bold cyan]\n"
            f"Code:       [bold]{claim.get('code', '')}[/bold]\n"
            f"Expires:    {claim.get('expires_at', '')}",
            title="Give this link and code to the person who owns this agent",
            border_style="green",
        )
    )
    console.print(
        f"Agent key {d.get('key_prefix', '')}... saved for {d.get('environment', '')}. "
        "It was shown once and is not printed."
    )
    console.print(
        f"Until claimed: {limits.get('businesses', 1)} business, "
        f"{limits.get('audits', 1)} audit, pay per audit "
        "([bold]cited credits buy-audit[/bold]). "
        f"The account is deleted on {account.get('expires_at', '')} unless claimed."
    )
    for step in d.get("next_steps") or []:
        console.print(f"  - {step}")


@agent_app.command("signup")
def agent_signup(
    ctx: typer.Context,
    name: Annotated[str | None, typer.Option("--name", help="Agent name")] = None,
    email: Annotated[
        str | None,
        typer.Option("--email", help="Owner's email; the claim link is emailed there too"),
    ] = None,
) -> None:
    """Create an unclaimed agent account and save its API key. No login needed."""
    out = get_output(ctx)
    _, _, env, api_url = get_env_and_url(ctx)
    store = TokenStore()
    if store.get_token(env):
        print_error(
            f"You are logged in to {env} as a person, so no agent key is needed. "
            "Agent signup is for AI agents without an account (run `cited logout` first).",
            out,
        )
        raise typer.Exit(ExitCode.VALIDATION_ERROR)
    if store.get_agent_key(env):
        print_error(
            f"An agent key is already saved for {env}. Check it with: cited agent key-status "
            "(remove it with `cited logout` before signing up again).",
            out,
        )
        raise typer.Exit(ExitCode.VALIDATION_ERROR)

    payload: dict[str, str] = {}
    if name:
        payload["agent_name"] = name
    if email:
        payload["owner_email"] = email
    client = CitedClient(base_url=api_url)
    try:
        data = client.post(endpoints.AGENT_SIGNUP, json=payload)
        api_key = data.pop("api_key", None)
        if not api_key:
            print_error("Signup response had no api_key.", out)
            raise typer.Exit(ExitCode.ERROR)
        store.save_agent_key(env, api_key)
        data["api_key_saved"] = True
        data["environment"] = env
        print_result(data, out, human_formatter=_render_signup)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@agent_app.command("key-status")
def agent_key_status(ctx: typer.Context) -> None:
    """Show the agent key's account state, expiry and how to switch to OAuth."""
    out, client, _ = get_authed_client(ctx)
    try:
        data = client.get(endpoints.AGENT_KEY_STATUS)

        def _human(d: dict[str, Any], console: Console) -> None:
            oauth = d.get("oauth") or {}
            render_kv(
                "Agent key",
                {
                    "Key": f"{d.get('key_prefix', '')}...",
                    "Account": "unclaimed" if d.get("unclaimed") else "claimed",
                    "Account expires": d.get("account_expires_at") or "-",
                    "Key expires": d.get("key_expires_at") or "never",
                    "Days left": d.get("days_left") if d.get("days_left") is not None else "-",
                    "OAuth MCP URL": oauth.get("mcp_url", ""),
                },
                console,
            )
            if d.get("notice"):
                console.print(f"[yellow]→ {d['notice']}[/yellow]")
            if oauth.get("instructions"):
                console.print(oauth["instructions"])

        print_result(data, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@agent_app.command("keys")
def agent_keys(ctx: typer.Context) -> None:
    """List this account's agent API keys."""
    out, client, _ = get_authed_client(ctx)
    try:
        data = client.get(endpoints.AGENT_KEYS)

        def _human(d: dict[str, Any], console: Console) -> None:
            rows = [
                [
                    k.get("id", ""),
                    f"{k.get('key_prefix', '')}...",
                    k.get("label") or "",
                    k.get("status", ""),
                    str(k.get("last_used_at") or "")[:19],
                    str(k.get("expires_at") or "never")[:19],
                ]
                for k in d.get("keys", [])
            ]
            render_table(
                "Agent keys",
                ["ID", "Key", "Label", "Status", "Last used", "Expires"],
                rows,
                console,
            )

        print_result(data, out, human_formatter=_human)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@agent_app.command("revoke")
def agent_revoke(
    ctx: typer.Context,
    key_id: Annotated[str, typer.Argument(help="Agent key ID (see `cited agent keys`)")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Revoke an agent API key. Agents using it lose access immediately."""
    out, client, _ = get_authed_client(ctx)
    confirm_action(f"Revoke agent key {key_id}?", out, skip=yes)
    try:
        data = client.delete(endpoints.AGENT_KEY.format(key_id=key_id))
        if out.json_mode:
            print_result(data, out)
        else:
            print_success(f"Revoked agent key {key_id}", out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()
