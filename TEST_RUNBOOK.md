# Cited CLI — Test Runbook

Comprehensive test commands organized by workflow stage. Each section builds on the previous one.

**Convention:** Commands that return an ID are shown with bash variable capture — replace placeholder values with real IDs as you run each step. The `--json` flag gives clean JSON output for extraction.

```bash
# Portable ID extraction — works without jq:
BUSINESS_ID=$(cited --json business create ... | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# If you have jq installed (cleaner):
BUSINESS_ID=$(cited --json business create ... | jq -r '.id')
```

---

## 1. System & Config

```bash
# Verify CLI is installed
cited version
cited --json version

# Check API health (both environments)
cited --env dev status
cited --env prod status
cited --json --env dev status

# Configure default environment (saves typing --env dev every time)
cited config set environment dev
cited config get environment
cited config show
cited config environments
cited --json config environments
```

---

## 2. Authentication

```bash
# --- Top-level login (preferred) ---

# Browser login (default — opens youcited login page)
cited login

# Browser login with specific OAuth provider
cited login --provider google
cited login --provider microsoft
cited login --provider github

# Password login (interactive — prompts for password)
cited login --email <your-email>

# Password login (non-interactive — scriptable / CI)
cited login --email <your-email> --password <your-password>

# --- Backward-compatible subcommand (same behavior) ---
cited auth login --email <your-email> --password <your-password>

# --- Token paste fallback ---
# If browser callback times out (firewall, WSL, SSH), the CLI will prompt
# you to paste the token shown on the browser success page.

# Verify session
cited auth status
cited --json auth status

# Extract token (for piping to other tools)
cited auth token
cited auth token | head -c 50   # Verify it's a JWT

# Test wrong credentials (should exit 2)
cited login --email fake@example.com --password wrong; echo "Exit: $?"

# Test invalid provider (should exit 4)
cited login --provider facebook; echo "Exit: $?"
```

---

## 3. Business CRUD

```bash
# List existing businesses
cited business list
cited --json business list

# Create a test business
# IMPORTANT: website must be a publicly resolvable domain (not example.com)
# IMPORTANT: industry must be one of the enum values below
BUSINESS_ID=$(cited --json business create \
  --name        "CLI Test Corp" \
  --website     "https://anthropic.com" \
  --description "A test technology company for validating CLI runbook commands and GEO workflows." \
  --industry    "technology" \
  | jq -r '.id')
echo "BUSINESS_ID=$BUSINESS_ID"

# Valid --industry values:
# automotive  beauty  consulting  education  entertainment  finance
# fitness  government  healthcare  home_services  hospitality  legal
# manufacturing  non_profit  real_estate  restaurant  retail  technology  other

# Get business details
cited business get $BUSINESS_ID
cited --json business get $BUSINESS_ID

# Update business
cited business update $BUSINESS_ID --name "CLI Test Corp Updated"
cited business update $BUSINESS_ID --website "https://anthropic.com"

# Health scores (meaningful after a crawl has run)
cited business health $BUSINESS_ID
cited --json business health $BUSINESS_ID
```

---

## 4. Audit Templates

Audit templates define the GEO questions you want answered — "Are we cited when people ask about X?" Each template is reusable across multiple audit runs.

Auto-generated questions are rarely perfect out of the box. The typical flow is: **create → review → refine → run audit**. Use `audit template update` to revise questions before starting an audit.

