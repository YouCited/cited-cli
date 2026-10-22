#!/usr/bin/env python3
"""Refresh the tool manifest bundled with cited-core from the Cited API.

``packages/core/src/cited_core/tools.json`` is what the CLI and cited-mcp use
when the API can't be reached. Run this after the API's tools change:

    python scripts/sync_tools_manifest.py              # api.youcited.com
    python scripts/sync_tools_manifest.py --env dev
    python scripts/sync_tools_manifest.py --url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from cited_core.config.constants import ENVIRONMENTS

TARGET = Path(__file__).resolve().parents[1] / "packages/core/src/cited_core/tools.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", default="prod", choices=sorted(ENVIRONMENTS))
    parser.add_argument("--url", help="API base URL (overrides --env)")
    args = parser.parse_args()

    base = (args.url or ENVIRONMENTS[args.env]).rstrip("/")
    response = httpx.get(f"{base}/agent/tools", timeout=30)
    response.raise_for_status()
    manifest = response.json()
    if not isinstance(manifest, dict) or not manifest.get("tools"):
        print(f"No tools in the response from {base}", file=sys.stderr)
        return 1

    old = json.loads(TARGET.read_text("utf-8")) if TARGET.exists() else {}
    TARGET.write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")

    before = {t["name"] for t in old.get("tools", [])}
    after = {t["name"] for t in manifest["tools"]}
    print(f"{len(after)} tools, version {manifest.get('version')} (was {old.get('version')})")
    for name in sorted(after - before):
        print(f"  + {name}")
    for name in sorted(before - after):
        print(f"  - {name}")
    if after != before:
        print("Update the CLI commands and tests/test_feature_parity.py to match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
