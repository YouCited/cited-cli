"""Tests for cited-mcp tool functions.

Tests call tool functions directly with a mocked CitedClient,
bypassing the MCP transport layer.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from cited_core.api.client import CitedClient
from cited_core.errors import CitedAPIError
from cited_mcp.context import CitedContext
from cited_mcp.server import create_stdio_server

# ---------------------------------------------------------------------------
# Test helpers (inline to avoid import issues across test roots)
# ---------------------------------------------------------------------------


@dataclass
class FakeRequestContext:
    lifespan_context: CitedContext


@dataclass
class FakeContext:
    """Minimal stand-in for mcp.server.fastmcp.Context."""

    request_context: FakeRequestContext


def make_ctx(
    token: str | None = "test-token",
    env: str = "dev",
    api_url: str = "https://dev.youcited.com",
    default_business_id: str | None = None,
) -> FakeContext:
    """Build a fake MCP context with a mocked CitedClient."""
    client = MagicMock(spec=CitedClient)
    client.token = token
    # Mock the underlying httpx client's cookie jar (used by login to set session cookie)
    client._client = MagicMock()
    cited_ctx = CitedContext(
        client=client,
        env=env,
        api_url=api_url,
        default_business_id=default_business_id,
    )
    return FakeContext(request_context=FakeRequestContext(lifespan_context=cited_ctx))


@pytest.fixture(autouse=True)
def _seed_tier_cache_and_reset_rate_limits():
    """Pre-seed tier cache and reset rate limiter between tests."""
    import time

    from cited_mcp.tools._helpers import _rate_limits, _tier_cache

    # Use "pro" tier for all test users so no tools are gated
    _tier_cache.clear()
    _rate_limits.clear()
    # The cache key is sha256(token)[:16] — pre-seed for "test-token"
    import hashlib
    cache_key = hashlib.sha256(b"test-token").hexdigest()[:16]
    _tier_cache[cache_key] = ("pro", time.monotonic() + 3600)
    yield
    _tier_cache.clear()
    _rate_limits.clear()


@pytest.fixture
def ctx():
    """Authenticated context fixture."""
    return make_ctx()


@pytest.fixture
def unauth_ctx():
    """Unauthenticated context fixture."""
    return make_ctx(token=None)


# Ensure tools are registered before importing them
create_stdio_server()

from cited_mcp.tools.action_plan import (  # noqa: E402
    dismiss_action,
    get_action_plan,
    get_action_progress,
    get_quick_wins,
    mark_action_done,
)
from cited_mcp.tools.agent import (  # noqa: E402
    buyer_fit_query,
    get_business_facts,
)
from cited_mcp.tools.analytics import get_analytics_trends  # noqa: E402
from cited_mcp.tools.audit import (  # noqa: E402
    create_audit_template,
    delete_audit_template,
    export_audit,
    get_audit_question_detail,
    get_audit_result,
    get_audit_status,
    list_audit_templates,
    list_audits,
    start_audit,
    update_audit_template,
)
from cited_mcp.tools.auth import check_auth_status, login, logout, ping  # noqa: E402
from cited_mcp.tools.business import (  # noqa: E402
    crawl_business,
    create_business,
    delete_business,
    get_business,
    get_health_scores,
    get_usage_stats,
    list_businesses,
    update_business,
)
from cited_mcp.tools.hq import get_business_hq  # noqa: E402
from cited_mcp.tools.job import cancel_job, get_job_status  # noqa: E402
from cited_mcp.tools.recommend import (  # noqa: E402
    get_recommendation_insights,
    get_recommendation_result,
    get_recommendation_status,
    list_recommendations,
    start_recommendation,
)
from cited_mcp.tools.solution import (  # noqa: E402
    get_solution_result,
    get_solution_status,
    list_solutions,
    start_solution,
    start_solutions_batch,
)


def run(coro):
    """Helper to run async tool functions synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Auth checks — all tools should reject unauthenticated requests
# ---------------------------------------------------------------------------


class TestAuthGuard:
    """Every tool that requires auth should return an error when no token is set."""

    def test_list_businesses_unauth(self, unauth_ctx):
        result = run(list_businesses(unauth_ctx))
        assert result["error"] is True
        assert "Not authenticated" in result["message"]

    def test_get_business_unauth(self, unauth_ctx):
        result = run(get_business(unauth_ctx, business_id="abc"))
        assert result["error"] is True

    def test_create_business_unauth(self, unauth_ctx):
        result = run(create_business(unauth_ctx, name="x", website="x", description="x"))
        assert result["error"] is True

    def test_start_audit_unauth(self, unauth_ctx):
        result = run(start_audit(unauth_ctx, named_audit_id="abc"))
        assert result["error"] is True

    def test_start_recommendation_unauth(self, unauth_ctx):
        result = run(start_recommendation(unauth_ctx, audit_job_id="abc"))
        assert result["error"] is True

    def test_start_solution_unauth(self, unauth_ctx):
        result = run(start_solution(
            unauth_ctx, recommendation_job_id="a", source_type="b", source_id="c"
        ))
        assert result["error"] is True

    def test_get_job_status_unauth(self, unauth_ctx):
        result = run(get_job_status(unauth_ctx, job_id="abc"))
        assert result["error"] is True


# ---------------------------------------------------------------------------
# Business tools
# ---------------------------------------------------------------------------


