---
name: geo-recommend
description: Generate recommendations and solutions from a completed GEO audit
---

# GEO Recommendation + Solution Workflow

Use the Cited MCP tools to generate actionable recommendations from a completed audit, then create solutions for the highest-priority insights.

## Steps

1. **Start recommendations**: Call `start_recommendation` with the `audit_job_id` from a completed audit. Save the returned `job_id`.

2. **Poll for completion**: Call `get_recommendation_status` with the `job_id`. Repeat every 10-15 seconds until `status` is `"completed"`.

3. **Get insights**: Call `get_recommendation_insights` with the `job_id`. This returns structured insights with `source_type` and `source_id` fields needed for solution generation:
   - `question_insights` — coverage gaps for specific queries (source_type: `question_insight`, source_id: `question_id`)
   - `head_to_head_comparisons` — competitive analysis (source_type: `head_to_head`, source_id: `competitor_domain`)
   - `strengthening_tips` — improvement suggestions (source_type: `strengthening_tip`, source_id: `category`)
   - `priority_actions` — urgent action items (source_type: `priority_action`)

4. **Generate solutions**: For each high-priority insight, call `start_solution` with:
   - `recommendation_job_id`: the recommendation job ID
   - `source_type`: from the insight
   - `source_id`: from the insight

5. **Poll solution status**: Call `get_solution_status`, then `get_solution_result` when complete.

## Tips

- Focus on `high` risk/priority items first.
- Solutions provide concrete, implementable steps — present them as an action plan.
- Group related solutions (e.g., all content improvements, all technical fixes) for clearer presentation.