```bash
# Create a template with multiple questions (--question is repeatable)
TEMPLATE_ID=$(cited --json audit template create \
  --name        "Q4 GEO Audit" \
  --business    $BUSINESS_ID \
  --description "Checks citation presence across key AI and technology queries" \
  --question    "Are we cited when people ask about AI productivity tools?" \
  --question    "Does our product appear in enterprise software recommendations?" \
  --question    "Are we mentioned when users research our core use case?" \
  | jq -r '.id')
echo "TEMPLATE_ID=$TEMPLATE_ID"

# List templates for a business
cited audit template list
cited audit template list --business $BUSINESS_ID
cited --json audit template list --business $BUSINESS_ID

# Inspect a template (shows all questions numbered)
cited audit template get $TEMPLATE_ID
cited --json audit template get $TEMPLATE_ID

# ── Update / refine questions before running an audit ──

# Replace ALL questions (--question flags replace the full list)
cited audit template update $TEMPLATE_ID \
  --question "Are we cited when enterprise buyers ask about AI safety?" \
  --question "Does Anthropic appear in responsible AI recommendations?" \
  --question "Are we mentioned when developers compare AI platforms?"

# Update just the name or description (keeps existing questions)
cited audit template update $TEMPLATE_ID --name "Q4 GEO Audit v2"
cited audit template update $TEMPLATE_ID --description "Revised scope for Q4"

# Update everything at once
cited audit template update $TEMPLATE_ID \
  --name "Q4 GEO Audit v2" \
  --description "Focused on enterprise buyer queries" \
  --question "Do enterprise teams find us when researching AI tools?" \
  --question "Are we cited in AI safety and alignment discussions?"

# Verify changes
cited audit template get $TEMPLATE_ID

# JSON output (for scripting)
cited --json audit template update $TEMPLATE_ID \
  --question "Updated question 1" \
  --question "Updated question 2"

# Delete a template
cited audit template delete $TEMPLATE_ID --yes        # skip confirmation
cited audit template delete $TEMPLATE_ID              # prompts for confirmation
```

---

## 5. Crawl (Scan Website)

The crawler reads your site so the platform understands your content, structure, and brand signals. Run this before your first audit for best results.

```bash
# Trigger a crawl — returns a job_id you can watch
CRAWL_JSON=$(cited --json business crawl $BUSINESS_ID)
CRAWL_JOB=$(echo $CRAWL_JSON | jq -r '.job_id')
echo "CRAWL_JOB=$CRAWL_JOB"

# Watch live progress until complete
cited job watch $CRAWL_JOB

# View crawl results as health score bars
cited business health $BUSINESS_ID
cited --json business health $BUSINESS_ID
```

---

## 6. Audit Workflow

```bash
# Start an audit from a template
# IMPORTANT: first argument is the template (named_audit) ID, not the business ID
AUDIT_JSON=$(cited --json audit start $TEMPLATE_ID --business $BUSINESS_ID)
AUDIT_JOB=$(echo $AUDIT_JSON | jq -r '.job_id')
echo "AUDIT_JOB=$AUDIT_JOB"

# Start with specific citation providers
cited audit start $TEMPLATE_ID --provider openai --provider perplexity

# Watch live progress bar
cited job watch $AUDIT_JOB
cited job watch $AUDIT_JOB --type audit         # explicit type (skips auto-detect probe)
cited job watch $AUDIT_JOB --interval 5         # poll every 5 seconds

# Poll status manually
cited audit status $AUDIT_JOB
cited --json audit status $AUDIT_JOB

# Get full results when complete (large JSON — pipe to jq for a summary)
cited audit result $AUDIT_JOB
cited --json audit result $AUDIT_JOB
cited --json audit result $AUDIT_JOB | jq '{total_citations: (.citations_pulled | length), citation_score: .citation_score}'

# List audit history
cited audit list
cited audit list --business $BUSINESS_ID
cited --json audit list --business $BUSINESS_ID

# Export PDF report
cited audit export $AUDIT_JOB
cited audit export $AUDIT_JOB --output my-audit.pdf
ls -la *.pdf
```

---

## 7. Recommendations (requires completed audit)

