from __future__ import annotations

import time

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from cited_cli.api.client import CitedClient
from cited_cli.utils.errors import CitedAPIError


def watch_job(
    client: CitedClient,
    status_path: str,
    console: Console | None = None,
    poll_interval: float = 2.0,
) -> dict[str, object]:
    """Poll a job status endpoint until completion. Returns the final status response."""
    c = console or Console()

    with Live(Spinner("dots", text="Starting..."), console=c, refresh_per_second=4) as live:
        while True:
            try:
                data = client.get(status_path)
            except CitedAPIError:
                raise

            status = data.get("status", "unknown")
            progress = data.get("progress")
            message = data.get("message", "")

            if progress is not None:
                pct = (
                    int(progress * 100)
                    if isinstance(progress, float) and progress <= 1
                    else int(progress)
                )
                bar_w = 20
                filled = int((pct / 100) * bar_w)
                bar = f"{'█' * filled}{'░' * (bar_w - filled)}"
                text = Text.from_markup(
                    f"[cyan]{bar}[/cyan] {pct}% — {status} {message}"
                )
            else:
                text = Text.from_markup(f"[cyan]⟳[/cyan] {status} {message}")

            live.update(Spinner("dots", text=text))

            if status in ("completed", "complete", "done", "failed", "error", "cancelled"):
                break

            time.sleep(poll_interval)

    return data  # type: ignore[no-any-return]
