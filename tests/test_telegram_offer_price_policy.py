import asyncio
from types import SimpleNamespace as NS
import pytest
from app.models.telegram_offer_caption import telegram_offer_caption
from app.models.telegram_unlock_action import TelegramUnlockAction
from app.models.telegram_transport_contract import TelegramPreflightError
from test_capability_prospect_offers import PrivateSender,URL
from test_prospect_manual_offers import sending,prospect
from test_relationship_manual_offers import row,OFFER_ID

@pytest.mark.parametrize('price',['USD 9.99','$10.01','EUR 9,99','10.01 dollars','GBP 10','9.99','10 \u20ac','10.01 USD'])
def test_no_currency_amount_in_either_rendering(monkeypatch,price):
    monkeypatch.setenv('CREATOR_OS_PUBLIC_API_URL','https://unlock.example.test')
    for transport in ['TELEGRAM_BUSINESS','TELETHON']:
        result=TelegramUnlockAction(URL).render('A preview for you\n\n'+price,transport=transport,button_label='🔓 Unlock')
        assert result['message_text']==('A preview for you' if transport=='TELEGRAM_BUSINESS' else 'A preview for you\n\nUnlock')
        target=result.get('button_url') or result['caption_entities'][0]['url']
        assert target==URL

@pytest.mark.parametrize('business_available',[True,False])
def test_final_1001_authority_retained_without_telegram_price(monkeypatch,business_available):
    monkeypatch.setenv('CREATOR_OS_PUBLIC_API_URL','https://unlock.example.test')
    s,ops,business_calls,created=sending();private=PrivateSender();s.runtime_transport=private
    s._offering=lambda *_:{**row(),'price_minor':999}
    reservation={'id':'one-original-reservation','amount':1001};reserved=[];issued=[];persisted=[];accepted=[]
    def reserve(intent):reserved.append(intent);return intent,reservation['amount']
    def issue(intent):issued.append((intent,reservation.copy()));return None,URL
    s.unlocks.reserve_offer_price=reserve;s.unlocks.issue=issue
    d=NS(operation_id='delivery',state='CONFIRMED')
    s.deliveries.prepare_operator_offer=lambda **kw:(persisted.append(kw['result'].delivery_payload) or d,True)
    s.deliveries.record_provider_evidence=lambda *args:(accepted.append(args) or args[0])
    if not business_available:
        def unavailable(**_):raise TelegramPreflightError('No Business peer')
        s.transport.prepare_delivery=unavailable
        s._select_transport=lambda *_:None
    args=dict(context=prospect(),offering_id=OFFER_ID,expected_control_version=9,business_connection_id=None,idempotency_key='one-price-free',message_text='A preview for you')
    result=asyncio.run(s._execute(**args));assert result['state']=='CONFIRMED'
    ops.item['commercial_offering_id']=OFFER_ID
    assert asyncio.run(s._execute(**args))==result
    assert len(created)==len(reserved)==len(issued)==1
    assert created[0]['expected_price_minor']==999 and reservation=={'id':'one-original-reservation','amount':1001}
    assert persisted[0]['metadata']['price_minor']==1001
    assert persisted[0]['metadata']['configured_base_price_minor']==999
    action=persisted[0]['metadata']['unlock_action']
    assert action['transport']==('TELEGRAM_BUSINESS' if business_available else 'TELETHON')
    assert action['rendering']==('INLINE_URL_BUTTON' if business_available else 'CAPTION_TEXT_URL')
    assert action['destination']==URL
    calls=business_calls+private.calls;assert len(calls)==1
    assert all(s not in calls[0]['message_text'] for s in ['9.99','10.01','USD','$','https://','fanvue'])
    assert result['outbound_telegram_message_id']==(44 if business_available else 55)
    assert accepted

def test_inline_amount_removed_and_non_price_numbers_preserved():
    assert telegram_offer_caption('3 photos for $10.01')=='3 photos'
    assert telegram_offer_caption('3 photos just for you')=='3 photos just for you'
    assert telegram_offer_caption('Want 3?')=='Want 3?'

@pytest.mark.parametrize('business,private,unknown',[(True,True,False),(False,True,False),(False,False,False),(True,True,True)])
def test_automatic_offer_uses_capability_priority_before_durable_invocation(monkeypatch,business,private,unknown):
    from datetime import datetime,timezone
    from app.models.telegram_transport_contract import TelegramReachability
    from app.models.telegram_commerce import TelegramDeliveryPayload
    from app.services.telegram_delivery_executor import TelegramDeliveryExecutor
    monkeypatch.setenv('CREATOR_OS_PUBLIC_API_URL','https://unlock.example.test')
    calls=[];evidence=[]
    class Sender:
        def __init__(self,kind,available):self.kind=kind;self.available=available
        def prepare_delivery(self,*,chat_id,requirements):
            if not self.available:raise TelegramPreflightError('Peer unavailable')
            p=TelegramReachability(self.kind,'test-sender',chat_id,'BUSINESS_INBOUND' if self.kind=='TELEGRAM_BUSINESS' else 'AUTHORIZED_SESSION_ENTITY',datetime.now(timezone.utc),'business-id' if self.kind=='TELEGRAM_BUSINESS' else None)
            p.validate(requirements);return p
        async def send_asset(self,**values):
            calls.append((self.kind,values))
            if unknown:raise TimeoutError('Ambiguous invocation')
            return 808
    b=Sender('TELEGRAM_BUSINESS',business);p=Sender('TELETHON',private)
    executor=TelegramDeliveryExecutor(global_safety_service=NS(check_global_safety=lambda:{'allowed':True}),business_commercial_transport=b)
    payload=TelegramDeliveryPayload(message_text='A preview\n\nUSD 10.01',asset_path='safe-teaser.jpg',delivery_method='private_ppv_media',metadata={'private_chat_unlock_button':{'label':'🔓 Unlock','url':URL}})
    context={'chat_id':91,'transport':p,'operation_id':'durable-test','record_transport_evidence':lambda value:(evidence.append(value) or value)}
    result=asyncio.run(executor.execute_async(payload,context=context))
    if not business and not private:
        assert not result.executed and not calls and not evidence
    else:
        assert len(calls)==1 and calls[0][0]==('TELEGRAM_BUSINESS' if business else 'TELETHON')
        assert '10.01' not in calls[0][1]['message_text'] and 'USD' not in calls[0][1]['message_text']
        assert evidence[0]['transport_route']['transport']==calls[0][0]
        if unknown:assert not result.executed
        else:
            assert result.metadata['telegram_message_id']==808
            assert evidence[-1]['accepted'] is True
