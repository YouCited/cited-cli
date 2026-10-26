"""The cited-mcp server: Cited's agent tools over stdio.

A thin client. The tools are defined once, in the Cited API, and this server
lists them from ``GET /agent/tools`` (or the snapshot bundled with cited-core
when the API can't be reached) and runs each call with
``POST /agent/tools/{name}``. The hosted server at mcp.youcited.com serves the
same tools over streamable HTTP with OAuth.

Two tools are local to this server: ``login`` (browser sign-in that stores a
session on this machine) and ``logout``. ``agent_signup`` saves the API key it
creates on this machine instead of returning it.
"""

from __future__ import annotations

import json
import os
import webbrowser
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import anyio
import mcp.types as types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from cited_core import __version__
from cited_core.api import endpoints
from cited_core.api.client import CitedClient
from cited_core.auth.credentials import resolve_agent_api_key
from cited_core.auth.oauth_server import OAuthCallbackServer
from cited_core.auth.store import TokenStore
from cited_core.config.manager import ConfigManager
from cited_core.errors import CitedAPIError
from cited_core.tools import fetch_manifest, run_tool

LOCAL_TOOLS: list[dict[str, Any]] = [
    {
        "name": "login",
        "title": "Log In",
        "description": (
            "Sign in to Cited with a browser. The first call opens the sign-in page "
            "and returns login_url to show the user; once they have signed in, "
            "call it again to finish. force=true signs in again (to switch "
            "accounts). Not needed for free_audit, account_status or search_docs, "
            "and agent_signup makes an account without a login."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "force": {
                    "type": "boolean",
                    "description": "Sign in again even when already signed in.",
                }
            },
        },
        "annotations": {
            "title": "Log In",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "logout",
        "title": "Log Out",
        "description": (
            "Sign out on this machine: forget the stored session, or the agent key "
            "saved by agent_signup when there is no session."
        ),
        "input_schema": {"type": "object", "properties": {}},
        "annotations": {
            "title": "Log Out",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
]
LOCAL_TOOL_NAMES = {t["name"] for t in LOCAL_TOOLS}


@dataclass
class CitedSession:
    """What one server process needs: the API client and the tool list."""

    client: CitedClient
    env: str
    api_url: str
    manifest: dict[str, Any] = field(default_factory=dict)
    pending_login: OAuthCallbackServer | None = None
    store: TokenStore = field(default_factory=TokenStore)

    def use_token(self, token: str | None) -> None:
        self.client.set_token(token)


def build_session(manifest: dict[str, Any] | None = None) -> CitedSession:
    """Credentials from the environment, config and the local store.

    ``CITED_TOKEN`` or the session from ``cited login`` wins; otherwise the
    agent key (``CITED_AGENT_API_KEY``, the ``agent_api_key`` config value, or
    the key ``agent_signup`` saved).
    """
    config = ConfigManager()
    env_override = os.environ.get("CITED_ENV")
    env = config.get_environment(override=env_override)
    api_url = config.get_api_url(env_override=env_override)
    store = TokenStore()
    token = os.environ.get("CITED_TOKEN") or store.get_token(env)
    agent_key = resolve_agent_api_key(config, env, store=store)
    client = CitedClient(base_url=api_url, token=token, agent_api_key=agent_key)
    session = CitedSession(client=client, env=env, api_url=api_url, store=store)
    session.manifest = manifest or fetch_manifest(client)
    return session


def tool_list(session: CitedSession) -> list[types.Tool]:
    entries = [*session.manifest.get("tools", []), *LOCAL_TOOLS]
    return [
        types.Tool(
            name=t["name"],
            title=t.get("title"),
            description=t.get("description"),
            input_schema=t.get("input_schema") or {"type": "object", "properties": {}},
            annotations=types.ToolAnnotations(**t["annotations"])
            if t.get("annotations")
            else None,
        )
        for t in entries
    ]


def _result(data: dict[str, Any], is_error: bool) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(data, indent=2, default=str))],
        structured_content=data,
        is_error=is_error,
    )


# ---------------------------------------------------------------------------
# Local tools
# ---------------------------------------------------------------------------


