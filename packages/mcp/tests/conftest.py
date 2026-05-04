"""Pytest fixtures shared across the cited-mcp test suite.

The most important thing this module does: prevent the MCP ``login`` tool
function from opening a real browser tab and binding a real localhost port
when its tests execute.

Background — without these autouse mocks, ``test_login_returns_url_immediately``
runs ``cited_mcp.tools.auth.login()`` in full: ``OAuthCallbackServer.start()``
binds an ephemeral 127.0.0.1 port on the test runner's machine, then
``webbrowser.open(login_url)`` opens the runner's default browser to the
cited authorize-app endpoint. The browser session is typically already
authed against cited, so the backend immediately redirects to
``http://localhost:<port>/callback?token=<USER_JWT>`` with a freshly minted
JWT. The test asserts the result and tears the server down — leaving an
orphaned browser tab pointing at a dead port. Running the suite repeatedly
during CI/dev iteration was producing exactly this symptom on the
maintainer's laptop (multiple Firefox "can't connect to localhost" tabs
correlated 1:1 with pytest invocations).

The autouse fixtures below stop both side effects so the suite is safe
to run anywhere a logged-in browser session might exist.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def no_real_browser_open() -> Iterator[MagicMock]:
    """Stop ``webbrowser.open`` from spawning real browser tabs in tests.

    Patches the import bound inside ``cited_mcp.tools.auth`` so that
    ``login()`` records the call but never reaches the OS shell.
    """
    with patch("cited_mcp.tools.auth.webbrowser.open") as fake:
        fake.return_value = True
        yield fake


@pytest.fixture(autouse=True)
def no_real_oauth_callback_server() -> Iterator[MagicMock]:
    """Stop ``OAuthCallbackServer`` from binding ephemeral localhost ports.

    The ``login`` tool instantiates ``OAuthCallbackServer(timeout=300)`` and
    calls ``.start()`` to bind a real socket. Tests don't need a real
    server — they only need an object with ``redirect_uri``, ``token``,
    ``start()``, and ``shutdown()`` attributes that look right.

    Tests that explicitly construct an ``OAuthCallbackServer`` themselves
    (e.g. ``test_login_second_call_detects_token``) get the mocked class.
    The mock auto-assigns a ``redirect_uri`` so URL-shape assertions in
    ``test_login_returns_url_immediately`` still hold.
    """
    instance_counter = {"n": 0}

    def fake_init(self: object, timeout: float = 120.0) -> None:
        instance_counter["n"] += 1
        # Synthetic deterministic port so URL assertions pass without
        # actually binding anything. 50000 + N keeps it well above the
        # privileged-port range and away from common dev-server defaults.
        port = 50000 + instance_counter["n"]
        # type: ignore[attr-defined]
        self.token = None  # type: ignore[attr-defined]
        self.port = port  # type: ignore[attr-defined]
        self.redirect_uri = f"http://localhost:{port}/callback"  # type: ignore[attr-defined]

    def fake_start(self: object) -> None:
        return None

    def fake_wait(self: object) -> str | None:
        return getattr(self, "token", None)

    def fake_shutdown(self: object) -> None:
        return None

    with (
        patch(
            "cited_core.auth.oauth_server.OAuthCallbackServer.__init__",
            fake_init,
        ),
        patch(
            "cited_core.auth.oauth_server.OAuthCallbackServer.start",
            fake_start,
        ),
        patch(
            "cited_core.auth.oauth_server.OAuthCallbackServer.wait_for_token",
            fake_wait,
        ),
        patch(
            "cited_core.auth.oauth_server.OAuthCallbackServer.shutdown",
            fake_shutdown,
        ),
    ):
        yield MagicMock()
