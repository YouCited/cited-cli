# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Monorepo for the [Cited](https://youcited.com) GEO platform tooling. Contains three Python packages:

- **`cited-core`** (`packages/core/`) — Shared library: API client, auth, config, endpoints, errors. No CLI or MCP dependencies.
- **`cited-mcp`** (`packages/mcp/`) — Standalone MCP server with 30 tools. Depends on `cited-core` + `mcp` SDK. Installable via `pip install cited-mcp` or `uvx cited-mcp`.
- **`cited-cli`** (root `src/cited_cli/`) — Typer + Rich CLI. Depends on `cited-core` + `typer` + `rich`. Optional dep on `cited-mcp` for `cited mcp serve`.

Also contains `cited-plugins/` — a Claude Code plugin (skills, commands, agents) that references the MCP server via `uvx cited-mcp`.

The backend API lives in a separate monorepo at `~/repos/cited/`.

## Commands

```bash
# Dev setup (install all three packages in editable mode)
./scripts/dev-install.sh

# Or manually:
pip install -e packages/core
pip install -e packages/mcp
pip install -e ".[dev]"

# Run tests, lint, type check
pytest -v                    # Run all tests
ruff check src/ packages/    # Lint all packages
mypy packages/core/src packages/mcp/src src/cited_cli/ --ignore-missing-imports

# Run the CLI
cited --help

# Run the standalone MCP server
cited-mcp                    # Standalone binary (from cited-mcp package)
cited mcp serve              # Via CLI (requires cited-cli[mcp])

# Release and deploy scripts are in the private infra repo:
# ~/repos/cited-mcp-infra (github.com/YouCited/cited-mcp-infra)
```

## Architecture

### Package Structure

**`cited-core`** (`packages/core/src/cited_core/`) — Zero CLI/MCP dependencies:
- `api/client.py` — `CitedClient` (httpx sync)
- `api/endpoints.py` — API endpoint path constants
- `auth/store.py` — `TokenStore` (keyring + file fallback)
- `auth/oauth_server.py` — Temporary localhost OAuth callback server
- `config/manager.py` — `ConfigManager` (TOML config)
- `config/constants.py` — `ENVIRONMENTS`, `CONFIG_DIR`, `VALID_INDUSTRIES`, etc.
- `errors.py` — `CitedAPIError`, `ExitCode`, `exit_code_for_status()`

**`cited-mcp`** (`packages/mcp/src/cited_mcp/`) — MCP server + 42 tools:
- `server.py` — `FastMCP` instance, lifespan, `run_server()`
- `tools/` — auth, business, audit, recommend, solution, job tool modules
- `plan_gating.py` — Per-plan tool access control (growth/scale/pro tiers)
- `auth_provider.py` — OAuth provider with stateless JWT tokens and user JWT expiry detection
- Supports `CITED_TOKEN` and `CITED_AGENT_API_KEY` env vars
- Includes browser OAuth `login` tool for Claude Desktop users
- Remote server (`remote.py`) runs stateless HTTP with Fargate Spot auto-scaling

**`cited-cli`** (`src/cited_cli/`) — Typer CLI:
- Imports core modules from `cited_core.*` (not `cited_cli.api.*`)
- `utils/errors.py` re-exports `CitedAPIError` etc. from `cited_core.errors` + adds `handle_api_error()` (Rich-based)
- `commands/mcp_cmd.py` lazy-imports from `cited_mcp` (optional dep)

### CLI Architecture

**Entry point:** `src/cited_cli/app.py` — creates the root `typer.Typer`, registers subcommand groups via `app.add_typer()`, plus top-level `login` and `logout` commands (delegating to `do_login`/`do_logout` from `commands/auth.py`). Defines global flags (`--json`, `--env`, `--profile`, etc.) in the `main_callback`, and stores shared state in `typer.Context.obj`.

**Global state flow:** The callback populates `ctx.obj` with `OutputContext`, `ConfigManager`, profile name, and env override. Every command extracts these via a `_get_ctx()` or `_get_client()` helper at the top of each command module.

**Dual output mode:** Every command must support both human (Rich) and JSON (`--json`) output. The pattern is:
```python
print_result(data, out, human_formatter=lambda d, c: render_kv("Title", d, c))
```
`print_result` writes `json.dumps(data)` to stdout in JSON mode, or calls the `human_formatter` otherwise. Errors always go to stderr.

**Output format resolution:** The output format is resolved with this precedence: `--json` flag → `--text` flag → config value (`cited config set output json|text`) → default (`text`). This lets users set `output = "json"` in config for scripting workflows and override back to human-readable with `--text` / `-t` for a single invocation.

**Authentication:** Top-level `cited login` is the primary entry point (also available as `cited auth login` for backward compat). Both delegate to `do_login()` / `do_logout()` in `commands/auth.py`.

