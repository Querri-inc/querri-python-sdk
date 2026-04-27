"""Skills resource for the Querri API.

Skills are named bundles of (a) instructions and (b) an example plan that
the planner agent can load to bias its reasoning toward a known-good approach.
They are not executors — they inject prompt context into the existing planner.
"""

from __future__ import annotations

import builtins
from typing import Any

from .._base_client import AsyncHTTPClient, SyncHTTPClient
from .._pagination import AsyncCursorPage, SyncCursorPage
from ..types.skill import Skill

# ---------------------------------------------------------------------------
# Skills (sync)
# ---------------------------------------------------------------------------


class Skills:
    """Resource for skill operations.

    Example::

        # List skills accessible to the caller
        for skill in client.skills.list():
            print(skill.title, skill.org_shared)

        # Create a skill
        skill = client.skills.create(
            title="Monthly Cohort Retention",
            description="Computes cohort retention from a sessions table.",
            advanced_instructions="Use DuckDB SQL. Output one row per cohort week.",
            example_plan=[
                {
                    "name": "Load sessions",
                    "tool": "load_source",
                    "prompt": "Load the sessions table",
                    "parent": None,
                    "columns": [],
                    "dependencies": [],
                }
            ],
        )

        # Get a specific skill
        skill = client.skills.get(skill.id)

        # Update a skill
        updated = client.skills.update(skill.id, title="Revised Title")

        # Delete a skill
        client.skills.delete(skill.id)
    """

    def __init__(self, http: SyncHTTPClient) -> None:
        self._http = http

    def list(
        self,
        *,
        q: str | None = None,
        mine: bool | None = None,
        shared: bool | None = None,
        limit: int = 25,
        after: str | None = None,
    ) -> SyncCursorPage[Skill]:
        """List skills accessible to the caller with cursor pagination.

        Args:
            q: Search query filtering by title and description.
            mine: If ``True``, return only skills created by the caller.
            shared: If ``True``, return only org-shared skills.
            limit: Maximum number of skills per page (1–200).
            after: Cursor for the next page.

        Returns:
            Auto-paginating iterator of :class:`Skill` objects.
        """
        params: dict[str, Any] = {"limit": limit}
        if after is not None:
            params["after"] = after
        if q is not None:
            params["q"] = q
        if mine is not None:
            params["mine"] = mine
        if shared is not None:
            params["shared"] = shared
        return SyncCursorPage(self._http, "/skills", Skill, params=params)

    def get(self, skill_id: str) -> Skill:
        """Get a skill by ID.

        The caller must be the creator or the skill must be org-shared.

        Args:
            skill_id: The skill UUID.

        Returns:
            :class:`Skill` object with full content.

        Raises:
            :class:`~querri.NotFoundError`: If the skill does not exist or
                the caller lacks view access.
        """
        response = self._http.get(f"/skills/{skill_id}")
        return Skill.model_validate(response.json())

    def create(
        self,
        *,
        title: str,
        description: str,
        advanced_instructions: str = "",
        example_plan: builtins.list[dict[str, Any]] | None = None,
        org_shared: bool = False,
    ) -> Skill:
        """Create a new skill.

        ``org_shared=True`` requires the caller to have admin role; non-admin
        callers will receive a ``403 admin_required`` error.

        Args:
            title: Skill display name (3–100 chars).
            description: Short description visible to the planner (10–500 chars).
            advanced_instructions: Free-form guidance injected after load
                (0–4000 chars).
            example_plan: Worked example plan as a list of ``PlanStep``-shaped
                dicts (0–20 items). Each dict must match the live ``PlanStep``
                schema on the server (fields: ``name``, ``tool``, ``prompt``,
                ``parent``, ``columns``, ``dependencies``).
            org_shared: Share with all org members (admin-only).

        Returns:
            Created :class:`Skill` object.

        Raises:
            :class:`~querri.ValidationError`: If field validation fails
                (length limits, DAG topology, unknown tool names).
            :class:`~querri.PermissionError`: If ``org_shared=True`` and the
                caller is not an admin.
        """
        body: dict[str, Any] = {
            "title": title,
            "description": description,
            "advanced_instructions": advanced_instructions,
            "example_plan": example_plan if example_plan is not None else [],
            "org_shared": org_shared,
        }
        response = self._http.post("/skills", json=body)
        return Skill.model_validate(response.json())

    def update(
        self,
        skill_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        advanced_instructions: str | None = None,
        example_plan: builtins.list[dict[str, Any]] | None = None,
        org_shared: bool | None = None,
    ) -> Skill:
        """Update a skill.

        Only the creator can update; admins can also update ``org_shared``
        skills. Flipping ``org_shared`` requires admin role.

        Args:
            skill_id: The skill UUID.
            title: New display name.
            description: New description.
            advanced_instructions: New free-form guidance.
            example_plan: Replacement example plan (full list, not a diff).
            org_shared: New sharing state (admin-only).

        Returns:
            Updated :class:`Skill` object.

        Raises:
            :class:`~querri.PermissionError`: If the caller lacks edit access or
                attempts to flip ``org_shared`` without admin role.
            :class:`~querri.ValidationError`: If field validation fails.
            :class:`~querri.NotFoundError`: If the skill does not exist.
        """
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if advanced_instructions is not None:
            body["advanced_instructions"] = advanced_instructions
        if example_plan is not None:
            body["example_plan"] = example_plan
        if org_shared is not None:
            body["org_shared"] = org_shared
        response = self._http.put(f"/skills/{skill_id}", json=body)
        return Skill.model_validate(response.json())

    def delete(self, skill_id: str) -> None:
        """Delete a skill (hard delete).

        Only the creator or an admin (for org-shared skills) can delete.

        Args:
            skill_id: The skill UUID.

        Raises:
            :class:`~querri.PermissionError`: If the caller lacks delete access.
            :class:`~querri.NotFoundError`: If the skill does not exist.
        """
        self._http.delete(f"/skills/{skill_id}")


