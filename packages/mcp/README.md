# cited-mcp

MCP server for the [Cited](https://youcited.com) Generative Engine Optimization (GEO) platform. Exposes 44 tools that let AI assistants like Claude manage businesses, run GEO audits, generate recommendations, and create solutions — all through the [Model Context Protocol](https://modelcontextprotocol.io/).

## Install

```bash
pip install cited-mcp
```

Or run directly without installing:

```bash
uvx cited-mcp
```

## Usage

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

Add the remote server as a tool source in your Claude Code settings or use the `cited-plugins/` configuration from the monorepo.

### Cursor

Add a `.cursor/mcp.json` file to your project root (or configure globally in `~/.cursor/mcp.json`):

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

Verify Node.js is installed first:

```bash
node --version   # should print v18+ or v20+
```

If not installed, run `brew install node` or download from [nodejs.org](https://nodejs.org).

Then in Cursor: open Settings (`Cmd+,`) → search "MCP" → verify the server appears and shows a green status indicator. Use Cited tools in Composer (Agent mode) or Chat by asking Claude to interact with your GEO data.

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

### Auth
| Tool | Description |
|------|-------------|
| `check_auth_status` | Check current authentication status |
| `login` | Authenticate via browser OAuth flow |
| `logout` | Clear stored authentication token |

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
| `get_usage_stats` | Get account usage statistics and plan info |

### Audit Templates
| Tool | Description |
|------|-------------|
| `list_audit_templates` | List all audit templates |
| `get_audit_template` | Get a specific template with questions |
| `create_audit_template` | Create a new audit template |
| `update_audit_template` | Update template name, description, or questions |
| `delete_audit_template` | Delete an audit template |

### Audits
| Tool | Description |
|------|-------------|
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
| `get_analytics_summary` | Get aggregated analytics summary |
| `compare_audits` | Compare an audit against its baseline |

### Agent API
| Tool | Description |
|------|-------------|
| `get_business_facts` | Get structured business facts |
| `get_business_claims` | Get verifiable claims about a business |
| `get_competitive_comparison` | Get competitive analysis data |
| `get_semantic_health` | Get semantic readiness signals |
| `buyer_fit_query` | Run a buyer-fit simulation query |

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

## Plan-Based Tool Access

Tools are gated by subscription tier. All tiers can read data; write operations require higher plans.

| Tier | Tools Available |
|------|----------------|
| **Growth** (entry) | Auth, list/get businesses, crawl, health scores, audits (start/status/result/list), all recommendation tools, job status — **19 tools** |
| **Scale** | Everything in Growth + create/update/delete businesses, create/update/delete audit templates, all solution tools, batch solutions, export audit, cancel job — **33 tools** |
| **Pro** | Everything in Scale + usage stats, HQ dashboard, analytics, agent API — **44 tools** |

When a user calls a tool above their plan, the server returns a structured error with an upgrade link:

```json
{
  "error": true,
  "message": "The 'create_business' tool requires the Scale plan or higher.",
  "upgrade_url": "https://app.youcited.com/settings/billing",
  "required_tier": "scale",
  "current_tier": "growth"
}
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CITED_TOKEN` | JWT auth token (stdio mode) |
| `CITED_AGENT_API_KEY` | Agent API key (alternative to JWT) |
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
