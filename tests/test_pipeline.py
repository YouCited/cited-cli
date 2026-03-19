"""
Integration and unit tests for the full cited CLI pipeline.

Assumes the user is already logged in to the dev environment (pre-seeded token).

Pipeline under test:
  1.  cited business create           → extracts BUSINESS_ID
  2.  cited audit template create     → extracts TEMPLATE_ID
  3.  cited audit start <TEMPLATE_ID> → extracts AUDIT_JOB_ID
  4.  cited job watch  <AUDIT_JOB_ID> → polls until completed
  5.  cited audit result <AUDIT_JOB_ID>  → displays questions / citations
  6.  cited business crawl <BUSINESS_ID> → triggers crawl
  7.  cited business health <BUSINESS_ID> → displays health scores
  8.  cited recommend start <AUDIT_JOB_ID>   → extracts RECOMMEND_JOB_ID
  9.  cited job watch  <RECOMMEND_JOB_ID>    → polls until completed
  10. cited recommend insights <RECOMMEND_JOB_ID> → prints source table
  11. cited solution start <RECOMMEND_JOB_ID> --type ... --source ... → nudge to web

State threading strategy
------------------------
Every command that produces an ID is run with the global --json flag.
`json.loads(result.output)` extracts the ID and passes it to the next command,
mirroring the bash pattern of `BUSINESS_ID=$(cited --json business create ...)`.

watch_job is monkeypatched to return an instant "completed" dict — this keeps
tests fast and avoids Rich's Live renderer interacting with the CliRunner's
StringIO stdout.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

from cited_cli.app import app

# ─────────────────────────────────────────────────────────────────────────────
# Pipeline-wide ID constants
# These UUIDs are used as the canonical IDs throughout all tests in this file.
# ─────────────────────────────────────────────────────────────────────────────
BUSINESS_ID       = "b1a2c3d4-e5f6-7890-abcd-ef1234567890"
TEMPLATE_ID       = "t1a2c3d4-e5f6-7890-abcd-ef1234567891"
AUDIT_JOB_ID      = "a1a2c3d4-e5f6-7890-abcd-ef1234567892"
RECOMMEND_JOB_ID  = "r1a2c3d4-e5f6-7890-abcd-ef1234567893"
SOLUTION_JOB_ID   = "s1a2c3d4-e5f6-7890-abcd-ef1234567894"
CRAWL_JOB_ID      = "c1a2c3d4-e5f6-7890-abcd-ef1234567895"
QI_SOURCE_ID      = "qi-abc123def456"       # question_insight source
HTH_COMPETITOR_DOMAIN = "competitorx.com"  # head_to_head competitor_domain

# Dev API base URL (matches cited_cli/config/constants.py ENVIRONMENTS["dev"])
DEV_API = "https://dev.youcited.com"
DEV_WEB = "https://dev.youcited.com"

# ─────────────────────────────────────────────────────────────────────────────
# Canonical mock API responses
# Each dict mirrors what the real backend would return for that endpoint.
# ─────────────────────────────────────────────────────────────────────────────
MOCK_BUSINESS = {
    "id": BUSINESS_ID,
    "name": "Acme GEO Corp",
    "website": "https://acme.example.com",
    "industry": "SaaS",
    "description": "Acme makes AI-powered tools for enterprise teams with great GEO presence.",
    "created_at": "2026-03-17T12:00:00Z",
    "updated_at": "2026-03-17T12:00:00Z",
}

MOCK_TEMPLATE = {
    "id": TEMPLATE_ID,
    "name": "Q4 GEO Audit",
    "description": "Checks citation presence across key GEO keywords",
    "business_id": BUSINESS_ID,
    "business_name": "Acme GEO Corp",
    "questions": [
        {"id": "q1", "question": "Are you cited when people ask about AI tools?"},
        {"id": "q2", "question": "Does your product appear for enterprise GEO searches?"},
    ],
    "created_at": "2026-03-17T12:01:00Z",
}

MOCK_TEMPLATE_UPDATED = {
    "id": TEMPLATE_ID,
    "name": "Q4 GEO Audit Revised",
    "description": "Updated scope for Q4",
    "business_id": BUSINESS_ID,
    "business_name": "Acme GEO Corp",
    "questions": [
        {"id": "q1", "question": "Are we cited for AI safety research?"},
        {"id": "q2", "question": "Do enterprise buyers find us via AI assistants?"},
        {"id": "q3", "question": "Are we mentioned in responsible AI discussions?"},
    ],
    "created_at": "2026-03-17T12:01:00Z",
    "updated_at": "2026-03-17T14:00:00Z",
}

MOCK_AUDIT_STARTED = {
    "job_id": AUDIT_JOB_ID,
    "status": "pending",
    "named_audit_id": TEMPLATE_ID,
    "business_id": BUSINESS_ID,
    "created_at": "2026-03-17T12:02:00Z",
}

MOCK_AUDIT_STATUS_COMPLETED = {
    "job_id": AUDIT_JOB_ID,
    "status": "completed",
    "progress": 1.0,
    "message": "All questions processed",
}

MOCK_AUDIT_RESULT = {
    "job_id": AUDIT_JOB_ID,
    "status": "completed",
    "business_id": BUSINESS_ID,
    "questions": [
        {
            "question": "Are you cited when people ask about AI tools?",
            "cited": True,
            "citation_count": 3,
            "providers": ["openai", "perplexity"],
        },
        {
            "question": "Does your product appear for enterprise GEO searches?",
            "cited": False,
            "citation_count": 0,
            "providers": [],
        },
    ],
    "overall_citation_rate": 0.5,
}

MOCK_CRAWL_STARTED = {
    "message": "Crawl job enqueued",
    "business_id": BUSINESS_ID,
    "job_id": CRAWL_JOB_ID,
    "status": "crawling",
}

MOCK_HEALTH_SCORES = {
    "business_id": BUSINESS_ID,
    "scores": {
        "citation_score": 72,
        "visibility_score": 58,
        "trust_score": 65,
        "content_freshness": 80,
    },
}

MOCK_RECOMMEND_STARTED = {
    "job_id": RECOMMEND_JOB_ID,
    "status": "pending",
    "audit_job_id": AUDIT_JOB_ID,
    "created_at": "2026-03-17T12:05:00Z",
}

MOCK_RECOMMEND_STATUS_COMPLETED = {
    "job_id": RECOMMEND_JOB_ID,
    "status": "completed",
    "progress": 1.0,
    "message": "Recommendations generated",
}

MOCK_RECOMMEND_RESULT = {
    "job_id": RECOMMEND_JOB_ID,
    "status": "completed",
    # question_insights use question_id + question_text (real API field names)
    "question_insights": [
        {
            "question_id": QI_SOURCE_ID,
            "question_text": "Are you cited when asked about AI tools?",
            "risk_level": "high",
            "coverage_score": 0.33,
        },
    ],
    # head_to_head_comparisons use competitor_domain as the source_id (real API field names)
    "head_to_head_comparisons": [
        {
            "competitor_domain": HTH_COMPETITOR_DOMAIN,
            "competitor_url": f"https://{HTH_COMPETITOR_DOMAIN}",
            "business_domain": "acme.example.com",
            "overall_winner": "competitor",
        },
    ],
    # strengthening_tips use category as source_id, title as description (real API field names)
    "strengthening_tips": [
        {
            "category": "llms_txt",
            "title": "Add FAQ schema markup to homepage",
            "priority": "high",
        },
    ],
    "priority_actions": [],
}

MOCK_SOLUTION_STARTED = {
    "job_id": SOLUTION_JOB_ID,
    "status": "pending",
    "recommendation_job_id": RECOMMEND_JOB_ID,
    "source_type": "question_insight",
    "source_id": QI_SOURCE_ID,
    "created_at": "2026-03-17T12:10:00Z",
}

# Reusable list of templates (for list endpoint)
MOCK_TEMPLATE_LIST = [MOCK_TEMPLATE]

# Reusable list of audits (for history endpoint)
MOCK_AUDIT_LIST = [{"job_id": AUDIT_JOB_ID, "business_name": "Acme GEO Corp", "status": "completed", "created_at": "2026-03-17T12:02:00Z"}]

# Reusable list of recommendations (for history endpoint)
MOCK_RECOMMEND_LIST = [{"job_id": RECOMMEND_JOB_ID, "status": "completed", "created_at": "2026-03-17T12:05:00Z"}]

# Reusable list of solutions (for history endpoint)
MOCK_SOLUTION_LIST = [{"job_id": SOLUTION_JOB_ID, "status": "completed", "created_at": "2026-03-17T12:10:00Z"}]


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def cli_app():
    return app


def _setup_logged_in(tmp_path, monkeypatch) -> None:
    """
    Isolate config to a temp dir and pre-seed a dev auth token.
    This simulates a user who has already logged in and completed onboarding.
    """
    config_dir = tmp_path / ".cited"
    config_file = config_dir / "config.toml"
    creds_file  = config_dir / "credentials.json"

    monkeypatch.setattr("cited_cli.config.constants.CONFIG_DIR",      config_dir)
    monkeypatch.setattr("cited_cli.config.constants.CONFIG_FILE",     config_file)
    monkeypatch.setattr("cited_cli.config.constants.CREDENTIALS_FILE", creds_file)
    monkeypatch.setattr("cited_cli.auth.store.CONFIG_DIR",             config_dir)
    monkeypatch.setattr("cited_cli.auth.store.CREDENTIALS_FILE",       creds_file)
    # Disable keyring so credentials go to the plain JSON file
    monkeypatch.setattr("cited_cli.auth.store.TokenStore._has_keyring", lambda self: False)

    config_dir.mkdir(parents=True, exist_ok=True)
    # Pre-seed a dev token — user is already logged in
    creds_file.write_text(json.dumps({"dev": "test-jwt-dev-token"}))


def _mock_watch_job_completed(job_id: str):
    """Return a monkeypatch target that resolves watch_job instantly as completed."""
    def _instant_complete(client, status_path, console, poll_interval=2.0):
        return {"status": "completed", "job_id": job_id, "progress": 1.0}
    return _instant_complete


def _invoke(runner, cli_app, args: list[str]) -> Any:
    """Run a CLI command and assert it succeeded, returning the parsed JSON."""
    result = runner.invoke(cli_app, args)
    assert result.exit_code == 0, (
        f"Command failed: cited {' '.join(args)}\n"
        f"Output: {result.output}"
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Business Creation
# ─────────────────────────────────────────────────────────────────────────────

@respx.mock
def test_business_create_returns_id(runner, cli_app, tmp_path, monkeypatch):
    """business create outputs JSON with an 'id' field in --json mode."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/businesses").mock(
        return_value=httpx.Response(201, json=MOCK_BUSINESS)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "business", "create",
        "--name", "Acme GEO Corp",
        "--website", "https://acme.example.com",
        "--description", "Acme makes AI-powered tools for enterprise teams with great GEO presence.",
        "--industry", "SaaS",
    ])

    data = json.loads(result.output)
    assert data["id"] == BUSINESS_ID
    assert data["name"] == "Acme GEO Corp"
    assert data["website"] == "https://acme.example.com"


