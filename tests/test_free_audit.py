from __future__ import annotations

import json

import httpx
import pytest
import respx

from tests.test_mcp_tools import _make_cited_ctx, _make_mcp_ctx, _mcp_available, _run  # noqa: F401

DEV_API = "https://dev.youcited.com"
TOKEN = "instant_a1b2c3d4_0123456789abcdef"

STARTED = {
    "domain": "acme-plumbing.com",
    "job_id": "a1b2c3d4e5",
    "status": "pending",
    "report_url": f"{DEV_API}/free-audit/report/{TOKEN}",
    "share_url": f"https://youcited.com/share/{TOKEN}",
    "poll_after_seconds": 30,
}
PROCESSING = {"status": "processing", "progress": 40, "poll_after_seconds": 30}
COMPLETED = {
    "status": "completed",
    "domain": "acme-plumbing.com",
    "providers_used": ["perplexity"],
    "summary": {
        "questions_checked": 2,
        "questions_where_brand_cited": 1,
        "high_risk_questions": 1,
        "share_of_voice": 35.0,
    },
    "questions": [
        {
            "question": "Best plumber in Austin?",
            "risk_level": "high",
            "brand_cited": False,
            "cited_domains": ["yelp.com", "angi.com"],
        }
    ],
    "share_url": f"https://youcited.com/share/{TOKEN}",
}


def _isolate_config(tmp_path, monkeypatch) -> None:
    """Point config and credentials at an empty temp dir: no login exists."""
    config_dir = tmp_path / ".cited"
    monkeypatch.setattr("cited_core.config.constants.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.config.constants.CONFIG_FILE", config_dir / "config.toml")
    monkeypatch.setattr(
        "cited_core.config.constants.CREDENTIALS_FILE", config_dir / "credentials.json"
    )
    monkeypatch.setattr("cited_core.auth.store.CONFIG_DIR", config_dir)
    monkeypatch.setattr(
        "cited_core.auth.store.CREDENTIALS_FILE", config_dir / "credentials.json"
    )
    monkeypatch.setattr("cited_core.auth.store.TokenStore._has_keyring", lambda self: False)
    monkeypatch.setattr("cited_cli.commands.audit.time.sleep", lambda s: None)


@respx.mock
def test_cli_audit_free_waits_for_report_without_login(runner, cli_app, tmp_path, monkeypatch):
    _isolate_config(tmp_path, monkeypatch)
    start = respx.get(f"{DEV_API}/free-audit").mock(
        return_value=httpx.Response(202, json=STARTED)
    )
    respx.get(f"{DEV_API}/free-audit/report/{TOKEN}").mock(
        side_effect=[
            httpx.Response(200, json=PROCESSING),
            httpx.Response(200, json=COMPLETED),
        ]
    )

    result = runner.invoke(
        cli_app, ["--env", "dev", "--json", "audit", "free", "acme-plumbing.com"]
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "completed"
    assert data["summary"]["questions_where_brand_cited"] == 1
    assert start.calls.last.request.url.params["url"] == "acme-plumbing.com"
    assert "cookie" not in start.calls.last.request.headers


@respx.mock
def test_cli_audit_free_no_wait_returns_progress(runner, cli_app, tmp_path, monkeypatch):
    _isolate_config(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/free-audit").mock(return_value=httpx.Response(202, json=STARTED))
    report = respx.get(f"{DEV_API}/free-audit/report/{TOKEN}").mock(
        return_value=httpx.Response(200, json=PROCESSING)
    )

    result = runner.invoke(
        cli_app,
        ["--env", "dev", "--json", "audit", "free", "acme-plumbing.com", "--no-wait"],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "processing"
    assert data["report_url"] == STARTED["report_url"]
    assert report.call_count == 1


@respx.mock
def test_cli_audit_free_rate_limited(runner, cli_app, tmp_path, monkeypatch):
    _isolate_config(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/free-audit").mock(
        return_value=httpx.Response(429, json={"detail": "at today's limit"})
    )

    result = runner.invoke(cli_app, ["--env", "dev", "audit", "free", "acme-plumbing.com"])

    assert result.exit_code == 5


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_mcp_free_audit_works_without_token():
    from cited_mcp.tools.audit import free_audit

    respx.get(f"{DEV_API}/free-audit").mock(return_value=httpx.Response(202, json=STARTED))
    respx.get(f"{DEV_API}/free-audit/report/{TOKEN}").mock(
        return_value=httpx.Response(200, json=PROCESSING)
    )

    ctx = _make_mcp_ctx(_make_cited_ctx(token=None))
    result = _run(free_audit(ctx, url="acme-plumbing.com"))

    assert result["status"] == "processing"
    assert "call free_audit again" in result["hint"].lower()


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_mcp_free_audit_returns_completed_report():
    from cited_mcp.tools.audit import free_audit

    respx.get(f"{DEV_API}/free-audit").mock(
        return_value=httpx.Response(202, json={**STARTED, "status": "completed"})
    )
    respx.get(f"{DEV_API}/free-audit/report/{TOKEN}").mock(
        return_value=httpx.Response(200, json=COMPLETED)
    )

    ctx = _make_mcp_ctx(_make_cited_ctx(token=None))
    result = _run(free_audit(ctx, url="acme-plumbing.com"))

    assert result["status"] == "completed"
    assert result["questions"][0]["cited_domains"] == ["yelp.com", "angi.com"]
    assert "hint" not in result
