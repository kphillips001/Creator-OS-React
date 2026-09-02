from types import SimpleNamespace

import pytest

from app.services.live_controlled_test_observer_service import (
    LiveControlledTestObserverService,
    LiveControlledTestUnavailable,
)


class Boundary:
    def __init__(self, identity): self.identity = identity
    def configured_identity(self): return self.identity


def test_live_mode_fails_closed_without_controlled_identity():
    service = LiveControlledTestObserverService(boundary=Boundary(None))
    with pytest.raises(LiveControlledTestUnavailable, match="No controlled"):
        service.snapshot()


def test_turn_projection_uses_persisted_diagnostics_without_execution():
    row = {
        "operation_id": "00000000-0000-0000-0000-000000000001",
        "response_payload": {"delivery_requires_payment": False, "delivery_type": "text",
            "diagnostic_metadata": {"intent": {"tier": "LOW"}, "offer_authorized": False,
                "commerce_decision": {"decision": "TEASE", "reason_code": "WARM_UP",
                    "commerce_execution_policy": "COMMERCE_DISABLED_FOR_TURN"}}},
        "response_text": "hello", "inbound_telegram_message_id": 10,
        "outbound_telegram_message_id": 11, "created_at": None, "generated_at": None,
        "sent_confirmed_at": None, "state": "SENT_CONFIRMED", "correlation_id": "c",
        "inbound_message_text": "exact new inbound text", "inbound_received_at": None,
    }
    service = LiveControlledTestObserverService(boundary=Boundary((1, 1)))
    turn = service._turn(row, [], None, [], 1)
    assert turn["decision"]["salesBrainDecision"] == "TEASE"
    assert turn["decision"]["purchaseIntentCreated"] is False
    assert turn["customerMessagePersisted"] is True
    assert turn["customerMessage"] == "exact new inbound text"
    assert turn["classification"] == "ordinary"


def test_historical_turn_is_explicitly_unavailable_not_reconstructed():
    row = {"operation_id": "00000000-0000-0000-0000-000000000002",
        "response_payload": {}, "response_text": None, "inbound_telegram_message_id": 1,
        "outbound_telegram_message_id": None, "created_at": None, "generated_at": None,
        "sent_confirmed_at": None, "state": "PENDING_GENERATION", "correlation_id": "x",
        "inbound_message_text": None, "inbound_received_at": None}
    turn = LiveControlledTestObserverService(boundary=Boundary((1, 1)))._turn(row, [], None, [], 1)
    assert turn["customerMessage"] == "Unavailable — predates durable inbound capture"
    assert turn["customerMessagePersisted"] is False


def test_turn_matches_purchase_intent_by_canonical_conversation_correlation():
    row = {
        "operation_id": "00000000-0000-0000-0000-000000000003",
        "response_payload": {
            "correlation_id": "telegram:7857064998:5459",
            "delivery_requires_payment": True,
            "delivery_type": "SINGLE_IMAGE",
            "diagnostic_metadata": {"offer_authorized": True},
        },
        "response_text": "Here you go.",
        "inbound_telegram_message_id": 5459,
        "inbound_sender_telegram_user_id": 7857064998,
        "outbound_telegram_message_id": None,
        "created_at": None,
        "generated_at": None,
        "sent_confirmed_at": None,
        "state": "GENERATED",
        "correlation_id": (
            "ordinary_reply:AVA_TELETHON_PRIVATE:7857064998:5459"
        ),
        "inbound_message_text": "show me",
        "inbound_received_at": None,
        "send_attempt_count": 0,
        "last_error": None,
    }
    intent = {
        "purchase_intent_id": "00000000-0000-0000-0000-000000000099",
        "conversation_id": "telegram:7857064998:5459",
        "telegram_user_id": 7857064998,
        "created_metadata": {"inbound_message_id": 5459},
    }
    turn = LiveControlledTestObserverService(
        boundary=Boundary((7857064998, 7857064998)),
    )._turn(row, [intent], None, [], 8)
    assert turn["decision"]["purchaseIntentCreated"] is True
    assert turn["decision"]["purchaseIntentId"] == intent["purchase_intent_id"]
    assert turn["decision"]["outboundRetryEligible"] is True
