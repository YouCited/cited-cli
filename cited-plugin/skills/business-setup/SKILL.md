---
name: business-setup
description: Create and onboard a new business on the Cited platform
---

# Business Setup Workflow

Use the Cited MCP tools to create a new business and prepare it for GEO auditing.

## Steps

1. **Verify auth**: Call `check_auth_status` to confirm the user is logged in.

2. **Create business**: Call `create_business` with:
   - `name`: Business name
   - `website`: Must be a publicly DNS-resolvable domain (not example.com)
   - `description`: At least ~50 characters describing the business
   - `industry`: One of: automotive, beauty, consulting, education, entertainment, finance, fitness, government, healthcare, home_services, hospitality, legal, manufacturing, non_profit, real_estate, restaurant, retail, technology, other

3. **Trigger crawl**: Call `crawl_business` with the `business_id` from the create response. Save the returned `job_id`.

4. **Poll crawl status**: Call `get_job_status` with `job_id` and `job_type="audit"` (crawl jobs use the same status endpoint pattern). Wait for completion.

5. **Check health scores**: Call `get_health_scores` with the `business_id` to see the initial GEO health assessment.

## Next Steps

After setup, suggest running a GEO audit using the `geo-audit` workflow.
