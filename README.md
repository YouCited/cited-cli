# Cited CLI

Command-line interface for the [Cited](https://youcited.com) GEO (Generative Engine Optimization) platform. Audit how often your business is cited by AI assistants, generate recommendations, and produce AI-ready content solutions — all from the terminal or a Python script.

## Installation

### Homebrew (recommended)

```bash
brew tap youcited/cited
brew install cited
```

### From source (development)

```bash
git clone https://github.com/YouCited/cited-cli.git
cd cited-cli
pip install -e ".[dev]"
```

## Quick Start

```bash
# Log in (opens browser by default)
cited login

# Check you're connected
cited status

# List your businesses
cited business list

# See all commands
cited --help
cited audit --help
cited audit template --help
```

For the full end-to-end workflow — creating a business, running a GEO audit, and generating content solutions — see the [GEO Audit Pipeline](#geo-audit-pipeline) section below.

---

## Authentication

```bash
# Browser login (default — opens youcited.com login page)
cited login

# Specific OAuth provider
cited login --provider google
cited login --provider microsoft
cited login --provider github

# Password login (non-interactive / CI)
cited login --email you@example.com --password "Secret123!"

# Check status
cited auth status

# Log out
cited logout
```

**Password registration** is a two-step email-verification flow:

```bash
cited register --email you@example.com --name "Your Name" --password "Secret123!"
# → Check your inbox, paste the verification URL when prompted
```

---

## MCP Server

This repo also includes `cited-mcp`, a [Model Context Protocol](https://modelcontextprotocol.io/) server that exposes 47 tools for AI assistants like Claude. It lets Claude manage businesses, run GEO audits, generate recommendations, and create solutions on your behalf.

### Claude Desktop (Custom Connector — recommended)

No local install required. Claude connects to Cited's hosted MCP server directly:

1. Open Claude Desktop → **Settings** → **Customize > Connectors**
2. Click **"+"** → **"Add custom connector"**
3. Enter URL: `https://mcp.youcited.com/mcp`
4. Click **Add**

Your browser will open for authentication on first use. See [Anthropic's connector guide](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp) for details.

> **Requires:** Claude Pro, Max, Team, or Enterprise plan.

### Claude Desktop (Developer Config — alternative)

If Custom Connectors aren't available, use the developer config with `mcp-remote`:

```json
{
  "mcpServers": {
    "cited": {
      "command": "npx",
      "args": ["mcp-remote", "https://mcp.youcited.com/mcp"]
    }
  }
}
```

Add to `Settings → Developer → Edit Config`, then restart Claude Desktop.

> **Prerequisite:** [Node.js](https://nodejs.org) (LTS) must be installed for `npx`.

### Claude Desktop (local stdio)

```json
{
  "mcpServers": {
    "cited": {
      "command": "uvx",
      "args": ["cited-mcp"],
      "env": {
        "CITED_TOKEN": "your-jwt-token"
      }
    }
  }
}
```

Get your token with `cited login` then `cited auth token`.

### Cursor

Add a `.cursor/mcp.json` file to your project root (or `~/.cursor/mcp.json` for global access):

```json
{
  "mcpServers": {
    "cited": {
      "command": "npx",
      "args": ["mcp-remote", "https://mcp.youcited.com/mcp"]
    }
  }
}
```

Verify Node.js is installed (`node --version`), or install with `brew install node`.

Open Settings (`Cmd+,`) → search "MCP" → verify the server shows a green status. Use tools in Composer (Agent mode).

### Updating to new Cited features

Cited adds new tools regularly. To access new tools after a release, **disconnect and reconnect the Cited connector** in your Claude Desktop or Claude.ai connector settings — restarting Claude alone is not enough, because the connector's tool list is cached at registration time. Once reconnected, ask the agent to call `whats_new` to see what changed since you last connected.

### Example

Once connected, ask Claude something like:

> "List my businesses, then run a GEO audit on Acme Corp using the default template. When it's done, generate recommendations and show me the top insights."

Claude will chain the tools automatically — `list_businesses` → `start_audit` → `get_audit_status` → `start_recommendation` → `get_recommendation_insights`.

### Available Tools

| Category | Tools |
|----------|-------|
| **Auth** | `check_auth_status`, `login`, `logout` |
| **Businesses** | `list_businesses`, `get_business`, `create_business`, `update_business`, `delete_business`, `crawl_business`, `get_health_scores`, `get_usage_stats` |
| **Audit Templates** | `list_audit_templates`, `get_audit_template`, `create_audit_template`, `update_audit_template`, `delete_audit_template` |
| **Audits** | `start_audit`, `get_audit_status`, `get_audit_result`, `list_audits`, `export_audit` |
| **Recommendations** | `start_recommendation`, `get_recommendation_status`, `get_recommendation_result`, `get_recommendation_insights`, `list_recommendations` |
| **Solutions** | `start_solution`, `get_solution_status`, `get_solution_result`, `list_solutions` |
| **Jobs** | `get_job_status`, `cancel_job` |
| **HQ** | `get_business_hq` |
| **Analytics** | `get_analytics_trends`, `get_analytics_summary`, `compare_audits` |
| **Agent API** | `get_business_facts`, `get_business_claims`, `get_competitive_comparison`, `get_semantic_health`, `buyer_fit_query` |

See [`packages/mcp/README.md`](packages/mcp/README.md) for full details, environment variables, and development instructions.

---

## Global Flags

These flags apply to every command and must be placed immediately after `cited`:

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Machine-readable JSON output (great for scripting) |
| `--text` | `-t` | Human-readable text output (overrides `output` config) |
| `--env` | `-e` | Environment: `dev`, `prod`, `local` (default: `prod`) |
| `--profile` | `-p` | Config profile to use |
| `--verbose` | `-v` | Debug logging |
| `--quiet` | `-q` | Minimal output |
| `--no-color` | | Disable colors (auto-applied when stdout is not a TTY) |

---

## GEO Audit Pipeline

The complete workflow from business registration through AI-ready content solutions. Each step captures an ID for the next — just like piping commands together.

### Prerequisites

- `jq` installed (`brew install jq`) for ID extraction in bash
- A publicly resolvable website domain (not `example.com`)
- Account logged in: `cited login`

### Step 1 — Create your business profile

```bash
BUSINESS_ID=$(cited --json business create \
  --name        "Acme Corp" \
  --website     "https://acme.com" \
  --description "Acme builds AI-powered tools for enterprise productivity teams." \
  --industry    "technology" \
  | jq -r '.id')

echo "Business: $BUSINESS_ID"
```

> **`--industry` must be one of:**
> `automotive` `beauty` `consulting` `education` `entertainment` `finance`
> `fitness` `government` `healthcare` `home_services` `hospitality` `legal`
> `manufacturing` `non_profit` `real_estate` `restaurant` `retail` `technology` `other`

### Step 2 — Scan your website

The crawler reads your site so the platform understands your content, products, and brand signals.

```bash
CRAWL_JOB=$(cited --json business crawl $BUSINESS_ID | jq -r '.job_id')
cited job watch $CRAWL_JOB

# View crawl results as health score bars
cited business health $BUSINESS_ID
```

### Step 3 — Create an audit template

An audit template defines the questions you want AI assistants to answer. Ask questions your target buyers would actually type.

```bash
TEMPLATE_ID=$(cited --json audit template create \
  --name     "Q4 GEO Audit" \
  --business $BUSINESS_ID \
  --question "Are we cited when people ask about AI productivity tools?" \
  --question "Does our product appear in enterprise software recommendations?" \
  --question "Are we mentioned when users research our core use case?" \
  | jq -r '.id')

echo "Template: $TEMPLATE_ID"

# List all templates for a business
cited audit template list --business $BUSINESS_ID

# Inspect a template
cited audit template get $TEMPLATE_ID
```

Auto-generated questions are rarely perfect out of the box. Refine them before running the audit:

```bash
# Replace all questions (--question flags replace the full list)
cited audit template update $TEMPLATE_ID \
  --question "Are we cited when enterprise buyers ask about AI safety?" \
  --question "Does our product appear in responsible AI recommendations?" \
  --question "Are we mentioned when developers compare AI platforms?"

# Update just the name (keeps existing questions)
cited audit template update $TEMPLATE_ID --name "Q4 GEO Audit v2"

# Verify changes
cited audit template get $TEMPLATE_ID
```

### Step 4 — Run the audit

```bash
AUDIT_JOB=$(cited --json audit start $TEMPLATE_ID --business $BUSINESS_ID \
  | jq -r '.job_id')

# Watch live progress bar
cited job watch $AUDIT_JOB

# View results: per-question citation data across providers
cited audit result $AUDIT_JOB
```

### Step 5 — Generate recommendations

```bash
RECO_JOB=$(cited --json recommend start $AUDIT_JOB | jq -r '.job_id')
cited job watch $RECO_JOB
```

### Step 6 — Discover what to fix

`recommend insights` prints a table of all actionable items with the source IDs you'll need for the next step:

```bash
cited recommend insights $RECO_JOB
```

```
                          Available Insights
┏━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ # ┃ Type              ┃ Source ID                ┃ Description              ┃
┡━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1 │ question_insight  │ d5b17bda-fa5b-48ff-...   │ Are we cited for AI...   │
│ 2 │ head_to_head      │ wikipedia.org            │ wikipedia.org            │
│ 3 │ strengthening_tip │ llms_txt                 │ Create llms.txt for AI   │
└───┴───────────────────┴──────────────────────────┴──────────────────────────┘

Run a solution: cited solution start $RECO_JOB --type <type> --source <source_id>
```

### Step 7 — Generate a content solution

Pick a row from the insights table and pass its type and source ID:

```bash
cited solution start $RECO_JOB \
  --type   question_insight \
  --source d5b17bda-fa5b-48ff-8238-a644c78b404a

# → ✓ Solution Started
# → Track progress: cited job watch <sol_job_id>
# → View artifacts: https://app.youcited.com/solutions/<sol_job_id>
```

**`--type` values:** `question_insight` · `head_to_head` · `strengthening_tip` · `priority_action`

> Rich solution artifacts (blog posts, FAQ schemas, structured content) are rendered in the web app.
> The CLI prints the direct link so you can jump straight there.

---

## Scripting & Automation

Every command supports `--json` output, making the CLI a first-class building block for automation pipelines — in bash, Python, or any language that can run a subprocess.

### Bash with `jq`

```bash
# Capture IDs by piping --json output through jq
BUSINESS_ID=$(cited --json business create --name "..." --website "..." \
  --description "..." --industry "technology" | jq -r '.id')

TEMPLATE_ID=$(cited --json audit template create \
  --name "My Audit" --business $BUSINESS_ID \
  --question "Are we cited for X?" | jq -r '.id')

AUDIT_JOB=$(cited --json audit start $TEMPLATE_ID | jq -r '.job_id')
cited job watch $AUDIT_JOB

RECO_JOB=$(cited --json recommend start $AUDIT_JOB | jq -r '.job_id')
cited job watch $RECO_JOB

# Extract first question insight source_id
SOURCE_ID=$(cited --json recommend result $RECO_JOB \
  | jq -r '.question_insights[0].question_id')

cited solution start $RECO_JOB --type question_insight --source $SOURCE_ID
```

### Python

The CLI is a thin, authenticated HTTP wrapper — Python scripts can drive it directly via `subprocess` with no extra dependencies. This is the same pattern used by the integration test suite.

```python
#!/usr/bin/env python3
"""
cited-pipeline.py — Automate a full GEO audit pipeline.

Requirements: `cited` CLI installed and authenticated (`cited login` first).
Usage:        python3 cited-pipeline.py
"""
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


# ── Step 1: Create business ───────────────────────────────────────────────────
print("→ Creating business...")
business = cited_json(
    "business", "create",
    "--name",        "Acme Corp",
    "--website",     "https://acme.com",
    "--description", "Acme builds AI-powered tools for enterprise productivity teams.",
    "--industry",    "technology",
)
business_id = business["id"]
print(f"  Business: {business_id}")

# ── Step 2: Scan the website ──────────────────────────────────────────────────
print("→ Scanning website...")
crawl = cited_json("business", "crawl", business_id)
if crawl_job := crawl.get("job_id"):
    cited_watch("job", "watch", crawl_job)

# ── Step 3: Create audit template ────────────────────────────────────────────
print("→ Creating audit template...")
template = cited_json(
    "audit", "template", "create",
    "--name",     "Q4 GEO Audit",
    "--business", business_id,
    "--question", "Are we cited when people ask about AI productivity tools?",
    "--question", "Does our product appear in enterprise software recommendations?",
    "--question", "Are we mentioned when users research our core use case?",
)
template_id = template["id"]
print(f"  Template: {template_id}")

# ── Step 3b: Refine questions (auto-generated questions usually need tuning) ─
print("→ Refining template questions...")
updated = cited_json(
    "audit", "template", "update", template_id,
    "--question", "Are we cited when enterprise buyers ask about AI safety?",
    "--question", "Does our product appear in responsible AI recommendations?",
    "--question", "Are we mentioned when developers compare AI platforms?",
)
print(f"  Updated: {len(updated['questions'])} questions")

# ── Step 4: Run the audit ─────────────────────────────────────────────────────
print("→ Starting audit...")
audit = cited_json("audit", "start", template_id, "--business", business_id)
audit_job = audit["job_id"]
cited_watch("job", "watch", audit_job)

# ── Step 5: Generate recommendations ─────────────────────────────────────────
print("→ Generating recommendations...")
recommend = cited_json("recommend", "start", audit_job)
reco_job = recommend["job_id"]
cited_watch("job", "watch", reco_job)

# ── Step 6: View available insights ──────────────────────────────────────────
print("→ Available insights:")
cited_watch("recommend", "insights", reco_job)

# ── Step 7: Start a content solution ─────────────────────────────────────────
# Extract source IDs directly from the JSON result
result = cited_json("recommend", "result", reco_job)
question_insights = result.get("question_insights", [])

if question_insights:
    source_id = question_insights[0]["question_id"]
    print(f"→ Solving: {question_insights[0]['question_text'][:60]}...")
    solution = cited_json(
        "solution", "start", reco_job,
        "--type",   "question_insight",
        "--source", source_id,
    )
    sol_job = solution["job_id"]
    print(f"  Solution job:    {sol_job}")
    print(f"  View artifacts:  https://{ENV}.youcited.com/solutions/{sol_job}")

print("\n✓ Pipeline complete!")
```

The `cited_json()` / `cited_watch()` pattern — capture IDs from `--json` output, stream human output for long-running jobs — is exactly what the integration test suite uses internally with mocked HTTP responses.

---

## Command Reference

```
cited login                               Log in (top-level alias)
cited logout                              Log out (top-level alias)
cited register                            Register new account (top-level alias)
cited status                              API health check
cited version                             Show CLI version

cited auth login|logout|register|status|token

cited config set|get|show|environments

cited business list|get|create|update|delete|health|crawl

cited audit template list|get|create|update|delete   ← Manage audit templates
cited audit start|status|result|list|export   ← Run and inspect audits

cited recommend start|status|result|list      ← Generate recommendations
cited recommend insights                      ← View actionable source table

cited solution start|status|result|list       ← Generate content solutions

cited hq <business_id> [--full] [--personas] [--products] [--intents] [--actions]

cited analytics compare|trends|summary

cited agent facts|claims|comparison|semantic-health|buyer-fit

cited job watch|cancel
```

---

## Configuration

Config is stored in `~/.cited/config.toml`:

```bash
# Set default environment (saves typing --env dev every time)
cited config set environment dev

# Set default output format (saves typing --json every time)
cited config set output json    # or "text" (default)

# Set a default business (used by commands that accept --business)
cited config set default_business_id <uuid>

# Set Agent API key (for cited agent commands)
cited config set agent_api_key <key>

# Inspect current config
cited config show
cited config environments
```

> **Tip:** With `output` set to `json`, use `--text` on any command to get human-readable output for that one invocation.

---

## JSON Output

All commands write clean JSON to stdout with `--json`, enabling pipelines with `jq`, `python3 -c`, or any other tool:

```bash
# Extract specific fields
cited --json business list | jq '.[].name'
cited --json audit result <id> | jq '.overall_citation_rate'
cited --json recommend result <id> | jq '.question_insights[].question_text'

# Save full results
cited --json audit result <id> > audit.json
cited --json recommend result <id> > recommendations.json

# Count citations by provider
cited --json audit result <id> | jq '[.citations_pulled[].provider_name] | group_by(.) | map({provider: .[0], count: length})'
```

Errors always go to **stderr** as `{"error": true, "message": "..."}` so they never corrupt stdout pipelines.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Authentication error |
| 3 | Not found |
| 4 | Validation error |
| 5 | Rate limited |

---

## Development

```bash
pip install -e ".[dev]"
pytest -v                                       # All tests
pytest tests/test_pipeline.py -v               # Pipeline integration tests
ruff check src/
mypy src/cited_cli/ --ignore-missing-imports
```

## Releasing

Release and deployment scripts are in a [private infrastructure repo](https://github.com/YouCited/cited-mcp-infra). See that repo's README for release and deploy instructions.
