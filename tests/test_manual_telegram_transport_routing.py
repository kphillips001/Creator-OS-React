from app.testing.telegram_transport_fixtures import ReachableTestSender, InvocationTestRepository
from app.integrations.telegram.telethon_transport import TelethonProviderRejectedError
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.telegram_relationship_control import (
    TelegramRelationshipControl, TelegramRelationshipMode,
)
from app.services.telegram_manual_transport_resolver import (
    ManualTelegramRoute, ManualTelegramRouteUnavailable,
    TelegramManualTransportResolver,
)
from app.services.telegram_operator_message_service import (
    TelegramOperatorMessageError, TelegramOperatorMessageService,
)
from app.integrations.telegram.telethon_runtime import TelethonRuntime


class Connections:
    def __init__(self, connection): self.connection=connection
    def active(self, **_): return self.connection


class Peers:
    def __init__(self, evidence): self.value=evidence;self.calls=[]
    def evidence(self, **values): self.calls.append(values);return self.value


def resolver(*, evidence=None, connection=True):
    current=(SimpleNamespace(business_connection_id="business-1")
             if connection else None)
    return TelegramManualTransportResolver(owner_user_id=1,bot_id=2,
        connections=Connections(current),peer_observations=Peers(evidence),
        private_readiness=SimpleNamespace(available=lambda:True))


def context(scope="AVA_TELETHON_PRIVATE", mapped=False):
    return {"creator_profile_id":2,"fanvue_account_id":2,
        "telegram_user_id":5729124166,"telegram_chat_id":5729124166,
        "telegram_account_scope":scope,
        "telegram_identity_mapping_id":uuid4() if mapped else None,
        "local_fanvue_user_id":7 if mapped else None,"conversation_thread_id":None}


def test_business_observed_peer_uses_business_transport_even_when_mapped():
    route=resolver(evidence={"is_enabled":True,"can_reply":True,
        "last_business_inbound_at":datetime.now(timezone.utc),"observation_count":1}).resolve(
            context(scope="AVA_TELETHON_PRIVATE",mapped=True))
    assert route.kind == "TELEGRAM_BUSINESS"
    assert route.business_connection_id == "business-1"


@pytest.mark.parametrize("evidence", [
    None,
    {"is_enabled":True,"can_reply":True,"last_business_inbound_at":None,
     "observation_count":0},
    {"is_enabled":True,"can_reply":False,"last_business_inbound_at":datetime.now(timezone.utc),
     "observation_count":1},
])
def test_global_business_connection_without_reply_capable_peer_uses_private(evidence):
    assert resolver(evidence=evidence).resolve(context()).kind == "AVA_TELETHON_PRIVATE"


def test_unmapped_johnny_exact_relationship_uses_private_route():
    route=resolver(evidence=None).resolve(context())
    assert route == ManualTelegramRoute("AVA_TELETHON_PRIVATE")


def test_mapping_alone_does_not_prove_business_and_no_route_is_local():
    with pytest.raises(ManualTelegramRouteUnavailable):
        resolver(evidence=None).resolve(context(scope=None,mapped=True))


class Controls:
    def __init__(self):
        self.current=TelegramRelationshipControl(uuid4(),2,2,5729124166,5729124166,
            TelegramRelationshipMode.HUMAN_OPERATOR,1)
        self.repository=SimpleNamespace(touch_manual_activity=lambda _value:None)
    def get(self, **_): return self.current


class Operations:
    def __init__(self,state="PREPARED"):
        self.row=None;self.initial=state;self.reserve_calls=0;self.claims=[]
    def reserve(self, **values):
        self.reserve_calls+=1
        if self.row is None:self.row={**values,"operation_id":uuid4(),"state":self.initial,
            "outbound_telegram_message_id":None,"send_attempt_count":1}
        return self.row
    def claim(self, operation_id, *, expected_version, route):
        self.claims.append(route);self.row["state"]="SENDING"
        self.row["send_attempt_count"]+=1;return self.row
    def confirmed(self,*_): raise AssertionError("business must not confirm")
    def failed(self,_id,error):self.row.update(state="FAILED",last_error=str(error));return self.row
    def ambiguous(self,_id,error):self.row.update(state="AMBIGUOUS",last_error=str(error));return self.row


class PrivateDispatch:
    def __init__(self,state="CONFIRMED"):self.state=state;self.calls=0
    def dispatch(self,operation):
        self.calls+=1;return {**operation,"state":self.state,
            "outbound_telegram_message_id":9123 if self.state=="CONFIRMED" else None}


def test_same_failed_operation_is_reused_and_private_dispatch_confirms():
    operations=Operations(state="FAILED");dispatch=PrivateDispatch()
    service=TelegramOperatorMessageService(repository=operations,controls=Controls(),
        transport=SimpleNamespace(send_text=lambda **_:pytest.fail("business called")),
        resolver=resolver(evidence=None),private_dispatcher=dispatch)
    result=service.send(context=context(),text="Still waiting on those coffees 😘",
        idempotency_key="82ddf34c-6260-407e-a7eb-258e377d5bee",
        expected_control_version=1,changed_by="CREATOR_OS_OPERATOR")
    assert result["state"] == "CONFIRMED"
    assert result["outbound_telegram_message_id"] == 9123
    assert operations.reserve_calls == 1
    assert operations.claims == ["AVA_TELETHON_PRIVATE"]
    assert operations.row["send_attempt_count"] == 2


