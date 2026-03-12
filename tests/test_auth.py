from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest


def test_auth_status_not_logged_in(runner, cli_app, tmp_path, monkeypatch):
    config_dir = tmp_path / ".cited"
    config_file = config_dir / "config.toml"
    creds_file = config_dir / "credentials.json"
    monkeypatch.setattr("cited_cli.config.constants.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_cli.config.constants.CONFIG_FILE", config_file)
    monkeypatch.setattr("cited_cli.config.constants.CREDENTIALS_FILE", creds_file)

    result = runner.invoke(cli_app, ["auth", "status"])
    assert result.exit_code != 0


def test_auth_logout_not_logged_in(runner, cli_app, tmp_path, monkeypatch):
    config_dir = tmp_path / ".cited"
    config_file = config_dir / "config.toml"
    creds_file = config_dir / "credentials.json"
    monkeypatch.setattr("cited_cli.config.constants.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_cli.config.constants.CONFIG_FILE", config_file)
    monkeypatch.setattr("cited_cli.config.constants.CREDENTIALS_FILE", creds_file)

    result = runner.invoke(cli_app, ["auth", "logout"])
    assert result.exit_code != 0


def test_auth_token_not_logged_in(runner, cli_app, tmp_path, monkeypatch):
    config_dir = tmp_path / ".cited"
    config_file = config_dir / "config.toml"
    creds_file = config_dir / "credentials.json"
    monkeypatch.setattr("cited_cli.config.constants.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_cli.config.constants.CONFIG_FILE", config_file)
    monkeypatch.setattr("cited_cli.config.constants.CREDENTIALS_FILE", creds_file)

    result = runner.invoke(cli_app, ["auth", "token"])
    assert result.exit_code != 0
