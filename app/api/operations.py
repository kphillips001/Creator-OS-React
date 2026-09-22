"""Read-only operational evidence API."""

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.api.customers import _account_id
from app.services.operations_workspace_service import OperationsWorkspaceService
from app.services.module_switches_service import ModuleSwitchesService
from app.services.ava_bot_control_service import AvaBotControlService
from app.services.purchase_attribution_recovery_service import PurchaseAttributionRecoveryService
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.telegram_identity_service import (
    TelegramIdentityService,
    TelegramIdentityError,
)
from app.services.canonical_customer_identity_service import CanonicalCustomerIdentityService
from app.repositories.canonical_customer_identity_repository import CustomerIdentityConflictError
from app.services.canonical_relationship_fact_service import CanonicalRelationshipFactService, CanonicalRelationshipContextPreviewService
from app.services.customer_controls_inventory_service import CustomerControlsInventoryService
from app.services.customer_snapshot_service import CustomerSnapshotService
from app.services.natural_language_intelligence_service import NaturalLanguageIntelligenceService
from app.services.telegram_broadcast_observation_service import (
    TelegramBroadcastMemberLookupService, TelegramBroadcastObservationService)


router = APIRouter(prefix="/api/v1/operations", tags=["operations"])

@router.get('/customer-controls-inventory')
def customer_controls_inventory(search:str='',filter:str='ALL',sort:str='LATEST_ACTIVITY',page:int=1,page_size:int=100):
    try:return jsonable_encoder(CustomerControlsInventoryService().list(creator_profile_id=_creator_profile_id(),fanvue_account_id=_account_id(),search=search,filter=filter,sort=sort,page=page,page_size=min(max(page_size,1),100)))
    except ValueError as error:raise HTTPException(status_code=422,detail=str(error)) from error


def _workspace_service() -> OperationsWorkspaceService:
    return OperationsWorkspaceService()


def _module_switches_service() -> ModuleSwitchesService:
    return ModuleSwitchesService()


def _global_controls_service() -> AvaBotControlService:
    return AvaBotControlService()


class ModuleSwitchUpdate(BaseModel):
    value: bool | str


class GlobalPermissionUpdate(BaseModel):
    value: bool


class ManualAttributionRequest(BaseModel):
    purchaseIntentId: str
    operatorNote: str | None = None


class TelegramIdentityVerificationRequest(BaseModel):
    localFanvueUserId: int
    verificationNote: str

class BroadcastMemberObservationRequest(BaseModel):
    telegramUserId: int; channelId: int; username: str | None = None
    displayName: str | None = None; participantStatus: str | None = None


class XIdentityVerificationRequest(BaseModel):
    localFanvueUserId: int
    externalNumericId: str
    observedUsername: str | None = None
    observedDisplayName: str | None = None
    verificationNote: str


class IdentityDeactivationRequest(BaseModel):
    reason: str

class RelationshipFactRequest(BaseModel):
    subjectType: str; subjectId: int; relation: str; objectType: str; objectValue: str
    objectData: dict = Field(default_factory=dict); attributes: dict = Field(default_factory=dict); category: str; sourcePlatform: str
    sourceType: str; sourceReference: dict = Field(default_factory=dict); verificationMethod: str
    confidence: float; usagePolicy: str; observedAt: str | None = None; idempotencyKey: str

class RelationshipFactCorrectionRequest(BaseModel):
    replacement: RelationshipFactRequest; reason: str

class NaturalLanguageIntelligencePreviewRequest(BaseModel):
    customerId: int; customerName: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2000)
    sourceType: str = "OPERATOR_VERIFIED"

class NaturalLanguageIntelligenceApplyRequest(NaturalLanguageIntelligencePreviewRequest):
    selectedProposalIds: list[str] = Field(min_length=1, max_length=10)
    silentProposalIds: list[str] = Field(default_factory=list, max_length=10)


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


