"""whats_new tool — diff the current tool surface against a prior release.

Loads tool_changelog.yaml at module import time and serves a tool that lets
agents detect what's new since they last connected. See cited-plugins/commands/
status.md for typical usage.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from cited_mcp.context import CitedContext
from cited_mcp.server import get_tools_fingerprint, mcp

_CHANGELOG_PATH = Path(__file__).parent.parent / "tool_changelog.yaml"


def _load_changelog() -> tuple[dict[str, Any], str | None]:
    """Load and validate the tool changelog from yaml.

    Returns ``(changelog_dict, error_message)``. ``error_message`` is non-None
    when the changelog could not be loaded for the stated reason; in that case
    ``changelog_dict`` is ``{"versions": []}`` so callers can keep operating.

    Failure modes covered:
      * ``FileNotFoundError`` — file missing (e.g. data file not packaged)
      * ``yaml.YAMLError``   — file present but syntactically invalid
      * ``OSError``          — read failures (permissions, etc.)
      * structural validation — file parses but isn't a dict with a
        ``versions`` list at the root

    Server startup is intentionally insulated from any of these: the module
    imports cleanly, the tool stays registered, ping is unaffected, and
    ``whats_new`` surfaces ``_CHANGELOG_LOAD_ERROR`` in its response so the
    agent has a clear "diff is unreliable" signal to act on.
    """
    try:
        with _CHANGELOG_PATH.open() as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {"versions": []}, "changelog file not found at expected path"
    except yaml.YAMLError as e:
        return (
            {"versions": []},
            f"changelog YAML parse error: {type(e).__name__}",
        )
    except OSError as e:
        return {"versions": []}, f"changelog read error: {e}"
    if not isinstance(data, dict) or not isinstance(data.get("versions"), list):
        return (
            {"versions": []},
            "changelog file has invalid structure (expected 'versions' list at root)",
        )
    return data, None


_CHANGELOG, _CHANGELOG_LOAD_ERROR = _load_changelog()


def _entries_since_fingerprint(
    versions: list[dict[str, Any]], since_fp: str
) -> list[dict[str, Any]] | None:
    """Return entries newer than the one matching since_fp, or None if no match."""
    for i, entry in enumerate(versions):
        if entry.get("fingerprint") == since_fp:
            return versions[:i]
    return None


def _entries_since_version(
    versions: list[dict[str, Any]], since_ver: str
) -> list[dict[str, Any]] | None:
    """Return entries newer than the one matching since_ver, or None if no match."""
    for i, entry in enumerate(versions):
        if entry.get("version") == since_ver:
            return versions[:i]
    return None


def _aggregate_entries(
    entries: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Flatten added/changed/removed across multiple version entries."""
    added: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for entry in entries:
        v = entry.get("version", "?")
        for t in entry.get("tools_added") or []:
            added.append({
                "name": t.get("name"),
                "description": t.get("description", ""),
                "added_in_version": v,
            })
        for t in entry.get("tools_changed") or []:
            changed.append({
                "name": t.get("name"),
                "change_summary": t.get("change_summary", ""),
                "changed_in_version": v,
            })
        for t in entry.get("tools_removed") or []:
            removed.append({
                "name": t.get("name"),
                "removed_in_version": v,
            })
    return {
        "tools_added": added,
        "tools_changed": changed,
        "tools_removed": removed,
    }


@mcp.tool(
    title="What's New",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
async def whats_new(
    ctx: Context[Any, CitedContext, Any],
    since_fingerprint: str | None = None,
    since_version: str | None = None,
) -> Any:
    """Diff the current tool surface against a previously-seen fingerprint or version.

    Pair with `ping` — stash the `tools_fingerprint` from a prior session,
    then call this tool after a release to find out exactly what changed.

    Behavior:
      * No inputs → returns the most recent changelog entry.
      * Matching latest fingerprint → returns no_changes: true.
      * Older fingerprint or version → aggregated diff across every entry
        newer than the matching one (each item carries an
        added_in_version / changed_in_version / removed_in_version field).
      * Unrecognized fingerprint OR version → returns the full changelog
        history with a `_note` explaining the diff is unbounded.
      * Changelog file missing or corrupt → returns a structured error with
        `error: true`, `error_type: "changelog_unavailable"`, and an empty
        diff. The MCP server itself stays up and `ping` continues to work;
        this branch only signals that whats_new can't compute a diff right
        now. Disconnect/reconnect the connector and try again, or report.

    `since_fingerprint` takes precedence over `since_version` when both are
    passed (fingerprints are more precise — they cover docstring and schema
    edits, not just additions/removals).

    The changelog includes gated tools regardless of subscription tier so the
    agent can recommend upgrades when relevant.

    Args:
        ctx: MCP context
        since_fingerprint: A fingerprint value previously read from `ping`.
        since_version: A semver string previously read from `ping`,
            `get_pricing`, or shown in the connector. Only used if
            `since_fingerprint` isn't passed or isn't recognized.
    """
    from cited_core import __version__

    versions: list[dict[str, Any]] = list(_CHANGELOG.get("versions") or [])
    current_fp = get_tools_fingerprint() or ""

    base: dict[str, Any] = {
        "current_version": __version__,
        "current_fingerprint": current_fp,
        "since": since_fingerprint or since_version,
    }

    if _CHANGELOG_LOAD_ERROR is not None:
        return {
            **base,
            "error": True,
            "error_type": "changelog_unavailable",
            "message": (
                f"Tool changelog could not be loaded: {_CHANGELOG_LOAD_ERROR}. "
                "Cannot compute a diff. Disconnect and reconnect the Cited "
                "connector to pick up the latest tools, or contact support if "
                "this persists."
            ),
            "tools_added": [],
            "tools_changed": [],
            "tools_removed": [],
        }

    matched: list[dict[str, Any]] | None = None

    if since_fingerprint:
        matched = _entries_since_fingerprint(versions, since_fingerprint)

    if matched is None and since_version:
        matched = _entries_since_version(versions, since_version)

    if matched is None and not since_fingerprint and not since_version:
        # No inputs → return the most recent entry as the "what's new" diff
        matched = versions[:1] if versions else []

    if matched is None:
        # Unrecognized — return full history
        return {
            **base,
            "_note": (
                "Provided since_fingerprint/since_version not recognized — "
                "returning full changelog history. The diff is unbounded."
            ),
            **_aggregate_entries(versions),
        }

    if not matched:
        return {
            **base,
            "no_changes": True,
            "tools_added": [],
            "tools_changed": [],
            "tools_removed": [],
        }

    return {**base, **_aggregate_entries(matched)}