@respx.mock
def test_business_create_human_output(runner, cli_app, tmp_path, monkeypatch):
    """business create renders a key-value panel in human mode."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/businesses").mock(
        return_value=httpx.Response(201, json=MOCK_BUSINESS)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "business", "create",
        "--name", "Acme GEO Corp",
        "--website", "https://acme.example.com",
        "--description", "Acme makes AI-powered tools for enterprise teams with great GEO presence.",
    ])

    assert "Acme GEO Corp" in result.output
    assert "acme.example.com" in result.output


@respx.mock
def test_business_create_api_error(runner, cli_app, tmp_path, monkeypatch):
    """business create exits non-zero when the API returns 422."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/businesses").mock(
        return_value=httpx.Response(422, json={"detail": "website is not a valid URL"})
    )

    result = runner.invoke(cli_app, [
        "--env", "dev", "business", "create",
        "--name", "Bad Business",
        "--website", "not-a-url",
        "--description", "This should fail because the website is invalid per the backend.",
    ])

    assert result.exit_code != 0


def test_business_create_requires_auth(runner, cli_app, tmp_path, monkeypatch):
    """business create exits with auth error when no token is present."""
    _setup_logged_in(tmp_path, monkeypatch)
    # Override creds file with an empty object (no dev token)
    creds_file = tmp_path / ".cited" / "credentials.json"
    creds_file.write_text(json.dumps({}))

    result = runner.invoke(cli_app, [
        "--env", "dev", "business", "create",
        "--name", "X",
        "--website", "https://x.com",
        "--description", "A valid description that is long enough for the check.",
    ])

    assert result.exit_code != 0
    assert "Not logged in" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Audit Template CRUD
