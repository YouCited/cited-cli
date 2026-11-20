"""Live tests run against prod (api.youcited.com) and never spend credits.

    pytest tests/live --live                     # no login needed
    CITED_SMOKE_AGENT_KEY=cak_... pytest tests/live --live   # adds the logged-in checks

They use a fresh config and credentials file under tmp_path, never the
keychain, and tag their User-Agent with "cited-ci".
"""

from __future__ import annotations

import json
import os

import pytest


@pytest.fixture(autouse=True)
def _fresh_home(tmp_path, monkeypatch):
    config_dir = tmp_path / ".cited"
    monkeypatch.setattr("cited_core.config.manager.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.config.manager.CONFIG_FILE", config_dir / "config.toml")
    monkeypatch.setattr("cited_core.auth.store.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.auth.store.CREDENTIALS_FILE", config_dir / "credentials.json")
    monkeypatch.setattr("cited_core.auth.store.TokenStore._has_keyring", lambda self: False)
    monkeypatch.delenv("CITED_TOKEN", raising=False)
    monkeypatch.delenv("CITED_AGENT_API_KEY", raising=False)
    monkeypatch.setenv("CITED_USER_AGENT_TAG", "cited-ci")

@pytest.fixture
def agent_key(monkeypatch) -> str:
    """The test account's agent key, sent like a user's own key."""
    key = os.environ.get("CITED_SMOKE_AGENT_KEY")
    if not key:
        pytest.skip("CITED_SMOKE_AGENT_KEY is not set")
    monkeypatch.setenv("CITED_AGENT_API_KEY", key)
    return key


SMOKE_SITE = "youcited.com"


@pytest.fixture
def smoke_business(runner, cli_app, agent_key) -> str:
    """The test account's youcited.com business. The account can hold others,
    so the tests name this one instead of relying on "your only business"."""
    result = runner.invoke(cli_app, ["--env", "prod", "--json", "business", "get"])
    assert result.exit_code == 0, result.output
    businesses = json.loads(result.stdout).get("businesses") or []
    for business in businesses:
        if SMOKE_SITE in (business.get("website") or ""):
            return str(business["id"])
    pytest.fail(f"The test account has no {SMOKE_SITE} business: {businesses}")
