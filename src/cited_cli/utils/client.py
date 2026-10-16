from __future__ import annotations

import typer

from cited_cli.output.formatter import OutputContext, print_error
from cited_core.api.client import CitedClient
from cited_core.auth.credentials import resolve_agent_api_key
from cited_core.auth.store import TokenStore
from cited_core.config.manager import ConfigManager
from cited_core.errors import ExitCode


def get_output(ctx: typer.Context) -> OutputContext:
    obj = ctx.obj or {}
    out: OutputContext = obj.get("output", OutputContext())
    return out


def get_env_and_url(ctx: typer.Context) -> tuple[ConfigManager, str, str, str]:
    """Return (config, profile, env, api_url) for this invocation."""
    obj = ctx.obj or {}
    cfg: ConfigManager = obj.get("config", ConfigManager())
    profile: str = obj.get("profile", "default")
    env = cfg.get_environment(profile, obj.get("env_override"))
    api_url = cfg.get_api_url(profile, obj.get("env_override"))
    return cfg, profile, env, api_url


def get_public_client(ctx: typer.Context) -> tuple[OutputContext, CitedClient]:
    """A client with no credentials, for public endpoints."""
    _, _, _, api_url = get_env_and_url(ctx)
    return get_output(ctx), CitedClient(base_url=api_url)


def get_authed_client(ctx: typer.Context) -> tuple[OutputContext, CitedClient, str]:
    """Build an authenticated client, or exit with an auth error.

    A session token from ``cited login`` wins. Without one, an agent API key
    is used (``CITED_AGENT_API_KEY``, the ``agent_api_key`` config value, or
    the key saved by ``cited agent signup``) and sent as ``X-Agent-API-Key``
    on every request.
    """
    out = get_output(ctx)
    cfg, profile, env, api_url = get_env_and_url(ctx)
    store = TokenStore()
    token = store.get_token(env)
    agent_key = None if token else resolve_agent_api_key(cfg, env, profile, store)
    if not token and not agent_key:
        print_error(
            f"Not logged in to {env}. Run: cited login "
            "(an AI agent without an account can run: cited agent signup)",
            out,
        )
        raise typer.Exit(ExitCode.AUTH_ERROR)
    return out, CitedClient(base_url=api_url, token=token, agent_api_key=agent_key), env
