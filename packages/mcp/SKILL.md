---
name: cited
description: Audit, optimize, and monitor your business's visibility in AI-powered search engines
---

# Cited — AI Search Visibility Platform

Cited helps businesses measure and improve how they appear in AI-powered search results from ChatGPT, Claude, Perplexity, and Gemini. Use these tools to run GEO (Generative Engine Optimization) audits, get actionable recommendations, and generate ready-to-deploy solutions.

## Core Workflow

The typical flow is: **Business Setup → Audit → Recommendations → Solutions**

### 1. Business Setup
- `check_auth_status` — Verify authentication and check plan limits
- `list_businesses` — See existing businesses
- `create_business` — Add a new business (requires name, website, description)
- `crawl_business` — Crawl the business website to gather data for analysis

### 2. Run an Audit
- `create_audit_template` — Define what questions to audit (e.g., "What is [business]?", "Best [industry] tools")
- `start_audit` — Launch the audit using a template
- `get_audit_status` — Poll until the audit completes (typically 2-4 minutes)
- `get_audit_result` — Retrieve visibility scores, citation rates, and competitor data

### 3. Generate Recommendations
- `start_recommendation` — Analyze audit results and generate improvement recommendations
- `get_recommendation_insights` — Get structured insights with question-level analysis, competitor head-to-head comparisons, and strengthening tips. Each insight includes `source_type` and `source_id` needed for the next step.

### 4. Create Solutions
- `start_solution` — Generate implementation artifacts (schema markup, content templates, outreach playbooks) for a specific insight
- `get_solution_result` — Retrieve the solution with downloadable artifacts

## Example Prompts

**Run a full GEO audit:**
> "List my businesses, then run a GEO audit on [business name]. When it's done, show me my visibility scores and which competitors are being cited instead of me."

**Competitive analysis:**
> "Run an audit on my business for these questions: 'Best CRM software for small business', 'Top sales automation tools', 'What is [my product]?'. Then generate recommendations and show me the head-to-head comparisons with my top competitors."

**Generate solutions:**
> "Look at my latest audit recommendations and generate solutions for the top 3 highest-risk insights. I want to see the schema markup and content changes I need to make."

**Monitor over time:**
> "Show me the health scores for my business and compare them to my last audit. What has improved and what still needs work?"

## Tips

- Always call `check_auth_status` first to verify authentication and plan limits
- Audits take 2-4 minutes — poll `get_audit_status` every 15 seconds
- Use `get_recommendation_insights` (not `get_recommendation_result`) for structured, actionable data
- Solutions have a concurrency limit of 3 — wait for one batch to complete before starting more
- Each insight's `source_type` and `source_id` map directly to `start_solution` parameters
