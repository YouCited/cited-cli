from __future__ import annotations

import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

import pytest

from cited_core.auth.oauth_server import OAuthCallbackServer


def _hit(server: OAuthCallbackServer, **params: str) -> int:
    url = f"{server.redirect_uri}?{urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as e:
        return e.code


@pytest.fixture
def server():
    s = OAuthCallbackServer(timeout=30)
    s.start()
    yield s
    s.shutdown()


def test_authorize_params_carry_callback_and_state(server):
    params = server.authorize_params()
    assert params == {"callback": server.redirect_uri, "state": server.state}
    assert len(server.state) >= 32


def test_token_without_our_state_is_ignored(server):
    assert _hit(server, token="planted") == 400
    assert _hit(server, token="planted", state="guess") == 400
    assert server.token is None


def test_token_with_our_state_is_accepted_once(server):
    assert _hit(server, token="real", state=server.state) == 200
    assert _hit(server, token="second", state=server.state) == 400
    assert server.wait_for_token() == "real"


def test_listener_stops_after_its_timeout():
    s = OAuthCallbackServer(timeout=0.2)
    s.start()
    deadline = time.monotonic() + 5
    while not s.expired and time.monotonic() < deadline:
        time.sleep(0.05)
    assert s.expired
    with pytest.raises(OSError):
        urllib.request.urlopen(s.redirect_uri, timeout=2)  # noqa: S310
    s.shutdown()
