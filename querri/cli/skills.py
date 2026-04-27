"""querri skill — create, browse, and manage Skills."""

from __future__ import annotations

import json
import sys
from typing import Any

import typer

from querri.cli._context import get_client
from querri.cli._output import (
    handle_api_error,
    print_detail,
    print_error,
    print_id,
    print_json,
    print_success,
    print_table,
)

skills_app = typer.Typer(
    name="skill",
    help=(
        "Manage Skills — reusable instruction + example-plan bundles that "
        "bias the planner toward known-good approaches."
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
)


# ---------------------------------------------------------------------------
# querri skill list
# ---------------------------------------------------------------------------


@skills_app.command("list")
def list_skills(
    ctx: typer.Context,
    q: str | None = typer.Option(
        None, "--query", "-q", help="Search by title/description."
    ),
    mine: bool = typer.Option(False, "--mine", help="Show only my skills."),
    shared: bool = typer.Option(False, "--shared", help="Show only org-shared skills."),
    limit: int = typer.Option(25, "--limit", "-l", help="Max results to return."),
    after: str | None = typer.Option(None, "--after", help="Cursor for pagination."),
) -> None:
    """List skills accessible to the caller."""
    obj = ctx.ensure_object(dict)
    client = get_client(ctx)

    kwargs: dict[str, Any] = {"limit": limit}
    if q:
        kwargs["q"] = q
    if mine:
        kwargs["mine"] = True
    if shared:
        kwargs["shared"] = True
    if after:
        kwargs["after"] = after

    try:
        page = client.skills.list(**kwargs)
        items = list(page)
    except Exception as exc:
        raise typer.Exit(code=handle_api_error(exc, is_json=obj.get("json"))) from None

    if obj.get("json"):
        print_json([s.model_dump(mode="json") for s in items])
    elif obj.get("quiet"):
        for s in items:
            print_id(s.id)
    else:
        rows = [
            {
                "id": s.id,
                "title": s.title,
                "shared": "org" if s.org_shared else "mine",
                "updated_at": s.updated_at or "",
            }
            for s in items
        ]
        print_table(
            rows,
            [
                ("id", "ID"),
                ("title", "Title"),
                ("shared", "Visibility"),
                ("updated_at", "Updated"),
            ],
            ctx=ctx,
        )


# ---------------------------------------------------------------------------
# querri skill get
# ---------------------------------------------------------------------------


@skills_app.command("get")
def get_skill(
    ctx: typer.Context,
    skill_id: str = typer.Argument(help="Skill UUID."),
) -> None:
    """Get full details of a skill."""
    obj = ctx.ensure_object(dict)
    client = get_client(ctx)

    try:
        skill = client.skills.get(skill_id)
    except Exception as exc:
        raise typer.Exit(code=handle_api_error(exc, is_json=obj.get("json"))) from None

    if obj.get("json"):
        print_json(skill)
    elif obj.get("quiet"):
        print_id(skill.id)
    else:
        print_detail(
            skill,
            [
                ("id", "ID"),
                ("title", "Title"),
                ("description", "Description"),
                ("advanced_instructions", "Instructions"),
                ("org_shared", "Org Shared"),
                ("created_by", "Created By"),
                ("created_at", "Created"),
                ("updated_at", "Updated"),
            ],
        )
        if skill.example_plan:
            print(
                f"\nExample Plan ({len(skill.example_plan)} step(s)):",
                file=sys.stderr,
            )
            print(
                json.dumps(skill.example_plan, indent=2),
                file=sys.stderr,
            )


# ---------------------------------------------------------------------------
# querri skill create
# ---------------------------------------------------------------------------


@skills_app.command("create")
def create_skill(
    ctx: typer.Context,
    title: str = typer.Argument(help="Skill title (3–100 chars)."),
    description: str = typer.Option(
        ..., "--description", "-d", help="Short description (10–500 chars)."
    ),
    instructions: str = typer.Option(
        "", "--instructions", "-i", help="Advanced instructions (0–4000 chars)."
    ),
    example_plan: str | None = typer.Option(
        None,
        "--example-plan",
        help="JSON string or @file.json with a list of PlanStep dicts.",
    ),
    org_shared: bool = typer.Option(
        False, "--org-shared", help="Share with all org members (admin only)."
    ),
) -> None:
    """Create a new skill.

    Pass --example-plan as a JSON string or prefix a file path with @:

    \\b
      querri skill create "Cohort Retention" \\
        --description "Computes monthly cohort retention." \\
        --example-plan '[{"name":"Load data","tool":"load_source",
        "prompt":"Load sessions","parent":null,"columns":[],
        "dependencies":[]}]'
    """
    obj = ctx.ensure_object(dict)
    client = get_client(ctx)

    plan: list[dict[str, Any]] = []
    if example_plan:
        raw = example_plan
        if raw.startswith("@"):
            try:
                with open(raw[1:]) as fh:
                    raw = fh.read()
            except OSError as e:
                print_error(f"Could not read example plan file: {e}")
                raise typer.Exit(code=1) from None
        try:
            plan = json.loads(raw)
            if not isinstance(plan, list):
                raise ValueError("example_plan must be a JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            print_error(f"Invalid example plan JSON: {e}")
            raise typer.Exit(code=1) from None

    try:
        skill = client.skills.create(
            title=title,
            description=description,
            advanced_instructions=instructions,
            example_plan=plan,
            org_shared=org_shared,
        )
    except Exception as exc:
        raise typer.Exit(code=handle_api_error(exc, is_json=obj.get("json"))) from None

    if obj.get("json"):
        print_json(skill)
    elif obj.get("quiet"):
        print_id(skill.id)
    else:
        print_success(f"Created skill: {skill.title} ({skill.id})")


# ---------------------------------------------------------------------------
# querri skill update
# ---------------------------------------------------------------------------


@skills_app.command("update")
def update_skill(
    ctx: typer.Context,
    skill_id: str = typer.Argument(help="Skill UUID."),
    title: str | None = typer.Option(None, "--title", "-t", help="New title."),
    description: str | None = typer.Option(
        None, "--description", "-d", help="New description."
    ),
    instructions: str | None = typer.Option(
        None, "--instructions", "-i", help="New advanced instructions."
    ),
    example_plan: str | None = typer.Option(
        None,
        "--example-plan",
        help="Replacement example plan as JSON string or @file.json.",
    ),
    org_shared: bool | None = typer.Option(
        None, "--org-shared/--no-org-shared", help="Toggle org sharing (admin only)."
    ),
) -> None:
    """Update a skill."""
    obj = ctx.ensure_object(dict)
    client = get_client(ctx)

    plan: list[dict[str, Any]] | None = None
    if example_plan is not None:
        raw = example_plan
        if raw.startswith("@"):
            try:
                with open(raw[1:]) as fh:
                    raw = fh.read()
            except OSError as e:
                print_error(f"Could not read example plan file: {e}")
                raise typer.Exit(code=1) from None
        try:
            plan = json.loads(raw)
            if not isinstance(plan, list):
                raise ValueError("example_plan must be a JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            print_error(f"Invalid example plan JSON: {e}")
            raise typer.Exit(code=1) from None

    try:
        skill = client.skills.update(
            skill_id,
            title=title,
            description=description,
            advanced_instructions=instructions,
            example_plan=plan,
            org_shared=org_shared,
        )
    except Exception as exc:
        raise typer.Exit(code=handle_api_error(exc, is_json=obj.get("json"))) from None

    if obj.get("json"):
        print_json(skill)
    elif obj.get("quiet"):
        print_id(skill.id)
    else:
        print_success(f"Updated skill {skill_id}")


# ---------------------------------------------------------------------------
# querri skill delete
# ---------------------------------------------------------------------------


@skills_app.command("delete")
def delete_skill(
    ctx: typer.Context,
    skill_id: str = typer.Argument(help="Skill UUID."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt."
    ),
) -> None:
    """Delete a skill (hard delete)."""
    obj = ctx.ensure_object(dict)
    is_interactive = obj.get("interactive", sys.stdin.isatty())

    if not yes and is_interactive:
        confirm = input(f"Delete skill {skill_id}? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted.", file=sys.stderr)
            raise typer.Exit(code=0)

    client = get_client(ctx)
    try:
        client.skills.delete(skill_id)
    except Exception as exc:
        raise typer.Exit(code=handle_api_error(exc, is_json=obj.get("json"))) from None

    if obj.get("json"):
        print_json({"id": skill_id, "deleted": True})
    else:
        print_success(f"Deleted skill {skill_id}")

