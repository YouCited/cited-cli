"""Docs tools — search and read the public Cited documentation. No login needed."""
from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from cited_core import docs as cited_docs
from cited_core.errors import CitedAPIError
from cited_mcp.context import CitedContext
from cited_mcp.server import mcp
from cited_mcp.tools._helpers import _api_error_response, log_tool_call

# Keep a single article well under the 50 KB response guardrail.
_MAX_DOC_CHARS = 40_000


@mcp.tool(
    title="Search Docs",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),  # noqa: E501
)
@log_tool_call
async def search_docs(
    ctx: Context[Any, CitedContext, Any],
    query: str,
    limit: int = 5,
) -> Any:
    """Search the public Cited documentation (how-tos, GEO concepts, feature guides).

    Use this to answer "how do I ..." questions about Cited or GEO before
    guessing. No login needed. Each result has a `path`; pass it to `get_doc`
    to read the full article as markdown.

    Args:
        ctx: MCP context
        query: Keywords or a question, e.g. "audit templates" or "what is llms.txt"
        limit: Maximum number of results (default 5, max 50)
    """
    try:
        return await asyncio.to_thread(cited_docs.search_docs, query, limit)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Get Doc",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),  # noqa: E501
)
@log_tool_call
async def get_doc(ctx: Context[Any, CitedContext, Any], path: str) -> Any:
    """Read one Cited documentation article as markdown. No login needed.

    Args:
        ctx: MCP context
        path: The doc's `category/slug` from `search_docs` results,
            e.g. "getting-started/quick-start-guide" (a full docs URL also works)
    """
    try:
        doc = await asyncio.to_thread(cited_docs.get_doc, path)
    except CitedAPIError as e:
        return _api_error_response(e)
    content = doc.get("content", "")
    if len(content) > _MAX_DOC_CHARS:
        doc["content"] = content[:_MAX_DOC_CHARS]
        doc["_truncated"] = True
        doc["_hint"] = f"Article truncated; read it in full at {doc['url']}"
    return doc