@router.get("/schema-certification")
def operations_schema_certification():
    return jsonable_encoder(_workspace_service().schema_certification())


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


@router.get("/global-controls")
def read_global_controls():
    return jsonable_encoder(
        _global_controls_service().read(creator_profile_id=_account_id())
    )


@router.get("/global-controls/display-status")
def read_global_controls_display_status():
    """Non-authorizing projection for fast dashboard display only."""
    return jsonable_encoder(
        _global_controls_service().read_display(creator_profile_id=_account_id())
    )


@router.post("/global-controls/ava-bot/turn-on")
def turn_ava_bot_on():
    try:
        result = _global_controls_service().turn_on(
            creator_profile_id=_account_id())
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return jsonable_encoder(result)


@router.post("/global-controls/ava-bot/turn-off")
def turn_ava_bot_off():
    try:
        result = _global_controls_service().turn_off(
            creator_profile_id=_account_id())
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return jsonable_encoder(result)


@router.patch("/global-controls/content-selling")
def set_global_content_selling(payload: GlobalPermissionUpdate):
    return jsonable_encoder(_global_controls_service().set_content_selling(
        payload.value, creator_profile_id=_account_id()))


@router.patch("/global-controls/session-selling")
def set_global_session_selling(payload: GlobalPermissionUpdate):
    return jsonable_encoder(_global_controls_service().set_session_selling(
        payload.value, creator_profile_id=_account_id()))


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

@router.post("/telegram-identity-readiness/{telegram_user_id}/preview")
def preview_telegram_identity(telegram_user_id:int,payload:TelegramIdentityVerificationRequest):
    try:return jsonable_encoder(TelegramIdentityService().preview_operator_mapping(
        telegram_user_id=telegram_user_id,fanvue_account_id=_account_id(),
        local_fanvue_user_id=payload.localFanvueUserId))
    except TelegramIdentityError as error:raise HTTPException(status_code=409,detail=str(error)) from error

@router.get('/telegram-identity/broadcast-members')
async def find_broadcast_members(search:str,limit:int=20):
    import os
    from telethon import TelegramClient
    channel_id=int(os.environ.get('TELEGRAM_CHANNEL_ID') or 0)
    if not channel_id:raise HTTPException(status_code=409,detail='Broadcast channel is not configured.')
    client=TelegramClient(os.environ.get('TG_SESSION_PATH','tg_sessions/ava'),int(os.environ['TG_API_ID']),os.environ['TG_API_HASH'])
    try:
        await client.connect()
        if not await client.is_user_authorized():raise HTTPException(status_code=409,detail='Ava Telethon session is not authorized.')
        rows=await TelegramBroadcastMemberLookupService(client).lookup(channel_id=channel_id,search=search,limit=limit)
        return jsonable_encoder({'channelId':channel_id,'items':[{'telegramUserId':row.telegram_user_id,
            'username':row.username,'firstName':row.first_name,'lastName':row.last_name,
            'displayName':row.display_name,'participantStatus':row.participant_status,
            'channelId':channel_id} for row in rows],
            'mutationPerformed':False})
    finally:await client.disconnect()

@router.post('/telegram-identity/broadcast-observations')
def persist_broadcast_observation(payload:BroadcastMemberObservationRequest):
    import os
    configured=int(os.environ.get('TELEGRAM_CHANNEL_ID') or 0)
    if payload.channelId!=configured:raise HTTPException(status_code=409,detail='Observation channel does not match Ava Broadcast.')
    try:return jsonable_encoder(TelegramBroadcastObservationService().persist(
        telegram_user_id=payload.telegramUserId,source_channel_id=payload.channelId,
        username=payload.username,display_name=payload.displayName,
        participant_status=payload.participantStatus))
    except ValueError as error:raise HTTPException(status_code=422,detail=str(error)) from error


@router.get("/customer-identity/reconciliation-preview")
def canonical_customer_reconciliation_preview():
    return CanonicalCustomerIdentityService().reconciliation_preview(
        creator_profile_id=_creator_profile_id())

