from types import SimpleNamespace as NS
from uuid import uuid4
import pytest
from test_relationship_manual_offers import service,context,row,Operations,Controls,OFFER_ID,NOW,reachable
from app.services.relationship_manual_offer_service import RelationshipManualOfferError
from app.services.private_ppv_presentation_service import PrivatePpvPresentationService
from app.models.telegram_transport_contract import TelegramReachability

def prospect():
    return {**context(),'telegram_identity_mapping_id':None,'local_fanvue_user_id':None,
            'external_fanvue_user_uuid':None,'conversation_thread_id':None}

def prepare(s,c=None):
    return s.prepare(context=c or prospect(),offering_id=OFFER_ID,expected_control_version=9,business_connection_id=None)

@pytest.mark.parametrize('c',[context(),prospect()])
def test_mapped_and_prospect_eligible_without_fabrication(c):
    before=dict(c);assert prepare(service(),c)['offering']['priceMinor']==2500;assert c==before

@pytest.mark.parametrize('reason',['Known Telegram relationship is required.','Relationship identity is ambiguous.','Telegram relationship is blocked.','Commerce is unavailable.','Customer safety restriction.'])
def test_canonical_authority_failure_is_exposed(reason):
    def fail(_):raise ValueError(reason)
    with pytest.raises(RelationshipManualOfferError,match=reason):prepare(service(eligibility=NS(require=fail)))

@pytest.mark.parametrize('attribute,value,reason',[('ignored',True,'ignored'),('content_selling_enabled',False,'disabled')])
def test_relationship_controls(attribute,value,reason):
    controls=Controls();setattr(controls.item,attribute,value)
    with pytest.raises(RelationshipManualOfferError,match=reason):prepare(service(controls=controls))

@pytest.mark.parametrize('price',[0,-1,None,9.99,True])
def test_invalid_price(price):
    fulfillment=NS(list_fulfillable=lambda **_:([{**row(),'price_minor':price}],1,1))
    with pytest.raises(RelationshipManualOfferError,match='price'):prepare(service(fulfillment=fulfillment))

def test_unavailable_product():
    with pytest.raises(RelationshipManualOfferError,match='not currently eligible'):
        prepare(service(fulfillment=NS(list_fulfillable=lambda **_:([],0,1))))

def test_expired_history_is_immutable_and_not_conflicting():
    old={'commercial_offering_id':OFFER_ID,'status':'EXPIRED','purchase_intent_id':uuid4(),'presented_at':NOW,'confirmed_delivery':True}
    before=dict(old);prepare(service(operations=Operations([old])));assert old==before

def test_telethon_cannot_substitute_for_unlock_button():
    transport=NS(prepare_delivery=lambda **kw:TelegramReachability('TELETHON','AVA_TELETHON_PRIVATE',kw['chat_id'],'AUTHORIZED_SESSION_ENTITY',NOW,sender_id=1))
    with pytest.raises(RelationshipManualOfferError,match='cannot send URL buttons'):prepare(service(transport=transport))

def test_missing_reachability_does_not_use_telegram_id():
    with pytest.raises(RelationshipManualOfferError,match='Missing reachability'):prepare(service(transport=NS()))

def sending(outcome='ok'):
    ops=Operations();calls=[];created=[];intent=NS(purchase_intent_id=uuid4(),creator_profile_id=1,fanvue_account_id=2,commercial_offering_id=OFFER_ID,commercial_publication_id=uuid4())
    def create(**kw):created.append(kw);return intent
    delivery=NS(operation_id=uuid4(),state="CONFIRMED");
    def send(**kw):
        calls.append(kw)
        if outcome=='timeout':raise TimeoutError('unknown')
        return NS(id=44)
    deliveries=NS(prepare_operator_offer=lambda **_:(delivery,True),claim=lambda d:d,record_provider_evidence=lambda *a:a[0],accepted=lambda *a:delivery,confirm=lambda d:d,failed=lambda *a:None)
    s=service(operations=ops,intents=NS(create_before_presentation=create,mark_delivery_failed=lambda _:None),unlocks=NS(issue=lambda _:(None,'https://unlock.example.test/u/AAAAAAAAAAAAAAAAAAAAAA')),
        deliveries=deliveries,transport=NS(prepare_delivery=reachable,BUTTON_LABEL='Unlock',send_asset=send))
    return s,ops,calls,created

