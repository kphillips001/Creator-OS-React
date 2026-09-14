from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from uuid import UUID

from app.api.developer_authorization import require_developer_authorization
from app.api.creator_intelligence import _snapshot_scope
from app.services.relationships_service import RelationshipFilter, RelationshipSort, RelationshipsService

router=APIRouter(prefix="/api/v1/relationships",tags=["relationships"])

class ControlChange(BaseModel):
    reason: str | None = Field(default=None,max_length=500)

class IgnoreChange(ControlChange):
    expectedControlVersion: int = Field(ge=0)

class CustomerPermissionChange(BaseModel):
    value: bool
    reason: str | None = Field(default=None,max_length=500)

class RelationshipValueChange(BaseModel):
    classification: str
    reason: str | None = Field(default=None,max_length=500)

class RelationshipMarketTierChange(BaseModel):
    marketTier: Literal["HIGH", "MEDIUM", "LOW"]
    reason: str | None = Field(default=None,max_length=500)

class ResolutionReview(BaseModel):
    """Approval identity is derived from the authenticated operator boundary."""
    pass

class ConversationAnalysisCreate(BaseModel):
    targetType: Literal["CONVERSATION", "TURN"] = "CONVERSATION"
    targetMessageReference: str | None = Field(default=None,max_length=200)

class ConversationRepairPlanCreate(BaseModel):
    findingId: str = Field(min_length=1,max_length=100)

class ProposalReview(BaseModel):
    """Operator identity and every frozen field are server-owned."""
    model_config = ConfigDict(extra="forbid")

class RepairExecutionCreate(BaseModel):
    authorizationId: UUID
    model_config = ConfigDict(extra="forbid")

class InterruptedGenerationRecovery(BaseModel):
    operationId: UUID
    idempotencyKey: str = Field(min_length=8,max_length=200)

class OperatorMessage(BaseModel):
    text: str = Field(min_length=1,max_length=4096)
    idempotencyKey: str = Field(min_length=8,max_length=200)
    expectedControlVersion: int = Field(ge=0)

class ManualOfferPrepare(BaseModel):
    offeringId: str
    expectedControlVersion: int = Field(ge=0)
    businessConnectionId: str = Field(min_length=1,max_length=200)

class ManualOfferSend(ManualOfferPrepare):
    text: str = Field(min_length=1,max_length=4096)
    idempotencyKey: str = Field(min_length=8,max_length=200)

def _relationship_scope(projection_key):
    creator,account=_snapshot_scope()
    try:
        prefix,expected_creator,expected_account,user_id=projection_key.split(":",3)
        if prefix!="telegram" or int(expected_creator)!=creator or int(expected_account)!=account: raise ValueError
        context=RelationshipsService().control_context(creator_profile_id=creator,
            fanvue_account_id=account,telegram_user_id=int(user_id))
    except (ValueError,LookupError): raise HTTPException(status_code=404,detail="Relationship not found.")
    return creator,account,int(user_id),context

def _control_response(control,context):
    return {"mode":control.mode.value,"controlVersion":control.control_version,
            "avaChatEnabled":control.mode.value=="AVA_AUTO",
            "contentSellingEnabled":control.content_selling_enabled,
            "sessionSellingEnabled":control.session_selling_enabled,
            "communicationDisposition":getattr(
                getattr(control,"communication_disposition","ACTIVE"),"value","ACTIVE"),
            "ignored":bool(getattr(control,"ignored",False)),
            "ignoreVersion":getattr(control,"ignore_version",0),
            "ignoredAt":getattr(control,"ignored_at",None),
            "ignoredBy":getattr(control,"ignored_by",None),
            "unignoredAt":getattr(control,"unignored_at",None),
            "unignoredBy":getattr(control,"unignored_by",None),
            "resumeAfterInboundMessageId":getattr(control,"resume_after_inbound_message_id",None),
            "changedAt":control.changed_at,"changedBy":control.changed_by,
            "reason":control.reason,"lastManualActivityAt":control.last_manual_activity_at,
            "activePurchaseIntent":bool(context.get("active_purchase_intent")),
            "activeSalesSession":bool(context.get("active_sales_session"))}

@router.get("")
def relationships(search:str="",sort:RelationshipSort=RelationshipSort.LATEST_ACTIVITY,
                  filter:RelationshipFilter=RelationshipFilter.ALL,
                  cursor:str|None=None,limit:int=Query(50,ge=1,le=100)):
    creator,account=_snapshot_scope()
    try: result=RelationshipsService().list(creator_profile_id=creator,fanvue_account_id=account,search=search,sort=sort,filter=filter,cursor=cursor,limit=limit)
    except ValueError as error: raise HTTPException(status_code=400,detail=str(error)) from error
    return jsonable_encoder(result)

