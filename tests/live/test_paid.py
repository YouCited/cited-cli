"""The paid path end to end on prod: run a real audit with the test account's
credits, wait for the report, then for its recommendations.

    CITED_SMOKE_AGENT_KEY=cak_... pytest tests/live/test_paid.py --live --paid

Only the weekly Paid audit check workflow runs it (about $10 of the test
account's credits and $5 of AI a run). It fails when an audit fails, when no
engine answered, or when no recommendations arrive.
"""

from __future__ import annotations

import json
import time

import pytest

pytestmark = [pytest.mark.live, pytest.mark.paid]

AUDIT_TIMEOUT_S = 30 * 60
RECOMMENDATIONS_TIMEOUT_S = 20 * 60
RUNNING = ("pending", "processing", "queued", "running", "drafting")


def cited(runner, cli_app, *args: str) -> dict:
    result = runner.invoke(cli_app, ["--env", "prod", "--json", *args])
    assert result.exit_code == 0, result.output
    data: dict = json.loads(result.stdout)
    return data


def wait_for(check, timeout_s: float, interval_s: float = 30.0):
    deadline = time.monotonic() + timeout_s
    while True:
        value = check()
        if value is not None:
            return value
        if time.monotonic() > deadline:
            pytest.fail(f"Gave up after {timeout_s / 60:.0f} minutes")
        time.sleep(interval_s)


def test_paid_audit_reports_real_answers_and_recommendations(runner, cli_app, agent_key):
    started = cited(runner, cli_app, "audit", "run", "--yes")
    audit_id = started.get("audit_id")
    assert audit_id, started

    def finished() -> dict | None:
        report = cited(runner, cli_app, "audit", "get", audit_id)
        return None if report.get("status") in RUNNING else report

    report = wait_for(finished, AUDIT_TIMEOUT_S)
    assert report.get("status") == "completed", report

    answers = [
        model.get("answer")
        for question in report.get("questions") or []
        for model in question.get("models") or []
    ]
    assert answers, "the report has no answers"
    answered = [a for a in answers if isinstance(a, str) and a.strip()]
    # Every engine can have a bad day; most of them can't
    assert len(answered) >= len(answers) / 2, f"{len(answered)} of {len(answers)} answered"

    def recommendations() -> dict | None:
        # Not found until the audit's follow-up queues them
        result = runner.invoke(
            cli_app, ["--env", "prod", "--json", "recommend", "list", "--audit", audit_id]
        )
        if result.exit_code != 0:
            return None
        data: dict = json.loads(result.stdout)
        if data.get("status") in RUNNING:
            return None
        return data

    data = wait_for(recommendations, RECOMMENDATIONS_TIMEOUT_S)
    assert data.get("items"), data