class TestBusinessTools:
    def test_list_businesses(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = [{"id": "b1", "name": "Test Biz"}]

        result = run(list_businesses(ctx))
        assert result["data"][0]["id"] == "b1"
        client.get.assert_called_once()

    def test_list_businesses_sets_default_for_single(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = [{"id": "only-one", "name": "Solo"}]

        run(list_businesses(ctx))
        assert ctx.request_context.lifespan_context.default_business_id == "only-one"

    def test_get_business(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"id": "b1", "name": "Biz", "website": "https://example.com"}

        result = run(get_business(ctx, business_id="b1"))
        assert result["name"] == "Biz"

    def test_create_business(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.post.return_value = {"id": "new-id", "name": "New Biz"}

        result = run(create_business(
            ctx,
            name="New Biz",
            website="https://new.com",
            description="A new business for testing purposes that is long enough",
        ))
        assert result["id"] == "new-id"
        client.post.assert_called_once()
        payload = client.post.call_args[1]["json"]
        assert payload["name"] == "New Biz"
        assert payload["industry"] == "technology"

    def test_update_business(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.put.return_value = {"id": "b1", "name": "Updated"}

        result = run(update_business(ctx, business_id="b1", name="Updated"))
        assert result["name"] == "Updated"
        payload = client.put.call_args[1]["json"]
        assert payload == {"name": "Updated"}

    def test_delete_business(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.delete.return_value = None

        result = run(delete_business(ctx, business_id="b1"))
        assert result["success"] is True

    def test_crawl_business(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.post.return_value = {"job_id": "j1", "status": "crawling"}

        result = run(crawl_business(ctx, business_id="b1"))
        assert result["job_id"] == "j1"

    def test_get_health_scores(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"overall": 75}

        result = run(get_health_scores(ctx, business_id="b1"))
        assert result["overall"] == 75

    def test_get_usage_stats(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = [
            {"email": "test@example.com", "plan": "pro"},  # /me
            [{"id": "b1"}],  # /businesses
            [{"id": "a1"}, {"id": "a2"}],  # /audit/history
        ]

        result = run(get_usage_stats(ctx))
        assert result["plan"] == "pro"
        assert result["business_count"] == 1
        assert result["audit_count"] == 2


# ---------------------------------------------------------------------------
# Audit tools
# ---------------------------------------------------------------------------


class TestAuditTools:
    def test_list_audit_templates(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = [{"id": "t1", "name": "Template 1"}]

        result = run(list_audit_templates(ctx))
        assert result["data"][0]["id"] == "t1"

    def test_create_audit_template(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.post.return_value = {"id": "t-new", "name": "My Template"}

        result = run(create_audit_template(
            ctx, name="My Template", business_id="b1", questions=["Q1", "Q2"],
        ))
        assert result["id"] == "t-new"
        payload = client.post.call_args[1]["json"]
        assert payload["questions"] == [{"question": "Q1"}, {"question": "Q2"}]

    def test_update_audit_template(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.put.return_value = {"id": "t1", "name": "Renamed"}

        result = run(update_audit_template(ctx, named_audit_id="t1", name="Renamed"))
        assert result["name"] == "Renamed"

    def test_delete_audit_template(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.delete.return_value = None

        result = run(delete_audit_template(ctx, named_audit_id="t1"))
        assert result["success"] is True

    def test_start_audit(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.post.return_value = {"job_id": "j1", "status": "running"}

        result = run(start_audit(ctx, named_audit_id="t1"))
        assert result["job_id"] == "j1"
        payload = client.post.call_args[1]["json"]
        assert payload["named_audit_id"] == "t1"
        assert "business_id" not in payload

    def test_start_audit_with_business_id(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.post.return_value = {"job_id": "j2", "status": "running"}

        run(start_audit(ctx, named_audit_id="t1", business_id="b1"))
        payload = client.post.call_args[1]["json"]
        assert payload["business_id"] == "b1"

    def test_get_audit_status(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"job_id": "j1", "status": "completed"}

        result = run(get_audit_status(ctx, job_id="j1"))
        assert result["status"] == "completed"

    def test_get_audit_result(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"scores": {"overall": 80}}

        result = run(get_audit_result(ctx, job_id="j1"))
        assert result["scores"]["overall"] == 80

    def test_list_audits(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = [{"job_id": "j1"}, {"job_id": "j2"}]

        result = run(list_audits(ctx))
        assert len(result["data"]) == 2


# ---------------------------------------------------------------------------
# Recommendation tools
# ---------------------------------------------------------------------------


class TestRecommendTools:
    def test_start_recommendation(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.post.return_value = {"job_id": "r1", "status": "running"}

        result = run(start_recommendation(ctx, audit_job_id="j1"))
        assert result["job_id"] == "r1"
        payload = client.post.call_args[1]["json"]
        assert payload["audit_job_id"] == "j1"

    def test_get_recommendation_status(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"job_id": "r1", "status": "completed"}

        result = run(get_recommendation_status(ctx, job_id="r1"))
        assert result["status"] == "completed"

    def test_get_recommendation_result(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"question_insights": [], "strengthening_tips": []}

        result = run(get_recommendation_result(ctx, job_id="r1"))
        assert "question_insights" in result

    def test_get_recommendation_insights_annotates_source(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {
            "question_insights": [{"question_id": "qi1", "question_text": "Test?"}],
            "head_to_head_comparisons": [{"competitor_domain": "comp.com"}],
            "strengthening_tips": [{"category": "llms_txt", "title": "Add llms.txt"}],
            "priority_actions": [],
        }

        result = run(get_recommendation_insights(ctx, job_id="r1"))
        qi = result["question_insights"][0]
        assert qi["source_type"] == "question_insight"
        assert qi["source_id"] == "qi1"

        h2h = result["head_to_head_comparisons"][0]
        assert h2h["source_type"] == "head_to_head"
        assert h2h["source_id"] == "comp.com"

        tip = result["strengthening_tips"][0]
        assert tip["source_type"] == "strengthening_tip"
        assert tip["source_id"] == "llms_txt"

    def test_list_recommendations(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = [{"job_id": "r1"}]

        result = run(list_recommendations(ctx, audit_job_id="j1"))
        assert result["data"][0]["job_id"] == "r1"


# ---------------------------------------------------------------------------
# Solution tools
# ---------------------------------------------------------------------------


class TestSolutionTools:
    def test_start_solution(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.post.return_value = {"job_id": "s1", "status": "running"}

        result = run(start_solution(
            ctx,
            recommendation_job_id="r1",
            source_type="question_insight",
            source_id="qi1",
        ))
        assert result["job_id"] == "s1"
        payload = client.post.call_args[1]["json"]
        assert payload == {
            "recommendation_job_id": "r1",
            "source_type": "question_insight",
            "source_id": "qi1",
        }

    def test_get_solution_status(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"job_id": "s1", "status": "completed"}

        result = run(get_solution_status(ctx, job_id="s1"))
        assert result["status"] == "completed"

    def test_get_solution_result(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"solution": "Add structured data..."}

        result = run(get_solution_result(ctx, job_id="s1"))
        assert "solution" in result

    def test_get_solution_result_strips_chat_history(self, ctx):
        """chat_history should be stripped — no MCP affordance for it."""
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {
            "solution_plan": "Do X",
            "chat_history": [{"role": "assistant", "content": "Ready?"}],
            "artifacts": [],
        }

        result = run(get_solution_result(ctx, job_id="s1"))
        assert "chat_history" not in result
        assert result["solution_plan"] == "Do X"

    def test_get_solution_result_absolute_download_path(self):
        """download_path should be absolute, not relative."""
        solution_ctx = make_ctx(api_url="https://api.youcited.com")
        client = solution_ctx.request_context.lifespan_context.client
        client.get.return_value = {
            "artifacts": [
                {
                    "id": "a1",
                    "download_path": "/solutions/j1/artifacts/a1/download",
                }
            ],
        }

        result = run(get_solution_result(solution_ctx, job_id="j1"))
        dp = result["artifacts"][0]["download_path"]
        assert dp == "https://api.youcited.com/solutions/j1/artifacts/a1/download"

    def test_start_solutions_batch(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.post.return_value = [
            {"source_type": "head_to_head", "source_id": "a.com", "job_id": "s1"},
            {"source_type": "head_to_head", "source_id": "b.com", "job_id": "s2"},
        ]

        result = run(start_solutions_batch(
            ctx,
            recommendation_job_id="r1",
            items=[
                {"source_type": "head_to_head", "source_id": "a.com"},
                {"source_type": "head_to_head", "source_id": "b.com"},
            ],
        ))
        assert result["data"][0]["job_id"] == "s1"
        payload = client.post.call_args[1]["json"]
        assert len(payload["items"]) == 2
        assert payload["items"][0]["recommendation_job_id"] == "r1"

    def test_list_solutions(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = [{"job_id": "s1"}, {"job_id": "s2"}]

        result = run(list_solutions(ctx))
        assert len(result["data"]) == 2


# ---------------------------------------------------------------------------
# Job tools
# ---------------------------------------------------------------------------


class TestJobTools:
    def test_get_job_status_with_type(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"job_id": "j1", "status": "completed"}

        result = run(get_job_status(ctx, job_id="j1", job_type="audit"))
        assert result["status"] == "completed"
        assert result["job_type"] == "audit"

    def test_get_job_status_probes_types(self, ctx):
        client = ctx.request_context.lifespan_context.client
        # First type (audit) 404s, second type (recommendation) succeeds
        client.get.side_effect = [
            CitedAPIError(404, "Not found"),
            {"job_id": "j1", "status": "completed"},
        ]

        result = run(get_job_status(ctx, job_id="j1"))
        assert result["status"] == "completed"
        assert result["job_type"] == "recommendation"

    def test_cancel_job(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.post.return_value = None

        result = run(cancel_job(ctx, job_id="j1", job_type="audit"))
        assert result["success"] is True
        assert result["job_type"] == "audit"

    def test_get_job_status_not_found(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = CitedAPIError(404, "Not found")

        result = run(get_job_status(ctx, job_id="j1"))
        assert result["error"] is True
        assert "No job found" in result["message"]


# ---------------------------------------------------------------------------
# Auth tools
# ---------------------------------------------------------------------------


class TestAuthTools:
    def test_check_auth_status(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = [
            {"email": "test@example.com", "plan": "pro"},  # /me
            [{"id": "b1"}],  # /businesses
        ]

        result = run(check_auth_status(ctx))
        assert result["email"] == "test@example.com"
        assert result["business_count"] == 1

    def test_logout(self, ctx):
        # Patch TokenStore to avoid real keyring access
        import cited_mcp.tools.auth as auth_mod
        original_clear = auth_mod._clear_session

        cleared = []

        def fake_clear(cited_ctx, env):
            cited_ctx.client.token = None
            cleared.append(env)

        auth_mod._clear_session = fake_clear
        try:
            result = run(logout(ctx))
            assert result["success"] is True
            assert "dev" in cleared
        finally:
            auth_mod._clear_session = original_clear

    def test_login_returns_url_immediately(self, unauth_ctx):
        """Login should NOT block — it returns a URL for the user to click."""
        import cited_mcp.tools.auth as auth_mod

        # Ensure no pending login
        auth_mod._pending_login = None
        auth_mod._pending_login_env = None

        result = run(login(unauth_ctx))

        assert result["action_required"] is True
        assert "login_url" in result
        assert "youcited.com/auth/authorize-app" in result["login_url"]
        assert "callback=" in result["login_url"]
        assert "app_name=cited-mcp" in result["login_url"]
        assert "instructions" in result

        # Clean up the callback server
        if auth_mod._pending_login:
            auth_mod._pending_login.shutdown()
            auth_mod._pending_login = None
            auth_mod._pending_login_env = None

    def test_login_second_call_detects_token(self, unauth_ctx):
        """Second login call should detect a captured token and finalize."""
        import cited_mcp.tools.auth as auth_mod
        from cited_core.auth.oauth_server import OAuthCallbackServer

        # Simulate a callback server that already captured a token
        server = OAuthCallbackServer(timeout=5)
        server.token = "captured-jwt-token"
        auth_mod._pending_login = server
        auth_mod._pending_login_env = "dev"

        # Mock the client to verify token works
        client = unauth_ctx.request_context.lifespan_context.client
        client.get.return_value = {"email": "user@example.com"}

        # Patch TokenStore to avoid real keyring/file writes
        import unittest.mock
        with unittest.mock.patch("cited_mcp.tools.auth.TokenStore"):
            result = run(login(unauth_ctx))

        assert result["success"] is True
        assert "user@example.com" in result["message"]
        assert auth_mod._pending_login is None

    def test_login_second_call_still_waiting(self, unauth_ctx):
        """If token hasn't arrived yet, login should remind the user."""
        import cited_mcp.tools.auth as auth_mod
        from cited_core.auth.oauth_server import OAuthCallbackServer

        # Simulate a callback server with no token yet
        server = OAuthCallbackServer(timeout=5)
        server.token = None
        server.start()
        auth_mod._pending_login = server
        auth_mod._pending_login_env = "dev"

        try:
            result = run(login(unauth_ctx))
            assert result["waiting"] is True
            assert "login_url" in result
        finally:
            server.shutdown()
            auth_mod._pending_login = None
            auth_mod._pending_login_env = None

    def test_login_already_authenticated(self, ctx):
        """If already authenticated, login should return success without starting a flow."""
        import cited_mcp.tools.auth as auth_mod
        auth_mod._pending_login = None

        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"email": "existing@example.com"}

        result = run(login(ctx))
        assert result["success"] is True
        assert "Already authenticated" in result["message"]

    def test_pending_login_auto_detected_by_other_tools(self):
        """_check_pending_login should capture token and set it on the client."""
        import unittest.mock

        import cited_mcp.tools.auth as auth_mod
        from cited_core.auth.oauth_server import OAuthCallbackServer

        # Create a real CitedContext (not mocked) so token assignment works
        cited_ctx = CitedContext(
            client=MagicMock(spec=CitedClient),
            env="dev",
            api_url="https://dev.youcited.com",
        )
        cited_ctx.client.token = None
        cited_ctx.client._client = MagicMock()

        # Set up pending login with a captured token
        server = OAuthCallbackServer(timeout=5)
        server.token = "auto-detected-jwt"
        auth_mod._pending_login = server
        auth_mod._pending_login_env = "dev"

        with unittest.mock.patch("cited_mcp.tools.auth.TokenStore"):
            result = auth_mod._check_pending_login(cited_ctx)

        assert result is True
        assert cited_ctx.client.token == "auto-detected-jwt"
        assert auth_mod._pending_login is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_api_error_with_hint(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = CitedAPIError(403, "plan limit reached")

        result = run(list_businesses(ctx))
        assert result["error"] is True
        assert result["status_code"] == 403
        assert "hint" in result
        assert "plan" in result["hint"].lower()

    def test_api_error_422(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.post.side_effect = CitedAPIError(422, "Validation error: website not resolvable")

        result = run(create_business(ctx, name="x", website="x", description="x" * 60))
        assert result["error"] is True
        assert result["status_code"] == 422
        assert "validation" in result["hint"].lower()

    def test_api_error_401(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = CitedAPIError(401, "Unauthorized")

        result = run(get_business(ctx, business_id="b1"))
        assert result["error"] is True
        assert result["status_code"] == 401
        assert "expired" in result["hint"].lower()


# ---------------------------------------------------------------------------
# New tools: ping, audit detail, HQ, analytics, agent, export
# ---------------------------------------------------------------------------


class TestPing:
    def test_ping_returns_ok(self, ctx):
        result = run(ping(ctx))
        assert result["status"] == "ok"
        assert result["server"] == "cited-mcp"

    def test_ping_works_without_auth(self, unauth_ctx):
        result = run(ping(unauth_ctx))
        assert result["status"] == "ok"


class TestAuditResultModes:
    def test_audit_result_summary_by_default(self, ctx):
        """Default mode should pass fields=summary to the API."""
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"overall_citation_rate": 75, "question_ids": ["q1"]}

        result = run(get_audit_result(ctx, job_id="j1"))
        assert result["overall_citation_rate"] == 75
        call_params = client.get.call_args[1].get("params", {})
        assert call_params.get("fields") == "summary"

    def test_audit_result_full_mode(self, ctx):
        """full=True should NOT pass fields=summary."""
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"citations_pulled": [{"id": "c1"}]}

        result = run(get_audit_result(ctx, job_id="j1", full=True))
        assert "citations_pulled" in result
        call_params = client.get.call_args[1].get("params", {})
        assert "fields" not in call_params

    def test_audit_question_detail(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {
            "id": "q1",
            "question_text": "Test question?",
            "coverage_score": 0.8,
            "citations": [{"id": "c1"}],
        }

        result = run(get_audit_question_detail(ctx, job_id="j1", question_id="q1"))
        assert result["question_text"] == "Test question?"

    def test_export_audit(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"url": "https://example.com/report.pdf"}

        result = run(export_audit(ctx, job_id="j1"))
        assert "url" in result

    def test_create_template_with_include_business_name(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.post.return_value = {"id": "t1", "include_business_name": True}

        run(create_audit_template(
            ctx, name="Test", business_id="b1", include_business_name=True,
        ))
        payload = client.post.call_args[1]["json"]
        assert payload["include_business_name"] is True


class TestNewToolModules:
    def test_get_business_hq(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"health_scores": {"overall": 80}}

        result = run(get_business_hq(ctx, business_id="b1"))
        assert result["health_scores"]["overall"] == 80

    def test_get_analytics_trends(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"trends": [{"date": "2026-04-01", "score": 75}]}

        result = run(get_analytics_trends(ctx, business_id="b1"))
        assert result["trends"][0]["score"] == 75

    def test_get_business_facts(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"facts": [{"key": "founded", "value": "2020"}]}

        result = run(get_business_facts(ctx, business_id="b1"))
        assert result["facts"][0]["key"] == "founded"

    def test_buyer_fit_query(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.post.return_value = {"fit_score": 0.85, "reasons": ["strong match"]}

        result = run(buyer_fit_query(ctx, query="best GEO tool"))
        assert result["fit_score"] == 0.85
        payload = client.post.call_args[1]["json"]
        assert payload["query"] == "best GEO tool"

    def test_agent_tool_requires_business_id(self, ctx):
        """Agent tools should return error if no business_id and no default."""
        # No default_business_id set on context
        result = run(get_business_facts(ctx))
        assert result["error"] is True
        assert "business_id" in result["message"]


# ---------------------------------------------------------------------------
# Error response structure (new fields: error_type, retriable)
# ---------------------------------------------------------------------------


class TestStructuredErrorResponses:
    def test_timeout_has_error_type_and_retriable(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = httpx.TimeoutException("timed out")

        result = run(list_businesses(ctx))
        assert result["error_type"] == "upstream_timeout"
        assert result["retriable"] is True

    def test_connect_error_has_error_type_and_retriable(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = httpx.ConnectError("refused")

        result = run(get_business(ctx, business_id="b1"))
        assert result["error_type"] == "connection_error"
        assert result["retriable"] is True

    def test_generic_exception_has_error_type_and_retriable(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = RuntimeError("unexpected")

        result = run(list_businesses(ctx))
        assert result["error_type"] == "RuntimeError"
        assert result["retriable"] is True


# ---------------------------------------------------------------------------
# Plan gating integration (decorator actually blocks)
# ---------------------------------------------------------------------------


class TestPlanGatingIntegration:
    """Verify the log_tool_call decorator enforces plan gating end-to-end."""

    def test_growth_user_blocked_from_create_business(self):
        """A growth-tier user should get an upgrade message for create_business."""
        import hashlib
        import time

        from cited_mcp.tools._helpers import _tier_cache

        growth_ctx = make_ctx(token="growth-user-token")
        cache_key = hashlib.sha256(b"growth-user-token").hexdigest()[:16]
        _tier_cache[cache_key] = ("growth", time.monotonic() + 3600)

        client = growth_ctx.request_context.lifespan_context.client
        client.post.return_value = {"id": "should-not-reach"}

        result = run(create_business(
            growth_ctx, name="X", website="x", description="x" * 60,
        ))
        assert result["error"] is True
        assert result["required_tier"] == "scale"
        assert "upgrade" in result["hint"].lower()
        # The actual API should NOT have been called
        client.post.assert_not_called()

    def test_scale_user_allowed_create_business(self):
        """A scale-tier user should successfully call create_business."""
        import hashlib
        import time

        from cited_mcp.tools._helpers import _tier_cache

        scale_ctx = make_ctx(token="scale-user-token")
        cache_key = hashlib.sha256(b"scale-user-token").hexdigest()[:16]
        _tier_cache[cache_key] = ("scale", time.monotonic() + 3600)

        client = scale_ctx.request_context.lifespan_context.client
        client.post.return_value = {"id": "new-id", "name": "Created"}

        result = run(create_business(
            scale_ctx, name="Biz", website="https://biz.com",
            description="A business description long enough",
        ))
        assert result["id"] == "new-id"
        client.post.assert_called_once()

    def test_growth_user_can_list_businesses(self):
        """Growth-tier users can still use base tools."""
        import hashlib
        import time

        from cited_mcp.tools._helpers import _tier_cache

        growth_ctx = make_ctx(token="growth-user-token2")
        cache_key = hashlib.sha256(b"growth-user-token2").hexdigest()[:16]
        _tier_cache[cache_key] = ("growth", time.monotonic() + 3600)

        client = growth_ctx.request_context.lifespan_context.client
        client.get.return_value = [{"id": "b1"}]

        result = run(list_businesses(growth_ctx))
        assert "data" in result


# ---------------------------------------------------------------------------
# Timeout and connection error handling
# ---------------------------------------------------------------------------


class TestDecoratorErrorHandling:
    """Verify the log_tool_call decorator catches ALL exceptions as structured errors."""

    def test_exception_in_plan_gating_returns_structured_error(self):
        """If _get_ctx raises during plan gating, should return error dict, not crash."""
        import hashlib
        import time
        from unittest.mock import patch

        from cited_mcp.tools._helpers import _tier_cache

        # Set up a context where the plan gating will call _get_ctx
        gated_ctx = make_ctx(token="gating-test-token")
        cache_key = hashlib.sha256(b"gating-test-token").hexdigest()[:16]
        _tier_cache[cache_key] = ("growth", time.monotonic() + 3600)

        # Mock _get_ctx to raise an exception (simulating OAuth failure)
        with patch(
            "cited_mcp.tools._helpers._get_ctx",
            side_effect=RuntimeError("OAuth context unavailable"),
        ):
            # Call a non-auth tool — plan gating will call _get_ctx
            result = run(list_businesses(gated_ctx))

        # Should get a structured error, NOT a bare exception
        assert result["error"] is True
        assert result["error_type"] == "RuntimeError"
        assert result["retriable"] is True
        assert "_request_id" in result

    def test_generic_exception_returns_structured_error(self):
        """Any uncaught exception in the tool should return structured error."""
        ctx = make_ctx()
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = RuntimeError("Unexpected internal error")

        result = run(list_businesses(ctx))
        assert result["error"] is True
        assert result["retriable"] is True
        assert "_request_id" in result


class TestTransportErrors:
    def test_timeout_returns_error(self, ctx):
        """httpx.TimeoutException should return a structured error, not crash."""
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = httpx.TimeoutException("timed out")

        result = run(list_businesses(ctx))
        assert result["error"] is True
        assert "timed out" in result["message"].lower()
        assert "_request_id" in result

    def test_connect_error_returns_error(self, ctx):
        """httpx.ConnectError should return a structured error."""
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = httpx.ConnectError("connection refused")

        result = run(get_business(ctx, business_id="b1"))
        assert result["error"] is True
        assert "connect" in result["message"].lower()
        assert "_request_id" in result


# ---------------------------------------------------------------------------
# Tier cache behavior
# ---------------------------------------------------------------------------


class TestTierCache:
    def test_cache_returns_cached_value(self):
        """Cached tier should be returned without API call."""
        import time

        from cited_mcp.tools._helpers import _get_user_tier, _tier_cache

        _tier_cache["cache-test-key"] = ("scale", time.monotonic() + 3600)

        mock_ctx = CitedContext(
            client=MagicMock(spec=CitedClient),
            env="dev",
            api_url="https://dev.youcited.com",
        )

        result = _get_user_tier(mock_ctx, "cache-test-key")
        assert result == "scale"
        mock_ctx.client.get.assert_not_called()

    def test_cache_miss_calls_api(self):
        """On cache miss, should call /auth/me and cache the result."""

        from cited_mcp.tools._helpers import _get_user_tier, _tier_cache

        _tier_cache.pop("new-user-key", None)

        mock_ctx = CitedContext(
            client=MagicMock(spec=CitedClient),
            env="dev",
            api_url="https://dev.youcited.com",
        )
        mock_ctx.client.get.return_value = {"subscription_tier": "pro"}

        result = _get_user_tier(mock_ctx, "new-user-key")
        assert result == "pro"
        mock_ctx.client.get.assert_called_once_with("/auth/me")
        assert "new-user-key" in _tier_cache

    def test_cache_fallback_on_api_failure(self):
        """On API failure with stale cache, should return stale value."""
        import time

        from cited_mcp.tools._helpers import _get_user_tier, _tier_cache

        # Set an expired cache entry
        _tier_cache["stale-key"] = ("growth", time.monotonic() - 100)

        mock_ctx = CitedContext(
            client=MagicMock(spec=CitedClient),
            env="dev",
            api_url="https://dev.youcited.com",
        )
        mock_ctx.client.get.side_effect = Exception("API down")

        result = _get_user_tier(mock_ctx, "stale-key")
        assert result == "growth"  # stale value used as fallback


# ---------------------------------------------------------------------------
# Helpers: truncation and rate limiting
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_truncate_response_small_payload(self):
        from cited_mcp.tools._helpers import _truncate_response

        data = {"items": [1, 2, 3]}
        assert _truncate_response(data) == data

    def test_truncate_response_large_list(self):
        from cited_mcp.tools._helpers import _truncate_response

        big_list = [{"content": "x" * 1000} for _ in range(200)]
        result = _truncate_response(big_list, max_bytes=5000)
        assert result["_truncated"] is True
        assert len(result["data"]) < 200

    def test_truncate_response_large_dict_with_lists(self):
        from cited_mcp.tools._helpers import _truncate_response

        data = {"items": [{"content": "x" * 500} for _ in range(200)], "meta": "ok"}
        result = _truncate_response(data, max_bytes=5000)
        assert result["_truncated"] is True
        assert "items" in result["_truncated_fields"]

    def test_rate_limit_blocks_after_limit(self):
        from cited_mcp.tools._helpers import _check_rate_limit, _rate_limits

        test_user = "test-rate-limit-user"
        _rate_limits.pop(test_user, None)

        # Fill up the window (use a low limit)
        import os
        original = os.environ.get("CITED_RATE_LIMIT")
        os.environ["CITED_RATE_LIMIT"] = "5"

        # Reload the limit
        import cited_mcp.tools._helpers as helpers
        helpers._RATE_LIMIT = 5

        try:
            for _ in range(5):
                assert _check_rate_limit(test_user) is None
            # 6th call should be blocked
            result = _check_rate_limit(test_user)
            assert result is not None
            assert result["error"] is True
            assert "Rate limited" in result["message"]
        finally:
            helpers._RATE_LIMIT = 60
            if original is not None:
                os.environ["CITED_RATE_LIMIT"] = original
            else:
                os.environ.pop("CITED_RATE_LIMIT", None)
            _rate_limits.pop(test_user, None)


# ---------------------------------------------------------------------------
# Server creation
# ---------------------------------------------------------------------------


class TestServerSetup:
    def test_create_stdio_server_registers_tools(self):
        import cited_mcp.server as server_mod

        server = server_mod.mcp
        assert server is not None
        # Check that tools are registered
        tool_names = [t.name for t in server._tool_manager.list_tools()]
        assert "list_businesses" in tool_names
        assert "start_audit" in tool_names
        assert "start_recommendation" in tool_names
        assert "start_solution" in tool_names
        assert "get_job_status" in tool_names
        assert "check_auth_status" in tool_names


# ---------------------------------------------------------------------------
# Action plan tools
# ---------------------------------------------------------------------------


def _action_fixture(
    action_id: str = "a1",
    action_type: str = "schema_patch",
    source_type: str = "recommendation",
    impact_score: int = 70,
    effort_score: int = 30,
    priority_score: int = 80,
    status: str = "pending",
    title: str = "Add FAQ schema",
) -> dict[str, Any]:
    """Build a PriorityActionResponse-shaped dict for tests."""
    return {
        "id": action_id,
        "title": title,
        "description": "Improve answer extraction",
        "action_type": action_type,
        "source_type": source_type,
        "impact_score": impact_score,
        "effort_score": effort_score,
        "priority_score": priority_score,
        "status": status,
        "components": {"impact": impact_score},
        "forecast": {"rationale": "Lifts citation rate"},
    }


class TestActionPlanTools:
    # -- get_action_plan --

    def test_get_action_plan_unauth(self, unauth_ctx):
        result = run(get_action_plan(unauth_ctx, business_id="b1"))
        assert result["error"] is True

    def test_get_action_plan_requires_business_id(self, ctx):
        # No default_business_id set on context
        result = run(get_action_plan(ctx))
        assert result["error"] is True
        assert "business_id" in result["message"]

    def test_get_action_plan_returns_simplified_actions(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = [
            _action_fixture("a1", title="First"),
            _action_fixture("a2", title="Second"),
        ]

        result = run(get_action_plan(ctx, business_id="b1", limit=2))

        assert result["total_actions"] == 2
        assert result["actions"][0]["rank"] == 1
        assert result["actions"][0]["id"] == "a1"
        assert result["actions"][0]["title"] == "First"
        # Effort is derived from action_type
        assert result["actions"][0]["effort_bucket"] == "easy"
        assert result["actions"][0]["effort"].startswith("Easy")
        assert result["actions"][1]["rank"] == 2
        assert "_checklist_hint" in result

    def test_get_action_plan_effort_filter(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = [
            _action_fixture("a1", action_type="schema_patch"),       # easy
            _action_fixture("a2", action_type="content_update"),     # medium
            _action_fixture("a3", action_type="content_new_page"),   # hard
        ]

        result = run(get_action_plan(ctx, business_id="b1", effort_filter="easy"))
        assert result["total_actions"] == 1
        assert result["actions"][0]["id"] == "a1"

    def test_get_action_plan_source_filter(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = [
            _action_fixture("a1", source_type="recommendation"),
            _action_fixture("a2", source_type="trust_signal"),
        ]

        result = run(get_action_plan(ctx, business_id="b1", source_filter="trust_signal"))
        assert result["total_actions"] == 1
        assert result["actions"][0]["id"] == "a2"

    def test_get_action_plan_handles_non_list_response(self, ctx):
        # Defensive: if the API returns a dict (e.g. error envelope), tool returns empty list
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"unexpected": "shape"}

        result = run(get_action_plan(ctx, business_id="b1"))
        assert result["total_actions"] == 0
        assert result["actions"] == []

    def test_get_action_plan_api_error(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = CitedAPIError(500, "boom")

        result = run(get_action_plan(ctx, business_id="b1"))
        assert result["error"] is True
        assert result["status_code"] == 500

    def test_get_action_plan_uses_priority_endpoint(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = []

        run(get_action_plan(ctx, business_id="b1", limit=5))
        path = client.get.call_args[0][0]
        assert "/businesses/b1/hq/priority" in path
        # Tool fetches more than `limit` so it can filter client-side
        assert client.get.call_args[1]["params"]["limit"] >= 5

    # -- get_quick_wins --

    def test_get_quick_wins_unauth(self, unauth_ctx):
        result = run(get_quick_wins(unauth_ctx, business_id="b1"))
        assert result["error"] is True

    def test_get_quick_wins_requires_business_id(self, ctx):
        result = run(get_quick_wins(ctx))
        assert result["error"] is True
        assert "business_id" in result["message"]

    def test_get_quick_wins_filters_low_effort_high_impact(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = [
            # Quick win: low effort, high impact
            _action_fixture("win", effort_score=20, impact_score=80),
            # Not a quick win: high effort
            _action_fixture("hard", effort_score=80, impact_score=80),
            # Not a quick win: low impact
            _action_fixture("low", effort_score=20, impact_score=30),
        ]

        result = run(get_quick_wins(ctx, business_id="b1"))
        assert result["total_quick_wins"] == 1
        assert result["actions"][0]["id"] == "win"

    def test_get_quick_wins_fallback_when_no_match(self, ctx):
        # No action passes the strict filter — fall back to easy/medium effort items
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = [
            _action_fixture("a1", action_type="schema_patch", effort_score=80, impact_score=20),
            _action_fixture("a2", action_type="content_new_page", effort_score=80, impact_score=20),
        ]

        result = run(get_quick_wins(ctx, business_id="b1"))
        # schema_patch is "easy" so it qualifies in fallback; content_new_page is "hard"
        assert result["total_quick_wins"] == 1
        assert result["actions"][0]["id"] == "a1"

    def test_get_quick_wins_respects_max_results(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = [
            _action_fixture(f"a{i}", effort_score=10, impact_score=90)
            for i in range(10)
        ]

        result = run(get_quick_wins(ctx, business_id="b1", max_results=3))
        assert result["total_quick_wins"] == 3

    def test_get_quick_wins_api_error(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = CitedAPIError(403, "forbidden")

        result = run(get_quick_wins(ctx, business_id="b1"))
        assert result["error"] is True
        assert result["status_code"] == 403

    # -- mark_action_done --

    def test_mark_action_done_unauth(self, unauth_ctx):
        result = run(mark_action_done(unauth_ctx, action_id="a1", business_id="b1"))
        assert result["error"] is True

    def test_mark_action_done_requires_business_id(self, ctx):
        result = run(mark_action_done(ctx, action_id="a1"))
        assert result["error"] is True
        assert "business_id" in result["message"]

    def test_mark_action_done_success(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.patch.return_value = {"updated_at": "2026-05-04T00:00:00Z"}

        result = run(mark_action_done(ctx, action_id="a1", business_id="b1"))
        assert result["success"] is True
        assert result["action_id"] == "a1"
        assert result["status"] == "completed"

        path = client.patch.call_args[0][0]
        assert "/businesses/b1/hq/priority/a1/status" in path
        assert client.patch.call_args[1]["json"] == {"status": "completed"}

    def test_mark_action_done_api_error(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.patch.side_effect = CitedAPIError(404, "not found")

        result = run(mark_action_done(ctx, action_id="a1", business_id="b1"))
        assert result["error"] is True
        assert result["status_code"] == 404

    # -- dismiss_action --

    def test_dismiss_action_unauth(self, unauth_ctx):
        result = run(dismiss_action(unauth_ctx, action_id="a1", business_id="b1"))
        assert result["error"] is True

    def test_dismiss_action_requires_business_id(self, ctx):
        result = run(dismiss_action(ctx, action_id="a1"))
        assert result["error"] is True
        assert "business_id" in result["message"]

    def test_dismiss_action_success(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.patch.return_value = {}

        result = run(dismiss_action(ctx, action_id="a1", business_id="b1"))
        assert result["success"] is True
        assert result["action_id"] == "a1"
        assert result["status"] == "dismissed"
        assert client.patch.call_args[1]["json"] == {"status": "dismissed"}

    def test_dismiss_action_api_error(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.patch.side_effect = CitedAPIError(403, "forbidden")

        result = run(dismiss_action(ctx, action_id="a1", business_id="b1"))
        assert result["error"] is True

    # -- get_action_progress --

    def test_get_action_progress_unauth(self, unauth_ctx):
        result = run(get_action_progress(unauth_ctx, business_id="b1"))
        assert result["error"] is True

    def test_get_action_progress_requires_business_id(self, ctx):
        result = run(get_action_progress(ctx))
        assert result["error"] is True
        assert "business_id" in result["message"]

    def test_get_action_progress_computes_percentages(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {
            "total": 10,
            "completed": 4,
            "dismissed": 1,
        }

        result = run(get_action_progress(ctx, business_id="b1"))
        assert result["total"] == 10
        assert result["completed"] == 4
        assert result["remaining"] == 5  # 10 - 4 - 1
        assert result["completion_pct"] == 40
        assert "_progress_hint" in result
        assert "4 of 10" in result["_progress_hint"]

    def test_get_action_progress_zero_total(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"total": 0, "completed": 0, "dismissed": 0}

        result = run(get_action_progress(ctx, business_id="b1"))
        assert result["completion_pct"] == 0
        assert result["remaining"] == 0

    def test_get_action_progress_uses_summary_endpoint(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.return_value = {"total": 1, "completed": 0, "dismissed": 0}

        run(get_action_progress(ctx, business_id="b1"))
        path = client.get.call_args[0][0]
        assert "/businesses/b1/hq/priority/summary" in path

    def test_get_action_progress_api_error(self, ctx):
        client = ctx.request_context.lifespan_context.client
        client.get.side_effect = CitedAPIError(500, "boom")

        result = run(get_action_progress(ctx, business_id="b1"))
        assert result["error"] is True
        assert result["status_code"] == 500