```bash
# Generate recommendations from an audit
RECO_JSON=$(cited --json recommend start $AUDIT_JOB)
RECO_JOB=$(echo $RECO_JSON | jq -r '.job_id')
echo "RECO_JOB=$RECO_JOB"

# Watch progress
cited job watch $RECO_JOB
cited job watch $RECO_JOB --type recommendations

# Check status / full raw results
cited recommend status $RECO_JOB
cited recommend result $RECO_JOB
cited --json recommend result $RECO_JOB

# *** View insights table — the key discovery step before running solutions ***
# Shows all actionable items with their source_type and source_id
cited recommend insights $RECO_JOB

# In --json mode, insights returns the same raw result as 'recommend result'
# but it's useful for scripting source_id extraction:
SOURCE_ID=$(cited --json recommend insights $RECO_JOB \
  | jq -r '.question_insights[0].question_id')
echo "SOURCE_ID=$SOURCE_ID"

# List recommendation history
cited recommend list
cited recommend list --audit $AUDIT_JOB
```

### Understanding the insights table

`cited recommend insights` renders a table with four source types:

| Type | Source ID | Where it comes from |
|------|-----------|-------------------|
| `question_insight` | UUID (`question_id` field) | One per audit question with low citation score |
| `head_to_head` | Domain string (e.g. `wikipedia.org`) | `competitor_domain` field in `head_to_head_comparisons` |
| `strengthening_tip` | Category string (e.g. `llms_txt`) | `category` field in `strengthening_tips` |
| `priority_action` | ID or category | From `priority_actions` |

---

## 8. Solutions (requires completed recommendation)

```bash
# First, run 'cited recommend insights $RECO_JOB' to see available source types and IDs
cited recommend insights $RECO_JOB

# Start a solution — specify the recommendation job, source type, and source ID
cited solution start $RECO_JOB \
  --type   question_insight \
  --source <source_id_from_insights_table>

# Other source types:
cited solution start $RECO_JOB --type head_to_head      --source <competitor_domain>
cited solution start $RECO_JOB --type strengthening_tip --source <category>
cited solution start $RECO_JOB --type priority_action   --source <source_id>

# The CLI prints:
# → "Track progress: cited job watch <sol_job_id>"
# → "View artifacts: https://dev.youcited.com/solutions/<sol_job_id>"
#   (artifacts are rich documents — open the link in the web app)

SOL_JOB=<job_id_from_solution_start_output>

# Watch progress
cited job watch $SOL_JOB
cited job watch $SOL_JOB --type solutions

# Check status / results
cited solution status $SOL_JOB
cited solution result $SOL_JOB
cited --json solution result $SOL_JOB

# List solution history
cited solution list
cited solution list --business $BUSINESS_ID
```

---

## 9. Business HQ Dashboard

```bash
# Basic dashboard (health scores + summary)
cited hq $BUSINESS_ID

# With additional sections
cited hq $BUSINESS_ID --personas
cited hq $BUSINESS_ID --products
cited hq $BUSINESS_ID --actions
cited hq $BUSINESS_ID --personas --products --intents --actions

# Full heavy load (all data in one request)
cited hq $BUSINESS_ID --full

# JSON output (great for piping to jq)
cited --json hq $BUSINESS_ID --full
cited --json hq $BUSINESS_ID --full | jq '.health_scores'
```

---

## 10. Analytics

```bash
# KPI trends over time
cited analytics trends $BUSINESS_ID
cited --json analytics trends $BUSINESS_ID

# Business summary
cited analytics summary $BUSINESS_ID
cited --json analytics summary $BUSINESS_ID

# Compare audit against baseline
cited analytics compare $AUDIT_JOB
```

---

## 11. Agent API (requires API key)

```bash
# Set agent API key
cited config set agent_api_key <your-agent-api-key>

# Business facts
cited agent facts $BUSINESS_ID
cited --json agent facts $BUSINESS_ID

# Verifiable claims
cited agent claims $BUSINESS_ID

# Competitive comparison
cited agent comparison $BUSINESS_ID

# Semantic health
cited agent semantic-health $BUSINESS_ID

# Buyer-fit simulation
cited agent buyer-fit --query "best GEO platform for e-commerce"
cited agent buyer-fit --query "enterprise SEO tool" --business $BUSINESS_ID
cited --json agent buyer-fit --query "best GEO platform" --business $BUSINESS_ID
```

