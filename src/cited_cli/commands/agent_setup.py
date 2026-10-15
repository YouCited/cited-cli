"""`cited agent setup` — connect local AI clients to the hosted Cited MCP server.

Writes (or prints) MCP config for Claude Code, Claude Desktop, Cursor and
Codex. It always merges into existing config and never replaces an existing
``cited`` entry; any file it changes is backed up first.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape

from cited_cli.output.formatter import OutputContext, print_error, print_result
from cited_cli.utils.errors import ExitCode
from cited_core.config.constants import DEFAULT_ENV, MCP_URLS
from cited_core.config.manager import ConfigManager

SERVER_NAME = "cited"
CLIENTS = ("claude-code", "claude-desktop", "cursor", "codex")
CLIENT_LABELS = {
    "claude-code": "Claude Code",
    "claude-desktop": "Claude Desktop",
    "cursor": "Cursor",
    "codex": "Codex",
}

# The Claude Code plugin (skills, slash commands, geo-analyst agent) is published
# from the public YouCited/cited-plugins repo, whose marketplace is named
# "youcited-cited-plugins" (see cited-plugins/.claude-plugin/marketplace.json).
PLUGIN_MARKETPLACE_REPO = "YouCited/cited-plugins"
PLUGIN_MARKETPLACE_NAME = "youcited-cited-plugins"
PLUGIN_NAME = "cited"

CONNECTOR_GUIDE = (
    "https://support.claude.com/en/articles/"
    "11175166-get-started-with-custom-connectors-using-remote-mcp"
)

# Statuses that mean "this run changed, or would change, something".
_CHANGE = {"configured", "would_configure"}


# ---------------------------------------------------------------------------
# Small seams (monkeypatched in tests)
# ---------------------------------------------------------------------------


def _is_interactive() -> bool:
    return sys.stdin.isatty()


def _which(name: str) -> str | None:
    return shutil.which(name)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)


def _home() -> Path:
    return Path.home()


# ---------------------------------------------------------------------------
# Paths and detection
# ---------------------------------------------------------------------------


def claude_desktop_config_path() -> Path:
    home = _home()
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return base / "Claude" / "claude_desktop_config.json"


def detect_clients() -> dict[str, bool]:
    home = _home()
    return {
        "claude-code": bool(_which("claude"))
        or (home / ".claude.json").exists()
        or (home / ".claude").is_dir(),
        "claude-desktop": claude_desktop_config_path().parent.is_dir(),
        "cursor": bool(_which("cursor")) or (home / ".cursor").is_dir(),
        "codex": bool(_which("codex")) or (home / ".codex").is_dir(),
    }


def mcp_url_for(env: str) -> str:
    return f"{MCP_URLS.get(env, MCP_URLS[DEFAULT_ENV])}/mcp"


# ---------------------------------------------------------------------------
# File helpers — merge, back up, write atomically
# ---------------------------------------------------------------------------


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    n = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak-{stamp}-{n}")
        n += 1
    shutil.copy2(path, backup)
    return backup


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.cited-tmp")
    tmp.write_text(text, encoding="utf-8")
    if path.exists():
        shutil.copymode(path, tmp)
    os.replace(tmp, path)


def merge_json_server(
    path: Path, entry: dict[str, Any], apply: bool, key: str = "mcpServers"
) -> dict[str, Any]:
    """Add ``entry`` as ``<key>.cited`` in a JSON config file, keeping everything else."""
    result: dict[str, Any] = {"method": "file", "path": str(path)}
    data: dict[str, Any] = {}
    if path.exists():
        try:
            raw = path.read_text(encoding="utf-8")
            loaded = json.loads(raw) if raw.strip() else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            return {**result, "status": "error",
                    "message": f"Could not parse {path} ({e}); left unchanged."}
        if not isinstance(loaded, dict):
            return {**result, "status": "error",
                    "message": f"{path} is not a JSON object; left unchanged."}
        data = loaded
    servers = data.get(key)
    if servers is None:
        servers = {}
    elif not isinstance(servers, dict):
        return {**result, "status": "error",
                "message": f"'{key}' in {path} is not an object; left unchanged."}
    existing = servers.get(SERVER_NAME)
    if existing == entry:
        return {**result, "status": "already_configured",
                "message": f"'{SERVER_NAME}' is already configured in {path}."}
    if existing is not None:
        return {**result, "status": "conflict", "existing": existing,
                "message": (f"A different '{SERVER_NAME}' server already exists in {path}; "
                            "left unchanged. Remove it first if you want it replaced.")}
    if not apply:
        return {**result, "status": "would_configure", "entry": entry}
    backup = _backup(path) if path.exists() else None
    data[key] = {**servers, SERVER_NAME: entry}
    _write_atomic(path, json.dumps(data, indent=2) + "\n")
    out = {**result, "status": "configured", "entry": entry}
    if backup:
        out["backup"] = str(backup)
    return out


def merge_codex_toml(path: Path, url: str, apply: bool) -> dict[str, Any]:
    """Append ``[mcp_servers.cited]`` to Codex's config.toml without rewriting the rest."""
    result: dict[str, Any] = {"method": "file", "path": str(path)}
    text = ""
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            data = tomllib.loads(text)
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            return {**result, "status": "error",
                    "message": f"Could not parse {path} ({e}); left unchanged."}
        servers = data.get("mcp_servers")
        existing = servers.get(SERVER_NAME) if isinstance(servers, dict) else None
        if existing is not None:
            if isinstance(existing, dict) and existing.get("url") == url:
                return {**result, "status": "already_configured",
                        "message": f"'{SERVER_NAME}' is already configured in {path}."}
            return {**result, "status": "conflict", "existing": existing,
                    "message": (f"A different [mcp_servers.{SERVER_NAME}] exists in {path}; "
                                "left unchanged. Remove it first if you want it replaced.")}
    block = f'[mcp_servers.{SERVER_NAME}]\nurl = "{url}"\n'
    sep = "" if not text.strip() else ("\n" if text.endswith("\n") else "\n\n")
    new_text = (text + sep + block) if text.strip() else block
    try:
        parsed = tomllib.loads(new_text)
        ok = parsed["mcp_servers"][SERVER_NAME]["url"] == url
    except (tomllib.TOMLDecodeError, KeyError, TypeError):
        ok = False
    if not ok:
        return {**result, "status": "error",
                "message": (f"Could not safely add [mcp_servers.{SERVER_NAME}] to {path} "
                            "(its mcp_servers table has an unusual layout); left unchanged. "
                            f"Add it by hand:\n{block}")}
    if not apply:
        return {**result, "status": "would_configure", "entry": {"url": url}}
    backup = _backup(path) if path.exists() else None
    _write_atomic(path, new_text)
    out = {**result, "status": "configured", "entry": {"url": url}}
    if backup:
        out["backup"] = str(backup)
    return out


