from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest

from app.models.telegram_inbound import TelegramInboundResult
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.post_nudge_conversation_policy_service import (
    PostNudgeConversationPolicyService,
)


NOW = datetime.now(timezone.utc)
INTENT_ID = UUID("630bd9c4-c80c-4120-8cc7-f30461bb4d99")


class Ledger:
    def relationship_nonconversion(self, **_): return {"nonconversion_count": 1}


class Operations:
    def post_nudge_policy_history(self, **_):
        return {"supporter_boundary_confirmed": False,
                "sexual_attempts_after_boundary": 0}


class Accounting:
    def today(self, **_):
        return {"replies_used_today": 0,
                "next_reset_at": NOW + timedelta(days=1)}


def active(status="CLICKED"):
    return SimpleNamespace(
        purchase_intent_id=INTENT_ID,
        status=SimpleNamespace(value=status),
        presented_at=NOW - timedelta(days=1),
        purchased_at=None,
    )


def operation(text, message_id=6549):
    return SimpleNamespace(
        inbound_message_text=text,
        inbound_received_at=NOW,
        inbound_sender_telegram_user_id=8303003496,
        inbound_telegram_message_id=message_id,
        telegram_chat_id=8303003496,
    )


def commercial(direct=False):
    return SimpleNamespace(commercial_bypass_eligible=direct)


def policy():
    return PostNudgeConversationPolicyService(
        ledger=Ledger(), operations=Operations(), accounting=Accounting())


@pytest.fixture
def active_intent(monkeypatch):
    monkeypatch.setattr(
        PurchaseIntentRepository, "list_confirmed_presentations_for_buyer",
        lambda *_args, **_kwargs: [active()],
    )


@pytest.mark.parametrize("text", [
    "Good morning beautiful", "How was your day?", "Do you golf?",
    "I just got home from work",
])
def test_active_ppv_ordinary_turns_preserve_normal_conversation(active_intent, text):
    result = policy().evaluate(operation=operation(text),
        commercial_decision=commercial(), verified_buyer=False,
        creator_profile_id=2, fanvue_account_id=2)
    assert result.response_purpose == "ACTIVE_PRESENTATION_BRIDGE"
    assert result.evidence["bridgeConversationalFunction"] == "NORMAL_CONVERSATION"
    assert result.provider_allowed and not result.sexual_access_gated
    assert result.evidence["supporterBoundaryEligible"] is False


def test_active_ppv_compliment_allows_light_flirt(active_intent):
    result = policy().evaluate(operation=operation("You have such sexy curves"),
        commercial_decision=commercial(), verified_buyer=False,
        creator_profile_id=2, fanvue_account_id=2)
    assert result.evidence["sexualSignalClass"] == "SEXUAL_ATTRACTIVE_COMPLIMENT"
    assert result.evidence["bridgeConversationalFunction"] == "LIGHT_FLIRT"
    assert result.provider_allowed


def test_joseph_active_clicked_escalation_uses_bridge_not_boundary(active_intent):
    text = ("If you lay down on your bed I will kiss and lick your inner thighs "
            "up to your sweet puss")
    result = policy().evaluate(operation=operation(text),
        commercial_decision=commercial(), verified_buyer=False,
        creator_profile_id=2, fanvue_account_id=2)
    assert result.response_purpose == "ACTIVE_PRESENTATION_BRIDGE"
    assert result.evidence["bridgeConversationalFunction"] == "PLAYFUL_REDIRECT"
    assert result.evidence["activePresentationId"] == str(INTENT_ID)
    assert result.evidence["activePresentationState"] == "CLICKED"
    assert result.evidence["supporterBoundarySuppressionReason"] == (
        "ACTIVE_UNSETTLED_PRESENTATION")


@pytest.mark.parametrize("text", [
    "How much is it?", "Where do I unlock it?", "Send me the link again", "I want it",
])
def test_fresh_commercial_signal_overrides_bridge(active_intent, text):
    result = policy().evaluate(operation=operation(text),
        commercial_decision=commercial(True), verified_buyer=False,
        creator_profile_id=2, fanvue_account_id=2)
    assert result.response_purpose == "COMMERCIAL_REENTRY"
    assert result.evidence["commercialSignalOverride"] is True


