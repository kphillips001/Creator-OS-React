import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from app.models.telegram_unlock_action import TelegramUnlockAction, validate_unlock_entities, utf16_length
from app.models.telegram_transport_contract import TelegramPreflightError, TelegramReachability, TelegramRequirements
from app.services.telegram_transport_boundary import RoutedTelegramSender, TelegramInvocationUnknown
from app.integrations.telegram.telethon_transport import TelethonUserTransport
from test_prospect_manual_offers import sending, prospect
from test_relationship_manual_offers import OFFER_ID, row

URL = 'https://unlock.example.test/u/AAAAAAAAAAAAAAAAAAAAAA'


@pytest.fixture(autouse=True)
def origin(monkeypatch):
    monkeypatch.setenv('CREATOR_OS_PUBLIC_API_URL', 'https://unlock.example.test')


@pytest.mark.parametrize('url', [
    'https://fanvue.com/u/AAAAAAAAAAAAAAAAAAAAAA',
    'https://evil.test/u/AAAAAAAAAAAAAAAAAAAAAA',
    'https://unlock.example.test.evil.test/u/AAAAAAAAAAAAAAAAAAAAAA',
    'http://unlock.example.test/u/AAAAAAAAAAAAAAAAAAAAAA',
    URL+'?x=1', URL+'#fragment', URL+'/', URL.replace('/u/', '/unlock/'),
    URL.replace('AAAAAAAAAAAAAAAAAAAAAA','short'),
    URL.replace('unlock.example.test','user@unlock.example.test'),
])
def test_untrusted_destination_rejected(url):
    with pytest.raises(TelegramPreflightError):
        TelegramUnlockAction(url).render('Hello',transport='TELETHON',button_label='Unlock')


def test_unicode_entity_and_business_shape():
    caption='A photo 💋'
    result=TelegramUnlockAction(URL).render(caption,transport='TELETHON',button_label='Unlock')
    entity=result['caption_entities'][0]
    assert entity==dict(type='text_url',offset=utf16_length(caption+'\n\n'),length=6,url=URL)
    assert result['message_text'].endswith('\n\nUnlock')
    assert 'https://' not in result['message_text']
    assert TelegramUnlockAction(URL).render(caption,transport='TELEGRAM_BUSINESS',button_label='🔓 Unlock')=={
        'message_text':caption,'button_label':'🔓 Unlock','button_url':URL}


@pytest.mark.parametrize('size,allowed', [(1016,True),(1017,False)])
def test_caption_boundary(size,allowed):
    if allowed:
        result=TelegramUnlockAction(URL).render('a'*size,transport='TELETHON',button_label='Unlock')
        assert utf16_length(result['message_text'])==1024
    else:
        with pytest.raises(TelegramPreflightError):
            TelegramUnlockAction(URL).render('a'*size,transport='TELETHON',button_label='Unlock')


@pytest.mark.parametrize('change', [{'offset':0},{'offset':True},{'length':7},{'type':'url'}, {'url':'https://fanvue.com/x'}])
def test_malformed_entities(change):
    result=TelegramUnlockAction(URL).render('Hi 💋',transport='TELETHON',button_label='Unlock')
    result['caption_entities'][0].update(change)
    with pytest.raises(TelegramPreflightError):validate_unlock_entities(result['message_text'],result['caption_entities'])


class PrivateSender:
    def __init__(self,available=True,outcome='ok'):
        self.available=available;self.calls=[];self.outcome=outcome
    async def prepare_delivery(self, *, chat_id, requirements):
        if not self.available:raise TelegramPreflightError('No private peer')
        return TelegramReachability('TELETHON','AVA_TELETHON_PRIVATE',chat_id,
            'AUTHORIZED_SESSION_ENTITY',datetime.now(timezone.utc),sender_id=99)
    async def send_asset(self, **values):
        self.calls.append(values)
        if self.outcome=='unknown':raise TimeoutError('simulated unknown')
        return NS(id=55)


def test_business_preferred_and_private_fallback():
    s,_,_,_=sending();private=PrivateSender();s.runtime_transport=private
    assert asyncio.run(s._live_transport(prospect(),row()))[1]=='TELEGRAM_BUSINESS'
    def unavailable(**_):raise TelegramPreflightError('No Business peer')
    s.transport.prepare_delivery=unavailable
    assert asyncio.run(s._live_transport(prospect(),row()))[1]=='TELETHON'
    private.available=False
    with pytest.raises(Exception,match='No reachable'):asyncio.run(s._live_transport(prospect(),row()))
    assert private.calls==[]


