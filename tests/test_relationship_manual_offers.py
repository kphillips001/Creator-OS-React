from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.relationship_manual_offer_service import RelationshipManualOfferError,RelationshipManualOfferService

NOW=datetime.now(timezone.utc)
OFFER_ID=uuid4();PUBLICATION_ID=uuid4()

def row():
    return {'offering_id':OFFER_ID,'publication_id':PUBLICATION_ID,'title':'Midnight Set','description':'private set',
        'offering_type':'SINGLE_IMAGE','price_minor':2500,'currency':'USD','hero_asset_id':42,
        'offering_status':'READY','publication_status':'LIVE','provider':'FANVUE','external_product_id':'product-1',
        'delivery_url':'https://fanvue.example/product-1'}

def context():
    return {'creator_profile_id':1,'fanvue_account_id':2,'telegram_user_id':3,'telegram_chat_id':3,
        'telegram_identity_mapping_id':4,'local_fanvue_user_id':5,'conversation_thread_id':6,
        'external_fanvue_user_uuid':uuid4(),'latest_inbound_telegram_message_id':7}

class Fulfillment:
    def get(self,*_args,**_kwargs):return row()
    def list_fulfillable(self,**_kwargs):return [row()],1,1
class Operations:
    def __init__(self,intents=None,owned=None):self.intents=intents or [];self.owned=owned or set();self.item=None;self.attachments=[]
    def customer_state(self,**_kwargs):return self.intents,self.owned
    def reserve(self,**values):
        if self.item is None:self.item={**values['context'],'operation_id':uuid4(),'message_text':values['message_text'],'state':'PREPARED','confirmed_at':None,'outbound_telegram_message_id':None,'purchase_intent_id':None}
        return self.item
    def claim(self,*_args,**_kwargs):self.item['state']='SENDING';return self.item
    def attach(self,*args,**values):self.attachments.append(values);self.item.update(values);return self.item
    def finish(self,_id,state,**values):self.item.update(state=state,confirmed_at=NOW if state=='CONFIRMED' else None,outbound_telegram_message_id=values.get('message_id'));return self.item
class Controls:
    def __init__(self,manual=True,version=9):self.item=SimpleNamespace(manual=manual,control_version=version);self.repository=SimpleNamespace(touch_manual_activity=lambda value:value)
    def get(self,**_kwargs):return self.item
class Peers:
    def evidence(self,**_kwargs):return {'is_enabled':True,'can_reply':True,'last_business_inbound_at':NOW}
class Selector:
    def select(self,**_kwargs):return SimpleNamespace(offering_id=OFFER_ID)

def service(**changes):
    values={'fulfillment':Fulfillment(),'operations':Operations(),'controls':Controls(),'peer_observations':Peers(),
        'selector':Selector(),'intents':SimpleNamespace(),'unlocks':SimpleNamespace(),'deliveries':SimpleNamespace(),
        'transport':SimpleNamespace(),'clock':lambda:NOW,
        'chat_inventory':SimpleNamespace(build_inventory=lambda **_kwargs:SimpleNamespace(items=(SimpleNamespace(asset_id=42),))),
        'ownership':SimpleNamespace(answer=lambda _identity:SimpleNamespace(owned_offering_ids=()))}
    values.update(changes);return RelationshipManualOfferService(**values)

def test_inventory_uses_confirmed_delivery_for_customer_scoped_exposure_and_hides_owned():
    offered={'commercial_offering_id':OFFER_ID,'purchase_intent_id':uuid4(),'status':'EXPIRED','presented_at':NOW,
        'confirmed_delivery':True,'presentation_origin':'AI_PRESENTED'}
    result=service(operations=Operations([offered])).inventory(context=context(),view='PREVIOUSLY_OFFERED')
    assert result['items'][0]['status']=='OFFERED_BEFORE'
    assert result['items'][0]['presentationCount']==1
    assert service(operations=Operations(owned={str(OFFER_ID)})).inventory(context=context(),view='ALL_ELIGIBLE')['items']==[]

def test_unconfirmed_delivery_is_not_exposure_and_unresolved_intent_is_active():
    failed={'commercial_offering_id':OFFER_ID,'purchase_intent_id':uuid4(),'status':'EXPIRED','presented_at':NOW,
        'confirmed_delivery':False,'presentation_origin':'AI_PRESENTED'}
    assert service(operations=Operations([failed])).inventory(context=context(),view='NEVER_OFFERED')['items'][0]['status']=='AVAILABLE'
    active={**failed,'status':'CREATED','presented_at':None}
    item=service(operations=Operations([active])).inventory(context=context(),view='ALL_ELIGIBLE')['items'][0]
    assert item['status']=='ACTIVE_OFFER' and item['eligible'] is False

