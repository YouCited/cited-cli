"""Feature parity test: CLI commands vs MCP tools.

This test fails when a CLI command has no MCP equivalent or vice versa,
preventing feature drift between the two interfaces. When adding a new
feature, add it to BOTH the CLI and MCP, then update the exceptions
below if the gap is intentional.
"""
from __future__ import annotations

import pytest


# Intentional gaps — features that only make sense in one interface.
# Each entry must have a comment explaining WHY it's CLI-only or MCP-only.
CLI_ONLY = {
    "auth token",       # Raw JWT export — only useful for CLI scripting/piping
    "auth register",    # Account creation — one-time flow, not suited for MCP
    "register",         # Top-level alias for auth register
    "config set",       # Local config management — no equivalent in MCP
    "config get",       # Local config management
    "config show",      # Local config management
    "config environments",  # Local config management
    "mcp serve",        # Starts the MCP server itself — meta, not a tool
    "job watch",        # Live Rich progress bar — interactive terminal only
    "version",          # CLI version display — not meaningful for MCP
}

MCP_ONLY = {
    "ping",                     # Lightweight readiness check — CLI users run `cited status` instead
    "get_pricing",              # Agent payment discovery — CLI users visit billing page
    "upgrade_plan",             # Agent plan upgrade — CLI users visit billing page
    "whats_new",                # Tool-surface diff for stale MCP-client caches — CLI doesn't have a tool cache
    "get_usage_stats",          # Aggregated stats — CLI uses auth status + business list
    "get_job_status",           # MCP probes types; CLI uses job watch (live polling)
    "get_audit_question_detail",  # Drill-down from summary — CLI uses audit result (full)
    "start_solutions_batch",    # Bulk operation — CLI users call solution start in a loop
}


def _get_cli_commands() -> set[str]:
    """Extract all CLI commands as 'group subcommand' strings."""
    from cited_cli.app import app
    import typer

    commands: set[str] = set()

    def _walk(typer_app: typer.Typer, prefix: str = "") -> None:
        # Get registered commands
        for command in typer_app.registered_commands:
            name = command.name or command.callback.__name__
            full = f"{prefix} {name}".strip() if prefix else name
            commands.add(full)

        # Get registered sub-apps (groups)
        for group in typer_app.registered_groups:
            sub_app = group.typer_instance
            group_name = group.name or ""
            full_prefix = f"{prefix} {group_name}".strip() if prefix else group_name
            if sub_app:
                _walk(sub_app, full_prefix)

    _walk(app)
    return commands


def _get_mcp_tools() -> set[str]:
    """Get all registered MCP tool names."""
    from cited_mcp.server import create_stdio_server

    server = create_stdio_server()
    return {t.name for t in server._tool_manager.list_tools()}


# Mapping from CLI command patterns to their MCP tool equivalents.
# This is the source of truth for feature parity.
_CLI_TO_MCP: dict[str, str | list[str]] = {
    # Auth
    "login": "login",
    "logout": "logout",
    "auth login": "login",
    "auth logout": "logout",
    "auth status": "check_auth_status",
    # Business
    "business list": "list_businesses",
    "business get": "get_business",
    "business create": "create_business",
    "business update": "update_business",
    "business delete": "delete_business",
    "business health": "get_health_scores",
    "business crawl": "crawl_business",
    # Audit templates
    "audit template list": "list_audit_templates",
    "audit template get": "get_audit_template",
    "audit template create": "create_audit_template",
    "audit template update": "update_audit_template",
    "audit template delete": "delete_audit_template",
    # Audits
    "audit start": "start_audit",
    "audit status": "get_audit_status",
    "audit result": "get_audit_result",
    "audit list": "list_audits",
    "audit export": "export_audit",
    # Recommendations
    "recommend start": "start_recommendation",
    "recommend status": "get_recommendation_status",
    "recommend result": "get_recommendation_result",
    "recommend insights": "get_recommendation_insights",
    "recommend list": "list_recommendations",
    # Solutions
    "solution start": "start_solution",
    "solution status": "get_solution_status",
    "solution result": "get_solution_result",
    "solution list": "list_solutions",
    # Jobs
    "job cancel": "cancel_job",
    # HQ
    "hq": "get_business_hq",
    # Analytics
    "analytics compare": "compare_audits",
    "analytics trends": "get_analytics_trends",
    "analytics summary": "get_analytics_summary",
    # Agent API
    "agent facts": "get_business_facts",
    "agent claims": "get_business_claims",
    "agent comparison": "get_competitive_comparison",
    "agent semantic-health": "get_semantic_health",
    "agent buyer-fit": "buyer_fit_query",
    # Status (top-level)
    "status": "check_auth_status",
}


@pytest.fixture
def _mcp_available():
    try:
        import mcp  # noqa: F401
    except ImportError:
        pytest.skip("mcp not installed")


@pytest.mark.usefixtures("_mcp_available")
def test_every_cli_command_has_mcp_equivalent():
    """Every CLI command should have an MCP tool, or be in CLI_ONLY."""
    cli_commands = _get_cli_commands()
    unmapped: list[str] = []
    for cmd in sorted(cli_commands):
        if cmd in CLI_ONLY:
            continue
        if cmd not in _CLI_TO_MCP:
            unmapped.append(cmd)
    assert unmapped == [], (
        f"CLI commands without MCP equivalents (add to _CLI_TO_MCP or CLI_ONLY): {unmapped}"
    )


@pytest.mark.usefixtures("_mcp_available")
def test_every_mcp_tool_has_cli_equivalent():
    """Every MCP tool should map from a CLI command, or be in MCP_ONLY."""
    mcp_tools = _get_mcp_tools()
    mapped_tools = set()
    for target in _CLI_TO_MCP.values():
        if isinstance(target, list):
            mapped_tools.update(target)
        else:
            mapped_tools.add(target)
    mapped_tools |= MCP_ONLY

    unmapped = mcp_tools - mapped_tools
    assert unmapped == set(), (
        f"MCP tools without CLI equivalents (add to _CLI_TO_MCP or MCP_ONLY): {unmapped}"
    )


@pytest.mark.usefixtures("_mcp_available")
def test_mapped_mcp_tools_actually_exist():
    """All MCP tools referenced in the mapping must be registered."""
    mcp_tools = _get_mcp_tools()
    for cli_cmd, mcp_tool in _CLI_TO_MCP.items():
        tools = [mcp_tool] if isinstance(mcp_tool, str) else mcp_tool
        for t in tools:
            assert t in mcp_tools, (
                f"CLI '{cli_cmd}' maps to MCP tool '{t}' which is not registered"
            )
