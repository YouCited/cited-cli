from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from cited_core.api.client import CitedClient
from cited_mcp.context import CitedContext

DEV_API = "https://dev.youcited.com"


@pytest.fixture
def _mcp_available():
    try:
        import mcp  # noqa: F401
    except ImportError:
        pytest.skip("mcp not installed")


def _make_cited_ctx(token: str | None = "test-token") -> CitedContext:
    client = CitedClient(base_url=DEV_API, token=token)
    return CitedContext(client=client, env="dev", api_url=DEV_API)


def _make_mcp_ctx(cited_ctx: CitedContext) -> Any:
    """Create a mock MCP Context that returns the CitedContext from lifespan."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = cited_ctx
    return ctx


def _run(coro: Any) -> Any:
    return asyncio.get_event_loop().run_until_complete(coro)


# --- Auth check ---


@pytest.mark.usefixtures("_mcp_available")
def test_auth_check_no_token():
    from cited_mcp.tools.auth import check_auth_status

    cited_ctx = _make_cited_ctx(token=None)
    ctx = _make_mcp_ctx(cited_ctx)
    result = _run(check_auth_status(ctx))
    assert result["error"] is True
    assert "Not authenticated" in result["message"]
    cited_ctx.client.close()


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_check_auth_status_success():
    from cited_mcp.tools.auth import check_auth_status

    respx.get(f"{DEV_API}/auth/me").mock(
        return_value=httpx.Response(200, json={"email": "test@example.com", "id": "u1"})
    )
    cited_ctx = _make_cited_ctx()
    ctx = _make_mcp_ctx(cited_ctx)
    result = _run(check_auth_status(ctx))
    assert result["email"] == "test@example.com"
    cited_ctx.client.close()


# --- Business tools ---


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_list_businesses():
    from cited_mcp.tools.business import list_businesses

    respx.get(f"{DEV_API}/businesses").mock(
        return_value=httpx.Response(200, json=[{"id": "b1", "name": "Acme"}])
    )
    cited_ctx = _make_cited_ctx()
    ctx = _make_mcp_ctx(cited_ctx)
    result = _run(list_businesses(ctx))
    assert isinstance(result, list)
    assert result[0]["id"] == "b1"
    cited_ctx.client.close()


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_create_business():
    from cited_mcp.tools.business import create_business

    respx.post(f"{DEV_API}/businesses").mock(
        return_value=httpx.Response(201, json={"id": "b2", "name": "NewCo"})
    )
    cited_ctx = _make_cited_ctx()
    ctx = _make_mcp_ctx(cited_ctx)
    result = _run(create_business(ctx, "NewCo", "https://newco.com", "A new company for testing", "technology"))
    assert result["id"] == "b2"
    cited_ctx.client.close()


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_crawl_business():
    from cited_mcp.tools.business import crawl_business

    respx.post(f"{DEV_API}/businesses/b1/crawl").mock(
        return_value=httpx.Response(202, json={"job_id": "j1", "status": "crawling"})
    )
    cited_ctx = _make_cited_ctx()
    ctx = _make_mcp_ctx(cited_ctx)
    result = _run(crawl_business(ctx, "b1"))
    assert result["job_id"] == "j1"
    cited_ctx.client.close()


# --- API error handling ---


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_api_error_returns_structured_error():
    from cited_mcp.tools.business import get_business

    respx.get(f"{DEV_API}/businesses/bad-id").mock(
        return_value=httpx.Response(404, json={"detail": "Not found"})
    )
    cited_ctx = _make_cited_ctx()
    ctx = _make_mcp_ctx(cited_ctx)
    result = _run(get_business(ctx, "bad-id"))
    assert result["error"] is True
    assert result["status_code"] == 404
    cited_ctx.client.close()


# --- Audit tools ---


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_start_audit():
    from cited_mcp.tools.audit import start_audit

    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(202, json={"job_id": "aj1", "status": "running"})

    respx.post(f"{DEV_API}/audit/start").mock(side_effect=_capture)
    cited_ctx = _make_cited_ctx()
    ctx = _make_mcp_ctx(cited_ctx)
    result = _run(start_audit(ctx, "template-1", "b1"))
    assert result["job_id"] == "aj1"
    assert captured["named_audit_id"] == "template-1"
    assert captured["business_id"] == "b1"
    cited_ctx.client.close()


# --- Recommendation insights ---


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_get_recommendation_insights():
    from cited_mcp.tools.recommend import get_recommendation_insights

    respx.get(f"{DEV_API}/recommendations/rj1/result").mock(
        return_value=httpx.Response(200, json={
            "question_insights": [
                {"question_id": "q1", "question_text": "Q?", "risk_level": "high", "coverage_score": 0.3}
            ],
            "head_to_head_comparisons": [
                {"competitor_domain": "comp.com", "overall_winner": "business"}
            ],
            "strengthening_tips": [
                {"category": "llms_txt", "title": "Create llms.txt", "priority": "high"}
            ],
            "priority_actions": [],
        })
    )
    cited_ctx = _make_cited_ctx()
    ctx = _make_mcp_ctx(cited_ctx)
    result = _run(get_recommendation_insights(ctx, "rj1"))
    assert result["question_insights"][0]["source_type"] == "question_insight"
    assert result["question_insights"][0]["source_id"] == "q1"
    assert result["head_to_head_comparisons"][0]["source_type"] == "head_to_head"
    assert result["head_to_head_comparisons"][0]["source_id"] == "comp.com"
    assert result["strengthening_tips"][0]["source_type"] == "strengthening_tip"
    assert result["strengthening_tips"][0]["source_id"] == "llms_txt"
    cited_ctx.client.close()


# --- Solution tools ---


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_start_solution():
    from cited_mcp.tools.solution import start_solution

    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(202, json={"job_id": "sj1", "status": "running"})

    respx.post(f"{DEV_API}/solutions/request").mock(side_effect=_capture)
    cited_ctx = _make_cited_ctx()
    ctx = _make_mcp_ctx(cited_ctx)
    result = _run(start_solution(ctx, "rj1", "question_insight", "q1"))
    assert result["job_id"] == "sj1"
    assert captured["recommendation_job_id"] == "rj1"
    assert captured["source_type"] == "question_insight"
    assert captured["source_id"] == "q1"
    cited_ctx.client.close()


# --- Job status ---


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_get_job_status_with_type():
    from cited_mcp.tools.job import get_job_status

    respx.get(f"{DEV_API}/audit/aj1/status").mock(
        return_value=httpx.Response(200, json={"job_id": "aj1", "status": "completed"})
    )
    cited_ctx = _make_cited_ctx()
    ctx = _make_mcp_ctx(cited_ctx)
    result = _run(get_job_status(ctx, "aj1", "audit"))
    assert result["status"] == "completed"
    assert result["job_type"] == "audit"
    cited_ctx.client.close()


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_get_job_status_probes():
    from cited_mcp.tools.job import get_job_status

    respx.get(f"{DEV_API}/audit/j1/status").mock(
        return_value=httpx.Response(404, json={"detail": "Not found"})
    )
    respx.get(f"{DEV_API}/recommendations/j1/status").mock(
        return_value=httpx.Response(200, json={"job_id": "j1", "status": "completed"})
    )
    cited_ctx = _make_cited_ctx()
    ctx = _make_mcp_ctx(cited_ctx)
    result = _run(get_job_status(ctx, "j1"))
    assert result["job_type"] == "recommendation"
    assert result["status"] == "completed"
    cited_ctx.client.close()
