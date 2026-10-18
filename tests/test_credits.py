"""CLI tests for pay-as-you-go credits: `cited credits ...` and `cited audit quote`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

DEV_API = "https://dev.youcited.com"
BUY_URL = "https://youcited.com/app/billing"

PRICES = {
    "currency": "usd",
    "credit_value_usd": 1,
    "audit": {"credits": 10, "questions_included": 5, "extra_model_credits": 2},
    "single_audit": {"price_usd": 15, "credits": 10},
    "packs": [
        {"id": "pack_20", "price_usd": 20, "bonus_percent": 0, "credits": 20},
        {"id": "pack_50", "price_usd": 50, "bonus_percent": 10, "credits": 55},
        {"id": "pack_100", "price_usd": 100, "bonus_percent": 20, "credits": 120},
    ],
    "credits_expire_after_months": 12,
    "refund_window_days": 30,
    "auto_refill": {"bonus_percent": 20, "default_monthly_cap_usd": 200},
}

CREDITS = {
    "balance": 25,
    "has_purchased": True,
    "unclaimed": False,
    "lots": [
        {
            "id": "lot1",
            "source": "pack",
            "pack_id": "pack_20",
            "credits_granted": 20,
            "credits_remaining": 15,
            "paid_usd": 20,
            "purchased_at": "2026-10-01T00:00:00Z",
            "expires_at": "2027-10-01T00:00:00Z",
            "refundable_usd": 15.0,
            "refunded_at": None,
            "refunded_usd": None,
        }
    ],
    "saved_card": {"brand": "visa", "last4": "4242"},
    "auto_refill": {
        "enabled": False,
        "pack_id": None,
        "monthly_cap_usd": 200,
        "paused": False,
        "pause_reason": None,
        "spent_this_month_usd": 0,
    },
}


def setup_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, creds: dict[str, str]) -> Path:
    """Point all config/credential paths at tmp_path and seed credentials."""
    config_dir = tmp_path / ".cited"
    config_file = config_dir / "config.toml"
    creds_file = config_dir / "credentials.json"
    for mod in ("cited_core.config.constants", "cited_core.config.manager"):
        monkeypatch.setattr(f"{mod}.CONFIG_DIR", config_dir)
        monkeypatch.setattr(f"{mod}.CONFIG_FILE", config_file)
    monkeypatch.setattr("cited_core.config.constants.CREDENTIALS_FILE", creds_file)
    monkeypatch.setattr("cited_core.auth.store.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.auth.store.CREDENTIALS_FILE", creds_file)
    monkeypatch.setattr("cited_core.auth.store.TokenStore._has_keyring", lambda self: False)
    monkeypatch.delenv("CITED_AGENT_API_KEY", raising=False)
    config_dir.mkdir(parents=True, exist_ok=True)
    creds_file.write_text(json.dumps(creds))
    return creds_file


@pytest.fixture
def logged_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return setup_config(tmp_path, monkeypatch, {"dev": "test-jwt-dev-token"})


@pytest.fixture
def logged_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return setup_config(tmp_path, monkeypatch, {})


def _invoke(runner: Any, app: Any, *args: str, **kwargs: Any) -> Any:
    return runner.invoke(app, ["--env", "dev", *args], **kwargs)


@respx.mock
def test_prices_works_without_login(runner, cli_app, logged_out):
    route = respx.get(f"{DEV_API}/billing/prices").mock(
        return_value=httpx.Response(200, json=PRICES)
    )
    result = _invoke(runner, cli_app, "--json", "credits", "prices")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["packs"][1]["credits"] == 55
    request = route.calls.last.request
    assert "advgeo_session" not in request.headers.get("cookie", "")
    assert "X-Agent-API-Key" not in request.headers


@respx.mock
def test_prices_human_output(runner, cli_app, logged_out):
    respx.get(f"{DEV_API}/billing/prices").mock(return_value=httpx.Response(200, json=PRICES))
    result = _invoke(runner, cli_app, "credits", "prices")
    assert result.exit_code == 0, result.output
    assert "pack_100" in result.output
    assert "10 credits" in result.output


@respx.mock
def test_balance(runner, cli_app, logged_in):
    respx.get(f"{DEV_API}/billing/credits").mock(return_value=httpx.Response(200, json=CREDITS))
    result = _invoke(runner, cli_app, "credits", "balance")
    assert result.exit_code == 0, result.output
    assert "25 credits" in result.output
    assert "4242" in result.output


def test_balance_requires_auth(runner, cli_app, logged_out):
    result = _invoke(runner, cli_app, "credits", "balance")
    assert result.exit_code == 2
    assert "Not logged in" in result.output


@respx.mock
def test_history_passes_limit(runner, cli_app, logged_in):
    route = respx.get(f"{DEV_API}/billing/credits/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "transactions": [
                    {
                        "id": "t1",
                        "delta": -10,
                        "kind": "spend",
                        "reference_type": "audit",
                        "reference_id": "a1",
                        "note": "Audit",
                        "created_at": "2026-10-02T00:00:00Z",
                        "lot_id": "lot1",
                    }
                ]
            },
        )
    )
    result = _invoke(runner, cli_app, "credits", "history", "--limit", "5")
    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params["limit"] == "5"
    assert "spend" in result.output


@respx.mock
def test_buy_prints_checkout_url_and_sends_save_card(runner, cli_app, logged_in):
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "checkout_url": "https://checkout.stripe.com/c/pay/cs_1",
                "session_id": "cs_1",
                "pack": PRICES["packs"][0],
            },
        )

    respx.post(f"{DEV_API}/billing/credits/checkout").mock(side_effect=_capture)
    result = _invoke(runner, cli_app, "credits", "buy", "pack_20", "--no-save-card")
    assert result.exit_code == 0, result.output
    assert captured == {"pack_id": "pack_20", "save_card": False}
    assert "https://checkout.stripe.com/c/pay/cs_1" in result.output
    assert "Nothing has been charged" in result.output


@respx.mock
def test_buy_defaults_to_saving_card(runner, cli_app, logged_in):
    route = respx.post(f"{DEV_API}/billing/credits/checkout").mock(
        return_value=httpx.Response(200, json={"checkout_url": "https://x", "session_id": "s"})
    )
    result = _invoke(runner, cli_app, "--json", "credits", "buy", "pack_50")
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == {
        "pack_id": "pack_50",
        "save_card": True,
    }
    assert json.loads(result.output)["checkout_url"] == "https://x"


@respx.mock
def test_buy_claim_required_shows_claim_url(runner, cli_app, logged_in):
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
    result = _invoke(runner, cli_app, "credits", "buy", "pack_20")
    assert result.exit_code == 2
    assert "Claim this account to buy packs." in result.output
    assert "https://youcited.com/claim/tok" in result.output


@respx.mock
def test_buy_audit(runner, cli_app, logged_in):
    route = respx.post(f"{DEV_API}/billing/audit-checkout").mock(
        return_value=httpx.Response(
            200,
            json={
                "checkout_url": "https://checkout.stripe.com/c/pay/cs_2",
                "session_id": "cs_2",
                "price_usd": 15,
                "credits": 10,
                "expires_at": "2026-10-17T00:00:00Z",
            },
        )
    )
    result = _invoke(runner, cli_app, "credits", "buy-audit")
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == {}
    assert "https://checkout.stripe.com/c/pay/cs_2" in result.output


@respx.mock
def test_refund_with_yes_skips_confirmation(runner, cli_app, logged_in):
    route = respx.post(f"{DEV_API}/billing/credits/refund").mock(
        return_value=httpx.Response(
            200, json={"refunded_usd": 15.0, "credits_removed": 15, "lots": ["lot1"]}
        )
    )
    result = _invoke(runner, cli_app, "--json", "credits", "refund", "--yes")
    assert result.exit_code == 0, result.output
    assert route.called
    assert json.loads(result.output)["refunded_usd"] == 15.0


@respx.mock
def test_redeem_voucher(runner, cli_app, logged_in):
    route = respx.post(f"{DEV_API}/billing/credits/redeem").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "LAUNCH20",
                "name": "Launch",
                "credits_added": 20,
                "expires_at": "2027-10-18T21:00:00+00:00",
                "balance": 45,
            },
        )
    )
    result = _invoke(runner, cli_app, "credits", "redeem", "launch20")
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == {"code": "launch20"}
    assert "LAUNCH20" in result.output
    assert "45 credits" in result.output


@respx.mock
def test_redeem_unknown_voucher_is_not_found(runner, cli_app, logged_in):
    respx.post(f"{DEV_API}/billing/credits/redeem").mock(
        return_value=httpx.Response(
            404,
            json={
                "detail": {
                    "error": "voucher_not_found",
                    "message": "That voucher code isn't valid.",
                }
            },
        )
    )
    result = _invoke(runner, cli_app, "--json", "credits", "redeem", "NOPE")
    assert result.exit_code == 3
    assert "voucher" in result.output.lower()


@respx.mock
def test_refund_non_interactive_without_yes_refuses(runner, cli_app, logged_in, monkeypatch):
    monkeypatch.setattr("cited_cli.utils.interactive.is_interactive", lambda: False)
    route = respx.post(f"{DEV_API}/billing/credits/refund").mock(
        return_value=httpx.Response(200, json={})
    )
    result = _invoke(runner, cli_app, "--json", "credits", "refund")
    assert result.exit_code == 4
    assert "--yes" in result.output
    assert not route.called


@respx.mock
def test_refund_interactive_confirm(runner, cli_app, logged_in, monkeypatch):
    monkeypatch.setattr("cited_cli.utils.interactive.is_interactive", lambda: True)
    respx.get(f"{DEV_API}/billing/credits").mock(return_value=httpx.Response(200, json=CREDITS))
    route = respx.post(f"{DEV_API}/billing/credits/refund").mock(
        return_value=httpx.Response(
            200, json={"refunded_usd": 15.0, "credits_removed": 15, "lots": ["lot1"]}
        )
    )
    result = _invoke(runner, cli_app, "credits", "refund", input="y\n")
    assert result.exit_code == 0, result.output
    assert "$15.00" in result.output
    assert route.called


@respx.mock
def test_refund_interactive_declined(runner, cli_app, logged_in, monkeypatch):
    monkeypatch.setattr("cited_cli.utils.interactive.is_interactive", lambda: True)
    respx.get(f"{DEV_API}/billing/credits").mock(return_value=httpx.Response(200, json=CREDITS))
    route = respx.post(f"{DEV_API}/billing/credits/refund").mock(
        return_value=httpx.Response(200, json={})
    )
    result = _invoke(runner, cli_app, "credits", "refund", input="n\n")
    assert result.exit_code != 0
    assert not route.called


@respx.mock
def test_refund_nothing_to_refund(runner, cli_app, logged_in):
    respx.post(f"{DEV_API}/billing/credits/refund").mock(
        return_value=httpx.Response(
            400,
            json={"detail": {"error": "nothing_to_refund", "message": "Nothing to refund."}},
        )
    )
    result = _invoke(runner, cli_app, "--json", "credits", "refund", "--yes")
    assert result.exit_code == 1
    assert '"error_code": "nothing_to_refund"' in result.output


@respx.mock
def test_auto_refill_on(runner, cli_app, logged_in):
    route = respx.put(f"{DEV_API}/billing/credits/auto-refill").mock(
        return_value=httpx.Response(200, json=CREDITS)
    )
    result = _invoke(
        runner, cli_app, "credits", "auto-refill", "--on", "--pack", "pack_50", "--cap", "100"
    )
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == {
        "enabled": True,
        "pack_id": "pack_50",
        "monthly_cap_usd": 100.0,
    }


@respx.mock
def test_auto_refill_off(runner, cli_app, logged_in):
    route = respx.put(f"{DEV_API}/billing/credits/auto-refill").mock(
        return_value=httpx.Response(200, json=CREDITS)
    )
    result = _invoke(runner, cli_app, "--json", "credits", "auto-refill", "--off")
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == {"enabled": False}


@respx.mock
def test_audit_quote(runner, cli_app, logged_in):
    route = respx.post(f"{DEV_API}/billing/audit-quote").mock(
        return_value=httpx.Response(
            200,
            json={
                "credits": 12,
                "balance": 5,
                "enough": False,
                "question_count": 5,
                "extra_models": ["openai:gpt-5.2"],
            },
        )
    )
    result = _invoke(
        runner, cli_app, "audit", "quote", "tmpl-1", "--model", "openai:gpt-5.2"
    )
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == {
        "named_audit_id": "tmpl-1",
        "models": ["openai:gpt-5.2"],
    }
    assert "12 credits" in result.output
    assert "cited credits buy-audit" in result.output


@respx.mock
def test_audit_start_insufficient_credits_402(runner, cli_app, logged_in):
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
    result = _invoke(runner, cli_app, "audit", "start", "tmpl-1")
    assert result.exit_code == 6
    assert "This audit needs 10 credits; you have 2." in result.output
    assert BUY_URL in result.output
    assert "cited credits buy" in result.output


@respx.mock
def test_audit_start_402_json_mode(runner, cli_app, logged_in):
    respx.post(f"{DEV_API}/audit/start").mock(
        return_value=httpx.Response(
            402,
            json={
                "detail": {
                    "error": "insufficient_credits",
                    "message": "Not enough credits.",
                    "credits_needed": 10,
                    "balance": 2,
                    "buy_url": BUY_URL,
                }
            },
        )
    )
    result = _invoke(runner, cli_app, "--json", "audit", "start", "tmpl-1")
    assert result.exit_code == 6
    err = json.loads(result.output.strip().splitlines()[-1])
    assert err["error_code"] == "insufficient_credits"
    assert err["credits_needed"] == 10
    assert err["balance"] == 2
    assert err["buy_url"] == BUY_URL