# ─────────────────────────────────────────────────────────────────────────────

@respx.mock
def test_template_create_returns_id(runner, cli_app, tmp_path, monkeypatch):
    """audit template create returns JSON with an 'id' field usable as next step input."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/named-audits").mock(
        return_value=httpx.Response(201, json=MOCK_TEMPLATE)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "audit", "template", "create",
        "--name", "Q4 GEO Audit",
        "--business", BUSINESS_ID,
        "--description", "Checks citation presence across key GEO keywords",
        "--question", "Are you cited when people ask about AI tools?",
        "--question", "Does your product appear for enterprise GEO searches?",
    ])

    data = json.loads(result.output)
    assert data["id"] == TEMPLATE_ID
    assert data["name"] == "Q4 GEO Audit"
    assert len(data["questions"]) == 2


@respx.mock
def test_template_create_human_output_shows_run_hint(runner, cli_app, tmp_path, monkeypatch):
    """audit template create (human mode) prints a hint for the next command."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/named-audits").mock(
        return_value=httpx.Response(201, json=MOCK_TEMPLATE)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "audit", "template", "create",
        "--name", "Q4 GEO Audit",
        "--business", BUSINESS_ID,
        "--question", "Are you cited when people ask about AI tools?",
    ])

    assert "cited audit start" in result.output
    assert TEMPLATE_ID in result.output


@respx.mock
def test_template_list_renders_table(runner, cli_app, tmp_path, monkeypatch):
    """audit template list renders a table with ID, Name, Business, Questions, Created."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/named-audits").mock(
        return_value=httpx.Response(200, json=MOCK_TEMPLATE_LIST)
    )

    result = _invoke(runner, cli_app, ["--env", "dev", "audit", "template", "list"])

    assert "Q4 GEO Audit" in result.output
    assert "Audit Templates" in result.output


@respx.mock
def test_template_list_filtered_by_business(runner, cli_app, tmp_path, monkeypatch):
    """audit template list --business sends business_id as query param."""
    _setup_logged_in(tmp_path, monkeypatch)

    captured_params: dict = {}

    def _capture(request):
        captured_params.update(dict(request.url.params))
        return httpx.Response(200, json=MOCK_TEMPLATE_LIST)

    respx.get(f"{DEV_API}/named-audits").mock(side_effect=_capture)

    _invoke(runner, cli_app, [
        "--env", "dev", "audit", "template", "list",
        "--business", BUSINESS_ID,
    ])

    assert captured_params.get("business_id") == BUSINESS_ID


@respx.mock
def test_template_get_shows_questions(runner, cli_app, tmp_path, monkeypatch):
    """audit template get renders template fields and a numbered question list."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/named-audits/{TEMPLATE_ID}").mock(
        return_value=httpx.Response(200, json=MOCK_TEMPLATE)
    )

    result = _invoke(runner, cli_app, ["--env", "dev", "audit", "template", "get", TEMPLATE_ID])

    assert "Q4 GEO Audit" in result.output
    assert "Are you cited when people ask about AI tools?" in result.output
    # Questions are numbered
    assert "1." in result.output
    assert "2." in result.output


@respx.mock
def test_template_update_replaces_questions(runner, cli_app, tmp_path, monkeypatch):
    """audit template update --question replaces all questions via PUT."""
    _setup_logged_in(tmp_path, monkeypatch)
    captured_body: dict = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        return httpx.Response(200, json=MOCK_TEMPLATE_UPDATED)

    respx.put(f"{DEV_API}/named-audits/{TEMPLATE_ID}").mock(side_effect=_capture)

    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "audit", "template", "update", TEMPLATE_ID,
        "--question", "Are we cited for AI safety research?",
        "--question", "Do enterprise buyers find us via AI assistants?",
        "--question", "Are we mentioned in responsible AI discussions?",
    ])

    data = json.loads(result.output)
    assert data["id"] == TEMPLATE_ID
    assert len(data["questions"]) == 3
    # Verify the PUT payload contained all three questions
    assert len(captured_body["questions"]) == 3
    assert captured_body["questions"][0]["question"] == "Are we cited for AI safety research?"


@respx.mock
def test_template_update_name_only(runner, cli_app, tmp_path, monkeypatch):
    """audit template update --name updates only the name, no questions in payload."""
    _setup_logged_in(tmp_path, monkeypatch)
    captured_body: dict = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        return httpx.Response(200, json=MOCK_TEMPLATE_UPDATED)

    respx.put(f"{DEV_API}/named-audits/{TEMPLATE_ID}").mock(side_effect=_capture)

    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "audit", "template", "update", TEMPLATE_ID,
        "--name", "Q4 GEO Audit Revised",
    ])

    data = json.loads(result.output)
    assert data["name"] == "Q4 GEO Audit Revised"
    assert captured_body["name"] == "Q4 GEO Audit Revised"
    assert "questions" not in captured_body


