from __future__ import annotations

import sys
from enum import IntEnum

from rich.console import Console

err_console = Console(stderr=True)


class ExitCode(IntEnum):
    SUCCESS = 0
    ERROR = 1
    AUTH_ERROR = 2
    NOT_FOUND = 3
    VALIDATION_ERROR = 4
    RATE_LIMITED = 5


class CitedAPIError(Exception):
    def __init__(self, status_code: int, message: str, error_code: str | None = None):
        self.status_code = status_code
        self.message = message
        self.error_code = error_code
        super().__init__(message)


def exit_code_for_status(status_code: int) -> ExitCode:
    if status_code == 401 or status_code == 403:
        return ExitCode.AUTH_ERROR
    if status_code == 404:
        return ExitCode.NOT_FOUND
    if status_code == 422:
        return ExitCode.VALIDATION_ERROR
    if status_code == 429:
        return ExitCode.RATE_LIMITED
    return ExitCode.ERROR


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
