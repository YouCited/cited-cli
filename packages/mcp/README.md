# cited-mcp

<!-- MCP Registry ownership verification for PyPI (must match "name" in server.json) -->
<!-- mcp-name: com.youcited/cited -->

MCP server for [Cited](https://youcited.com): check whether ChatGPT, Gemini, Claude and Google AI Mode cite your website when buyers ask about what you sell, and get the fixes that get you cited. 21 tools over the [Model Context Protocol](https://modelcontextprotocol.io/): the 19 Cited tools, the same ones the hosted server at `mcp.youcited.com` serves, plus local `login` and `logout`.

## Install

```bash
pip install cited-mcp
```

Or run directly without installing:

```bash
uvx cited-mcp
```

## Usage

The hosted server is at **`https://mcp.youcited.com/mcp`** (streamable HTTP; your browser opens to log in on first use). The `free_audit`, `account_status`, `agent_signup` and `search_docs` tools work without logging in.

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
cited-mcp                          # stdio; uses `cited login`, CITED_TOKEN or an agent key
CITED_ENV=dev cited-mcp            # another environment
```

The tools are defined once, in the Cited API. On start the server reads the current list from `GET https://api.youcited.com/agent/tools` (falling back to the copy bundled with `cited-core`) and runs each call through `POST /agent/tools/{name}`, so it always behaves like the hosted server.

### Updating to new Cited features

Clients cache the tool list. After a Cited release, reconnect the connector (or restart a local `cited-mcp`) to pick up new tools.

## Tools

Start with `account_status`: it says who is signed in, the credit balance, the businesses and the next step.

| Tool | What it does | Login |
|------|--------------|-------|
| `free_audit` | Free check of how AI answers 5 buyer questions about a site; poll with `report_token` | no |
| `agent_signup` | Create an account for your human without a login; the key is saved locally, the claim link and code are returned | no |
| `account_status` | Who is signed in, balance, businesses, prices, next step | no |
| `search_docs` | Search the Cited docs, or read one with `path` | no |
| `buy_credits` | Checkout link for a credit pack or one audit, or redeem a voucher | yes |
| `setup_business` | Add a business from its website, or update it, its buyer personas and offerings | yes |
| `get_business` | List businesses, or one business's profile, questions, schedule and recent audits | yes |
| `get_agent_brief` | What to focus on next for a business | yes |
| `draft_questions` | Draft, extend or replace the buyer questions the audit asks | yes |
| `quote_audit` | What an audit costs, the balance and the models | yes |
| `run_audit` | Run a paid audit; returns the price first, spends only with `confirm=true` | yes |
| `get_audit` | List audits, or one audit's status and report | yes |
| `compare_audits` | Citations won and lost against an earlier audit | yes |
| `schedule_recheck` | Re-run the audit every N days, email and webhook alerts | yes |
| `get_recommendations` | What to change, with item keys, evidence, status and fixes | yes |
| `update_recommendation` | Mark an item done or dismissed, or open it again | yes |
| `generate_fixes` | Write fix files and steps for items (or all); asks before spending | yes |
| `get_fixes` | List fixes, or one fix's files, targets and steps | yes |
| `update_fix` | `done`, `undo`, or `verify` the fix on the live site | yes |
| `login` | Browser sign-in that stores a session on this machine (local server only) | no |
| `logout` | Forget the session or saved agent key (local server only) | no |

## Example Workflow

1. `account_status`, then `free_audit` with the website for a free first look.
2. `agent_signup` (or `login`), then `setup_business` with the website.
3. `draft_questions`, review them with the user, then `quote_audit`.
4. `run_audit` (the user approves the price), then `get_audit` until it finishes.
5. `get_recommendations`, `generate_fixes`, `get_fixes` for the files, then `update_fix` with `done` and `verify`.

## Pricing: pay-as-you-go credits

No plans or subscriptions. 1 credit = $1; `account_status` and `quote_audit` show current prices. Purchase tools only return a Stripe checkout link for a person to open: nothing is bought until `account_status` shows the new balance. A short balance comes back as an error with `status_code` 402 and `credits_needed`.

## Agent signup and keys

`agent_signup` makes an unclaimed account for an AI agent. The API key is saved on this machine (the OS keychain, or `~/.cited/credentials.json`) and used for every call; it is never shown to the model. Give your human the claim link and 6-digit code so they keep the account. `logout` forgets the key.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CITED_TOKEN` | A Cited session token (`cited login`, then `cited auth token`). Optional. |
| `CITED_AGENT_API_KEY` | A Cited agent key (`cak_...`). Optional; `agent_signup` saves one for you. |
| `CITED_ENV` | `prod` (default), `dev` or `local`. |

## Development

```bash
pip install -e ../core -e ".[dev]"
pytest
ruff check src/ && mypy src/ --ignore-missing-imports
```

## Privacy Policy

See [youcited.com/privacy](https://youcited.com/privacy).

## License

Proprietary — see [youcited.com](https://youcited.com) for terms.