---

## 12. Job Management

```bash
# Watch any job by ID (auto-detects type)
cited job watch $JOB_ID

# Explicit type skips the auto-detect probe (faster, no extra HTTP call)
cited job watch $JOB_ID --type audit
cited job watch $JOB_ID --type recommendations
cited job watch $JOB_ID --type solutions

# Custom poll interval
cited job watch $JOB_ID --interval 5

# Cancel a running job
cited job cancel $JOB_ID
cited job cancel $JOB_ID --type audit
```

---

## 13. Global Flags & Edge Cases

```bash
# JSON mode on everything
cited --json version
cited --json status
cited --json auth status
cited --json business list
cited --json audit list

# Quiet mode (minimal output)
cited --quiet auth status
cited --quiet business list

# No color (for CI/log capture)
cited --no-color business list
cited --no-color status

# Pipe-friendly (auto-detects non-TTY and disables color)
cited business list | cat
cited --json business list | jq '.[0].name'

# Environment switching inline
cited --env dev  status
cited --env prod status
cited --env dev  business list
cited --env prod business list

# Error handling — verify exit codes
cited business get nonexistent-id; echo "Exit: $?"           # 3 (not found)
cited --env dev login --email bad --password bad; echo "Exit: $?"  # 2 (auth error)
cited business update $BUSINESS_ID; echo "Exit: $?"          # 4 (validation — no fields given)
```

---

## 14. Cleanup

```bash
# Delete test business (removes all associated data)
cited business delete $BUSINESS_ID --yes

# Delete test audit template
cited audit template delete $TEMPLATE_ID --yes

# Logout
cited logout
cited auth status   # Should fail with exit code 2
```

### Automated cleanup script

