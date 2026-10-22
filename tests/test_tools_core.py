"""cited_core.tools: the thin client every interface uses to run a tool."""

from __future__ import annotations

import json

import httpx
import respx

from cited_core.api.client import CitedClient
from cited_core.tools import bundled_manifest, call_tool, fetch_manifest, run_tool, tool_names

API = "https://dev.youcited.com"

EXPECTED_TOOLS = [
    "free_audit",
    "agent_signup",
    "account_status",
    "buy_credits",
    "setup_business",
    "get_business",
    "get_agent_brief",
    "draft_questions",
    "quote_audit",
    "run_audit",
    "get_audit",
    "compare_audits",
    "schedule_recheck",
    "get_recommendations",
    "update_recommendation",
    "generate_fixes",
    "get_fixes",
    "update_fix",
    "search_docs",
]


def test_bundled_manifest_is_the_approved_tool_list():
    manifest = bundled_manifest()
    assert tool_names(manifest) == EXPECTED_TOOLS
    for tool in manifest["tools"]:
        assert tool["input_schema"]["type"] == "object"
        assert tool["description"]
        assert "readOnlyHint" in tool["annotations"]


@respx.mock
def test_fetch_manifest_prefers_the_api():
    live = {"version": "x", "tools": [{"name": "free_audit"}]}
    respx.get(f"{API}/agent/tools").mock(return_value=httpx.Response(200, json=live))
    assert fetch_manifest(CitedClient(API)) == live


@respx.mock
def test_fetch_manifest_falls_back_to_the_bundled_snapshot():
    respx.get(f"{API}/agent/tools").mock(side_effect=httpx.ConnectError("down"))
    assert tool_names(fetch_manifest(CitedClient(API))) == EXPECTED_TOOLS


@respx.mock
def test_call_tool_sends_arguments_and_credentials():
    route = respx.post(f"{API}/agent/tools/get_audit").mock(
        return_value=httpx.Response(200, json={"audits": []})
    )
    result, status = call_tool(CitedClient(API, agent_api_key="cak_x"), "get_audit", {"limit": 5})
    assert (result, status) == ({"audits": []}, 200)
    request = route.calls[0].request
    assert json.loads(request.content) == {"limit": 5}
    assert request.headers["X-Agent-API-Key"] == "cak_x"


@respx.mock
def test_call_tool_keeps_tool_errors_and_normalizes_api_errors():
    respx.post(f"{API}/agent/tools/run_audit").mock(
        return_value=httpx.Response(
            402, json={"error": "Not enough credits", "status_code": 402, "credits_needed": 8}
        )
    )
    respx.post(f"{API}/agent/tools/get_audit").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid, expired or revoked API key"})
    )
    result, status = call_tool(CitedClient(API), "run_audit")
    assert status == 402 and result["credits_needed"] == 8
    result, status = call_tool(CitedClient(API), "get_audit")
    assert status == 401
    assert result == {
        "error": "Invalid, expired or revoked API key",
        "status_code": 401,
        "error_type": "login_required",
    }


@respx.mock
def test_call_tool_reports_an_unreachable_api():
    respx.post(f"{API}/agent/tools/get_audit").mock(side_effect=httpx.ConnectError("down"))
    result, status = call_tool(CitedClient(API), "get_audit")
    assert status == 503 and "Could not reach" in result["error"]


@respx.mock
def test_agent_signup_saves_the_key_and_never_returns_it(creds):
    respx.post(f"{API}/agent/tools/agent_signup").mock(
        return_value=httpx.Response(
            200,
            json={
                "api_key": "cak_secret",
                "claim": {"url": "https://x/claim", "code": "123456"},
                "next_steps": ["Store api_key now; it is shown only once.", "Show the claim"],
            },
        )
    )
    client = CitedClient(API)
    result, status = run_tool(client, "dev", "agent_signup", {}, store=creds)
    assert status == 200
    assert "api_key" not in result and "cak_secret" not in json.dumps(result)
    assert result["api_key_saved"] is True
    assert result["next_steps"][1] == "Show the claim"
    assert creds.get_agent_key("dev") == "cak_secret"
    assert client.agent_api_key == "cak_secret"
