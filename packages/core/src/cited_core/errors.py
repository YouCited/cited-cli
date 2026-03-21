from __future__ import annotations

from enum import IntEnum


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
