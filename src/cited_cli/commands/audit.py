"""`cited audit`: free_audit, draft_questions, quote_audit, run_audit, get_audit,
compare_audits and schedule_recheck."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

import typer
from rich.console import Console

from cited_cli.output.formatter import OutputContext, print_result
from cited_cli.output.tables import render_kv, render_table
from cited_cli.utils.interactive import can_prompt
from cited_cli.utils.tools import as_commands, call, clean, poll, render, run

audit_app = typer.Typer(help="Free and paid AI visibility audits.", no_args_is_help=True)

_RUNNING = ("pending", "processing", "queued", "running", "drafting")

BusinessOpt = Annotated[
    str | None,
    typer.Option("--business", "-b", help="Business id (optional with one business)"),
]


def _next(data: dict[str, Any], console: Console) -> None:
    for key in ("message", "next_step"):
        if isinstance(data.get(key), str):
            console.print(f"→ {as_commands(data[key])}", markup=False)


# ---------------------------------------------------------------------------
# free
# ---------------------------------------------------------------------------


def _score_text(score: Any) -> str | None:
    if not isinstance(score, dict) or score.get("score") is None:
        return None
    band = (score.get("band") or {}).get("label")
    return f"{score['score']}/100" + (f" ({band})" if band else "")


def _checked_text(data: dict[str, Any]) -> str | None:
    """"Checked Oct 27, 15:57", or a cached-result note when the audit was reused."""
    raw = data.get("completed_at")
    if not raw:
        return None
    try:
        checked = datetime.fromisoformat(str(raw)).astimezone()
    except ValueError:
        return None
    when = f"{checked:%b} {checked.day}, {checked:%H:%M}"
    if not data.get("reused"):
        return f"Checked {when}."
    hours = data.get("cache_hours") or 24
    return f"Cached result from {when}: free audits of a site are cached for {hours} hours."


def _free(data: dict[str, Any], console: Console) -> None:
    status = data.get("status")
    if status in _RUNNING:
        console.print(
            f"Free audit {status}: check again with "
            f"cited audit free --token {data.get('report_token')}",
            markup=False,
        )
        return
    if status != "completed":
        console.print(f"Free audit {status}: {data.get('error') or 'it did not finish.'}",
                      markup=False)
        return
    summary = data.get("executive_summary")
    if isinstance(summary, dict):
        if summary.get("headline"):
            console.print(summary["headline"], markup=False)
        for point in summary.get("points") or []:
            console.print(f"  • {point}", markup=False)
    checked = _checked_text(data)
    if checked:
        console.print(checked, style="dim", markup=False)
    render_kv(
        f"Free audit: {data.get('domain')}",
        {"score": _score_text(data.get("score")), **(data.get("summary") or {})},
        console,
    )
    blocked = [
        b for b in ((data.get("site_check") or {}).get("bot_access") or {}).get("bots") or []
        if b.get("status") != "pass"
    ]
    if blocked:
        render_table(
            "AI bots your site turns away",
            ["bot", "engine", "fix"],
            [[b.get("bot"), b.get("engine"), b.get("fix") or b.get("reason")] for b in blocked],
            console,
        )
    others = data.get("most_cited_other_domains") or []
    if others:
        render_table(
            "Cited instead",
            ["domain", "questions"],
            [[o.get("domain"), o.get("questions")] for o in others],
            console,
        )
    questions = data.get("questions") or []
    if questions:
        render_table(
            "Questions",
            ["question", "risk", "cited"],
            [[q.get("question"), q.get("risk_level"), "yes" if q.get("brand_cited") else "no"]
             for q in questions],
            console,
        )
    if data.get("share_url"):
        console.print(f"Report: {data['share_url']}", markup=False)
    if data.get("pdf_url"):
        console.print(f"PDF: {data['pdf_url']}", markup=False)
    console.print(
        "A paid audit adds every engine and model, recommendations and fixes: cited status",
        markup=False,
    )


@audit_app.command("free")
def free(
    ctx: typer.Context,
    url: Annotated[str | None, typer.Argument(help="Website to audit, e.g. example.com")] = None,
    token: Annotated[
        str | None, typer.Option("--token", help="Check an audit already started")
    ] = None,
    wait: Annotated[
        bool, typer.Option("--wait/--no-wait", help="Wait for the report (2-4 minutes)")
    ] = True,
) -> None:
    """Free check of how AI answers 5 buyer questions about a site. No account needed."""
    if not url and not token:
        raise typer.BadParameter("Pass a website, or --token for an audit already started")
    args = clean({"url": url, "report_token": token})
    if not wait:
        run(ctx, "free_audit", args, _free)
        return
    result, out = poll(
        ctx,
        "free_audit",
        args,
        done=lambda r: r.get("status") not in _RUNNING,
        next_args=lambda r: {"report_token": r.get("report_token")},
        # Each check waits on the server (up to 20s) while the audit runs
        interval=2.0,
    )
    print_result(result, out, human_formatter=_free)


# ---------------------------------------------------------------------------
# questions
# ---------------------------------------------------------------------------


def _questions(data: dict[str, Any], console: Console) -> None:
    if data.get("status") == "drafting":
        console.print(
            f"Drafting questions (job {data.get('job_id')}). Finish with: "
            f"cited audit questions --job {data.get('job_id')}",
            markup=False,
        )
        return
    questions = (data.get("question_set") or {}).get("questions") or []
    console.print(f"[bold]{len(questions)} questions[/bold]")
    for i, q in enumerate(questions, 1):
        console.print(f"  {i}. {q}", markup=False)
    console.print("Replace them with: cited audit questions -q '...' -q '...'")
    console.print("Then: cited audit quote, cited audit run")


@audit_app.command("questions")
def questions(
    ctx: typer.Context,
    business: BusinessOpt = None,
    question: Annotated[
        list[str] | None,
        typer.Option("--question", "-q", help="Replace the set with these (repeat)"),
    ] = None,
    regenerate: Annotated[bool, typer.Option("--regenerate", help="Draft a new set")] = False,
    add: Annotated[bool, typer.Option("--add", help="Draft more and add them")] = False,
    count: Annotated[int | None, typer.Option("--count", help="How many to draft")] = None,
    focus: Annotated[str | None, typer.Option("--focus", help="Steer the drafting")] = None,
    job: Annotated[str | None, typer.Option("--job", help="Finish a draft started earlier")] = None,
    wait: Annotated[bool, typer.Option("--wait/--no-wait", help="Wait for drafting")] = True,
) -> None:
    """Show, draft or replace the buyer questions the audit asks AI."""
    args = clean(
        {
            "business_id": business,
            "questions": question,
            "regenerate": regenerate,
            "add": add,
            "count": count,
            "focus": focus,
            "job_id": job,
        }
    )
    if not wait:
        run(ctx, "draft_questions", args, _questions)
        return
    result, out = poll(
        ctx,
        "draft_questions",
        args,
        done=lambda r: r.get("status") != "drafting",
        next_args=lambda r: clean(
            {"business_id": business or r.get("business_id"), "job_id": r.get("job_id"),
             "add": add}
        ),
        interval=10.0,
    )
    print_result(result, out, human_formatter=_questions)


# ---------------------------------------------------------------------------
# quote / run
# ---------------------------------------------------------------------------


def _quote(data: dict[str, Any], console: Console) -> None:
    render_kv(
        "Audit price",
        {k: data.get(k) for k in ("credits", "balance", "question_count", "models")
         if data.get(k) is not None},
        console,
    )
    if data.get("available_models"):
        console.print(f"Models: {', '.join(data['available_models'])}", markup=False)
    _next(data, console)


@audit_app.command("quote")
def quote(
    ctx: typer.Context,
    business: BusinessOpt = None,
    model: Annotated[list[str] | None, typer.Option("--model", "-m", help="Repeat")] = None,
) -> None:
    """What an audit of the question set costs, and the models it can use."""
    run(ctx, "quote_audit", clean({"business_id": business, "models": model}), _quote)


def _confirm_and_rerun(
    ctx: typer.Context, name: str, args: dict[str, Any], yes: bool
) -> tuple[dict[str, Any], OutputContext]:
    """Spending tools return a price first; ask, then call again with confirm."""
    if yes:
        return call(ctx, name, {**args, "confirm": True})
    result, out = call(ctx, name, args)
    if not result.get("confirmation_required"):
        return result, out
    if out.json_mode or not can_prompt(out):
        # Leave the decision to the caller: the price is the result.
        return result, out
    out.console.print(as_commands(str(result.get("message") or "")), markup=False)
    typer.confirm("Go ahead?", abort=True)
    return call(ctx, name, {**args, "confirm": True})


@audit_app.command("run")
def run_audit(
    ctx: typer.Context,
    business: BusinessOpt = None,
    model: Annotated[list[str] | None, typer.Option("--model", "-m", help="Repeat")] = None,
    engine: Annotated[
        list[str] | None, typer.Option("--engine", help="Citation engine (repeat)")
    ] = None,
    country: Annotated[str | None, typer.Option("--country")] = None,
    deep: Annotated[bool, typer.Option("--deep", help="Deeper recommendations")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Spend without asking")] = False,
) -> None:
    """Run a paid audit of the question set. Asks before spending unless --yes."""
    args = clean(
        {
            "business_id": business,
            "models": model,
            "engines": engine,
            "country": country,
            "deep_recommendations": deep,
        }
    )
    result, out = _confirm_and_rerun(ctx, "run_audit", args, yes)
    print_result(result, out, human_formatter=render)


# ---------------------------------------------------------------------------
# get / compare / schedule
# ---------------------------------------------------------------------------


def _get(data: dict[str, Any], console: Console) -> None:
    if "audits" in data:
        render_table(
            "Audits",
            ["audit_id", "business_name", "status", "created_at", "question_count"],
            [[a.get("audit_id"), a.get("business_name"), a.get("status"), a.get("created_at"),
              a.get("question_count")] for a in data["audits"]],
            console,
        )
        return
    if data.get("status") != "completed" and "summary" not in data:
        render(data, console)
        return
    if isinstance(data.get("summary"), str):
        console.print(data["summary"], markup=False)
    elif isinstance(data.get("summary"), dict):
        render_kv("Summary", data["summary"], console)
    console.print("Full report: cited --json audit get <audit_id>")
    recs = data.get("recommendations") or {}
    if recs.get("next_step"):
        console.print(f"→ {as_commands(recs['next_step'])}", markup=False)


@audit_app.command("get")
def get(
    ctx: typer.Context,
    audit_id: Annotated[str | None, typer.Argument(help="Omit to list audits")] = None,
    business: BusinessOpt = None,
    answers: Annotated[bool, typer.Option("--answers", help="Full AI answers")] = False,
    wait: Annotated[bool, typer.Option("--wait", help="Wait until it finishes")] = False,
    limit: Annotated[int | None, typer.Option("--limit")] = None,
) -> None:
    """List audits, or one audit's status and report."""
    args = clean(
        {"audit_id": audit_id, "business_id": business, "include_answers": answers,
         "limit": limit}
    )
    if wait and audit_id:
        result, out = poll(
            ctx, "get_audit", args,
            done=lambda r: r.get("status") not in _RUNNING,
            next_args=lambda r: args,
            interval=30.0,
            timeout=1800.0,
        )
        print_result(result, out, human_formatter=_get)
        return
    run(ctx, "get_audit", args, _get)


