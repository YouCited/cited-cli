# Future Enhancements

## MCP Integration: `cited mcp serve`

Expose CLI commands as [Model Context Protocol](https://modelcontextprotocol.io/) tools, making the Cited platform directly callable from Claude Code, Cursor, Windsurf, and other MCP-compatible agents.

### What it does

`cited mcp serve` starts a stdio-based MCP server that exposes each CLI command as a tool. An AI agent can then call tools like `cited_business_list`, `cited_audit_start`, `cited_hq` directly without shelling out.

### Implementation

**New command (`src/cited_cli/commands/mcp.py`):**
```python
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server

mcp_app = typer.Typer(name="mcp", help="MCP server for AI agent integration.")

@mcp_app.command("serve")
def mcp_serve(ctx: typer.Context):
    """Start MCP server exposing CLI commands as tools."""
    server = Server("cited-cli")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(name="cited_status", description="Check API health", inputSchema={...}),
            Tool(name="cited_business_list", description="List businesses", inputSchema={...}),
            Tool(name="cited_audit_start", description="Start audit", inputSchema={...}),
            # ... one tool per CLI command
        ]

    @server.call_tool()
    async def call_tool(name, arguments):
        # Route to the appropriate API client call
        # Always return JSON (same as --json mode)
        ...

    asyncio.run(stdio_server(server))
```

**New dependency:**
```toml
# pyproject.toml
dependencies = [
    ...,
    "mcp>=1.0.0",
]
```

**Register in app.py:**
```python
from cited_cli.commands.mcp import mcp_app
app.add_typer(mcp_app, name="mcp")
```

### User configuration

Users add the server to their MCP client config. For Claude Code (`.claude/settings.json`):
```json
{
  "mcpServers": {
    "cited": {
      "command": "cited",
      "args": ["mcp", "serve", "--env", "dev"]
    }
  }
}
```

### Tools to expose

Priority tools for agent use (all return JSON):

| Tool | Maps to | Description |
|------|---------|-------------|
| `cited_status` | `cited status` | API health check |
| `cited_business_list` | `cited business list` | List businesses |
| `cited_business_get` | `cited business get` | Business details |
| `cited_business_health` | `cited business health` | Health scores |
| `cited_business_crawl` | `cited business crawl` | Trigger crawl |
| `cited_audit_start` | `cited audit start` | Start audit |
| `cited_audit_status` | `cited audit status` | Job status |
| `cited_audit_result` | `cited audit result` | Audit results |
| `cited_recommend_start` | `cited recommend start` | Generate recommendations |
| `cited_recommend_result` | `cited recommend result` | Recommendation results |
| `cited_solution_start` | `cited solution start` | Generate solution |
| `cited_solution_result` | `cited solution result` | Solution results |
| `cited_hq` | `cited hq` | Business HQ dashboard |
| `cited_analytics_trends` | `cited analytics trends` | KPI trends |
| `cited_agent_facts` | `cited agent facts` | Business facts |
| `cited_agent_claims` | `cited agent claims` | Verifiable claims |
| `cited_agent_buyer_fit` | `cited agent buyer-fit` | Buyer-fit simulation |

### Design notes

- The MCP server reuses the same `CitedClient` and auth from the CLI — no separate auth flow needed
- All tool responses are JSON (equivalent to `--json` mode)
- The server inherits `--env` and `--profile` from the `cited mcp serve` invocation
- Long-running operations (audit, recommend, solution) should return the job ID immediately, letting the agent poll status separately

---

## Shell Completions: `cited completions`

Generate shell completion scripts for bash, zsh, and fish. Typer has built-in support for this but it needs to be exposed as a command.

```bash
# Generate and install completions
cited completions zsh > ~/.zfunc/_cited
cited completions bash > /etc/bash_completion.d/cited
cited completions fish > ~/.config/fish/completions/cited.fish
```

Typer provides this via `typer.main.get_command(app).get_help()` and Click's shell completion utilities.

---

## Batch Operations

### `cited audit batch`

Run multiple audit templates in sequence or parallel, collecting results into a single report.

```bash
# Run all templates for a business
cited audit batch --business $BID --all

# Run specific templates
cited audit batch --business $BID --template $T1 --template $T2

# Export combined results
cited audit batch --business $BID --all --export results.json
```

### `cited business import`

Bulk-create businesses from a CSV or JSON file for agencies managing multiple clients.

```bash
cited business import clients.csv
cited business import --format json clients.json
```

---

## Diff and History

### `cited audit diff`

Compare two audit runs side-by-side to show citation changes over time.

```bash
cited audit diff $JOB_ID_1 $JOB_ID_2
```

Output would show per-question citation deltas (gained/lost citations, score changes) in a Rich table.

### `cited analytics export`

Export historical analytics data to CSV/JSON for external analysis or dashboarding.

```bash
cited analytics export --business $BID --from 2026-01-01 --to 2026-03-20 --format csv > trends.csv
```

---

## Interactive Mode: `cited interactive`

A REPL-style session that keeps auth and business context loaded, reducing repetitive flags:

```bash
$ cited interactive --business $BID --env dev
cited> audit template list
cited> audit start $TEMPLATE_ID
cited> job watch $JOB_ID
cited> recommend start $JOB_ID
```

Would use `prompt_toolkit` for readline-style history, tab completion, and inline help.

---

## Webhooks: `cited webhook`

Register webhook URLs to get notified when jobs complete, instead of polling with `job watch`.

```bash
cited webhook create --event job.completed --url https://example.com/hook
cited webhook list
cited webhook delete $WEBHOOK_ID
```

Requires backend support for webhook delivery.
