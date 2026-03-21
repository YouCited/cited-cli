from __future__ import annotations

import sys

from rich.console import Console

from cited_core.errors import CitedAPIError as CitedAPIError  # noqa: F401
from cited_core.errors import ExitCode as ExitCode  # noqa: F401
from cited_core.errors import exit_code_for_status as exit_code_for_status  # noqa: F401

err_console = Console(stderr=True)


def handle_api_error(error: CitedAPIError, json_mode: bool = False) -> None:
    code = exit_code_for_status(error.status_code)
    if json_mode:
        import json

        err_console.print(
            json.dumps(
                {
                    "error": True,
                    "status_code": error.status_code,
                    "message": error.message,
                    "error_code": error.error_code,
                }
            )
        )
    else:
        err_console.print(f"[red]Error[/red] ({error.status_code}): {error.message}")
    sys.exit(code)