@respx.mock
def test_template_update_human_shows_questions(runner, cli_app, tmp_path, monkeypatch):
    """audit template update human output shows updated questions."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.put(f"{DEV_API}/named-audits/{TEMPLATE_ID}").mock(
        return_value=httpx.Response(200, json=MOCK_TEMPLATE_UPDATED)
    )

    result = runner.invoke(cli_app, [
        "--env", "dev", "audit", "template", "update", TEMPLATE_ID,
        "--question", "Are we cited for AI safety research?",
    ])

    assert result.exit_code == 0
    assert "Template Updated" in result.output
    assert "Are we cited for AI safety research?" in result.output


@respx.mock
def test_template_update_no_args_exits_with_error(runner, cli_app, tmp_path, monkeypatch):
    """audit template update with no flags exits with validation error."""
    _setup_logged_in(tmp_path, monkeypatch)

    result = runner.invoke(cli_app, [
        "--env", "dev", "audit", "template", "update", TEMPLATE_ID,
    ])

    assert result.exit_code == 4  # VALIDATION_ERROR


@respx.mock
def test_template_delete_with_flag_skips_prompt(runner, cli_app, tmp_path, monkeypatch):
    """audit template delete --yes deletes without confirmation prompt."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.delete(f"{DEV_API}/named-audits/{TEMPLATE_ID}").mock(
        return_value=httpx.Response(204)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "audit", "template", "delete", TEMPLATE_ID, "--yes",
    ])

    assert result.exit_code == 0


@respx.mock
def test_template_delete_prompts_without_flag(runner, cli_app, tmp_path, monkeypatch):
    """audit template delete without --yes prompts for confirmation."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.delete(f"{DEV_API}/named-audits/{TEMPLATE_ID}").mock(
        return_value=httpx.Response(204)
    )

    # Answer "n" → Abort
    result = runner.invoke(
        cli_app,
        ["--env", "dev", "audit", "template", "delete", TEMPLATE_ID],
        input="n\n",
    )
    assert result.exit_code != 0


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Audit Start
# ─────────────────────────────────────────────────────────────────────────────

@respx.mock
def test_audit_start_returns_job_id(runner, cli_app, tmp_path, monkeypatch):
    """audit start returns JSON with a job_id field."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/audit/start").mock(
        return_value=httpx.Response(202, json=MOCK_AUDIT_STARTED)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "audit", "start", TEMPLATE_ID,
    ])

    data = json.loads(result.output)
    assert data["job_id"] == AUDIT_JOB_ID
    assert data["status"] == "pending"


@respx.mock
def test_audit_start_sends_named_audit_id(runner, cli_app, tmp_path, monkeypatch):
    """audit start sends named_audit_id (not business_id) in the request body."""
    _setup_logged_in(tmp_path, monkeypatch)

    captured_body: dict = {}

    def _capture(request):
        captured_body.update(json.loads(request.content))
        return httpx.Response(202, json=MOCK_AUDIT_STARTED)

    respx.post(f"{DEV_API}/audit/start").mock(side_effect=_capture)

    _invoke(runner, cli_app, [
        "--env", "dev", "audit", "start", TEMPLATE_ID,
        "--business", BUSINESS_ID,
    ])

    assert captured_body.get("named_audit_id") == TEMPLATE_ID
    assert captured_body.get("business_id") == BUSINESS_ID
    # Must NOT send old-style business_id-only payload
    assert "recommendation_id" not in captured_body


@respx.mock
def test_audit_start_with_providers(runner, cli_app, tmp_path, monkeypatch):
    """audit start --provider flags are collected into a list in the payload."""
    _setup_logged_in(tmp_path, monkeypatch)

    captured_body: dict = {}

    def _capture(request):
        captured_body.update(json.loads(request.content))
        return httpx.Response(202, json=MOCK_AUDIT_STARTED)

    respx.post(f"{DEV_API}/audit/start").mock(side_effect=_capture)

    _invoke(runner, cli_app, [
        "--env", "dev", "audit", "start", TEMPLATE_ID,
        "--provider", "openai",
        "--provider", "perplexity",
    ])

    assert set(captured_body.get("providers", [])) == {"openai", "perplexity"}


@respx.mock
def test_audit_start_human_output_shows_watch_hint(runner, cli_app, tmp_path, monkeypatch):
    """audit start (human mode) prints a 'cited job watch' hint."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/audit/start").mock(
        return_value=httpx.Response(202, json=MOCK_AUDIT_STARTED)
    )

    result = _invoke(runner, cli_app, ["--env", "dev", "audit", "start", TEMPLATE_ID])

    assert "cited job watch" in result.output
    assert AUDIT_JOB_ID in result.output


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Job Watch (Audit)
# ─────────────────────────────────────────────────────────────────────────────

@respx.mock
def test_job_watch_audit_completes(runner, cli_app, tmp_path, monkeypatch):
    """job watch polls the audit status endpoint and prints 'completed' on success."""
    _setup_logged_in(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "cited_cli.commands.job.watch_job",
        _mock_watch_job_completed(AUDIT_JOB_ID),
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "job", "watch", AUDIT_JOB_ID, "--type", "audit",
    ])

    assert "completed" in result.output.lower()


@respx.mock
def test_job_watch_auto_detects_audit_type(runner, cli_app, tmp_path, monkeypatch):
    """job watch without --type probes status endpoints to identify the job type."""
    _setup_logged_in(tmp_path, monkeypatch)

    # _guess_job_type probes /audit/{id}/status first — return a 200
    respx.get(f"{DEV_API}/audit/{AUDIT_JOB_ID}/status").mock(
        return_value=httpx.Response(200, json=MOCK_AUDIT_STATUS_COMPLETED)
    )

    monkeypatch.setattr(
        "cited_cli.commands.job.watch_job",
        _mock_watch_job_completed(AUDIT_JOB_ID),
    )

    result = _invoke(runner, cli_app, ["--env", "dev", "job", "watch", AUDIT_JOB_ID])

    assert result.exit_code == 0


@respx.mock
def test_job_watch_failed_job_exits_nonzero(runner, cli_app, tmp_path, monkeypatch):
    """job watch returns a non-zero exit code when the job status is 'failed'."""
    _setup_logged_in(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "cited_cli.commands.job.watch_job",
        lambda client, path, console, poll_interval=2.0: {
            "status": "failed",
            "job_id": AUDIT_JOB_ID,
            "error": "Provider timeout",
        },
    )

    result = runner.invoke(cli_app, [
        "--env", "dev", "job", "watch", AUDIT_JOB_ID, "--type", "audit",
    ])

    assert result.exit_code != 0
    assert "failed" in result.output.lower() or "Provider timeout" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — Audit Result
# ─────────────────────────────────────────────────────────────────────────────

@respx.mock
def test_audit_result_json_output(runner, cli_app, tmp_path, monkeypatch):
    """audit result returns JSON with question-level citation data."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/audit/{AUDIT_JOB_ID}/result").mock(
        return_value=httpx.Response(200, json=MOCK_AUDIT_RESULT)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "audit", "result", AUDIT_JOB_ID,
    ])

    data = json.loads(result.output)
    assert data["job_id"] == AUDIT_JOB_ID
    assert len(data["questions"]) == 2
    assert data["questions"][0]["cited"] is True
    assert data["questions"][1]["cited"] is False
    assert data["overall_citation_rate"] == 0.5


