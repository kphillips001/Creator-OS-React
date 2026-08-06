from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import commercial_roles as api
from app.models.asset_intelligence import (
    AssetIntelligenceProfile,
    AssetIntelligenceStatus,
)
from app.models.commercial_role import (
    COMMERCIAL_ROLE_VOCABULARY_VERSION,
    CommercialRole,
    CommercialRoleActorType,
    CommercialRoleAssignment,
    CommercialRoleHistoryEntry,
    CommercialRoleOrigin,
    CommercialRoleState,
)
from app.services.commercial_role_service import (
    CommercialRoleError,
    CommercialRoleService,
    CommercialRoleSuggestionService,
)


class FakeAssets:
    def __init__(self, creator_profile_id=7):
        self.asset = SimpleNamespace(id=12, creator_profile_id=creator_profile_id)

    def get_by_id(self, asset_id):
        return self.asset if int(asset_id) == self.asset.id else None


class FakeRoles:
    def __init__(self):
        self.items = {}
        self.events = []

    def get(self, *, asset_id, creator_profile_id, role):
        return self.items.get((asset_id, creator_profile_id, role))

    def create(
        self, *, asset_id, creator_profile_id, role, state, origin,
        rationale, suggestion_confidence, evidence, actor_type,
        actor_identifier, event_type,
    ):
        item = CommercialRoleAssignment(
            assignment_id=uuid4(), asset_id=asset_id,
            creator_profile_id=creator_profile_id, role=role, state=state,
            origin=origin, rationale=rationale,
            suggestion_confidence=suggestion_confidence, evidence=dict(evidence),
            assigned_by_type=actor_type,
            assigned_by_identifier=actor_identifier,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.items[(asset_id, creator_profile_id, role)] = item
        self._event(item, event_type, None, actor_type, actor_identifier, rationale)
        return item

    def transition(
        self, *, assignment_id, creator_profile_id, expected_state, new_state,
        actor_type, actor_identifier, event_type, reason, origin=None,
    ):
        current = next((
            item for item in self.items.values()
            if item.assignment_id == assignment_id
            and item.creator_profile_id == creator_profile_id
        ), None)
        if current is None or current.state is not expected_state:
            return None
        updated = replace(
            current, state=new_state, origin=origin or current.origin,
            assigned_by_type=actor_type,
            assigned_by_identifier=actor_identifier,
            updated_at=datetime.now(timezone.utc),
        )
        self.items[(current.asset_id, creator_profile_id, current.role)] = updated
        self._event(
            updated, event_type, expected_state, actor_type,
            actor_identifier, reason,
        )
        return updated

    def list_for_asset(self, *, asset_id, creator_profile_id, states=None):
        values = tuple(
            item for item in self.items.values()
            if item.asset_id == asset_id
            and item.creator_profile_id == creator_profile_id
            and (not states or item.state in states)
        )
        return tuple(sorted(values, key=lambda item: item.role.value))

    def list_history(self, *, asset_id, creator_profile_id):
        return tuple(
            event for event in self.events
            if event.asset_id == asset_id
            and event.creator_profile_id == creator_profile_id
        )

    def _event(
        self, item, event_type, previous_state, actor_type,
        actor_identifier, reason,
    ):
        self.events.append(CommercialRoleHistoryEntry(
            history_id=len(self.events) + 1,
            assignment_id=item.assignment_id, asset_id=item.asset_id,
            creator_profile_id=item.creator_profile_id, role=item.role,
            event_type=event_type, previous_state=previous_state,
            new_state=item.state, actor_type=actor_type,
            actor_identifier=actor_identifier, reason=reason,
            created_at=datetime.now(timezone.utc),
        ))


@pytest.fixture
def role_setup():
    repository = FakeRoles()
    service = CommercialRoleService(
        repository=repository, asset_repository=FakeAssets()
    )
    return service, repository


def test_v1_vocabulary_is_frozen():
    assert [role.value for role in CommercialRoleService.vocabulary()] == [
        "DISCOVERY", "TEASER", "HERO", "CORE", "CORE_SESSION",
        "PROGRESSION", "PREMIUM", "FINALE", "FINALE_IMAGE",
        "FINALE_VIDEO", "BONUS",
    ]
    assert COMMERCIAL_ROLE_VOCABULARY_VERSION == "2.0"


def test_multiple_creator_owned_roles_can_be_assigned(role_setup):
    service, repository = role_setup
    hero = service.assign(
        asset_id=12, creator_profile_id=7, role="HERO",
        actor_type="CREATOR", actor_identifier="creator:7",
    )
    core = service.assign(
        asset_id=12, creator_profile_id=7, role="CORE",
        actor_type="OPERATOR", actor_identifier="operator:local",
    )
    assert hero.state is CommercialRoleState.APPROVED
    assert hero.origin is CommercialRoleOrigin.CREATOR_ASSIGNED
    assert core.origin is CommercialRoleOrigin.OPERATOR_ASSIGNED
    assert {item.role for item in service.effective_roles(
        asset_id=12, creator_profile_id=7
    )} == {CommercialRole.HERO, CommercialRole.CORE}
    assert len(repository.events) == 2


def test_ai_cannot_assign_or_approve_roles(role_setup):
    service, repository = role_setup
    with pytest.raises(CommercialRoleError, match="AI cannot"):
        service.assign(
            asset_id=12, creator_profile_id=7, role="HERO",
            actor_type="AI", actor_identifier="planner",
        )
    repository.create(
        asset_id=12, creator_profile_id=7, role=CommercialRole.HERO,
        state=CommercialRoleState.SUGGESTED,
        origin=CommercialRoleOrigin.AI_SUGGESTED,
        rationale="Suggested", suggestion_confidence=.8, evidence={},
        actor_type=CommercialRoleActorType.AI,
        actor_identifier="asset-intelligence-v1", event_type="SUGGESTED",
    )
    with pytest.raises(CommercialRoleError, match="AI cannot"):
        service.approve(
            asset_id=12, creator_profile_id=7, role="HERO",
            actor_type="AI", actor_identifier="planner",
        )
    approved = service.approve(
        asset_id=12, creator_profile_id=7, role="HERO",
        actor_type="OPERATOR", actor_identifier="operator:local",
    )
    assert approved.origin is CommercialRoleOrigin.AI_SUGGESTED
    assert approved.assigned_by_type is CommercialRoleActorType.OPERATOR


def test_lifecycle_history_and_effective_roles(role_setup):
    service, _ = role_setup
    assigned = service.assign(
        asset_id=12, creator_profile_id=7, role="PREMIUM",
        actor_type="OPERATOR", actor_identifier="operator:local",
    )
    inactive = service.deactivate(
        asset_id=12, creator_profile_id=7, role="PREMIUM",
        actor_type="OPERATOR", actor_identifier="operator:local",
        reason="Seasonal pause",
    )
    assert inactive.state is CommercialRoleState.INACTIVE
    assert service.effective_roles(asset_id=12, creator_profile_id=7) == ()
    active = service.reactivate(
        asset_id=12, creator_profile_id=7, role="PREMIUM",
        actor_type="CREATOR", actor_identifier="creator:7",
    )
    retired = service.retire(
        asset_id=12, creator_profile_id=7, role="PREMIUM",
        actor_type="CREATOR", actor_identifier="creator:7",
    )
    assert active.state is CommercialRoleState.APPROVED
    assert retired.state is CommercialRoleState.RETIRED
    assert [item.event_type for item in service.history(
        asset_id=12, creator_profile_id=7
    )] == ["ASSIGNED", "DEACTIVATE", "REACTIVATE", "RETIRED"]
    with pytest.raises(CommercialRoleError, match="Retired"):
        service.assign(
            asset_id=12, creator_profile_id=7, role="PREMIUM",
            actor_type="CREATOR", actor_identifier="creator:7",
        )
    assert assigned.assignment_id == retired.assignment_id


def test_rejected_suggestion_requires_explicit_human_reconsideration(role_setup):
    service, repository = role_setup
    repository.create(
        asset_id=12, creator_profile_id=7, role=CommercialRole.DISCOVERY,
        state=CommercialRoleState.SUGGESTED,
        origin=CommercialRoleOrigin.AI_SUGGESTED,
        rationale="Preview suitable", suggestion_confidence=.7, evidence={},
        actor_type=CommercialRoleActorType.AI,
        actor_identifier="asset-intelligence-v1", event_type="SUGGESTED",
    )
    service.reject(
        asset_id=12, creator_profile_id=7, role="DISCOVERY",
        actor_type="OPERATOR", actor_identifier="operator:local",
    )
    reconsidered = service.assign(
        asset_id=12, creator_profile_id=7, role="DISCOVERY",
        actor_type="CREATOR", actor_identifier="creator:7",
        rationale="Creator reconsidered the role.",
    )
    assert reconsidered.state is CommercialRoleState.APPROVED
    assert [item.event_type for item in repository.events] == [
        "SUGGESTED", "REJECT", "RECONSIDERED_AND_ASSIGNED",
    ]


class FakeIntelligence:
    def get_profile(self, asset_id):
        return AssetIntelligenceProfile(
            asset_id=asset_id, creator_profile_id=7,
            analysis_status=AssetIntelligenceStatus.READY,
            suggested_use_cases=("premium preview", "bonus alternate"),
            preview_suitability="high", quality_score=.82,
            content_uniqueness=.88, overall_confidence=.79,
        )


class FakePhotoshoots:
    def commercial_role_context_for_asset(self, asset_id, creator_profile_id):
        return {
            "photoshoot_session_id": "photoshoot-1",
            "shot_order": 6, "is_hero": False, "is_last": True,
        }


def test_ai_suggestions_reuse_intelligence_and_do_not_repeat_decisions(role_setup):
    service, repository = role_setup
    suggestions = CommercialRoleSuggestionService(
        role_service=service, intelligence_repository=FakeIntelligence(),
        photoshoot_repository=FakePhotoshoots(),
    )
    created = suggestions.suggest(asset_id=12, creator_profile_id=7)
    assert {item.role for item in created} == {
        CommercialRole.DISCOVERY, CommercialRole.HERO, CommercialRole.CORE,
        CommercialRole.PROGRESSION, CommercialRole.PREMIUM,
        CommercialRole.FINALE, CommercialRole.BONUS,
    }
    assert all(item.state is CommercialRoleState.SUGGESTED for item in created)
    assert all(
        item.origin is CommercialRoleOrigin.AI_SUGGESTED for item in created
    )
    assert suggestions.suggest(asset_id=12, creator_profile_id=7) == ()
    assert len(repository.events) == 7


def test_asset_scope_prevents_cross_creator_assignment():
    service = CommercialRoleService(
        repository=FakeRoles(), asset_repository=FakeAssets(creator_profile_id=8)
    )
    with pytest.raises(KeyError, match="not found"):
        service.assign(
            asset_id=12, creator_profile_id=7, role="CORE",
            actor_type="OPERATOR", actor_identifier="operator:local",
        )


def test_commercial_roles_api_exposes_vocabulary_and_lifecycle(monkeypatch, role_setup):
    service, repository = role_setup
    monkeypatch.setattr(api, "_service", lambda: service)
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 7})
    application = FastAPI()
    application.include_router(api.router)
    client = TestClient(application)

    vocabulary = client.get("/api/v1/commercial-roles/vocabulary")
    assert vocabulary.status_code == 200
    assert vocabulary.json()["version"] == "2.0"

    assigned = client.post(
        "/api/v1/commercial-roles/assets/12/assignments",
        json={"role": "CORE", "actorType": "OPERATOR"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["state"] == "APPROVED"

    effective = client.get("/api/v1/commercial-roles/assets/12/effective")
    assert effective.status_code == 200
    assert [item["role"] for item in effective.json()["items"]] == ["CORE"]

    history = client.get("/api/v1/commercial-roles/assets/12/history")
    assert history.status_code == 200
    assert history.json()["items"][0]["eventType"] == "ASSIGNED"
    assert len(repository.events) == 1


def test_migration_keeps_roles_independent_from_existing_commerce_domains():
    sql = Path(
        "migrations/forward/20260730_025_commercial_roles.sql"
    ).read_text(encoding="utf-8")
    assert "REFERENCES public.content_items" in sql
    for forbidden in (
        "asset_content_destinations", "commercial_offerings",
        "commercial_publications", "customer_entitlements",
        "purchase_intents", "products(", "publishing_jobs",
    ):
        assert forbidden not in sql
