"""CLI commands: each one runs one tool with the right arguments."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

API = "https://dev.youcited.com"


@pytest.fixture
def tool_calls(creds):
    """Mock every tool; record (name, arguments). Set responses via the dict."""
    calls: list[tuple[str, dict]] = []
    responses: dict[str, tuple[int, dict]] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        calls.append((name, json.loads(request.content or b"{}")))
        status, body = responses.get(name, (200, {"ok": True}))
        if callable(body):
            body = body(calls)
        return httpx.Response(status, json=body)

    with respx.mock:
        respx.post(url__startswith=f"{API}/agent/tools/").mock(side_effect=_handler)
        yield calls, responses


def _cli(runner, cli_app, *args):
    return runner.invoke(cli_app, ["--env", "dev", "--json", *args])


@pytest.mark.parametrize(
    ("argv", "tool", "arguments"),
    [
        (["status"], "account_status", {}),
        (["auth", "status"], "account_status", {}),
        (["audit", "free", "acme.com", "--no-wait"], "free_audit", {"url": "acme.com"}),
        (["agent", "signup", "--name", "Claude"], "agent_signup", {"agent_name": "Claude"}),
        (
            ["agent", "signup", "--free-audit", "instant_ab_cd"],
            "agent_signup",
            {"free_audit_token": "instant_ab_cd"},
        ),
        (["credits", "buy", "pack_20"], "buy_credits", {"pack_id": "pack_20"}),
        (["credits", "buy", "--one-audit"], "buy_credits", {"one_audit": True}),
        (["credits", "buy", "--voucher", "HELLO"], "buy_credits", {"voucher_code": "HELLO"}),
        (
            ["business", "setup", "-w", "acme.com", "--persona", "Ops lead: buys tools"],
            "setup_business",
            {"website": "acme.com",
             "personas": [{"name": "Ops lead", "description": "buys tools"}]},
        ),
        (
            ["business", "setup", "--id", "b1", "--remove-offering", "o1"],
            "setup_business",
            {"business_id": "b1", "offerings": [{"id": "o1", "remove": True}]},
        ),
        (["business", "get"], "get_business", {}),
        (["business", "get", "b1"], "get_business", {"business_id": "b1"}),
        (["business", "brief", "b1"], "get_agent_brief", {"business_id": "b1"}),
        (
            ["audit", "questions", "-q", "best widgets", "-q", "widget makers"],
            "draft_questions",
            {"questions": ["best widgets", "widget makers"]},
        ),
        (["audit", "quote", "-m", "gpt-5"], "quote_audit", {"models": ["gpt-5"]}),
        (["audit", "run", "--yes"], "run_audit", {"confirm": True}),
        (["audit", "get"], "get_audit", {}),
        (["audit", "get", "a1", "--answers"], "get_audit",
         {"audit_id": "a1", "include_answers": True}),
        (["audit", "compare", "a2", "--baseline", "a1"], "compare_audits",
         {"audit_id": "a2", "baseline_audit_id": "a1"}),
        (["audit", "schedule", "--every", "14", "--no-email"], "schedule_recheck",
         {"every_days": 14, "email_alerts": False}),
        (["recommend", "list", "--audit", "a1"], "get_recommendations", {"audit_id": "a1"}),
        (["recommend", "set", "k1", "done"], "update_recommendation",
         {"item_key": "k1", "status": "done"}),
        (["fix", "generate", "k1", "k2", "--yes"], "generate_fixes",
         {"item_keys": ["k1", "k2"], "confirm": True}),
        (["fix", "list", "--state", "ready"], "get_fixes", {"state": "ready"}),
        (["fix", "get", "f1"], "get_fixes", {"fix_id": "f1"}),
        (["fix", "done", "f1"], "update_fix", {"fix_id": "f1", "action": "done"}),
        (["fix", "undo", "f1"], "update_fix", {"fix_id": "f1", "action": "undo"}),
        (["fix", "verify", "f1"], "update_fix", {"fix_id": "f1", "action": "verify"}),
        (["docs", "search", "credits"], "search_docs", {"query": "credits", "limit": 5}),
        (["docs", "get", "billing/credits"], "search_docs", {"path": "billing/credits"}),
        (["tools", "call", "get_audit", '{"limit": 3}'], "get_audit", {"limit": 3}),
    ],
)
def test_command_runs_its_tool(runner, cli_app, tool_calls, argv, tool, arguments):
    calls, _ = tool_calls
    result = _cli(runner, cli_app, *argv)
    assert result.exit_code == 0, result.output
    assert calls == [(tool, arguments)]


def test_json_output_is_the_tool_result(runner, cli_app, tool_calls):
    _, responses = tool_calls
    responses["get_business"] = (200, {"businesses": [{"id": "b1", "name": "Acme"}]})
    result = _cli(runner, cli_app, "business", "get")
    assert json.loads(result.output) == {"businesses": [{"id": "b1", "name": "Acme"}]}


def test_tool_errors_set_the_exit_code(runner, cli_app, tool_calls):
    _, responses = tool_calls
    responses["run_audit"] = (
        402,
        {"error": "Not enough credits", "status_code": 402, "error_type": "insufficient_credits",
         "credits_needed": 8},
    )
    result = _cli(runner, cli_app, "audit", "run", "--yes")
    assert result.exit_code == 6
    responses["get_business"] = (
        401, {"error": "Sign in first", "status_code": 401, "error_type": "login_required"}
    )
    assert _cli(runner, cli_app, "business", "get").exit_code == 2


def test_spending_without_yes_in_json_mode_only_quotes(runner, cli_app, tool_calls):
    calls, responses = tool_calls
    responses["run_audit"] = (
        200, {"confirmation_required": True, "credits": 10, "message": "Ask the user"}
    )
    result = _cli(runner, cli_app, "audit", "run")
    assert result.exit_code == 0
    assert json.loads(result.output)["confirmation_required"] is True
    assert calls == [("run_audit", {})]


def test_free_audit_waits_for_the_report(runner, cli_app, tool_calls, monkeypatch):
    calls, responses = tool_calls
    monkeypatch.setattr("cited_cli.utils.tools.time.sleep", lambda s: None)

    def _report(seen):
        if len(seen) == 1:
            return {"status": "pending", "report_token": "tok"}
        return {"status": "completed", "score": 42, "report_token": "tok"}

    responses["free_audit"] = (200, _report)
    result = _cli(runner, cli_app, "audit", "free", "acme.com")
    assert result.exit_code == 0, result.output
    assert calls == [("free_audit", {"url": "acme.com"}),
                     ("free_audit", {"report_token": "tok"})]
    assert json.loads(result.output)["score"] == 42


def test_fix_get_saves_files(runner, cli_app, tool_calls, tmp_path):
    _, responses = tool_calls
    responses["get_fixes"] = (
        200,
        {"fix_id": "f1", "files": [
            {"file_name": "faq.html", "content": "<p>hi</p>"},
            {"file_name": "../evil.txt", "content": "x"},
        ]},
    )
    out_dir = tmp_path / "fix"
    result = _cli(runner, cli_app, "fix", "get", "f1", "--save", str(out_dir))
    assert result.exit_code == 0, result.output
    assert (out_dir / "faq.html").read_text() == "<p>hi</p>"
    assert (out_dir / "evil.txt").exists()
    assert not (tmp_path / "evil.txt").exists()


def test_signup_never_prints_the_key(runner, cli_app, tool_calls, creds):
    _, responses = tool_calls
    responses["agent_signup"] = (200, {"api_key": "cak_secret", "claim": {"code": "123456"}})
    result = _cli(runner, cli_app, "agent", "signup")
    assert result.exit_code == 0
    assert "cak_secret" not in result.output
    assert creds.get_agent_key("dev") == "cak_secret"


def test_saved_agent_key_is_sent(runner, cli_app, creds):
    creds.save_agent_key("dev", "cak_saved")
    with respx.mock:
        route = respx.post(f"{API}/agent/tools/account_status").mock(
            return_value=httpx.Response(200, json={"signed_in": True})
        )
        assert _cli(runner, cli_app, "status").exit_code == 0
    assert route.calls[0].request.headers["X-Agent-API-Key"] == "cak_saved"


def test_human_output_names_commands_not_tools(runner, cli_app, tool_calls):
    _, responses = tool_calls
    responses["setup_business"] = (
        200,
        {"created": True, "business": {"id": "b1", "name": "Acme"},
         "next_step": "Call draft_questions to draft the buyer questions to audit."},
    )
    result = runner.invoke(cli_app, ["--env", "dev", "business", "setup", "-w", "acme.com"])
    assert result.exit_code == 0, result.output
    assert "cited audit questions" in result.output
    assert "draft_questions" not in result.output


def test_expired_login_says_to_sign_in_again(runner, cli_app, tool_calls):
    _, responses = tool_calls
    responses["account_status"] = (401, {"detail": "Invalid session"})
    result = runner.invoke(cli_app, ["--env", "dev", "status"])
    assert result.exit_code == 2
    assert "Invalid session" in result.output
    assert "cited login" in result.output


def test_free_audit_says_when_a_result_is_cached(runner, cli_app, tool_calls):
    _, responses = tool_calls
    report = {
        "status": "completed",
        "domain": "acme.com",
        "completed_at": "2026-10-27T12:00:00+00:00",
        "cache_hours": 24,
        "reused": True,
        "report_token": "tok",
    }
    responses["free_audit"] = (200, report)
    result = runner.invoke(cli_app, ["--env", "dev", "audit", "free", "acme.com"])
    assert result.exit_code == 0, result.output
    # Rich wraps at the console width, which differs by OS.
    text = " ".join(result.output.split())
    assert "Cached result from Oct 27" in text
    assert "cached for 24 hours" in text

    responses["free_audit"] = (200, {**report, "reused": False})
    result = runner.invoke(cli_app, ["--env", "dev", "audit", "free", "acme.com"])
    assert "Checked Oct 27" in result.output
    assert "Cached" not in result.output
