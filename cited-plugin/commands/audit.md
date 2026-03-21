---
name: audit
description: Run a GEO audit on a business
user_invocable: true
arguments:
  - name: business
    description: Business name or ID (optional, will prompt if not provided)
    required: false
---

Run a full GEO audit workflow using the Cited platform.

If `$ARGUMENTS` contains a business name or ID, use it to find the business. Otherwise, list businesses and ask the user to pick one.

Follow the geo-audit skill workflow: verify auth, select business, select/create template, start audit, poll until complete, then present results with actionable insights.

After showing results, offer to run recommendations for deeper analysis.
