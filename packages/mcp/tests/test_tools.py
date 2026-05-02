"""Tests for cited-mcp tool functions.

Tests call tool functions directly with a mocked CitedClient,
bypassing the MCP transport layer.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
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
from cited_mcp.tools.billing import upgrade_plan  # noqa: E402
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
from cited_mcp.tools.changelog import whats_new  # noqa: E402
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
            ctx, name="My Template", business_id="b1", questions=["Q1", "Q2"]
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

    def test_ping_includes_server_version(self, ctx):
        from cited_core import __version__

        result = run(ping(ctx))
        assert result["server_version"] == __version__

    def test_ping_includes_tools_fingerprint(self, ctx):
        result = run(ping(ctx))
        assert "tools_fingerprint" in result
        fp = result["tools_fingerprint"]
        assert isinstance(fp, str) and len(fp) == 12
        int(fp, 16)  # 12-char lowercase hex

    def test_ping_includes_tools_count(self, ctx):
        result = run(ping(ctx))
        assert isinstance(result["tools_count"], int)
        assert result["tools_count"] > 0

    def test_ping_fingerprint_deterministic_across_calls(self, ctx):
        first = run(ping(ctx))
        second = run(ping(ctx))
        assert first["tools_fingerprint"] == second["tools_fingerprint"]


class TestToolsFingerprint:
    """Direct coverage of the fingerprint hash and registry hookup."""

    def test_hash_deterministic(self):
        from cited_mcp.server import _hash_tool_surface

        items = [("a", "desc", "{}"), ("b", "desc2", '{"x":1}')]
        assert _hash_tool_surface(items) == _hash_tool_surface(items)

    def test_hash_order_independent(self):
        from cited_mcp.server import _hash_tool_surface

        forward = [("a", "d1", "{}"), ("b", "d2", "{}")]
        reverse = [("b", "d2", "{}"), ("a", "d1", "{}")]
        assert _hash_tool_surface(forward) == _hash_tool_surface(reverse)

    def test_hash_changes_when_name_changes(self):
        from cited_mcp.server import _hash_tool_surface

        a = [("foo", "desc", "{}")]
        b = [("bar", "desc", "{}")]
        assert _hash_tool_surface(a) != _hash_tool_surface(b)

    def test_hash_changes_when_description_changes(self):
        from cited_mcp.server import _hash_tool_surface

        a = [("foo", "old description", "{}")]
        b = [("foo", "new description", "{}")]
        assert _hash_tool_surface(a) != _hash_tool_surface(b)

    def test_hash_changes_when_input_schema_changes(self):
        from cited_mcp.server import _hash_tool_surface

        a = [("foo", "desc", '{"properties":{"x":{"type":"string"}}}')]
        b = [("foo", "desc", '{"properties":{"x":{"type":"integer"}}}')]
        assert _hash_tool_surface(a) != _hash_tool_surface(b)

    def test_compute_uses_registered_tools(self):
        """compute_tools_fingerprint reflects the live tool registry."""
        from cited_mcp.server import compute_tools_fingerprint
        from cited_mcp.server import mcp as registered_mcp

        first = compute_tools_fingerprint(registered_mcp)
        second = compute_tools_fingerprint(registered_mcp)
        assert first == second
        assert isinstance(first, str) and len(first) == 12

    def test_fingerprint_changes_when_tool_added(self):
        """Adding a tool to the live registry produces a different fingerprint."""
        from cited_mcp.server import compute_tools_fingerprint
        from cited_mcp.server import mcp as registered_mcp

        before = compute_tools_fingerprint(registered_mcp)

        async def __synthetic_test_tool() -> str:
            """Synthetic tool used only by tests."""
            return "ok"

        registered_mcp._tool_manager.add_tool(
            __synthetic_test_tool, name="__synthetic_test_tool"
        )
        try:
            after = compute_tools_fingerprint(registered_mcp)
            assert before != after
        finally:
            del registered_mcp._tool_manager._tools["__synthetic_test_tool"]

        restored = compute_tools_fingerprint(registered_mcp)
        assert restored == before


class TestWhatsNew:
    """whats_new tool — diff against a prior fingerprint or version."""

    @pytest.fixture
    def fake_changelog(self, monkeypatch):
        """Patch the module-level changelog with a deterministic fixture."""
        from cited_mcp.tools import changelog as cl

        fixture = {
            "versions": [
                {
                    "version": "0.4.0",
                    "released": "2026-06-01",
                    "fingerprint": "FFF000000000",
                    "tools_added": [
                        {"name": "new_tool", "description": "Newest tool"}
                    ],
                    "tools_changed": [],
                    "tools_removed": [],
                },
                {
                    "version": "0.3.9",
                    "released": "2026-05-15",
                    "fingerprint": "EEE000000000",
                    "tools_added": [],
                    "tools_changed": [
                        {"name": "old_tool", "change_summary": "Tweaked schema"}
                    ],
                    "tools_removed": [],
                },
                {
                    "version": "0.3.8",
                    "released": "2026-05-01",
                    "fingerprint": "DDD000000000",
                    "tools_added": [
                        {"name": "ancient_tool", "description": "Was new once"}
                    ],
                    "tools_changed": [],
                    "tools_removed": [
                        {"name": "removed_tool"}
                    ],
                },
            ]
        }
        monkeypatch.setattr(cl, "_CHANGELOG", fixture)
        return fixture

    def test_no_args_returns_most_recent_entry(self, ctx, fake_changelog):
        result = run(whats_new(ctx))
        names = [t["name"] for t in result["tools_added"]]
        assert names == ["new_tool"]
        assert result.get("no_changes") is not True
        assert "_note" not in result

    def test_matching_latest_fingerprint_returns_no_changes(self, ctx, fake_changelog):
        result = run(whats_new(ctx, since_fingerprint="FFF000000000"))
        assert result["no_changes"] is True
        assert result["tools_added"] == []
        assert result["tools_changed"] == []
        assert result["tools_removed"] == []

    def test_old_fingerprint_returns_aggregated_diff(self, ctx, fake_changelog):
        # Came from 0.3.8 → expect diffs from 0.3.9 + 0.4.0 aggregated
        result = run(whats_new(ctx, since_fingerprint="DDD000000000"))
        names_added = [t["name"] for t in result["tools_added"]]
        names_changed = [t["name"] for t in result["tools_changed"]]
        assert names_added == ["new_tool"]
        assert names_changed == ["old_tool"]
        # added_in_version should reflect the entry that introduced the tool
        assert result["tools_added"][0]["added_in_version"] == "0.4.0"
        assert result["tools_changed"][0]["changed_in_version"] == "0.3.9"
        assert result.get("no_changes") is not True
        assert "_note" not in result

    def test_old_version_returns_aggregated_diff(self, ctx, fake_changelog):
        result = run(whats_new(ctx, since_version="0.3.8"))
        names_added = [t["name"] for t in result["tools_added"]]
        assert names_added == ["new_tool"]

    def test_unrecognized_fingerprint_returns_full_history_with_note(
        self, ctx, fake_changelog
    ):
        result = run(whats_new(ctx, since_fingerprint="000000000000"))
        assert "_note" in result
        assert "not recognized" in result["_note"]
        # Full history aggregated — every tools_added across all entries
        names = [t["name"] for t in result["tools_added"]]
        assert "new_tool" in names
        assert "ancient_tool" in names

    def test_unrecognized_version_returns_full_history_with_note(
        self, ctx, fake_changelog
    ):
        result = run(whats_new(ctx, since_version="0.0.1"))
        assert "_note" in result
        names = [t["name"] for t in result["tools_added"]]
        assert "ancient_tool" in names

    def test_fingerprint_takes_precedence_over_version(self, ctx, fake_changelog):
        # Fingerprint matches 0.3.9; since_version says 0.3.8.
        # Expect fingerprint to win → only entries newer than 0.3.9.
        result = run(
            whats_new(
                ctx,
                since_fingerprint="EEE000000000",
                since_version="0.3.8",
            )
        )
        names_added = [t["name"] for t in result["tools_added"]]
        assert names_added == ["new_tool"]

    def test_unrecognized_fingerprint_falls_back_to_version(
        self, ctx, fake_changelog
    ):
        # Bogus fingerprint but valid version — should resolve via version
        # rather than returning full history.
        result = run(
            whats_new(
                ctx,
                since_fingerprint="000000000000",
                since_version="0.3.8",
            )
        )
        # Recognized via version, so no _note and bounded diff
        assert "_note" not in result
        names_added = [t["name"] for t in result["tools_added"]]
        assert names_added == ["new_tool"]

    def test_response_includes_current_version_and_fingerprint(
        self, ctx, fake_changelog
    ):
        result = run(whats_new(ctx))
        assert "current_version" in result
        assert "current_fingerprint" in result

    def test_load_changelog_missing_file(self, tmp_path, monkeypatch):
        from cited_mcp.tools import changelog as cl

        monkeypatch.setattr(cl, "_CHANGELOG_PATH", tmp_path / "nonexistent.yaml")
        data, err = cl._load_changelog()
        assert data == {"versions": []}
        assert err is not None
        assert "not found" in err

    def test_load_changelog_invalid_structure(self, tmp_path, monkeypatch):
        from cited_mcp.tools import changelog as cl

        bad = tmp_path / "tool_changelog.yaml"
        bad.write_text("this is just a string, not a versions dict")
        monkeypatch.setattr(cl, "_CHANGELOG_PATH", bad)
        data, err = cl._load_changelog()
        assert data == {"versions": []}
        assert err is not None
        assert "invalid structure" in err

    def test_load_changelog_yaml_parse_error_does_not_raise(
        self, tmp_path, monkeypatch
    ):
        """Blast-radius guard: a parse error must NOT propagate up to module
        import / register_tools / server startup."""
        from cited_mcp.tools import changelog as cl

        bad = tmp_path / "tool_changelog.yaml"
        # Real-world parse error: bad indent + unclosed bracket
        bad.write_text(
            'versions:\n'
            '  - version: "0.4.0"\n'
            '      malformed_indent: true\n'
            '      [unclosed bracket\n'
        )
        monkeypatch.setattr(cl, "_CHANGELOG_PATH", bad)
        # Critical: this MUST NOT raise
        data, err = cl._load_changelog()
        assert data == {"versions": []}
        assert err is not None
        assert "parse error" in err.lower()

    def test_whats_new_surfaces_changelog_load_error(self, ctx, monkeypatch):
        """Blast-radius (c): when the changelog couldn't be loaded, whats_new
        returns a structured error rather than a 500 or a silent empty diff."""
        from cited_mcp.tools import changelog as cl

        monkeypatch.setattr(cl, "_CHANGELOG", {"versions": []})
        monkeypatch.setattr(
            cl,
            "_CHANGELOG_LOAD_ERROR",
            "changelog YAML parse error: ParserError",
        )
        result = run(whats_new(ctx))
        assert result["error"] is True
        assert result["error_type"] == "changelog_unavailable"
        assert "ParserError" in result["message"]
        assert "Disconnect and reconnect" in result["message"]
        assert result["tools_added"] == []
        assert result["tools_changed"] == []
        assert result["tools_removed"] == []
        # current_version / current_fingerprint still populated so the agent
        # can correlate with ping
        assert "current_version" in result
        assert "current_fingerprint" in result

    def test_ping_unaffected_by_broken_changelog(self, ctx, monkeypatch):
        """Blast-radius (b): ping doesn't read changelog state — but pin this
        invariant explicitly so a future refactor doesn't quietly couple them."""
        from cited_mcp.tools import changelog as cl

        monkeypatch.setattr(cl, "_CHANGELOG", {"versions": []})
        monkeypatch.setattr(
            cl,
            "_CHANGELOG_LOAD_ERROR",
            "changelog YAML parse error: ParserError",
        )
        result = run(ping(ctx))
        assert result["status"] == "ok"
        assert result["server"] == "cited-mcp"
        assert "tools_fingerprint" in result


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