def send(s):return s.send(context=prospect(),offering_id=OFFER_ID,expected_control_version=9,business_connection_id=None,idempotency_key='same-request',message_text='Picked this for you')

def test_sanitized_prospect_fresh_offer_and_repeat_request():
    s,ops,calls,created=sending();result=send(s)
    ops.item['commercial_offering_id']=OFFER_ID
    assert send(s)==result and len(calls)==len(created)==1
    assert result['state']=='CONFIRMED'
    assert created[0]['telegram_identity_mapping_id'] is None and created[0]['external_fanvue_user_uuid'] is None
    assert calls[0]['asset_path']=='safe-teaser.jpg' and calls[0]['button_url'].endswith('/AAAAAAAAAAAAAAAAAAAAAA')
    assert 'https://' not in calls[0]['message_text']

def test_unknown_quarantined_no_retry():
    s,ops,calls,created=sending('timeout')
    with pytest.raises(RelationshipManualOfferError,match='uncertain'):send(s)
    ops.item['commercial_offering_id']=OFFER_ID
    with pytest.raises(RelationshipManualOfferError,match='reconciliation'):send(s)
    assert ops.item['state']=='AMBIGUOUS' and len(calls)==1 and len(created)==1

def test_ui_inventory_exposes_ownership_unknown_and_real_blocker():
    s=service(controls=Controls(manual=False));card=s.inventory(context=prospect(),view='ALL_ELIGIBLE')['items'][0]
    assert not card['eligible'] and 'Manual Mode' in card['eligibilityReason']
    assert card['ownershipEvidence']=='FANVUE_HISTORY_UNKNOWN'

def test_visible_url_rejected():
    with pytest.raises(RuntimeError,match='commerce URL'):
        PrivatePpvPresentationService.validate_customer_text('See https://provider.test/product')

@pytest.mark.parametrize('kind',['missing','ambiguous','blocked','commerce','safety','prospect'])
def test_real_eligibility_service_uses_identity_and_policy_authorities(kind):
    from contextlib import contextmanager
    from app.services.relationship_offer_eligibility_service import RelationshipOfferEligibilityService
    c=prospect();current={k:v for k,v in c.items() if k not in ('creator_profile_id','fanvue_account_id','telegram_user_id')}
    class Query:
        def __init__(self,sql):self.sql=sql
        def fetchall(self):return [{'id':111,'telegram_chat_id':3},{'id':222,'telegram_chat_id':3}] if kind=='ambiguous' else []
        def fetchone(self):return {'telegram_chat_id':3,'relationship_state':{'telegramContactBlock':{'state':'PERMANENT_BLOCKED'}} if kind=='blocked' else {}}
    @contextmanager
    def connection():yield NS(execute=lambda sql,*_:Query(sql))
    s=RelationshipOfferEligibilityService(connection_factory=connection,runtime=NS(evaluate_runtime=lambda **_:NS(allow_offers=kind!='commerce',allow_deliveries=True,reason='unavailable')),safety=NS(decide=lambda **_:NS(allowed=False,code='BLOCKED')))
    if kind=='safety':c['local_fanvue_user_id']=current['local_fanvue_user_id']=9
    s.relationships=NS(control_context=lambda **_:None if kind=='missing' else current)
    if kind=='prospect':assert s.require(c)['ownershipEvidence']=='FANVUE_HISTORY_UNKNOWN'
    else:
        with pytest.raises(ValueError):s.require(c)

def test_missing_safe_teaser_blocks_before_transaction():
    s=service();s.presentations.readiness=NS(evaluate=lambda _:NS(ready=False,reason='CHAT_TEASER_MISSING'))
    with pytest.raises(RelationshipManualOfferError,match='CHAT_TEASER_MISSING'):prepare(s)
    assert s.operations.item is None

def test_conflicting_ownership_cannot_be_treated_as_unpurchased():
    s=service(ownership=NS(answer=lambda _:NS(owned_offering_ids=(),conflicts=('identity conflict',))))
    with pytest.raises(RelationshipManualOfferError,match='conflicting'):prepare(s)


@pytest.fixture(autouse=True)
def trusted_unlock_origin(monkeypatch):
    monkeypatch.setenv("CREATOR_OS_PUBLIC_API_URL", "https://unlock.example.test")
