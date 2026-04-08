# cited-mcp

MCP server for the [Cited](https://youcited.com) Generative Engine Optimization (GEO) platform. Exposes 28 tools that let AI assistants like Claude manage businesses, run GEO audits, generate recommendations, and create solutions — all through the [Model Context Protocol](https://modelcontextprotocol.io/).

## Install

```bash
pip install cited-mcp
```

Or run directly without installing:

```bash
uvx cited-mcp
```

## Usage

### Claude Desktop (remote server — recommended)

No local install required. Add this to your Claude Desktop config (`Settings → Developer → Edit Config`):

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

Restart Claude Desktop. A browser window will open for authentication on first use.

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
| `get_solution_status` | Check solution job status |
| `get_solution_result` | Get completed solution with implementation steps |
| `list_solutions` | List all solutions |

### Jobs
| Tool | Description |
|------|-------------|
| `get_job_status` | Check status of any job by type and ID |

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
pytest tests/test_mcp_server.py tests/test_mcp_tools.py -v

# Lint and type check
ruff check packages/mcp/
mypy packages/mcp/src --ignore-missing-imports
```

## Privacy Policy

See our [Privacy Policy](https://youcited.com/privacy) for details on data collection, usage, storage, and third-party sharing.

## License

Proprietary — see [youcited.com](https://youcited.com) for terms.
