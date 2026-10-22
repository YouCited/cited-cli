# Cited CLI

Command-line interface for the [Cited](https://youcited.com) GEO (Generative Engine Optimization) platform. See how often ChatGPT, Gemini and Claude cite your business, get recommendations, and generate the fix files, all from the terminal or a script.

## For AI agents

- **Free audit, no login:** call the `free_audit` MCP tool (or run `cited audit free example.com`) to see how AI answers 5 buyer questions about a site, and who it cites instead.
- **MCP server:** `https://mcp.youcited.com/mcp` (streamable HTTP, OAuth login on first use). Also on PyPI as [`cited-mcp`](https://pypi.org/project/cited-mcp/) for local stdio.
- **One-command setup:** `cited agent setup` connects Claude Code, Cursor and Codex (and prints the Claude Desktop connector steps). Add `--dry-run` to preview.
- **No account yet:** `cited agent signup` (or the `agent_signup` tool) creates an account and API key without a login; give your human the claim link and code.
- **Docs:** the `search_docs` tool, or `cited docs search "<question>"`, searches the public [Cited docs](https://youcited.com/docs) without a login.

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
./scripts/dev-install.sh
```

## Quick Start

```bash
cited audit free example.com     # free first look, no account needed
cited login                      # opens the browser
cited status                     # who you are, credits, businesses and the next step
cited business setup --website example.com
cited --help
```

The [workflow](#workflow) section below walks through a paid audit, recommendations and fixes.

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

`cited-mcp` and the hosted server at `mcp.youcited.com` give AI assistants Cited's tools: set up a business, draft questions, run audits, get recommendations and generate fixes.

### Quick setup

```bash
cited agent setup             # configure every AI client found on this machine
cited agent setup --dry-run   # preview the changes first
cited agent setup --client cursor --yes
```

`cited agent setup` merges into your existing config (it never replaces an existing `cited` entry), backs up any file it changes, and supports `--client claude-code|claude-desktop|cursor|codex|all`, `--dry-run`, `--yes` and `--json`. The manual steps for each client follow.

### Claude Code

```bash
claude mcp add --transport http --scope user cited https://mcp.youcited.com/mcp
```

Then run `/mcp` in Claude Code and choose **Authenticate**. For Cited slash commands, skills and the `geo-analyst` agent, also install the plugin:

```
/plugin marketplace add YouCited/cited-plugins
/plugin install cited@youcited-cited-plugins
```

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

With no env vars, call the `login` tool to sign in with a browser, or `agent_signup` to make an account. To reuse a CLI login, get the token with `cited login` then `cited auth token`.

### Cursor

Add to `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` in your project root — or run `cited agent setup --client cursor`:

```json
{
  "mcpServers": {
    "cited": {
      "url": "https://mcp.youcited.com/mcp"
    }
  }
}
```

Open Settings (`Cmd+,`) → **MCP**, click **Login** next to `cited`, and verify it shows a green status. Use tools in Agent mode.

**Fallback** (older Cursor versions without remote-server support) — proxy through [`mcp-remote`](https://www.npmjs.com/package/mcp-remote), which needs Node.js:

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

Or add `[mcp_servers.cited]` with `url = "https://mcp.youcited.com/mcp"` to `~/.codex/config.toml` (`cited agent setup --client codex` does this for you).

### One set of tools everywhere

The tools are defined once, in the Cited API. The hosted server at `mcp.youcited.com`, the local `cited-mcp` server and this CLI all run the same tools (`GET /agent/tools` lists them, `POST /agent/tools/{name}` runs one), so they behave the same. New tools show up in `cited-mcp` without a release; hosted clients may need to reconnect the Cited connector to refresh the cached list.

| Tool | CLI command | What it does |
|------|-------------|--------------|
| `free_audit` | `cited audit free` | Free check of 5 buyer questions about a site (no login) |
| `agent_signup` | `cited agent signup` | Account and API key for an AI agent (no login) |
| `account_status` | `cited status` | Who is signed in, balance, businesses, prices, next step |
| `search_docs` | `cited docs search` / `get` | Search or read the Cited docs (no login) |
| `buy_credits` | `cited credits buy` | Checkout link for a pack or one audit, or redeem a voucher |
| `setup_business` | `cited business setup` | Add a business from its website, or update it |
| `get_business` | `cited business get` | List businesses, or one business in full |
| `get_agent_brief` | `cited business brief` | What to focus on next |
| `draft_questions` | `cited audit questions` | Draft, extend or replace the buyer questions |
| `quote_audit` | `cited audit quote` | What an audit costs, and the models |
| `run_audit` | `cited audit run` | Run a paid audit (asks before spending) |
| `get_audit` | `cited audit get` | List audits, or one audit's status and report |
| `compare_audits` | `cited audit compare` | Citations won and lost between two audits |
| `schedule_recheck` | `cited audit schedule` | Re-run the audit every N days, with alerts |
| `get_recommendations` | `cited recommend list` | What to change, with evidence, status and fixes |
| `update_recommendation` | `cited recommend set` | Mark an item done or dismissed, or open it again |
| `generate_fixes` | `cited fix generate` | Write fix files and steps (asks before spending) |
| `get_fixes` | `cited fix list` / `get` | Fixes, their files, targets and steps |
| `update_fix` | `cited fix done` / `undo` / `verify` | Track a fix and re-check the live site |

`cited-mcp` adds local `login` and `logout` tools. `cited tools list` prints the live list and `cited tools call NAME '{...}'` calls any tool with JSON arguments. See [`packages/mcp/README.md`](packages/mcp/README.md) for the MCP server's details.

### Example

Once connected, ask your assistant something like:

> "Set up Acme Corp from acme.com, draft the buyer questions, and tell me what an audit costs."

It chains the tools: `setup_business` → `draft_questions` → `quote_audit`, then `run_audit` once you approve the price.

### Pricing: pay-as-you-go credits

No plans or tiers: every command and tool works on every account, and work is paid with credits (1 credit = $1). `cited audit quote` shows what an audit costs, and `cited status` shows the balance and prices. `cited credits buy` prints a Stripe checkout link for a person to open; nothing is bought until the balance changes. `cited audit run` and `cited fix generate` show the price and ask before spending (`--yes` skips the question).

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

## Workflow

Commands that need a business take `--business/-b`, which is optional when you have one business (or set `cited config set default_business_id <id>`). Audit commands default to the newest audit.

```bash
# 1. A free first look (no account)
cited audit free acme.com

# 2. Sign in (or `cited agent signup` for an agent) and add the business
cited login
cited business setup --website acme.com
cited business setup --id <business_id> --persona "Ops lead: runs a 20-person warehouse"

# 3. Draft the buyer questions the audit asks, then review them
cited audit questions                       # show them, drafting a set if there is none
cited audit questions --add --count 5 --focus "pricing"
cited audit questions -q "Best WMS for small warehouses?" -q "..."   # replace the set

# 4. Price it and run it
cited audit quote
cited audit run                             # shows the price and asks; --yes to skip
cited audit get --wait                      # status, then the report

# 5. What to change
cited recommend list
cited recommend set <item_key> dismissed

# 6. Fix files, then check them live
cited fix generate --all                    # asks before spending
cited fix list
cited fix get <fix_id> --save ./fixes       # write the files to disk
cited fix done <fix_id>                     # after putting it on the site
cited fix verify <fix_id>                   # re-check the live site (free)

# 7. Keep watching
cited audit schedule --every 30
cited audit compare <audit_id>              # against the audit before it
cited business brief
```

## Scripting

Every command takes `--json` and prints the tool's result unchanged, so the JSON is the same shape an MCP client sees:

```bash
BUSINESS=$(cited --json business setup --website acme.com | jq -r '.business.id')
cited --json audit run -b "$BUSINESS" --yes | jq -r '.audit_id'
cited --json recommend list | jq -r '.items[] | "\(.item_key)\t\(.title)"'
```

`cited tools call` runs any tool with JSON arguments, for anything the commands don't expose:

```bash
cited tools call get_audit '{"limit": 5}'
```

A command that would spend credits without `--yes` prints the price instead and exits 0 in `--json` mode, with `"confirmation_required": true` in the result.

---

## Command Reference

```
cited login | logout | register | status | version
cited auth login|logout|status|token|register
cited config set|get|show|environments

cited agent setup [--client ...] [--dry-run] [--yes]  ← Connect AI clients to Cited
cited agent signup [--name] [--email]               ← Account + API key for an agent (no login)

cited credits buy [PACK_ID] [--one-audit] [--voucher CODE] [--no-save-card]

cited business setup [--website URL | --id ID] [--name ...] [--persona "Name: desc"] ...
cited business get [BUSINESS_ID]
cited business brief [-b ID]

cited audit free URL [--token TOKEN] [--wait/--no-wait]
cited audit questions [-q ...] [--regenerate] [--add] [--count N] [--focus TEXT] [--job ID]
cited audit quote [-m MODEL ...]
cited audit run [-m MODEL ...] [--engine ...] [--country CC] [--deep] [--yes]
cited audit get [AUDIT_ID] [--answers] [--wait] [--limit N]
cited audit compare AUDIT_ID [--baseline ID]
cited audit schedule [--every DAYS | --off] [--email/--no-email] [--webhook URL]

cited recommend list [--audit ID] [--run ID] [--all]
cited recommend set ITEM_KEY open|done|dismissed

cited fix generate [ITEM_KEY ...] [--all] [--yes]
cited fix list [--state STATE]
cited fix get FIX_ID [--save DIR]
cited fix done|undo|verify FIX_ID

cited docs search QUERY | cited docs get PATH
cited tools list | cited tools call NAME [JSON]
cited mcp serve
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

# Use an agent API key instead of `cited login` (sent as X-Agent-API-Key on every
# request; `cited agent signup` saves one for you). A login session takes precedence.
cited config set agent_api_key <key>

# Inspect current config
cited config show
cited config environments
```

> **Tip:** With `output` set to `json`, use `--text` on any command to get human-readable output for that one invocation.

---

## JSON Output

All commands write clean JSON to stdout with `--json`, so they pipe into `jq`, `python3 -c`, or any other tool. Errors always go to **stderr** as `{"error": true, "message": "..."}` so they never corrupt stdout pipelines.

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
| 6 | Payment required (not enough credits, or no purchase yet) |

---

## Development

```bash
./scripts/dev-install.sh
pytest -v
ruff check src/ packages/
mypy packages/core/src packages/mcp/src src/cited_cli/ --ignore-missing-imports
```

`packages/core/src/cited_core/tools.json` is a snapshot of the API's tool list, used when the API can't be reached. Refresh it after the API's tools change:

```bash
python scripts/sync_tools_manifest.py            # from api.youcited.com
python scripts/sync_tools_manifest.py --env dev
```

## Releasing

Release and deployment scripts are in a [private infrastructure repo](https://github.com/YouCited/cited-mcp-infra). See that repo's README for release and deploy instructions.
