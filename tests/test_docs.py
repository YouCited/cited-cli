from __future__ import annotations

import json

import httpx
import pytest
import respx

from cited_core import docs as cited_docs
from cited_core.errors import CitedAPIError
from tests.test_mcp_tools import _make_cited_ctx, _make_mcp_ctx, _mcp_available, _run  # noqa: F401

SITE = "https://youcited.com"

INDEX_MD = """# Cited Documentation

## Getting Started

- [Quick Start Guide](https://youcited.com/docs/getting-started/quick-start-guide.md): Go from
  sign-up to first insights in under 10 minutes
- [Understanding Your Scores](/docs/getting-started/understanding-your-scores) — Interpret your
  visibility, citation, and trust scores

## Feature Guides

- [Audit Templates & Runs](https://youcited.com/docs/feature-guides/audit-templates-and-runs.md): How audits work and how to configure them
- [Recommendations](https://youcited.com/docs/feature-guides/recommendations.md): Ranked, evidence-backed fixes
- [Audit Templates & Runs](https://youcited.com/docs/feature-guides/audit-templates-and-runs.md): duplicate

## GEO Concepts

- [What is llms.txt?](https://youcited.com/docs/geo-concepts/llms-txt.md): Publishing an llms.txt file for AI crawlers
"""  # noqa: E501

LLMS_TXT = """# Cited

### Docs — top entries
- [What is GEO?](https://youcited.com/docs/geo-concepts/what-is-geo): Fundamentals of Generative Engine Optimization
"""  # noqa: E501

DOC_MD = """---
title: "Quick Start Guide"
---

# Quick Start Guide

1. Create a business.
2. Run an audit.
"""


@pytest.fixture(autouse=True)
def _default_docs_url(monkeypatch):
    monkeypatch.delenv("CITED_DOCS_URL", raising=False)


# --- core ---------------------------------------------------------------------


def test_parse_docs_index_handles_link_styles_and_dedupes():
    entries = cited_docs.parse_docs_index(INDEX_MD, SITE)
    paths = [e["path"] for e in entries]
    assert paths == [
        "getting-started/quick-start-guide",
        "getting-started/understanding-your-scores",
        "feature-guides/audit-templates-and-runs",
        "feature-guides/recommendations",
        "geo-concepts/llms-txt",
    ]
    by_path = {e["path"]: e for e in entries}
    scores = by_path["getting-started/understanding-your-scores"]
    assert scores["description"].startswith("Interpret your")
    assert scores["url"] == f"{SITE}/docs/getting-started/understanding-your-scores"
    assert scores["markdown_url"].endswith("understanding-your-scores.md")
    assert scores["section"] == "Getting Started"
    assert by_path["feature-guides/audit-templates-and-runs"]["description"] == (
        "How audits work and how to configure them"
    )


def test_rank_docs_orders_by_relevance():
    entries = cited_docs.parse_docs_index(INDEX_MD, SITE)
    results = cited_docs.rank_docs(entries, "how do audit templates work?", limit=5)
    assert results[0]["path"] == "feature-guides/audit-templates-and-runs"
    assert all(r["score"] > 0 for r in results)
    assert cited_docs.rank_docs(entries, "llms.txt", 5)[0]["path"] == "geo-concepts/llms-txt"
    assert cited_docs.rank_docs(entries, "kubernetes", 5) == []
    assert len(cited_docs.rank_docs(entries, "scores audits recommendations", 1)) == 1


@pytest.mark.parametrize(
    "raw",
    [
        "getting-started/quick-start-guide",
        "/docs/getting-started/quick-start-guide",
        "getting-started/quick-start-guide.md",
        "https://youcited.com/docs/getting-started/quick-start-guide",
        "https://youcited.com/docs/getting-started/quick-start-guide.md#step-1",
    ],
)
def test_normalize_doc_path_accepts_variants(raw):
    assert cited_docs.normalize_doc_path(raw) == "getting-started/quick-start-guide"


@pytest.mark.parametrize("raw", ["../etc/passwd", "a/b/c", "quick-start", ""])
def test_normalize_doc_path_rejects_bad_input(raw):
    with pytest.raises(CitedAPIError) as exc:
        cited_docs.normalize_doc_path(raw)
    assert exc.value.status_code == 422


@respx.mock
def test_search_falls_back_to_llms_txt_when_index_missing():
    respx.get(f"{SITE}/docs/index.md").mock(return_value=httpx.Response(404))
    respx.get(f"{SITE}/llms.txt").mock(
        return_value=httpx.Response(200, text=LLMS_TXT, headers={"content-type": "text/plain"})
    )
    data = cited_docs.search_docs("what is geo")
    assert data["source"] == f"{SITE}/llms.txt"
    assert data["results"][0]["path"] == "geo-concepts/what-is-geo"


