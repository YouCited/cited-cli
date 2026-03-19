#!/usr/bin/env python3
"""
cleanup_dev.py — Find and remove test assets from the Cited dev environment.

Lists all businesses (and their audit templates) on the target environment,
lets you pick which ones to delete, and removes them along with associated
templates.

Requirements: `cited` CLI installed and authenticated (`cited login` first).

Usage:
    python3 scripts/cleanup_dev.py              # interactive — prompts before deleting
    python3 scripts/cleanup_dev.py --dry-run    # just list, don't delete anything
    python3 scripts/cleanup_dev.py --auto       # auto-delete businesses matching test patterns
    python3 scripts/cleanup_dev.py --env prod   # target a different environment
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime

# Patterns that identify test businesses (case-insensitive substring match)
TEST_PATTERNS = [
    "e2e test",
    "cli test",
    "pipeline test",
    "test corp",
    "test business",
    "runbook test",
]


def cited_json(env: str, *args: str) -> dict | list:
    """Run a cited command with --json and return parsed output."""
    cmd = ["cited", "--env", env, "--json", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Try to parse error JSON, fall back to stderr
        try:
            err = json.loads(result.stdout or result.stderr)
            msg = err.get("message", result.stderr)
        except (json.JSONDecodeError, TypeError):
            msg = result.stderr.strip() or result.stdout.strip()
        print(f"  ✗ Command failed: {' '.join(args)}")
        print(f"    {msg}")
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"  ✗ Could not parse JSON from: {' '.join(args)}")
        return []


def cited_run(env: str, *args: str) -> bool:
    """Run a cited command (non-JSON) and return success."""
    cmd = ["cited", "--env", env, *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def is_test_business(name: str) -> bool:
    """Check if a business name matches known test patterns."""
    lower = name.lower()
    return any(p in lower for p in TEST_PATTERNS)


def format_age(created_at: str) -> str:
    """Return a human-readable age string from an ISO timestamp."""
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        now = datetime.now(created.tzinfo)
        delta = now - created
        if delta.days > 0:
            return f"{delta.days}d ago"
        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours}h ago"
        minutes = delta.seconds // 60
        return f"{minutes}m ago"
    except (ValueError, TypeError):
        return "unknown"


def list_businesses(env: str) -> list[dict]:
    """Fetch all businesses and annotate with test pattern match."""
    businesses = cited_json(env, "business", "list")
    if not isinstance(businesses, list):
        return []
    return businesses


def list_templates(env: str, business_id: str) -> list[dict]:
    """Fetch audit templates for a business."""
    templates = cited_json(env, "audit", "template", "list", "--business", business_id)
    if not isinstance(templates, list):
        return []
    return templates


def delete_business(env: str, business_id: str, name: str) -> bool:
    """Delete a business and return success."""
    ok = cited_run(env, "business", "delete", business_id, "--yes")
    if ok:
        print(f"  ✓ Deleted business {business_id[:8]} ({name})")
    else:
        print(f"  ✗ Failed to delete business {business_id[:8]} ({name})")
    return ok


def delete_template(env: str, template_id: str, name: str) -> bool:
    """Delete an audit template and return success."""
    ok = cited_run(env, "audit", "template", "delete", template_id, "--yes")
    if ok:
        print(f"  ✓ Deleted template {template_id[:8]} ({name})")
    else:
        print(f"  ✗ Failed to delete template {template_id[:8]} ({name})")
    return ok


def print_business_table(businesses: list[dict]) -> None:
    """Print a formatted table of businesses."""
    print(f"\n{'#':>3}  {'ID':8}  {'Test?':5}  {'Age':>8}  Name")
    print(f"{'─'*3}  {'─'*8}  {'─'*5}  {'─'*8}  {'─'*30}")
    for i, b in enumerate(businesses, 1):
        bid = b.get("id", "")[:8]
        name = b.get("name", "")
        age = format_age(b.get("created_at", ""))
        test = "YES" if is_test_business(name) else ""
        print(f"{i:>3}  {bid}  {test:<5}  {age:>8}  {name}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean up test assets from a Cited environment."
    )
    parser.add_argument(
        "--env", default="dev",
        help="Target environment (default: dev)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List assets without deleting anything",
    )
    parser.add_argument(
        "--auto", action="store_true",
        help="Auto-delete businesses matching test patterns (no prompts)",
    )
    args = parser.parse_args()

    env = args.env
    print(f"Scanning {env} environment...\n")

    # 1. List businesses
    businesses = list_businesses(env)
    if not businesses:
        print("No businesses found.")
        return

    print_business_table(businesses)

    if args.dry_run:
        test_count = sum(1 for b in businesses if is_test_business(b.get("name", "")))
        print(f"Dry run: {test_count} test business(es) would be deleted.")
        print("Run without --dry-run to delete.")
        return

    # 2. Determine which businesses to delete
    to_delete: list[dict] = []

    if args.auto:
        to_delete = [b for b in businesses if is_test_business(b.get("name", ""))]
        if not to_delete:
            print("No businesses match test patterns. Nothing to clean up.")
            return
        print(f"Auto mode: {len(to_delete)} business(es) match test patterns.")
    else:
        # Interactive mode
        print("Enter business numbers to delete (comma-separated), 'test' for all")
        print("test-pattern matches, or 'q' to quit:")
        choice = input("> ").strip().lower()

        if choice in ("q", "quit", ""):
            print("Aborted.")
            return
        elif choice == "test":
            to_delete = [b for b in businesses if is_test_business(b.get("name", ""))]
        else:
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(",")]
                to_delete = [businesses[i] for i in indices if 0 <= i < len(businesses)]
            except (ValueError, IndexError):
                print("Invalid input. Aborted.")
                return

    if not to_delete:
        print("Nothing selected. Aborted.")
        return

    # 3. Confirm
    if not args.auto:
        print(f"\nWill delete {len(to_delete)} business(es):")
        for b in to_delete:
            print(f"  • {b['id'][:8]}  {b.get('name', '')}")
        confirm = input("\nProceed? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    # 4. Delete templates first, then businesses
    deleted_templates = 0
    deleted_businesses = 0

    for b in to_delete:
        bid = b["id"]
        name = b.get("name", "")
        print(f"\n── {name} ({bid[:8]}) ──")

        # Delete associated templates
        templates = list_templates(env, bid)
        for t in templates:
            tid = t.get("id", "")
            tname = t.get("name", "")
            if delete_template(env, tid, tname):
                deleted_templates += 1

        # Delete the business
        if delete_business(env, bid, name):
            deleted_businesses += 1

    # 5. Summary
    print(f"\n{'─'*40}")
    print(f"Cleanup complete:")
    print(f"  Businesses deleted: {deleted_businesses}")
    print(f"  Templates deleted:  {deleted_templates}")

    # 6. Verify
    remaining = list_businesses(env)
    print(f"  Businesses remaining: {len(remaining)}")


if __name__ == "__main__":
    main()