@respx.mock
def test_audit_list_renders_table(runner, cli_app, tmp_path, monkeypatch):
    """audit list renders a table with job ID, business, status, and created columns."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/audit/history").mock(
        return_value=httpx.Response(200, json=MOCK_AUDIT_LIST)
    )

    result = _invoke(runner, cli_app, ["--env", "dev", "audit", "list"])

    assert "Audit History" in result.output
    assert "Acme GEO Corp" in result.output
    assert "completed" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# Step 6 — Business Crawl
# ─────────────────────────────────────────────────────────────────────────────

@respx.mock
def test_business_crawl_starts_successfully(runner, cli_app, tmp_path, monkeypatch):
    """business crawl posts to the crawl endpoint and shows 'Crawl Started'."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/businesses/{BUSINESS_ID}/crawl").mock(
        return_value=httpx.Response(202, json=MOCK_CRAWL_STARTED)
    )

    result = _invoke(runner, cli_app, ["--env", "dev", "business", "crawl", BUSINESS_ID])

    assert "Crawl" in result.output
    assert CRAWL_JOB_ID in result.output


@respx.mock
def test_business_crawl_json_output(runner, cli_app, tmp_path, monkeypatch):
    """business crawl with --json returns the raw crawl response."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/businesses/{BUSINESS_ID}/crawl").mock(
        return_value=httpx.Response(202, json=MOCK_CRAWL_STARTED)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "business", "crawl", BUSINESS_ID,
    ])

    data = json.loads(result.output)
    assert data["business_id"] == BUSINESS_ID
    assert data["job_id"] == CRAWL_JOB_ID
    assert data["status"] == "crawling"


# ─────────────────────────────────────────────────────────────────────────────
# Step 7 — Business Health (view crawl results)
# ─────────────────────────────────────────────────────────────────────────────

@respx.mock
def test_business_health_renders_score_bars(runner, cli_app, tmp_path, monkeypatch):
    """business health displays score bars after a crawl has completed."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/businesses/{BUSINESS_ID}/health-scores").mock(
        return_value=httpx.Response(200, json=MOCK_HEALTH_SCORES)
    )

    result = _invoke(runner, cli_app, ["--env", "dev", "business", "health", BUSINESS_ID])

    assert "Health Scores" in result.output
    # Score labels are displayed (snake_case -> Title Case)
    assert "72" in result.output
    assert "58" in result.output


@respx.mock
def test_business_health_json_output(runner, cli_app, tmp_path, monkeypatch):
    """business health --json returns structured score data."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/businesses/{BUSINESS_ID}/health-scores").mock(
        return_value=httpx.Response(200, json=MOCK_HEALTH_SCORES)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "business", "health", BUSINESS_ID,
    ])

    data = json.loads(result.output)
    scores = data.get("scores", {})
    assert scores["citation_score"] == 72
    assert scores["visibility_score"] == 58


# ─────────────────────────────────────────────────────────────────────────────
# Step 8 — Recommend Start
# ─────────────────────────────────────────────────────────────────────────────

@respx.mock
def test_recommend_start_returns_job_id(runner, cli_app, tmp_path, monkeypatch):
    """recommend start returns JSON with a job_id to feed into job watch."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/recommendations/start").mock(
        return_value=httpx.Response(202, json=MOCK_RECOMMEND_STARTED)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "recommend", "start", AUDIT_JOB_ID,
    ])

    data = json.loads(result.output)
    assert data["job_id"] == RECOMMEND_JOB_ID
    assert data["audit_job_id"] == AUDIT_JOB_ID


@respx.mock
def test_recommend_start_sends_audit_job_id(runner, cli_app, tmp_path, monkeypatch):
    """recommend start POSTs {audit_job_id: ...} to /recommendations/start."""
    _setup_logged_in(tmp_path, monkeypatch)

    captured_body: dict = {}

    def _capture(request):
        captured_body.update(json.loads(request.content))
        return httpx.Response(202, json=MOCK_RECOMMEND_STARTED)

    respx.post(f"{DEV_API}/recommendations/start").mock(side_effect=_capture)

    _invoke(runner, cli_app, ["--env", "dev", "recommend", "start", AUDIT_JOB_ID])

    assert captured_body.get("audit_job_id") == AUDIT_JOB_ID


