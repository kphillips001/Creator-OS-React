import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from test_telegram_worker_readiness_service import service, heartbeat
from test_capability_prospect_offers import PrivateSender
from test_prospect_manual_offers import sending, prospect
from test_relationship_manual_offers import row
from app.test_joseph_delivery_routing_repair import Heartbeat, Transport, payload
from app.integrations.telegram.telethon_runtime import TelethonRuntime
from app.models.telegram_transport_contract import TelegramPeerUnavailableError, TelegramRequirements
from app.services.telegram_business_commercial_transport import TelegramBusinessCommercialTransport, TelegramBusinessConnectionDisabledError

def business(kind):
    connection=NS(business_connection_id='b',is_enabled=kind!='disabled',can_reply=True)
    evidence=None if kind=='missing' else dict(is_enabled=True,can_reply=True,
        last_business_inbound_at=datetime.now(timezone.utc)-timedelta(hours=25 if kind=='expired' else 0))
    return TelegramBusinessCommercialTransport(enabled=True,owner_user_id=1,bot_id=2,
        connection_service=NS(current=lambda **_:connection,active=lambda **_:connection),
        peer_observations=NS(evidence=lambda **_:evidence))

@pytest.mark.parametrize('kind',['missing','disabled','expired'])
@pytest.mark.parametrize('private_available',[True,False])
def test_peer_rejection_and_capable_fallback_do_not_poison_global_health(tmp_path,kind,private_available):
    transport=business(kind)
    with pytest.raises((TelegramPeerUnavailableError,TelegramBusinessConnectionDisabledError)):
        transport.prepare_delivery(chat_id=91,requirements=TelegramRequirements())
    s,_,_,_=sending();s.transport=transport;s.transport_candidates=[transport];s.runtime_transport=PrivateSender(private_available)
    if private_available:
        assert asyncio.run(s._live_transport(prospect(),row()))[1]=='TELETHON'
    else:
        with pytest.raises(Exception,match='No reachable'):
            asyncio.run(s._live_transport(prospect(),row()))
    result=service(tmp_path,[heartbeat(metadata={'ordinary_reply_peer_reachability':{
        'scope':'RECIPIENT_REACHABILITY','available':False,'chat_id':91}})]).read(creator_profile_id=1)
    assert result['ready'] and result['healthScope']=='GLOBAL_RUNTIME'
    assert not s.runtime_transport.calls

@pytest.mark.parametrize('error',[
    TelegramPeerUnavailableError('No current Business peer reply evidence.'),
    TelegramBusinessConnectionDisabledError('disabled'),
])
def test_resume_peer_failure_retains_cooldown_without_global_failure(error):
    async def run():
        hb=Heartbeat();runtime=TelethonRuntime(transport=Transport(),inbound_adapter=NS(),heartbeat_service=hb)
        async def resume(_):raise error
        runtime._resume_available_payload=resume
        item=payload();runtime._schedule_ordinary_resume(item,now=hb.now())
        await asyncio.gather(*tuple(runtime._ordinary_resume_tasks.values()),return_exceptions=True)
        await asyncio.sleep(.05)
        assert runtime._ordinary_resume_failures[(91,6408)]['count']==1
        assert not runtime._schedule_ordinary_resume(item,now=hb.now())
        assert hb.events and all('ordinary_reply_resume_healthy' not in e for e in hb.events)
        peer=hb.events[-1]['ordinary_reply_peer_reachability']
        assert peer['chat_id']==91 and peer['message_id']==6408 and peer['available'] is False
    asyncio.run(run())

def test_activation_uses_canonical_authority_not_legacy_resume_diagnostic(tmp_path):
    result=service(tmp_path,[heartbeat(metadata={'ordinary_reply_resume_healthy':False,
        'ordinary_reply_resume_last_error':'TelegramPreflightError: No current Business peer reply evidence.'})]).read(creator_profile_id=1)
    assert result['ready'] and result['healthScope']=='GLOBAL_RUNTIME'
    assert result['ordinaryReplyScheduler']['resumeExecution']['healthy'] is False

