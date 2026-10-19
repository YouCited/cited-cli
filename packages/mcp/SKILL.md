---
name: cited
description: Audit, optimize, and monitor your business's visibility in AI-powered search engines
---

# Cited — AI Search Visibility Platform

Cited helps businesses measure and improve how they appear in AI-powered search results from ChatGPT, Claude, Perplexity, and Gemini. Use these tools to run GEO (Generative Engine Optimization) audits, get actionable recommendations, and generate ready-to-deploy solutions.

## Core Workflow

The typical flow is: **Business Setup → Audit → Recommendations → Solutions**

### 0. Account
- `check_auth_status` — Verify authentication; shows `credits_balance`, `unclaimed` and, for agent keys, key expiry
- No credentials and no human login? `agent_signup` creates an account and API key for you (no login). Show the human the claim link and 6-digit code it returns.

### 1. Business Setup
- `list_businesses` — See existing businesses
- `create_business` — Add a new business (requires name, website, description)
- `crawl_business` — Optional: force a fresh website crawl. Audits and solutions trigger crawls automatically if needed.

### 2. Run an Audit
- `create_audit_template` — Define what questions to audit (e.g., "What is [business]?", "Best [industry] tools")
- `free_audit` — Free GEO audit of any website, no login or credits needed. Use it when the user has no Cited account yet. Call again with the same `url` every ~30 seconds until `status` is `completed` (2-4 minutes).
- `quote_audit` — Check the credit cost first (a standard audit is 10 credits)
- `start_audit` — Launch the audit using a template (2-4 minutes); credits are charged up front. Poll `get_audit_status` every 30-60 seconds.
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

### 5. Monitor & Analyze
- `get_business_hq` — Comprehensive dashboard with health scores, personas, products
- `compare_audits` — Compare an audit against its baseline

### Help & Docs (no login)
- `search_docs` — Search the public Cited docs (how-tos, GEO concepts, feature guides). Use it before guessing how a Cited feature works.
- `get_doc` — Read one doc as markdown, by the `path` from a `search_docs` result.

## Credits (pay-as-you-go)

There are no plans or tiers; all 75 tools are available to every account. Work is paid for
with credits, 1 credit = $1:

- A standard audit is 10 credits (up to 5 questions with each engine's included models; each further 5 questions adds 10, each extra model 2). Failed or cancelled audits return their credits.
- Recommendations, solutions, crawls and question regeneration need the account to have bought credits at least once.
- `get_prices` (no login), `get_credits`, `credit_history`, `quote_audit`
- `buy_audit` — $15 for one audit; works for unclaimed agent accounts
- `buy_credits` — packs (pack_20, pack_50, pack_100; bigger packs add bonus credits); needs a claimed account
- `request_refund` (unused credits bought in the last 30 days; confirm with the human first), `set_auto_refill`
- `redeem_voucher` (a voucher code the human gives you adds free credits; once per account)

Purchases return a `checkout_url`. Show it to the human and wait: nothing is charged until they pay. Confirm with `get_credits` before saying the purchase is done.

On HTTP 402 a tool returns `payment_required: true` and `error_type` `insufficient_credits` (with `credits_needed`, `balance`, `buy_url`) or `purchase_required`. On 403 `claim_required` the agent account must be claimed by its human first.

If a result carries a top-level `notice` (for example, the agent key is about to expire), pass it on to the human.

## Tips

- Always call `check_auth_status` first to verify authentication and the credit balance
- Audits take 2-4 minutes — poll `get_audit_status` every 30-60 seconds (not every 10-15s)
- Use `get_recommendation_insights` (not `get_recommendation_result`) for structured, actionable data
- Use `start_solutions_batch` to generate multiple solutions in one call instead of sequential `start_solution` calls
- Solution artifacts include inline `content` for text-based files and absolute `download_path` URLs
- If a tool returns an error with `"retriable": true`, wait a moment and try again — transient errors are automatically surfaced with error details
