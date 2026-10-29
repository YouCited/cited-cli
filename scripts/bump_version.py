#!/usr/bin/env python3
"""Set the release version everywhere it is written down.

    python scripts/bump_version.py 0.8.1

Updates ``cited_core.__version__`` (the source of truth), the ``version`` of
the three pyproject.toml files, the ``cited-core`` / ``cited-mcp`` minimum
versions the CLI and cited-mcp depend on, and server.json (the MCP Registry
entry). A release PR is this script's output; merging it publishes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "packages/core/src/cited_core/__init__.py"
PYPROJECTS = [
    ROOT / "pyproject.toml",
    ROOT / "packages/core/pyproject.toml",
    ROOT / "packages/mcp/pyproject.toml",
]
SERVER_JSON = ROOT / "server.json"


def substitute(path: Path, pattern: str, replacement: str, required: bool = True) -> None:
    text = path.read_text("utf-8")
    new, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if required and count == 0:
        raise SystemExit(f"No match for {pattern!r} in {path.relative_to(ROOT)}")
    path.write_text(new, "utf-8")


def main() -> None:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        raise SystemExit("Usage: bump_version.py <major.minor.patch>")
    version = sys.argv[1]

    substitute(VERSION_FILE, r'^__version__ = ".*"', f'__version__ = "{version}"')
    for path in PYPROJECTS:
        substitute(path, r'^version = ".*"', f'version = "{version}"')
        for dep in ("cited-core", "cited-mcp"):
            substitute(path, rf'"{dep}>=[^"]*"', f'"{dep}>={version}"', required=False)

    data = json.loads(SERVER_JSON.read_text("utf-8"))
    data["version"] = version
    for pkg in data.get("packages", []):
        if pkg.get("registryType") == "pypi" and pkg.get("identifier") == "cited-mcp":
            pkg["version"] = version
    SERVER_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(f"Version set to {version}")


if __name__ == "__main__":
    main()