If you forget to clean up (or a run fails partway through), use the cleanup script from the [private infra repo](https://github.com/YouCited/cited-mcp-infra):

```bash
# Dry run — see what would be deleted
python3 ~/repos/cited-mcp-infra/scripts/cleanup_dev.py --dry-run

# Auto — deletes all businesses matching test name patterns (no prompts)
python3 ~/repos/cited-mcp-infra/scripts/cleanup_dev.py --auto
```

The script detects test businesses by name patterns ("E2E Test", "CLI Test", etc.), deletes associated audit templates first, then the business itself.

---

## 15. Python Scripting

Every command supports `--json` output, making the CLI a first-class building block for Python automation. The `subprocess.run` + `json.loads` pattern requires no extra dependencies — just the standard library.

This is the same pattern used by the integration test suite (`tests/test_pipeline.py`).

### Helper functions

```python
import json
import subprocess

ENV = "dev"  # or "prod"

def cited_json(*args: str) -> dict | list:
    """Run a cited command with --json and return parsed output."""
    result = subprocess.run(
        ["cited", "--env", ENV, "--json", *args],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)

def cited_watch(*args: str) -> None:
    """Run a cited command streaming human output live (progress bars, tables)."""
    subprocess.run(["cited", "--env", ENV, *args], check=True)
```

### Full pipeline script

```python
#!/usr/bin/env python3
"""
cited-pipeline.py — Automate a full GEO audit pipeline.

Requirements: `cited` CLI installed and authenticated (`cited login` first).
Usage:        python3 cited-pipeline.py
"""
import json
import subprocess

ENV = "dev"


def cited_json(*args: str) -> dict | list:
    result = subprocess.run(
        ["cited", "--env", ENV, "--json", *args],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def cited_watch(*args: str) -> None:
    subprocess.run(["cited", "--env", ENV, *args], check=True)


# ── Step 1: Create business ───────────────────────────────────────────────────
print("→ Creating business...")
business = cited_json(
    "business", "create",
    "--name",        "Acme Corp",
    "--website",     "https://acme.com",
    "--description", "Acme builds AI-powered tools for enterprise productivity teams.",
    "--industry",    "technology",
)
BUSINESS_ID = business["id"]
print(f"  Business: {BUSINESS_ID}")

# ── Step 2: Scan the website ──────────────────────────────────────────────────
print("→ Scanning website...")
crawl = cited_json("business", "crawl", BUSINESS_ID)
if crawl_job := crawl.get("job_id"):
    cited_watch("job", "watch", crawl_job)

# ── Step 3: Create audit template ────────────────────────────────────────────
print("→ Creating audit template...")
template = cited_json(
    "audit", "template", "create",
    "--name",     "Q4 GEO Audit",
    "--business", BUSINESS_ID,
    "--question", "Are we cited when people ask about AI productivity tools?",
    "--question", "Does our product appear in enterprise software recommendations?",
    "--question", "Are we mentioned when users research our core use case?",
)
TEMPLATE_ID = template["id"]
print(f"  Template: {TEMPLATE_ID}")

# ── Step 4: Run the audit ─────────────────────────────────────────────────────
print("→ Starting audit...")
audit = cited_json("audit", "start", TEMPLATE_ID, "--business", BUSINESS_ID)
AUDIT_JOB = audit["job_id"]
cited_watch("job", "watch", AUDIT_JOB)  # live progress bar in terminal

# ── Step 5: Generate recommendations ─────────────────────────────────────────
print("→ Generating recommendations...")
recommend = cited_json("recommend", "start", AUDIT_JOB)
RECO_JOB = recommend["job_id"]
cited_watch("job", "watch", RECO_JOB)

# ── Step 6: View available insights ──────────────────────────────────────────
print("→ Available insights:")
cited_watch("recommend", "insights", RECO_JOB)  # prints table to terminal

# ── Step 7: Extract source IDs and start a solution ──────────────────────────
# Use --json to get machine-readable data for source_id extraction
result = cited_json("recommend", "result", RECO_JOB)
question_insights = result.get("question_insights", [])

if question_insights:
    # question_id is the source_id for question_insight solutions
    source_id = question_insights[0]["question_id"]
    print(f"→ Solving: {question_insights[0]['question_text'][:60]}...")
    solution = cited_json(
        "solution", "start", RECO_JOB,
        "--type",   "question_insight",
        "--source", source_id,
    )
    SOL_JOB = solution["job_id"]
    print(f"  Solution job:   {SOL_JOB}")
    print(f"  View artifacts: https://{ENV}.youcited.com/solutions/{SOL_JOB}")
else:
    print("  No question insights found.")

print("\n✓ Pipeline complete!")
```

### Ad-hoc scripting examples

```python
# List all businesses and print names
businesses = cited_json("business", "list")
for b in businesses:
    print(b["name"], b["id"])

# Get all audit templates for a business
templates = cited_json("audit", "template", "list", "--business", BUSINESS_ID)
for t in templates:
    print(f"{t['name']} — {len(t['questions'])} questions — {t['id']}")

# Refine template questions (common — auto-generated questions need tuning)
updated = cited_json("audit", "template", "update", TEMPLATE_ID,
    "--question", "Revised question 1",
    "--question", "Revised question 2",
)
print(f"Updated: {len(updated['questions'])} questions")

# Run an audit with multiple providers
audit = cited_json("audit", "start", TEMPLATE_ID,
    "--provider", "openai",
    "--provider", "perplexity",
)

# Extract a summary from a completed recommendation
result = cited_json("recommend", "result", RECO_JOB)
print(f"Questions analyzed:  {result['total_questions']}")
print(f"Wins / Losses / Ties: {result['record_wins']} / {result['record_losses']} / {result['record_ties']}")
print(f"Insights available:  {len(result['question_insights'])} question, "
      f"{len(result['head_to_head_comparisons'])} head-to-head, "
      f"{len(result['strengthening_tips'])} tips")

# Start solutions for ALL question insights automatically
for qi in result["question_insights"]:
    sol = cited_json("solution", "start", RECO_JOB,
        "--type",   "question_insight",
        "--source", qi["question_id"],
    )
    print(f"  Started solution {sol['job_id']} for: {qi['question_text'][:50]}")
```

---

## End-to-End Pipeline

The complete deepest-path test — exercises auth, business CRUD, crawl, audit templates, async jobs, recommendations, insights, solutions, HQ dashboard, and cleanup. Run this against dev before any significant release.

```bash
# ── Setup ─────────────────────────────────────────────────────────────────────
cited config set environment dev
cited login --email <your-email> --password <your-password>
cited auth status   # Verify logged in

# ── Step 1: Create business ────────────────────────────────────────────────────
BUSINESS_ID=$(cited --json business create \
  --name        "E2E Test $(date +%H%M%S)" \
  --website     "https://anthropic.com" \
  --description "End-to-end test business for validating the full CLI pipeline." \
  --industry    "technology" \
  | jq -r '.id')
echo "BUSINESS_ID=$BUSINESS_ID"

# ── Step 2: Scan the website ───────────────────────────────────────────────────
CRAWL_JOB=$(cited --json business crawl $BUSINESS_ID | jq -r '.job_id')
cited job watch $CRAWL_JOB
cited business health $BUSINESS_ID   # view score bars

# ── Step 3: Create audit template ─────────────────────────────────────────────
TEMPLATE_ID=$(cited --json audit template create \
  --name        "E2E Audit Template" \
  --business    $BUSINESS_ID \
  --question    "Are we cited when people ask about AI safety?" \
  --question    "Does our product appear in AI assistant recommendations?" \
  --question    "Are we mentioned for responsible AI development?" \
  | jq -r '.id')
echo "TEMPLATE_ID=$TEMPLATE_ID"

cited audit template get $TEMPLATE_ID   # verify questions

# ── Step 3b: Refine questions (common — auto-generated questions need tuning) ─
cited audit template update $TEMPLATE_ID \
  --question "Are we cited when enterprise buyers ask about AI safety?" \
  --question "Does Anthropic appear in responsible AI tool recommendations?" \
  --question "Are we mentioned when developers compare AI platforms?"

cited audit template get $TEMPLATE_ID   # verify updated questions

# ── Step 4: Run the audit ──────────────────────────────────────────────────────
AUDIT_JOB=$(cited --json audit start $TEMPLATE_ID --business $BUSINESS_ID \
  | jq -r '.job_id')
echo "AUDIT_JOB=$AUDIT_JOB"
cited job watch $AUDIT_JOB

cited audit result $AUDIT_JOB           # view full results
cited audit list --business $BUSINESS_ID

# ── Step 5: Generate recommendations ──────────────────────────────────────────
RECO_JOB=$(cited --json recommend start $AUDIT_JOB | jq -r '.job_id')
echo "RECO_JOB=$RECO_JOB"
cited job watch $RECO_JOB --type recommendations

cited recommend insights $RECO_JOB      # view insights table

# ── Step 6: Start a solution ───────────────────────────────────────────────────
SOURCE_ID=$(cited --json recommend result $RECO_JOB \
  | jq -r '.question_insights[0].question_id')
echo "SOURCE_ID=$SOURCE_ID"

SOL_JOB=$(cited --json solution start $RECO_JOB \
  --type   question_insight \
  --source $SOURCE_ID \
  | jq -r '.job_id')
echo "SOL_JOB=$SOL_JOB"

cited job watch $SOL_JOB --type solutions
# → "View artifacts: https://dev.youcited.com/solutions/$SOL_JOB"

# ── Step 7: HQ dashboard ──────────────────────────────────────────────────────
cited hq $BUSINESS_ID --full
cited analytics trends $BUSINESS_ID

# ── Step 8: Cleanup ────────────────────────────────────────────────────────────
cited audit template delete $TEMPLATE_ID --yes
cited business delete $BUSINESS_ID --yes
cited logout
cited auth status   # Should fail — exit code 2
```
