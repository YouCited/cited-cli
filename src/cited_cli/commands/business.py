"""`cited business`: setup_business, get_business and get_agent_brief."""

from __future__ import annotations

from typing import Annotated, Any

import typer
from rich.console import Console

from cited_cli.output.tables import render_kv, render_table
from cited_cli.utils.tools import as_commands, clean, run

business_app = typer.Typer(help="Add and describe your business.", no_args_is_help=True)


def _people(values: list[str] | None, removals: list[str] | None) -> list[Any]:
    """``"Name: description"`` adds one; ``--remove-* ID`` removes one."""
    items: list[dict[str, Any]] = []
    for value in values or []:
        name, _, description = value.partition(":")
        item: dict[str, Any] = {"name": name.strip()}
        if description.strip():
            item["description"] = description.strip()
        items.append(item)
    items.extend({"id": i, "remove": True} for i in removals or [])
    return items


def _setup(data: dict[str, Any], console: Console) -> None:
    business = data.get("business") or {}
    verb = "Added" if data.get("created") else "Updated"
    console.print(f"{verb} {business.get('name')} ({business.get('id')})", markup=False)
    for kind in ("personas", "offerings"):
        for item in data.get(kind) or []:
            what = "removed" if item.get("removed") else "saved"
            label = item.get("name") or item.get("id")
            console.print(f"  {kind[:-1]} {what}: {label}", markup=False)
    console.print(f"→ {as_commands(str(data.get('next_step') or ''))}", markup=False)


@business_app.command("setup")
def setup(
    ctx: typer.Context,
    website: Annotated[str | None, typer.Option("--website", "-w", help="Add a business")] = None,
    business_id: Annotated[
        str | None, typer.Option("--id", help="Update this business instead")
    ] = None,
    name: Annotated[str | None, typer.Option("--name")] = None,
    industry: Annotated[str | None, typer.Option("--industry")] = None,
    description: Annotated[
        str | None, typer.Option("--description", help="What it does (10+ words)")
    ] = None,
    tagline: Annotated[
        str | None, typer.Option("--tagline", help="One-line description, max 140 characters")
    ] = None,
    customer: Annotated[str | None, typer.Option("--customer", help="Primary customer")] = None,
    problem: Annotated[str | None, typer.Option("--problem", help="Problem it solves")] = None,
    offering_type: Annotated[str | None, typer.Option("--offering-type")] = None,
    market: Annotated[str | None, typer.Option("--market", help="Primary market")] = None,
    service_areas: Annotated[str | None, typer.Option("--service-areas")] = None,
    country: Annotated[
        str | None, typer.Option("--country", help="Headquarters country (two letters)")
    ] = None,
    goal: Annotated[list[str] | None, typer.Option("--goal", help="Repeat for several")] = None,
    persona: Annotated[
        list[str] | None, typer.Option("--persona", help="Add one: 'Name: description'")
    ] = None,
    offering: Annotated[
        list[str] | None, typer.Option("--offering", help="Add one: 'Name: description'")
    ] = None,
    remove_persona: Annotated[list[str] | None, typer.Option("--remove-persona")] = None,
    remove_offering: Annotated[list[str] | None, typer.Option("--remove-offering")] = None,
) -> None:
    """Add a business from its website, or update one with --id."""
    args = clean(
        {
            "website": website,
            "business_id": business_id,
            "name": name,
            "industry": industry,
            "description": description,
            "one_line_description": tagline,
            "primary_customer": customer,
            "problem_solved": problem,
            "offering_type": offering_type,
            "primary_market": market,
            "service_areas": service_areas,
            "headquarters_country": country,
            "goals": goal,
            "personas": _people(persona, remove_persona),
            "offerings": _people(offering, remove_offering),
        }
    )
    run(ctx, "setup_business", args, _setup)


def _get(data: dict[str, Any], console: Console) -> None:
    if "businesses" in data:
        render_table(
            "Businesses",
            ["id", "name", "website", "industry"],
            [[b.get("id"), b.get("name"), b.get("website"), b.get("industry")]
             for b in data["businesses"]],
            console,
        )
        return
    business = data.get("business") or {}
    render_kv(
        business.get("name") or "Business",
        {k: business.get(k) for k in ("id", "website", "industry", "description")
         if business.get(k)},
        console,
    )
    for kind in ("personas", "offerings"):
        items = data.get(kind) or []
        if items:
            render_table(
                kind.title(),
                ["id", "name", "description"],
                [[i.get("id"), i.get("name"), i.get("description") or ""] for i in items],
                console,
            )
    question_set = data.get("question_set")
    if question_set:
        console.print("[bold]Questions[/bold]")
        for q in question_set.get("questions") or []:
            console.print(f"  • {q}", markup=False)
        schedule = question_set.get("schedule") or {}
        if schedule.get("enabled"):
            console.print(f"  Re-checked every {schedule.get('every_days')} days", markup=False)
    else:
        console.print("No questions yet: cited audit questions")
    audits = data.get("recent_audits") or []
    if audits:
        render_table(
            "Recent audits",
            ["audit_id", "status", "created_at", "avg_cited_kpi"],
            [[a.get("audit_id"), a.get("status"), a.get("created_at"), a.get("avg_cited_kpi")]
             for a in audits],
            console,
        )


@business_app.command("get")
def get(
    ctx: typer.Context,
    business_id: Annotated[
        str | None, typer.Argument(help="Omit to list your businesses")
    ] = None,
) -> None:
    """List your businesses, or show one: profile, personas, questions and audits."""
    run(ctx, "get_business", clean({"business_id": business_id}), _get)


@business_app.command("brief")
def brief(
    ctx: typer.Context,
    business_id: Annotated[str, typer.Argument(help="The business")],
) -> None:
    """What to focus on next: top recommendations, quick wins and recent movement."""
    run(ctx, "get_agent_brief", {"business_id": business_id})