@router.get('/customer-identity/fanvue/{local_user_id}/metadata-enrichment-preview')
def preview_fanvue_metadata(local_user_id:int):
    try:return jsonable_encoder(CanonicalCustomerIdentityService().metadata_enrichment_preview(fanvue_account_id=_account_id(),local_fanvue_user_id=local_user_id))
    except LookupError as error:raise HTTPException(status_code=404,detail=str(error)) from error

@router.post('/customer-identity/fanvue/{local_user_id}/metadata-enrichment')
def apply_fanvue_metadata(local_user_id:int):
    try:return jsonable_encoder(CanonicalCustomerIdentityService().apply_metadata_enrichment(fanvue_account_id=_account_id(),local_fanvue_user_id=local_user_id))
    except (LookupError,CustomerIdentityConflictError) as error:raise HTTPException(status_code=409,detail=str(error)) from error


@router.post("/customer-identity/x/preview")
def preview_x_identity(payload: XIdentityVerificationRequest):
    try:
        return CanonicalCustomerIdentityService().preview_x_link(
            creator_profile_id=_creator_profile_id(),
            local_fanvue_user_id=payload.localFanvueUserId,
            external_numeric_id=payload.externalNumericId)
    except (ValueError,LookupError) as error:
        raise HTTPException(status_code=409,detail=str(error)) from error


@router.get("/customer-identity/x/observations")
def list_observed_x_identities():
    return jsonable_encoder(CanonicalCustomerIdentityService().observed_x_identities(
        creator_profile_id=_creator_profile_id()))


@router.post("/customer-identity/x/verify")
def verify_x_identity(payload: XIdentityVerificationRequest):
    try:
        row,replay=CanonicalCustomerIdentityService().verify_x_link(
            creator_profile_id=_creator_profile_id(),fanvue_account_id=_account_id(),
            local_fanvue_user_id=payload.localFanvueUserId,
            external_numeric_id=payload.externalNumericId,
            username=payload.observedUsername,display_name=payload.observedDisplayName,
            evidence_reason=payload.verificationNote)
    except (ValueError,LookupError,CustomerIdentityConflictError) as error:
        raise HTTPException(status_code=409,detail=str(error)) from error
    return jsonable_encoder({"success":True,"idempotentReplay":replay,"link":row})


@router.post("/customer-identity/x/{link_id}/deactivate")
def deactivate_x_identity(link_id: str, payload: IdentityDeactivationRequest):
    try: return jsonable_encoder(CanonicalCustomerIdentityService().deactivate(link_id=link_id,reason=payload.reason))
    except (ValueError,LookupError) as error: raise HTTPException(status_code=409,detail=str(error)) from error

def _fact_values(payload):
    return dict(creator_profile_id=_creator_profile_id(),fanvue_account_id=_account_id(),
        subject_type=payload.subjectType,subject_id=payload.subjectId,relation=payload.relation,
        object_type=payload.objectType,object_value=payload.objectValue,object_data=payload.objectData,
        attributes=payload.attributes,category=payload.category,source_platform=payload.sourcePlatform,
        source_type=payload.sourceType,source_reference=payload.sourceReference,
        verification_method=payload.verificationMethod,confidence=payload.confidence,
        usage_policy=payload.usagePolicy,observed_at=payload.observedAt,idempotency_key=payload.idempotencyKey)

@router.post('/relationship-facts/preview')
def preview_relationship_fact(payload:RelationshipFactRequest):
    try:return jsonable_encoder(CanonicalRelationshipFactService().preview_create(**_fact_values(payload)))
    except ValueError as error:raise HTTPException(status_code=409,detail=str(error)) from error

@router.post('/relationship-facts')
def create_relationship_fact(payload:RelationshipFactRequest):
    try:row,replay=CanonicalRelationshipFactService().create_verified(**_fact_values(payload));return jsonable_encoder({'fact':row,'idempotentReplay':replay})
    except ValueError as error:raise HTTPException(status_code=409,detail=str(error)) from error

