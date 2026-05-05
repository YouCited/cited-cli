---
name: geo-recommend
description: Generate recommendations and solutions from a completed GEO audit
---

# GEO Recommendation + Solution Workflow

Use the Cited MCP tools to generate actionable recommendations from a completed audit, then create solutions for the highest-priority insights.

## Steps

1. **Start recommendations**: Call `start_recommendation` with the `audit_job_id` from a completed audit. Save the returned `job_id`.

2. **Poll for completion**: Call `get_recommendation_status` with the `job_id`. Repeat every 10-15 seconds until `status` is `"completed"`.

3. **Get insights** (summary): Call `get_recommendation_insights` with the `job_id`. By default this returns a **summary** with per-category counts and light rows ({source_type, source_id, label, key_metric}) — not the full payload. Categories:
   - `question_insights` — coverage gaps for specific queries (source_type: `question_insight`, source_id: `question_id`, key metric: `risk_level`)
   - `head_to_head_comparisons` — competitive analysis (source_type: `head_to_head`, source_id: `competitor_domain`, key metric: `overall_winner`)
   - `strengthening_tips` — improvement suggestions (source_type: `strengthening_tip`, source_id: `category`, key metric: `priority`)
   - `priority_actions` — urgent action items (source_type: `priority_action`, key metric: `priority`)

4. **Drill into one insight** (optional): When the user asks for the underlying detail of a specific item — full question text, full action description, citations — call `get_recommendation_insight_detail(job_id, source_type, source_id)`. Avoids pulling the whole payload via `full=True`.

5. **Generate solutions**: For each high-priority insight, call `start_solution` with:
   - `recommendation_job_id`: the recommendation job ID
   - `source_type`: from the insight
   - `source_id`: from the insight

6. **Poll solution status**: Call `get_solution_status`, then `get_solution_result` when complete.

## Tips

- Focus on `high` risk/priority items first.
- Solutions provide concrete, implementable steps — present them as an action plan.
- Group related solutions (e.g., all content improvements, all technical fixes) for clearer presentation.