@respx.mock
def test_recommend_start_human_output_shows_watch_hint(runner, cli_app, tmp_path, monkeypatch):
    """recommend start (human mode) prints a 'cited job watch' hint."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/recommendations/start").mock(
        return_value=httpx.Response(202, json=MOCK_RECOMMEND_STARTED)
    )

    result = _invoke(runner, cli_app, ["--env", "dev", "recommend", "start", AUDIT_JOB_ID])

    assert "cited job watch" in result.output
    assert RECOMMEND_JOB_ID in result.output


# ─────────────────────────────────────────────────────────────────────────────
# Step 9 — Job Watch (Recommendations)
# ─────────────────────────────────────────────────────────────────────────────

@respx.mock
def test_job_watch_recommend_completes(runner, cli_app, tmp_path, monkeypatch):
    """job watch on a recommendations job exits zero and prints completion."""
    _setup_logged_in(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "cited_cli.commands.job.watch_job",
        _mock_watch_job_completed(RECOMMEND_JOB_ID),
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "job", "watch", RECOMMEND_JOB_ID,
        "--type", "recommendations",
    ])

    assert "completed" in result.output.lower()


@respx.mock
def test_job_watch_auto_detects_recommend_type(runner, cli_app, tmp_path, monkeypatch):
    """_guess_job_type falls through /audit (404) then succeeds on /recommendations."""
    _setup_logged_in(tmp_path, monkeypatch)

    # audit probe → 404
    respx.get(f"{DEV_API}/audit/{RECOMMEND_JOB_ID}/status").mock(
        return_value=httpx.Response(404, json={"detail": "not found"})
    )
    # recommendations probe → 200
    respx.get(f"{DEV_API}/recommendations/{RECOMMEND_JOB_ID}/status").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMEND_STATUS_COMPLETED)
    )

    monkeypatch.setattr(
        "cited_cli.commands.job.watch_job",
        _mock_watch_job_completed(RECOMMEND_JOB_ID),
    )

    result = _invoke(runner, cli_app, ["--env", "dev", "job", "watch", RECOMMEND_JOB_ID])

    assert result.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────────
# Step 10 — Recommend Insights
# ─────────────────────────────────────────────────────────────────────────────

@respx.mock
def test_recommend_insights_table_contains_source_ids(runner, cli_app, tmp_path, monkeypatch):
    """recommend insights renders a table with Type, Source ID, and Description columns."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/recommendations/{RECOMMEND_JOB_ID}/result").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMEND_RESULT)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "recommend", "insights", RECOMMEND_JOB_ID,
    ])

    assert "Available Insights" in result.output
    # question_id is the source_id for question_insights
    assert QI_SOURCE_ID in result.output
    # competitor_domain is the source_id for head_to_head_comparisons
    assert HTH_COMPETITOR_DOMAIN in result.output
    # category is the source_id for strengthening_tips
    assert "llms_txt" in result.output
    # Source types appear in the Type column
    assert "question_insight" in result.output
    assert "head_to_head" in result.output
    assert "strengthening_tip" in result.output


@respx.mock
def test_recommend_insights_shows_solution_command_hint(runner, cli_app, tmp_path, monkeypatch):
    """recommend insights prints a 'cited solution start' hint with the job_id pre-filled."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/recommendations/{RECOMMEND_JOB_ID}/result").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMEND_RESULT)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "recommend", "insights", RECOMMEND_JOB_ID,
    ])

    assert "cited solution start" in result.output
    assert RECOMMEND_JOB_ID in result.output


@respx.mock
def test_recommend_insights_json_output(runner, cli_app, tmp_path, monkeypatch):
    """recommend insights --json returns the raw result (usable for scripting)."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/recommendations/{RECOMMEND_JOB_ID}/result").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMEND_RESULT)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "recommend", "insights", RECOMMEND_JOB_ID,
    ])

    data = json.loads(result.output)
    # Real API uses question_id (not id) for question_insights
    assert data["question_insights"][0]["question_id"] == QI_SOURCE_ID
    # Real API uses head_to_head_comparisons (not head_to_head) with competitor_domain as id
    assert data["head_to_head_comparisons"][0]["competitor_domain"] == HTH_COMPETITOR_DOMAIN


@respx.mock
def test_recommend_insights_field_name_regression(runner, cli_app, tmp_path, monkeypatch):
    """
    Regression: the insights command uses real API field names, not assumed ones.
    - question_insights: question_id (not id), question_text (not question)
    - head_to_head: head_to_head_comparisons key (not head_to_head), competitor_domain as source_id
    - strengthening_tips: category as source_id (no uuid id field)

    These field names were verified against the live API on 2026-03-18.
    """
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/recommendations/{RECOMMEND_JOB_ID}/result").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMEND_RESULT)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "recommend", "insights", RECOMMEND_JOB_ID,
    ])

    # question_insight row: source_id is question_id value
    assert QI_SOURCE_ID in result.output
    # head_to_head row: source_id is competitor_domain value
    assert HTH_COMPETITOR_DOMAIN in result.output
    # strengthening_tip row: source_id is category value (not a uuid)
    assert "llms_txt" in result.output
    # Descriptions come from question_text and title respectively
    # (table may wrap long text, so check a prefix that fits on one line)
    assert "Are you cited when asked about AI" in result.output
    assert "Add FAQ schema markup to homepage" in result.output


@respx.mock
def test_recommend_list_renders_table(runner, cli_app, tmp_path, monkeypatch):
    """recommend list renders a table of past recommendation jobs."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/recommendations/audit/{AUDIT_JOB_ID}/history").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMEND_LIST)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "recommend", "list", "--audit", AUDIT_JOB_ID,
    ])

    assert "Recommendations" in result.output
    assert "completed" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# Step 11 — Solution Start
# ─────────────────────────────────────────────────────────────────────────────

@respx.mock
def test_solution_start_returns_job_id(runner, cli_app, tmp_path, monkeypatch):
    """solution start returns JSON with a job_id."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/solutions/request").mock(
        return_value=httpx.Response(202, json=MOCK_SOLUTION_STARTED)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "solution", "start", RECOMMEND_JOB_ID,
        "--type", "question_insight",
        "--source", QI_SOURCE_ID,
    ])

    data = json.loads(result.output)
    assert data["job_id"] == SOLUTION_JOB_ID
    assert data["source_type"] == "question_insight"
    assert data["source_id"] == QI_SOURCE_ID


@respx.mock
def test_solution_start_uses_solution_request_endpoint(runner, cli_app, tmp_path, monkeypatch):
    """solution start POSTs to /solutions/request (NOT the deprecated /solutions/create)."""
    _setup_logged_in(tmp_path, monkeypatch)

    captured_body: dict = {}
    deprecated_called = False

    def _capture_request(request):
        captured_body.update(json.loads(request.content))
        return httpx.Response(202, json=MOCK_SOLUTION_STARTED)

    def _deprecated_called_handler(request):
        nonlocal deprecated_called
        deprecated_called = True
        return httpx.Response(410, json={"detail": "This endpoint is deprecated"})

    respx.post(f"{DEV_API}/solutions/request").mock(side_effect=_capture_request)
    respx.post(f"{DEV_API}/solutions/create").mock(side_effect=_deprecated_called_handler)

    _invoke(runner, cli_app, [
        "--env", "dev", "solution", "start", RECOMMEND_JOB_ID,
        "--type", "question_insight",
        "--source", QI_SOURCE_ID,
    ])

    # Correct endpoint was called with the right payload
    assert captured_body.get("recommendation_job_id") == RECOMMEND_JOB_ID
    assert captured_body.get("source_type") == "question_insight"
    assert captured_body.get("source_id") == QI_SOURCE_ID
    # Old payload shape must NOT be used
    assert "recommendation_id" not in captured_body
    # Deprecated endpoint must NOT have been called
    assert deprecated_called is False


