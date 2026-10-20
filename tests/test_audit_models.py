"""Tests for per-model audit comparison: `audit start --model`, `audit models`, MCP tool."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
import respx

from cited_cli.app import app
from tests.test_mcp_tools import _make_cited_ctx, _make_mcp_ctx, _mcp_available  # noqa: F401
from tests.test_pipeline import DEV_API, _setup_logged_in

JOB_ID = "aj-models-1"

MOCK_CATALOG = {
    "models": [
        {"id": "anthropic:claude-opus-5-5", "provider": "anthropic", "model": "claude-opus-5-5"},
        {"id": "openai:gpt-5.2", "provider": "openai", "model": "gpt-5.2"},
    ],
    "max_models_per_audit": 6,
}

MOCK_RESULTS = {
    "job_id": JOB_ID,
    "status": "completed",
    "models": [
        {
            "id": "anthropic:claude-opus-5-5",
            "provider": "anthropic",
            "model": "claude-opus-5-5",
            "questions_answered": 2,
            "questions_cited": 2,
            "questions_failed": 0,
            "citation_rate": 1.0,
            "share_of_citations": 0.4,
        },
        {
            "id": "openai:gpt-5.2",
            "provider": "openai",
            "model": "gpt-5.2",
            "questions_answered": 2,
            "questions_cited": 1,
            "questions_failed": 0,
            "citation_rate": 0.5,
            "share_of_citations": 0.2,
        },
    ],
    "by_question": [
        {
            "question": "Best GEO tool?",
            "cited_by_model": {"anthropic:claude-opus-5-5": True, "openai:gpt-5.2": False},
        }
    ],
}


@respx.mock
def test_audit_start_sends_models(runner, tmp_path, monkeypatch):
    _setup_logged_in(tmp_path, monkeypatch)
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(202, json={"job_id": JOB_ID, "status": "pending"})

    respx.post(f"{DEV_API}/audit/start").mock(side_effect=_capture)
    result = runner.invoke(
        app,
        [
            "--env", "dev", "--json", "audit", "start", "tpl-1",
            "--model", "anthropic:claude-opus-5-5", "-m", "openai:gpt-5.2",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["models"] == ["anthropic:claude-opus-5-5", "openai:gpt-5.2"]
    assert "providers" not in captured


@respx.mock
def test_audit_models_lists_catalog(runner, tmp_path, monkeypatch):
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/audit/models").mock(return_value=httpx.Response(200, json=MOCK_CATALOG))
    result = runner.invoke(app, ["--env", "dev", "audit", "models"])
    assert result.exit_code == 0, result.output
    assert "anthropic:claude-opus-5-5" in result.output
    assert "up to 6" in result.output


@respx.mock
def test_audit_models_for_job_json(runner, tmp_path, monkeypatch):
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/audit/{JOB_ID}/models").mock(
        return_value=httpx.Response(200, json=MOCK_RESULTS)
    )
    result = runner.invoke(app, ["--env", "dev", "--json", "audit", "models", JOB_ID])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert [m["id"] for m in data["models"]] == ["anthropic:claude-opus-5-5", "openai:gpt-5.2"]


@respx.mock
def test_audit_models_for_job_human(runner, tmp_path, monkeypatch):
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/audit/{JOB_ID}/models").mock(
        return_value=httpx.Response(200, json=MOCK_RESULTS)
    )
    result = runner.invoke(app, ["--env", "dev", "--text", "audit", "models", JOB_ID])
    assert result.exit_code == 0, result.output
    assert "Citations by model" in result.output
    assert "100%" in result.output
    assert "50%" in result.output


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_mcp_get_audit_models():
    from cited_mcp.tools.audit import get_audit_models

    respx.get(f"{DEV_API}/audit/models").mock(return_value=httpx.Response(200, json=MOCK_CATALOG))
    respx.get(f"{DEV_API}/audit/{JOB_ID}/models").mock(
        return_value=httpx.Response(200, json=MOCK_RESULTS)
    )
    cited_ctx = _make_cited_ctx()
    ctx = _make_mcp_ctx(cited_ctx)
    catalog = asyncio.run(get_audit_models(ctx))
    assert catalog["max_models_per_audit"] == 6
    results = asyncio.run(get_audit_models(ctx, JOB_ID))
    assert results["models"][0]["id"] == "anthropic:claude-opus-5-5"
    cited_ctx.client.close()


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_mcp_start_audit_with_models():
    from cited_mcp.tools.audit import start_audit

    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(202, json={"job_id": JOB_ID, "status": "pending"})

    respx.post(f"{DEV_API}/audit/start").mock(side_effect=_capture)
    cited_ctx = _make_cited_ctx()
    ctx = _make_mcp_ctx(cited_ctx)
    asyncio.run(
        start_audit(ctx, "tpl-1", models=["anthropic:claude-sonnet-5-5"], confirm=True)
    )
    assert captured["models"] == ["anthropic:claude-sonnet-5-5"]
    cited_ctx.client.close()
