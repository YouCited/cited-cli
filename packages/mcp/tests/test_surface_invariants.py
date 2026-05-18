"""Surface-invariant tests — catch unintended changes to the MCP tool surface.

These tests don't exercise tool logic. They lock down structural properties
that should change deliberately, not accidentally:

  - The set of registered tool names (snapshot)
  - The mapping of each tool to its plan tier (snapshot)
  - The latest changelog entry's fingerprint matches the live registry's
    compute_tools_fingerprint() result
  - whats_new() returns the expected diff when called with an older
    fingerprint (verifies the changelog cursor works end-to-end)
  - README / SKILL.md tool-count strings match the live registry size

When any of these fail, the message tells you which invariant broke. Update
the snapshot intentionally if the change is desired.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from cited_mcp.plan_gating import required_tier_for_tool
from cited_mcp.server import compute_tools_fingerprint, create_stdio_server

# ─────────────────────────────────────────────────────────────────────────────
# Locations of the artifacts we lock the surface against
# ─────────────────────────────────────────────────────────────────────────────

_PKG_ROOT = Path(__file__).resolve().parent.parent  # packages/mcp/
_CHANGELOG = _PKG_ROOT / "src" / "cited_mcp" / "tool_changelog.yaml"
_README = _PKG_ROOT / "README.md"
_SKILL = _PKG_ROOT / "SKILL.md"


@pytest.fixture(scope="module")
def server():
    """One server instance reused across the module — server boot is the
    expensive bit (~100ms) and these tests are read-only."""
    return create_stdio_server()


@pytest.fixture(scope="module")
def registered_tool_names(server) -> set[str]:
    return {t.name for t in server._tool_manager.list_tools()}


# ─────────────────────────────────────────────────────────────────────────────
# Surface snapshot — the canonical tool name set
# ─────────────────────────────────────────────────────────────────────────────

# Updated for the v0.5.0 surface (PR #23). When adding or removing a tool,
# update this set AND the changelog top entry in one commit.
EXPECTED_TOOLS_V0_5_0: set[str] = {
    # Auth + meta
    "ping",
    "check_auth_status",
    "login",
    "logout",
    "get_pricing",
    "upgrade_plan",
    "whats_new",
    "get_usage_stats",
    # Businesses
    "list_businesses",
    "get_business",
    "create_business",
    "update_business",
    "delete_business",
    "crawl_business",
    "get_health_scores",
    "list_profile_competitors",
    "set_profile_competitors",
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
    # HQ — composite reads + persona/product/buyer-intent CRUD
    "get_business_hq",
    "get_agent_brief",
    "recompute_health_scores",
    "refresh_business_overview",
    "list_personas",
    "create_persona",
    "update_persona",
    "delete_persona",
    "list_products",
    "create_product",
    "update_product",
    "delete_product",
    "list_buyer_intents",
    "create_buyer_intent",
    "update_buyer_intent",
    "delete_buyer_intent",
    # Analytics
    "get_analytics_trends",
    "get_analytics_dashboard",
    "compare_audits",
    # Agent API (composite-data reads)
    "get_business_facts",
    "get_business_claims",
    "get_competitive_comparison",
    "get_semantic_health",
    "buyer_fit_query",
    # Action plan
    "get_action_plan",
    "get_quick_wins",
    "mark_action_done",
    "dismiss_action",
    "get_action_progress",
}


def test_registered_tool_names_match_snapshot(registered_tool_names):
    """The live tool registry must match the v0.5.0 snapshot.

    On accidental removal: ``missing`` will be non-empty.
    On accidental addition (un-snapshotted tool): ``extra`` will be non-empty.

    Update EXPECTED_TOOLS_V0_5_0 above when a release intentionally adds or
    removes a tool, and bump the changelog in the same commit so whats_new()
    surfaces the change to existing clients.
    """
    missing = EXPECTED_TOOLS_V0_5_0 - registered_tool_names
    extra = registered_tool_names - EXPECTED_TOOLS_V0_5_0
    assert missing == set(), f"Tools missing from registry: {missing}"
    assert extra == set(), (
        f"Tools registered without being in the snapshot: {extra}. "
        f"Add them to EXPECTED_TOOLS_V0_5_0 and the changelog top entry."
    )


# Per-tool tier snapshot — catches subtle tier reclassifications that the
# bulk counts wouldn't notice. Update this when intentionally changing a
# tool's tier.
EXPECTED_TIER_FOR_TOOL: dict[str, str | None] = {
    # Scale-tier write tools (the v0.4.0 / v0.5.0 surface)
    "create_business": "scale",
    "delete_business": "scale",
    "set_profile_competitors": "scale",
    "create_persona": "scale",
    "update_persona": "scale",
    "delete_persona": "scale",
    "create_product": "scale",
    "update_product": "scale",
    "delete_product": "scale",
    "create_buyer_intent": "scale",
    "update_buyer_intent": "scale",
    "delete_buyer_intent": "scale",
    "recompute_health_scores": "scale",
    "refresh_business_overview": "scale",
    # Pro-tier — billing-sensitive analytics
    "get_usage_stats": "pro",
    "compare_audits": "pro",
    "get_analytics_trends": "pro",
    "get_analytics_dashboard": "pro",
}


def test_per_tool_tier_assignments_stable():
    """Lock down the tier each gated tool is mapped to. Catches accidental
    re-classifications (e.g., a Pro tool slipping to Scale would silently
    give it away for less revenue)."""
    drift: dict[str, tuple[str | None, str | None]] = {}
    for tool, expected in EXPECTED_TIER_FOR_TOOL.items():
        actual = required_tier_for_tool(tool)
        if actual != expected:
            drift[tool] = (expected, actual)
    assert drift == {}, (
        f"Tier drift detected (expected → actual): {drift}. "
        f"If intentional, update EXPECTED_TIER_FOR_TOOL."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Changelog fingerprint integrity
# ─────────────────────────────────────────────────────────────────────────────


def _load_changelog() -> dict:
    return yaml.safe_load(_CHANGELOG.read_text())


def test_top_changelog_entry_fingerprint_matches_live_registry(server):
    """The newest tool_changelog.yaml entry must pin the live registry's
    fingerprint. Drift here means either:
      (a) someone changed the tool surface without bumping the changelog, or
      (b) the changelog entry was pinned before the surface stabilized.

    Either way it breaks ``whats_new`` for clients that cache fingerprints —
    they'll be told they're up to date when they aren't."""
    changelog = _load_changelog()
    top = changelog["versions"][0]
    live_fp = compute_tools_fingerprint(server)
    assert top["fingerprint"] == live_fp, (
        f"Top changelog entry ({top['version']}) has fingerprint "
        f"{top['fingerprint']!r} but the live registry computes "
        f"{live_fp!r}. Recompute and update the changelog entry, OR add a "
        f"new top entry if a release is in progress."
    )