- **Browser login (default):** `cited login` opens the youcited login page in the browser. The CLI starts a temporary localhost HTTP server (`auth/oauth_server.py`) to receive the OAuth callback token. The success page includes a collapsible token-copy section for the paste fallback.
- **OAuth provider shortcut:** `cited login --provider google|microsoft|github` sends the user directly to that provider.
- **Password login:** `cited login --email user@example.com` prompts for password (or use `--password` for non-interactive/CI).
- **Password registration:** `cited register --email ... --name ... --password ...` is a two-step flow:
  1. `POST /auth/cli-register` — creates the account and sends a verification email; returns `{"message": "..."}` (201, **no token**).
  2. CLI prompts the user to paste the verification URL from their inbox (e.g. `https://app.youcited.com/complete-registration?token=<43-char-token>`).
  3. CLI parses the `?token=` query param and calls `POST /auth/cli-verify-email {"token": "..."}`.
  4. Backend marks email verified and returns `{"token": "<JWT>", "user": {...}}`; JWT is stored; prints "Email verified! Logged in as {email}".
  - Endpoint constant: `endpoints.CLI_VERIFY_EMAIL = "/auth/cli-verify-email"`.
  - Tests mock both endpoints and supply the verification URL via `input=` on `runner.invoke`.
- **Paste fallback:** If the localhost callback times out (firewall, WSL, SSH), the CLI prompts the user to paste the token shown on the browser success page.
- **Token storage:** Per-environment via OS keychain (`keyring`) with a file fallback (`~/.cited/credentials.json`). The token is sent back to the API as a cookie, not a Bearer header.
- **TTY detection:** `commands/auth.py` uses `_is_interactive()` (wrapping `sys.stdin.isatty()`) for all TTY checks — tests monkeypatch this helper.

**Agent API auth** uses a separate path: `X-Agent-API-Key` header, configured via `cited config set agent_api_key` or `CITED_AGENT_API_KEY` env var.

**Adding a new command group:**
1. Create `src/cited_cli/commands/<name>.py` with a `typer.Typer()` instance
2. Add endpoint paths to `src/cited_cli/api/endpoints.py`
3. Register in `app.py` with `app.add_typer(..., name="<name>")`

**Adding a nested command group (sub-subcommands):**
Create the inner Typer in a separate file, then register it on the parent app — not on the root app. Example: `audit template` lives in `commands/named_audit.py` and is registered in `app.py` as:
```python
audit_app.add_typer(named_audit_app, name="template")
```
This gives `cited audit template list|get|create|update|delete` while `cited audit start|status|...` remain top-level on `audit_app`. Crucially, the nested registration must happen **before** `app.add_typer(audit_app, ...)` — in practice, put it at the top of the registration block in `app.py`.

**Adding a new command to an existing group:** Add a function decorated with `@<group>_app.command()` in the relevant command file. Follow the `_get_client()` → try/except `CitedAPIError` → `print_result()` pattern.

