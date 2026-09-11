"""Creator-scoped Global AI Training controls API."""
from datetime import date, datetime
from uuid import UUID
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.background_operations import _context
from app.services.ai_training_control_service import (
    AiTrainingControlError, AiTrainingControlService,
)
from app.services.relationships_service import RelationshipsService
from app.services.ai_training_work_queue_service import AiTrainingWorkQueueService
from app.services.ai_training_history_service import AiTrainingHistoryService
from app.api.developer_authorization import require_developer_authorization

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


class CustomerTreatmentRequest(BaseModel):
    salesPressure: str
    freeEngagement: str
    responseLength: str

    def configuration(self):
        return {"sales_pressure": self.salesPressure,
                "free_engagement": self.freeEngagement,
                "response_length": self.responseLength}


class CustomerTrainingPlanRequest(BaseModel):
    operatorText: str = Field(min_length=1, max_length=2000)
    conversationGuidance: list[str] | None = None
    treatment: CustomerTreatmentRequest | None = None


class QueueCreateRequest(BaseModel):
    originalRequestText: str = Field(min_length=1, max_length=2000)
    scope: str = "GLOBAL"
    customerProjectionKey: str | None = None


class QueueEditRequest(BaseModel):
    originalRequestText: str = Field(min_length=1, max_length=2000)


