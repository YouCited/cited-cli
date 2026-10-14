"""server.json — the official MCP Registry entry — must stay in sync with the package."""

from __future__ import annotations

import json
import re
from pathlib import Path

from cited_core import __version__
from cited_core.config.constants import MCP_URLS

ROOT = Path(__file__).resolve().parent.parent
SERVER_JSON = ROOT / "server.json"
MCP_README = ROOT / "packages" / "mcp" / "README.md"


def _server() -> dict:
    return json.loads(SERVER_JSON.read_text())


def test_server_json_version_matches_package_version():
    data = _server()
    assert data["version"] == __version__, (
        "server.json version is out of sync with cited_core.__version__ — "
        "release.sh bumps both; update server.json by hand if you bumped manually."
    )
    pypi = [p for p in data["packages"] if p["registryType"] == "pypi"]
    assert [p["identifier"] for p in pypi] == ["cited-mcp"]
    assert pypi[0]["version"] == __version__


def test_server_json_name_matches_pypi_readme_mcp_name():
    """The registry verifies PyPI ownership via `mcp-name: <name>` in the package README."""
    names = re.findall(r"mcp-name:\s*(\S+)", MCP_README.read_text())
    assert names == [_server()["name"]]


def test_server_json_remote_and_package_transports():
    data = _server()
    assert data["remotes"] == [
        {"type": "streamable-http", "url": f"{MCP_URLS['prod']}/mcp"}
    ]
    pkg = data["packages"][0]
    assert pkg["transport"] == {"type": "stdio"}
    env_names = {e["name"] for e in pkg["environmentVariables"]}
    assert {"CITED_TOKEN", "CITED_AGENT_API_KEY"} <= env_names


def test_server_json_registry_limits():
    data = _server()
    assert re.fullmatch(r"[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+", data["name"])
    assert 1 <= len(data["description"]) <= 100
    assert data["$schema"].startswith("https://static.modelcontextprotocol.io/schemas/")


def test_server_json_is_canonically_formatted():
    """release.sh rewrites the file with json.dumps(indent=2); keep it diff-stable."""
    text = SERVER_JSON.read_text()
    assert text == json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n"