@router.get("/{projection_key}/messages")
def relationship_messages(projection_key:str,cursor:str|None=None,limit:int=Query(50,ge=1,le=100)):
    creator,account=_snapshot_scope()
    try:
        prefix,expected_creator,expected_account,user_id=projection_key.split(":",3)
        if prefix!="telegram" or int(expected_creator)!=creator or int(expected_account)!=account: raise ValueError
        result=RelationshipsService().messages(creator_profile_id=creator,fanvue_account_id=account,
            telegram_user_id=int(user_id),cursor=cursor,limit=limit)
    except (ValueError,LookupError): raise HTTPException(status_code=404,detail="Relationship not found.")
    return jsonable_encoder(result)

@router.get("/{projection_key}/intelligence")
def relationship_intelligence(projection_key: str):
    creator, account = _snapshot_scope()
    try:
        prefix, expected_creator, expected_account, user_id = projection_key.split(":", 3)
        if prefix != "telegram" or int(expected_creator) != creator or int(expected_account) != account:
            raise ValueError
        result = RelationshipsService().intelligence(
            creator_profile_id=creator, fanvue_account_id=account,
            telegram_user_id=int(user_id))
    except (ValueError, LookupError):
        raise HTTPException(status_code=404, detail="Relationship not found.")
    return jsonable_encoder(result)

def _value_override_response(projection_key, mutation):
    creator,account,user_id,_context=_relationship_scope(projection_key)
    intelligence=RelationshipsService().intelligence(
        creator_profile_id=creator,fanvue_account_id=account,
        telegram_user_id=user_id)
    return jsonable_encoder({"intelligence":intelligence,"scheduling":{
        "scheduleAdvanced":mutation["scheduleAdvanced"],
        "advancedOperation":mutation["advancedOperation"]}})

@router.put("/{projection_key}/operator-classification",
            dependencies=[Depends(require_developer_authorization)])
def set_relationship_operator_classification(projection_key:str,
                                               body:RelationshipValueChange):
    from app.services.relationship_value_override_service import RelationshipValueOverrideService
    creator,account,user_id,context=_relationship_scope(projection_key)
    try:
        result=RelationshipValueOverrideService().set(
            creator_profile_id=creator,fanvue_account_id=account,
            telegram_user_id=user_id,telegram_chat_id=context["telegram_chat_id"],
            classification=body.classification,changed_by="CREATOR_OS_OPERATOR",
            reason=body.reason)
    except ValueError as error:
        raise HTTPException(status_code=422,detail=str(error)) from error
    return _value_override_response(projection_key,result)

@router.delete("/{projection_key}/operator-classification",
               dependencies=[Depends(require_developer_authorization)])
def remove_relationship_operator_classification(projection_key:str):
    from app.services.relationship_value_override_service import RelationshipValueOverrideService
    creator,account,user_id,context=_relationship_scope(projection_key)
    result=RelationshipValueOverrideService().remove(
        creator_profile_id=creator,fanvue_account_id=account,
        telegram_user_id=user_id,telegram_chat_id=context["telegram_chat_id"],
        removed_by="CREATOR_OS_OPERATOR")
    return _value_override_response(projection_key,result)

def _market_tier_context(projection_key):
    from app.services.relationship_market_tier_service import RelationshipMarketTierService
    from app.services.relationship_value_override_service import RelationshipValueOverrideService
    creator,account,user_id,context=_relationship_scope(projection_key)
    scope={"creator_profile_id":creator,"fanvue_account_id":account,
           "telegram_user_id":user_id,"telegram_chat_id":context["telegram_chat_id"]}
    intelligence=RelationshipsService().intelligence(
        creator_profile_id=creator,fanvue_account_id=account,
        telegram_user_id=user_id)
    value=intelligence["customerValue"]
    verified_buyer=bool(intelligence["mappingStatus"]=="VERIFIED"
        and value.get("buyerStatus")=="VERIFIED_BUYER"
        and int(value.get("purchaseCount") or 0)>0)
    high_value=bool(RelationshipValueOverrideService().active(**scope))
    return RelationshipMarketTierService(),scope,high_value,verified_buyer

