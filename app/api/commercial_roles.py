"""Creator-scoped Commercial Role lifecycle and suggestion API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.asset_library import _creator_profile
from app.models.commercial_role import COMMERCIAL_ROLE_VOCABULARY_VERSION
from app.services.commercial_role_service import (
    CommercialRoleError,
    CommercialRoleService,
    CommercialRoleSuggestionService,
)


router = APIRouter(
    prefix="/api/v1/commercial-roles", tags=["commercial-roles"]
)


class HumanRoleRequest(BaseModel):
    role: str
    actorType: str = "OPERATOR"
    actorIdentifier: str | None = None
    reason: str | None = None


def _service() -> CommercialRoleService:
    return CommercialRoleService()


def _suggestions() -> CommercialRoleSuggestionService:
    return CommercialRoleSuggestionService()


def _creator_id() -> int:
    return int(_creator_profile()["id"])


def _actor_identifier(request: HumanRoleRequest, creator_id: int) -> str:
    return (
        str(request.actorIdentifier or "").strip()
        or f"creator-profile:{creator_id}"
    )


def _assignment_payload(value):
    return {
        "assignmentId": str(value.assignment_id),
        "assetId": value.asset_id,
        "creatorProfileId": value.creator_profile_id,
        "role": value.role.value,
        "state": value.state.value,
        "origin": value.origin.value,
        "rationale": value.rationale,
        "suggestionConfidence": value.suggestion_confidence,
        "evidence": dict(value.evidence),
        "assignedByType": (
            value.assigned_by_type.value if value.assigned_by_type else None
        ),
        "assignedByIdentifier": value.assigned_by_identifier,
        "vocabularyVersion": value.vocabulary_version,
        "createdAt": value.created_at.isoformat() if value.created_at else None,
        "updatedAt": value.updated_at.isoformat() if value.updated_at else None,
    }


@router.get("/vocabulary")
def get_vocabulary():
    return {
        "version": COMMERCIAL_ROLE_VOCABULARY_VERSION,
        "roles": [role.value for role in _service().vocabulary()],
    }


@router.get("/assets/{asset_id}")
def list_asset_roles(asset_id: int):
    creator_id = _creator_id()
    try:
        roles = _service().list_for_asset(
            asset_id=asset_id, creator_profile_id=creator_id
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"items": [_assignment_payload(item) for item in roles]}


@router.get("/assets/{asset_id}/effective")
def list_effective_asset_roles(asset_id: int):
    creator_id = _creator_id()
    try:
        roles = _service().effective_roles(
            asset_id=asset_id, creator_profile_id=creator_id
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"items": [_assignment_payload(item) for item in roles]}


@router.get("/assets/{asset_id}/history")
def list_asset_role_history(asset_id: int):
    creator_id = _creator_id()
    try:
        history = _service().history(
            asset_id=asset_id, creator_profile_id=creator_id
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {
        "items": [{
            "historyId": item.history_id,
            "assignmentId": str(item.assignment_id),
            "assetId": item.asset_id,
            "creatorProfileId": item.creator_profile_id,
            "role": item.role.value,
            "eventType": item.event_type,
            "previousState": (
                item.previous_state.value if item.previous_state else None
            ),
            "newState": item.new_state.value,
            "actorType": item.actor_type.value,
            "actorIdentifier": item.actor_identifier,
            "reason": item.reason,
            "createdAt": item.created_at.isoformat(),
        } for item in history],
    }


@router.post("/assets/{asset_id}/suggestions")
def suggest_asset_roles(asset_id: int):
    creator_id = _creator_id()
    try:
        suggestions = _suggestions().suggest(
            asset_id=asset_id, creator_profile_id=creator_id
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"items": [_assignment_payload(item) for item in suggestions]}


@router.post("/assets/{asset_id}/assignments")
def assign_asset_role(asset_id: int, request: HumanRoleRequest):
    return _human_action("assign", asset_id, request)


@router.post("/assets/{asset_id}/approve")
def approve_asset_role(asset_id: int, request: HumanRoleRequest):
    return _human_action("approve", asset_id, request)


@router.post("/assets/{asset_id}/reject")
def reject_asset_role(asset_id: int, request: HumanRoleRequest):
    return _human_action("reject", asset_id, request)


@router.post("/assets/{asset_id}/deactivate")
def deactivate_asset_role(asset_id: int, request: HumanRoleRequest):
    return _human_action("deactivate", asset_id, request)


@router.post("/assets/{asset_id}/reactivate")
def reactivate_asset_role(asset_id: int, request: HumanRoleRequest):
    return _human_action("reactivate", asset_id, request)


@router.post("/assets/{asset_id}/retire")
def retire_asset_role(asset_id: int, request: HumanRoleRequest):
    return _human_action("retire", asset_id, request)


def _human_action(action: str, asset_id: int, request: HumanRoleRequest):
    creator_id = _creator_id()
    values = {
        "asset_id": asset_id,
        "creator_profile_id": creator_id,
        "role": request.role,
        "actor_type": request.actorType,
        "actor_identifier": _actor_identifier(request, creator_id),
    }
    try:
        if action == "assign":
            assignment = _service().assign(
                **values, rationale=request.reason
            )
        else:
            assignment = getattr(_service(), action)(
                **values, reason=request.reason
            )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except CommercialRoleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _assignment_payload(assignment)
