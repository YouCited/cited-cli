from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console


@dataclass
class OutputContext:
    json_mode: bool = False
    quiet: bool = False
    no_color: bool = False
    _console: Console | None = field(default=None, repr=False)

    @property
    def console(self) -> Console:
        if self._console is None:
            self._console = Console(
                no_color=self.no_color,
                quiet=self.quiet and not self.json_mode,
            )
        return self._console


def print_result(
    data: Any,
    ctx: OutputContext,
    human_formatter: Callable[[Any, Console], None] | None = None,
) -> None:
    if ctx.json_mode:
        sys.stdout.write(json.dumps(data, indent=2, default=str) + "\n")
    elif human_formatter:
        human_formatter(data, ctx.console)
    else:
        ctx.console.print_json(json.dumps(data, default=str))


def print_success(message: str, ctx: OutputContext) -> None:
    if ctx.json_mode:
        sys.stdout.write(json.dumps({"status": "ok", "message": message}) + "\n")
    elif not ctx.quiet:
        ctx.console.print(f"[green]✓[/green] {message}")


def print_error(message: str, ctx: OutputContext, status_code: int | None = None) -> None:
    if ctx.json_mode:
        err: dict[str, Any] = {"error": True, "message": message}
        if status_code:
            err["status_code"] = status_code
        sys.stderr.write(json.dumps(err) + "\n")
    else:
        Console(stderr=True).print(f"[red]Error:[/red] {message}")


def print_warning(message: str, ctx: OutputContext) -> None:
    if not ctx.json_mode and not ctx.quiet:
        ctx.console.print(f"[yellow]Warning:[/yellow] {message}")