@router.get('/relationship-facts')
def list_relationship_facts(customer_id:int|None=None):return jsonable_encoder(CanonicalRelationshipFactService().list_facts(creator_profile_id=_creator_profile_id(),fanvue_account_id=_account_id(),customer_id=customer_id))

@router.get('/relationship-facts/{fact_id}/history')
def relationship_fact_history(fact_id:str):
    try:return jsonable_encoder(CanonicalRelationshipFactService().history(fact_id=fact_id,creator_profile_id=_creator_profile_id(),fanvue_account_id=_account_id()))
    except LookupError as error:raise HTTPException(status_code=404,detail=str(error)) from error

@router.post('/relationship-facts/{fact_id}/correct')
def correct_relationship_fact(fact_id:str,payload:RelationshipFactCorrectionRequest):
    try:return jsonable_encoder(CanonicalRelationshipFactService().correct(fact_id=fact_id,replacement=_fact_values(payload.replacement),reason=payload.reason))
    except (ValueError,LookupError) as error:raise HTTPException(status_code=409,detail=str(error)) from error

@router.post('/relationship-facts/{fact_id}/deactivate')
def deactivate_relationship_fact(fact_id:str,payload:IdentityDeactivationRequest):
    try:return jsonable_encoder(CanonicalRelationshipFactService().deactivate(fact_id=fact_id,reason=payload.reason))
    except (ValueError,LookupError) as error:raise HTTPException(status_code=409,detail=str(error)) from error

@router.get('/relationship-context-preview')
def relationship_context_preview(customer_id:int,message:str=''):
    return jsonable_encoder(CanonicalRelationshipContextPreviewService().preview(creator_profile_id=_creator_profile_id(),fanvue_account_id=_account_id(),customer_id=customer_id,message=message))

@router.get('/customer-snapshot')
def customer_snapshot(customer_id:int|None=None,telegram_user_id:int|None=None):
    if (customer_id is None)==(telegram_user_id is None):
        raise HTTPException(status_code=422,detail='Provide exactly one stable customer or Telegram prospect key.')
    service=CustomerSnapshotService()
    try:
        result=(service.for_customer(creator_profile_id=_creator_profile_id(),fanvue_account_id=_account_id(),customer_id=customer_id)
                if customer_id is not None else
                service.for_prospect(creator_profile_id=_creator_profile_id(),fanvue_account_id=_account_id(),telegram_user_id=telegram_user_id))
    except LookupError as error:raise HTTPException(status_code=404,detail=str(error)) from error
    except ValueError as error:raise HTTPException(status_code=409,detail=str(error)) from error
    return jsonable_encoder(result)

@router.post('/intelligence/natural-language/preview')
def preview_natural_language_intelligence(payload:NaturalLanguageIntelligencePreviewRequest):
    try:return jsonable_encoder(NaturalLanguageIntelligenceService().preview(
        creator_profile_id=_creator_profile_id(),fanvue_account_id=_account_id(),
        customer_id=payload.customerId,customer_name=payload.customerName,
        text=payload.text,source_type=payload.sourceType))
    except (ValueError,LookupError) as error:raise HTTPException(status_code=409,detail=str(error)) from error

@router.post('/intelligence/natural-language/apply')
def apply_natural_language_intelligence(payload:NaturalLanguageIntelligenceApplyRequest):
    try:return jsonable_encoder(NaturalLanguageIntelligenceService().apply(
        creator_profile_id=_creator_profile_id(),fanvue_account_id=_account_id(),
        customer_id=payload.customerId,customer_name=payload.customerName,text=payload.text,
        selected_proposal_ids=payload.selectedProposalIds,
        silent_proposal_ids=payload.silentProposalIds,source_type=payload.sourceType))
    except (ValueError,LookupError) as error:raise HTTPException(status_code=409,detail=str(error)) from error