def test_purchase_exits_bridge(monkeypatch):
    monkeypatch.setattr(PurchaseIntentRepository,
        "list_confirmed_presentations_for_buyer",
        lambda *_args, **_kwargs: [active("PURCHASED")])
    result = policy().evaluate(operation=operation("I want you naked"),
        commercial_decision=commercial(), verified_buyer=True,
        creator_profile_id=2, fanvue_account_id=2)
    assert result.active is False
    assert result.evidence["activePresentationBridge"] is False


def test_settled_nonpurchase_exits_bridge(monkeypatch):
    monkeypatch.setattr(PurchaseIntentRepository,
        "list_confirmed_presentations_for_buyer",
        lambda *_args, **_kwargs: [active("EXPIRED")])
    result = policy().evaluate(operation=operation("I want you naked"),
        commercial_decision=commercial(), verified_buyer=False,
        creator_profile_id=2, fanvue_account_id=2)
    assert result.response_purpose is None
    assert result.evidence["sexualSalesOpportunity"][
        "sexualSalesOpportunityEligible"] is True


def inbound_result(text):
    return TelegramInboundResult(
        correlation_id="telegram:1:2", telegram_chat_id=1,
        telegram_user_id=2, message_id=3, engine_user_id="telegram:2",
        response_text=text, offer_authorized=False, offer_link=None,
        blocked=False, error_code=None, delivery_type="MESSAGE_TEXT",
        delivery_mode="conversation", delivery_requires_payment=False,
        delivery_payload={"type": "MESSAGE_TEXT", "message_text": text},
        diagnostic_metadata={},
    )


def bridge_operation(message_id=6549):
    return SimpleNamespace(
        operation_id="operation", inbound_telegram_message_id=message_id,
        inbound_received_at=NOW,
        inbound_message_text="I want to lick your body",
        inbound_sender_telegram_user_id=8303003496,
        telegram_chat_id=8303003496,
        delivery_payload={"postNudgeConversationPolicy": {
            "active": True, "responsePurpose": "ACTIVE_PRESENTATION_BRIDGE",
            "activePresentationBridge": True,
            "activePresentationId": str(INTENT_ID),
            "activePresentationState": "CLICKED",
            "activePresentationBridgeReason": "KEEP_RELATIONSHIP_ALIVE",
            "sexualSignalClass": "SEXUAL_ESCALATION",
            "bridgeConversationalFunction": "PLAYFUL_REDIRECT",
            "commercialSignalOverride": False,
            "supporterBoundaryEligible": False,
            "supporterBoundarySuppressionReason": "ACTIVE_UNSETTLED_PRESENTATION",
            "sexualAccessGated": True, "commercialReentry": False,
        }},
    )


def test_bridge_quality_gate_removes_explicit_participation_and_sales_language():
    repository = Mock(); repository.store_generated.return_value = "generated"
    repository.recent_ava_responses.return_value = []
    service = OrdinaryChatReplyService(repository=repository, worker_id="worker")
    service.generated(bridge_operation(),
        inbound_result("I want to fuck you all night, unlock it now"))
    stored = repository.store_generated.call_args.kwargs
    text = stored["response_text"].lower()
    assert "fuck" not in text and "unlock" not in text and "supporter" not in text
    assert len(text.split()) <= 12
    diagnostics = stored["response_payload"]["diagnostic_metadata"]
    assert diagnostics["activePresentationBridge"]["supporterBoundaryEligible"] is False


def test_bridge_retry_payload_passes_function_first_composition_context():
    service = OrdinaryChatReplyService(repository=Mock(), worker_id="worker")
    payload = service.retry_payload(bridge_operation())
    bridge = payload.quality_correction_context["activePresentationBridge"]
    assert bridge["bridgeConversationalFunction"] == "PLAYFUL_REDIRECT"
    assert bridge["activePresentationState"] == "CLICKED"
