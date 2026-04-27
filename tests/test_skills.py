"""Unit tests for the Skills resource and Skill type.

All HTTP calls are intercepted via respx — no live server required.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from querri._base_client import SyncHTTPClient
from querri._config import ClientConfig

BASE = "https://test.querri.com/api/v1"

_SKILL_PAYLOAD = {
    "uuid": "skill_001",
    "created_by": "usr_creator",
    "org_shared": False,
    "title": "Cohort Retention",
    "description": "Computes monthly cohort retention from a sessions table.",
    "advanced_instructions": "Use DuckDB SQL. Output one row per cohort week.",
    "example_plan": [
        {
            "name": "Load sessions",
            "tool": "load_source",
            "prompt": "Load the sessions table",
            "parent": None,
            "columns": [],
            "dependencies": [],
        }
    ],
    "created_at": "2026-04-26T10:00:00Z",
    "updated_at": "2026-04-26T10:00:00Z",
}


def _make_config() -> ClientConfig:
    return ClientConfig(
        api_key="qk_test",
        org_id="org_test",
        base_url=BASE,
        timeout=10.0,
        max_retries=0,
    )


def _http() -> SyncHTTPClient:
    return SyncHTTPClient(_make_config())


# ---------------------------------------------------------------------------
# Skill type
# ---------------------------------------------------------------------------


class TestSkillType:
    """Tests for querri.types.skill.Skill."""

    def test_model_validate_maps_uuid_to_id(self):
        from querri.types.skill import Skill

        skill = Skill.model_validate(_SKILL_PAYLOAD)
        assert skill.id == "skill_001"

    def test_model_validate_preserves_id_if_present(self):
        from querri.types.skill import Skill

        payload = {**_SKILL_PAYLOAD, "id": "existing_id"}
        skill = Skill.model_validate(payload)
        assert skill.id == "existing_id"

    def test_model_fields(self):
        from querri.types.skill import Skill

        skill = Skill.model_validate(_SKILL_PAYLOAD)
        assert skill.created_by == "usr_creator"
        assert skill.org_shared is False
        assert skill.title == "Cohort Retention"
        assert "cohort retention" in skill.description.lower()
        assert "DuckDB" in skill.advanced_instructions
        assert isinstance(skill.example_plan, list)
        assert len(skill.example_plan) == 1
        assert skill.example_plan[0]["name"] == "Load sessions"
        assert skill.created_at == "2026-04-26T10:00:00Z"
        assert skill.updated_at == "2026-04-26T10:00:00Z"

    def test_example_plan_is_list_of_dicts(self):
        """example_plan must be List[Dict], not List[PlanStep] (DECISIONS.md D10)."""
        from querri.types.skill import Skill

        skill = Skill.model_validate(_SKILL_PAYLOAD)
        assert all(isinstance(step, dict) for step in skill.example_plan)

    def test_defaults(self):
        from querri.types.skill import Skill

        minimal = {
            "uuid": "skill_min",
            "created_by": "usr_x",
            "title": "Min Skill",
            "description": "Minimal description here.",
        }
        skill = Skill.model_validate(minimal)
        assert skill.advanced_instructions == ""
        assert skill.example_plan == []
        assert skill.org_shared is False
        assert skill.created_at is None
        assert skill.updated_at is None


# ---------------------------------------------------------------------------
# Skills resource — sync
# ---------------------------------------------------------------------------


class TestSkillsSync:
    """Tests for querri.resources.skills.Skills."""

    @respx.mock
    def test_list_returns_cursor_page(self):
        respx.get(f"{BASE}/skills").mock(
            return_value=httpx.Response(
                200,
                json={"data": [_SKILL_PAYLOAD], "next_cursor": None},
            )
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        page = skills.list()
        items = list(page)
        assert len(items) == 1
        assert items[0].id == "skill_001"
        assert items[0].title == "Cohort Retention"

    @respx.mock
    def test_list_passes_query_params(self):
        route = respx.get(f"{BASE}/skills").mock(
            return_value=httpx.Response(
                200,
                json={"data": [], "next_cursor": None},
            )
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        list(skills.list(q="cohort", mine=True, limit=10))
        req = route.calls[0].request
        assert b"q=cohort" in req.url.query or "q=cohort" in str(req.url)
        assert "mine=True" in str(req.url) or "mine=true" in str(req.url)
        assert "limit=10" in str(req.url)

    @respx.mock
    def test_get_returns_skill(self):
        respx.get(f"{BASE}/skills/skill_001").mock(
            return_value=httpx.Response(200, json=_SKILL_PAYLOAD)
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        skill = skills.get("skill_001")
        assert skill.id == "skill_001"
        assert skill.title == "Cohort Retention"

    @respx.mock
    def test_create_sends_body_and_returns_skill(self):
        route = respx.post(f"{BASE}/skills").mock(
            return_value=httpx.Response(201, json=_SKILL_PAYLOAD)
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        skill = skills.create(
            title="Cohort Retention",
            description="Computes monthly cohort retention from a sessions table.",
            advanced_instructions="Use DuckDB SQL.",
            example_plan=[
                {
                    "name": "Load sessions",
                    "tool": "load_source",
                    "prompt": "Load it",
                    "parent": None,
                    "columns": [],
                    "dependencies": [],
                }
            ],
            org_shared=False,
        )
        assert skill.id == "skill_001"
        req = route.calls[0].request
        body = req.content
        assert b"Cohort Retention" in body
        assert b"example_plan" in body

    @respx.mock
    def test_create_defaults_empty_plan(self):
        route = respx.post(f"{BASE}/skills").mock(
            return_value=httpx.Response(201, json=_SKILL_PAYLOAD)
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        skills.create(
            title="Simple",
            description="A simple instruction-only skill.",
        )
        req = route.calls[0].request
        body = req.content
        assert b"example_plan" in body
        # Should send empty array, not omit the field
        assert b"[]" in body

    @respx.mock
    def test_update_sends_partial_body(self):
        route = respx.put(f"{BASE}/skills/skill_001").mock(
            return_value=httpx.Response(
                200, json={**_SKILL_PAYLOAD, "title": "Updated Title"}
            )
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        skill = skills.update("skill_001", title="Updated Title")
        assert skill.title == "Updated Title"
        req = route.calls[0].request
        body = req.content
        assert b"Updated Title" in body
        # Should not send fields that weren't provided
        assert b"description" not in body

    @respx.mock
    def test_delete_sends_delete_request(self):
        route = respx.delete(f"{BASE}/skills/skill_001").mock(
            return_value=httpx.Response(204)
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        result = skills.delete("skill_001")
        assert result is None
        assert route.called

    @respx.mock
    def test_list_with_shared_filter(self):
        route = respx.get(f"{BASE}/skills").mock(
            return_value=httpx.Response(
                200,
                json={"data": [], "next_cursor": None},
            )
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        list(skills.list(shared=True))
        assert "shared=True" in str(route.calls[0].request.url) or "shared=true" in str(
            route.calls[0].request.url
        )

    @respx.mock
    def test_update_org_shared_sends_field(self):
        route = respx.put(f"{BASE}/skills/skill_001").mock(
            return_value=httpx.Response(
                200, json={**_SKILL_PAYLOAD, "org_shared": True}
            )
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        skill = skills.update("skill_001", org_shared=True)
        assert skill.org_shared is True
        req = route.calls[0].request
        assert b"org_shared" in req.content


# ---------------------------------------------------------------------------
# Skills resource — async
# ---------------------------------------------------------------------------


class TestSkillsAsync:
    """Tests for querri.resources.skills.AsyncSkills."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_async(self):
        from querri._base_client import AsyncHTTPClient

        respx.get(f"{BASE}/skills/skill_001").mock(
            return_value=httpx.Response(200, json=_SKILL_PAYLOAD)
        )
        from querri.resources.skills import AsyncSkills

        http = AsyncHTTPClient(_make_config())
        skills = AsyncSkills(http)
        skill = await skills.get("skill_001")
        assert skill.id == "skill_001"
        await http.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_async(self):
        from querri._base_client import AsyncHTTPClient

        respx.post(f"{BASE}/skills").mock(
            return_value=httpx.Response(201, json=_SKILL_PAYLOAD)
        )
        from querri.resources.skills import AsyncSkills

        http = AsyncHTTPClient(_make_config())
        skills = AsyncSkills(http)
        skill = await skills.create(
            title="Cohort Retention",
            description="Computes monthly cohort retention from a sessions table.",
        )
        assert skill.id == "skill_001"
        await http.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_async(self):
        from querri._base_client import AsyncHTTPClient

        route = respx.delete(f"{BASE}/skills/skill_001").mock(
            return_value=httpx.Response(204)
        )
        from querri.resources.skills import AsyncSkills

        http = AsyncHTTPClient(_make_config())
        skills = AsyncSkills(http)
        await skills.delete("skill_001")
        assert route.called
        await http.close()