# ---------------------------------------------------------------------------
# Per-client setup
# ---------------------------------------------------------------------------


def setup_claude_code(url: str, apply: bool) -> dict[str, Any]:
    next_steps = [
        "In Claude Code, run /mcp, select 'cited' and choose Authenticate to log in "
        "(the free audit and docs search work without logging in).",
    ]
    cmd = ["claude", "mcp", "add", "--transport", "http", "--scope", "user", SERVER_NAME, url]
    if _which("claude"):
        result: dict[str, Any] = {"method": "cli", "command": cmd, "next_steps": next_steps}
        try:
            got = _run(["claude", "mcp", "get", SERVER_NAME])
        except (OSError, subprocess.SubprocessError) as e:
            return {**result, "status": "error", "message": f"Could not run claude: {e}"}
        if got.returncode == 0:
            if url in (got.stdout or ""):
                return {**result, "status": "already_configured",
                        "message": "Claude Code already has the 'cited' MCP server."}
            return {**result, "status": "conflict",
                    "message": ("Claude Code already has a different 'cited' MCP server; left "
                                "unchanged. Remove it with `claude mcp remove cited` to replace.")}
        if not apply:
            return {**result, "status": "would_configure"}
        try:
            done = _run(cmd)
        except (OSError, subprocess.SubprocessError) as e:
            return {**result, "status": "error", "message": f"Could not run claude: {e}"}
        if done.returncode != 0:
            err = (done.stderr or done.stdout or "").strip()
            return {**result, "status": "error",
                    "message": f"`{' '.join(cmd)}` failed: {err}"}
        return {**result, "status": "configured"}
    # No `claude` binary on PATH: add a user-scoped server to ~/.claude.json directly.
    res = merge_json_server(_home() / ".claude.json", {"type": "http", "url": url}, apply)
    return {**res, "command": cmd, "next_steps": next_steps}


