---
name: explore
description: Ad-hoc tool exploration beyond the standard audit flow — diagnostics, comparisons, intel without re-running an audit, and one-off probes
---

# Explore Cited Beyond the Audit Flow

The standard pipeline is `cited:business-setup` → `cited:geo-audit` → `cited:geo-recommend`. This skill covers the eleven tools that DON'T fit that pipeline — diagnostics, deltas, intel surfaces, ad-hoc probes — so you can answer "what changed since last week," "what does Cited know about this business," "would AI recommend us for X" without burning a fresh audit.

If a tool returns `payment_required: true` with an `upgrade_tier` field, surface the upgrade message verbatim. Don't pretend the result was empty.

## Per-tool reference

### compare_audits — week-over-week regression detection

When to use it: The user asks "what changed since the last audit" or "are we improving." Run this instead of summarizing two full audit reports back to back — it computes the diff for you.

Recipe:
1. `list_audits(business_id=<biz_id>, limit=10)` — pull recent audits, find two completed ones on the same `named_audit_id`.
2. `compare_audits(audit_id=<recent_job_id>, baseline_id=<prior_job_id>)`.

What to do with the response: `questions_comparison` is a per-question delta map — surface regressions first (questions where the score fell), wins second. `changes` is the aggregate KPI delta block — name the top 2-3 movers ("share of voice fell 12 points; coverage flat"). `baseline_audit` and `current_audit` echo the two records being compared so the user knows what timeframe.

### cancel_job — recovery for hung or wrong-target jobs

When to use it: A `get_*_status` call shows a job has been "running" far longer than expected (audits typically 2-4 min, recommendations 1-2 min, solutions 30-60s) OR the user realizes the job was started against the wrong template/business. Cancelling stops further plan-budget consumption.

Recipe:
1. `cancel_job(job_id=<id>)` — `job_type` auto-probes if omitted.

What to do with the response: `{success, job_type, message}` on success, or a not-found error. Confirm the cancellation by job_type ("audit cancelled," not just "cancelled") and tell the user they can start a fresh job.

### get_analytics_dashboard — combined analytics page (Pro)

When to use it: The user asks for an overview of AI search performance — KPIs, trends, top/declining questions, citation patterns, benchmarks. One call covers what the web Analytics page shows.

Recipe:
1. `get_analytics_dashboard(business_id=<biz_id>)`.

What to do with the response: Top-level fields are `kpi_trends` (time-series per KPI), `question_performance` (top + declining), `citation_trends` (match rates, domain diversity), `benchmarks` (vs. historical average), `domain_benchmarks` (per-domain severity). Lead the summary with `benchmarks` deltas; then the worst-trending KPI from `kpi_trends`; then the top declining questions.

### get_analytics_trends — KPI time series only (Pro)

When to use it: You only need the KPI time-series — e.g., for a chart, or to compute a custom trend. Cheaper than the dashboard if you don't need the rest.

Recipe:
1. `get_analytics_trends(business_id=<biz_id>)`.

What to do with the response: `periods` is the x-axis (ordered date labels). `kpi_trends` maps KPI name → list of values aligned with `periods`. `summary` has aggregate stats. Plot or summarize the largest delta first.

### get_business_facts — structured intel from the fact graph (Pro)

When to use it: The user asks "what does Cited know about [business]" or you need structured intel (locations, products, summary) without running an audit. Cheap, no plan-budget impact. Pair with crawl_business if the data looks stale.

Recipe:
1. `get_business_facts(business_id=<biz_id>)`.

What to do with the response: `name`, `summary`, `locations`, `products`, `facts`. Surface `summary` as the headline. If `summary` is null AND `facts` is empty, the fact graph is thin — recommend running `crawl_business` to populate (see "Cold-start business intel" below).

### get_business_claims — verifiable claims with evidence (Pro)

When to use it: Auditing brand truth-in-advertising, or surfacing claims that need stronger evidence before they appear in AI summaries. Useful when prepping a product page or a press kit.

Recipe:
1. `get_business_claims(business_id=<biz_id>)`.

What to do with the response: `claims` is a list of statements with evidence references. Highlight claims with weak/absent evidence first — those are the ones to either substantiate or remove.

### get_business_hq — comprehensive dashboard (Pro)

When to use it: The user wants a one-shot snapshot of an account — health scores, recent audits, recommendations, competitive position, top action items. Reach for this when summarizing an account holistically rather than answering a narrow question.

Recipe:
1. `get_business_hq(business_id=<biz_id>, full=True)` — everything in one call.
2. (Cheaper) `get_business_hq(business_id=<biz_id>)` for just the core dashboard, then add `include_personas` / `include_products` / `include_intents` / `include_actions` flags as needed.

What to do with the response: Lead with `health_scores` (5 core scores: brand_confidence, crawl_coverage, ai_readiness, buyer_clarity, trust_score) and `priority_actions` — those tell the user what's wrong and what to fix. `recent_audits` and `recommendations` for activity context. `top_competitors` and `displacement` for competitive context. `agentic_readiness` if the user is asking specifically about AI-agent visibility.

