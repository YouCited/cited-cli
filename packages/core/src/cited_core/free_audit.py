"""Free audit: the no-login GEO audit behind the youcited.com homepage prompt.

``GET /free-audit?url=...`` starts an audit (or returns the one already run for
that domain in the last 24 hours) and hands back a ``report_url``. Fetching the
report returns status while the audit runs and the full report once it is done.
Neither call needs a token, so these work before the user has an account.
"""

from __future__ import annotations

from typing import Any

from cited_core.api import endpoints
from cited_core.api.client import LONG_TIMEOUT, CitedClient


def report_token(report_url: str) -> str:
    """Extract the report token from a ``report_url`` returned by the API."""
    return report_url.rstrip("/").rsplit("/", 1)[-1]


def check_free_audit(client: CitedClient, url: str) -> dict[str, Any]:
    """Start (or resume) the free audit for ``url`` and return its current report.

    Safe to call repeatedly: the API reuses the same audit for a domain, so
    calling again later returns progress or, once complete, the full report.
    """
    # Starting a new audit generates its questions in-request, which can be slow.
    started = client.get(endpoints.FREE_AUDIT, params={"url": url}, timeout=LONG_TIMEOUT)
    token = report_token(started["report_url"])
    report: dict[str, Any] = client.get(endpoints.FREE_AUDIT_REPORT.format(token=token))
    report.setdefault("report_url", started["report_url"])
    report.setdefault("share_url", started.get("share_url"))
    report.setdefault("domain", started.get("domain"))
    return report


def is_finished(report: dict[str, Any]) -> bool:
    return report.get("status") not in ("pending", "processing")
