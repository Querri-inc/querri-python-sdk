"""Skill type model for the Querri SDK."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator


class Skill(BaseModel):
    """A Querri Skill — a named bundle of instructions and an example plan
    that the planner agent can load to bias its reasoning toward a known-good
    approach.

    Skills are not executors. They inject prompt context (description,
    advanced_instructions, example_plan) into the planner when loaded.

    ``example_plan`` is typed as ``List[Dict]`` on the SDK side to avoid
    coupling the SDK to backend Pydantic types (DECISIONS.md D10). The dicts
    validate against the live ``PlanStep`` shape on the server at save time.
    """

    id: str  #: Unique skill identifier (mapped from server ``uuid``).
    created_by: str  #: UUID of the user who created this skill.
    org_shared: bool = False  #: ``True`` if every org member can view/load this skill.
    title: str  #: Display name (3–100 chars).
    description: str  #: Short "what does this skill do" line (10–500 chars).
    #: Free-form guidance injected after load (0–4000 chars).
    advanced_instructions: str = ""
    example_plan: list[dict[str, Any]] = []  #: Worked example plan steps (0–20 items).
    created_at: str | None = None  #: ISO-8601 creation timestamp.
    updated_at: str | None = None  #: ISO-8601 last-update timestamp.

    @model_validator(mode="before")
    @classmethod
    def _normalize_id(cls, data: Any) -> Any:
        """Map server ``uuid`` field to SDK ``id`` field.

        Returns a new dict rather than mutating the input so callers that
        reuse the same payload dict across multiple ``model_validate`` calls
        are not affected by accumulated side effects.
        """
        if not isinstance(data, dict):
            return data
        if "uuid" in data and "id" not in data:
            return {**data, "id": data["uuid"]}
        return data
