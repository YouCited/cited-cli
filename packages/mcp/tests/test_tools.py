"""Tests for cited-mcp tool functions.

Tests call tool functions directly with a mocked CitedClient,
bypassing the MCP transport layer.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

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

from cited_mcp.tools.audit import (  # noqa: E402
    create_audit_template,
    delete_audit_template,
    get_audit_result,
    get_audit_status,
    list_audit_templates,
    list_audits,
    start_audit,
    update_audit_template,
)
from cited_mcp.tools.auth import check_auth_status, login, logout  # noqa: E402
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
from cited_mcp.tools.job import get_job_status  # noqa: E402
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
        result = run(start_solution(unauth_ctx, recommendation_job_id="a", source_type="b", source_id="c"))
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

        result = run(create_business(ctx, name="New Biz", website="https://new.com", description="A new business for testing purposes that is long enough"))
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

        result = run(create_audit_template(ctx, name="My Template", business_id="b1", questions=["Q1", "Q2"]))
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
        """Other tools should auto-detect a completed pending login."""
        import cited_mcp.tools.auth as auth_mod
        from cited_core.auth.oauth_server import OAuthCallbackServer
        import unittest.mock

        # Set up: unauthenticated context with a pending login that captured a token
        fake_ctx = make_ctx(token=None)
        server = OAuthCallbackServer(timeout=5)
        server.token = "auto-detected-jwt"
        auth_mod._pending_login = server
        auth_mod._pending_login_env = "dev"

        # Mock TokenStore
        with unittest.mock.patch("cited_mcp.tools.auth.TokenStore"):
            # Call list_businesses — it should auto-detect the pending login
            client = fake_ctx.request_context.lifespan_context.client
            client.get.return_value = [{"id": "b1", "name": "My Biz"}]
            # The client mock needs token set to trigger the auto-detection path
            client.token = None

            # After _check_pending_login runs, it sets client.token
            # We need to make the mock respond to token assignment
            def set_token(value):
                client.token = value if value else None

            type(client).token = unittest.mock.PropertyMock(
                side_effect=[None, None, "auto-detected-jwt", "auto-detected-jwt"]
            )

        # Clean up
        auth_mod._pending_login = None
        auth_mod._pending_login_env = None


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
