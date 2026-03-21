---
name: recommend
description: Generate GEO recommendations from a completed audit
user_invocable: true
arguments:
  - name: audit_job_id
    description: Audit job ID (optional, will show recent audits if not provided)
    required: false
---

Generate recommendations and solutions from a completed GEO audit.

If `$ARGUMENTS` contains an audit job ID, use it directly. Otherwise, call `list_audits` and ask the user to pick a completed audit.

Follow the geo-recommend skill workflow: start recommendations, poll until complete, get insights, then offer to generate solutions for the highest-priority items.
