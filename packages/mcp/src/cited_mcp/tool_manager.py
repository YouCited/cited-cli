"""Custom FastMCP ToolManager that returns a structured payload for unknown tools.

FastMCP's default behavior on `tools/call` for an unregistered tool name is to
raise ``ToolError("Unknown tool: <name>")``, which the protocol layer converts
into a generic JSON-RPC error. That signal is hard for an agent to act on —
the most common cause is a stale MCP-client tool cache after a Cited release,
which the agent CAN fix by calling ``whats_new`` or comparing
``tools_fingerprint`` from ``ping``, but the generic error doesn't say so.

This manager intercepts the unknown-tool path and instead returns a structured
``tool_unavailable`` dict that the agent can read directly:

    {
      "error": true,
      "error_type": "tool_unavailable",
      "message": "Tool 'old_name' is not registered. It may have been removed
                  or renamed. Call `whats_new` or `ping` (compare
                  tools_fingerprint) to detect stale tool surface.",
      "_request_id": "<12-char hex>"
    }

Resource-not-found (audit_id missing, business not found, etc.) is unaffected
— that goes through the normal CitedAPIError path. This shape is specifically
for *tool*-not-found.

The implementation is intentionally pure Python (no ASGI middleware, no
streamed-body parsing) so it survives FastMCP upgrades and is testable
without standing up a transport.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp.tools import ToolManager

if TYPE_CHECKING:
    from mcp.server.fastmcp.server import Context
    from mcp.server.session import ServerSessionT
    from mcp.shared.context import LifespanContextT, RequestT


logger = logging.getLogger("cited_mcp.usage")


class CitedToolManager(ToolManager):
    """ToolManager that returns a structured payload on unknown tools.

    All known tools are dispatched normally via ``super().call_tool``.
    """

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Context[ServerSessionT, LifespanContextT, RequestT] | None = None,
        convert_result: bool = False,
    ) -> Any:
        if name in self._tools:
            return await super().call_tool(
                name, arguments, context=context, convert_result=convert_result
            )

        request_id = uuid.uuid4().hex[:12]
        logger.info(
            json.dumps(
                {
                    "event": "tool_unavailable",
                    "request_id": request_id,
                    "tool": name,
                }
            )
        )
        return {
            "error": True,
            "error_type": "tool_unavailable",
            "message": (
                f"Tool '{name}' is not registered. It may have been removed or "
                "renamed. Call `whats_new` or `ping` (compare tools_fingerprint) "
                "to detect stale tool surface."
            ),
            "_request_id": request_id,
        }


def install(server: Any) -> None:
    """Replace the FastMCP server's ToolManager with CitedToolManager.

    Preserves all already-registered tools and the original
    warn_on_duplicate_tools setting. Idempotent: safe to call repeatedly,
    no-ops if the manager is already a CitedToolManager.
    """
    if isinstance(server._tool_manager, CitedToolManager):
        return
    existing = server._tool_manager
    server._tool_manager = CitedToolManager(
        warn_on_duplicate_tools=existing.warn_on_duplicate_tools,
        tools=existing.list_tools(),
    )
