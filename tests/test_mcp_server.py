"""The cited-mcp server: the shared tools plus local login/logout."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from cited_core.api.client import CitedClient
from cited_core.tools import bundled_manifest, tool_names

API = "https://dev.youcited.com"

EXPECTED_TOOLS = [*tool_names(bundled_manifest()), "login", "logout"]


@pytest.fixture
def session(creds, monkeypatch):
    from cited_mcp.server import CitedSession

    monkeypatch.setattr("cited_mcp.server.webbrowser.open", lambda url: True)
    s = CitedSession(
        client=CitedClient(API), env="dev", api_url=API, manifest=bundled_manifest(), store=creds
    )
    yield s
    if s.pending_login is not None:
        s.pending_login.shutdown()


def test_lists_the_shared_tools_and_local_ones(session):
    from cited_mcp.server import tool_list

    tools = {t.name: t for t in tool_list(session)}
    assert list(tools) == EXPECTED_TOOLS
    assert tools["run_audit"].annotations.read_only_hint is False
    assert tools["get_business"].annotations.read_only_hint is True
    assert tools["free_audit"].input_schema["properties"]["url"]["type"] == "string"
    assert tools["login"].title == "Log In"


@respx.mock
def test_calls_go_to_the_api(session):
    from cited_mcp.server import call

    route = respx.post(f"{API}/agent/tools/get_audit").mock(
        return_value=httpx.Response(200, json={"audits": []}, headers={"X-Cited-Notice": "hi"})
    )
    result = call(session, "get_audit", {"limit": 2})
    assert json.loads(route.calls[0].request.content) == {"limit": 2}
    assert result.is_error is False
    assert result.structured_content == {"audits": [], "notice": "hi"}


@respx.mock
def test_errors_are_marked_and_point_at_login(session):
    from cited_mcp.server import call

    respx.post(f"{API}/agent/tools/get_business").mock(
        return_value=httpx.Response(
            401, json={"error": "Sign in first", "status_code": 401, "error_type": "login_required"}
        )
    )
    result = call(session, "get_business", {})
    assert result.is_error is True
    assert "login" in result.structured_content["hint"]


@respx.mock
def test_agent_signup_keeps_the_key_local(session, creds):
    from cited_mcp.server import call

    respx.post(f"{API}/agent/tools/agent_signup").mock(
        return_value=httpx.Response(200, json={"api_key": "cak_new", "claim": {"code": "1"}})
    )
    result = call(session, "agent_signup", {})
    assert "cak_new" not in result.content[0].text
    assert creds.get_agent_key("dev") == "cak_new"
    assert session.client.agent_api_key == "cak_new"


def test_login_starts_a_browser_sign_in_then_finishes(session, creds):
    from cited_mcp.server import call

    first = call(session, "login", {}).structured_content
    assert first["action_required"] is True
    assert first["login_url"].startswith(f"{API}/auth/authorize-app?")
    assert call(session, "login", {}).structured_content["waiting"] is True

    session.pending_login.token = "jwt-token"
    with respx.mock:
        respx.get(f"{API}/auth/me").mock(
            return_value=httpx.Response(200, json={"email": "a@b.co"})
        )
        done = call(session, "login", {}).structured_content
    assert done["success"] is True and "a@b.co" in done["message"]
    assert creds.get_token("dev") == "jwt-token"
    assert session.client.token == "jwt-token"


def test_logout_forgets_the_session_then_the_agent_key(session, creds):
    from cited_mcp.server import call

    creds.save_token("dev", "jwt")
    session.client.set_token("jwt")
    session.client.set_agent_api_key("cak_x")
    creds.save_agent_key("dev", "cak_x")
    assert "Signed out" in call(session, "logout", {}).structured_content["message"]
    assert creds.get_token("dev") is None
    assert "agent key" in call(session, "logout", {}).structured_content["message"]
    assert creds.get_agent_key("dev") is None
    assert call(session, "logout", {}).structured_content["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
@pytest.mark.parametrize("mode", ["legacy", "2026-07-28"])
async def test_server_answers_over_mcp(session, anyio_backend, mode):
    """List and call tools through a real MCP client, in memory: ``legacy`` is
    the initialize handshake, 2026-07-28 the per-request protocol."""
    from mcp import Client

    from cited_mcp.server import create_server

    server = create_server(session)
    with respx.mock:
        respx.post(f"{API}/agent/tools/search_docs").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        async with Client(server, mode=mode) as client:
            listed = await client.list_tools()
            assert [t.name for t in listed.tools] == EXPECTED_TOOLS
            result = await client.call_tool("search_docs", {"query": "x"})
            assert result.structured_content == {"results": []}
