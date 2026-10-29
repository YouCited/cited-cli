"""Prod smoke tests: the CLI and cited-mcp against api.youcited.com.

Nothing here spends credits: spending tools are only called without
``confirm``, which returns the price. Run with ``pytest tests/live --live``.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import httpx
import pytest

from cited_core.tools import bundled_manifest

pytestmark = pytest.mark.live

PROD = "https://api.youcited.com"
# Free audits of a domain are cached for 24 hours, so a nightly run starts at
# most one real audit a day.
FREE_AUDIT_DOMAIN = "youcited.com"


def cited(runner, cli_app, *args: str) -> dict:
    result = runner.invoke(cli_app, ["--env", "prod", "--json", *args])
    assert result.exit_code == 0, result.output
    data: dict = json.loads(result.stdout)
    return data


def test_bundled_tool_list_matches_prod():
    live = httpx.get(f"{PROD}/agent/tools", timeout=30).raise_for_status().json()
    bundled = bundled_manifest()
    assert [t["name"] for t in live["tools"]] == [t["name"] for t in bundled["tools"]]
    assert live == bundled, (
        "The API's tools changed. Run: python scripts/sync_tools_manifest.py, "
        "then update the CLI commands if a tool was added or its arguments changed."
    )


def test_tools_list_reads_prod(runner, cli_app):
    data = cited(runner, cli_app, "tools", "list")
    assert len(data["tools"]) == len(bundled_manifest()["tools"])


def test_status_without_login(runner, cli_app):
    data = cited(runner, cli_app, "status")
    assert data["signed_in"] is False
    assert data["prices"]["credit_value_usd"] == 1


def test_free_audit(runner, cli_app):
    data = cited(runner, cli_app, "audit", "free", FREE_AUDIT_DOMAIN)
    assert data["status"] == "completed"
    assert data["domain"] == FREE_AUDIT_DOMAIN
    assert data["share_url"].startswith("https://")
    assert data["cache_hours"] == 24
    assert data["questions"]


def test_docs_search(runner, cli_app):
    data = cited(runner, cli_app, "docs", "search", "credits")
    assert any(r["path"] == "getting-started/credits-and-pricing" for r in data["results"])


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_cited_mcp_over_stdio(anyio_backend, tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    here = Path(sys.executable).parent
    command = next(
        (str(p) for p in (here / "cited-mcp", here / "cited-mcp.exe") if p.exists()),
        shutil.which("cited-mcp"),
    )
    assert command, "cited-mcp is not installed"
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "CITED_ENV": "prod",
    }
    env.pop("CITED_AGENT_API_KEY", None)
    params = StdioServerParameters(command=command, env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        names = [t.name for t in (await session.list_tools()).tools]
        assert "free_audit" in names and "login" in names
        result = await session.call_tool("search_docs", {"query": "credits"})
        assert not result.is_error
        assert result.structured_content["results"]


# With the test account's agent key (CITED_SMOKE_AGENT_KEY). Read-only, or
# spending tools without confirm.


def test_status_signed_in(runner, cli_app, agent_key):
    data = cited(runner, cli_app, "status")
    assert data["signed_in"] is True


def test_business_and_audits(runner, cli_app, agent_key):
    cited(runner, cli_app, "business", "get")
    cited(runner, cli_app, "audit", "get")
    cited(runner, cli_app, "recommend", "list")
    cited(runner, cli_app, "fix", "list")


def test_audit_run_only_quotes_without_confirm(runner, cli_app, agent_key):
    data = cited(runner, cli_app, "audit", "run")
    assert data["confirmation_required"] is True