class TestUpgradePlan:
    """Wrap-logic for upgrade_plan: tools_unlocked + pending_action."""

    @pytest.fixture
    def upgrade_ctx(self, ctx):
        """Authenticated context with a mocked ctx.session for notifications."""
        from unittest.mock import AsyncMock, MagicMock
        session = MagicMock()
        session.send_tool_list_changed = AsyncMock()
        ctx.session = session  # FakeContext is a dataclass — assign attribute
        return ctx

    @staticmethod
    def _stub_get_post(client, *, current_tier: str, backend_response: dict):
        """Wire client.get(/auth/me) and client.post(/billing/agent-upgrade)."""
        def _get(path, *args, **kwargs):
            if path.endswith("/auth/me"):
                return {"subscription_tier": current_tier}
            raise AssertionError(f"unexpected GET {path!r}")
        def _post(path, *args, **kwargs):
            if path.endswith("/billing/agent-upgrade"):
                return backend_response
            raise AssertionError(f"unexpected POST {path!r}")
        client.get.side_effect = _get
        client.post.side_effect = _post

    # --- branch (a): already_on_plan -------------------------------------

    def test_already_on_plan_no_tools_unlocked_no_pending_action(self, upgrade_ctx):
        client = upgrade_ctx.request_context.lifespan_context.client
        self._stub_get_post(
            client,
            current_tier="scale",
            backend_response={
                "success": True,
                "tier": "scale",
                "action": "already_on_plan",
                "checkout_url": None,
                "message": "Already on the Scale plan.",
            },
        )

        result = run(upgrade_plan(upgrade_ctx, target_tier="scale"))

        assert result["success"] is True
        assert result["tier"] == "scale"
        assert result["action"] == "already_on_plan"
        assert result["tools_unlocked"] == []
        # Always-present, null when no action pending.
        assert "pending_action" in result
        assert result["pending_action"] is None
        # Notification should NOT be sent for no-op upgrades.
        upgrade_ctx.session.send_tool_list_changed.assert_not_called()

    # --- branch (b): upgraded (immediate) --------------------------------

    def test_upgraded_returns_unlocked_tools_and_reconnect_pending_action(
        self, upgrade_ctx
    ):
        client = upgrade_ctx.request_context.lifespan_context.client
        self._stub_get_post(
            client,
            current_tier="growth",
            backend_response={
                "success": True,
                "tier": "scale",
                "action": "upgraded",
                "checkout_url": None,
                "message": "Upgraded to Scale plan.",
            },
        )

        result = run(upgrade_plan(upgrade_ctx, target_tier="scale"))

        assert result["action"] == "upgraded"
        assert result["tier"] == "scale"
        # tools_unlocked must be a non-empty list of {name, description}
        assert isinstance(result["tools_unlocked"], list)
        assert len(result["tools_unlocked"]) > 0
        names = {entry["name"] for entry in result["tools_unlocked"]}
        # Sanity-check a few canonical scale-tier tools
        assert "start_solution" in names
        assert "start_solutions_batch" in names
        assert "get_audit_question_detail" in names
        # Each entry has both name and description fields
        for entry in result["tools_unlocked"]:
            assert "name" in entry and isinstance(entry["name"], str)
            assert "description" in entry and isinstance(entry["description"], str)
        # pending_action points at disconnect/reconnect
        assert result["pending_action"] is not None
        assert "isconnect and reconnect" in result["pending_action"]
        # Notification was emitted (best-effort)
        upgrade_ctx.session.send_tool_list_changed.assert_awaited_once()

    def test_upgraded_pro_unlocks_pro_tier_tools(self, upgrade_ctx):
        client = upgrade_ctx.request_context.lifespan_context.client
        self._stub_get_post(
            client,
            current_tier="scale",
            backend_response={
                "success": True,
                "tier": "pro",
                "action": "upgraded",
                "checkout_url": None,
                "message": "Upgraded to Pro plan. Your card on file will be charged the prorated difference.",  # noqa: E501
            },
        )
        result = run(upgrade_plan(upgrade_ctx, target_tier="pro"))
        names = {entry["name"] for entry in result["tools_unlocked"]}
        # Pro-only tools should appear; scale tools should NOT (we already had those)
        assert "get_business_facts" in names
        assert "buyer_fit_query" in names
        assert "start_solution" not in names

    # --- branch (c): checkout_required -----------------------------------

    def test_checkout_required_no_tools_unlocked_pending_action_has_url(
        self, upgrade_ctx
    ):
        client = upgrade_ctx.request_context.lifespan_context.client
        checkout_url = "https://checkout.stripe.com/c/pay/cs_test_abc123"
        self._stub_get_post(
            client,
            current_tier="growth",
            backend_response={
                "success": False,
                "tier": "scale",
                "action": "checkout_required",
                "checkout_url": checkout_url,
                "message": "No payment method on file. Please complete checkout...",
            },
        )

        result = run(upgrade_plan(upgrade_ctx, target_tier="scale"))

        assert result["action"] == "checkout_required"
        assert result["checkout_url"] == checkout_url
        # Upgrade hasn't taken effect — no tools unlocked yet
        assert result["tools_unlocked"] == []
        # pending_action must surface the checkout URL so the agent can show it
        assert result["pending_action"] is not None
        assert checkout_url in result["pending_action"]
        # Notification should NOT fire — nothing to refresh yet
        upgrade_ctx.session.send_tool_list_changed.assert_not_called()

    # --- notification swallowing ----------------------------------------

    def test_notification_failure_does_not_break_upgrade(self, upgrade_ctx, caplog):
        from unittest.mock import AsyncMock
        upgrade_ctx.session.send_tool_list_changed = AsyncMock(
            side_effect=RuntimeError("transport closed")
        )
        client = upgrade_ctx.request_context.lifespan_context.client
        self._stub_get_post(
            client,
            current_tier="growth",
            backend_response={
                "success": True,
                "tier": "scale",
                "action": "upgraded",
                "checkout_url": None,
                "message": "Upgraded to Scale plan.",
            },
        )
        import logging
        with caplog.at_level(logging.INFO, logger="cited_mcp.usage"):
            result = run(upgrade_plan(upgrade_ctx, target_tier="scale"))

        # Upgrade response is intact even though the notification raised.
        assert result["action"] == "upgraded"
        assert len(result["tools_unlocked"]) > 0
        # Structured log line emitted with tool, user, error type.
        joined = "\n".join(rec.message for rec in caplog.records)
        assert "tools_list_changed_send_failed" in joined
        assert "upgrade_plan" in joined
        assert "RuntimeError" in joined

    # --- field always-present invariant ---------------------------------

    @pytest.mark.parametrize(
        "backend_response,current_tier",
        [
            (
                {
                    "success": True,
                    "tier": "scale",
                    "action": "already_on_plan",
                    "checkout_url": None,
                    "message": "Already on the Scale plan.",
                },
                "scale",
            ),
            (
                {
                    "success": True,
                    "tier": "scale",
                    "action": "upgraded",
                    "checkout_url": None,
                    "message": "Upgraded to Scale plan.",
                },
                "growth",
            ),
            (
                {
                    "success": False,
                    "tier": "scale",
                    "action": "checkout_required",
                    "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_abc",
                    "message": "No payment method on file...",
                },
                "growth",
            ),
        ],
    )
    def test_response_always_includes_tools_unlocked_and_pending_action(
        self, upgrade_ctx, backend_response, current_tier
    ):
        client = upgrade_ctx.request_context.lifespan_context.client
        self._stub_get_post(
            client,
            current_tier=current_tier,
            backend_response=backend_response,
        )
        result = run(upgrade_plan(upgrade_ctx, target_tier=backend_response["tier"]))
        assert "tools_unlocked" in result
        assert "pending_action" in result
        assert isinstance(result["tools_unlocked"], list)
        assert result["pending_action"] is None or isinstance(
            result["pending_action"], str
        )


