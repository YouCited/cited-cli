"""`cited agent`: agent_signup, plus `agent setup` for local AI clients."""

from __future__ import annotations

from typing import Annotated

import typer

from cited_cli.commands.agent_setup import agent_setup
from cited_cli.utils.tools import clean, run

agent_app = typer.Typer(
    help="Accounts for AI agents, and connecting AI clients to Cited.", no_args_is_help=True
)
agent_app.command("setup")(agent_setup)


@agent_app.command("signup")
def signup(
    ctx: typer.Context,
    name: Annotated[
        str | None, typer.Option("--name", help="The agent's name, shown to the person")
    ] = None,
    email: Annotated[
        str | None, typer.Option("--email", help="Email the claim link to the person")
    ] = None,
) -> None:
    """Create a Cited account for an AI agent, without a login.

    The API key is saved on this machine (never printed). Give the person the
    claim link and code so they can keep the account.
    """
    run(ctx, "agent_signup", clean({"agent_name": name, "owner_email": email}))