@audit_app.command("compare")
def compare(
    ctx: typer.Context,
    audit_id: Annotated[str, typer.Argument(help="The newer audit")],
    baseline: Annotated[
        str | None, typer.Option("--baseline", help="Default: the previous audit")
    ] = None,
) -> None:
    """Citations won and lost between two audits."""
    run(ctx, "compare_audits", clean({"audit_id": audit_id, "baseline_audit_id": baseline}))


@audit_app.command("schedule")
def schedule(
    ctx: typer.Context,
    business: BusinessOpt = None,
    every: Annotated[
        int | None, typer.Option("--every", help="Days between re-checks (7-90)")
    ] = None,
    off: Annotated[bool, typer.Option("--off", help="Stop re-checking")] = False,
    email: Annotated[
        bool | None, typer.Option("--email/--no-email", help="Email alerts")
    ] = None,
    webhook: Annotated[
        str | None, typer.Option("--webhook", help="Alert webhook URL ('' clears it)")
    ] = None,
) -> None:
    """Re-run the audit on a schedule (charged per run) and set alerts."""
    args = clean({"business_id": business, "every_days": every, "off": off})
    if email is not None:
        args["email_alerts"] = email
    if webhook is not None:
        args["webhook_url"] = webhook
    run(ctx, "schedule_recheck", args)
