# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Monorepo for the [Cited](https://youcited.com) GEO platform tooling. Contains three Python packages:

- **`cited-core`** (`packages/core/`) — Shared library: API client, auth, config, endpoints, errors, and the tool client (`tools.py`). No CLI or MCP dependencies.
- **`cited-mcp`** (`packages/mcp/`) — Local stdio MCP server: Cited's agent tools plus local `login`/`logout`. Depends on `cited-core` + `mcp` SDK. Installable via `pip install cited-mcp` or `uvx cited-mcp`.
- **`cited-cli`** (root `src/cited_cli/`) — Typer + Rich CLI. Depends on `cited-core` + `typer` + `rich`. Optional dep on `cited-mcp` for `cited mcp serve`.

Also contains `cited-plugins/` — a Claude Code plugin (skills, commands, agents) that points at the hosted MCP server.

The backend API lives in a separate monorepo at `~/repos/cited/` (YouCited/cited).

## One tool definition

The agent tools are defined **once**, in the backend (`backend/services/agent_tools/` in YouCited/cited). The backend serves them three ways:

- the hosted MCP server at `https://mcp.youcited.com/mcp` (`routes/mcp.py`, OAuth),
- `GET /agent/tools` — the manifest (name, title, description, input schema, annotations, `version`, `instructions`),
- `POST /agent/tools/{name}` — runs one tool with a JSON object of arguments and returns its result (errors come back as `{"error", "status_code", "error_type", ...}` with the HTTP status).

This repo holds **thin clients** of those endpoints. `cited-mcp` lists the manifest and forwards each call; every CLI data command turns its options into one tool call. Tool behavior, wording and next steps change in the backend, not here. To add or change a tool, change the backend first, then add or adjust the CLI command, then refresh the bundled snapshot.

The tools (19): `free_audit`, `agent_signup`, `account_status`, `search_docs` (no login), `buy_credits`, `setup_business`, `get_business`, `get_agent_brief`, `draft_questions`, `quote_audit`, `run_audit`, `get_audit`, `compare_audits`, `schedule_recheck`, `get_recommendations`, `update_recommendation`, `generate_fixes`, `get_fixes`, `update_fix`. `run_audit` and `generate_fixes` return `{"confirmation_required": true, ...price}` unless called with `confirm=true`.

## Commands

```bash
# Dev setup (install all three packages in editable mode)
./scripts/dev-install.sh

# Run tests, lint, type check
pytest -v
ruff check src/ packages/
mypy packages/core/src packages/mcp/src src/cited_cli/ --ignore-missing-imports

# Refresh the bundled tool manifest after backend tool changes
python scripts/sync_tools_manifest.py [--env dev|local]

# Run the CLI / the MCP server
cited --help
cited-mcp                    # Standalone binary (from cited-mcp package)
cited mcp serve              # Via CLI (requires cited-cli[mcp])

# Release and deploy scripts are in the private infra repo:
# ~/repos/cited-mcp-infra (github.com/YouCited/cited-mcp-infra)
```

## Architecture

### Package Structure

**`cited-core`** (`packages/core/src/cited_core/`) — Zero CLI/MCP dependencies:
- `tools.py` — `fetch_manifest()` (API, falling back to the bundled `tools.json`), `call_tool()` (`POST /agent/tools/{name}` → `(result, status)`, never raises for API errors), `run_tool()` (also saves the key `agent_signup` returns via `keep_agent_key` and strips it from the result)
- `tools.json` — snapshot of `GET /agent/tools`; refreshed by `scripts/sync_tools_manifest.py`
- `api/client.py` — `CitedClient` (httpx sync); records the `X-Cited-Notice` header as `last_notice`
- `api/endpoints.py` — API endpoint path constants (auth, config)
- `auth/store.py` — `TokenStore` (keyring + file fallback); also stores per-env agent keys (`agent_key:<env>`)
- `auth/credentials.py` — `resolve_agent_api_key()` (env var → config → saved key)
- `auth/oauth_server.py` — Temporary localhost OAuth callback server
- `config/manager.py` — `ConfigManager` (TOML config)
- `config/constants.py` — `ENVIRONMENTS`, `CONFIG_DIR`, etc.
- `errors.py` — `CitedAPIError`, `ExitCode`, `exit_code_for_status()`