def _market_tier_response(service,scope,high_value,buyer,result=None):
    from app.repositories.market_tier_resource_gate_repository import MarketTierResourceGateRepository
    from app.services.market_tier_reply_accounting_service import MarketTierReplyAccountingService
    projection=result or service.read(
        **scope,high_value_prospect=high_value,verified_buyer=buyer)
    accounting=MarketTierReplyAccountingService()
    usage=accounting.today(**scope)
    tier=projection["marketTier"]
    budget=None
    if tier=="LOW":
        budget=2
    elif tier=="MEDIUM":
        business_date=usage["business_day_start"].astimezone(accounting.ZONE).date()
        persisted=MarketTierResourceGateRepository().read_medium_budget(
            **scope,business_date=business_date)
        budget=int(persisted["daily_reply_budget"]) if persisted else None
    exhausted=bool(budget is not None and usage["replies_used_today"]>=budget)
    return {**projection,
        "repliesUsedToday":int(usage["replies_used_today"]),
        "dailyReplyBudget":"FULL" if tier=="HIGH" else budget,
        "budgetStatus":"EXHAUSTED" if exhausted else "AVAILABLE",
        "nextBudgetResetAt":usage["next_reset_at"],
        "prospectReplyLimit":"NOT_APPLICABLE" if buyer else None}

@router.get("/{projection_key}/market-tier",
            dependencies=[Depends(require_developer_authorization)])
def relationship_market_tier(projection_key:str):
    service,scope,high_value,buyer=_market_tier_context(projection_key)
    return jsonable_encoder(_market_tier_response(service,scope,high_value,buyer))

@router.put("/{projection_key}/market-tier",
            dependencies=[Depends(require_developer_authorization)])
def set_relationship_market_tier(projection_key:str,
                                 body:RelationshipMarketTierChange):
    service,scope,high_value,buyer=_market_tier_context(projection_key)
    try:
        result=service.set(**scope,market_tier=body.marketTier,
            changed_by="CREATOR_OS_OPERATOR",reason=body.reason,
            high_value_prospect=high_value,verified_buyer=buyer)
    except ValueError as error:
        raise HTTPException(status_code=422,detail=str(error)) from error
    return jsonable_encoder(_market_tier_response(
        service,scope,high_value,buyer,result))

@router.delete("/{projection_key}/market-tier",
               dependencies=[Depends(require_developer_authorization)])
def remove_relationship_market_tier(projection_key:str):
    service,scope,high_value,buyer=_market_tier_context(projection_key)
    result=service.remove(**scope,removed_by="CREATOR_OS_OPERATOR",
        high_value_prospect=high_value,verified_buyer=buyer)
    return jsonable_encoder(_market_tier_response(
        service,scope,high_value,buyer,result))

@router.post("/{projection_key}/recovery/interrupted-generation",
             dependencies=[Depends(require_developer_authorization)])
def recover_interrupted_generation(projection_key:str,
                                   body:InterruptedGenerationRecovery):
    from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
    from app.services.customer_effective_permissions_service import CustomerEffectivePermissionsService
    creator,account,user_id,context=_relationship_scope(projection_key)
    scope={"creator_profile_id":creator,"fanvue_account_id":account,
           "telegram_user_id":user_id,"telegram_chat_id":context["telegram_chat_id"]}
    permissions=CustomerEffectivePermissionsService().read(**scope)
    if not permissions["effective"]["chatAllowed"]:
        raise HTTPException(status_code=409,detail="Ava Auto chat permission is not enabled.")
    operation=OrdinaryChatReplyRepository().requeue_interrupted_generation(
        **scope,operation_id=body.operationId,approved_by="CREATOR_OS_OPERATOR",
        idempotency_key=body.idempotencyKey)
    if operation is None:
        raise HTTPException(status_code=409,detail="Interrupted generation is no longer eligible for recovery.")
    return jsonable_encoder({"operationId":operation.operation_id,
        "state":operation.state.value,"nextRetryAt":operation.next_retry_at,
        "generationAttempts":operation.generation_attempt_count,
        "sendAttempts":operation.send_attempt_count,
        "freshGenerationRequired":True})

@router.get("/{projection_key}/control")
def relationship_control(projection_key:str):
    from app.services.telegram_relationship_control_service import TelegramRelationshipControlService
    creator,account,user_id,context=_relationship_scope(projection_key)
    control=TelegramRelationshipControlService().get(creator_profile_id=creator,
        fanvue_account_id=account,telegram_user_id=user_id,
        telegram_chat_id=context["telegram_chat_id"])
    return jsonable_encoder(_control_response(control,context))

