from __future__ import annotations

import hashlib
import json
import os
from collections.abc import AsyncIterator, Iterable
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

# Tool surface snapshot, populated once after register_tools() by
# cache_tool_surface(). Exposed via the `ping` tool so agent skills can detect
# stale MCP-client tool caches without relying on tools/list_changed.
_TOOLS_FINGERPRINT: str | None = None
_TOOLS_COUNT: int = 0


def _hash_tool_surface(items: Iterable[tuple[str, str, str]]) -> str:
    """Return a 12-char fingerprint over (name, description, schema_json) tuples.

    Pure function — order-independent, deterministic. Extracted so the hash
    algorithm is testable without standing up a FastMCP instance.
    """
    serialized = json.dumps(sorted(items))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]


def compute_tools_fingerprint(server: FastMCP) -> str:
    """Hash the registered tool surface (name + description + input schema).

    Any change a client would notice — added/removed tool, edited docstring,
    edited parameter schema — produces a different fingerprint.
    """
    items = (
        (
            tool.name,
            tool.description or "",
            json.dumps(tool.parameters or {}, sort_keys=True),
        )
        for tool in server._tool_manager.list_tools()
    )
    return _hash_tool_surface(items)


def cache_tool_surface(server: FastMCP) -> None:
    """Populate module-level fingerprint/count caches. Call once post-register."""
    import cited_mcp.server as _self

    _self._TOOLS_FINGERPRINT = compute_tools_fingerprint(server)
    _self._TOOLS_COUNT = len(server._tool_manager.list_tools())


def get_tools_fingerprint() -> str | None:
    """Cached fingerprint computed at startup, or None before registration."""
    return _TOOLS_FINGERPRINT


def get_tools_count() -> int:
    """Cached tool count from startup, or 0 before registration."""
    return _TOOLS_COUNT


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
    import cited_mcp.tools.action_plan  # noqa: I001, E402, F401
    import cited_mcp.tools.agent  # noqa: E402, F401
    import cited_mcp.tools.analytics  # noqa: E402, F401
    import cited_mcp.tools.auth  # noqa: E402, F401
    import cited_mcp.tools.billing  # noqa: E402, F401
    import cited_mcp.tools.audit  # noqa: E402, F401
    import cited_mcp.tools.business  # noqa: E402, F401
    import cited_mcp.tools.changelog  # noqa: E402, F401
    import cited_mcp.tools.hq  # noqa: E402, F401
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
    # Replace FastMCP's default ToolManager with our subclass that returns a
    # structured tool_unavailable payload on unknown tool names instead of
    # raising a generic ToolError. Must run AFTER register_tools so the new
    # manager inherits the registered tool set.
    from cited_mcp.tool_manager import install as _install_tool_manager
    _install_tool_manager(_self.mcp)
    cache_tool_surface(_self.mcp)
    return _self.mcp


def run_server() -> None:
    """Start the MCP server on stdio transport."""
    server = create_stdio_server()
    server.run(transport="stdio")
