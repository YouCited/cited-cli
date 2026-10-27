"""A keychain that refuses access falls back to the credentials file."""

from __future__ import annotations

import json

import httpx
import keyring
import pytest
import respx
from keyring.backend import KeyringBackend
from keyring.errors import KeyringLocked

from cited_core.auth.store import TokenStore

API = "https://dev.youcited.com"


class DeniedKeychain(KeyringBackend):
    """Like macOS after "Deny" on the keychain prompt (-128)."""

    priority = 1  # type: ignore[assignment]

    def get_password(self, service, username):
        raise KeyringLocked("Can't get password from keychain: (-128, 'Keychain Access Denied')")

    def set_password(self, service, username, password):
        raise KeyringLocked("Can't store password on keychain: (-128, 'Keychain Access Denied')")

    def delete_password(self, service, username):
        raise KeyringLocked("Can't delete password in keychain: (-128, 'Keychain Access Denied')")


@pytest.fixture
def denied(tmp_path, monkeypatch):
    config_dir = tmp_path / ".cited"
    monkeypatch.setattr("cited_core.auth.store.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.auth.store.CREDENTIALS_FILE", config_dir / "credentials.json")
    monkeypatch.delenv("CITED_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("CITED_TOKEN", raising=False)
    previous = keyring.get_keyring()
    keyring.set_keyring(DeniedKeychain())
    yield
    keyring.set_keyring(previous)


def test_denied_keychain_reads_as_no_login(denied):
    assert TokenStore().get_token("prod") is None
    assert TokenStore().get_agent_key("prod") is None


def test_denied_keychain_saves_and_deletes_in_the_file(denied):
    store = TokenStore()
    store.save_token("prod", "tok")
    store.save_agent_key("prod", "cak_x")
    assert TokenStore().get_token("prod") == "tok"
    assert TokenStore().get_agent_key("prod") == "cak_x"
    store = TokenStore()
    store.delete_token("prod")
    store.delete_agent_key("prod")
    assert TokenStore().get_token("prod") is None
    assert TokenStore().get_agent_key("prod") is None


@respx.mock
def test_free_audit_never_reads_the_keychain(runner, cli_app, denied, monkeypatch):
    monkeypatch.setenv("CITED_AGENT_API_KEY", "cak_env")
    seen = []

    def _free(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return httpx.Response(200, json={"status": "pending", "report_token": "tok"})

    monkeypatch.setattr(DeniedKeychain, "get_password", lambda *a: pytest.fail("keychain read"))
    respx.post(f"{API}/agent/tools/free_audit").mock(side_effect=_free)
    result = runner.invoke(
        cli_app, ["--env", "dev", "--json", "audit", "free", "acme.com", "--no-wait"]
    )
    assert result.exit_code == 0, result.output
    assert "x-agent-api-key" not in seen[0]
    assert "cookie" not in seen[0]


@respx.mock
def test_status_runs_when_the_keychain_is_denied(runner, cli_app, denied):
    sent = []

    def _status(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content or b"{}"))
        return httpx.Response(200, json={"logged_in": False})

    respx.post(f"{API}/agent/tools/account_status").mock(side_effect=_status)
    result = runner.invoke(cli_app, ["--env", "dev", "--json", "status"])
    assert result.exit_code == 0, result.output
    assert sent == [{}]