# ---------------------------------------------------------------------------
# AsyncSkills
# ---------------------------------------------------------------------------


class AsyncSkills:
    """Async resource for skill operations.

    Example::

        async for skill in client.skills.list():
            print(skill.title, skill.org_shared)

        skill = await client.skills.create(
            title="Monthly Cohort Retention",
            description="Computes cohort retention from a sessions table.",
        )
    """

    def __init__(self, http: AsyncHTTPClient) -> None:
        self._http = http

    def list(
        self,
        *,
        q: str | None = None,
        mine: bool | None = None,
        shared: bool | None = None,
        limit: int = 25,
        after: str | None = None,
    ) -> AsyncCursorPage[Skill]:
        """List skills accessible to the caller with cursor pagination.

        Args:
            q: Search query filtering by title and description.
            mine: If ``True``, return only skills created by the caller.
            shared: If ``True``, return only org-shared skills.
            limit: Maximum number of skills per page (1–200).
            after: Cursor for the next page.

        Returns:
            Async auto-paginating iterator of :class:`Skill` objects.
        """
        params: dict[str, Any] = {"limit": limit}
        if after is not None:
            params["after"] = after
        if q is not None:
            params["q"] = q
        if mine is not None:
            params["mine"] = mine
        if shared is not None:
            params["shared"] = shared
        return AsyncCursorPage(self._http, "/skills", Skill, params=params)

    async def get(self, skill_id: str) -> Skill:
        """Get a skill by ID.

        Args:
            skill_id: The skill UUID.

        Returns:
            :class:`Skill` object with full content.

        Raises:
            :class:`~querri.NotFoundError`: If the skill does not exist or
                the caller lacks view access.
        """
        response = await self._http.get(f"/skills/{skill_id}")
        return Skill.model_validate(response.json())

    async def create(
        self,
        *,
        title: str,
        description: str,
        advanced_instructions: str = "",
        example_plan: builtins.list[dict[str, Any]] | None = None,
        org_shared: bool = False,
    ) -> Skill:
        """Create a new skill.

        ``org_shared=True`` requires admin role.

        Args:
            title: Skill display name (3–100 chars).
            description: Short description visible to the planner (10–500 chars).
            advanced_instructions: Free-form guidance injected after load
                (0–4000 chars).
            example_plan: Worked example plan as a list of ``PlanStep``-shaped
                dicts.
            org_shared: Share with all org members (admin-only).

        Returns:
            Created :class:`Skill` object.
        """
        body: dict[str, Any] = {
            "title": title,
            "description": description,
            "advanced_instructions": advanced_instructions,
            "example_plan": example_plan if example_plan is not None else [],
            "org_shared": org_shared,
        }
        response = await self._http.post("/skills", json=body)
        return Skill.model_validate(response.json())

    async def update(
        self,
        skill_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        advanced_instructions: str | None = None,
        example_plan: builtins.list[dict[str, Any]] | None = None,
        org_shared: bool | None = None,
    ) -> Skill:
        """Update a skill.

        Args:
            skill_id: The skill UUID.
            title: New display name.
            description: New description.
            advanced_instructions: New free-form guidance.
            example_plan: Replacement example plan (full list, not a diff).
            org_shared: New sharing state (admin-only).

        Returns:
            Updated :class:`Skill` object.
        """
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if advanced_instructions is not None:
            body["advanced_instructions"] = advanced_instructions
        if example_plan is not None:
            body["example_plan"] = example_plan
        if org_shared is not None:
            body["org_shared"] = org_shared
        response = await self._http.put(f"/skills/{skill_id}", json=body)
        return Skill.model_validate(response.json())

    async def delete(self, skill_id: str) -> None:
        """Delete a skill (hard delete).

        Args:
            skill_id: The skill UUID.
        """
        await self._http.delete(f"/skills/{skill_id}")
