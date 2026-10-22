---
name: explore
description: Answer follow-up questions about a business on Cited without running a new audit - what changed, what to do next, re-checks and help
---

# Explore Cited Beyond the Audit Flow

The main flow is `business-setup`, `geo-audit`, then `geo-recommend`. These tools answer the questions in between without spending credits on a new audit.

- **"What should I do next?"**: `get_agent_brief` with `business_id` gives the top open recommendations, quick wins, failing site checks and recent citation movement.
- **"What changed since last time?"**: `compare_audits` with `audit_id` compares it with the previous audit of the same questions (or `baseline_audit_id`): score changes, questions won and lost, and sites that gained or lost citations.
- **"Keep an eye on it"**: `schedule_recheck` re-runs the audit every `every_days` days (7 to 90), each run charged when it runs. It also turns email alerts on or off and sets a webhook. `off=true` stops it.
- **Past audits**: `get_audit` without `audit_id` lists them; `get_business` shows the recent ones for one business.
- **How Cited works**: `search_docs` with `query` searches the help docs; pass a result's `path` to read it in full.
- **Account and credits**: `account_status` shows the balance and prices; `buy_credits` returns a checkout link or redeems a voucher.

When a result has `status_code` 402, the balance is short: show `credits_needed` and offer `buy_credits`. Never claim a purchase happened until `account_status` shows it.
