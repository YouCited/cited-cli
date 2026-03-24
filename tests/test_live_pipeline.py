from __future__ import annotations

import asyncio
import os
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from cited_core.api.client import CitedClient
from cited_core.auth.store import TokenStore
from cited_mcp.context import CitedContext

DEV_API = "https://dev.youcited.com"

pytestmark = pytest.mark.live


def _make_cited_ctx(token: str) -> CitedContext:
    client = CitedClient(base_url=DEV_API, token=token)
    return CitedContext(client=client, env="dev", api_url=DEV_API)


def _make_mcp_ctx(cited_ctx: CitedContext) -> Any:
    ctx = MagicMock()
    ctx.request_context.lifespan_context = cited_ctx
    return ctx


def _run(coro: Any) -> Any:
    return asyncio.get_event_loop().run_until_complete(coro)


def _ensure_mcp_initialized() -> None:
    """Ensure the MCP server instance exists so @mcp.tool() decorators work."""
    import cited_mcp.server as _mcp_server

    if _mcp_server.mcp is None:
        from mcp.server.fastmcp import FastMCP

        _mcp_server.mcp = FastMCP("cited-test")
        _mcp_server.register_tools()


def _get_token() -> str | None:
    token = os.environ.get("CITED_TOKEN")
    if token:
        return token
    try:
        return TokenStore().get_token("dev")
    except Exception:
        return None


def _poll_until_complete(
    cited_ctx: CitedContext,
    job_type: str,
    job_id: str,
    timeout: int = 300,
) -> dict[str, Any]:
    """Poll job status until completed or timeout."""
    from cited_core.api import endpoints

    endpoint_map = {
        "audit": endpoints.AUDIT_STATUS,
        "recommendation": endpoints.RECOMMEND_STATUS,
        "solution": endpoints.SOLUTION_STATUS,
    }
    endpoint = endpoint_map[job_type].format(job_id=job_id)
    start = time.time()
    while time.time() - start < timeout:
        result = cited_ctx.client.get(endpoint)
        status = result.get("status")
        if status == "completed":
            return result
        if status in ("failed", "cancelled"):
            pytest.fail(f"{job_type} job {job_id} {status}: {result}")
        time.sleep(5)
    pytest.fail(f"{job_type} job {job_id} timed out after {timeout}s")


def test_full_live_pipeline():
    """Full customer journey against the live dev API."""
    _ensure_mcp_initialized()

    from cited_mcp.tools.auth import check_auth_status
    from cited_mcp.tools.audit import create_audit_template, start_audit, get_audit_result
    from cited_mcp.tools.business import (
        create_business,
        delete_business,
        get_health_scores,
    )
    from cited_mcp.tools.recommend import (
        get_recommendation_insights,
        start_recommendation,
    )
    from cited_mcp.tools.solution import get_solution_result, start_solution

    token = _get_token()
    if not token:
        pytest.skip("No dev auth token available (set CITED_TOKEN or login to dev)")

    cited_ctx = _make_cited_ctx(token)
    ctx = _make_mcp_ctx(cited_ctx)
    business_id = None
    template_id = None

    try:
        # 1. Check auth status
        auth = _run(check_auth_status(ctx))
        assert "email" in auth, f"Auth check failed: {auth}"
        print(f"\n  Auth: {auth['email']}")

        # 2. Create a test business
        biz = _run(
            create_business(
                ctx,
                "MCP Integration Test Bakery",
                "https://sunrisebakery.com",
                "Integration test business for MCP pipeline validation. "
                "Artisan bakery in Austin Texas specializing in sourdough and pastries.",
                "restaurant",
            )
        )
        assert "id" in biz, f"Business create failed: {biz}"
        business_id = biz["id"]
        print(f"  Business: {business_id}")

        # 3. Get health scores (baseline, may be empty)
        scores = _run(get_health_scores(ctx, business_id))
        assert not isinstance(scores, dict) or not scores.get("error"), f"Health scores failed: {scores}"
        print(f"  Health scores: {type(scores).__name__}")

        # 4. Create audit template
        template = _run(
            create_audit_template(
                ctx,
                "MCP Test Audit",
                business_id,
                "Integration test audit template",
                [
                    "What is the best bakery in Austin Texas?",
                    "Where can I find artisan sourdough bread near me?",
                    "Best wedding cake bakeries in Austin",
                ],
            )
        )
        assert "id" in template, f"Template create failed: {template}"
        template_id = template["id"]
        print(f"  Template: {template_id}")

        # 5. Start audit
        audit = _run(start_audit(ctx, template_id, business_id))
        assert "job_id" in audit, f"Audit start failed: {audit}"
        audit_job_id = audit["job_id"]
        print(f"  Audit job: {audit_job_id}")

        # 6. Poll until audit completes
        print("  Polling audit...", end="", flush=True)
        _poll_until_complete(cited_ctx, "audit", audit_job_id, timeout=300)
        print(" done")

        # 7. Get audit result
        audit_result = _run(get_audit_result(ctx, audit_job_id))
        assert audit_result is not None
        assert not (isinstance(audit_result, dict) and audit_result.get("error"))
        print(f"  Audit result: OK")

        # 8. Start recommendation
        rec = _run(start_recommendation(ctx, audit_job_id))
        assert "job_id" in rec, f"Recommendation start failed: {rec}"
        rec_job_id = rec["job_id"]
        print(f"  Recommendation job: {rec_job_id}")

        # 9. Poll until recommendation completes
        print("  Polling recommendation...", end="", flush=True)
        _poll_until_complete(cited_ctx, "recommendation", rec_job_id, timeout=300)
        print(" done")

        # 10. Get recommendation insights
        insights = _run(get_recommendation_insights(ctx, rec_job_id))
        assert "question_insights" in insights, f"Insights failed: {insights}"
        qi = insights["question_insights"]
        print(f"  Insights: {len(qi)} question insights")

        # Verify annotations are present
        if qi:
            assert "source_type" in qi[0], f"Missing source_type in insight: {qi[0]}"
            assert "source_id" in qi[0], f"Missing source_id in insight: {qi[0]}"

        # 11. Start solution from first question insight (if available)
        if qi:
            sol = _run(
                start_solution(
                    ctx, rec_job_id, qi[0]["source_type"], qi[0]["source_id"]
                )
            )
            assert "job_id" in sol, f"Solution start failed: {sol}"
            sol_job_id = sol["job_id"]
            print(f"  Solution job: {sol_job_id}")

            # 12. Poll until solution completes
            print("  Polling solution...", end="", flush=True)
            _poll_until_complete(cited_ctx, "solution", sol_job_id, timeout=300)
            print(" done")

            # 13. Get solution result
            sol_result = _run(get_solution_result(ctx, sol_job_id))
            assert sol_result is not None
            assert not (isinstance(sol_result, dict) and sol_result.get("error"))
            print(f"  Solution result: OK")

        print("  Pipeline complete!")

    finally:
        # Cleanup: delete business (which cascades to templates, audits, etc.)
        if business_id:
            try:
                _run(delete_business(ctx, business_id))
                print(f"  Cleanup: deleted business {business_id}")
            except Exception as e:
                print(f"  Cleanup warning: failed to delete business {business_id}: {e}")
        cited_ctx.client.close()
