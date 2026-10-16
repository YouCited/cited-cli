"""MCP tool tests for credits billing, agent signup/keys, error surfacing and notices."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from cited_core.api.client import CitedClient
from cited_mcp.context import CitedContext

DEV_API = "https://dev.youcited.com"
BUY_URL = "https://youcited.com/app/billing"
API_KEY = "cak_live_secret_abcdef"


@pytest.fixture(autouse=True)
def _mcp_server():
    import cited_mcp.server as server_mod

    if server_mod.mcp is None:
        server_mod.create_stdio_server()
    from cited_mcp.tools._helpers import _rate_limits

    _rate_limits.clear()
    yield
    _rate_limits.clear()


@pytest.fixture
def creds_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_dir = tmp_path / ".cited"
    creds = config_dir / "credentials.json"
    monkeypatch.setattr("cited_core.auth.store.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.auth.store.CREDENTIALS_FILE", creds)
    monkeypatch.setattr("cited_core.auth.store.TokenStore._has_keyring", lambda self: False)
    return creds


def _ctx(
    token: str | None = "test-token", agent_api_key: str | None = None
) -> tuple[Any, CitedContext]:
    client = CitedClient(base_url=DEV_API, token=token, agent_api_key=agent_api_key)
    cited_ctx = CitedContext(client=client, env="dev", api_url=DEV_API)
    ctx = MagicMock()
    ctx.request_context.lifespan_context = cited_ctx
    return ctx, cited_ctx


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _body(route: respx.Route) -> Any:
    return json.loads(route.calls.last.request.content)


# --- Prices / balance / history -------------------------------------------------


@respx.mock
def test_get_prices_without_auth():
    from cited_mcp.tools.billing import get_prices

    respx.get(f"{DEV_API}/billing/prices").mock(
        return_value=httpx.Response(200, json={"audit": {"credits": 10}, "packs": []})
    )
    ctx, cited = _ctx(token=None)
    result = _run(get_prices(ctx))
    assert result["audit"]["credits"] == 10
    cited.client.close()


def test_get_credits_requires_auth():
    from cited_mcp.tools.billing import get_credits

    ctx, cited = _ctx(token=None)
    result = _run(get_credits(ctx))
    assert result["error"] is True
    assert "agent_signup" in result["message"]
    cited.client.close()


@respx.mock
def test_get_credits():
    from cited_mcp.tools.billing import get_credits

    respx.get(f"{DEV_API}/billing/credits").mock(
        return_value=httpx.Response(200, json={"balance": 25, "has_purchased": True})
    )
    ctx, cited = _ctx()
    assert _run(get_credits(ctx))["balance"] == 25
    cited.client.close()


@respx.mock
def test_credit_history_passes_limit():
    from cited_mcp.tools.billing import credit_history

    route = respx.get(f"{DEV_API}/billing/credits/transactions").mock(
        return_value=httpx.Response(200, json={"transactions": [{"id": "t1", "delta": -10}]})
    )
    ctx, cited = _ctx()
    result = _run(credit_history(ctx, limit=7))
    assert result["transactions"][0]["delta"] == -10
    assert route.calls.last.request.url.params["limit"] == "7"
    cited.client.close()


# --- Purchases ------------------------------------------------------------------


@respx.mock
def test_buy_credits_returns_checkout_link_for_human():
    from cited_mcp.tools.billing import buy_credits

    route = respx.post(f"{DEV_API}/billing/credits/checkout").mock(
        return_value=httpx.Response(
            200, json={"checkout_url": "https://checkout.stripe.com/c/1", "session_id": "cs_1"}
        )
    )
    ctx, cited = _ctx()
    result = _run(buy_credits(ctx, pack_id="pack_50"))
    assert _body(route) == {"pack_id": "pack_50", "save_card": True}
    assert result["checkout_url"] == "https://checkout.stripe.com/c/1"
    assert "do not say the purchase is done" in result["instructions"]
    cited.client.close()


@respx.mock
def test_buy_credits_no_save_card():
    from cited_mcp.tools.billing import buy_credits

    route = respx.post(f"{DEV_API}/billing/credits/checkout").mock(
        return_value=httpx.Response(200, json={"checkout_url": "https://x"})
    )
    ctx, cited = _ctx()
    _run(buy_credits(ctx, pack_id="pack_20", save_card=False))
    assert _body(route) == {"pack_id": "pack_20", "save_card": False}
    cited.client.close()


@respx.mock
def test_buy_credits_claim_required_surfaces_claim_url():
    from cited_mcp.tools.billing import buy_credits

    respx.post(f"{DEV_API}/billing/credits/checkout").mock(
        return_value=httpx.Response(
            403,
            json={
                "detail": {
                    "error": "claim_required",
                    "message": "Claim this account to buy packs.",
                    "claim_url": "https://youcited.com/claim/tok",
                }
            },
        )
    )
    ctx, cited = _ctx(token=None, agent_api_key=API_KEY)
    result = _run(buy_credits(ctx, pack_id="pack_20"))
    assert result["error"] is True
    assert result["status_code"] == 403
    assert result["error_type"] == "claim_required"
    assert result["message"] == "Claim this account to buy packs."
    assert result["claim_url"] == "https://youcited.com/claim/tok"
    assert "buy_audit" in result["hint"]
    assert "payment_required" not in result
    cited.client.close()


@respx.mock
def test_buy_audit():
    from cited_mcp.tools.billing import buy_audit

    route = respx.post(f"{DEV_API}/billing/audit-checkout").mock(
        return_value=httpx.Response(
            200,
            json={
                "checkout_url": "https://checkout.stripe.com/c/2",
                "price_usd": 15,
                "credits": 10,
            },
        )
    )
    ctx, cited = _ctx(token=None, agent_api_key=API_KEY)
    result = _run(buy_audit(ctx))
    assert _body(route) == {}
    assert route.calls.last.request.headers["X-Agent-API-Key"] == API_KEY
    assert result["price_usd"] == 15
    assert "instructions" in result
    cited.client.close()


# --- 402 surfacing ----------------------------------------------------------------


@respx.mock
def test_start_audit_insufficient_credits_402():
    from cited_mcp.tools.audit import start_audit

    respx.post(f"{DEV_API}/audit/start").mock(
        return_value=httpx.Response(
            402,
            json={
                "detail": {
                    "error": "insufficient_credits",
                    "message": "This audit needs 10 credits; you have 2.",
                    "credits_needed": 10,
                    "balance": 2,
                    "buy_url": BUY_URL,
                }
            },
        )
    )
    ctx, cited = _ctx()
    result = _run(start_audit(ctx, named_audit_id="tmpl-1"))
    assert result["error"] is True
    assert result["status_code"] == 402
    assert result["payment_required"] is True
    assert result["error_type"] == "insufficient_credits"
    assert result["message"] == "This audit needs 10 credits; you have 2."
    assert result["credits_needed"] == 10
    assert result["balance"] == 2
    assert result["buy_url"] == BUY_URL
    assert "buy_audit" in result["hint"]
    assert "upgrade" not in json.dumps(result).lower()
    cited.client.close()


@respx.mock
def test_crawl_purchase_required_402():
    from cited_mcp.tools.business import crawl_business

    respx.post(f"{DEV_API}/businesses/b1/crawl").mock(
        return_value=httpx.Response(
            402,
            json={
                "detail": {
                    "error": "purchase_required",
                    "message": "Buy credits once to unlock crawls.",
                    "buy_url": BUY_URL,
                }
            },
        )
    )
    ctx, cited = _ctx()
    result = _run(crawl_business(ctx, "b1"))
    assert result["error_type"] == "purchase_required"
    assert result["payment_required"] is True
    assert result["buy_url"] == BUY_URL
    assert "credits_needed" not in result
    cited.client.close()


# --- Refunds, auto-refill, quotes -------------------------------------------------


@respx.mock
def test_request_refund_previews_without_confirm():
    from cited_mcp.tools.billing import request_refund

    respx.get(f"{DEV_API}/billing/credits").mock(
        return_value=httpx.Response(
            200,
            json={
                "balance": 15,
                "lots": [
                    {"id": "lot1", "source": "pack", "credits_remaining": 15, "refundable_usd": 15},
                    {"id": "lot0", "source": "pack", "credits_remaining": 5, "refundable_usd": 0},
                ],
            },
        )
    )
    refund = respx.post(f"{DEV_API}/billing/credits/refund").mock(
        return_value=httpx.Response(200, json={})
    )
    ctx, cited = _ctx()
    result = _run(request_refund(ctx))
    assert result["confirmation_required"] is True
    assert result["refundable_usd"] == 15
    assert [lot["id"] for lot in result["lots"]] == ["lot1"]
    assert not refund.called
    cited.client.close()


@respx.mock
def test_request_refund_with_confirm():
    from cited_mcp.tools.billing import request_refund

    refund = respx.post(f"{DEV_API}/billing/credits/refund").mock(
        return_value=httpx.Response(
            200, json={"refunded_usd": 15.0, "credits_removed": 15, "lots": ["lot1"]}
        )
    )
    ctx, cited = _ctx()
    result = _run(request_refund(ctx, confirm=True))
    assert refund.called
    assert result["refunded_usd"] == 15.0
    cited.client.close()


@respx.mock
def test_set_auto_refill():
    from cited_mcp.tools.billing import set_auto_refill

    route = respx.put(f"{DEV_API}/billing/credits/auto-refill").mock(
        return_value=httpx.Response(200, json={"auto_refill": {"enabled": True}})
    )
    ctx, cited = _ctx()
    result = _run(set_auto_refill(ctx, enabled=True, pack_id="pack_50", monthly_cap_usd=100))
    assert _body(route) == {"enabled": True, "pack_id": "pack_50", "monthly_cap_usd": 100}
    assert result["auto_refill"]["enabled"] is True
    cited.client.close()


@respx.mock
def test_set_auto_refill_off_sends_only_enabled():
    from cited_mcp.tools.billing import set_auto_refill

    route = respx.put(f"{DEV_API}/billing/credits/auto-refill").mock(
        return_value=httpx.Response(200, json={})
    )
    ctx, cited = _ctx()
    _run(set_auto_refill(ctx, enabled=False))
    assert _body(route) == {"enabled": False}
    cited.client.close()


@respx.mock
def test_quote_audit():
    from cited_mcp.tools.billing import quote_audit

    route = respx.post(f"{DEV_API}/billing/audit-quote").mock(
        return_value=httpx.Response(
            200,
            json={"credits": 12, "balance": 20, "enough": True, "question_count": 5,
                  "extra_models": ["openai:gpt-5.2"]},
        )
    )
    ctx, cited = _ctx()
    result = _run(quote_audit(ctx, named_audit_id="tmpl-1", models=["openai:gpt-5.2"]))
    assert _body(route) == {"named_audit_id": "tmpl-1", "models": ["openai:gpt-5.2"]}
    assert result["credits"] == 12
    cited.client.close()


# --- Agent signup and keys -------------------------------------------------------

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


@respx.mock
def test_agent_signup_stores_key_and_uses_it(creds_file):
    from cited_core.auth.store import TokenStore
    from cited_mcp.tools.agent_keys import agent_signup
    from cited_mcp.tools.business import list_businesses

    signup = respx.post(f"{DEV_API}/agent/signup").mock(
        return_value=httpx.Response(201, json=SIGNUP_RESPONSE)
    )
    businesses = respx.get(f"{DEV_API}/businesses").mock(
        return_value=httpx.Response(200, json=[])
    )
    ctx, cited = _ctx(token=None)
    result = _run(agent_signup(ctx, agent_name="Helper", owner_email="owner@acme.io"))

    assert _body(signup) == {"agent_name": "Helper", "owner_email": "owner@acme.io"}
    assert "X-Agent-API-Key" not in signup.calls.last.request.headers
    assert "api_key" not in result
    assert result["api_key_saved"] is True
    assert result["claim"]["url"] == "https://youcited.com/claim/tok123"
    assert result["claim"]["code"] == "123456"
    assert "https://youcited.com/claim/tok123" in result["instructions"]
    assert "123456" in result["instructions"]

    # Persisted for future runs ...
    assert TokenStore().get_agent_key("dev") == API_KEY
    assert json.loads(creds_file.read_text())["agent_key:dev"] == API_KEY
    # ... and used by later calls in this process.
    listed = _run(list_businesses(ctx))
    assert "error" not in listed
    assert businesses.calls.last.request.headers["X-Agent-API-Key"] == API_KEY
    cited.client.close()


def test_agent_signup_refused_when_signed_in():
    from cited_mcp.tools.agent_keys import agent_signup

    ctx, cited = _ctx(token="test-token")
    result = _run(agent_signup(ctx))
    assert result["error"] is True
    assert result["error_type"] == "already_authenticated"
    cited.client.close()


def test_agent_signup_refused_when_key_configured():
    from cited_mcp.tools.agent_keys import agent_signup

    ctx, cited = _ctx(token=None, agent_api_key=API_KEY)
    result = _run(agent_signup(ctx))
    assert result["error_type"] == "already_has_agent_key"
    cited.client.close()


@respx.mock
def test_agent_signup_rate_limited_error():
    from cited_mcp.tools.agent_keys import agent_signup

    respx.post(f"{DEV_API}/agent/signup").mock(
        return_value=httpx.Response(429, json={"detail": "Too many signups"})
    )
    ctx, cited = _ctx(token=None)
    result = _run(agent_signup(ctx))
    assert result["error"] is True
    assert result["status_code"] == 429
    cited.client.close()


@respx.mock
def test_key_status_list_and_revoke():
    from cited_mcp.tools.agent_keys import key_status, list_api_keys, revoke_api_key

    respx.get(f"{DEV_API}/agent/key-status").mock(
        return_value=httpx.Response(200, json={"key_prefix": "cak_live", "days_left": 90})
    )
    respx.get(f"{DEV_API}/agent-keys").mock(
        return_value=httpx.Response(200, json={"keys": [{"id": "k1", "status": "active"}]})
    )
    revoke = respx.delete(f"{DEV_API}/agent-keys/k1").mock(
        return_value=httpx.Response(200, json={"revoked": True})
    )
    ctx, cited = _ctx(token=None, agent_api_key=API_KEY)
    assert _run(key_status(ctx))["days_left"] == 90
    assert _run(list_api_keys(ctx))["keys"][0]["id"] == "k1"
    assert _run(revoke_api_key(ctx, key_id="k1"))["revoked"] is True
    assert revoke.calls.last.request.headers["X-Agent-API-Key"] == API_KEY
    cited.client.close()


@respx.mock
def test_check_auth_status_with_agent_key():
    from cited_mcp.tools.auth import check_auth_status

    respx.get(f"{DEV_API}/auth/me").mock(
        return_value=httpx.Response(200, json={"email": "a@b.c", "credits_balance": 10})
    )
    respx.get(f"{DEV_API}/businesses").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{DEV_API}/agent/key-status").mock(
        return_value=httpx.Response(
            200,
            json={
                "key_prefix": "cak_live",
                "unclaimed": False,
                "key_expires_at": "2027-01-14T00:00:00Z",
                "days_left": 90,
                "oauth": {"mcp_url": "https://mcp.youcited.com/mcp"},
            },
        )
    )
    ctx, cited = _ctx(token=None, agent_api_key=API_KEY)
    result = _run(check_auth_status(ctx))
    assert result["auth_method"] == "agent_key"
    assert result["agent_key"]["days_left"] == 90
    assert "2027-01-14" in result["auth_note"]
    assert "https://mcp.youcited.com/mcp" in result["auth_note"]
    cited.client.close()


@respx.mock
def test_check_auth_status_with_session_has_no_agent_key_block():
    from cited_mcp.tools.auth import check_auth_status

    respx.get(f"{DEV_API}/auth/me").mock(return_value=httpx.Response(200, json={"email": "a"}))
    respx.get(f"{DEV_API}/businesses").mock(return_value=httpx.Response(200, json=[]))
    ctx, cited = _ctx()
    result = _run(check_auth_status(ctx))
    assert result["auth_method"] == "session"
    assert "agent_key" not in result
    cited.client.close()


# --- X-Cited-Notice passthrough --------------------------------------------------


@respx.mock
def test_notice_header_added_to_tool_result():
    from cited_mcp.tools.business import get_business, list_businesses

    notice = "This agent key expires in 12 days. Connect https://mcp.youcited.com/mcp with OAuth."
    respx.get(f"{DEV_API}/businesses").mock(
        return_value=httpx.Response(200, json=[{"id": "b1"}], headers={"X-Cited-Notice": notice})
    )
    respx.get(f"{DEV_API}/businesses/b1").mock(
        return_value=httpx.Response(200, json={"id": "b1"})
    )
    ctx, cited = _ctx(token=None, agent_api_key=API_KEY)
    listed = _run(list_businesses(ctx))
    assert listed["notice"] == notice
    assert listed["data"][0]["id"] == "b1"
    # A later call without the header carries no stale notice.
    got = _run(get_business(ctx, business_id="b1"))
    assert "notice" not in got
    cited.client.close()


@respx.mock
def test_notice_header_added_to_error_result():
    from cited_mcp.tools.billing import get_credits

    respx.get(f"{DEV_API}/billing/credits").mock(
        return_value=httpx.Response(
            500, json={"detail": "boom"}, headers={"X-Cited-Notice": "Key expires soon."}
        )
    )
    ctx, cited = _ctx(token=None, agent_api_key=API_KEY)
    result = _run(get_credits(ctx))
    assert result["error"] is True
    assert result["notice"] == "Key expires soon."
    cited.client.close()


# --- Hosted MCP: agent key as Bearer token ---------------------------------------


def test_auth_provider_accepts_agent_key_bearer():
    from cited_mcp.auth_provider import CitedOAuthProvider

    provider = CitedOAuthProvider(
        backend_url=DEV_API, mcp_url="https://mcp.example.com", jwt_secret="x" * 32
    )
    token = _run(provider.load_access_token(API_KEY))
    assert token is not None
    assert token.agent_api_key == API_KEY
    assert token.user_jwt == ""
    assert _run(provider.load_access_token("not-a-valid-token")) is None


@respx.mock
def test_remote_agent_key_bearer_reaches_api_as_header():
    from cited_mcp.auth_provider import CitedAccessToken
    from cited_mcp.tools.business import list_businesses

    route = respx.get(f"{DEV_API}/businesses").mock(return_value=httpx.Response(200, json=[]))
    ctx, cited = _ctx(token=None)
    access = CitedAccessToken(
        token=API_KEY, client_id="agent-key", scopes=["cited"], user_jwt="",
        agent_api_key=API_KEY,
    )
    with patch(
        "mcp.server.auth.middleware.auth_context.get_access_token", return_value=access
    ):
        result = _run(list_businesses(ctx))
    assert "error" not in result
    assert route.calls.last.request.headers["X-Agent-API-Key"] == API_KEY
    # The shared lifespan client was not given the key.
    assert cited.client.agent_api_key is None
    cited.client.close()