**`cited-mcp`** (`packages/mcp/src/cited_mcp/server.py`) — one module, low-level `mcp.server.lowlevel.Server` over stdio:
- `build_session()` — credentials (`CITED_TOKEN` or the stored login, else the agent key from `CITED_AGENT_API_KEY` / `agent_api_key` config / the key `agent_signup` saved) and the manifest
- `tool_list()` — the manifest's tools plus `LOCAL_TOOLS` (`login`, `logout`)
- `call()` — local tools run here; everything else goes through `cited_core.tools.run_tool`. Adds `notice` from the API header and a login hint on 401; `isError` when status ≥ 400
- The hosted server is the backend's; this package no longer has a remote/HTTP mode

**`cited-cli`** (`src/cited_cli/`) — Typer CLI:
- `utils/tools.py` — `call()` / `run()` / `poll()` run one tool and print it; `COMMAND_FOR_TOOL` + `as_commands()` rewrite tool names in next steps into CLI commands; `render()` is the default human formatter
- `commands/` — `account.py` (`status`, `credits buy`), `agent.py` (`setup`, `signup`), `business.py`, `audit.py`, `recommend.py`, `fix.py`, `docs.py`, `tools_cmd.py` (`tools list|call`), plus local `auth.py`, `config_cmd.py`, `mcp_cmd.py`
- `utils/errors.py` re-exports `CitedAPIError` etc. from `cited_core.errors` + adds `handle_api_error()` (Rich-based)

### CLI Architecture

**Entry point:** `src/cited_cli/app.py` — creates the root `typer.Typer`, registers subcommand groups via `app.add_typer()`, plus top-level `login`, `logout`, `register` and `status`. Defines global flags (`--json`, `--env`, `--profile`, etc.) in the `main_callback`, and stores shared state in `typer.Context.obj`.

**A data command is one tool call:**
```python
@fix_app.command("verify")
def verify(ctx: typer.Context, fix_id: Annotated[str, typer.Argument()]) -> None:
    """Re-check the live site for a fix (free)."""
    run(ctx, "update_fix", {"fix_id": fix_id, "action": "verify"})
```
Use `clean({...})` to drop options the user didn't give, so the tool's defaults apply. `--json` prints the tool result unchanged (same shape an MCP client sees); otherwise the command's human formatter (or `render`). Tool errors exit with the code for their status via `handle_api_error`. Spending commands (`audit run`, `fix generate`) show the price and `typer.confirm` unless `--yes`; in `--json` or non-interactive mode they print the `confirmation_required` result instead.

**Output format resolution:** `--json` flag → `--text` flag → config value (`cited config set output json|text`) → default (`text`).

**Authentication:** Top-level `cited login` is the primary entry point (also `cited auth login`). Both delegate to `do_login()` / `do_logout()` in `commands/auth.py`.

- **Browser login (default):** opens the youcited login page; a temporary localhost server (`auth/oauth_server.py`) receives the token. The success page includes a token-copy section for the paste fallback.
- **OAuth provider shortcut:** `cited login --provider google|microsoft|github`.
- **Password login:** `cited login --email user@example.com` prompts for password (or `--password` for CI).
- **Password registration:** `cited register --email ... --name ... --password ...` calls `POST /auth/cli-register` (sends a verification email, no token), then prompts for the verification URL, parses `?token=` and calls `POST /auth/cli-verify-email`, which returns `{"token", "user"}`. Tests supply the URL via `input=` on `runner.invoke`.
- **Paste fallback:** if the localhost callback times out (firewall, WSL, SSH), the CLI prompts for the token shown on the success page.
- **Token storage:** per environment via OS keychain (`keyring`) with a file fallback (`~/.cited/credentials.json`). The token is sent to the API as a cookie, not a Bearer header.
- **TTY detection:** `commands/auth.py` uses `_is_interactive()` for TTY checks — tests monkeypatch it.

**Agent keys:** per-user agent keys (`cak_...`) authenticate via the `X-Agent-API-Key` header. Sources, in order: `CITED_AGENT_API_KEY`, `cited config set agent_api_key`, then the key saved by `cited agent signup` / the `agent_signup` tool (never printed or returned to the model). A login session takes precedence: the CLI sends the key only when there is no token. `cited logout` / the `logout` tool forget a saved key when there is no session.

## CLI / MCP Feature Parity

**Every tool must have a CLI command, and every CLI command must run a tool** (or be listed as CLI-only). `tests/test_feature_parity.py` enforces this against the bundled manifest.