def test_no_changelog_entries_still_pending():
    """No production changelog entry should ship with a ``fingerprint:
    "PENDING"`` value. The release.sh script substitutes PENDING for the
    live value on tag; a PENDING value on main means a release was authored
    but never tagged.

    Match only the YAML value form (``fingerprint: "PENDING"``), not the
    word ``PENDING`` appearing in the file's instructional header comments.
    """
    text = _CHANGELOG.read_text()
    pending_values = re.findall(r'fingerprint:\s*"PENDING"', text)
    assert pending_values == [], (
        "PENDING placeholder remains in tool_changelog.yaml. "
        "Run scripts/release.sh to substitute or hand-pin it."
    )


# ─────────────────────────────────────────────────────────────────────────────
# README / SKILL.md tool count consistency
# ─────────────────────────────────────────────────────────────────────────────


_TOOL_COUNT_RE = re.compile(r"(\d{2,3})\s*(?:tools|MCP tools)\b", re.IGNORECASE)


def _extract_documented_tool_counts(path: Path) -> list[int]:
    """Find any 'NN tools' or 'NN MCP tools' strings in a doc — these are
    the most common places stale counts live."""
    if not path.exists():
        return []
    return [int(m) for m in _TOOL_COUNT_RE.findall(path.read_text())]


def test_readme_tool_count_matches_registry(registered_tool_names):
    """If README.md cites tool counts, at least one must be the live total.

    Docs typically carry multiple ``NN tools`` mentions (per-tier breakdowns
    like 31 / 62 / 73). The simplest invariant that catches release-stale
    docs is: the live registry size must appear at least once. A README
    that's been updated for the current release will mention the total
    somewhere; one that's drifted won't.
    """
    counts = _extract_documented_tool_counts(_README)
    if not counts:
        pytest.skip("README has no 'NN tools' string to verify")
    live = len(registered_tool_names)
    assert live in counts, (
        f"README cites tool counts {sorted(set(counts))} — none match the "
        f"live registry size {live}. Update the README's top-line total."
    )


def test_skill_tool_count_matches_registry(registered_tool_names):
    """SKILL.md is the entry-point document for MCP directories (Anthropic
    Connectors etc.). Same rule as README: at least one mentioned count
    must be the live total."""
    counts = _extract_documented_tool_counts(_SKILL)
    if not counts:
        pytest.skip("SKILL.md has no 'NN tools' string to verify")
    live = len(registered_tool_names)
    assert live in counts, (
        f"SKILL.md cites tool counts {sorted(set(counts))} — none match "
        f"the live registry size {live}. Update SKILL.md's top-line total."
    )


# ─────────────────────────────────────────────────────────────────────────────
# whats_new diff coverage — verify the changelog cursor works end-to-end
# ─────────────────────────────────────────────────────────────────────────────


def test_whats_new_returns_v0_5_0_entries_from_v0_4_0_fingerprint():
    """A client cached at v0.4.0's fingerprint calling whats_new should see
    v0.5.0's added/changed tools. Catches: dropped entries, version-
    ordering bugs, fingerprint typos in the changelog."""
    changelog = _load_changelog()
    v0_4_0 = next((v for v in changelog["versions"] if v["version"] == "0.4.0"), None)
    v0_5_0 = next((v for v in changelog["versions"] if v["version"] == "0.5.0"), None)
    assert v0_4_0 is not None, "0.4.0 entry missing from changelog"
    assert v0_5_0 is not None, "0.5.0 entry missing from changelog"

    # v0.5.0 must add at minimum the buyer-intent write tools (the
    # symmetry-completing PR) and the list_* discovery tools the agent
    # needs before CRUD.
    added = {t["name"] for t in v0_5_0.get("tools_added", [])}
    changed = {t["name"] for t in v0_5_0.get("tools_changed", [])}
    delta = added | changed
    expected_min_additions = {
        "list_personas",
        "list_products",
        "list_buyer_intents",
        "update_buyer_intent",
        "delete_buyer_intent",
    }
    missing = expected_min_additions - delta
    assert missing == set(), (
        f"v0.5.0 changelog entry doesn't record {missing}. whats_new() "
        f"would silently fail to surface these to upgrading clients."
    )
