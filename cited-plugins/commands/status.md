---
name: status
description: Quick status check of the Cited account
user_invocable: true
---

Call `account_status` and give the user a short summary: who is signed in (or that no one is), the credit balance, the businesses on the account and the suggested next step.

If a business has audits, call `get_business` with its `business_id` for the latest ones, and `get_agent_brief` for what to focus on next.

For questions beyond the audit flow (what changed, scheduled re-checks, the docs), see `cited:explore`.