@router.post("/{projection_key}/attention/{occurrence_id}/acknowledge")
def acknowledge_relationship_attention(projection_key: str, occurrence_id: str):
    creator,account,user_id,_context=_relationship_scope(projection_key)
    try:
        result=RelationshipsService().acknowledge_attention(
            creator_profile_id=creator,fanvue_account_id=account,
            telegram_user_id=user_id,occurrence_id=occurrence_id,
            acknowledged_by="CREATOR_OS_OPERATOR")
    except ValueError as error:
        raise HTTPException(status_code=409,detail=str(error)) from error
    return jsonable_encoder(result)

def _resolution_service():
    from app.services.conversation_attention_resolution_service import (
        ConversationAttentionResolutionService,
    )
    return ConversationAttentionResolutionService()

@router.post("/{projection_key}/attention/{occurrence_id}/inspect",
             dependencies=[Depends(require_developer_authorization)])
def inspect_relationship_attention(projection_key: str, occurrence_id: str,
        inspection_request_id: UUID | None = Header(
            default=None,alias="X-Creator-OS-Inspection-Key")):
    creator,account,user_id,_context=_relationship_scope(projection_key)
    try:
        return jsonable_encoder(_resolution_service().inspect(
            creator_profile_id=creator,fanvue_account_id=account,
            telegram_user_id=user_id,relationship_key=projection_key,
            occurrence_id=occurrence_id,request_id=inspection_request_id))
    except LookupError as error:
        raise HTTPException(status_code=404,detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403,detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409,detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503,detail=str(error)) from error

@router.get("/{projection_key}/attention/inspections/{inspection_id}",
            dependencies=[Depends(require_developer_authorization)])
def get_attention_inspection(projection_key: str, inspection_id: UUID):
    from app.repositories.conversation_attention_resolution_repository import (
        ConversationAttentionResolutionRepository,
    )
    creator,account,_user,_context=_relationship_scope(projection_key)
    item=ConversationAttentionResolutionRepository().get_inspection(
        inspection_id,creator_profile_id=creator,fanvue_account_id=account)
    if not item or item["relationship_key"] != projection_key:
        raise HTTPException(status_code=404,detail="Inspection was not found.")
    return jsonable_encoder(item)

@router.get("/{projection_key}/attention/inspections/{inspection_id}/similar",
            dependencies=[Depends(require_developer_authorization)])
def get_attention_similar_cases(projection_key: str, inspection_id: UUID):
    from app.repositories.conversation_attention_resolution_repository import (
        ConversationAttentionResolutionRepository,
    )
    creator,account,_user,_context=_relationship_scope(projection_key)
    repository=ConversationAttentionResolutionRepository()
    item=repository.get_inspection(inspection_id,creator_profile_id=creator,
                                   fanvue_account_id=account)
    if not item or item["relationship_key"] != projection_key:
        raise HTTPException(status_code=404,detail="Inspection was not found.")
    result=item["validated_result"]
    return {"items":result.get("similarCurrentCases",[]) if isinstance(result,dict) else []}

@router.get("/{projection_key}/attention/plans/{plan_id}",
            dependencies=[Depends(require_developer_authorization)])
def get_attention_resolution_plan(projection_key: str, plan_id: UUID):
    from app.repositories.conversation_attention_resolution_repository import (
        ConversationAttentionResolutionRepository,
    )
    creator,account,_user,_context=_relationship_scope(projection_key)
    item=ConversationAttentionResolutionRepository().get_plan(
        plan_id,creator_profile_id=creator,fanvue_account_id=account)
    if not item or item["relationship_key"] != projection_key:
        raise HTTPException(status_code=404,detail="Resolution plan was not found.")
    return jsonable_encoder(item)

def _plan_command(projection_key,plan_id,body,command):
    from app.repositories.conversation_attention_resolution_repository import (
        ConversationAttentionResolutionRepository,
    )
    creator,account,_user,_context=_relationship_scope(projection_key)
    try:
        persisted=ConversationAttentionResolutionRepository().get_plan(
            plan_id,creator_profile_id=creator,fanvue_account_id=account)
        if not persisted or persisted["relationship_key"] != projection_key:
            raise LookupError("Resolution plan was not found.")
        service=_resolution_service()
        action=getattr(service,command)
        result=action(plan_id,creator_profile_id=creator,fanvue_account_id=account,
                      operator="CREATOR_OS_OPERATOR")
        return jsonable_encoder(result)
    except LookupError as error:
        raise HTTPException(status_code=404,detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403,detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409,detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409,detail=str(error)) from error

