"""Check an installed cited-cli the way a user gets it, not the source tree.

Run it with the Python of a clean venv that has the built wheels installed,
and with ``-I`` so the repo's own sources can't be imported by accident:

    .venv-smoke/bin/python -I scripts/smoke_install.py --version 0.8.1

Everything runs offline against ``--env local`` (nothing listens there), so the
CLI and cited-mcp fall back to the bundled tool list. Exits non-zero on the
first failure.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

TIMEOUT = 60


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def find_bin(name: str) -> str:
    here = Path(sys.executable).parent
    for candidate in (here / name, here / f"{name}.exe"):
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if not found:
        fail(f"{name} is not installed next to {sys.executable} or on PATH")
    return str(found)


def run(args: list[str], env: dict[str, str], code: int = 0, timeout: int = TIMEOUT) -> str:
    try:
        done = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, env=env, check=False
        )
    except subprocess.TimeoutExpired:
        fail(f"{' '.join(args)} hung for {timeout}s")
    if done.returncode != code:
        fail(f"{' '.join(args)} exited {done.returncode}\n{done.stdout}\n{done.stderr}")
    if "Traceback" in done.stderr:
        fail(f"{' '.join(args)} printed a traceback\n{done.stderr}")
    return done.stdout + done.stderr


def command_paths() -> list[list[str]]:
    """Every command and group in the installed CLI, e.g. ["audit", "free"]."""
    import typer

    from cited_cli.app import app

    paths: list[list[str]] = []

    def walk(command: Any, prefix: list[str]) -> None:
        paths.append(prefix)
        # Typer vendors its own click, so look for subcommands, not a class.
        for name, sub in sorted((getattr(command, "commands", None) or {}).items()):
            if not getattr(sub, "hidden", False):
                walk(sub, [*prefix, name])

    walk(typer.main.get_command(app), [])
    return paths


async def mcp_tool_names(cited_mcp: str, env: dict[str, str]) -> list[str]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=cited_mcp, env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listed = await session.list_tools()
        return [t.name for t in listed.tools]


def check_keychain(cited: str, env: dict[str, str]) -> None:
    """Commands that read or clear the saved login must finish, never wait on a
    keychain prompt. Nothing listens on --env local, so status fails fast after
    the keychain read."""
    out = run([cited, "--env", "local", "--json", "status"], env, code=1, timeout=30)
    if "api_unreachable" not in out:
        fail(f"cited status didn't get past the keychain to the API:\n{out}")
    out = run([cited, "--env", "local", "logout"], env, code=1, timeout=30)
    if "Not logged in" not in out:
        fail(f"cited logout didn't read the keychain cleanly:\n{out}")
    out = run([cited, "--env", "local", "audit", "free", "acme.com", "--no-wait"], env, code=1)
    if "Could not reach the Cited API" not in out:
        fail(f"cited audit free didn't reach the API step:\n{out}")
    print("ok  status, logout and audit free finish without a keychain prompt")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="Version the packages should report")
    parser.add_argument(
        "--keychain-only",
        action="store_true",
        help="Only check that commands reading the keychain finish (for a locked keychain)",
    )
    args = parser.parse_args()
    expected = args.version

    from cited_core import __version__
    from cited_core.tools import bundled_manifest, tool_names

    if __version__ != expected:
        fail(f"cited_core reports {__version__}, expected {expected}")
    tools = tool_names(bundled_manifest())
    if len(tools) < 10:
        fail(f"bundled tools.json has only {len(tools)} tools")

    cited = find_bin("cited")
    cited_mcp = find_bin("cited-mcp")
    home = tempfile.mkdtemp(prefix="cited-smoke-")
    env = {
        **os.environ,
        "HOME": home,
        "USERPROFILE": home,
        "CITED_ENV": "local",
        "PYTHONIOENCODING": "utf-8",
    }
    env.pop("CITED_AGENT_API_KEY", None)
    env.pop("CITED_TOKEN", None)

    if args.keychain_only:
        check_keychain(cited, env)
        return

    out = run([cited, "--version"], env)
    if expected not in out:
        fail(f"cited --version printed {out.strip()!r}, expected {expected}")
    print(f"ok  cited --version: {out.strip()}")

    paths = command_paths()
    for path in paths:
        run([cited, *path, "--help"], env)
    print(f"ok  --help on {len(paths)} commands and groups")

    out = run([cited, "--env", "local", "--json", "tools", "list"], env)
    missing = [name for name in tools if name not in out]
    if missing:
        fail(f"cited tools list (bundled fallback) is missing {missing}")
    print(f"ok  cited tools list falls back to the bundled {len(tools)} tools")

    names = asyncio.run(asyncio.wait_for(mcp_tool_names(cited_mcp, env), TIMEOUT))
    expected_names = [*tools, "login", "logout"]
    if names != expected_names:
        fail(f"cited-mcp listed {names}, expected {expected_names}")
    print(f"ok  cited-mcp handshake lists {len(names)} tools")


if __name__ == "__main__":
    main()
