from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

import cited_cli.commands.agent_setup as setup_mod

PROD_URL = "https://mcp.youcited.com/mcp"


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """Fake HOME with no AI clients installed and no `claude`/`codex`/`npx` on PATH."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setattr(setup_mod.sys, "platform", "linux")
    monkeypatch.setattr(setup_mod, "_home", lambda: home)
    monkeypatch.setattr(setup_mod, "_which", lambda name: None)
    monkeypatch.setattr(setup_mod, "_is_interactive", lambda: False)

    def _no_subprocess(cmd: list[str]) -> Any:
        raise AssertionError(f"unexpected subprocess: {cmd}")

    monkeypatch.setattr(setup_mod, "_run", _no_subprocess)
    config_dir = tmp_path / ".cited"
    monkeypatch.setattr("cited_core.config.manager.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.config.manager.CONFIG_FILE", config_dir / "config.toml")
    return home


def _invoke(runner, cli_app, *args: str, input: str | None = None):
    return runner.invoke(cli_app, ["--json", "agent", "setup", *args], input=input)


def _by_client(output: str) -> dict[str, dict[str, Any]]:
    return {r["client"]: r for r in json.loads(output)["results"]}


def _backups(path: Path) -> list[Path]:
    return sorted(path.parent.glob(f"{path.name}.bak-*"))


# --- general ------------------------------------------------------------------


def test_nothing_detected_skips_everything(runner, cli_app, home):
    result = _invoke(runner, cli_app, "--yes")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["mcp_url"] == PROD_URL
    assert {r["status"] for r in data["results"]} == {"not_detected"}
    assert data["plugin"]["commands"] == [
        "/plugin marketplace add YouCited/cited-plugins",
        "/plugin install cited@youcited-cited-plugins",
    ]
    assert list(home.iterdir()) == []


def test_dry_run_writes_nothing(runner, cli_app, home):
    (home / ".cursor").mkdir()
    result = _invoke(runner, cli_app, "--dry-run", "--yes")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["applied"] is False
    assert _by_client(result.output)["cursor"]["status"] == "would_configure"
    assert not (home / ".cursor" / "mcp.json").exists()


def test_non_interactive_without_yes_does_not_write(runner, cli_app, home):
    (home / ".cursor").mkdir()
    result = _invoke(runner, cli_app)
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["applied"] is False
    assert "--yes" in data["note"]
    assert not (home / ".cursor" / "mcp.json").exists()


def test_interactive_decline_skips(runner, cli_app, home, monkeypatch):
    monkeypatch.setattr(setup_mod, "_is_interactive", lambda: True)
    (home / ".cursor").mkdir()
    result = runner.invoke(cli_app, ["agent", "setup", "-c", "cursor"], input="n\n")
    assert result.exit_code == 0, result.output
    assert "skipped" in result.output
    assert not (home / ".cursor" / "mcp.json").exists()


def test_interactive_accept_writes(runner, cli_app, home, monkeypatch):
    monkeypatch.setattr(setup_mod, "_is_interactive", lambda: True)
    result = runner.invoke(cli_app, ["agent", "setup", "-c", "cursor"], input="y\n")
    assert result.exit_code == 0, result.output
    assert json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"]["cited"]


def test_unknown_client(runner, cli_app, home):
    result = _invoke(runner, cli_app, "-c", "vscode")
    assert result.exit_code == 4


def test_env_dev_uses_dev_mcp_url(runner, cli_app, home):
    result = runner.invoke(
        cli_app, ["--env", "dev", "--json", "agent", "setup", "-c", "cursor", "--yes"]
    )
    assert result.exit_code == 0, result.output
    cfg = json.loads((home / ".cursor" / "mcp.json").read_text())
    assert cfg["mcpServers"]["cited"] == {"url": "https://mcpdev.youcited.com/mcp"}


# --- Cursor -------------------------------------------------------------------


def test_cursor_merges_backs_up_and_is_idempotent(runner, cli_app, home):
    cfg_path = home / ".cursor" / "mcp.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({"mcpServers": {"other": {"url": "https://x"}}, "keep": 1}))

    result = _invoke(runner, cli_app, "--yes")
    assert result.exit_code == 0, result.output
    cursor = _by_client(result.output)["cursor"]
    assert cursor["status"] == "configured"
    cfg = json.loads(cfg_path.read_text())
    assert cfg["keep"] == 1
    assert cfg["mcpServers"]["other"] == {"url": "https://x"}
    assert cfg["mcpServers"]["cited"] == {"url": PROD_URL}
    backups = _backups(cfg_path)
    assert len(backups) == 1
    assert "cited" not in json.loads(backups[0].read_text())["mcpServers"]
    assert cursor["backup"] == str(backups[0])

    again = _invoke(runner, cli_app, "--yes")
    assert _by_client(again.output)["cursor"]["status"] == "already_configured"
    assert len(_backups(cfg_path)) == 1


def test_cursor_existing_different_entry_is_left_alone(runner, cli_app, home):
    cfg_path = home / ".cursor" / "mcp.json"
    cfg_path.parent.mkdir()
    original = {"mcpServers": {"cited": {"command": "npx", "args": ["mcp-remote", "x"]}}}
    cfg_path.write_text(json.dumps(original))

    result = _invoke(runner, cli_app, "--yes", "-c", "cursor")
    assert result.exit_code == 0, result.output
    assert _by_client(result.output)["cursor"]["status"] == "conflict"
    assert json.loads(cfg_path.read_text()) == original
    assert _backups(cfg_path) == []


def test_cursor_invalid_json_is_not_touched(runner, cli_app, home):
    cfg_path = home / ".cursor" / "mcp.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text("{ not json")

    result = _invoke(runner, cli_app, "--yes", "-c", "cursor")
    assert result.exit_code == 1
    assert cfg_path.read_text() == "{ not json"


# --- Claude Code --------------------------------------------------------------


def test_claude_code_without_cli_writes_user_scope_server(runner, cli_app, home):
    claude_json = home / ".claude.json"
    claude_json.write_text(json.dumps({"projects": {"/x": {"mcpServers": {}}}, "numStartups": 3}))

    result = _invoke(runner, cli_app, "--yes", "-c", "claude-code")
    assert result.exit_code == 0, result.output
    data = json.loads(claude_json.read_text())
    assert data["numStartups"] == 3
    assert data["projects"] == {"/x": {"mcpServers": {}}}
    assert data["mcpServers"]["cited"] == {"type": "http", "url": PROD_URL}
    assert len(_backups(claude_json)) == 1


def test_claude_code_with_cli_runs_mcp_add(runner, cli_app, home, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[:3] == ["claude", "mcp", "get"]:
            return subprocess.CompletedProcess(cmd, 1, "", "No MCP server found")
        return subprocess.CompletedProcess(cmd, 0, "Added", "")

    monkeypatch.setattr(setup_mod, "_which", lambda n: "/usr/bin/claude" if n == "claude" else None)
    monkeypatch.setattr(setup_mod, "_run", fake_run)

    result = _invoke(runner, cli_app, "--yes")
    assert result.exit_code == 0, result.output
    assert _by_client(result.output)["claude-code"]["status"] == "configured"
    assert calls[-1] == [
        "claude", "mcp", "add", "--transport", "http", "--scope", "user", "cited", PROD_URL,
    ]
    assert not (home / ".claude.json").exists()


def test_claude_code_with_cli_already_configured(runner, cli_app, home, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, f"cited:\n  URL: {PROD_URL}\n", "")

    monkeypatch.setattr(setup_mod, "_which", lambda n: "/usr/bin/claude" if n == "claude" else None)
    monkeypatch.setattr(setup_mod, "_run", fake_run)

    result = _invoke(runner, cli_app, "--yes", "-c", "claude-code")
    assert _by_client(result.output)["claude-code"]["status"] == "already_configured"
    assert all(c[2] != "add" for c in calls)


def test_claude_code_cli_failure_reports_error(runner, cli_app, home, monkeypatch):
    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, "", "boom")

    monkeypatch.setattr(setup_mod, "_which", lambda n: "/usr/bin/claude" if n == "claude" else None)
    monkeypatch.setattr(setup_mod, "_run", fake_run)

    result = _invoke(runner, cli_app, "--yes", "-c", "claude-code")
    assert result.exit_code == 1
    assert "boom" in _by_client(result.output)["claude-code"]["message"]


# --- Codex --------------------------------------------------------------------


def test_codex_appends_table_preserving_file(runner, cli_app, home):
    cfg_path = home / ".codex" / "config.toml"
    cfg_path.parent.mkdir()
    original = '# my settings\nmodel = "gpt-5"\n\n[mcp_servers.other]\ncommand = "x"\n'
    cfg_path.write_text(original)

    result = _invoke(runner, cli_app, "--yes")
    assert result.exit_code == 0, result.output
    codex = _by_client(result.output)["codex"]
    assert codex["status"] == "configured"
    assert "codex mcp login cited" in codex["next_steps"][0]
    text = cfg_path.read_text()
    assert text.startswith(original)
    parsed = tomllib.loads(text)
    assert parsed["mcp_servers"]["cited"] == {"url": PROD_URL}
    assert parsed["mcp_servers"]["other"] == {"command": "x"}
    assert parsed["model"] == "gpt-5"
    assert len(_backups(cfg_path)) == 1

    again = _invoke(runner, cli_app, "--yes")
    assert _by_client(again.output)["codex"]["status"] == "already_configured"


def test_codex_unusual_layout_is_not_touched(runner, cli_app, home):
    cfg_path = home / ".codex" / "config.toml"
    cfg_path.parent.mkdir()
    original = 'mcp_servers = { other = { command = "x" } }\n'
    cfg_path.write_text(original)

    result = _invoke(runner, cli_app, "--yes", "-c", "codex")
    assert result.exit_code == 1
    assert _by_client(result.output)["codex"]["status"] == "error"
    assert cfg_path.read_text() == original


def test_codex_with_cli_runs_mcp_add(runner, cli_app, home, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(setup_mod, "_which", lambda n: "/usr/bin/codex" if n == "codex" else None)
    monkeypatch.setattr(setup_mod, "_run", fake_run)

    result = _invoke(runner, cli_app, "--yes")
    assert result.exit_code == 0, result.output
    assert _by_client(result.output)["codex"]["status"] == "configured"
    assert calls == [["codex", "mcp", "add", "cited", "--url", PROD_URL]]


# --- Claude Desktop -----------------------------------------------------------


def test_claude_desktop_prints_connector_steps_by_default(runner, cli_app, home):
    desktop_dir = home / ".config" / "Claude"
    desktop_dir.mkdir(parents=True)

    result = _invoke(runner, cli_app, "--yes")
    assert result.exit_code == 0, result.output
    desktop = _by_client(result.output)["claude-desktop"]
    assert desktop["status"] == "instructions"
    assert any(PROD_URL in s for s in desktop["next_steps"])
    assert list(desktop_dir.iterdir()) == []


def test_claude_desktop_config_flag_writes_mcp_remote(runner, cli_app, home):
    cfg_path = home / ".config" / "Claude" / "claude_desktop_config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({"globalShortcut": "Alt+Space"}))

    result = _invoke(runner, cli_app, "--yes", "-c", "claude-desktop", "--desktop-config")
    assert result.exit_code == 0, result.output
    cfg = json.loads(cfg_path.read_text())
    assert cfg["globalShortcut"] == "Alt+Space"
    assert cfg["mcpServers"]["cited"] == {"command": "npx", "args": ["mcp-remote", PROD_URL]}
    steps = _by_client(result.output)["claude-desktop"]["next_steps"]
    assert any("Node.js" in s for s in steps)


def test_claude_desktop_path_on_macos(home, monkeypatch):
    monkeypatch.setattr(setup_mod.sys, "platform", "darwin")
    assert setup_mod.claude_desktop_config_path() == (
        home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    )


def test_human_output_mentions_plugin(runner, cli_app, home):
    result = runner.invoke(cli_app, ["--text", "agent", "setup", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "/plugin install cited@youcited-cited-plugins" in result.output