@respx.mock
def test_search_treats_html_index_as_missing():
    respx.get(f"{SITE}/docs/index.md").mock(
        return_value=httpx.Response(
            200, text="<!DOCTYPE html><html></html>", headers={"content-type": "text/html"}
        )
    )
    respx.get(f"{SITE}/llms.txt").mock(return_value=httpx.Response(200, text=LLMS_TXT))
    assert cited_docs.search_docs("geo")["source"] == f"{SITE}/llms.txt"


@respx.mock
def test_docs_url_override(monkeypatch):
    monkeypatch.setenv("CITED_DOCS_URL", "https://staging.example.org/")
    route = respx.get("https://staging.example.org/docs/index.md").mock(
        return_value=httpx.Response(200, text=INDEX_MD)
    )
    data = cited_docs.search_docs("recommendations")
    assert route.called
    assert data["results"][0]["url"].startswith("https://staging.example.org/docs/")


# --- CLI ----------------------------------------------------------------------


@respx.mock
def test_cli_docs_search_json(runner, cli_app):
    route = respx.get(f"{SITE}/docs/index.md").mock(
        return_value=httpx.Response(200, text=INDEX_MD)
    )
    result = runner.invoke(cli_app, ["--json", "docs", "search", "audit", "templates", "-n", "2"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["query"] == "audit templates"
    assert data["results"][0]["path"] == "feature-guides/audit-templates-and-runs"
    assert len(data["results"]) <= 2
    assert "cookie" not in route.calls.last.request.headers


@respx.mock
def test_cli_docs_search_human_no_results(runner, cli_app):
    respx.get(f"{SITE}/docs/index.md").mock(return_value=httpx.Response(200, text=INDEX_MD))
    result = runner.invoke(cli_app, ["--text", "docs", "search", "kubernetes"])
    assert result.exit_code == 0, result.output
    assert "No docs matched" in result.output


@respx.mock
def test_cli_docs_get(runner, cli_app):
    respx.get(f"{SITE}/docs/getting-started/quick-start-guide.md").mock(
        return_value=httpx.Response(200, text=DOC_MD, headers={"content-type": "text/markdown"})
    )
    result = runner.invoke(
        cli_app, ["--json", "docs", "get", "getting-started/quick-start-guide"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["title"] == "Quick Start Guide"
    assert "Run an audit." in data["content"]
    assert data["url"] == f"{SITE}/docs/getting-started/quick-start-guide"


@respx.mock
def test_cli_docs_get_not_found(runner, cli_app):
    respx.get(f"{SITE}/docs/getting-started/nope.md").mock(return_value=httpx.Response(404))
    result = runner.invoke(cli_app, ["docs", "get", "getting-started/nope"])
    assert result.exit_code == 3


def test_cli_docs_get_invalid_path(runner, cli_app):
    result = runner.invoke(cli_app, ["docs", "get", "../../etc/passwd"])
    assert result.exit_code == 4


@respx.mock
def test_cli_docs_search_network_error(runner, cli_app):
    respx.get(f"{SITE}/docs/index.md").mock(side_effect=httpx.ConnectError("boom"))
    respx.get(f"{SITE}/llms.txt").mock(side_effect=httpx.ConnectError("boom"))
    result = runner.invoke(cli_app, ["docs", "search", "geo"])
    assert result.exit_code == 1


# --- MCP ----------------------------------------------------------------------


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_mcp_search_docs_without_token():
    from cited_mcp.tools.docs import search_docs

    respx.get(f"{SITE}/docs/index.md").mock(return_value=httpx.Response(200, text=INDEX_MD))
    ctx = _make_mcp_ctx(_make_cited_ctx(token=None))
    result = _run(search_docs(ctx, query="recommendations", limit=3))
    assert result["results"][0]["path"] == "feature-guides/recommendations"
    assert "get_doc" in result["hint"]


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_mcp_get_doc_and_not_found():
    from cited_mcp.tools.docs import get_doc

    respx.get(f"{SITE}/docs/getting-started/quick-start-guide.md").mock(
        return_value=httpx.Response(200, text=DOC_MD)
    )
    respx.get(f"{SITE}/docs/getting-started/nope.md").mock(return_value=httpx.Response(404))
    ctx = _make_mcp_ctx(_make_cited_ctx(token=None))

    doc = _run(get_doc(ctx, path="getting-started/quick-start-guide"))
    assert doc["title"] == "Quick Start Guide"

    missing = _run(get_doc(ctx, path="getting-started/nope"))
    assert missing["error"] is True
    assert missing["status_code"] == 404


@pytest.mark.usefixtures("_mcp_available")
@respx.mock
def test_mcp_get_doc_truncates_huge_articles():
    from cited_mcp.tools.docs import _MAX_DOC_CHARS, get_doc

    respx.get(f"{SITE}/docs/geo-concepts/big.md").mock(
        return_value=httpx.Response(200, text="# Big\n" + "x" * (_MAX_DOC_CHARS + 10))
    )
    ctx = _make_mcp_ctx(_make_cited_ctx(token=None))
    doc = _run(get_doc(ctx, path="geo-concepts/big"))
    assert doc["_truncated"] is True
    assert len(doc["content"]) == _MAX_DOC_CHARS
