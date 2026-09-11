from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.api.creator_intelligence import _snapshot_scope
from app.services.relationships_service import RelationshipFilter, RelationshipSort, RelationshipsService

router=APIRouter(prefix="/api/v1/relationships",tags=["relationships"])

class ControlChange(BaseModel):
    reason: str | None = Field(default=None,max_length=500)

class CustomerPermissionChange(BaseModel):
    value: bool
    reason: str | None = Field(default=None,max_length=500)

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

@router.get("/{projection_key}/control")
def relationship_control(projection_key:str):
    from app.services.telegram_relationship_control_service import TelegramRelationshipControlService
    creator,account,user_id,context=_relationship_scope(projection_key)
    control=TelegramRelationshipControlService().get(creator_profile_id=creator,
        fanvue_account_id=account,telegram_user_id=user_id,
        telegram_chat_id=context["telegram_chat_id"])
    return jsonable_encoder(_control_response(control,context))

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