def _login_url(session: CitedSession, server: OAuthCallbackServer) -> str:
    params = urlencode({**server.authorize_params(), "app_name": "cited-mcp"})
    return f"{session.api_url}{endpoints.AUTHORIZE_APP}?{params}"


def _finish_pending_login(session: CitedSession) -> str | None:
    """Store the token a finished browser sign-in delivered; None while waiting."""
    pending = session.pending_login
    if pending is None or not pending.token:
        return None
    token = pending.token
    pending.shutdown()
    session.pending_login = None
    session.store.save_token(session.env, token)
    session.use_token(token)
    return token


def _whoami(session: CitedSession) -> str:
    try:
        user = session.client.get(endpoints.ME)
    except CitedAPIError:
        return ""
    return str(user.get("email") or "")


def login(session: CitedSession, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    pending = session.pending_login
    if pending is not None and not pending.token and pending.expired:
        pending.shutdown()
        session.pending_login = None

    if _finish_pending_login(session):
        email = _whoami(session)
        return {
            "success": True,
            "message": f"Signed in{' as ' + email if email else ''} ({session.env}).",
            "next_step": "Call account_status.",
        }, False

    force = arguments.get("force") is True
    if session.pending_login is not None and not force:
        return {
            "waiting": True,
            "login_url": _login_url(session, session.pending_login),
            "message": "Still waiting for the browser sign-in. Show the user login_url; "
            "call login again once they have signed in.",
        }, False

    if force:
        if session.pending_login is not None:
            session.pending_login.shutdown()
            session.pending_login = None
        session.store.delete_token(session.env)
        session.use_token(None)
    elif session.client.token:
        email = _whoami(session)
        if email:
            return {"success": True, "message": f"Already signed in as {email}."}, False

    callback = OAuthCallbackServer(timeout=300.0)
    callback.start()
    session.pending_login = callback
    url = _login_url(session, callback)
    try:
        opened = webbrowser.open(url)
    except Exception:
        opened = False
    return {
        "action_required": True,
        "login_url": url,
        "message": (
            "I opened the sign-in page in the browser. "
            if opened
            else "Open login_url in a browser to sign in. "
        )
        + "Once you've signed in, I'll call login again to finish.",
    }, False


def logout(session: CitedSession, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if session.pending_login is not None:
        session.pending_login.shutdown()
        session.pending_login = None
    if session.client.token:
        session.store.delete_token(session.env)
        session.use_token(None)
        return {"success": True, "message": f"Signed out of {session.env}."}, False
    if session.client.agent_api_key:
        session.store.delete_agent_key(session.env)
        session.client.set_agent_api_key(None)
        return {
            "success": True,
            "message": f"Removed the saved agent key ({session.env}).",
        }, False
    return {"success": False, "message": f"Not signed in to {session.env}."}, False


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------


def call(
    session: CitedSession, name: str, arguments: dict[str, Any] | None
) -> types.CallToolResult:
    arguments = arguments or {}
    if name == "login":
        return _result(*login(session, arguments))
    if name == "logout":
        return _result(*logout(session, arguments))

    # A browser sign-in started earlier may have finished in the meantime.
    _finish_pending_login(session)
    session.client.last_notice = None
    result, status = run_tool(session.client, session.env, name, arguments, session.store)
    if session.client.last_notice and "notice" not in result:
        result["notice"] = session.client.last_notice
    if status == 401:
        result.setdefault(
            "hint",
            "Call login to sign in with a browser, or agent_signup to make an "
            "account without one.",
        )
    return _result(result, status >= 400)


def create_server(session: CitedSession) -> Server[Any]:
    async def _list_tools(
        ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tool_list(session))

    async def _call_tool(
        ctx: ServerRequestContext[Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        # The client is synchronous; keep the event loop free while it waits.
        return await anyio.to_thread.run_sync(
            call, session, params.name, params.arguments or {}
        )

    return Server(
        "cited",
        version=__version__,
        instructions=session.manifest.get("instructions"),
        website_url="https://youcited.com",
        on_list_tools=_list_tools,
        on_call_tool=_call_tool,
    )


async def _serve(session: CitedSession) -> None:
    server = create_server(session)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def run_server() -> None:
    """Start the MCP server on stdio."""
    session = build_session()
    try:
        anyio.run(_serve, session)
    finally:
        session.client.close()
