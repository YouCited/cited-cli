from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from cited_core.api.client import CitedClient
from cited_core.auth.store import TokenStore
from cited_core.config.manager import ConfigManager
from cited_mcp.context import CitedContext


@asynccontextmanager
async def cited_lifespan(server: FastMCP) -> AsyncIterator[CitedContext]:
    """Set up CitedClient for the MCP server lifetime."""
    config = ConfigManager()
    env_override = os.environ.get("CITED_ENV")
    env = config.get_environment(override=env_override)
    api_url = config.get_api_url(env_override=env_override)

    token = os.environ.get("CITED_TOKEN") or TokenStore().get_token(env)
    agent_api_key = os.environ.get("CITED_AGENT_API_KEY") or config.get("agent_api_key")

    client = CitedClient(
        base_url=api_url,
        token=token,
        agent_api_key=agent_api_key,
    )
    try:
        yield CitedContext(client=client, env=env, api_url=api_url)
    finally:
        client.close()


mcp = FastMCP(
    "cited",
    instructions="Cited GEO platform — audit, optimize, and monitor AI search presence",
    lifespan=cited_lifespan,
)

# Import tool modules to trigger @mcp.tool() registrations
import cited_mcp.tools.auth  # noqa: I001, E402, F401
import cited_mcp.tools.audit  # noqa: E402, F401
import cited_mcp.tools.business  # noqa: E402, F401
import cited_mcp.tools.job  # noqa: E402, F401
import cited_mcp.tools.recommend  # noqa: E402, F401
import cited_mcp.tools.solution  # noqa: E402, F401


def run_server() -> None:
    """Start the MCP server on stdio transport."""
    mcp.run(transport="stdio")
