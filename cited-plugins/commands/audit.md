---
name: audit
description: Run a GEO audit on a business
user_invocable: true
arguments:
  - name: business
    description: Business website, name or ID (optional, will ask if not provided)
    required: false
---

Check whether AI assistants cite a business, using Cited.

If `$ARGUMENTS` names a website, business or business ID, use it. Otherwise call `get_business` to list businesses and ask the user to pick one, or ask for their website.

Follow the geo-audit skill: `account_status` first, the free audit when there is no account, otherwise the question set, the quote, `run_audit` once the user approves the price, then `get_audit` until it finishes. Present the results with what to fix first.

After showing results, offer the geo-recommend workflow for the fixes.