def _instruction(item):
    def iso(value):
        return value.isoformat() if isinstance(value, (date, datetime)) else value
    result = {
        "instructionId": str(item.instruction_id),
        "creatorProfileId": item.creator_profile_id,
        "fanvueAccountId": item.fanvue_account_id,
        "customerFanvueUserId": item.customer_fanvue_user_id,
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
    result["implementationStatus"] = AiTrainingWorkQueueService.implementation_status(item)
    return result


def _customer_target(projection_key: str):
    creator_id, account_id = _context()
    parts = projection_key.split(":")
    if len(parts) != 4 or parts[0] != "telegram":
        raise HTTPException(status_code=404, detail="Customer relationship was not found.")
    try:
        key_creator, key_account, telegram_user_id = map(int, parts[1:])
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Customer relationship was not found.") from error
    if key_creator != creator_id or key_account != account_id:
        raise HTTPException(status_code=404, detail="Customer relationship was not found.")
    try:
        context = RelationshipsService().control_context(
            creator_profile_id=creator_id, fanvue_account_id=account_id,
            telegram_user_id=telegram_user_id,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    customer_id = context.get("local_fanvue_user_id")
    return creator_id, account_id, int(customer_id) if customer_id is not None else None


@router.get("/queue")
def list_training_queue():
    creator_id,account_id=_context()
    return {"items":AiTrainingWorkQueueService().list(creator_profile_id=creator_id,fanvue_account_id=account_id)}


@router.get("/history-view")
def training_history_view():
    creator_id,account_id=_context()
    result=AiTrainingHistoryService().list_visible(creator_profile_id=creator_id,fanvue_account_id=account_id)
    return {"baselineAt":result["baselineAt"].isoformat() if result["baselineAt"] else None,
            "items":[_instruction(item) for item in result["items"]]}


@router.post("/queue",status_code=201)
def add_training_queue(payload: QueueCreateRequest):
    creator_id,account_id=_context();customer_id=None
    if payload.scope=="CUSTOMER":
        if not payload.customerProjectionKey:raise HTTPException(status_code=422,detail="Select a canonical customer for customer-scoped work.")
        _,_,customer_id=_customer_target(payload.customerProjectionKey)
        if customer_id is None:raise HTTPException(status_code=409,detail="A verified customer identity is required.")
    try:return AiTrainingWorkQueueService().add(creator_profile_id=creator_id,fanvue_account_id=account_id,
        scope=payload.scope,customer_fanvue_user_id=customer_id,customer_projection_key=payload.customerProjectionKey,
        text=payload.originalRequestText)
    except AiTrainingControlError as error:raise HTTPException(status_code=422,detail=str(error)) from error


@router.patch("/queue/{work_item_id}")
def edit_training_queue(work_item_id: UUID,payload: QueueEditRequest):
    creator_id,account_id=_context()
    try:return AiTrainingWorkQueueService().edit(work_item_id,creator_profile_id=creator_id,fanvue_account_id=account_id,text=payload.originalRequestText)
    except AiTrainingControlError as error:raise HTTPException(status_code=409,detail=str(error)) from error


@router.post("/queue/{work_item_id}/{action}")
def transition_training_queue(work_item_id: UUID,action: str):
    creator_id,account_id=_context();service=AiTrainingWorkQueueService();identity={"creator_profile_id":creator_id,"fanvue_account_id":account_id}
    try:
        if action=="analyze":return service.analyze(work_item_id,**identity)
        if action=="apply":return service.apply(work_item_id,**identity)
        if action=="close":return service.close(work_item_id,**identity)
        raise AiTrainingControlError("Unsupported Queue action.")
    except AiTrainingControlError as error:raise HTTPException(status_code=409,detail=str(error)) from error


@router.post("/queue/{work_item_id}/implementation/prepare", dependencies=[Depends(require_developer_authorization)])
def prepare_training_implementation(work_item_id: UUID):
    creator_id,account_id=_context()
    try:return AiTrainingWorkQueueService().prepare_implementation(work_item_id,creator_profile_id=creator_id,fanvue_account_id=account_id)
    except AiTrainingControlError as error:raise HTTPException(status_code=409,detail=str(error)) from error


@router.post("/queue/{work_item_id}/implementation/start", dependencies=[Depends(require_developer_authorization)])
def start_training_implementation(work_item_id: UUID):
    creator_id,account_id=_context()
    try:return AiTrainingWorkQueueService().start_implementation(work_item_id,creator_profile_id=creator_id,fanvue_account_id=account_id)
    except PermissionError as error:raise HTTPException(status_code=403,detail=str(error)) from error
    except (AiTrainingControlError,RuntimeError,ValueError) as error:raise HTTPException(status_code=409,detail=str(error)) from error


@router.get("/queue/{work_item_id}/implementation", dependencies=[Depends(require_developer_authorization)])
def training_implementation_detail(work_item_id: UUID):
    creator_id,account_id=_context()
    try:return AiTrainingWorkQueueService().implementation_detail(work_item_id,creator_profile_id=creator_id,fanvue_account_id=account_id)
    except AiTrainingControlError as error:raise HTTPException(status_code=404,detail=str(error)) from error


@router.post("/queue/{work_item_id}/implementation/verify", dependencies=[Depends(require_developer_authorization)])
def verify_training_implementation(work_item_id: UUID):
    creator_id,account_id=_context()
    try:return AiTrainingWorkQueueService().verify_implementation(work_item_id,creator_profile_id=creator_id,fanvue_account_id=account_id)
    except AiTrainingControlError as error:raise HTTPException(status_code=409,detail=str(error)) from error


@router.post("/customer-preview")
def preview_customer_training(payload: TrainingPreviewRequest):
    try:
        return AiTrainingControlService().classify_customer(payload.operatorText)
    except AiTrainingControlError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/customers/{projection_key}/analyze")
def analyze_customer_training(projection_key: str, payload: TrainingPreviewRequest):
    _customer_target(projection_key)
    try:
        return AiTrainingControlService().analyze_customer_training(payload.operatorText)
    except AiTrainingControlError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/customers/{projection_key}/apply-plan")
def apply_customer_training_plan(projection_key: str, payload: CustomerTrainingPlanRequest):
    creator_id, account_id, customer_id = _customer_target(projection_key)
    if customer_id is None:
        raise HTTPException(status_code=409, detail="A verified customer identity is required before training can be applied.")
    try:
        result = AiTrainingControlService().apply_customer_training_plan(
            creator_profile_id=creator_id, fanvue_account_id=account_id,
            customer_fanvue_user_id=customer_id, operator_text=payload.operatorText,
            conversation_guidance=payload.conversationGuidance or [],
            configuration=(payload.treatment.configuration() if payload.treatment
                           else dict(AiTrainingControlService.TREATMENT_DEFAULTS)))
    except AiTrainingControlError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"guidance": [_instruction(item) for item in result["guidance"]],
            "treatment": _instruction(result["treatment"]) if result["treatment"] else None,
            "configuration": result["configuration"],
            "usingAvaDefaults": result["usingAvaDefaults"]}


@router.post("/customer-treatment/preview")
def preview_customer_treatment(payload: CustomerTreatmentRequest):
    try:
        return AiTrainingControlService().preview_customer_treatment(payload.configuration())
    except AiTrainingControlError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/customer-treatment/{projection_key}")
def get_customer_treatment(projection_key: str):
    creator_id, account_id, customer_id = _customer_target(projection_key)
    if customer_id is None:
        return {"eligible": False, "eligibilityReason": "A verified customer identity is required before treatment can be applied.",
                "configuration": AiTrainingControlService.TREATMENT_DEFAULTS,
                "usingAvaDefaults": True, "runtimeEffect": "BOUNDED_PHASE_2B", "item": None}
    result = AiTrainingControlService().get_customer_treatment(
        creator_profile_id=creator_id, fanvue_account_id=account_id,
        customer_fanvue_user_id=customer_id)
    return {**result, "eligible": True, "eligibilityReason": None,
            "item": _instruction(result["item"]) if result["item"] else None}


@router.put("/customer-treatment/{projection_key}")
def apply_customer_treatment(projection_key: str, payload: CustomerTreatmentRequest):
    creator_id, account_id, customer_id = _customer_target(projection_key)
    if customer_id is None:
        raise HTTPException(status_code=409, detail="A verified customer identity is required before treatment can be applied.")
    try:
        item = AiTrainingControlService().apply_customer_treatment(
            creator_profile_id=creator_id, fanvue_account_id=account_id,
            customer_fanvue_user_id=customer_id, configuration=payload.configuration())
        result = AiTrainingControlService().get_customer_treatment(
            creator_profile_id=creator_id, fanvue_account_id=account_id,
            customer_fanvue_user_id=customer_id)
    except AiTrainingControlError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {**result, "item": _instruction(item) if item else None,
            "eligible": True, "eligibilityReason": None}


@router.post("/customer-treatment/{projection_key}/{instruction_id}/disable")
def disable_customer_treatment(projection_key: str, instruction_id: UUID):
    creator_id, account_id, customer_id = _customer_target(projection_key)
    if customer_id is None:
        raise HTTPException(status_code=409, detail="A verified customer identity is required.")
    try:
        item = AiTrainingControlService().disable_customer_treatment(
            instruction_id, creator_profile_id=creator_id, fanvue_account_id=account_id,
            customer_fanvue_user_id=customer_id)
    except AiTrainingControlError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _instruction(item)


@router.get("/customer-treatment/{projection_key}/{instruction_id}/history")
def customer_treatment_history(projection_key: str, instruction_id: UUID):
    creator_id, account_id, customer_id = _customer_target(projection_key)
    service = AiTrainingControlService()
    item = service.repository.customer_treatment(creator_profile_id=creator_id,
        fanvue_account_id=account_id, customer_fanvue_user_id=customer_id) if customer_id else None
    if item is None or item.instruction_id != instruction_id:
        raise HTTPException(status_code=404, detail="Customer treatment was not found.")
    return {"items": service.repository.revisions(instruction_id,
        creator_profile_id=creator_id, fanvue_account_id=account_id)}


@router.get("/customers")
def list_all_customer_training():
    creator_id, account_id = _context()
    return {"items": [_instruction(item) for item in
        AiTrainingControlService().repository.list_all_customer(
            creator_profile_id=creator_id, fanvue_account_id=account_id)]}


@router.get("/customer-history/{instruction_id}")
def account_customer_training_history(instruction_id: UUID):
    creator_id, account_id = _context()
    service = AiTrainingControlService()
    if service.repository.get_customer_in_account(instruction_id,
            creator_profile_id=creator_id, fanvue_account_id=account_id) is None:
        raise HTTPException(status_code=404, detail="Customer training instruction was not found.")
    return {"items": service.repository.revisions(instruction_id,
        creator_profile_id=creator_id, fanvue_account_id=account_id)}


@router.get("/customers/{projection_key}")
def list_customer_training(projection_key: str):
    creator_id, account_id, customer_id = _customer_target(projection_key)
    if customer_id is None:
        return {"eligible": False, "eligibilityReason": "A verified customer identity is required before training can be activated.", "items": []}
    items = AiTrainingControlService().list_customer(
        creator_profile_id=creator_id, fanvue_account_id=account_id,
        customer_fanvue_user_id=customer_id)
    return {"eligible": True, "eligibilityReason": None,
            "items": [_instruction(item) for item in items]}


@router.post("/customers/{projection_key}", status_code=201)
def create_customer_training(projection_key: str, payload: TrainingCreateRequest):
    creator_id, account_id, customer_id = _customer_target(projection_key)
    if customer_id is None:
        raise HTTPException(status_code=409, detail="A verified customer identity is required before training can be activated.")
    try:
        item = AiTrainingControlService().create_customer(
            creator_profile_id=creator_id, fanvue_account_id=account_id,
            customer_fanvue_user_id=customer_id, operator_text=payload.operatorText,
            priority=payload.priority, activate=payload.activate)
    except AiTrainingControlError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _instruction(item)


@router.patch("/customers/{projection_key}/{instruction_id}")
def edit_customer_training(projection_key: str, instruction_id: UUID, payload: TrainingEditRequest):
    creator_id, account_id, customer_id = _customer_target(projection_key)
    if customer_id is None:
        raise HTTPException(status_code=409, detail="A verified customer identity is required.")
    try:
        item = AiTrainingControlService().edit_customer(
            instruction_id, creator_profile_id=creator_id, fanvue_account_id=account_id,
            customer_fanvue_user_id=customer_id, operator_text=payload.operatorText,
            priority=payload.priority)
    except AiTrainingControlError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _instruction(item)


@router.post("/customers/{projection_key}/{instruction_id}/{action}")
def transition_customer_training(projection_key: str, instruction_id: UUID, action: str):
    creator_id, account_id, customer_id = _customer_target(projection_key)
    if customer_id is None:
        raise HTTPException(status_code=409, detail="A verified customer identity is required.")
    try:
        item = AiTrainingControlService().transition_customer(
            instruction_id, creator_profile_id=creator_id, fanvue_account_id=account_id,
            customer_fanvue_user_id=customer_id, action=action)
    except AiTrainingControlError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _instruction(item)


@router.get("/customers/{projection_key}/{instruction_id}/history")
def customer_training_history(projection_key: str, instruction_id: UUID):
    creator_id, account_id, customer_id = _customer_target(projection_key)
    service = AiTrainingControlService()
    if customer_id is None or service.repository.get_customer(
        instruction_id, creator_profile_id=creator_id, fanvue_account_id=account_id,
        customer_fanvue_user_id=customer_id) is None:
        raise HTTPException(status_code=404, detail="Customer training instruction was not found.")
    return {"items": service.repository.revisions(
        instruction_id, creator_profile_id=creator_id, fanvue_account_id=account_id)}


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
    service = AiTrainingControlService()
    if service.repository.get(instruction_id, creator_profile_id=creator_id,
                              fanvue_account_id=account_id) is None:
        raise HTTPException(status_code=404, detail="Global training instruction was not found.")
    rows = service.repository.revisions(
        instruction_id, creator_profile_id=creator_id, fanvue_account_id=account_id
    )
    return {"items": rows}
