# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Standalone CLI for the [Cited](https://youcited.com) GEO platform. Built with Python (Typer + Rich + httpx). Talks to the Cited backend API — does not contain any backend code itself. The backend lives in a separate monorepo at `~/repos/cited/`.

## Commands

```bash
pip install -e ".[dev]"      # Install with dev dependencies
pytest -v                    # Run all tests
pytest tests/test_auth.py    # Run a single test file
pytest -k test_version_json  # Run a single test by name
ruff check src/              # Lint
mypy src/cited_cli/ --ignore-missing-imports  # Type check
cited --help                 # Run the CLI
```

## Architecture

**Entry point:** `src/cited_cli/app.py` — creates the root `typer.Typer`, registers 10 subcommand groups via `app.add_typer()`, defines global flags (`--json`, `--env`, `--profile`, etc.) in the `main_callback`, and stores shared state in `typer.Context.obj`.

**Global state flow:** The callback populates `ctx.obj` with `OutputContext`, `ConfigManager`, profile name, and env override. Every command extracts these via a `_get_ctx()` or `_get_client()` helper at the top of each command module.

**Dual output mode:** Every command must support both human (Rich) and JSON (`--json`) output. The pattern is:
```python
print_result(data, out, human_formatter=lambda d, c: render_kv("Title", d, c))
```
`print_result` writes `json.dumps(data)` to stdout in JSON mode, or calls the `human_formatter` otherwise. Errors always go to stderr.

**Authentication:** The CLI authenticates by POSTing to `/auth/login` and extracting the JWT from the `advgeo_session` Set-Cookie header (not the response body). Tokens are stored per-environment via OS keychain (`keyring`) with a file fallback (`~/.cited/credentials.json`). The token is sent back to the API as a cookie, not a Bearer header.

**Agent API auth** uses a separate path: `X-Agent-API-Key` header, configured via `cited config set agent_api_key` or `CITED_AGENT_API_KEY` env var.

**Adding a new command group:**
1. Create `src/cited_cli/commands/<name>.py` with a `typer.Typer()` instance
2. Add endpoint paths to `src/cited_cli/api/endpoints.py`
3. Register in `app.py` with `app.add_typer(..., name="<name>")`

**Adding a new command to an existing group:** Add a function decorated with `@<group>_app.command()` in the relevant command file. Follow the `_get_client()` → try/except `CitedAPIError` → `print_result()` pattern.

## Key Conventions

- **Exit codes:** 0=success, 1=error, 2=auth, 3=not found, 4=validation, 5=rate limited (defined in `utils/errors.py`)
- **Line length:** 100 chars (ruff enforced)
- **All files** start with `from __future__ import annotations`
- **Type hints** use `X | None` syntax, not `Optional[X]`
- **Config module** is named `config_cmd.py` (not `config.py`) to avoid shadowing stdlib
- **Tests** use `typer.testing.CliRunner` (fixtures `runner` and `cli_app` in `conftest.py`), `respx` for HTTP mocking, and `monkeypatch` to redirect `CONFIG_DIR`/`CONFIG_FILE`/`CREDENTIALS_FILE` to `tmp_path`
- **User config** lives at `~/.cited/config.toml`; version is in `src/cited_cli/__init__.py`

## API Environments

| Name | URL | Default |
|------|-----|---------|
| prod | `https://api.youcited.com` | yes |
| dev | `https://dev.youcited.com` | |
| local | `http://localhost:8000` | |