def test_search_and_customer_views_use_confirmed_history_only():
    confirmed={'commercial_offering_id':OFFER_ID,'purchase_intent_id':uuid4(),'status':'EXPIRED','presented_at':NOW,
        'confirmed_delivery':True,'presentation_origin':'HUMAN_OPERATOR_PRESENTED'}
    candidate=service(operations=Operations([confirmed]))
    assert len(candidate.inventory(context=context(),view='PREVIOUSLY_OFFERED',search='midnight')['items'])==1
    assert candidate.inventory(context=context(),view='PREVIOUSLY_OFFERED',search='unrelated')['items']==[]

def test_empty_optional_chat_inventory_does_not_suppress_fulfillable_candidates():
    empty=SimpleNamespace(build_inventory=lambda **_kwargs:SimpleNamespace(items=()))
    result=service(chat_inventory=empty).inventory(context=context(),view='ALL_ELIGIBLE')
    assert [item['title'] for item in result['items']]==['Midnight Set']
    assert result['items'][0]['legacyChatInventoryPresent'] is False

def test_session_offering_is_not_flattened_into_the_one_off_manual_path():
    session_row={**row(),'photoshoot_selling_mode':'SESSION','source_photoshoot_deliverable_id':uuid4()}
    fulfillment=Fulfillment();fulfillment.get=lambda *_args,**_kwargs:session_row
    fulfillment.list_fulfillable=lambda **_kwargs:([session_row],1,1)
    candidate=service(fulfillment=fulfillment).inventory(context=context(),view='ALL_ELIGIBLE')
    assert candidate['items']==[]
    with pytest.raises(RelationshipManualOfferError,match='Session selling'):
        service(fulfillment=fulfillment).prepare(context=context(),offering_id=OFFER_ID,
            expected_control_version=9,business_connection_id='bc')

@pytest.mark.parametrize(('requested','expected'),[
    ('SINGLE',True),('BUNDLE',False),('SESSION',False),('SINGLE_IMAGE',True)])
def test_type_classification(requested,expected):
    assert RelationshipManualOfferService._matches_type(row(),requested) is expected

def test_prepare_blocks_auto_stale_owned_active_and_missing_peer_evidence():
    with pytest.raises(RelationshipManualOfferError,match='Manual Mode'):
        service(controls=Controls(manual=False)).prepare(context=context(),offering_id=OFFER_ID,expected_control_version=9,business_connection_id='bc')
    with pytest.raises(RelationshipManualOfferError,match='stale'):
        service().prepare(context=context(),offering_id=OFFER_ID,expected_control_version=8,business_connection_id='bc')
    with pytest.raises(RelationshipManualOfferError,match='already owns'):
        service(operations=Operations(owned={str(OFFER_ID)})).prepare(context=context(),offering_id=OFFER_ID,expected_control_version=9,business_connection_id='bc')
    active={'commercial_offering_id':OFFER_ID,'purchase_intent_id':uuid4(),'status':'PRESENTED','presented_at':NOW,'confirmed_delivery':True}
    with pytest.raises(RelationshipManualOfferError,match='active PurchaseIntent'):
        service(operations=Operations([active])).prepare(context=context(),offering_id=OFFER_ID,expected_control_version=9,business_connection_id='bc')

def test_send_reuses_purchase_intent_unlock_delivery_and_exact_business_connection_once():
    operations=Operations();intent=SimpleNamespace(purchase_intent_id=uuid4(),creator_profile_id=1,fanvue_account_id=2,
        commercial_offering_id=OFFER_ID,commercial_publication_id=PUBLICATION_ID)
    intents=SimpleNamespace(create_before_presentation=lambda **values:intent,mark_delivery_failed=lambda *_:None)
    delivery=SimpleNamespace(operation_id=uuid4(),state='CREATED');accepted=SimpleNamespace(operation_id=delivery.operation_id,state='TELEGRAM_ACCEPTED')
    calls=[]
    deliveries=SimpleNamespace(prepare=lambda **kwargs:(delivery,True),claim=lambda value:value,
        accepted=lambda value,message_id:accepted,record_provider_evidence=lambda *args:None,
        confirm=lambda value:calls.append(('confirm',value)),failed=lambda *args:None)
    receipt=SimpleNamespace(id=77,provider_payload={'ok':True})
    transport=SimpleNamespace(BUTTON_LABEL='Unlock',send_text=lambda **values:(calls.append(('send',values)) or receipt))
    result=service(operations=operations,intents=intents,unlocks=SimpleNamespace(issue=lambda value:(object(),'https://example.test/u/token')),
        deliveries=deliveries,transport=transport).send(context=context(),offering_id=OFFER_ID,expected_control_version=9,
            business_connection_id='bc-exact',idempotency_key='stable-key',message_text='A natural offer')
    assert result['state']=='CONFIRMED'
    assert calls[0][1]['expected_business_connection_id']=='bc-exact'
    assert operations.attachments[0]['purchase_intent_id']==intent.purchase_intent_id
    assert calls[-1][0]=='confirm'
