import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import os

import psycopg
from psycopg.rows import dict_row
import pytest

from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.models.telegram_transport_contract import TelegramReachability, TelegramPreflightError
from app.services.telegram_transport_boundary import capture_acknowledgement
from app.services import telegram_transport_certification_service as module


@pytest.fixture
def service(tmp_path, monkeypatch):
    @contextmanager
    def connection():
        with psycopg.connect(os.environ['TEST_DATABASE_URL'], row_factory=dict_row) as c:
            assert c.execute('SELECT current_database() n').fetchone()['n'] == 'creator_os_governance_release_test_20260920'
            yield c
    monkeypatch.setattr(module, 'IMAGE', tmp_path/'neutral.png')
    with connection() as c:
        c.execute('DELETE FROM ordinary_chat_reply_operations WHERE telegram_account_scope=%s', (module.SCOPE,))
    service = module.TelegramTransportCertificationService(OrdinaryChatReplyRepository(connection))
    yield service
    with connection() as c:
        c.execute('DELETE FROM ordinary_chat_reply_operations WHERE telegram_account_scope=%s', (module.SCOPE,))


class Transport:
    def __init__(self, service, *, failure=None):
        self.service=service; self.calls=[]; self.failure=failure; self.preflights=[]

    async def prepare_delivery(self, *, chat_id, requirements):
        assert chat_id == module.PEER
        self.preflights.append(requirements)
        if self.failure == 'route':
            raise TelegramPreflightError('Unavailable')
        return TelegramReachability('TELETHON','AVA_TELETHON_PRIVATE',chat_id,
            'AUTHORIZED_SESSION_ENTITY',datetime.now(timezone.utc),sender_id=6432023689)

    async def send_text(self, **values):
        return self.invoke('text', values)

    async def send_asset(self, **values):
        return self.invoke('media', values)

    def invoke(self, kind, values):
        row=self.service.repository.get(module.operation_id(kind))
        route=row.delivery_payload['provider_delivery_evidence']['transport_route']
        assert route['peer_id']==module.PEER
        assert route['required_capabilities']['photo'] == (kind=='media')
        assert route['required_capabilities']['caption'] == (kind=='media')
        assert route['required_capabilities']['text'] == (kind=='text')
        assert row.state.value=='SENDING' and row.send_attempt_count==1
        self.calls.append((kind,values))
        if self.failure=='unknown':
            raise TimeoutError('Ambiguous')
        if self.failure=='missing':
            return None
        capture_acknowledgement(8101 if kind=='text' else 8102)
        if self.failure=='after_ack':
            raise ConnectionError('Accepted but interrupted')
        return 8101 if kind=='text' else 8102


def test_text_then_media_shared_lifecycle_and_no_replay(service):
    with pytest.raises(ValueError): service.enqueue('media')
    transport=Transport(service)
    service.enqueue('text')
    asyncio.run(service.poll(transport))
    text=service.repository.get(module.operation_id('text'))
    assert text.state.value=='SENT_CONFIRMED' and text.outbound_telegram_message_id==8101
    service.enqueue('text')
    service.enqueue('media')
    asyncio.run(service.poll(transport))
    service.enqueue('media')
    asyncio.run(service.poll(transport))
    media=service.repository.get(module.operation_id('media'))
    assert media.state.value=='SENT_CONFIRMED' and media.outbound_telegram_message_id==8102
    assert len(transport.calls)==2
    assert media.delivery_payload['provider_delivery_evidence']['telegram_message_id']==8102


@pytest.mark.parametrize('failure',['route','unknown','missing','after_ack'])
def test_failure_stops_campaign_and_never_retries(service, failure):
    service.enqueue('text'); transport=Transport(service,failure=failure)
    asyncio.run(service.poll(transport))
    service.enqueue('text'); asyncio.run(service.poll(transport))
    row=service.repository.get(module.operation_id('text'))
    assert row.state.value!='SENT_CONFIRMED'
    assert len(transport.calls)==(0 if failure=='route' else 1)
    with pytest.raises(ValueError):service.enqueue('media')
    if failure=='after_ack':assert row.delivery_payload['provider_delivery_evidence']['telegram_message_id']==8101


def test_confirmation_persistence_failure_keeps_ack_and_stops(service, monkeypatch):
    service.enqueue('text');transport=Transport(service)
    monkeypatch.setattr(service.repository,'confirm_sent',lambda *a,**kw:None)
    asyncio.run(service.poll(transport));asyncio.run(service.poll(transport))
    row=service.repository.get(module.operation_id('text'))
    assert row.state.value=='SEND_UNCERTAIN' and len(transport.calls)==1
    assert row.delivery_payload['provider_delivery_evidence']['telegram_message_id']==8101


def test_route_persistence_failure_prevents_provider_call(service, monkeypatch):
    service.enqueue('text');transport=Transport(service)
    monkeypatch.setattr(service.repository,'record_provider_evidence',lambda *a,**kw:None)
    asyncio.run(service.poll(transport));asyncio.run(service.poll(transport))
    assert not transport.calls


@pytest.mark.parametrize('column,value',[('telegram_chat_id',42),('response_text','not authorized')])
def test_wrong_recipient_or_content_cannot_send(service, column, value):
    service.enqueue('text')
    with service.repository.connection_factory() as c:
        c.execute('UPDATE ordinary_chat_reply_operations SET '+column+'=%s WHERE operation_id=%s',(value,module.operation_id('text')))
    transport=Transport(service);asyncio.run(service.poll(transport))
    assert not transport.calls


def test_concurrent_poll_single_claim(service):
    service.enqueue('text');transport=Transport(service)
    async def run():await asyncio.gather(service.poll(transport),service.poll(transport))
    asyncio.run(run());assert len(transport.calls)==1


def test_arbitrary_media_rejected(service):
    transport=Transport(service);service.enqueue('text');asyncio.run(service.poll(transport))
    service.enqueue('media');module.IMAGE.write_bytes(b'not-the-neutral-fixture')
    asyncio.run(service.poll(transport));assert len(transport.calls)==1