@router.post("/{projection_key}/attention/plans/{plan_id}/approve",
             dependencies=[Depends(require_developer_authorization)])
def approve_attention_resolution_plan(projection_key: str, plan_id: UUID,
                                      body: ResolutionReview):
    return _plan_command(projection_key,plan_id,body,"approve")

@router.post("/{projection_key}/attention/plans/{plan_id}/reject",
             dependencies=[Depends(require_developer_authorization)])
def reject_attention_resolution_plan(projection_key: str, plan_id: UUID,
                                     body: ResolutionReview):
    return _plan_command(projection_key,plan_id,body,"reject")

@router.post("/{projection_key}/attention/plans/{plan_id}/execute",
             dependencies=[Depends(require_developer_authorization)])
def execute_attention_resolution_plan(projection_key: str, plan_id: UUID,
                                      body: ResolutionReview):
    return _plan_command(projection_key,plan_id,body,"execute")

@router.get("/{projection_key}/attention/executions/{execution_id}",
            dependencies=[Depends(require_developer_authorization)])
def get_attention_resolution_execution(projection_key: str, execution_id: UUID):
    from app.repositories.conversation_attention_resolution_repository import (
        ConversationAttentionResolutionRepository,
    )
    creator,account,_user,_context=_relationship_scope(projection_key)
    item=ConversationAttentionResolutionRepository().get_execution(
        execution_id,creator_profile_id=creator,fanvue_account_id=account)
    if not item:
        raise HTTPException(status_code=404,detail="Resolution execution was not found.")
    return jsonable_encoder(item)

def _customer_permissions_service():
    from app.services.customer_effective_permissions_service import (
        CustomerEffectivePermissionsService,
    )
    return CustomerEffectivePermissionsService()

def _permission_scope(projection_key):
    creator,account,user_id,context=_relationship_scope(projection_key)
    return creator,account,user_id,context,{
        "creator_profile_id":creator,"fanvue_account_id":account,
        "telegram_user_id":user_id,"telegram_chat_id":context["telegram_chat_id"],
        "telegram_identity_mapping_id":context.get("telegram_identity_mapping_id"),
        "local_fanvue_user_id":context.get("local_fanvue_user_id")}

@router.get("/{projection_key}/automation-controls")
def relationship_automation_controls(projection_key:str):
    creator,account,user_id,context,_scope=_permission_scope(projection_key)
    return jsonable_encoder(_customer_permissions_service().read(
        creator_profile_id=creator,fanvue_account_id=account,
        telegram_user_id=user_id,telegram_chat_id=context["telegram_chat_id"]))

def _patch_customer_permission(projection_key,body,control):
    _creator,_account,_user,_context,scope=_permission_scope(projection_key)
    service=_customer_permissions_service()
    action={"ava-chat":service.set_chat,"content-selling":service.set_content,
            "session-selling":service.set_session}[control]
    try:
        return jsonable_encoder(action(body.value,changed_by="CREATOR_OS_OPERATOR",
                                       reason=body.reason,**scope))
    except ValueError as error:
        raise HTTPException(status_code=422,detail=str(error)) from error

@router.patch("/{projection_key}/automation-controls/ava-chat")
def patch_relationship_ava_chat(projection_key:str,body:CustomerPermissionChange):
    return _patch_customer_permission(projection_key,body,"ava-chat")

@router.patch("/{projection_key}/automation-controls/content-selling")
def patch_relationship_content_selling(projection_key:str,body:CustomerPermissionChange):
    return _patch_customer_permission(projection_key,body,"content-selling")

@router.patch("/{projection_key}/automation-controls/session-selling")
def patch_relationship_session_selling(projection_key:str,body:CustomerPermissionChange):
    return _patch_customer_permission(projection_key,body,"session-selling")

@router.get("/{projection_key}/business-peer-evidence")
def relationship_business_peer_evidence(
    projection_key: str, businessConnectionId: str = Query(min_length=1,max_length=200),
):
    from app.services.telegram_business_peer_observation_service import (
        TelegramBusinessPeerObservationService,
    )
    _creator,_account,user_id,_context=_relationship_scope(projection_key)
    evidence=TelegramBusinessPeerObservationService().evidence(
        business_connection_id=businessConnectionId,
        telegram_peer_user_id=user_id,
    )
    if evidence is None:
        raise HTTPException(status_code=404,detail="Business connection not found.")
    return jsonable_encoder(evidence)

