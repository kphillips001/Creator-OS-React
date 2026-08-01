"""Creator-scoped operational boundary for canonical Sales Sessions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.asset_library import _creator_profile
from app.services.sales_session_service import (
    SalesSessionError,
    SalesSessionService,
)


router = APIRouter(prefix="/api/v1/sales-sessions", tags=["sales-sessions"])


class StartSalesSessionRequest(BaseModel):
    fanvueAccountId: int = Field(gt=0)
    fanvueUserId: int = Field(gt=0)
    telegramUserId: int | None = Field(default=None, gt=0)
    conversationThreadId: int | None = Field(default=None, gt=0)
    commercialFoundationType: str = "PHOTOSHOOT"
    commercialFoundationReference: str | None = None
    objective: str | None = None
    commercialContext: dict[str, Any] = Field(default_factory=dict)
    actorType: str = "OPERATOR"
    actorIdentifier: str | None = None


class SalesSessionActionRequest(BaseModel):
    actorType: str = "OPERATOR"
    actorIdentifier: str | None = None
    reason: str | None = None


class AdvanceSalesSessionRequest(SalesSessionActionRequest):
    state: str
    progressionStage: str | None = None


class ProgressSalesSessionRequest(SalesSessionActionRequest):
    progressionStage: str


class AssociatePurchaseIntentRequest(SalesSessionActionRequest):
    purchaseIntentId: UUID


class CompleteSalesSessionRequest(SalesSessionActionRequest):
    withPurchase: bool = False


def _service() -> SalesSessionService:
    return SalesSessionService()


def _creator_id() -> int:
    return int(_creator_profile()["id"])


def _session_payload(item) -> dict:
    return {
        "salesSessionId": str(item.sales_session_id),
        "creatorProfileId": item.creator_profile_id,
        "fanvueAccountId": item.fanvue_account_id,
        "fanvueUserId": item.fanvue_user_id,
        "externalFanvueUserUuid": str(item.external_fanvue_user_uuid),
        "telegramIdentityMappingId": item.telegram_identity_mapping_id,
        **(
            {"conversationThreadId": item.conversation_thread_id}
            if item.commercial_foundation_type.value == "CONVERSATION"
            else {}
        ),
        "commercialFoundationType": item.commercial_foundation_type,
        **(
            {"commercialFoundationReference": item.commercial_foundation_reference}
            if item.commercial_foundation_type.value == "PHOTOSHOOT"
            else {}
        ),
        "state": item.state.value,
        "progressionStage": item.progression_stage.value,
        "objective": item.objective,
        "commercialContext": dict(item.commercial_context),
        "outcome": item.outcome.value if item.outcome else None,
        "terminalReason": item.terminal_reason,
        "startedByType": item.started_by_type.value,
        "startedByIdentifier": item.started_by_identifier,
        "startedAt": item.started_at.isoformat() if item.started_at else None,
        "lastActivityAt": (
            item.last_activity_at.isoformat()
            if item.last_activity_at else None
        ),
        "endedAt": item.ended_at.isoformat() if item.ended_at else None,
        "createdAt": item.created_at.isoformat() if item.created_at else None,
        "updatedAt": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.post("")
def start_sales_session(request: StartSalesSessionRequest):
    return _execute(lambda: _session_payload(_service().start(
        creator_profile_id=_creator_id(),
        fanvue_account_id=request.fanvueAccountId,
        fanvue_user_id=request.fanvueUserId,
        telegram_user_id=request.telegramUserId,
        conversation_thread_id=request.conversationThreadId,
        commercial_foundation_type=request.commercialFoundationType,
        commercial_foundation_reference=request.commercialFoundationReference,
        objective=request.objective,
        commercial_context=request.commercialContext,
        actor_type=request.actorType,
        actor_identifier=request.actorIdentifier,
    )))


@router.get("")
def list_sales_sessions(limit: int = Query(100, ge=1, le=500)):
    return {
        "items": [
            _session_payload(item) for item in _service().list(
                creator_profile_id=_creator_id(), limit=limit
            )
        ]
    }


@router.get("/{session_id}")
def get_sales_session(session_id: UUID):
    return _execute(lambda: _session_payload(_service().get(
        session_id=session_id, creator_profile_id=_creator_id()
    )))


@router.get("/{session_id}/history")
def get_sales_session_history(session_id: UUID):
    def operation():
        values = _service().history(
            session_id=session_id, creator_profile_id=_creator_id()
        )
        return {"items": [{
            "historyId": item.history_id,
            "salesSessionId": str(item.sales_session_id),
            "eventType": item.event_type,
            "previousState": (
                item.previous_state.value if item.previous_state else None
            ),
            "newState": item.new_state.value,
            "previousProgressionStage": (
                item.previous_progression_stage.value
                if item.previous_progression_stage else None
            ),
            "newProgressionStage": item.new_progression_stage.value,
            "purchaseIntentId": (
                str(item.purchase_intent_id)
                if item.purchase_intent_id else None
            ),
            "actorType": item.actor_type.value,
            "actorIdentifier": item.actor_identifier,
            "reason": item.reason,
            "occurredAt": item.occurred_at.isoformat(),
        } for item in values]}
    return _execute(operation)


@router.get("/{session_id}/commercial-context")
def get_sales_session_commercial_context(session_id: UUID):
    def operation():
        value = _service().commercial_context(
            session_id=session_id, creator_profile_id=_creator_id()
        )
        customer = value["customer"]
        return {
            "salesSession": _session_payload(value["sales_session"]),
            "customerId": customer.customer_id if customer else None,
            "commercialGuidance": value["commercial_guidance"],
            "purchaseIntents": [{
                "purchaseIntentId": str(row["purchase_intent_id"]),
                "commercialOfferingId": str(row["commercial_offering_id"]),
                "sequenceIndex": int(row["sequence_index"]),
                "status": row["status"],
                "attributionResult": row["attribution_result"],
            } for row in value["purchase_intents"]],
        }
    return _execute(operation)


@router.post("/{session_id}/advance")
def advance_sales_session(
    session_id: UUID, request: AdvanceSalesSessionRequest,
):
    return _action(session_id, request, "advance")


@router.post("/{session_id}/progression")
def progress_sales_session(
    session_id: UUID, request: ProgressSalesSessionRequest,
):
    return _action(session_id, request, "progression")


@router.post("/{session_id}/purchase-intents")
def associate_purchase_intent(
    session_id: UUID, request: AssociatePurchaseIntentRequest,
):
    def operation():
        result = _service().associate_purchase_intent(
            session_id=session_id, creator_profile_id=_creator_id(),
            purchase_intent_id=request.purchaseIntentId,
            actor_type=request.actorType,
            actor_identifier=request.actorIdentifier,
            reason=request.reason,
        )
        return {
            "salesSessionId": str(result["session"].sales_session_id),
            "purchaseIntentId": str(
                result["purchase_intent"].purchase_intent_id
            ),
            "sequenceIndex": result["sequence"],
        }
    return _execute(operation)


@router.post("/{session_id}/complete")
def complete_sales_session(
    session_id: UUID, request: CompleteSalesSessionRequest,
):
    return _execute(lambda: _session_payload(_service().complete(
        session_id=session_id, creator_profile_id=_creator_id(),
        with_purchase=request.withPurchase,
        actor_type=request.actorType,
        actor_identifier=request.actorIdentifier, reason=request.reason,
    )))


@router.post("/{session_id}/expire")
def expire_sales_session(
    session_id: UUID, request: SalesSessionActionRequest,
):
    return _action(session_id, request, "expire")


@router.post("/{session_id}/abandon")
def abandon_sales_session(
    session_id: UUID, request: SalesSessionActionRequest,
):
    return _action(session_id, request, "abandon")


@router.post("/{session_id}/cancel")
def cancel_sales_session(
    session_id: UUID, request: SalesSessionActionRequest,
):
    return _action(session_id, request, "cancel")


def _action(session_id, request, action):
    def operation():
        service = _service()
        common = {
            "session_id": session_id,
            "creator_profile_id": _creator_id(),
            "actor_type": request.actorType,
            "actor_identifier": request.actorIdentifier,
            "reason": request.reason,
        }
        if action == "advance":
            item = service.advance(
                **common, state=request.state,
                progression_stage=request.progressionStage,
            )
        elif action == "progression":
            item = service.set_progression(
                **common, progression_stage=request.progressionStage,
            )
        else:
            item = getattr(service, action)(**common)
        return _session_payload(item)
    return _execute(operation)


def _execute(operation):
    try:
        return operation()
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SalesSessionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
