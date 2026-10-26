"""cited-mcp: tool surface, docs counts and the login flow."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import respx

from cited_core.api.client import CitedClient
from cited_core.tools import bundled_manifest, tool_names
from cited_mcp.server import CitedSession, build_session, call, tool_list

_PKG = Path(__file__).resolve().parent.parent
API = "https://dev.youcited.com"


def _session(store) -> CitedSession:
    return CitedSession(
        client=CitedClient(API), env="dev", api_url=API, manifest=bundled_manifest(), store=store
    )


def test_tool_surface_is_the_manifest_plus_login_and_logout(store):
    names = [t.name for t in tool_list(_session(store))]
    assert names == [*tool_names(), "login", "logout"]


def test_docs_name_the_live_tool_count(store):
    """README and SKILL.md must not advertise a stale tool count."""
    live = len(tool_list(_session(store)))
    for doc in ("README.md", "SKILL.md"):
        counts = {int(n) for n in re.findall(r"\b(\d{1,3}) tools\b", (_PKG / doc).read_text())}
        assert counts <= {live}, f"{doc} mentions {counts} tools; the server has {live}"


@respx.mock
def test_build_session_falls_back_to_the_bundled_manifest(store, monkeypatch):
    monkeypatch.setenv("CITED_ENV", "dev")
    monkeypatch.delenv("CITED_TOKEN", raising=False)
    monkeypatch.delenv("CITED_AGENT_API_KEY", raising=False)
    respx.get(f"{API}/agent/tools").mock(return_value=httpx.Response(503))
    session = build_session()
    try:
        assert tool_names(session.manifest) == tool_names()
        assert session.env == "dev"
    finally:
        session.client.close()


def test_login_with_force_drops_the_old_session(store):
    session = _session(store)
    store.save_token("dev", "old")
    session.client.set_token("old")
    result = call(session, "login", {"force": True}).structured_content
    assert result["action_required"] is True
    assert store.get_token("dev") is None
    assert session.client.token is None
