---
name: geo-audit
description: Run a full GEO audit on a business using the Cited platform
---

# GEO Audit Workflow

Use the Cited MCP tools to run a complete GEO (Generative Engine Optimization) audit.

## Steps

1. **Verify auth**: Call `check_auth_status` to confirm the user is logged in.

2. **Select business**: Call `list_businesses` and let the user pick one, or use a known `business_id`.

3. **Select or create template**: Call `list_audit_templates` to show available templates.
   - To create a new one: `create_audit_template` with a name, business_id, and optional questions.
   - Each template defines the audit questions that will be evaluated.

4. **Start the audit**: Call `start_audit` with the `named_audit_id` (and optional `business_id` override). Save the returned `job_id`.

5. **Poll for completion**: Call `get_audit_status` with the `job_id`. Repeat every 10-15 seconds until `status` is `"completed"` or `"failed"`.

6. **Get results**: Call `get_audit_result` with the `job_id` to retrieve scores and findings.

## Interpreting Results

- **Risk levels**: `high` = needs immediate attention, `medium` = should address soon, `low` = minor improvement opportunity
- **Coverage scores**: 0.0-1.0 scale. Below 0.5 means the business is poorly represented for that query.
- After reviewing audit results, suggest running recommendations with the `geo-recommend` workflow.