@respx.mock
def test_solution_start_shows_web_nudge(runner, cli_app, tmp_path, monkeypatch):
    """solution start (human mode) prints a web URL so the user can view artifacts."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/solutions/request").mock(
        return_value=httpx.Response(202, json=MOCK_SOLUTION_STARTED)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "solution", "start", RECOMMEND_JOB_ID,
        "--type", "question_insight",
        "--source", QI_SOURCE_ID,
    ])

    # Web nudge must include the solution job ID and point to the dev web origin
    assert SOLUTION_JOB_ID in result.output
    assert f"{DEV_WEB}/solutions/{SOLUTION_JOB_ID}" in result.output


@respx.mock
def test_solution_start_shows_watch_hint(runner, cli_app, tmp_path, monkeypatch):
    """solution start (human mode) also prints a 'cited job watch' hint."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.post(f"{DEV_API}/solutions/request").mock(
        return_value=httpx.Response(202, json=MOCK_SOLUTION_STARTED)
    )

    result = _invoke(runner, cli_app, [
        "--env", "dev", "solution", "start", RECOMMEND_JOB_ID,
        "--type", "question_insight",
        "--source", QI_SOURCE_ID,
    ])

    assert "cited job watch" in result.output


@respx.mock
def test_solution_start_requires_type_and_source(runner, cli_app, tmp_path, monkeypatch):
    """solution start exits with a usage error when --type or --source is missing."""
    _setup_logged_in(tmp_path, monkeypatch)

    result = runner.invoke(cli_app, [
        "--env", "dev", "solution", "start", RECOMMEND_JOB_ID,
        # Missing --type and --source
    ])

    assert result.exit_code != 0


@respx.mock
def test_solution_list_renders_table(runner, cli_app, tmp_path, monkeypatch):
    """solution list renders a table of past solution jobs."""
    _setup_logged_in(tmp_path, monkeypatch)
    respx.get(f"{DEV_API}/solutions/history").mock(
        return_value=httpx.Response(200, json=MOCK_SOLUTION_LIST)
    )

    result = _invoke(runner, cli_app, ["--env", "dev", "solution", "list"])

    assert "Solutions" in result.output
    assert "completed" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# Full Pipeline Integration Test
#
# Chains every step together using Python variables to thread IDs between
# commands — the equivalent of bash variable capture:
#   BUSINESS_ID=$(cited --env dev --json business create ...)
# ─────────────────────────────────────────────────────────────────────────────