def _change_control(projection_key,body,manual):
    from app.services.telegram_relationship_control_service import TelegramRelationshipControlService
    creator,account,user_id,context=_relationship_scope(projection_key)
    service=TelegramRelationshipControlService()
    action=service.takeover if manual else service.return_to_ava
    control=action(creator_profile_id=creator,fanvue_account_id=account,
        telegram_user_id=user_id,telegram_chat_id=context["telegram_chat_id"],
        telegram_identity_mapping_id=context.get("telegram_identity_mapping_id"),
        local_fanvue_user_id=context.get("local_fanvue_user_id"),
        changed_by="CREATOR_OS_OPERATOR",reason=body.reason)
    return jsonable_encoder(_control_response(control,context))

@router.post("/{projection_key}/takeover")
def relationship_takeover(projection_key:str,body:ControlChange):
    return _change_control(projection_key,body,True)

@router.post("/{projection_key}/return-to-ava")
def relationship_return(projection_key:str,body:ControlChange):
    return _change_control(projection_key,body,False)

def _change_ignore(projection_key,body,ignored):
    from app.services.telegram_relationship_control_service import TelegramRelationshipControlService
    creator,account,user_id,context=_relationship_scope(projection_key)
    service=TelegramRelationshipControlService()
    action=service.ignore if ignored else service.unignore
    try:
        control,changed,neutralized=action(
            creator_profile_id=creator,fanvue_account_id=account,
            telegram_user_id=user_id,telegram_chat_id=context["telegram_chat_id"],
            telegram_identity_mapping_id=context.get("telegram_identity_mapping_id"),
            local_fanvue_user_id=context.get("local_fanvue_user_id"),
            expected_control_version=body.expectedControlVersion,
            changed_by="CREATOR_OS_OPERATOR",reason=body.reason)
    except ValueError as error:
        raise HTTPException(status_code=409,detail=str(error)) from error
    return jsonable_encoder({**_control_response(control,context),
                             "changed":changed,"neutralized":neutralized})

@router.put("/{projection_key}/ignore",
            dependencies=[Depends(require_developer_authorization)])
def relationship_ignore(projection_key:str,body:IgnoreChange):
    return _change_ignore(projection_key,body,True)

@router.delete("/{projection_key}/ignore",
               dependencies=[Depends(require_developer_authorization)])
def relationship_unignore(projection_key:str,body:IgnoreChange):
    return _change_ignore(projection_key,body,False)

def _conversation_analysis_scope(projection_key):
    creator,account,user_id,context=_relationship_scope(projection_key)
    return {"creator_profile_id":creator,"fanvue_account_id":account,
        "telegram_user_id":user_id,"telegram_chat_id":context["telegram_chat_id"],
        "relationship_key":projection_key}

@router.post("/{projection_key}/conversation-analyses",
             dependencies=[Depends(require_developer_authorization)])
def create_conversation_analysis(projection_key:str,body:ConversationAnalysisCreate):
    from app.services.conversation_analysis_service import ConversationAnalysisService
    scope=_conversation_analysis_scope(projection_key)
    try:
        result=ConversationAnalysisService().analyze(**scope,target_type=body.targetType,
            target_message_reference=body.targetMessageReference)
    except ValueError as error:
        raise HTTPException(status_code=422,detail=str(error)) from error
    return jsonable_encoder(result)

def _get_conversation_analysis(projection_key,analysis_id):
    from app.services.conversation_analysis_service import ConversationAnalysisService
    try:return ConversationAnalysisService().retrieve(analysis_id,**_conversation_analysis_scope(projection_key))
    except LookupError as error:raise HTTPException(status_code=404,detail=str(error)) from error

@router.get("/{projection_key}/conversation-analyses/{analysis_id}",
            dependencies=[Depends(require_developer_authorization)])
def get_conversation_analysis(projection_key:str,analysis_id:UUID):
    return jsonable_encoder(_get_conversation_analysis(projection_key,analysis_id))

@router.get("/{projection_key}/conversation-analyses/{analysis_id}/findings",
            dependencies=[Depends(require_developer_authorization)])
def get_conversation_analysis_findings(projection_key:str,analysis_id:UUID):
    result=_get_conversation_analysis(projection_key,analysis_id)
    return jsonable_encoder({"analysisId":result["analysisId"],"staleState":result["staleState"],
                             "findings":result["findings"]})

