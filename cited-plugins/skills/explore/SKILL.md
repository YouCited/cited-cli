---
name: explore
description: Ad-hoc tool exploration beyond the standard audit flow — diagnostics, comparisons, intel without re-running an audit, and one-off probes
---

# Explore Cited Beyond the Audit Flow

The standard pipeline is `cited:business-setup` → `cited:geo-audit` → `cited:geo-recommend`. This skill covers the seven tools that DON'T fit that pipeline — diagnostics, deltas, intel surfaces, ad-hoc probes, and Validation Engine fix-verification — so you can answer "what changed since last week," "what does Cited know about this business," and "did my fix actually land" without burning a fresh audit.

If a tool returns `payment_required: true` (HTTP 402: `insufficient_credits` or `purchase_required`), tell the user, show them the `buy_url` (or a checkout link from `buy_audit` / `buy_credits`), and retry after they pay. Don't pretend the result was empty.

## Per-tool reference

### compare_audits — week-over-week regression detection

When to use it: The user asks "what changed since the last audit" or "are we improving." Run this instead of summarizing two full audit reports back to back — it computes the diff for you.

Recipe:
1. `list_audits(business_id=<biz_id>, limit=10)` — pull recent audits, find two completed ones on the same `named_audit_id`.
2. `compare_audits(audit_id=<recent_job_id>, baseline_id=<prior_job_id>)`.

What to do with the response: `questions_comparison` is a per-question delta map — surface regressions first (questions where the score fell), wins second. `changes` is the aggregate KPI delta block — name the top 2-3 movers ("share of voice fell 12 points; coverage flat"). `baseline_audit` and `current_audit` echo the two records being compared so the user knows what timeframe.

### cancel_job — recovery for hung or wrong-target jobs

When to use it: A `get_*_status` call shows a job has been "running" far longer than expected (audits typically 2-4 min, recommendations 1-2 min, solutions 30-60s) OR the user realizes the job was started against the wrong template/business. Cancelling a failed or unwanted audit returns its credits.

Recipe:
1. `cancel_job(job_id=<id>)` — `job_type` auto-probes if omitted.

What to do with the response: `{success, job_type, message}` on success, or a not-found error. Confirm the cancellation by job_type ("audit cancelled," not just "cancelled") and tell the user they can start a fresh job.

### get_business_hq — comprehensive dashboard

When to use it: The user wants a one-shot snapshot of an account — health scores, recent audits, recommendations, competitive position, top action items. Reach for this when summarizing an account holistically rather than answering a narrow question.

Recipe:
1. `get_business_hq(business_id=<biz_id>, full=True)` — everything in one call.
2. (Cheaper) `get_business_hq(business_id=<biz_id>)` for just the core dashboard, then add `include_personas` / `include_products` / `include_actions` flags as needed.

What to do with the response: Lead with `health_scores` (5 core scores: brand_confidence, crawl_coverage, ai_readiness, buyer_clarity, trust_score) and `priority_actions` — those tell the user what's wrong and what to fix. `recent_audits` and `recommendations` for activity context. `top_competitors` for competitive context. `agentic_readiness` if the user is asking specifically about AI-agent visibility.

### Verify recommendation fixes — Validation Engine (Base)

When to use it: the user just told you they made a fix ("added the FAQ schema", "set my canonical tags") and wants to confirm it's live, OR they want a deep diagnostic of what's actually detectable on their site beyond the AI-citation audit. The Validation Engine runs 62 deterministic GEO/SEO checks across schema, llms.txt, technical SEO, content, and social — complementary to the audit, NOT a replacement.

Recipes:
1. **"Did my fix land?"** — `validate_recommendation(recommendation_id=<id>)` returns an ARQ `job_id`. Wait a few seconds, then `get_recommendation_validation_latest(recommendation_id=<id>)` to read the result.
2. **"Show me everything that's still broken"** — `get_recommendation_check_status(recommendation_job_id=<id>, mode="cache")` for fast read from recent crawl, or `mode="fresh"` for live HTTP fetches (slow, more accurate).

What to do with the response:
- `validate_recommendation`: returns `{job_id, recommendation_id, check_id, mode}`. Tell user the job is queued; the result will appear in `get_recommendation_validation_latest` after the worker finishes.
- `get_recommendation_validation_latest`: `status` is the headline — `valid` (fix landed), `invalid` (still missing), `inconclusive` (couldn't verify, often crawler-blocked). `evidence.message` has detail.
- `get_recommendation_check_status`: lead with `counts` (X valid / Y invalid / Z inconclusive), then surface the invalid checks first — those are the unfixed gaps. Inconclusive results often mean the site blocked the crawler; mention that as a possibility before assuming the fix is broken.

### export_audit — share the report outside MCP

When to use it: The user wants to forward, attach, or archive the audit as a PDF.

Recipe:
1. `export_audit(job_id=<completed_audit_job_id>)`. Add `provider="openai"|"gemini"|"perplexity"` for a per-provider view.

What to do with the response: `url` is a presigned download link with a 1-hour TTL. Surface it with `expires_at` so the user knows to grab it promptly. `filename` is the suggested save name.

## Compound recipes

### Weekly visibility report

When to use it: The user asks for a status update on AI search performance, or sets up a weekly check-in.

1. `list_audits(business_id=<biz_id>, limit=5)` — find the two most recent completed audits on the same `named_audit_id`.
2. `compare_audits(audit_id=<latest>, baseline_id=<prior>)` — week-over-week delta.

Compose into a markdown report ready to forward:
- **Headline:** top KPI movement from `compare_audits.changes`.
- **Regressions:** top 3 from `compare_audits.questions_comparison` where score fell.
- **Wins:** top 2 from `compare_audits.questions_comparison` where score rose.

Don't dump raw JSON — the report is for a human stakeholder.

### Cold-start business intel

When to use it: The user asks "what does Cited know about this business" — no audit yet, or the existing data is stale.

1. `get_business_hq(business_id=<biz_id>, full=True)` — comprehensive snapshot.
2. **Decision point:** if `crawl_freshness.last_crawled_at` is missing or > 30 days old, OR `health_scores.crawl_coverage` is below ~30, the data is stale. Call `crawl_business(business_id=<biz_id>)`, save the `job_id`, then `get_job_status(job_id=<id>)` until status is `completed` (1-3 min).
3. After the crawl finishes, call `get_business_hq(business_id=<biz_id>, full=True)` again for the refreshed snapshot.

Surface: identity + the 5 health scores + personas and products. If you triggered a fresh crawl, mention that the data is now current.

## Cross-references

- **Standard pipeline:** `cited:business-setup` → `cited:geo-audit` → `cited:geo-recommend`.
- **Conversation status check:** `cited:status`.