def setup_cursor(url: str, apply: bool) -> dict[str, Any]:
    res = merge_json_server(_home() / ".cursor" / "mcp.json", {"url": url}, apply)
    res["next_steps"] = [
        "Restart Cursor, open Settings → MCP, and click 'Login' next to cited "
        "to authenticate.",
    ]
    return res


def setup_codex(url: str, apply: bool) -> dict[str, Any]:
    path = _home() / ".codex" / "config.toml"
    next_steps = [f"Run `codex mcp login {SERVER_NAME}` to authenticate."]
    cmd = ["codex", "mcp", "add", SERVER_NAME, "--url", url]
    # Check the file first: it is where both `codex mcp add` and we would write.
    res = merge_codex_toml(path, url, apply=False)
    if res["status"] != "would_configure" or not _which("codex"):
        if res["status"] == "would_configure" and apply:
            res = merge_codex_toml(path, url, apply=True)
        return {**res, "next_steps": next_steps}
    result: dict[str, Any] = {"method": "cli", "command": cmd, "path": str(path),
                              "next_steps": next_steps}
    if not apply:
        return {**result, "status": "would_configure"}
    try:
        done = _run(cmd)
    except (OSError, subprocess.SubprocessError) as e:
        return {**result, "status": "error", "message": f"Could not run codex: {e}"}
    if done.returncode != 0:
        err = (done.stderr or done.stdout or "").strip()
        return {**result, "status": "error", "message": f"`{' '.join(cmd)}` failed: {err}"}
    return {**result, "status": "configured"}


def setup_claude_desktop(url: str, apply: bool, write_config: bool) -> dict[str, Any]:
    connector_steps = [
        "Open Claude Desktop → Settings → Connectors (Customize > Connectors).",
        "Click '+' → 'Add custom connector'.",
        f"Enter the URL {url} and click Add.",
        "Your browser opens to log in to Cited on first use.",
        f"Guide: {CONNECTOR_GUIDE}",
    ]
    if not write_config:
        return {
            "method": "manual",
            "status": "instructions",
            "message": ("Custom connectors can't be added from a file. Add Cited as a "
                        "custom connector (recommended), or re-run with --desktop-config to "
                        "write the mcp-remote developer config instead."),
            "next_steps": connector_steps,
        }
    entry = {"command": "npx", "args": ["mcp-remote", url]}
    res = merge_json_server(claude_desktop_config_path(), entry, apply)
    steps = ["Quit and reopen Claude Desktop (fully quit, not just close the window)."]
    if not _which("npx"):
        steps.insert(0, "Install Node.js (https://nodejs.org) — mcp-remote runs via npx.")
    steps.append("Don't also add the custom connector, or Cited's tools will appear twice.")
    res["next_steps"] = steps
    return res


def plugin_instructions() -> dict[str, Any]:
    return {
        "description": ("Optional, Claude Code only: Cited slash commands, skills and the "
                        "geo-analyst agent."),
        "commands": [
            f"/plugin marketplace add {PLUGIN_MARKETPLACE_REPO}",
            f"/plugin install {PLUGIN_NAME}@{PLUGIN_MARKETPLACE_NAME}",
        ],
    }


def run_setup(
    clients: list[str],
    url: str,
    apply: bool,
    desktop_config: bool,
    explicit: bool,
    confirm: Any = None,
) -> list[dict[str, Any]]:
    """Plan (and with ``apply``, perform) setup for ``clients``.

    ``confirm(client, result) -> bool`` is asked before each change when given.
    Clients that aren't installed are skipped unless they were named explicitly.
    """
    detected = detect_clients()
    results: list[dict[str, Any]] = []
    for client in clients:
        base = {"client": client, "label": CLIENT_LABELS[client],
                "detected": detected[client]}
        if not detected[client] and not explicit:
            results.append({**base, "status": "not_detected",
                            "message": f"{CLIENT_LABELS[client]} not found; skipped."})
            continue

        def _do(do_apply: bool, client: str = client) -> dict[str, Any]:
            if client == "claude-code":
                return setup_claude_code(url, do_apply)
            if client == "cursor":
                return setup_cursor(url, do_apply)
            if client == "codex":
                return setup_codex(url, do_apply)
            return setup_claude_desktop(url, do_apply, desktop_config)

        plan = _do(False)
        if apply and plan["status"] == "would_configure":
            if confirm is not None and not confirm(client, plan):
                results.append({**base, **plan, "status": "skipped",
                                "message": "Skipped at your request."})
                continue
            results.append({**base, **_do(True)})
        else:
            results.append({**base, **plan})
    return results


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_STATUS_STYLE = {
    "configured": "[green]✓ configured[/green]",
    "would_configure": "[cyan]→ would configure[/cyan]",
    "already_configured": "[green]✓ already configured[/green]",
    "instructions": "[yellow]! manual step[/yellow]",
    "conflict": "[yellow]! left unchanged[/yellow]",
    "skipped": "[dim]- skipped[/dim]",
    "not_detected": "[dim]- not installed[/dim]",
    "error": "[red]✗ error[/red]",
}


