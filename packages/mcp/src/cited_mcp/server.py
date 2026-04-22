from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from cited_core.api.client import CitedClient
from cited_core.auth.store import TokenStore
from cited_core.config.manager import ConfigManager
from cited_mcp.context import CitedContext

# Module-level MCP instance. Tool modules import this via:
#   from cited_mcp.server import mcp
# and register tools with @mcp.tool().
#
# For stdio: set by run_server() before tool imports.
# For remote: set by remote.py before tool imports.
mcp: FastMCP = None  # type: ignore[assignment]


@asynccontextmanager
async def cited_lifespan(server: FastMCP) -> AsyncIterator[CitedContext]:
    """Set up CitedClient for the MCP server lifetime (stdio transport)."""
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


def register_tools() -> None:
    """Import tool modules to trigger @mcp.tool() registrations.

    Must be called after `cited_mcp.server.mcp` is set to a valid FastMCP instance.
    """
    import cited_mcp.tools.auth  # noqa: I001, E402, F401
    import cited_mcp.tools.audit  # noqa: E402, F401
    import cited_mcp.tools.business  # noqa: E402, F401
    import cited_mcp.tools.job  # noqa: E402, F401
    import cited_mcp.tools.recommend  # noqa: E402, F401
    import cited_mcp.tools.solution  # noqa: E402, F401


def create_stdio_server() -> FastMCP:
    """Create the stdio MCP server and register all tools.

    Sets the module-level `mcp` variable so tool modules can find it.
    Idempotent — returns the existing server if already created.
    """
    import cited_mcp.server as _self

    if _self.mcp is not None:
        return _self.mcp

    _self.mcp = FastMCP(
        "cited",
        instructions="Cited GEO platform — audit, optimize, and monitor AI search presence",
        lifespan=cited_lifespan,
    )
    register_tools()
    return _self.mcp


def run_server() -> None:
    """Start the MCP server on stdio transport."""
    server = create_stdio_server()
    server.run(transport="stdio")
