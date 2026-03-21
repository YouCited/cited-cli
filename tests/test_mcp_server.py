from __future__ import annotations

import pytest


@pytest.fixture
def _mcp_available():
    try:
        import mcp  # noqa: F401
    except ImportError:
        pytest.skip("mcp not installed")


EXPECTED_TOOLS = [
    "check_auth_status",
    "login",
    "list_businesses",
    "get_business",
    "create_business",
    "update_business",
    "delete_business",
    "crawl_business",
    "get_health_scores",
    "list_audit_templates",
    "get_audit_template",
    "create_audit_template",
    "update_audit_template",
    "delete_audit_template",
    "start_audit",
    "get_audit_status",
    "get_audit_result",
    "list_audits",
    "start_recommendation",
    "get_recommendation_status",
    "get_recommendation_result",
    "get_recommendation_insights",
    "list_recommendations",
    "start_solution",
    "get_solution_status",
    "get_solution_result",
    "list_solutions",
    "get_job_status",
]


@pytest.mark.usefixtures("_mcp_available")
def test_all_tools_registered():
    from cited_mcp.server import mcp

    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert len(tool_names) == len(EXPECTED_TOOLS)
    for name in EXPECTED_TOOLS:
        assert name in tool_names, f"Missing tool: {name}"


@pytest.mark.usefixtures("_mcp_available")
def test_all_tools_have_descriptions():
    from cited_mcp.server import mcp

    for tool in mcp._tool_manager.list_tools():
        assert tool.description, f"Tool {tool.name} has no description"