@pytest.mark.parametrize('outcome',['ok','unknown'])
def test_async_offer_persists_rendering_and_no_post_invocation_failover(outcome):
    s,ops,business_calls,_=sending();private=PrivateSender(outcome=outcome);s.runtime_transport=private
    def unavailable(**_):raise TelegramPreflightError('No Business peer')
    s.transport.prepare_delivery=unavailable
    s._select_transport=lambda *_:None
    persisted=[]
    delivery=NS(operation_id='test',state='CONFIRMED')
    s.deliveries.prepare_operator_offer=lambda **kw:(persisted.append(kw['result'].delivery_payload) or delivery,True)
    s.unlocks.reserve_offer_price=lambda intent:(intent,2499)
    kwargs=dict(context=prospect(),offering_id=OFFER_ID,expected_control_version=9,
        business_connection_id=None,idempotency_key='test-capability',message_text='A photo 💋')
    if outcome=='ok':assert asyncio.run(s._execute(**kwargs))['state']=='CONFIRMED'
    else:
        with pytest.raises(Exception,match='uncertain'):asyncio.run(s._execute(**kwargs))
        assert ops.item['state']=='AMBIGUOUS'
    with pytest.raises(Exception,match='reconciliation') if outcome=='unknown' else __import__('contextlib').nullcontext():
        asyncio.run(s._execute(**kwargs))
    assert len(private.calls)==1 and not business_calls
    assert persisted[0]['operator_rendered_send']['caption_entities'][0]['url']==URL
    assert persisted[0]['metadata']['price_minor']==2499
    assert 'USD' not in private.calls[0]['message_text'] and '24.99' not in private.calls[0]['message_text']


@pytest.mark.parametrize('failure',['none','timeout','receipt_mismatch','persistence'])
def test_real_transport_entity_ack_and_evidence(tmp_path,failure):
    from PIL import Image
    media=tmp_path/'teaser.jpg';Image.new('RGB',(32,32),'white').save(media)
    calls=[];evidence=[]
    async def authorized():return True
    async def send_file(chat,path,**values):
        calls.append(values)
        if failure=='timeout':raise TimeoutError('unknown')
        return NS(id=888,message=values['caption'],entities=[] if failure=='receipt_mismatch' else values['formatting_entities'])
    client=NS(is_connected=lambda:True,is_user_authorized=authorized,
        session=NS(get_input_entity=lambda _:object()),send_file=send_file,_self_id=99)
    transport=TelethonUserTransport(client=client)
    def record(value):
        evidence.append(value)
        if failure=='persistence' and value.get('accepted'):raise RuntimeError('database unavailable')
        return True
    sender=RoutedTelegramSender(transport,context={'operation_id':'operation','record_transport_evidence':record},metadata={})
    rendered=TelegramUnlockAction(URL).render('Photo 💋',transport='TELETHON',button_label='Unlock')
    async def run():return await sender.send_asset(chat_id=3,asset_path=str(media),**rendered)
    if failure=='none':assert asyncio.run(run())==888
    else:
        with pytest.raises(Exception) as caught:asyncio.run(run())
        assert getattr(caught.value,"certainty",None) in {"UNKNOWN","ACCEPTED"} or isinstance(caught.value,ConnectionError)
    assert len(calls)==1 and calls[0]['parse_mode'] is None
    assert evidence[0]['transport_route']['rendered_action']['entities']==rendered['caption_entities']
    assert evidence[0]['transport_route']['payload_sha256']
    with pytest.raises(TelegramInvocationUnknown):asyncio.run(run())
    assert len(calls)==1


@pytest.mark.parametrize('mapped',[False,True])
def test_final_price_uses_existing_allocator_without_provider_or_click(monkeypatch,mapped):
    from contextlib import nullcontext
    from app.services.private_chat_unlock_gateway_service import PrivateChatUnlockGatewayService
    monkeypatch.setenv('PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED','true')
    monkeypatch.setenv('CONTROLLED_AUTONOMY_TEST_ENABLED','false')
    calls=[]
    def reserve(**values):
        calls.append(values)
        assert values['candidate_prices'][:2]==(998,1000)
        return NS(state='RESERVED',exact_price_minor=998)
    intent=NS(purchase_intent_id='fresh',telegram_user_id=3,fanvue_account_id=2,expected_price_minor=999,expected_currency='USD')
    gateway=PrivateChatUnlockGatewayService(repository=NS(serialize_intent=lambda _:nullcontext(),reserve_price=reserve),
        identities=NS(get_verified_by_telegram_user_id=lambda _:object() if mapped else None),
        client_factory=lambda *_:pytest.fail('No provider resources during price reservation'))
    gateway._canonical_prices=lambda *_:{999}
    returned,price=gateway.reserve_offer_price(intent)
    assert returned is intent and intent.expected_price_minor==999
    assert price==(999 if mapped else 998) and len(calls)==(0 if mapped else 1)


def test_unconfirmed_terminal_response_is_quarantined():
    s,ops,calls,_=sending()
    s.deliveries.confirm=lambda op:NS(operation_id=op.operation_id,state='TELEGRAM_ACCEPTED')
    with pytest.raises(Exception,match='uncertain'):
        s.send(context=prospect(),offering_id=OFFER_ID,expected_control_version=9,business_connection_id=None,
            idempotency_key='no-false-success',message_text='A photo')
    assert ops.item['state']=='AMBIGUOUS' and len(calls)==1
