from __future__ import annotations

import httpx
import pytest
import respx

from cited_core.api.client import CitedClient
from cited_core.errors import CitedAPIError


@respx.mock
def test_get_success():
    respx.get("https://api.example.com/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    client = CitedClient(base_url="https://api.example.com")
    result = client.get("/health")
    assert result == {"status": "ok"}
    client.close()


@respx.mock
def test_get_404():
    respx.get("https://api.example.com/missing").mock(
        return_value=httpx.Response(404, json={"detail": "Not found"})
    )
    client = CitedClient(base_url="https://api.example.com")
    with pytest.raises(CitedAPIError) as exc_info:
        client.get("/missing")
    assert exc_info.value.status_code == 404
    assert "Not found" in exc_info.value.message
    client.close()


@respx.mock
def test_post_with_json():
    respx.post("https://api.example.com/data").mock(
        return_value=httpx.Response(200, json={"id": "abc"})
    )
    client = CitedClient(base_url="https://api.example.com")
    result = client.post("/data", json={"name": "test"})
    assert result == {"id": "abc"}
    client.close()


@respx.mock
def test_auth_cookie_sent():
    route = respx.get("https://api.example.com/auth/me").mock(
        return_value=httpx.Response(200, json={"email": "test@example.com"})
    )
    client = CitedClient(base_url="https://api.example.com", token="my-jwt-token")
    client.get("/auth/me")
    assert route.called
    request = route.calls[0].request
    assert "advgeo_session=my-jwt-token" in request.headers.get("cookie", "")
    client.close()


@respx.mock
def test_agent_api_key_header():
    route = respx.get("https://api.example.com/agent/v1/business/123/facts").mock(
        return_value=httpx.Response(200, json={"facts": []})
    )
    client = CitedClient(base_url="https://api.example.com", agent_api_key="test-key")
    client.get("/agent/v1/business/123/facts")
    assert route.called
    request = route.calls[0].request
    assert request.headers["x-agent-api-key"] == "test-key"
    client.close()


@respx.mock
def test_context_manager():
    respx.get("https://api.example.com/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    with CitedClient(base_url="https://api.example.com") as client:
        result = client.get("/health")
        assert result["status"] == "ok"


# --- Per-user agent keys, structured errors, notices ---------------------------

API = "https://api.example.com"


@respx.mock
def test_agent_key_sent_on_every_route():
    routes = [
        respx.get(f"{API}/businesses").mock(return_value=httpx.Response(200, json=[])),
        respx.post(f"{API}/audit/start").mock(return_value=httpx.Response(202, json={})),
        respx.put(f"{API}/billing/credits/auto-refill").mock(
            return_value=httpx.Response(200, json={})
        ),
        respx.delete(f"{API}/agent-keys/k1").mock(return_value=httpx.Response(200, json={})),
    ]
    client = CitedClient(base_url=API, agent_api_key="cak_x")
    client.get("/businesses")
    client.post("/audit/start", json={})
    client.put("/billing/credits/auto-refill", json={})
    client.delete("/agent-keys/k1")
    for route in routes:
        assert route.calls.last.request.headers["X-Agent-API-Key"] == "cak_x"
    assert client.auth_method == "agent_key"
    client.close()


@respx.mock
def test_session_token_takes_precedence_over_agent_key():
    route = respx.get(f"{API}/businesses").mock(return_value=httpx.Response(200, json=[]))
    client = CitedClient(base_url=API, token="jwt", agent_api_key="cak_x")
    client.get("/businesses")
    request = route.calls.last.request
    assert "advgeo_session=jwt" in request.headers["cookie"]
    assert "X-Agent-API-Key" not in request.headers
    assert client.auth_method == "token"
    client.close()


@respx.mock
def test_set_token_and_agent_key_switch_headers():
    route = respx.get(f"{API}/x").mock(return_value=httpx.Response(200, json={}))
    client = CitedClient(base_url=API)
    client.set_agent_api_key("cak_x")
    client.get("/x")
    assert route.calls.last.request.headers["X-Agent-API-Key"] == "cak_x"
    client.set_token("jwt")
    client.get("/x")
    assert "X-Agent-API-Key" not in route.calls.last.request.headers
    client.set_token(None)
    client.get("/x")
    assert route.calls.last.request.headers["X-Agent-API-Key"] == "cak_x"
    client.close()


@respx.mock
def test_structured_error_detail():
    respx.post(f"{API}/audit/start").mock(
        return_value=httpx.Response(
            402,
            json={
                "detail": {
                    "error": "insufficient_credits",
                    "message": "Need 10 credits.",
                    "credits_needed": 10,
                    "balance": 2,
                    "buy_url": "https://youcited.com/app/billing",
                }
            },
        )
    )
    client = CitedClient(base_url=API, token="jwt")
    with pytest.raises(CitedAPIError) as exc:
        client.post("/audit/start", json={})
    assert exc.value.status_code == 402
    assert exc.value.message == "Need 10 credits."
    assert exc.value.error_code == "insufficient_credits"
    assert exc.value.detail is not None
    assert exc.value.detail["credits_needed"] == 10
    client.close()


def test_exit_code_for_402():
    from cited_core.errors import ExitCode, exit_code_for_status

    assert exit_code_for_status(402) == ExitCode.PAYMENT_REQUIRED == 6


@respx.mock
def test_notice_header_recorded():
    from cited_core.api.client import clear_notice, get_notice

    respx.get(f"{API}/a").mock(
        return_value=httpx.Response(200, json={}, headers={"X-Cited-Notice": "Switch to OAuth"})
    )
    clear_notice()
    client = CitedClient(base_url=API, agent_api_key="cak_x")
    client.get("/a")
    assert client.last_notice == "Switch to OAuth"
    assert get_notice() == "Switch to OAuth"
    clear_notice()
    assert get_notice() is None
    client.close()


def test_resolve_agent_api_key_order(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from cited_core.auth.credentials import resolve_agent_api_key

    store = MagicMock()
    store.get_agent_key.return_value = "cak_saved"
    config = MagicMock()
    config.get.return_value = None
    monkeypatch.delenv("CITED_AGENT_API_KEY", raising=False)

    assert resolve_agent_api_key(config, "dev", store=store) == "cak_saved"
    store.get_agent_key.assert_called_with("dev")
    config.get.return_value = "cak_config"
    assert resolve_agent_api_key(config, "dev", store=store) == "cak_config"
    monkeypatch.setenv("CITED_AGENT_API_KEY", "cak_env")
    assert resolve_agent_api_key(config, "dev", store=store) == "cak_env"


def test_token_store_agent_key_file_fallback(tmp_path, monkeypatch):
    from cited_core.auth.store import TokenStore

    creds = tmp_path / "credentials.json"
    monkeypatch.setattr("cited_core.auth.store.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("cited_core.auth.store.CREDENTIALS_FILE", creds)
    monkeypatch.setattr("cited_core.auth.store.TokenStore._has_keyring", lambda self: False)
    store = TokenStore()
    store.save_token("dev", "jwt")
    store.save_agent_key("dev", "cak_x")
    assert store.get_agent_key("dev") == "cak_x"
    assert store.get_agent_key("prod") is None
    assert store.get_token("dev") == "jwt"
    store.delete_agent_key("dev")
    assert store.get_agent_key("dev") is None
    assert store.get_token("dev") == "jwt"


@pytest.mark.parametrize(
    ("kwargs", "header"),
    [({"token": "jwt"}, "cookie"), ({"agent_api_key": "cak_test"}, "x-agent-api-key")],
)
@respx.mock
def test_redirect_to_another_host_drops_credentials(kwargs, header):
    respx.get("https://api.example.com/moved").mock(
        return_value=httpx.Response(302, headers={"Location": "https://other.example.net/x"})
    )
    other = respx.get("https://other.example.net/x").mock(
        return_value=httpx.Response(200, json={})
    )
    client = CitedClient(base_url="https://api.example.com", **kwargs)
    client.get("/moved")
    assert header not in other.calls[0].request.headers
    client.close()


@respx.mock
def test_redirect_on_the_same_host_keeps_credentials():
    respx.get("https://api.example.com/items").mock(
        return_value=httpx.Response(307, headers={"Location": "https://api.example.com/items/"})
    )
    target = respx.get("https://api.example.com/items/").mock(
        return_value=httpx.Response(200, json={})
    )
    client = CitedClient(base_url="https://api.example.com", token="jwt")
    client.get("/items")
    assert target.calls[0].request.headers["cookie"] == "advgeo_session=jwt"
    client.close()


@respx.mock
def test_user_agent_names_the_version_and_the_ci_tag(monkeypatch):
    from cited_core import __version__

    route = respx.get("https://api.example.com/health").mock(
        return_value=httpx.Response(200, json={})
    )
    CitedClient(base_url="https://api.example.com").get("/health")
    assert route.calls[-1].request.headers["User-Agent"] == f"cited/{__version__}"

    monkeypatch.setenv("CITED_USER_AGENT_TAG", "cited-ci")
    CitedClient(base_url="https://api.example.com").get("/health")
    assert route.calls[-1].request.headers["User-Agent"] == f"cited/{__version__} cited-ci"
