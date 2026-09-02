"""Read-only operational evidence API."""

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.api.customers import _account_id
from app.services.operations_workspace_service import OperationsWorkspaceService
from app.services.module_switches_service import ModuleSwitchesService
from app.services.purchase_attribution_recovery_service import PurchaseAttributionRecoveryService
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.telegram_identity_service import (
    TelegramIdentityService,
    TelegramIdentityError,
)


router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


def _workspace_service() -> OperationsWorkspaceService:
    return OperationsWorkspaceService()


def _module_switches_service() -> ModuleSwitchesService:
    return ModuleSwitchesService()


class ModuleSwitchUpdate(BaseModel):
    value: bool | str


class ManualAttributionRequest(BaseModel):
    purchaseIntentId: str
    operatorNote: str | None = None


class TelegramIdentityVerificationRequest(BaseModel):
    localFanvueUserId: int
    verificationNote: str


def _creator_profile_id() -> int:
    account_id = _account_id()
    creator = get_active_creator_profile(str(account_id)) or {}
    creator_id = int(creator.get("id") or 0)
    if creator_id <= 0:
        raise HTTPException(status_code=404, detail="Active creator profile was not found.")
    return creator_id


@router.get("/overview")
def operations_overview():
    return jsonable_encoder(_workspace_service().overview(account_id=_account_id()))


@router.get("/runtime")
def operations_runtime():
    return jsonable_encoder(_workspace_service().runtime(account_id=_account_id()))


@router.get("/workers")
def operations_workers():
    return jsonable_encoder(_workspace_service().workers(account_id=_account_id()))


@router.get("/queues")
def operations_queues():
    return jsonable_encoder(_workspace_service().queues(account_id=_account_id()))


@router.get("/publishing")
def operations_publishing():
    return jsonable_encoder(_workspace_service().publishing(account_id=_account_id()))


@router.get("/failures")
def operations_failures():
    return jsonable_encoder(_workspace_service().failures(account_id=_account_id()))


@router.get("/module-switches")
def operations_module_switches():
    return jsonable_encoder(_module_switches_service().read(creator_profile_id=_account_id()))


@router.patch("/module-switches/{module}")
def update_operations_module_switch(module: str, payload: ModuleSwitchUpdate):
    try:
        result = _module_switches_service().update(module, payload.value, creator_profile_id=_account_id())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return jsonable_encoder(result)


@router.get("/purchase-recovery")
def unresolved_purchase_recovery():
    return jsonable_encoder(PurchaseAttributionRecoveryService().queue(
        creator_profile_id=_creator_profile_id()
    ))


@router.get("/purchase-recovery/{reconciliation_id}")
def unresolved_purchase_detail(reconciliation_id: str):
    try:
        result = PurchaseAttributionRecoveryService().detail(
            creator_profile_id=_creator_profile_id(),
            reconciliation_id=reconciliation_id,
        )
    except (ValueError, LookupError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return jsonable_encoder(result)


@router.post("/purchase-recovery/{reconciliation_id}/attribute")
def manually_attribute_purchase(
    reconciliation_id: str, payload: ManualAttributionRequest,
):
    try:
        result = PurchaseAttributionRecoveryService().attribute(
            creator_profile_id=_creator_profile_id(),
            reconciliation_id=reconciliation_id,
            purchase_intent_id=payload.purchaseIntentId,
            operator_note=payload.operatorNote,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return jsonable_encoder(result)


@router.get("/telegram-identity-readiness")
def telegram_identity_readiness():
    return jsonable_encoder(
        TelegramIdentityService().readiness(fanvue_account_id=_account_id())
    )


@router.post("/telegram-identity-readiness/{telegram_user_id}/verify")
def verify_telegram_identity(
    telegram_user_id: int, payload: TelegramIdentityVerificationRequest,
):
    try:
        mapping, idempotent = TelegramIdentityService().verify_operator_mapping(
            telegram_user_id=telegram_user_id,
            fanvue_account_id=_account_id(),
            local_fanvue_user_id=payload.localFanvueUserId,
            verification_note=payload.verificationNote,
        )
    except TelegramIdentityError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return jsonable_encoder({
        "success": True,
        "idempotentReplay": idempotent,
        "mappingId": mapping.id,
        "status": mapping.verification_status,
    })
