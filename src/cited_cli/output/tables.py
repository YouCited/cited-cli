from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def render_table(
    title: str,
    columns: list[str],
    rows: list[list[Any]],
    console: Console | None = None,
) -> None:
    c = console or Console()
    table = Table(title=title, show_header=True, header_style="bold cyan")
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(v) for v in row])
    c.print(table)


def render_kv(
    title: str,
    items: dict[str, Any],
    console: Console | None = None,
) -> None:
    c = console or Console()
    lines = []
    for key, value in items.items():
        lines.append(f"[bold]{key}:[/bold] {value}")
    panel = Panel("\n".join(lines), title=title, border_style="cyan")
    c.print(panel)


def render_bar(
    label: str,
    value: int | float,
    max_value: int | float = 100,
    console: Console | None = None,
) -> None:
    c = console or Console()
    bar_width = 20
    filled = int((value / max_value) * bar_width) if max_value > 0 else 0
    empty = bar_width - filled
    bar = f"[green]{'█' * filled}[/green][dim]{'░' * empty}[/dim]"
    c.print(f"  {label:<25} {bar}  {value:.0f}%")
