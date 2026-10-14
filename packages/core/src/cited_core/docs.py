"""Public Cited documentation search, for agents and the CLI.

The docs live on the marketing site, not the API: every article is served as
markdown at ``https://youcited.com/docs/<category>/<slug>.md`` and listed in
``https://youcited.com/docs/index.md``. There is no backend search endpoint, so
search fetches the index and ranks entries by keyword match on the client.
``/llms.txt`` lists the top docs in the same link format and is the fallback
when the index cannot be fetched.

No call here needs a token.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from cited_core.errors import CitedAPIError

DEFAULT_DOCS_URL = "https://youcited.com"
DOCS_INDEX_PATH = "/docs/index.md"
DOCS_FALLBACK_INDEX_PATH = "/llms.txt"
DOCS_TIMEOUT = 15.0

# A doc is addressed as "<category>/<slug>"; both parts are lowercase slugs.
_DOC_PATH_RE = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*$")

# [Title](https://youcited.com/docs/<category>/<slug>[.md]) optional ": description"
_LINK_RE = re.compile(
    r"\[(?P<title>[^\]]+)\]\((?P<url>(?:https?://[^\s)]+?)?/docs/"
    r"(?P<category>[a-z0-9-]+)/(?P<slug>[a-z0-9-]+)(?:\.md)?/?)\)"
    r"(?P<rest>[^\n]*)"
)
_HEADING_RE = re.compile(r"^#{1,6}\s+(?P<text>.+?)\s*$")

_STOPWORDS = {
    "a", "an", "and", "are", "can", "do", "does", "for", "how", "i", "in", "is", "it",
    "my", "of", "on", "or", "the", "to", "what", "when", "where", "which", "why",
    "with", "you", "your",
}


def docs_base_url() -> str:
    """The docs site root, overridable with ``CITED_DOCS_URL`` (e.g. for staging)."""
    return (os.environ.get("CITED_DOCS_URL") or DEFAULT_DOCS_URL).rstrip("/")


def normalize_doc_path(path: str) -> str:
    """Turn a doc reference into ``<category>/<slug>``.

    Accepts ``category/slug``, ``/docs/category/slug``, ``category/slug.md`` or a
    full ``https://youcited.com/docs/...`` URL. Raises ``CitedAPIError`` (422)
    for anything else, so callers never build a URL from arbitrary input.
    """
    p = path.strip()
    p = re.sub(r"^https?://[^/]+", "", p)
    p = p.split("?", 1)[0].split("#", 1)[0].strip("/")
    if p.startswith("docs/"):
        p = p[len("docs/"):]
    if p.endswith(".md"):
        p = p[: -len(".md")]
    p = p.lower()
    if not _DOC_PATH_RE.match(p):
        raise CitedAPIError(
            422,
            f"Invalid doc path {path!r}. Use '<category>/<slug>', "
            "e.g. 'getting-started/quick-start-guide' (see search_docs results).",
        )
    return p


def parse_docs_index(markdown: str, base_url: str | None = None) -> list[dict[str, Any]]:
    """Extract doc entries from a markdown index (``docs/index.md`` or ``llms.txt``).

    Each entry has ``title``, ``path`` (``category/slug``), ``url`` (the page),
    ``markdown_url``, ``category``, ``section`` (nearest heading) and
    ``description`` (text after the link). Duplicate paths keep the first entry.
    """
    base = (base_url or docs_base_url()).rstrip("/")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    section = ""
    for line in markdown.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            section = heading.group("text").strip()
            continue
        for m in _LINK_RE.finditer(line):
            path = f"{m.group('category')}/{m.group('slug')}"
            if path in seen:
                continue
            seen.add(path)
            rest = m.group("rest")
            # Description is the text right after the link, up to the next link.
            rest = rest.split("[", 1)[0]
            description = re.sub(r"^[\s:\-–—|]+", "", rest).strip()
            entries.append({
                "title": m.group("title").strip(),
                "path": path,
                "url": f"{base}/docs/{path}",
                "markdown_url": f"{base}/docs/{path}.md",
                "category": m.group("category"),
                "section": section,
                "description": description,
            })
    return entries


def _get(url: str) -> httpx.Response:
    try:
        return httpx.get(url, timeout=DOCS_TIMEOUT, follow_redirects=True)
    except httpx.HTTPError as e:
        raise CitedAPIError(503, f"Could not reach the Cited docs at {url}: {e}") from e


def _is_markdown(resp: httpx.Response) -> bool:
    """False when the site answered with an HTML page (e.g. a soft 404)."""
    ctype = resp.headers.get("content-type", "")
    if "html" in ctype:
        return False
    return not resp.text.lstrip().lower().startswith(("<!doctype", "<html"))


def fetch_docs_index(base_url: str | None = None) -> tuple[list[dict[str, Any]], str]:
    """Fetch and parse the docs index. Returns ``(entries, source_url)``.

    Tries ``/docs/index.md`` first, then ``/llms.txt``.
    """
    base = (base_url or docs_base_url()).rstrip("/")
    last_error: CitedAPIError | None = None
    for index_path in (DOCS_INDEX_PATH, DOCS_FALLBACK_INDEX_PATH):
        url = f"{base}{index_path}"
        try:
            resp = _get(url)
        except CitedAPIError as e:
            last_error = e
            continue
        if resp.status_code != 200 or not _is_markdown(resp):
            last_error = CitedAPIError(
                resp.status_code if resp.status_code != 200 else 502,
                f"Docs index unavailable at {url} (HTTP {resp.status_code})",
            )
            continue
        entries = parse_docs_index(resp.text, base)
        if entries:
            return entries, url
        last_error = CitedAPIError(502, f"No docs found in index at {url}")
    assert last_error is not None
    raise last_error


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _words(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())]


def query_terms(query: str) -> list[str]:
    terms = [w for w in _words(query) if w not in _STOPWORDS]
    return list(dict.fromkeys(terms))  # dedupe, keep order


def score_doc(entry: dict[str, Any], query: str) -> float:
    """Keyword relevance of one index entry to ``query`` (0 = no match)."""
    terms = query_terms(query)
    if not terms:
        return 0.0
    fields = (
        (entry.get("title", ""), 3.0),
        (entry.get("path", "").replace("/", " ").replace("-", " "), 2.0),
        (entry.get("description", ""), 1.0),
        (f"{entry.get('section', '')} {entry.get('category', '')}".replace("-", " "), 0.5),
    )
    score = 0.0
    matched: set[str] = set()
    for text, weight in fields:
        words = set(_words(text))
        for term in terms:
            if term in words:
                score += weight
                matched.add(term)
            elif len(term) >= 3 and any(w.startswith(term) for w in words):
                score += weight / 2
                matched.add(term)
    if not matched:
        return 0.0
    # Favour docs that cover more of the query, and exact phrase hits in the title.
    score *= len(matched) / len(terms)
    phrase = " ".join(re.findall(r"[a-z0-9]+", query.lower()))
    if len(phrase) > 3 and phrase in entry.get("title", "").lower():
        score += 3.0
    return round(score, 3)


def rank_docs(entries: list[dict[str, Any]], query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return up to ``limit`` entries matching ``query``, best first, each with a ``score``."""
    limit = max(1, min(limit, 50))
    scored = [(score_doc(e, query), i, e) for i, e in enumerate(entries)]
    hits = [(s, i, e) for s, i, e in scored if s > 0]
    hits.sort(key=lambda t: (-t[0], t[1]))
    return [{**e, "score": s} for s, _, e in hits[:limit]]


