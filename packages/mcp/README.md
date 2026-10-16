# cited-mcp

<!-- MCP Registry ownership verification for PyPI (must match "name" in server.json) -->
<!-- mcp-name: com.youcited/cited -->

MCP server for the [Cited](https://youcited.com) Generative Engine Optimization (GEO) platform. Exposes 87 tools that let AI assistants like Claude manage businesses, run GEO audits, generate recommendations, work a prioritized action plan, verify fixes via the Validation Engine, and create solutions — all through the [Model Context Protocol](https://modelcontextprotocol.io/).

## Install

```bash
pip install cited-mcp
```

Or run directly without installing:

```bash
uvx cited-mcp
```

## Usage

The hosted server is at **`https://mcp.youcited.com/mcp`** (streamable HTTP; your browser opens to log in on first use). The `free_audit`, `search_docs` and `get_doc` tools work without logging in.

**Quick setup:** with the [cited-cli](https://pypi.org/project/cited-cli/) installed, `cited agent setup` configures Claude Code, Cursor and Codex for you and prints the Claude Desktop connector steps (`--dry-run` to preview). It merges into existing config and backs up files before changing them.

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

> **Prerequisite:** [Node.js](https://nodejs.org) must be installed for `npx`.

### Claude Desktop (local stdio server)

If you prefer running the server locally:

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

Get your token by running `cited login` and then `cited auth token` with the [cited-cli](https://pypi.org/project/cited-cli/).

### Claude Code

```bash
claude mcp add --transport http --scope user cited https://mcp.youcited.com/mcp
```

Then run `/mcp` in Claude Code and choose **Authenticate**. For Cited slash commands, skills and the `geo-analyst` agent, also install the plugin with `/plugin marketplace add YouCited/cited-plugins` and `/plugin install cited@youcited-cited-plugins`.

### Cursor

Add to `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "cited": {
      "url": "https://mcp.youcited.com/mcp"
    }
  }
}
```

Then in Cursor: open Settings (`Cmd+,`) → **MCP**, click **Login** next to `cited`, and verify it shows a green status indicator. Use Cited tools in Agent mode.

**Fallback** (older Cursor versions without remote-server support) — proxy through [`mcp-remote`](https://www.npmjs.com/package/mcp-remote), which needs Node.js (`node --version` should print v18+):

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

### Codex

```bash
codex mcp add cited --url https://mcp.youcited.com/mcp
codex mcp login cited
```

Or add `[mcp_servers.cited]` with `url = "https://mcp.youcited.com/mcp"` to `~/.codex/config.toml`.

### Standalone

```bash
# Local stdio mode (requires CITED_TOKEN env var)
CITED_TOKEN=your-jwt-token cited-mcp

# Remote HTTP mode (used for hosted deployment)
cited-mcp-remote
```

### Updating to new Cited features

Cited adds new tools regularly. To access new tools after a release, **disconnect and reconnect the Cited connector** in your Claude Desktop or Claude.ai connector settings — restarting Claude alone is not enough, because the connector's tool list is cached at registration time. Once reconnected, ask the agent to call `whats_new` to see what changed since you last connected.

## Tools

### Auth & meta
| Tool | Description |
|------|-------------|
| `ping` | Readiness check — returns server version, tool count, and tool-surface fingerprint |
| `check_auth_status` | Check current authentication status |
| `login` | Authenticate via browser OAuth flow |
| `logout` | Clear stored authentication token |
| `whats_new` | Diff the current tool surface against a prior fingerprint or version |

### Credits (1 credit = $1)
| Tool | Description |
|------|-------------|
| `get_prices` | Credit prices, audit cost and packs (no login) |
| `get_credits` | Balance, purchases (lots), saved card and auto-refill settings |
| `credit_history` | Credit transactions: purchases, spends, returns, refunds, expiries |
| `buy_credits` | Checkout link for a credit pack (claimed accounts) |
| `buy_audit` | $15 checkout link for one audit (any account) |
| `request_refund` | Refund unused credits bought in the last 30 days (asks for confirmation) |
| `set_auto_refill` | Turn auto-refill on or off, with pack and monthly cap |
| `quote_audit` | Credits an audit will cost before starting it |

### Agent signup & keys
| Tool | Description |
|------|-------------|
| `agent_signup` | Create an account and API key for this agent (no login); returns a claim link and code for the human |
| `key_status` | Agent key state: unclaimed, expiry, notice, OAuth instructions |
| `list_api_keys` | List the account's agent API keys |
| `revoke_api_key` | Revoke an agent API key |

### Businesses
| Tool | Description |
|------|-------------|
| `list_businesses` | List all businesses on your account |
| `get_business` | Get details for a specific business |
| `create_business` | Create a new business |
| `update_business` | Update business details |
| `delete_business` | Delete a business |
| `crawl_business` | Start a website crawl for a business |
| `get_health_scores` | Get GEO health scores for a business |
| `get_usage_stats` | Get credit balance, business count and audit count |

### Audit Templates
| Tool | Description |
|------|-------------|
| `list_audit_templates` | List all audit templates |
| `get_audit_template` | Get a specific template with questions |
| `create_audit_template` | Create a new audit template |
| `update_audit_template` | Update template name, description, or questions |
| `delete_audit_template` | Delete an audit template |

### Docs (no login)
| Tool | Description |
|------|-------------|
| `search_docs` | Search the public Cited documentation by keyword; returns doc paths, titles, and descriptions |
| `get_doc` | Read one doc as markdown by its `category/slug` path |

### Audits
| Tool | Description |
|------|-------------|
| `free_audit` | Free GEO audit of any website, no login needed. Call again with the same URL for progress and the full report |
| `start_audit` | Run a GEO audit using a template |
| `get_audit_status` | Check audit job status |
| `get_audit_result` | Get completed audit results |
| `list_audits` | List all audits |
| `export_audit` | Export a completed audit as a PDF report |

### Recommendations
| Tool | Description |
|------|-------------|
| `start_recommendation` | Generate recommendations from a completed audit |
| `get_recommendation_status` | Check recommendation job status |
| `get_recommendation_result` | Get full recommendation results |
| `get_recommendation_insights` | Get actionable insights with risk levels and coverage scores |
| `list_recommendations` | List all recommendation jobs |
| `get_recommendation_check_status` | Run all 62 deterministic GEO/SEO checks (Validation Engine) — counts + per-check detail |
| `validate_recommendation` | Re-run the deterministic check for a single recommendation |
| `get_recommendation_validation_latest` | Fetch the latest stored validation result for a recommendation |

### Solutions
| Tool | Description |
|------|-------------|
| `start_solution` | Generate a solution for a specific insight or tip |
| `start_solutions_batch` | Start up to 10 solutions in one call |
| `get_solution_status` | Check solution job status |
| `get_solution_result` | Get completed solution with implementation steps |
| `list_solutions` | List all solutions |

### Jobs
| Tool | Description |
|------|-------------|
| `get_job_status` | Check status of any job by type and ID |
| `cancel_job` | Cancel a running job |

### HQ Dashboard
| Tool | Description |
|------|-------------|
| `get_business_hq` | Get comprehensive business dashboard with health scores, personas, products |

### Analytics
| Tool | Description |
|------|-------------|
| `get_analytics_trends` | Get KPI trends over time |
| `get_analytics_dashboard` | Combined analytics dashboard (KPI trends + question performance + benchmarks) |
| `compare_audits` | Compare an audit against its baseline |

### Agent API
| Tool | Description |
|------|-------------|
| `get_business_facts` | Get structured business facts |
| `get_business_claims` | Get verifiable claims about a business |
| `get_competitive_comparison` | Get competitive analysis data |
| `get_semantic_health` | Get semantic readiness signals |
| `buyer_fit_query` | Run a buyer-fit simulation query |

### Action Plan
| Tool | Description |
|------|-------------|
| `get_action_plan` | Get a prioritised checklist of next steps to improve GEO |
| `get_quick_wins` | Get low-effort, high-impact actions to tackle first |
| `mark_action_done` | Mark a priority action as completed |
| `dismiss_action` | Dismiss a priority action as not applicable |
| `get_action_progress` | Get progress summary (completed vs remaining) |

## Example Workflow

Once connected, ask Claude to run a full GEO audit:

> "List my businesses, then run a GEO audit on Acme Corp using the default template. When it's done, generate recommendations and show me the top insights."

Claude will chain the tools automatically:

1. `list_businesses` → find the business ID
2. `list_audit_templates` → find or create a template
3. `start_audit` → kick off the audit
4. `get_audit_status` → poll until complete
5. `start_recommendation` → generate recommendations
6. `get_recommendation_insights` → display actionable results
7. `start_solution` → generate implementation steps for top issues

## Pricing: pay-as-you-go credits

There are no plans or tiers: every tool is available to every account, and work is paid for
with credits (1 credit = $1). A standard audit costs 10 credits (up to 5 questions with each
engine's included models; each further 5 questions adds 10, each extra model 2). Call
`quote_audit` before `start_audit` to see the cost. Recommendations, solutions, crawls and
question regeneration need the account to have bought credits at least once. A one-off audit
costs $15 (`buy_audit`, works for unclaimed agent accounts); packs (`buy_credits`) need a
claimed account. Purchases return a Stripe `checkout_url` for the human to open — no tool
charges a card on its own.

When an account is short of credits, tools return HTTP 402 details the agent can act on:

```json
{
  "error": true,
  "status_code": 402,
  "payment_required": true,
  "error_type": "insufficient_credits",
  "message": "This audit needs 10 credits; you have 2.",
  "credits_needed": 10,
  "balance": 2,
  "buy_url": "https://youcited.com/app/billing",
  "hint": "Not enough credits. Show the human buy_url, or call 'buy_credits' ..."
}
```

`error_type` is `insufficient_credits`, `purchase_required` (402) or `claim_required` (403, an
unclaimed agent account tried something that needs a person to claim it; includes `claim_url`).

## Agent signup and keys

An agent with no Cited account can call `agent_signup` (no login needed). It gets its own API
key, saved locally and sent as `X-Agent-API-Key` on every call, on an unclaimed account (1
business, 1 audit, deleted after 7 days unless claimed). The agent shows its human the claim
link and 6-digit code; claiming moves everything into the human's account, and the key then
expires 90 days later. While a key has an expiry, API responses carry an `X-Cited-Notice`
header, which every tool result surfaces as a top-level `notice` field. Connecting the hosted
server (`https://mcp.youcited.com/mcp`) with OAuth does not expire. The hosted server also
accepts an agent key as its Bearer token.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CITED_TOKEN` | JWT auth token (stdio mode) |
| `CITED_AGENT_API_KEY` | Per-user agent API key (alternative to JWT; `agent_signup` saves one for you) |
| `CITED_API_URL` | API base URL (default: `https://api.youcited.com`) |
| `CITED_ENV` | Environment: `prod`, `dev`, or `local` |
| `MCP_URL` | Public URL of this MCP server (remote mode) |
| `JWT_SECRET` | Secret for signing OAuth tokens (remote mode) |

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e packages/core
pip install -e "packages/mcp[dev]"

# Run tests
pytest tests/test_mcp_tools.py tests/test_mcp_server.py packages/mcp/tests/ -v

# Lint and type check
ruff check packages/mcp/
mypy packages/mcp/src --ignore-missing-imports
```

## Privacy Policy

See our [Privacy Policy](https://youcited.com/privacy) for details on data collection, usage, storage, and third-party sharing.

## License

Proprietary — see [youcited.com](https://youcited.com) for terms.
