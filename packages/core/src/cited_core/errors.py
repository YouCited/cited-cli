from __future__ import annotations

from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    SUCCESS = 0
    ERROR = 1
    AUTH_ERROR = 2
    NOT_FOUND = 3
    VALIDATION_ERROR = 4
    RATE_LIMITED = 5
    PAYMENT_REQUIRED = 6


class CitedAPIError(Exception):
    """An error response from the Cited API.

    ``detail`` holds the structured ``detail`` object when the API sent one,
    e.g. ``{"error": "insufficient_credits", "message": ..., "credits_needed": 10,
    "balance": 2, "buy_url": ...}``. ``error_code`` is the machine-readable
    code (``detail["error"]`` or a top-level ``error_code``).
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        error_code: str | None = None,
        detail: dict[str, Any] | None = None,
    ):
        self.status_code = status_code
        self.message = message
        self.error_code = error_code
        self.detail = detail
        super().__init__(message)


def exit_code_for_status(status_code: int) -> ExitCode:
    if status_code == 401 or status_code == 403:
        return ExitCode.AUTH_ERROR
    if status_code == 402:
        return ExitCode.PAYMENT_REQUIRED
    if status_code == 404:
        return ExitCode.NOT_FOUND
    if status_code == 422:
        return ExitCode.VALIDATION_ERROR
    if status_code == 429:
        return ExitCode.RATE_LIMITED
    return ExitCode.ERROR
