"""Feature parity: every CLI command runs a tool, and every tool has a command.

The tools are defined once, in the Cited API (``cited_core/tools.json`` is the
bundled snapshot); cited-mcp lists exactly those plus its local login/logout.
When a tool is added, add its CLI command and map it here.
"""

from __future__ import annotations

from cited_core.tools import bundled_manifest, tool_names

# Commands with no tool behind them, and why.
CLI_ONLY = {
    "auth token",  # Prints the raw session token for scripts
    "auth register",  # Account creation in a browser or with a password
    "register",  # Top-level alias for auth register
    "config set",  # Local config
    "config get",  # Local config
    "config show",  # Local config
    "config environments",  # Local config
    "mcp serve",  # Starts the MCP server itself
    "version",  # CLI version
    "agent setup",  # Writes MCP config for AI clients on this machine
    "tools list",  # The tool list itself
    "tools call",  # Calls any tool by name
}

# CLI command -> the tool it runs.
CLI_TO_TOOL: dict[str, str] = {
    "login": "login",
    "logout": "logout",
    "auth login": "login",
    "auth logout": "logout",
    "status": "account_status",
    "auth status": "account_status",
    "audit free": "free_audit",
    "agent signup": "agent_signup",
    "credits buy": "buy_credits",
    "business setup": "setup_business",
    "business get": "get_business",
    "business brief": "get_agent_brief",
    "audit questions": "draft_questions",
    "audit quote": "quote_audit",
    "audit run": "run_audit",
    "audit get": "get_audit",
    "audit compare": "compare_audits",
    "audit schedule": "schedule_recheck",
    "recommend list": "get_recommendations",
    "recommend set": "update_recommendation",
    "fix generate": "generate_fixes",
    "fix list": "get_fixes",
    "fix get": "get_fixes",
    "fix done": "update_fix",
    "fix undo": "update_fix",
    "fix verify": "update_fix",
    "docs search": "search_docs",
    "docs get": "search_docs",
}


def _cli_commands() -> set[str]:
    import typer

    from cited_cli.app import app

    commands: set[str] = set()

    def _walk(typer_app: typer.Typer, prefix: str = "") -> None:
        for command in typer_app.registered_commands:
            name = command.name or (command.callback.__name__ if command.callback else "")
            commands.add(f"{prefix} {name}".strip())
        for group in typer_app.registered_groups:
            if group.typer_instance:
                _walk(group.typer_instance, f"{prefix} {group.name or ''}".strip())

    _walk(app)
    return commands


def _mcp_tools() -> set[str]:
    from cited_core.api.client import CitedClient
    from cited_mcp.server import CitedSession, tool_list

    session = CitedSession(
        client=CitedClient("http://localhost"), env="dev", api_url="http://localhost",
        manifest=bundled_manifest(),
    )
    return {t.name for t in tool_list(session)}


def test_every_cli_command_runs_a_tool():
    unmapped = sorted(c for c in _cli_commands() if c not in CLI_ONLY and c not in CLI_TO_TOOL)
    assert unmapped == [], f"Map these to a tool in CLI_TO_TOOL, or add to CLI_ONLY: {unmapped}"


def test_mapped_commands_exist():
    assert set(CLI_TO_TOOL) - _cli_commands() == set()


def test_every_tool_has_a_cli_command():
    missing = _mcp_tools() - set(CLI_TO_TOOL.values())
    assert missing == set(), f"Tools without a CLI command: {missing}"


def test_cli_maps_only_to_real_tools():
    assert set(CLI_TO_TOOL.values()) <= _mcp_tools()


def test_mcp_lists_the_shared_tools_plus_login_and_logout():
    assert _mcp_tools() == {*tool_names(), "login", "logout"}