@router.get("/{projection_key}/conversation-analyses/{analysis_id}/similar-cases",
            dependencies=[Depends(require_developer_authorization)])
def get_conversation_analysis_similar(projection_key:str,analysis_id:UUID):
    result=_get_conversation_analysis(projection_key,analysis_id)
    return jsonable_encoder({"analysisId":result["analysisId"],"staleState":result["staleState"],
                             "similarCaseSummary":result["similarCaseSummary"]})

def _repair_planning():
    from app.services.conversation_repair_planning_service import ConversationRepairPlanningService
    return ConversationRepairPlanningService()

@router.post("/{projection_key}/conversation-analyses/{analysis_id}/repair-proposals",
             dependencies=[Depends(require_developer_authorization)])
def create_conversation_repair_proposal(projection_key:str,analysis_id:UUID,
                                        body:ConversationRepairPlanCreate):
    try:return jsonable_encoder(_repair_planning().plan(analysis_id,finding_id=body.findingId,
        operator="CREATOR_OS_OPERATOR",**_conversation_analysis_scope(projection_key)))
    except LookupError as error:raise HTTPException(status_code=404,detail=str(error)) from error
    except (RuntimeError,ValueError) as error:raise HTTPException(status_code=409,detail=str(error)) from error

@router.get("/{projection_key}/conversation-repair-proposals/{proposal_id}",
            dependencies=[Depends(require_developer_authorization)])
def get_conversation_repair_proposal(projection_key:str,proposal_id:UUID):
    try:return jsonable_encoder(_repair_planning().get(proposal_id,**_conversation_analysis_scope(projection_key)))
    except LookupError as error:raise HTTPException(status_code=404,detail=str(error)) from error

@router.post("/{projection_key}/conversation-repair-proposals/{proposal_id}/reject",
             dependencies=[Depends(require_developer_authorization)])
def reject_conversation_repair_proposal(projection_key:str,proposal_id:UUID,body:ProposalReview):
    try:return jsonable_encoder(_repair_planning().reject(proposal_id,operator="CREATOR_OS_OPERATOR",
        **_conversation_analysis_scope(projection_key)))
    except LookupError as error:raise HTTPException(status_code=404,detail=str(error)) from error
    except RuntimeError as error:raise HTTPException(status_code=409,detail=str(error)) from error

@router.post("/{projection_key}/conversation-repair-proposals/{proposal_id}/approve",
             dependencies=[Depends(require_developer_authorization)])
def approve_conversation_repair_proposal(projection_key:str,proposal_id:UUID,body:ProposalReview):
    try:return jsonable_encoder(_repair_planning().approve(proposal_id,operator="CREATOR_OS_OPERATOR",
        **_conversation_analysis_scope(projection_key)))
    except LookupError as error:raise HTTPException(status_code=404,detail=str(error)) from error
    except RuntimeError as error:raise HTTPException(status_code=409,detail=str(error)) from error

@router.get("/{projection_key}/conversation-repair-authorizations/{authorization_id}",
            dependencies=[Depends(require_developer_authorization)])
def get_conversation_repair_authorization(projection_key:str,authorization_id:UUID):
    try:return jsonable_encoder(_repair_planning().authorization(authorization_id,
        **_conversation_analysis_scope(projection_key)))
    except LookupError as error:raise HTTPException(status_code=404,detail=str(error)) from error

@router.post("/{projection_key}/conversation-repair-executions",
             dependencies=[Depends(require_developer_authorization)])
def execute_conversation_repair(projection_key:str,body:RepairExecutionCreate):
    from app.services.conversation_repair_execution_gate import (
        ConversationRepairExecutionDisabled,
        ConversationRepairExecutionGate,
    )
    try:
        ConversationRepairExecutionGate().require_enabled()
    except ConversationRepairExecutionDisabled as error:
        raise HTTPException(status_code=409,detail=str(error)) from error
    from app.services.conversation_repair_executor_service import ConversationRepairExecutorService
    try:return jsonable_encoder(ConversationRepairExecutorService().execute(body.authorizationId,
        operator="CREATOR_OS_DEVELOPER_AGENT",**_conversation_analysis_scope(projection_key)))
    except LookupError as error:raise HTTPException(status_code=404,detail=str(error)) from error
    except (PermissionError,RuntimeError) as error:raise HTTPException(status_code=409,detail=str(error)) from error

@router.get("/{projection_key}/conversation-repair-executions/{execution_id}",
            dependencies=[Depends(require_developer_authorization)])
