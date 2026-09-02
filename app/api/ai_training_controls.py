"""Creator-scoped Global AI Training controls API."""
from datetime import date, datetime
from uuid import UUID
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.background_operations import _context
from app.services.ai_training_control_service import (
    AiTrainingControlError, AiTrainingControlService,
)

router = APIRouter(prefix="/api/v1/ai-training-controls", tags=["ai-training-controls"])


class TrainingPreviewRequest(BaseModel):
    operatorText: str = Field(min_length=1, max_length=2000)


class TrainingCreateRequest(TrainingPreviewRequest):
    priority: int = Field(default=100, ge=0, le=1000)
    activate: bool = True
    policyConfiguration: dict[str, Any] | None = None


class TrainingEditRequest(TrainingPreviewRequest):
    priority: int = Field(default=100, ge=0, le=1000)
    policyConfiguration: dict[str, Any] | None = None


def _instruction(item):
    def iso(value):
        return value.isoformat() if isinstance(value, (date, datetime)) else value
    return {
        "instructionId": str(item.instruction_id),
        "creatorProfileId": item.creator_profile_id,
        "fanvueAccountId": item.fanvue_account_id,
        "scope": item.scope, "instructionType": item.instruction_type.value,
        "originalOperatorText": item.original_operator_text,
        "normalizedInstruction": item.normalized_instruction,
        "status": item.status.value, "priority": item.priority,
        "source": item.source, "classificationReason": item.classification_reason,
        "policyKey": item.policy_key, "enforcementMode": item.enforcement_mode,
        "policyConfiguration": item.policy_configuration or {},
        "version": item.version, "createdAt": iso(item.created_at),
        "updatedAt": iso(item.updated_at), "enabledAt": iso(item.enabled_at),
        "disabledAt": iso(item.disabled_at), "archivedAt": iso(item.archived_at),
    }


@router.get("")
def list_global_training():
    creator_id, account_id = _context()
    return {"items": [_instruction(item) for item in AiTrainingControlService().list(
        creator_profile_id=creator_id, fanvue_account_id=account_id
    )]}


@router.post("/preview")
def preview_global_training(payload: TrainingPreviewRequest):
    try:
        return AiTrainingControlService().classify(payload.operatorText)
    except AiTrainingControlError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("", status_code=201)
def create_global_training(payload: TrainingCreateRequest):
    creator_id, account_id = _context()
    try:
        item = AiTrainingControlService().create(
            creator_profile_id=creator_id, fanvue_account_id=account_id,
            operator_text=payload.operatorText, priority=payload.priority,
            activate=payload.activate,
            policy_configuration=payload.policyConfiguration,
        )
    except AiTrainingControlError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    response = _instruction(item)
    response["runtimeRecognized"] = True
    if item.instruction_type.value == "SAFETY_HARD_STOP" and item.status.value == "ENABLED":
        response["runtimeRecognized"] = AiTrainingControlService().repository.is_backend_policy_enabled(
            creator_profile_id=creator_id, fanvue_account_id=account_id,
            policy_key=str(item.policy_key))
        if not response["runtimeRecognized"]:
            raise HTTPException(status_code=500, detail="Safety policy persisted but runtime projection could not recognize it.")
    if item.instruction_type.value == "ENGAGEMENT_RULE" and item.status.value == "ENABLED":
        from app.repositories.engagement_teaser_policy_repository import EngagementTeaserPolicyRepository
        response["runtimeRecognized"] = bool(EngagementTeaserPolicyRepository().active_policy(
            creator_profile_id=creator_id, fanvue_account_id=account_id))
        if not response["runtimeRecognized"]:
            raise HTTPException(status_code=500, detail="Engagement policy persisted but runtime projection could not recognize it.")
    if item.instruction_type.value == "SALES_RULE" and item.status.value == "ENABLED":
        from app.repositories.adaptive_sales_readiness_repository import AdaptiveSalesReadinessRepository
        response["runtimeRecognized"] = bool(AdaptiveSalesReadinessRepository().active_policy(
            creator_profile_id=creator_id, fanvue_account_id=account_id))
        if not response["runtimeRecognized"]:
            raise HTTPException(status_code=500, detail="Sales readiness policy persisted but Customer Sales Brain could not recognize it.")
    return response


@router.patch("/{instruction_id}")
def edit_global_training(instruction_id: UUID, payload: TrainingEditRequest):
    creator_id, account_id = _context()
    try:
        item = AiTrainingControlService().edit(
            instruction_id, creator_profile_id=creator_id,
            fanvue_account_id=account_id, operator_text=payload.operatorText,
            priority=payload.priority,
            policy_configuration=payload.policyConfiguration,
        )
    except AiTrainingControlError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _instruction(item)


@router.post("/{instruction_id}/{action}")
def transition_global_training(instruction_id: UUID, action: str):
    creator_id, account_id = _context()
    try:
        item = AiTrainingControlService().transition(
            instruction_id, creator_profile_id=creator_id,
            fanvue_account_id=account_id, action=action,
        )
    except AiTrainingControlError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _instruction(item)


@router.get("/{instruction_id}/history")
def global_training_history(instruction_id: UUID):
    creator_id, account_id = _context()
    rows = AiTrainingControlService().repository.revisions(
        instruction_id, creator_profile_id=creator_id, fanvue_account_id=account_id
    )
    return {"items": rows}