def _render(data: dict[str, Any], console: Console) -> None:
    console.print(f"[bold]Cited MCP server:[/bold] {data['mcp_url']}\n")
    for r in data["results"]:
        console.print(f"[bold]{r['label']}[/bold]  {_STATUS_STYLE.get(r['status'], r['status'])}")
        if r.get("command") and r.get("method") == "cli":
            console.print(f"  command: {escape(' '.join(r['command']))}", soft_wrap=True)
        if r.get("path"):
            console.print(f"  file:    {escape(r['path'])}", soft_wrap=True)
        if r.get("backup"):
            console.print(f"  backup:  {escape(r['backup'])}", soft_wrap=True)
        if r.get("message"):
            console.print(f"  {escape(r['message'])}")
        if r["status"] in ("configured", "already_configured", "would_configure",
                           "instructions"):
            for step in r.get("next_steps", []):
                console.print(f"  • {escape(step)}")
        console.print()
    if not data["applied"]:
        console.print(f"[yellow]{escape(data['note'])}[/yellow]\n")
    plugin = data["plugin"]
    console.print(f"[bold]Claude Code plugin[/bold] — {escape(plugin['description'])}")
    for cmd in plugin["commands"]:
        console.print(f"  {escape(cmd)}", soft_wrap=True)
    console.print(
        "\n[dim]Try it: ask your agent to \"run a free Cited audit of example.com\" — "
        "no login needed.[/dim]"
    )


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def agent_setup(
    ctx: typer.Context,
    client: Annotated[
        str,
        typer.Option(
            "--client", "-c",
            help="claude-code, claude-desktop, cursor, codex, or all (installed clients)",
        ),
    ] = "all",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would change without writing anything")
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Don't ask for confirmation")
    ] = False,
    desktop_config: Annotated[
        bool,
        typer.Option(
            "--desktop-config",
            help="Claude Desktop: write the npx mcp-remote developer config instead of "
                 "printing custom-connector steps",
        ),
    ] = False,
    json_flag: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Connect Claude Code, Claude Desktop, Cursor or Codex to the Cited MCP server.

    Merges into existing config (never replaces an existing 'cited' entry) and
    backs up any file before changing it.
    """
    obj = ctx.obj or {}
    out: OutputContext = obj.get("output", OutputContext())
    if json_flag:
        out = OutputContext(json_mode=True, quiet=out.quiet, no_color=out.no_color)
    cfg: ConfigManager = obj.get("config", ConfigManager())
    env = cfg.get_environment(obj.get("profile", "default"), obj.get("env_override"))
    url = mcp_url_for(env)

    choice = client.strip().lower()
    if choice != "all" and choice not in CLIENTS:
        print_error(f"Unknown client '{client}'. Use one of: {', '.join(CLIENTS)}, all", out)
        raise typer.Exit(ExitCode.VALIDATION_ERROR)
    clients = list(CLIENTS) if choice == "all" else [choice]

    can_prompt = _is_interactive() and not out.json_mode
    apply = not dry_run and (yes or can_prompt)
    note = ""
    if dry_run:
        note = "Dry run: nothing was written."
    elif not apply:
        note = "Non-interactive shell: nothing was written. Re-run with --yes to apply."

    def _confirm(name: str, plan: dict[str, Any]) -> bool:
        target = plan.get("path") or " ".join(plan.get("command", []))
        return typer.confirm(f"Configure {CLIENT_LABELS[name]} ({target})?", default=True)

    results = run_setup(
        clients, url, apply=apply, desktop_config=desktop_config,
        explicit=choice != "all", confirm=None if yes else _confirm,
    )
    data: dict[str, Any] = {
        "mcp_url": url,
        "environment": env,
        "applied": apply,
        "results": results,
        "plugin": plugin_instructions(),
    }
    if note:
        data["note"] = note
    print_result(data, out, human_formatter=_render)
    if any(r["status"] == "error" for r in results):
        raise typer.Exit(ExitCode.ERROR)
