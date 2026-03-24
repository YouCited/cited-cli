from __future__ import annotations

import pytest
from typer.testing import CliRunner

from cited_cli.app import app


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", default=False, help="Run live integration tests")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: mark test as live integration test (requires --live)")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--live"):
        skip_live = pytest.mark.skip(reason="need --live option to run")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def cli_app():
    return app
