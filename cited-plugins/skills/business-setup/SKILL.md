---
name: business-setup
description: Add a business to Cited and fill in its profile, buyer personas and offerings
---

# Business Setup Workflow

Use the Cited tools to add a business and give the audit enough context to ask good buyer questions.

## Steps

1. **Account**: call `account_status`. If no one is signed in, call `agent_signup` and show the user the claim link and code. An unclaimed account can add 1 business.
2. **Add the business**: call `setup_business` with `website`. The name comes from the domain and the industry defaults to `other`; pass `name`, `industry` and a `description` (10+ words) when you know them.
3. **Profile**: call `setup_business` again with `business_id` and what you learn from the user or the site: `one_line_description`, `primary_customer`, `problem_solved`, `offering_type`, `primary_market`, `service_areas`, `goals`.
4. **Personas and offerings**: in the same call pass `personas` (`{name, description}`) and `offerings` (`{name, description, category}`). Change one with `{id, ...}` and remove one with `{id, remove: true}`.
5. **Check**: `get_business` with `business_id` shows the profile, personas, offerings, question set and recent audits.

Then draft the buyer questions with `draft_questions` and continue with the `geo-audit` skill.