When the backend adds a tool:
1. Run `python scripts/sync_tools_manifest.py` to refresh `tools.json`
2. Add the CLI command in `src/cited_cli/commands/` and its entry in `COMMAND_FOR_TOOL` (`utils/tools.py`)
3. Map it in `CLI_TO_TOOL` in `tests/test_feature_parity.py` (commands with no tool go in `CLI_ONLY` with a reason)
4. Update the tool tables in `README.md` and `packages/mcp/README.md`, and the plugin skills in `cited-plugins/` if the workflow changed

## Key Conventions

- **Exit codes:** 0=success, 1=error, 2=auth, 3=not found, 4=validation, 5=rate limited, 6=payment required (HTTP 402) (defined in `cited_core/errors.py`, re-exported by `utils/errors.py`)
- **Line length:** 100 chars (ruff enforced)
- **All files** start with `from __future__ import annotations`
- **Type hints** use `X | None` syntax, not `Optional[X]`
- **Valid config keys:** `environment`, `default_business_id`, `agent_api_key`, `output` (values: `json`, `text`)
- **Config module** is named `config_cmd.py` (not `config.py`) to avoid shadowing stdlib
- **Tests** use `typer.testing.CliRunner` (fixtures `runner`, `cli_app` and `creds` in `conftest.py`), `respx` for HTTP mocking, and `monkeypatch` to redirect `CONFIG_DIR`/`CONFIG_FILE`/`CREDENTIALS_FILE` to `tmp_path`
- **User config** lives at `~/.cited/config.toml`
- **Version** single source of truth is `packages/core/src/cited_core/__init__.py`. The CLI and MCP packages import it via `from cited_core import __version__`. The `version =` field in all three `pyproject.toml` files must also be bumped (the release script handles this).

## Releasing & Deployment

Release and infrastructure scripts live in the **private** repo `~/repos/cited-mcp-infra` ([YouCited/cited-mcp-infra](https://github.com/YouCited/cited-mcp-infra)):

- `scripts/release.sh <version>` — Bumps version, publishes to PyPI, updates Homebrew tap
- `scripts/cleanup_dev.py` — Removes test data from dev environment

The hosted MCP server ships with the backend (merges to `main` in YouCited/cited deploy prod); there is no separate MCP deploy.

**Prerequisites:** clean git state on `main`, `gh` CLI authenticated, `.venv` with cited-cli installed, `~/repos/homebrew-cited` cloned.

**Homebrew tap repo:** `~/repos/homebrew-cited` (`YouCited/homebrew-cited` on GitHub). Contains a single formula `Formula/cited.rb` that installs cited-cli into a Python virtualenv with pinned dependency hashes. The formula uses `Language::Python::Virtualenv` and depends on `python@3.12` only: keep Rust-built packages such as `pydantic` out of cited-core and cited-cli, because `release.sh` then adds `rust` (and its ~2GB llvm) as a build dependency. Homebrew 7 only loads formulae from trusted taps, so docs must say `brew install youcited/cited/cited` (never the old tap-then-install pair), and existing users run `brew trust --formula youcited/cited/cited` before `brew upgrade cited`. Never tell users to trust the whole tap.

## API Environments

| Name | URL | Default |
|------|-----|---------|
| prod | `https://api.youcited.com` | yes |
| dev  | `https://dev.youcited.com` | |
| local | `http://localhost:8000` | |

## Credits Billing

No plans or tiers. Billing is pay-as-you-go credits (1 credit = $1). `account_status` / `quote_audit` show current prices. Purchase tools only return a Stripe `checkout_url` for a person to open; they never claim a payment happened. A short balance is a 402 with `credits_needed` (exit code 6).

## Testing Patterns

CLI tests mock `POST /agent/tools/{name}` with `respx` and check the arguments the command sent:

```python
captured = {}
def _capture(request):
    captured.update(json.loads(request.content))
    return httpx.Response(200, json={"status": "running", "audit_id": "a1"})
respx.post(f"{API}/agent/tools/run_audit").mock(side_effect=_capture)
result = runner.invoke(app, ["--json", "audit", "run", "--yes"])
assert captured["confirm"] is True
```

`tests/test_mcp_server.py` runs the MCP server in memory with an `mcp` client session; `packages/mcp/tests/` covers `login`/`logout` and the call path.
