from app.services.telegram_inbound_adapter import TelegramInboundAdapter
from app.test_telegram_inbound_adapter import (
    RecordingConversationGateway, RecordingIdentityAdapter, inbound_payload,
)


class AttributionObserver:
    def __init__(self, disposition="ENTRY_OBSERVED"):
        self.disposition=disposition; self.calls=[]
    def observe_message(self, **values):
        self.calls.append(values)
        return {"disposition":self.disposition,
            "entryObserved":self.disposition=="ENTRY_OBSERVED",
            "publicationId":"publication-one" if self.disposition=="ENTRY_OBSERVED" else None}


def test_legitimate_entry_is_observed_without_gateway_generation_or_response():
    gateway=RecordingConversationGateway(); observer=AttributionObserver()
    adapter=TelegramInboundAdapter(identity_adapter=RecordingIdentityAdapter(),
        conversation_gateway=gateway,creator_profile_id=7,
        content_entry_attribution_service=observer)
    result=adapter.execute(inbound_payload(message_text="/start cc_"+"A"*43))
    assert observer.calls and gateway.calls==[]
    assert result.response_text=="" and result.offer_authorized is False
    assert result.diagnostic_metadata["ai_generation_count"]==0
    assert result.diagnostic_metadata["commercial_execution_count"]==0
    assert result.diagnostic_metadata["automatic_send_count"]==0


def test_ordinary_message_still_reaches_gateway_without_attribution():
    gateway=RecordingConversationGateway(); observer=AttributionObserver("NONE")
    result=TelegramInboundAdapter(identity_adapter=RecordingIdentityAdapter(),
        conversation_gateway=gateway,creator_profile_id=7,
        content_entry_attribution_service=observer).execute(inbound_payload())
    assert len(gateway.calls)==1 and result.response_text=="Normalized Ava reply"


def test_telethon_consumes_control_before_reservation_or_ordinary_reply_begin():
    import inspect
    from app.integrations.telegram.telethon_runtime import TelethonRuntime
    source = inspect.getsource(TelethonRuntime._handle_payload_observed)
    consumed = source.index("observe_content_entry_control")
    reservation = source.index("reserve_text")
    ordinary_dispatch = source.index("handle_payload(payload)")
    assert consumed < reservation < ordinary_dispatch
    assert "consume_control" in source
    assert "ordinary_reply_operations=0" in source