**Audit template workflow:** The typical flow is create → review → refine → run audit. Auto-generated questions are rarely perfect, so `audit template update` is a common operation. The `--question` flags on `update` **replace all** existing questions (matching the web editor's save behavior). Omit `--question` to keep existing questions unchanged while updating name/description. Backend endpoint: `PUT /named-audits/{id}` with `NamedAuditUpdate` schema.

## CLI / MCP Feature Parity

**Every new feature must be added to BOTH the CLI and MCP server.** A test (`tests/test_feature_parity.py`) enforces this — it compares all CLI commands against MCP tools and fails if a command exists in one but not the other.

When adding a new feature:
1. Add the CLI command in `src/cited_cli/commands/`
2. Add the MCP tool in `packages/mcp/src/cited_mcp/tools/`
3. Add the tool to `plan_gating.py` (in the appropriate tier set)
4. Update the `_CLI_TO_MCP` mapping in `tests/test_feature_parity.py`
5. If the feature is intentionally one-interface-only, add it to `CLI_ONLY` or `MCP_ONLY` with a comment explaining why

## Key Conventions

- **Exit codes:** 0=success, 1=error, 2=auth, 3=not found, 4=validation, 5=rate limited (defined in `utils/errors.py`)
- **Line length:** 100 chars (ruff enforced)
- **All files** start with `from __future__ import annotations`
- **Type hints** use `X | None` syntax, not `Optional[X]`
- **Valid config keys:** `environment`, `default_business_id`, `agent_api_key`, `output` (values: `json`, `text`)
- **Config module** is named `config_cmd.py` (not `config.py`) to avoid shadowing stdlib
- **Tests** use `typer.testing.CliRunner` (fixtures `runner` and `cli_app` in `conftest.py`), `respx` for HTTP mocking, and `monkeypatch` to redirect `CONFIG_DIR`/`CONFIG_FILE`/`CREDENTIALS_FILE` to `tmp_path`
- **User config** lives at `~/.cited/config.toml`; version is in `src/cited_cli/__init__.py`
- **Version** single source of truth is `packages/core/src/cited_core/__init__.py`. The CLI and MCP packages import it via `from cited_core import __version__`. The `version =` field in all three `pyproject.toml` files must also be bumped (the release script handles this).

## Releasing & Deployment

Release, deploy, and infrastructure scripts live in the **private** repo `~/repos/cited-mcp-infra` ([YouCited/cited-mcp-infra](https://github.com/YouCited/cited-mcp-infra)):

- `scripts/release.sh <version>` — Bumps version, publishes to PyPI, updates Homebrew tap
- `scripts/deploy-mcp.sh <env>` — Deploys MCP server to AWS ECS Fargate
- `scripts/cleanup_dev.py` — Removes test data from dev environment
- `docker/Dockerfile` — Docker image for the remote MCP server

**Prerequisites:** clean git state on `main`, `gh` CLI authenticated, `.venv` with cited-cli installed, `~/repos/homebrew-cited` cloned.

**Homebrew tap repo:** `~/repos/homebrew-cited` (`YouCited/homebrew-cited` on GitHub). Contains a single formula `Formula/cited.rb` that installs cited-cli into a Python virtualenv with pinned dependency hashes. The formula uses `Language::Python::Virtualenv` and depends on `python@3.12` and `rust` (build-time, for `pydantic-core`).

## API Environments

| Name | URL | Default |
|------|-----|---------|
| prod | `https://api.youcited.com` | yes |
| dev  | `https://dev.youcited.com` | |
| local | `http://localhost:8000` | |

## Real API Response Field Names (Critical)

These field names were confirmed against the live dev API on 2026-03-18. Using the wrong names produces silently empty output (no error, just blank table cells). Always check the live response shape before adding new field access.

### `GET /recommendations/{job_id}/result` (used by `recommend insights` + `recommend result`)

```python
{
    "question_insights": [
        {
            "question_id":   "uuid",      # ← source_id for solution start; NOT "id"
            "question_text": "...",       # ← description field; NOT "question"
            "risk_level":    "high",
            "coverage_score": 0.33,
        }
    ],
    "head_to_head_comparisons": [         # ← key name; NOT "head_to_head"
        {
            "competitor_domain": "competitor.com",  # ← source_id; no uuid id field
            "competitor_url":    "https://...",
            "business_domain":   "...",
            "overall_winner":    "business",
        }
    ],
    "strengthening_tips": [
        {
            "category": "llms_txt",       # ← source_id for solution start; no uuid id field
            "title":    "Create llms.txt for AI Discovery",
            "priority": "high",
        }
    ],
    "priority_actions": [],
}
```

### `POST /solutions/request` (used by `solution start`)

```json
{
    "recommendation_job_id": "<uuid>",
    "source_type": "question_insight",
    "source_id": "<question_id from question_insights>"
}
```

**`source_type` enum:** `question_insight` · `head_to_head` · `strengthening_tip` · `priority_action`

This endpoint replaced the deprecated `POST /solutions/create` which took `{"recommendation_id": ...}`.

### `POST /businesses/{id}/crawl` (used by `business crawl`)

Returns a `job_id` in the response body — you can `job watch` the crawl:
```json
{
    "message":     "Crawl job enqueued",
    "business_id": "...",
    "job_id":      "...",
    "status":      "crawling"
}
```

### `POST /businesses` (used by `business create`)

- `industry` must be one of: `automotive` `beauty` `consulting` `education` `entertainment` `finance` `fitness` `government` `healthcare` `home_services` `hospitality` `legal` `manufacturing` `non_profit` `real_estate` `restaurant` `retail` `technology` `other`
- `website` must be a publicly DNS-resolvable domain — fabricated domains (e.g. `example.com`, `acme-test.example.com`) will return 422
- `description` minimum ~50 characters

### `POST /audit/start` (used by `audit start`)

```json
{
    "named_audit_id": "<template uuid>",
    "business_id":    "<optional override>"
}
```

The old shape `{"business_id": ...}` returns 422 — `named_audit_id` is required.

## Testing Patterns

Tests use `respx` for HTTP mocking. Key patterns from `tests/test_pipeline.py`:

**Pre-seeding a login token** (avoids needing to mock the auth flow):
```python
def _setup_logged_in(tmp_path, monkeypatch):
    # redirect config to tmp_path, then write credentials
    creds_file.write_text(json.dumps({"dev": "test-jwt-dev-token"}))
```

**Mocking `watch_job`** to avoid `time.sleep` and Rich `Live` renderer in tests:
```python
monkeypatch.setattr(
    "cited_cli.commands.job.watch_job",
    lambda client, path, console, poll_interval=2.0: {"status": "completed", "job_id": "..."},
)
```

**Threading IDs between commands** (the `--json` pattern):
```python
result = runner.invoke(app, ["--env", "dev", "--json", "business", "create", ...])
business_id = json.loads(result.output)["id"]  # thread into next command
```

**Verifying request payload** (not just response):
```python
captured_body = {}
def _capture(request):
    captured_body.update(json.loads(request.content))
    return httpx.Response(202, json=MOCK_RESPONSE)
respx.post(f"{DEV_API}/audit/start").mock(side_effect=_capture)
# ... invoke command ...
assert captured_body["named_audit_id"] == TEMPLATE_ID
assert "recommendation_id" not in captured_body  # old field must not appear
```
