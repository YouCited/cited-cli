"""Running Cited's agent tools from CLI commands.

Every data command is one tool call (``cited_core.tools``): the command turns
its options into the tool's arguments, and prints the result as JSON
(``--json``) or as a short human summary.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

import typer
from rich.console import Console

from cited_cli.output.formatter import OutputContext, print_result
from cited_cli.utils.client import get_env_and_url, get_output
from cited_cli.utils.errors import CitedAPIError, handle_api_error
from cited_core.api.client import CitedClient
from cited_core.auth.credentials import resolve_agent_api_key
from cited_core.auth.store import TokenStore
from cited_core.tools import run_tool

Formatter = Callable[[dict[str, Any], Console], None]


def tool_client(ctx: typer.Context) -> tuple[OutputContext, CitedClient, str]:
    """A client with whatever credentials there are (none is fine: public tools)."""
    out = get_output(ctx)
    cfg, profile, env, api_url = get_env_and_url(ctx)
    store = TokenStore()
    token = store.get_token(env)
    agent_key = None if token else resolve_agent_api_key(cfg, env, profile, store)
    return out, CitedClient(base_url=api_url, token=token, agent_api_key=agent_key), env


def clean(args: dict[str, Any]) -> dict[str, Any]:
    """Drop options the user didn't give, so the tool's defaults apply."""
    return {k: v for k, v in args.items() if v is not None and v != [] and v is not False}


def fail(result: dict[str, Any], status: int, out: OutputContext) -> None:
    """Print a tool error the way every command does, and exit with its code."""
    error = CitedAPIError(
        status,
        str(result.get("error") or f"HTTP {status}"),
        result.get("error_type"),
        result,
    )
    handle_api_error(error, out.json_mode)


def call(
    ctx: typer.Context, name: str, args: dict[str, Any]
) -> tuple[dict[str, Any], OutputContext]:
    """Run a tool; on an error print it and exit. Returns ``(result, output)``."""
    out, client, env = tool_client(ctx)
    try:
        result, status = run_tool(client, env, name, args)
    finally:
        client.close()
    if status >= 400:
        fail(result, status, out)
    return result, out


def run(
    ctx: typer.Context,
    name: str,
    args: dict[str, Any],
    human: Formatter | None = None,
) -> dict[str, Any]:
    """Run a tool and print its result."""
    result, out = call(ctx, name, args)
    print_result(result, out, human_formatter=human or render)
    return result


def poll(
    ctx: typer.Context,
    name: str,
    args: dict[str, Any],
    done: Callable[[dict[str, Any]], bool],
    next_args: Callable[[dict[str, Any]], dict[str, Any]],
    interval: float = 15.0,
    timeout: float = 600.0,
) -> tuple[dict[str, Any], OutputContext]:
    """Call a tool until ``done(result)``, for the ``--wait`` options."""
    deadline = time.monotonic() + timeout
    result, out = call(ctx, name, args)
    status = Console(stderr=True)
    while not done(result) and time.monotonic() < deadline:
        if not out.json_mode and not out.quiet:
            status.print(f"[dim]{result.get('status') or 'waiting'}...[/dim]")
        time.sleep(interval)
        result, out = call(ctx, name, next_args(result))
    return result, out


# ---------------------------------------------------------------------------
# Human output
# ---------------------------------------------------------------------------

# Tool results say what to call next by tool name; people read the command.
COMMAND_FOR_TOOL = {
    "free_audit": "cited audit free",
    "agent_signup": "cited agent signup",
    "account_status": "cited status",
    "buy_credits": "cited credits buy",
    "setup_business": "cited business setup",
    "get_business": "cited business get",
    "get_agent_brief": "cited business brief",
    "draft_questions": "cited audit questions",
    "quote_audit": "cited audit quote",
    "run_audit": "cited audit run",
    "get_audit": "cited audit get",
    "compare_audits": "cited audit compare",
    "schedule_recheck": "cited audit schedule",
    "get_recommendations": "cited recommend list",
    "update_recommendation": "cited recommend set",
    "generate_fixes": "cited fix generate",
    "get_fixes": "cited fix get",
    "update_fix": "cited fix done / cited fix verify",
    "search_docs": "cited docs search",
}
_TOOL_NAME_RE = re.compile(r"\b(" + "|".join(COMMAND_FOR_TOOL) + r")\b")


def as_commands(text: str) -> str:
    """``"Call run_audit"`` reads ``"Call `cited audit run`"``."""
    return _TOOL_NAME_RE.sub(lambda m: f"`{COMMAND_FOR_TOOL[m.group(1)]}`", text)


_LEAD_KEYS = ("error", "message", "headline", "summary")
_TRAILING_KEYS = ("next_step", "next_steps", "notice", "instructions")
_SKIP_KEYS = {"instructions", "status_code"}


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _table(title: str, rows: list[dict[str, Any]], console: Console) -> None:
    from cited_cli.output.tables import render_table

    columns: list[str] = []
    for row in rows:
        for key, value in row.items():
            if key not in columns and _scalar(value) and len(columns) < 7:
                columns.append(key)
    render_table(
        title,
        columns,
        [["" if row.get(c) is None else row.get(c) for c in columns] for row in rows],
        console,
    )


def render(data: dict[str, Any], console: Console) -> None:
    """A readable default for any tool result: the scalars, then tables."""
    from cited_cli.output.tables import render_kv

    for key in _LEAD_KEYS:
        if isinstance(data.get(key), str):
            console.print(as_commands(data[key]), markup=False)
    scalars = {
        k: v
        for k, v in data.items()
        if _scalar(v) and v is not None and k not in _LEAD_KEYS + _TRAILING_KEYS
        and k not in _SKIP_KEYS
    }
    if scalars:
        render_kv("Result", scalars, console)
    for key, value in data.items():
        if key in _TRAILING_KEYS:
            continue
        if isinstance(value, dict) and value and all(_scalar(v) for v in value.values()):
            render_kv(key.replace("_", " ").title(), value, console)
        elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            _table(key.replace("_", " ").title(), value, console)
        elif isinstance(value, list) and value:
            console.print(f"[bold]{key.replace('_', ' ').title()}[/bold]")
            for item in value:
                console.print(f"  • {item}")
    if data.get("notice"):
        console.print(f"→ {data['notice']}", style="yellow", markup=False)
    steps = data.get("next_steps")
    if isinstance(steps, list):
        for step in steps:
            console.print(f"→ {as_commands(str(step))}", markup=False)
    if isinstance(data.get("next_step"), str):
        console.print(f"→ {as_commands(data['next_step'])}", markup=False)
