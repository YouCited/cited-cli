"""Tests for per-plan tool gating."""
from __future__ import annotations

from cited_mcp.plan_gating import (
    get_tier_rank,
    is_tool_allowed,
    required_tier_for_tool,
    tools_for_tier,
    upgrade_message,
)


class TestTierRank:
    def test_known_tiers(self):
        assert get_tier_rank("free") == 0
        assert get_tier_rank("growth") == 1
        assert get_tier_rank("scale") == 2
        assert get_tier_rank("pro") == 3
        assert get_tier_rank("enterprise") == 3  # legacy, same as pro

    def test_none_and_unknown(self):
        assert get_tier_rank(None) == 0
        assert get_tier_rank("unknown") == 0

    def test_case_insensitive(self):
        assert get_tier_rank("Growth") == 1
        assert get_tier_rank("PRO") == 3


class TestIsToolAllowed:
    # Base tools — available to all tiers
    def test_list_businesses_free(self):
        assert is_tool_allowed("list_businesses", "free") is True

    def test_list_businesses_growth(self):
        assert is_tool_allowed("list_businesses", "growth") is True

    def test_start_audit_free(self):
        assert is_tool_allowed("start_audit", "free") is True

    def test_auth_tools_always_allowed(self):
        assert is_tool_allowed("check_auth_status", None) is True
        assert is_tool_allowed("login", "free") is True
        assert is_tool_allowed("logout", "growth") is True

    # Scale-gated tools
    def test_create_business_growth_blocked(self):
        assert is_tool_allowed("create_business", "growth") is False

    def test_create_business_scale_allowed(self):
        assert is_tool_allowed("create_business", "scale") is True

    def test_create_business_pro_allowed(self):
        assert is_tool_allowed("create_business", "pro") is True

    def test_start_solution_growth_blocked(self):
        assert is_tool_allowed("start_solution", "growth") is False

    def test_start_solution_scale_allowed(self):
        assert is_tool_allowed("start_solution", "scale") is True

    def test_delete_business_free_blocked(self):
        assert is_tool_allowed("delete_business", "free") is False

    # Pro-gated tools
    def test_get_usage_stats_scale_blocked(self):
        assert is_tool_allowed("get_usage_stats", "scale") is False

    def test_get_usage_stats_pro_allowed(self):
        assert is_tool_allowed("get_usage_stats", "pro") is True

    def test_get_usage_stats_enterprise_allowed(self):
        assert is_tool_allowed("get_usage_stats", "enterprise") is True


class TestRequiredTier:
    def test_ungated_tool(self):
        assert required_tier_for_tool("list_businesses") is None

    def test_scale_tool(self):
        assert required_tier_for_tool("create_business") == "scale"

    def test_pro_tool(self):
        assert required_tier_for_tool("get_usage_stats") == "pro"


class TestUpgradeMessage:
    def test_message_structure(self):
        msg = upgrade_message("create_business", "growth")
        assert msg["error"] is True
        assert "Scale" in msg["message"]
        assert "Growth" in msg["message"]
        assert msg["upgrade_url"] == "https://app.youcited.com/settings/billing"
        assert msg["required_tier"] == "scale"
        assert msg["current_tier"] == "growth"

    def test_none_tier_shows_free(self):
        msg = upgrade_message("create_business", None)
        assert msg["current_tier"] == "free"
        assert "Free" in msg["message"]


class TestToolsForTier:
    def test_free_gets_base_tools(self):
        tools = tools_for_tier("free")
        assert "list_businesses" in tools
        assert "start_audit" in tools
        assert "create_business" not in tools
        assert "start_solution" not in tools

    def test_growth_same_as_free(self):
        assert tools_for_tier("growth") == tools_for_tier("free")

    def test_scale_includes_scale_tools(self):
        tools = tools_for_tier("scale")
        assert "create_business" in tools
        assert "start_solution" in tools
        assert "get_usage_stats" not in tools

    def test_pro_includes_everything(self):
        tools = tools_for_tier("pro")
        assert "create_business" in tools
        assert "start_solution" in tools
        assert "get_usage_stats" in tools

    def test_enterprise_same_as_pro(self):
        assert tools_for_tier("enterprise") == tools_for_tier("pro")

    def test_pro_has_all_tools(self):
        # All tools should be available to pro. Bump this count whenever a tool
        # is added/removed to/from any tier set.
        tools = tools_for_tier("pro")
        assert len(tools) == 55

    def test_all_registered_tools_are_in_tier_sets(self):
        """Every registered MCP tool must appear in exactly one tier set."""
        from cited_mcp.server import create_stdio_server

        server = create_stdio_server()
        registered = {t.name for t in server._tool_manager.list_tools()}
        in_tiers = tools_for_tier("pro")  # pro gets everything
        missing = registered - in_tiers
        assert missing == set(), f"Tools registered but not in any tier set: {missing}"
        extra = in_tiers - registered
        assert extra == set(), f"Tools in tier sets but not registered: {extra}"
