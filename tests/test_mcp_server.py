from __future__ import annotations

import pytest


@pytest.fixture
def _mcp_available():
    try:
        import mcp  # noqa: F401
    except ImportError:
        pytest.skip("mcp not installed")


EXPECTED_TOOLS = [
    # Auth
    "ping",
    "check_auth_status",
    "login",
    "logout",
    # Businesses
    "list_businesses",
    "get_business",
    "create_business",
    "update_business",
    "delete_business",
    "crawl_business",
    "get_health_scores",
    "get_usage_stats",
    # Audit templates
    "list_audit_templates",
    "get_audit_template",
    "create_audit_template",
    "update_audit_template",
    "delete_audit_template",
    # Audits
    "start_audit",
    "get_audit_status",
    "get_audit_result",
    "list_audits",
    "get_audit_question_detail",
    "export_audit",
    # Recommendations
    "start_recommendation",
    "get_recommendation_status",
    "get_recommendation_result",
    "get_recommendation_insights",
    "get_recommendation_insight_detail",
    "list_recommendations",
    "get_recommendation_check_status",
    "validate_recommendation",
    "get_recommendation_validation_latest",
    # Solutions
    "start_solution",
    "start_solutions_batch",
    "get_solution_status",
    "get_solution_result",
    "list_solutions",
    # Jobs
    "get_job_status",
    "cancel_job",
    # HQ
    "get_business_hq",
    # Analytics
    "get_analytics_trends",
    "get_analytics_dashboard",
    "compare_audits",
    # Billing
    "get_pricing",
    "upgrade_plan",
    # Changelog
    "whats_new",
    # Agent API
    "get_business_facts",
    "get_business_claims",
    "get_competitive_comparison",
    "get_semantic_health",
    "buyer_fit_query",
    # Action Plan
    "get_action_plan",
    "get_quick_wins",
    "mark_action_done",
    "dismiss_action",
    "get_action_progress",
]


@pytest.mark.usefixtures("_mcp_available")
def test_all_tools_registered():
    from cited_mcp.server import create_stdio_server

    mcp = create_stdio_server()
    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert len(tool_names) == len(EXPECTED_TOOLS)
    for name in EXPECTED_TOOLS:
        assert name in tool_names, f"Missing tool: {name}"


@pytest.mark.usefixtures("_mcp_available")
def test_all_tools_have_descriptions():
    from cited_mcp.server import create_stdio_server

    mcp = create_stdio_server()
    for tool in mcp._tool_manager.list_tools():
        assert tool.description, f"Tool {tool.name} has no description"