# ---------------------------------------------------------------------------
# Skills resource — error handling
# ---------------------------------------------------------------------------


class TestSkillsErrors:
    """Verify that field-level API error codes surface as the correct exceptions.

    Wire format per SPEC §8.1: per-field errors include ``code``, ``field``,
    ``limit``, ``actual`` inside the ``error`` object.  The SDK's
    ``raise_for_status`` maps the ``code`` string onto the raised exception's
    ``.code`` attribute; callers can inspect it for programmatic handling.
    """

    @respx.mock
    def test_create_title_too_long_raises_validation_error(self):
        from querri._exceptions import ValidationError

        respx.post(f"{BASE}/skills").mock(
            return_value=httpx.Response(
                400,
                json={
                    "error": {
                        "type": "invalid_request",
                        "code": "title_too_long",
                        "message": "title exceeds 100 characters",
                        "field": "title",
                        "limit": 100,
                        "actual": 150,
                    }
                },
            )
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        with pytest.raises(ValidationError) as exc_info:
            skills.create(title="x" * 150, description="A valid description here.")
        assert exc_info.value.status == 400
        assert exc_info.value.code == "title_too_long"

    @respx.mock
    def test_create_description_too_short_raises_validation_error(self):
        from querri._exceptions import ValidationError

        respx.post(f"{BASE}/skills").mock(
            return_value=httpx.Response(
                400,
                json={
                    "error": {
                        "type": "invalid_request",
                        "code": "description_too_short",
                        "message": "description must be at least 10 characters",
                        "field": "description",
                        "limit": 10,
                        "actual": 5,
                    }
                },
            )
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        with pytest.raises(ValidationError) as exc_info:
            skills.create(title="Valid Title", description="Hi")
        assert exc_info.value.status == 400
        assert exc_info.value.code == "description_too_short"

    @respx.mock
    def test_update_org_shared_admin_required_raises_permission_error(self):
        """Non-admin toggling org_shared gets 403 admin_required (SPEC §5.1)."""
        from querri._exceptions import PermissionError

        respx.put(f"{BASE}/skills/skill_001").mock(
            return_value=httpx.Response(
                403,
                json={
                    "error": {
                        "type": "permission_denied",
                        "code": "admin_required",
                        "message": "org_shared toggle requires admin role",
                    }
                },
            )
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        with pytest.raises(PermissionError) as exc_info:
            skills.update("skill_001", org_shared=True)
        assert exc_info.value.status == 403
        assert exc_info.value.code == "admin_required"

    @respx.mock
    def test_get_nonexistent_skill_raises_not_found_error(self):
        from querri._exceptions import NotFoundError

        respx.get(f"{BASE}/skills/missing_001").mock(
            return_value=httpx.Response(
                404,
                json={
                    "error": {
                        "type": "not_found",
                        "code": "skill_not_found",
                        "message": "skill not found",
                    }
                },
            )
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        with pytest.raises(NotFoundError) as exc_info:
            skills.get("missing_001")
        assert exc_info.value.status == 404

    @respx.mock
    def test_create_invalid_example_plan_topology_raises_validation_error(self):
        """DAG validation failure (SPEC §7.4) surfaces as ValidationError."""
        from querri._exceptions import ValidationError

        respx.post(f"{BASE}/skills").mock(
            return_value=httpx.Response(
                400,
                json={
                    "error": {
                        "type": "invalid_request",
                        "code": "invalid_example_plan_topology",
                        "message": "example_plan has a cycle or dangling reference",
                        "field": "example_plan",
                    }
                },
            )
        )
        from querri.resources.skills import Skills

        skills = Skills(_http())
        with pytest.raises(ValidationError) as exc_info:
            skills.create(
                title="Bad Plan Skill",
                description="Skill with a cyclic example plan.",
                example_plan=[
                    {
                        "name": "Step A",
                        "tool": "load_source",
                        "prompt": "Load it",
                        "parent": "Step B",  # cycle: A→B→A
                        "columns": [],
                        "dependencies": [],
                    },
                    {
                        "name": "Step B",
                        "tool": "duckdb_query",
                        "prompt": "Query it",
                        "parent": "Step A",
                        "columns": [],
                        "dependencies": [],
                    },
                ],
            )
        assert exc_info.value.status == 400
        assert exc_info.value.code == "invalid_example_plan_topology"


# ---------------------------------------------------------------------------
# Client integration — skills registered on Querri and AsyncQuerri
# ---------------------------------------------------------------------------


class TestClientIntegration:
    """Verify skills is accessible via the top-level client."""

    def test_querri_client_has_skills(self):
        from querri import Querri
        from querri.resources.skills import Skills

        client = Querri(api_key="qk_test", org_id="org_test")
        assert isinstance(client.skills, Skills)
        client.close()

    def test_async_querri_client_has_skills(self):
        from querri import AsyncQuerri
        from querri.resources.skills import AsyncSkills

        client = AsyncQuerri(api_key="qk_test", org_id="org_test")
        assert isinstance(client.skills, AsyncSkills)

    def test_skill_exported_from_top_level(self):
        from querri import Skill
        from querri.types.skill import Skill as SkillType

        assert Skill is SkillType