class TestCitedToolManager:
    """Custom ToolManager: structured payload on unknown tool names."""

    def _make_manager(self):
        """Build a CitedToolManager with one synthetic registered tool."""
        from cited_mcp.tool_manager import CitedToolManager

        async def _known() -> str:
            """A test tool used as the 'happy path' for the manager."""
            return "ran"

        mgr = CitedToolManager()
        mgr.add_tool(_known, name="known_tool")
        return mgr

    def test_known_tool_dispatches_normally(self):
        mgr = self._make_manager()
        result = run(mgr.call_tool("known_tool", {}))
        assert result == "ran"

    def test_unknown_tool_returns_structured_payload(self):
        mgr = self._make_manager()
        result = run(mgr.call_tool("nonexistent_tool", {}))
        assert isinstance(result, dict)
        assert result["error"] is True
        assert result["error_type"] == "tool_unavailable"
        assert "nonexistent_tool" in result["message"]
        assert "whats_new" in result["message"]
        assert "ping" in result["message"]
        assert "tools_fingerprint" in result["message"]

    def test_unknown_tool_includes_request_id(self):
        mgr = self._make_manager()
        result = run(mgr.call_tool("does_not_exist", {}))
        assert "_request_id" in result
        rid = result["_request_id"]
        assert isinstance(rid, str) and len(rid) == 12
        int(rid, 16)

    def test_unknown_tool_request_ids_unique(self):
        mgr = self._make_manager()
        a = run(mgr.call_tool("missing", {}))["_request_id"]
        b = run(mgr.call_tool("missing", {}))["_request_id"]
        assert a != b

    def test_unknown_tool_does_not_raise(self):
        """The whole point of the subclass: never raise on unknown tools."""
        mgr = self._make_manager()
        result = run(mgr.call_tool("anything", {}))
        assert result["error_type"] == "tool_unavailable"

    def test_unknown_tool_logs_structured_event(self, caplog):
        import logging

        mgr = self._make_manager()
        with caplog.at_level(logging.INFO, logger="cited_mcp.usage"):
            run(mgr.call_tool("ghost_tool", {}))
        joined = "\n".join(rec.message for rec in caplog.records)
        assert "tool_unavailable" in joined
        assert "ghost_tool" in joined

    def test_install_swaps_manager_idempotently(self):
        """install() replaces ToolManager but preserves registered tools."""
        from cited_mcp.server import mcp as registered_mcp
        from cited_mcp.tool_manager import CitedToolManager, install

        # Already a CitedToolManager (installed in create_stdio_server)
        assert isinstance(registered_mcp._tool_manager, CitedToolManager)

        before_tools = sorted(
            t.name for t in registered_mcp._tool_manager.list_tools()
        )
        install(registered_mcp)  # idempotent
        after_tools = sorted(
            t.name for t in registered_mcp._tool_manager.list_tools()
        )
        assert before_tools == after_tools

    def test_live_server_returns_structured_payload_for_unknown_tool(self):
        """End-to-end: hit the LIVE registered server with a bogus tool name."""
        from cited_mcp.server import mcp as registered_mcp

        result = run(
            registered_mcp._tool_manager.call_tool(
                "definitely_not_a_real_tool", {}
            )
        )
        assert result["error"] is True
        assert result["error_type"] == "tool_unavailable"
        assert "definitely_not_a_real_tool" in result["message"]
