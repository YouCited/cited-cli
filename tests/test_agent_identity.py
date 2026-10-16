"""CLI tests for agent signup and per-user agent keys (`cited agent ...`, auth status)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from tests.test_credits import DEV_API, setup_config

API_KEY = "cak_live_secret_abcdef"

SIGNUP_RESPONSE = {
    "api_key": API_KEY,
    "key_prefix": "cak_live",
    "user_id": "u-agent",
    "account": {
        "unclaimed": True,
        "expires_at": "2026-10-23T00:00:00Z",
        "limits": {"businesses": 1, "audits": 1},
    },
    "claim": {
        "url": "https://youcited.com/claim/tok123",
        "code": "123456",
        "expires_at": "2026-10-23T00:00:00Z",
    },
    "oauth": {"mcp_url": "https://mcp.youcited.com/mcp"},
    "next_steps": ["Give your human the claim link and code."],
}

KEY_STATUS = {
    "key_prefix": "cak_live",
    "unclaimed": False,
    "account_expires_at": None,
    "key_expires_at": "2027-01-14T00:00:00Z",
    "days_left": 90,
    "notice": "This key expires in 90 days. Switch to OAuth.",
    "oauth": {
        "mcp_url": "https://mcp.youcited.com/mcp",
        "instructions": "Connect the hosted MCP server and sign in.",
    },
}


def _invoke(runner: Any, app: Any, *args: str, **kwargs: Any) -> Any:
    return runner.invoke(app, ["--env", "dev", *args], **kwargs)


@pytest.fixture
def no_creds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return setup_config(tmp_path, monkeypatch, {})


@pytest.fixture
def with_agent_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return setup_config(tmp_path, monkeypatch, {"agent_key:dev": API_KEY})


@respx.mock
def test_signup_saves_key_and_prints_claim(runner, cli_app, no_creds):
    route = respx.post(f"{DEV_API}/agent/signup").mock(
        return_value=httpx.Response(201, json=SIGNUP_RESPONSE)
    )
    result = _invoke(
        runner, cli_app, "agent", "signup", "--name", "Helper", "--email", "owner@acme.io"
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert json.loads(request.content) == {"agent_name": "Helper", "owner_email": "owner@acme.io"}
    assert "X-Agent-API-Key" not in request.headers
    assert "https://youcited.com/claim/tok123" in result.output
    assert "123456" in result.output
    assert API_KEY not in result.output
    assert json.loads(no_creds.read_text())["agent_key:dev"] == API_KEY


@respx.mock
def test_signup_json_omits_key(runner, cli_app, no_creds):
    respx.post(f"{DEV_API}/agent/signup").mock(
        return_value=httpx.Response(201, json=SIGNUP_RESPONSE)
    )
    result = _invoke(runner, cli_app, "--json", "agent", "signup")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "api_key" not in data
    assert data["api_key_saved"] is True
    assert data["claim"]["code"] == "123456"


def test_signup_refused_when_logged_in(runner, cli_app, tmp_path, monkeypatch):
    setup_config(tmp_path, monkeypatch, {"dev": "test-jwt-dev-token"})
    result = _invoke(runner, cli_app, "agent", "signup")
    assert result.exit_code == 4
    assert "logged in" in result.output


def test_signup_refused_when_key_saved(runner, cli_app, with_agent_key):
    result = _invoke(runner, cli_app, "agent", "signup")
    assert result.exit_code == 4
    assert "already saved" in result.output


@respx.mock
def test_saved_agent_key_sent_on_normal_routes(runner, cli_app, with_agent_key):
    route = respx.get(f"{DEV_API}/businesses").mock(return_value=httpx.Response(200, json=[]))
    result = _invoke(runner, cli_app, "--json", "business", "list")
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.headers["X-Agent-API-Key"] == API_KEY
    assert "advgeo_session" not in request.headers.get("cookie", "")


@respx.mock
def test_session_token_takes_precedence_over_agent_key(runner, cli_app, tmp_path, monkeypatch):
    setup_config(
        tmp_path, monkeypatch, {"dev": "test-jwt-dev-token", "agent_key:dev": API_KEY}
    )
    route = respx.get(f"{DEV_API}/businesses").mock(return_value=httpx.Response(200, json=[]))
    result = _invoke(runner, cli_app, "--json", "business", "list")
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert "advgeo_session=test-jwt-dev-token" in request.headers["cookie"]
    assert "X-Agent-API-Key" not in request.headers


@respx.mock
def test_env_var_agent_key(runner, cli_app, no_creds, monkeypatch):
    monkeypatch.setenv("CITED_AGENT_API_KEY", "cak_from_env")
    route = respx.get(f"{DEV_API}/billing/credits").mock(
        return_value=httpx.Response(200, json={"balance": 0, "lots": []})
    )
    result = _invoke(runner, cli_app, "--json", "credits", "balance")
    assert result.exit_code == 0, result.output
    assert route.calls.last.request.headers["X-Agent-API-Key"] == "cak_from_env"


@respx.mock
def test_agent_api_commands_accept_session_token(runner, cli_app, tmp_path, monkeypatch):
    setup_config(tmp_path, monkeypatch, {"dev": "test-jwt-dev-token"})
    respx.get(f"{DEV_API}/agent/v1/business/b1/facts").mock(
        return_value=httpx.Response(200, json={"name": "Acme"})
    )
    result = _invoke(runner, cli_app, "--json", "agent", "facts", "b1")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["name"] == "Acme"


@respx.mock
def test_key_status(runner, cli_app, with_agent_key):
    route = respx.get(f"{DEV_API}/agent/key-status").mock(
        return_value=httpx.Response(200, json=KEY_STATUS)
    )
    result = _invoke(runner, cli_app, "agent", "key-status")
    assert result.exit_code == 0, result.output
    assert route.calls.last.request.headers["X-Agent-API-Key"] == API_KEY
    assert "2027-01-14" in result.output
    assert "Switch to OAuth" in result.output


@respx.mock
def test_keys_list(runner, cli_app, with_agent_key):
    respx.get(f"{DEV_API}/agent-keys").mock(
        return_value=httpx.Response(
            200,
            json={
                "keys": [
                    {
                        "id": "k1",
                        "key_prefix": "cak_live",
                        "label": "Helper",
                        "created_at": "2026-10-16T00:00:00Z",
                        "last_used_at": None,
                        "expires_at": None,
                        "revoked_at": None,
                        "status": "active",
                    }
                ]
            },
        )
    )
    result = _invoke(runner, cli_app, "--json", "agent", "keys")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["keys"][0]["status"] == "active"


@respx.mock
def test_revoke_key(runner, cli_app, with_agent_key):
    route = respx.delete(f"{DEV_API}/agent-keys/k1").mock(
        return_value=httpx.Response(200, json={"revoked": True})
    )
    result = _invoke(runner, cli_app, "agent", "revoke", "k1", "--yes")
    assert result.exit_code == 0, result.output
    assert route.called
    assert "Revoked agent key k1" in result.output


@respx.mock
def test_auth_status_with_agent_key_mentions_expiry_and_oauth(runner, cli_app, with_agent_key):
    respx.get(f"{DEV_API}/auth/me").mock(
        return_value=httpx.Response(
            200,
            json={"email": "agent@agents.youcited.com", "credits_balance": 10, "unclaimed": False},
        )
    )
    respx.get(f"{DEV_API}/agent/key-status").mock(
        return_value=httpx.Response(200, json=KEY_STATUS)
    )
    result = _invoke(runner, cli_app, "auth", "status")
    assert result.exit_code == 0, result.output
    assert "agent_key" in result.output
    assert "expires on 2027-01-14" in result.output
    assert "https://mcp.youcited.com/mcp" in result.output


@respx.mock
def test_auth_status_json_agent_key(runner, cli_app, with_agent_key):
    respx.get(f"{DEV_API}/auth/me").mock(
        return_value=httpx.Response(
            200, json={"email": "a@b.c", "credits_balance": 0, "unclaimed": True}
        )
    )
    respx.get(f"{DEV_API}/agent/key-status").mock(
        return_value=httpx.Response(
            200,
            json={**KEY_STATUS, "unclaimed": True, "account_expires_at": "2026-10-23"},
        )
    )
    result = _invoke(runner, cli_app, "--json", "auth", "status")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["auth_method"] == "agent_key"
    assert data["unclaimed"] is True
    assert data["account_expires_at"] == "2026-10-23"
    assert "plan" not in data


def test_logout_removes_saved_agent_key(runner, cli_app, with_agent_key):
    result = _invoke(runner, cli_app, "logout")
    assert result.exit_code == 0, result.output
    assert "agent_key:dev" not in json.loads(with_agent_key.read_text())