@respx.mock
def test_full_pipeline(runner, cli_app, tmp_path, monkeypatch):
    """
    End-to-end pipeline: business create → template create → audit start →
    job watch → audit result → business crawl → business health →
    recommend start → job watch → recommend insights → solution start.

    IDs are extracted from --json output at each step and fed into the next,
    mirroring real-world scripted usage.
    """
    _setup_logged_in(tmp_path, monkeypatch)

    # Monkeypatch watch_job to return instantly without any polling
    def _fast_watch(client, status_path, console, poll_interval=2.0):
        # Determine job type from the path to return the right job_id
        if "recommendations" in status_path:
            return {"status": "completed", "job_id": RECOMMEND_JOB_ID}
        if "solutions" in status_path:
            return {"status": "completed", "job_id": SOLUTION_JOB_ID}
        return {"status": "completed", "job_id": AUDIT_JOB_ID}

    monkeypatch.setattr("cited_cli.commands.job.watch_job", _fast_watch)

    # ── Register all API mocks ────────────────────────────────────────────────
    respx.post(f"{DEV_API}/businesses").mock(
        return_value=httpx.Response(201, json=MOCK_BUSINESS)
    )
    respx.post(f"{DEV_API}/named-audits").mock(
        return_value=httpx.Response(201, json=MOCK_TEMPLATE)
    )
    respx.put(f"{DEV_API}/named-audits/{TEMPLATE_ID}").mock(
        return_value=httpx.Response(200, json=MOCK_TEMPLATE_UPDATED)
    )
    respx.post(f"{DEV_API}/audit/start").mock(
        return_value=httpx.Response(202, json=MOCK_AUDIT_STARTED)
    )
    respx.get(f"{DEV_API}/audit/{AUDIT_JOB_ID}/status").mock(
        return_value=httpx.Response(200, json=MOCK_AUDIT_STATUS_COMPLETED)
    )
    respx.get(f"{DEV_API}/audit/{AUDIT_JOB_ID}/result").mock(
        return_value=httpx.Response(200, json=MOCK_AUDIT_RESULT)
    )
    respx.post(f"{DEV_API}/businesses/{BUSINESS_ID}/crawl").mock(
        return_value=httpx.Response(202, json=MOCK_CRAWL_STARTED)
    )
    respx.get(f"{DEV_API}/businesses/{BUSINESS_ID}/health-scores").mock(
        return_value=httpx.Response(200, json=MOCK_HEALTH_SCORES)
    )
    respx.post(f"{DEV_API}/recommendations/start").mock(
        return_value=httpx.Response(202, json=MOCK_RECOMMEND_STARTED)
    )
    respx.get(f"{DEV_API}/recommendations/{RECOMMEND_JOB_ID}/status").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMEND_STATUS_COMPLETED)
    )
    respx.get(f"{DEV_API}/recommendations/{RECOMMEND_JOB_ID}/result").mock(
        return_value=httpx.Response(200, json=MOCK_RECOMMEND_RESULT)
    )
    respx.post(f"{DEV_API}/solutions/request").mock(
        return_value=httpx.Response(202, json=MOCK_SOLUTION_STARTED)
    )

    # ── Step 1: Create a business ─────────────────────────────────────────────
    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "business", "create",
        "--name", "Acme GEO Corp",
        "--website", "https://acme.example.com",
        "--description", "Acme makes AI-powered tools for enterprise teams with great GEO presence.",
        "--industry", "SaaS",
    ])
    business = json.loads(result.output)
    business_id = business["id"]  # ← threading state into next step

    assert business_id == BUSINESS_ID

    # ── Step 2: Create an audit template ─────────────────────────────────────
    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "audit", "template", "create",
        "--name", "Q4 GEO Audit",
        "--business", business_id,  # ← uses business_id from step 1
        "--description", "Checks citation presence across key GEO keywords",
        "--question", "Are you cited when people ask about AI tools?",
        "--question", "Does your product appear for enterprise GEO searches?",
    ])
    template = json.loads(result.output)
    template_id = template["id"]  # ← threading state into next step

    assert template_id == TEMPLATE_ID
    assert template["business_id"] == business_id

    # ── Step 2b: Refine the template questions ──────────────────────────────
    # Auto-generated questions are rarely perfect — update before running audit
    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "audit", "template", "update",
        template_id,
        "--name", "Q4 GEO Audit Revised",
        "--question", "Are we cited for AI safety research?",
        "--question", "Do enterprise buyers find us via AI assistants?",
        "--question", "Are we mentioned in responsible AI discussions?",
    ])
    updated = json.loads(result.output)
    assert updated["id"] == template_id
    assert len(updated["questions"]) == 3
    assert updated["name"] == "Q4 GEO Audit Revised"

    # ── Step 3: Start the audit ───────────────────────────────────────────────
    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "audit", "start",
        template_id,  # ← uses template_id from step 2
        "--business", business_id,
    ])
    audit_started = json.loads(result.output)
    audit_job_id = audit_started["job_id"]  # ← threading state into next step

    assert audit_job_id == AUDIT_JOB_ID
    assert audit_started["status"] == "pending"

    # ── Step 4: Watch audit job until completion ──────────────────────────────
    result = _invoke(runner, cli_app, [
        "--env", "dev", "job", "watch",
        audit_job_id,  # ← uses audit_job_id from step 3
        "--type", "audit",
    ])
    assert "completed" in result.output.lower()

    # ── Step 5: View audit results in CLI ─────────────────────────────────────
    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "audit", "result",
        audit_job_id,  # ← same audit_job_id
    ])
    audit_result = json.loads(result.output)

    assert audit_result["job_id"] == audit_job_id
    assert len(audit_result["questions"]) == 2
    # One question was cited, one was not
    cited_questions    = [q for q in audit_result["questions"] if q["cited"]]
    uncited_questions  = [q for q in audit_result["questions"] if not q["cited"]]
    assert len(cited_questions) == 1
    assert len(uncited_questions) == 1

    # ── Step 6: Scan/crawl the business ──────────────────────────────────────
    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "business", "crawl",
        business_id,  # ← uses business_id from step 1
    ])
    crawl = json.loads(result.output)

    assert crawl["status"] == "crawling"
    assert crawl["business_id"] == business_id

    # Extract crawl job_id and watch it
    crawl_job_id = crawl.get("job_id", "")
    assert crawl_job_id == CRAWL_JOB_ID
    result = _invoke(runner, cli_app, [
        "--env", "dev", "job", "watch", crawl_job_id, "--type", "audit",
    ])
    assert "completed" in result.output.lower()

    # ── Step 7: View crawl results (health scores) in CLI ────────────────────
    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "business", "health",
        business_id,  # ← uses business_id from step 1
    ])
    health = json.loads(result.output)

    scores = health["scores"]
    assert scores["citation_score"] == 72
    assert scores["visibility_score"] == 58
    # All scores are non-negative integers/floats
    for score_name, value in scores.items():
        assert value >= 0, f"{score_name} should be non-negative"

    # ── Step 8: Generate recommendations ─────────────────────────────────────
    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "recommend", "start",
        audit_job_id,  # ← uses audit_job_id from step 3
    ])
    recommend_started = json.loads(result.output)
    recommend_job_id = recommend_started["job_id"]  # ← threading state into next step

    assert recommend_job_id == RECOMMEND_JOB_ID
    assert recommend_started["audit_job_id"] == audit_job_id

    # ── Step 9: Watch recommendation job until completion ────────────────────
    result = _invoke(runner, cli_app, [
        "--env", "dev", "job", "watch",
        recommend_job_id,  # ← uses recommend_job_id from step 8
        "--type", "recommendations",
    ])
    assert "completed" in result.output.lower()

    # ── Step 10: View insights — discover what to solve ──────────────────────
    result = _invoke(runner, cli_app, [
        "--env", "dev", "--json", "recommend", "insights",
        recommend_job_id,  # ← uses recommend_job_id from step 8
    ])
    insights = json.loads(result.output)

    # Extract the first question_insight source_id (what the user will pass to solution start)
    # Real API uses question_id as the source identifier, not id
    question_insights = insights["question_insights"]
    assert len(question_insights) > 0
    source_id = question_insights[0]["question_id"]  # ← threading state into next step

    assert source_id == QI_SOURCE_ID

    # ── Step 11: Start a solution for that insight ────────────────────────────
    # Run in human mode to verify the web nudge is printed
    result = _invoke(runner, cli_app, [
        "--env", "dev", "solution", "start",
        recommend_job_id,          # ← uses recommend_job_id from step 8
        "--type", "question_insight",
        "--source", source_id,     # ← uses source_id from step 10
    ])

    # Verify the job started
    assert "Solution Started" in result.output

    # Verify the web nudge is shown (rich documents → web only)
    assert SOLUTION_JOB_ID in result.output
    assert f"{DEV_WEB}/solutions/{SOLUTION_JOB_ID}" in result.output

    # Verify the watch hint is shown
    assert "cited job watch" in result.output
