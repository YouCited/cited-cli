from __future__ import annotations

import sys
from typing import Any

from rich.console import Console

from cited_core.errors import CitedAPIError as CitedAPIError  # noqa: F401
from cited_core.errors import ExitCode as ExitCode  # noqa: F401
from cited_core.errors import exit_code_for_status as exit_code_for_status  # noqa: F401

err_console = Console(stderr=True)

# Fields of a structured error detail worth showing to the user.
_DETAIL_FIELDS = ("credits_needed", "balance", "buy_url", "claim_url")

_NEXT_STEPS: dict[str, str] = {
    "insufficient_credits": (
        "Buy credits with: cited credits buy pack_20 (or pay for one audit: "
        "cited credits buy-audit)"
    ),
    "purchase_required": (
        "This needs an account that has bought credits at least once. "
        "Buy with: cited credits buy pack_20 (or: cited credits buy-audit)"
    ),
    "login_required": (
        "Your saved login is missing or has expired. Sign in again with: cited login "
        "(or forget it with: cited logout)"
    ),
    "api_unreachable": (
        "Check your connection. If the address above isn't https://api.youcited.com, "
        "switch to production with: cited config set environment prod"
    ),
    "claim_required": (
        "This agent account is unclaimed. Ask the person to open the claim link "
        "from `cited agent signup` and enter the code."
    ),
}


def handle_api_error(error: CitedAPIError, json_mode: bool = False) -> None:
    code = exit_code_for_status(error.status_code)
    detail: dict[str, Any] = error.detail or {}
    if json_mode:
        import json

        payload: dict[str, Any] = {
            "error": True,
            "status_code": error.status_code,
            "message": error.message,
            "error_code": error.error_code,
        }
        for key in _DETAIL_FIELDS:
            if detail.get(key) is not None:
                payload[key] = detail[key]
        # Plain write, not Rich: Rich would wrap long lines and parse [markup].
        sys.stderr.write(json.dumps(payload) + "\n")
    else:
        err_console.print(f"[red]Error[/red] ({error.status_code}): {error.message}")
        if detail.get("credits_needed") is not None:
            err_console.print(
                f"  Credits needed: {detail['credits_needed']}  "
                f"Balance: {detail.get('balance', '?')}"
            )
        for key, label in (("buy_url", "Buy credits"), ("claim_url", "Claim the account")):
            if detail.get(key):
                err_console.print(f"  {label}: {detail[key]}")
        hint = _NEXT_STEPS.get(error.error_code or "")
        if hint:
            err_console.print(f"  {hint}")
    sys.exit(code)