def test_no_route_persists_deterministic_failure_before_provider():
    operations=Operations();business=SimpleNamespace(send_text=lambda **_:pytest.fail("provider called"))
    service=TelegramOperatorMessageService(repository=operations,controls=Controls(),
        transport=business,resolver=resolver(evidence=None),private_dispatcher=PrivateDispatch())
    with pytest.raises(TelegramOperatorMessageError) as caught:
        service.send(context=context(scope=None),text="hello",idempotency_key="stable",
            expected_control_version=1,changed_by="operator")
    assert caught.value.code == "MANUAL_TELEGRAM_ROUTE_UNAVAILABLE"
    assert caught.value.delivery_certainty == "DEFINITELY_NOT_SENT"
    assert operations.row["state"] == "FAILED"


def test_private_ambiguous_result_cannot_retry():
    operations=Operations();dispatch=PrivateDispatch("AMBIGUOUS")
    service=TelegramOperatorMessageService(repository=operations,controls=Controls(),
        transport=SimpleNamespace(),resolver=resolver(evidence=None),
        private_dispatcher=dispatch)
    with pytest.raises(TelegramOperatorMessageError) as caught:
        service.send(context=context(),text="hello",idempotency_key="stable",
            expected_control_version=1,changed_by="operator")
    assert caught.value.delivery_certainty == "DELIVERY_UNCERTAIN"
    operations.row["state"]="AMBIGUOUS"
    with pytest.raises(TelegramOperatorMessageError):
        service.send(context=context(),text="hello",idempotency_key="stable",
            expected_control_version=1,changed_by="operator")
    assert dispatch.calls == 1


def test_private_dispatch_uses_supplied_singleton_runtime_transport():
    class RuntimeOperations(InvocationTestRepository):
        def __init__(self): self.confirmed_values=[]
        def pending_private_dispatches(self,_limit):
            return [{"operation_id":uuid4(),"telegram_chat_id":5729124166,
                "message_text":"fixture only"}]
        def confirmed(self,operation_id,message_id,**_):
            self.confirmed_values.append((operation_id,message_id))
        def failed(self,*_,**__):pytest.fail("unexpected deterministic failure")
        def ambiguous(self,*_,**__):pytest.fail("unexpected ambiguity")
    class ExistingRuntimeTransport(ReachableTestSender):
        def __init__(self):self.calls=[]
        def set_inbound_handler(self,_handler):pass
        async def send_text(self,**values):self.calls.append(values);return 991
    operations=RuntimeOperations();transport=ExistingRuntimeTransport()
    safety=SimpleNamespace(refresh=lambda:None,behavior_config={})
    ordinary=SimpleNamespace(due_availability_payloads=lambda **_:[],
        due_generated_send_payloads=lambda **_:[])
    runtime=TelethonRuntime(transport=transport,inbound_adapter=SimpleNamespace(),
        global_safety_service=safety,operator_message_repository=operations,
        ordinary_reply_service=ordinary)
    runtime._transport_connected=True
    import asyncio
    result=asyncio.run(runtime._availability_iteration(
        now=datetime.now(timezone.utc)))
    assert result["manualPrivateDispatches"] == 1
    assert transport.calls == [{"chat_id":5729124166,"message_text":"fixture only"}]
    assert operations.confirmed_values[0][1] == 991


@pytest.mark.parametrize("error,terminal", [
    (TelethonProviderRejectedError("provider rejected"), "FAILED"),
    (ConnectionError("acceptance unknown"), "AMBIGUOUS"),
])
def test_private_runtime_preserves_delivery_certainty(error,terminal):
    class RuntimeOperations(InvocationTestRepository):
        def __init__(self):self.terminal=None
        def pending_private_dispatches(self,_limit):return [{"operation_id":uuid4(),
            "telegram_chat_id":44,"message_text":"fixture"}]
        def confirmed(self,*_):pytest.fail("must not confirm")
        def failed(self,*_,**__):self.terminal="FAILED"
        def ambiguous(self,*_,**__):self.terminal="AMBIGUOUS"
    class Transport(ReachableTestSender):
        def set_inbound_handler(self,_handler):pass
        async def send_text(self,**_):raise error
    operations=RuntimeOperations()
    runtime=TelethonRuntime(transport=Transport(),inbound_adapter=SimpleNamespace(),
        global_safety_service=SimpleNamespace(refresh=lambda:None,behavior_config={}),
        operator_message_repository=operations,
        ordinary_reply_service=SimpleNamespace(due_availability_payloads=lambda **_:[],
            due_generated_send_payloads=lambda **_:[]))
    runtime._transport_connected=True
    import asyncio
    asyncio.run(runtime._availability_iteration(now=datetime.now(timezone.utc)))
    assert operations.terminal == terminal