### get_competitive_comparison — strengths/weaknesses vs competitors (Pro)

When to use it: Mid-conversation, the user asks "how do we stack up against X." Pulls existing competitive analysis without running new prompts.

Recipe:
1. `get_competitive_comparison(business_id=<biz_id>)`.

What to do with the response: `competitors` (named competitor entities), `strengths` (top 5-10 wins), `weaknesses` (top 5-10 gaps), `market_intelligence` (supporting observations). Lead with weaknesses if the user is looking for what to fix; lead with strengths if they're pitching/positioning.

### get_semantic_health — AI-readability diagnostics (Pro)

When to use it: The user wants to know what to fix to be more discoverable to AI engines. Returns structured diagnostics rather than free-text recommendations.

Recipe:
1. `get_semantic_health(business_id=<biz_id>)`.

What to do with the response: `entity_grounding`, `schema_coverage`, `faq_coverage`, `claim_evidence_coverage` are coverage diagnostics — surface the lowest-coverage area first as the priority fix. `trust_signals` is a list of finding+confidence entries.

### buyer_fit_query — ad-hoc fit simulation (Pro)

When to use it: "Would AI recommend us for X" probes — testing positioning before committing to a full audit, or evaluating a new buyer profile. Faster and cheaper than a full audit; doesn't update the business record.

Recipe:
1. `buyer_fit_query(buyer="<profile or query>", business_id=<biz_id>, limit=5)`. Add `constraints=[{...}]` to narrow.

What to do with the response: `recommendations` is the ordered fit list — top entries are the strongest matches. Echo the `buyer` field back to the user so they know what was scored. If recommendations look weak, suggest a full audit with a template tuned for this buyer's queries.

### export_audit — share the report outside MCP (Scale)

When to use it: The user wants to forward, attach, or archive the audit as a PDF.

Recipe:
1. `export_audit(job_id=<completed_audit_job_id>)`. Add `provider="openai"|"gemini"|"perplexity"` for a per-provider view.

What to do with the response: `url` is a presigned download link with a 1-hour TTL. Surface it with `expires_at` so the user knows to grab it promptly. `filename` is the suggested save name.

## Compound recipes

### Weekly visibility report

When to use it: The user asks for a status update on AI search performance, or sets up a weekly check-in.

1. `get_analytics_dashboard(business_id=<biz_id>)` — KPI trends + benchmarks in one shot.
2. `list_audits(business_id=<biz_id>, limit=5)` — find the two most recent completed audits on the same `named_audit_id`.
3. `compare_audits(audit_id=<latest>, baseline_id=<prior>)` — week-over-week delta.

Compose into a markdown report ready to forward:
- **Headline:** top KPI movement from `compare_audits.changes`.
- **Trend section:** 1-2 sentences from `kpi_trends` (direction + magnitude per KPI).
- **Regressions:** top 3 from `compare_audits.questions_comparison` where score fell.
- **Wins:** top 2 from `compare_audits.questions_comparison` where score rose.
- **Benchmarks:** where the business sits vs. historical from `benchmarks`.

Don't dump raw JSON — the report is for a human stakeholder.

### Cold-start business intel

When to use it: The user asks "what does Cited know about this business" — no audit yet, or the existing data is stale.

1. `get_business_hq(business_id=<biz_id>, full=True)` — comprehensive snapshot.
2. **Decision point:** if `crawl_freshness.last_crawled_at` is missing or > 30 days old, OR `health_scores.crawl_coverage` is below ~30, the data is stale. Call `crawl_business(business_id=<biz_id>)`, save the `job_id`, then `get_job_status(job_id=<id>)` until status is `completed` (1-3 min).
3. After the crawl finishes, `get_business_facts(business_id=<biz_id>)` for the populated fact graph.

Surface: identity + the 5 health scores + populated facts (locations, products, summary). If you triggered a fresh crawl, mention that the data is now current.

### Ad-hoc buyer-fit probe

When to use it: The user asks "would AI recommend us if someone searched for X" or wants to test product positioning before running a full audit.

1. `buyer_fit_query(buyer="<phrasing>", business_id=<biz_id>, limit=5)`.
2. Inspect the top recommendation entry. If the response includes a numeric score field, use it; otherwise judge by the ordering and the recommendation metadata.
3. **Decision:**
   - **Strong fit** (top entry clearly dominant, high score if present): the business is well-positioned for this buyer; surface the matching strengths.
   - **Mixed** (recommendations present but no clear winner): there's coverage but gaps; surface what's matching and what's missing.
   - **Weak fit** (low scores, generic recommendations): suggest running `start_audit` with a template tuned for this buyer's queries to get a deeper diagnosis.

Surface the top 2-3 recommendations and your verdict, not the raw recommendations list.

## Cross-references

- **Standard pipeline:** `cited:business-setup` → `cited:geo-audit` → `cited:geo-recommend`.
- **Conversation status check:** `cited:status`.
