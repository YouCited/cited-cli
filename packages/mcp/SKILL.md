---
name: cited
description: Audit, optimize, and monitor your business's visibility in AI-powered search engines
---

# Cited — AI Search Visibility Platform

Cited helps businesses measure and improve how they appear in AI-powered search results from ChatGPT, Claude, Perplexity, and Gemini. Use these tools to run GEO (Generative Engine Optimization) audits, get actionable recommendations, and generate ready-to-deploy solutions.

## Core Workflow

The typical flow is: **Business Setup → Audit → Recommendations → Solutions**

### 1. Business Setup
- `check_auth_status` — Verify authentication and check plan limits
- `list_businesses` — See existing businesses
- `create_business` — Add a new business (requires name, website, description)
- `crawl_business` — Optional: force a fresh website crawl. Audits and solutions trigger crawls automatically if needed.

### 2. Run an Audit
- `create_audit_template` — Define what questions to audit (e.g., "What is [business]?", "Best [industry] tools")
- `free_audit` — Free GEO audit of any website, no login or plan needed. Use it when the user has no Cited account yet. Call again with the same `url` every ~30 seconds until `status` is `completed` (2-4 minutes).
- `start_audit` — Launch the audit using a template (2-4 minutes). Poll `get_audit_status` every 30-60 seconds.
- `get_audit_result` — Returns a summary by default (aggregate KPIs, competitor leaderboard, question IDs). Use `full=True` for detailed per-question citations — warning: full results can be very large.

### 3. Generate Recommendations
- `start_recommendation` — Analyze audit results and generate improvement recommendations
- `get_recommendation_insights` — Get structured insights with `source_type` and `source_id` needed for solutions:
  - `question_insight` → source_id is the `question_id`
  - `head_to_head` → source_id is the `competitor_domain`
  - `strengthening_tip` → source_id is the `category`

### 4. Create Solutions
- `start_solution` — Generate a solution for a single insight
- `start_solutions_batch` — **Preferred**: generate up to 10 solutions in one call. Pass all insights from step 3 to fan out efficiently.
- `get_solution_result` — Retrieve the solution with artifacts (inline content for text files, absolute download URLs)

### 4b. Verify Fixes (Validation Engine)
- `get_recommendation_check_status` — Run all 62 deterministic GEO/SEO checks against the business linked to a recommendation job; returns counts (valid/invalid/inconclusive) plus per-check detail. Modes: `cache` (read recent crawl) or `fresh` (live HTTP fetches).
- `validate_recommendation` — Re-run the deterministic check for one recommendation (after the user says they made the fix).
- `get_recommendation_validation_latest` — Fetch the latest stored validation result for a recommendation.

### 5. Monitor & Analyze (Pro plan)
- `get_business_hq` — Comprehensive dashboard with health scores, personas, products
- `get_analytics_trends` — KPI trends over time
- `get_analytics_dashboard` — Combined analytics dashboard (KPI trends + question performance + benchmarks)
- `compare_audits` — Compare an audit against its baseline
- Agent API: `get_business_facts`, `get_business_claims`, `get_competitive_comparison`, `get_semantic_health`, `buyer_fit_query`

## Plan Requirements

Tools are gated by subscription tier. If a tool is above the user's plan, it returns an upgrade message with a billing link.

- **Growth** (entry tier): Read-only — list/get businesses, run audits, view recommendations (32 tools)
- **Scale**: Full write access — create/update/delete, solutions, export, cancel (63 tools)
- **Pro**: Everything + HQ dashboard, analytics, agent API (74 tools)

Always call `check_auth_status` first — it shows the user's plan and remaining limits.

## Tips

- Always call `check_auth_status` first to verify authentication and plan limits
- Audits take 2-4 minutes — poll `get_audit_status` every 30-60 seconds (not every 10-15s)
- Use `get_recommendation_insights` (not `get_recommendation_result`) for structured, actionable data
- Use `start_solutions_batch` to generate multiple solutions in one call instead of sequential `start_solution` calls
- Solution artifacts include inline `content` for text-based files and absolute `download_path` URLs
- If a tool returns an error with `"retriable": true`, wait a moment and try again — transient errors are automatically surfaced with error details