def get_conversation_repair_execution(projection_key:str,execution_id:UUID):
    from app.services.conversation_repair_executor_service import ConversationRepairExecutorService
    scope=_conversation_analysis_scope(projection_key)
    try:return jsonable_encoder(ConversationRepairExecutorService().refresh(execution_id,creator_profile_id=scope['creator_profile_id'],fanvue_account_id=scope['fanvue_account_id']))
    except LookupError as error:raise HTTPException(status_code=404,detail=str(error)) from error

@router.post("/{projection_key}/messages")
def relationship_send(projection_key:str,body:OperatorMessage):
    from app.services.telegram_operator_message_service import TelegramOperatorMessageError,TelegramOperatorMessageService
    creator,account,user_id,context=_relationship_scope(projection_key)
    scope={"creator_profile_id":creator,"fanvue_account_id":account,
           "telegram_user_id":user_id,**context}
    try:
        operation=TelegramOperatorMessageService().send(context=scope,text=body.text,
            idempotency_key=body.idempotencyKey,
            expected_control_version=body.expectedControlVersion,
            changed_by="CREATOR_OS_OPERATOR")
    except (TelegramOperatorMessageError,ValueError) as error:
        raise HTTPException(status_code=getattr(error,"status_code",409),detail=str(error)) from error
    return jsonable_encoder({"state":operation["state"],
        "eventKey":f"telegram:{operation['telegram_chat_id']}:{operation['outbound_telegram_message_id']}",
        "direction":"AVA","content":operation["message_text"],
        "timestamp":operation["confirmed_at"],"telegramMessageId":operation["outbound_telegram_message_id"],
        "messageType":"HUMAN_OPERATOR","purchaseIntentId":None,"origin":"HUMAN_OPERATOR"})

@router.get("/{projection_key}/offer-inventory")
def relationship_offer_inventory(projection_key:str,view:str="RECOMMENDED",type:str|None=None,
                                 search:str="",hidePurchased:bool=True):
    from app.services.relationship_manual_offer_service import RelationshipManualOfferService
    creator,account,user_id,context=_relationship_scope(projection_key)
    scope={"creator_profile_id":creator,"fanvue_account_id":account,"telegram_user_id":user_id,**context}
    return jsonable_encoder(RelationshipManualOfferService().inventory(context=scope,view=view,
        offering_type=type,search=search,hide_purchased=hidePurchased))

def _offer_error(error):
    raise HTTPException(status_code=getattr(error,"status_code",409),detail=str(error)) from error

@router.post("/{projection_key}/offers/prepare")
def relationship_offer_prepare(projection_key:str,body:ManualOfferPrepare):
    from app.services.relationship_manual_offer_service import RelationshipManualOfferError,RelationshipManualOfferService
    creator,account,user_id,context=_relationship_scope(projection_key)
    scope={"creator_profile_id":creator,"fanvue_account_id":account,"telegram_user_id":user_id,**context}
    try:return jsonable_encoder(RelationshipManualOfferService().prepare(context=scope,offering_id=body.offeringId,
        expected_control_version=body.expectedControlVersion,business_connection_id=body.businessConnectionId))
    except (RelationshipManualOfferError,ValueError) as error:_offer_error(error)

@router.post("/{projection_key}/offers")
def relationship_offer_send(projection_key:str,body:ManualOfferSend):
    from app.services.relationship_manual_offer_service import RelationshipManualOfferError,RelationshipManualOfferService
    creator,account,user_id,context=_relationship_scope(projection_key)
    scope={"creator_profile_id":creator,"fanvue_account_id":account,"telegram_user_id":user_id,**context}
    try:operation=RelationshipManualOfferService().send(context=scope,offering_id=body.offeringId,
        expected_control_version=body.expectedControlVersion,business_connection_id=body.businessConnectionId,
        idempotency_key=body.idempotencyKey,message_text=body.text)
    except (RelationshipManualOfferError,ValueError) as error:_offer_error(error)
    return jsonable_encoder({"state":operation["state"],"direction":"AVA","content":operation["message_text"],
        "timestamp":operation["confirmed_at"],"telegramMessageId":operation["outbound_telegram_message_id"],
        "eventKey":f"telegram:{operation['telegram_chat_id']}:{operation['outbound_telegram_message_id']}",
        "messageType":"COMMERCIAL_OFFER","purchaseIntentId":str(operation["purchase_intent_id"]),
        "origin":"HUMAN_OPERATOR"})
