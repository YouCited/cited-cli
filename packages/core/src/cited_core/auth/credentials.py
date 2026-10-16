from __future__ import annotations

import os

from cited_core.auth.store import TokenStore
from cited_core.config.manager import ConfigManager

AGENT_KEY_ENV_VAR = "CITED_AGENT_API_KEY"


def resolve_agent_api_key(
    config: ConfigManager | None,
    env: str,
    profile: str = "default",
    store: TokenStore | None = None,
) -> str | None:
    """Find the agent API key to use for *env*.

    Order: ``CITED_AGENT_API_KEY`` env var, then the ``agent_api_key`` config
    value for *profile*, then the key saved by agent signup for *env*.
    """
    key = os.environ.get(AGENT_KEY_ENV_VAR)
    if key:
        return key
    if config is not None:
        configured = config.get("agent_api_key", profile)
        if configured:
            return str(configured)
    return (store or TokenStore()).get_agent_key(env)
