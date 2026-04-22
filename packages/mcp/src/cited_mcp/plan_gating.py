"""Per-plan tool gating for the Cited MCP server.

Defines which tools are available at each subscription tier and provides
helpers to filter the tool list and return upgrade messages.

Plan tiers (from backend SubscriptionTierEnum):
  - free      (legacy, deprecated)
  - growth    (entry tier)
  - scale     (mid tier)
  - pro       (top tier)
  - enterprise (legacy, deprecated — treated as pro)
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("cited_mcp.plan_gating")

# ---------------------------------------------------------------------------
# Tool tier mapping
# ---------------------------------------------------------------------------
# Tools not listed here are available to ALL tiers (including free/growth).

# Tools restricted to scale+ tier
_SCALE_TOOLS: set[str] = {
    "create_business",
    "update_business",
    "delete_business",
    "create_audit_template",
    "update_audit_template",
    "delete_audit_template",
    "start_solution",
    "start_solutions_batch",
    "get_solution_status",
    "get_solution_result",
    "list_solutions",
    "export_audit",
    "cancel_job",
}

# Tools restricted to pro+ tier
_PRO_TOOLS: set[str] = {
    "get_usage_stats",
    "get_business_facts",
    "get_business_claims",
    "get_competitive_comparison",
    "get_semantic_health",
    "buyer_fit_query",
    "get_business_hq",
    "get_analytics_trends",
    "get_analytics_summary",
    "compare_audits",
}

# Tier hierarchy (higher index = more access)
_TIER_RANK: dict[str, int] = {
    "free": 0,
    "growth": 1,
    "scale": 2,
    "pro": 3,
    "enterprise": 3,  # legacy — same as pro
}

# Minimum tier required for each gated tool
_TOOL_MIN_TIER: dict[str, str] = {}
for _tool in _SCALE_TOOLS:
    _TOOL_MIN_TIER[_tool] = "scale"
for _tool in _PRO_TOOLS:
    _TOOL_MIN_TIER[_tool] = "pro"


def get_tier_rank(tier: str | None) -> int:
    """Return the numeric rank for a tier name."""
    if not tier:
        return 0
    return _TIER_RANK.get(tier.lower(), 0)


def is_tool_allowed(tool_name: str, user_tier: str | None) -> bool:
    """Check if a tool is available for the given subscription tier."""
    min_tier = _TOOL_MIN_TIER.get(tool_name)
    if min_tier is None:
        return True  # Tool is available to all tiers
    return get_tier_rank(user_tier) >= get_tier_rank(min_tier)


def required_tier_for_tool(tool_name: str) -> str | None:
    """Return the minimum tier required for a tool, or None if unrestricted."""
    return _TOOL_MIN_TIER.get(tool_name)


def upgrade_message(tool_name: str, current_tier: str | None) -> dict[str, Any]:
    """Return a structured error message for a gated tool."""
    min_tier = _TOOL_MIN_TIER.get(tool_name, "growth")
    return {
        "error": True,
        "message": (
            f"The '{tool_name}' tool requires the {min_tier.title()} plan or higher. "
            f"Your current plan is {(current_tier or 'free').title()}."
        ),
        "upgrade_url": "https://app.youcited.com/settings/billing",
        "hint": (
            f"Upgrade to {min_tier.title()} at https://app.youcited.com/settings/billing "
            f"to unlock this feature."
        ),
        "required_tier": min_tier,
        "current_tier": current_tier or "free",
    }


# ---------------------------------------------------------------------------
# Tools available per tier (for documentation / tool list filtering)
# ---------------------------------------------------------------------------

# All base tools (available to every tier including free/growth)
_BASE_TOOLS: set[str] = {
    "ping",
    "check_auth_status",
    "login",
    "logout",
    "list_businesses",
    "get_business",
    "crawl_business",
    "get_health_scores",
    "list_audit_templates",
    "get_audit_template",
    "start_audit",
    "get_audit_status",
    "get_audit_result",
    "list_audits",
    "start_recommendation",
    "get_recommendation_status",
    "get_recommendation_result",
    "get_recommendation_insights",
    "list_recommendations",
    "get_job_status",
}

# Verify all registered tools are accounted for in the tier sets.
# This is checked by the drift detection test in test_plan_gating.py.


def tools_for_tier(tier: str | None) -> set[str]:
    """Return the set of tool names available for a given tier."""
    rank = get_tier_rank(tier)
    tools = set(_BASE_TOOLS)
    if rank >= get_tier_rank("scale"):
        tools |= _SCALE_TOOLS
    if rank >= get_tier_rank("pro"):
        tools |= _PRO_TOOLS
    return tools
