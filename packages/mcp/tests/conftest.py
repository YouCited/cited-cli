"""Keep the cited-mcp tests from opening a browser or binding localhost ports.

The ``login`` tool starts an ``OAuthCallbackServer`` and opens the sign-in page.
In tests both are stubbed, so a logged-in browser on the machine running the
suite never gets a stray tab pointing at a dead port.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def no_real_browser_open() -> Iterator[MagicMock]:
    with patch("cited_mcp.server.webbrowser.open") as fake:
        fake.return_value = True
        yield fake


@pytest.fixture(autouse=True)
def no_real_oauth_callback_server() -> Iterator[None]:
    counter = {"n": 0}

    def fake_init(self: object, timeout: float = 120.0) -> None:
        counter["n"] += 1
        port = 50000 + counter["n"]
        self.token = None  # type: ignore[attr-defined]
        self.port = port  # type: ignore[attr-defined]
        self.redirect_uri = f"http://localhost:{port}/callback"  # type: ignore[attr-defined]
        self.state = f"test-state-{port}"  # type: ignore[attr-defined]
        self.expired = False  # type: ignore[attr-defined]

    with (
        patch("cited_core.auth.oauth_server.OAuthCallbackServer.__init__", fake_init),
        patch("cited_core.auth.oauth_server.OAuthCallbackServer.start", lambda self: None),
        patch("cited_core.auth.oauth_server.OAuthCallbackServer.shutdown", lambda self: None),
    ):
        yield


@pytest.fixture
def store(tmp_path, monkeypatch):
    from cited_core.auth.store import TokenStore

    monkeypatch.setattr("cited_core.auth.store.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("cited_core.auth.store.CREDENTIALS_FILE", tmp_path / "credentials.json")
    monkeypatch.setattr("cited_core.auth.store.TokenStore._has_keyring", lambda self: False)
    return TokenStore()