def search_docs(query: str, limit: int = 5, base_url: str | None = None) -> dict[str, Any]:
    """Search the public Cited docs. Returns ``{query, count, results, source, hint}``."""
    entries, source = fetch_docs_index(base_url)
    results = rank_docs(entries, query, limit)
    data: dict[str, Any] = {
        "query": query,
        "count": len(results),
        "results": results,
        "source": source,
    }
    if results:
        data["hint"] = "Read a result in full with get_doc(path) / `cited docs get <path>`."
    else:
        data["hint"] = (
            f"No docs matched. Try broader words, or browse {docs_base_url()}/docs "
            f"({len(entries)} docs indexed)."
        )
    return data


def _title_from_markdown(markdown: str) -> str | None:
    fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", markdown, re.DOTALL)
    if fm:
        t = re.search(r"^title:\s*[\"']?(.+?)[\"']?\s*$", fm.group(1), re.MULTILINE)
        if t:
            return t.group(1)
    h1 = re.search(r"^#\s+(.+?)\s*$", markdown, re.MULTILINE)
    return h1.group(1) if h1 else None


def get_doc(path: str, base_url: str | None = None) -> dict[str, Any]:
    """Fetch one doc as markdown. ``path`` is ``category/slug`` (see ``normalize_doc_path``)."""
    doc_path = normalize_doc_path(path)
    base = (base_url or docs_base_url()).rstrip("/")
    md_url = f"{base}/docs/{doc_path}.md"
    resp = _get(md_url)
    if resp.status_code == 404 or (resp.status_code == 200 and not _is_markdown(resp)):
        raise CitedAPIError(
            404,
            f"Doc not found as markdown: {doc_path}. Use search_docs to find valid "
            f"paths, or open {base}/docs/{doc_path} in a browser.",
        )
    if resp.status_code != 200:
        raise CitedAPIError(resp.status_code, f"Could not fetch {md_url} (HTTP {resp.status_code})")
    content = resp.text
    return {
        "path": doc_path,
        "title": _title_from_markdown(content) or doc_path.rsplit("/", 1)[-1],
        "url": f"{base}/docs/{doc_path}",
        "markdown_url": md_url,
        "content": content,
    }
