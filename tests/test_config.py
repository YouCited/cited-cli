from __future__ import annotations

import json


def test_config_set_and_get(runner, cli_app, tmp_path, monkeypatch):
    config_dir = tmp_path / ".cited"
    config_file = config_dir / "config.toml"
    monkeypatch.setattr("cited_core.config.constants.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.config.constants.CONFIG_FILE", config_file)

    result = runner.invoke(cli_app, ["config", "set", "environment", "dev"])
    assert result.exit_code == 0

    result = runner.invoke(cli_app, ["config", "get", "environment"])
    assert result.exit_code == 0
    assert "dev" in result.output


def test_config_set_invalid_key(runner, cli_app, tmp_path, monkeypatch):
    config_dir = tmp_path / ".cited"
    config_file = config_dir / "config.toml"
    monkeypatch.setattr("cited_core.config.constants.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.config.constants.CONFIG_FILE", config_file)

    result = runner.invoke(cli_app, ["config", "set", "bad_key", "value"])
    assert result.exit_code != 0


def test_config_set_invalid_env(runner, cli_app, tmp_path, monkeypatch):
    config_dir = tmp_path / ".cited"
    config_file = config_dir / "config.toml"
    monkeypatch.setattr("cited_core.config.constants.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.config.constants.CONFIG_FILE", config_file)

    result = runner.invoke(cli_app, ["config", "set", "environment", "invalid"])
    assert result.exit_code != 0


def test_config_environments(runner, cli_app, tmp_path, monkeypatch):
    config_dir = tmp_path / ".cited"
    config_file = config_dir / "config.toml"
    monkeypatch.setattr("cited_core.config.constants.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.config.constants.CONFIG_FILE", config_file)

    result = runner.invoke(cli_app, ["config", "environments"])
    assert result.exit_code == 0
    assert "prod" in result.output
    assert "dev" in result.output


def test_config_environments_json(runner, cli_app, tmp_path, monkeypatch):
    config_dir = tmp_path / ".cited"
    config_file = config_dir / "config.toml"
    monkeypatch.setattr("cited_core.config.constants.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.config.constants.CONFIG_FILE", config_file)

    result = runner.invoke(cli_app, ["--json", "config", "environments"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "prod" in data
    assert "dev" in data


def test_config_show_masks_agent_key(runner, cli_app, tmp_path, monkeypatch):
    config_dir = tmp_path / ".cited"
    monkeypatch.setattr("cited_core.config.constants.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.config.constants.CONFIG_FILE", config_dir / "config.toml")
    key = "cak_" + "s3cr3t" * 6

    result = runner.invoke(cli_app, ["config", "set", "agent_api_key", key])
    assert result.exit_code == 0
    assert key not in result.output

    result = runner.invoke(cli_app, ["--json", "config", "show"])
    assert result.exit_code == 0
    assert key not in result.output
    assert json.loads(result.output)["agent_api_key"] == f"{key[:4]}…{key[-4:]}"

    # `config get` still returns the whole key for scripts.
    result = runner.invoke(cli_app, ["config", "get", "agent_api_key"])
    assert key in result.output
