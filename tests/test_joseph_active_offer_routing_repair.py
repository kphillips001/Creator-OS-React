from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

from app.models.pre_generation_commercial_decision import (
    PreGenerationCommercialDecision,
)
from app.models.telegram_inbound import TelegramInboundPayload
from app.services.gpt_service import GPTService
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService


FIRST = "Good morning beautiful did you get all your beauty sleep last night"
SECOND = (
    "I fell asleep thinking about you and I woke up this morning with a "
    "hardon and a smile thinking about you"
)
NOW = datetime(2026, 9, 17, 14, 52, 5, tzinfo=timezone.utc)


def projection(**overrides):
    values = dict(
        fresh_direct_intent=False,
        current_commercial_interest=False,
        commercial_interest_type="NONE",
        referent_present=True,
        grounded_purchase_acceptance=False,
        temporal_deferred=False,
        no_buy_boundary=False,
        classifier_rejected_buying_intent=False,
        deterministic_commercial_evidence=False,
        commercial_bypass_eligible=False,
        active_offer_nudge_candidate=True,
        active_offer_reservation_authorized=False,
        active_offer_reservation_reason="RESERVATION_DENIED",
        mandatory_response_obligation=False,
    )
    values.update(overrides)
    return PreGenerationCommercialDecision(**values)


def test_denied_optional_nudge_authority_falls_through_to_ordinary_chat():
    result, removed = OrdinaryChatReplyService._remove_denied_optional_nudge_authority(
        projection()
    )
    assert removed is True
    assert result.active_offer_nudge_candidate is False
    assert result.active_offer_reservation_authorized is False
    assert result.active_offer_reservation_reason == (
        "OPTIONAL_NUDGE_AUTHORITY_DENIED_FALLTHROUGH"
    )


def test_genuine_current_commercial_denial_remains_blocking():
    original = projection(
        fresh_direct_intent=True,
        current_commercial_interest=True,
        commercial_interest_type="PRICE_REQUEST",
        deterministic_commercial_evidence=True,
        commercial_bypass_eligible=True,
    )
    result, removed = OrdinaryChatReplyService._remove_denied_optional_nudge_authority(
        original
    )
    assert removed is False
    assert result is original
    assert result.active_offer_nudge_candidate is True


@dataclass(frozen=True)
class Item:
    inbound_sender_telegram_user_id: int = 8303003496
    telegram_chat_id: int = 8303003496
    inbound_telegram_message_id: int = 6490
    inbound_received_at: datetime = NOW
    operation_id: str = "op-6490"
    inbound_message_text: str = SECOND


class Repository:
    def __init__(self):
        self.suppressions = []
        self.commercial = None

    def release_due_availability(self, **_): return [Item()]
    def market_tier_priority_buckets(self, *_args, **_kwargs): return {}
    def record_pre_generation_commercial_decision(self, _operation_id, values):
        self.commercial = values
    def suppress_for_market_limit(self, operation_id, **values):
        self.suppressions.append((operation_id, values))
    def buyer_attention_context(self, **_): return {}
    def record_post_nudge_conversation_policy(self, *_args): return None
    def coalesced_burst_messages(self, *_args, **_kwargs):
        return [
            {"operation_id": "op-6489", "message_id": 6489, "text": FIRST},
            {"operation_id": "op-6490", "message_id": 6490, "text": SECOND},
        ]
    def recent_attention_messages(self, *_): return [FIRST, SECOND]
    def record_attention(self, *_): return None


class Commercial:
    def project(self, **_): return projection()


class PostNudge:
    def observe(self, *_args, **_kwargs): return None


class Policy:
    def evaluate(self, **_):
        return SimpleNamespace(
            suppress_optional_reply=False, diagnostics=lambda: {},
        )


class Gate:
    def evaluate(self, **_):
        return SimpleNamespace(allowed=True, reason=None, evidence={})


class Attention:
    def evaluate(self, *_args, **_kwargs):
        return SimpleNamespace(outcome="RESPOND", diagnostics=lambda: {})


def test_joseph_optional_denial_survives_and_preserves_coalesced_context(monkeypatch):
    repository = Repository()
    service = OrdinaryChatReplyService(
        repository=repository,
        creator_profile_id=2,
        fanvue_account_id=2,
        pre_generation_commercial=Commercial(),
        post_nudge_nonconversion=PostNudge(),
        post_nudge_conversation_policy=Policy(),
        market_resource_gate=Gate(),
        attention_service=Attention(),
    )
    monkeypatch.setattr(service, "relationship_scheduling_profile", lambda **_: {
        "high_value_prospect": False, "verified_buyer": False,
        "market_tier": "HIGH",
    })
    monkeypatch.setattr(service, "retry_payload", lambda _item: TelegramInboundPayload(
        telegram_user_id=8303003496,
        telegram_chat_id=8303003496,
        message_text=SECOND,
        message_id=6490,
        received_at=NOW,
    ))

    payloads = service.due_availability_payloads(now=NOW)

    assert len(payloads) == 1
    assert payloads[0].message_id == 6490
    assert payloads[0].chat_history == [{
        "role": "user", "content": FIRST, "telegram_message_id": 6489,
    }]
    assert repository.suppressions == []
    assert repository.commercial["active_offer_nudge_candidate"] is False


def test_joseph_embedded_question_creates_three_bounded_obligations():
    assert set(GPTService._turn_obligations(FIRST, new_relationship=False)) == {
        "RESPOND_TO_GREETING",
        "ANSWER_DIRECT_PERSONAL_QUESTION",
        "ACKNOWLEDGE_COMPLIMENT",
    }
    assert GPTService._direct_personal_question_slot(FIRST) == "REST_SLEEP"


def test_joseph_embedded_question_does_not_require_question_mark():
    result = GPTService._semantic_question(FIRST)
    assert result["detected"] is True
    assert result["type"] == "DIRECT_PERSONAL_QUESTION"


def test_statement_form_is_not_a_question():
    statement = "I did get all my beauty sleep last night"
    assert GPTService._semantic_question(statement)["detected"] is False
    assert "ANSWER_DIRECT_PERSONAL_QUESTION" not in GPTService._turn_obligations(
        statement, new_relationship=False,
    )


def test_vocative_compliment_is_bounded_to_salutation_address():
    assert GPTService._compliment_semantics(FIRST) == {
        "detected": True, "target": "AVA",
    }
    assert GPTService._compliment_semantics(
        "The morning was beautiful near the lake"
    )["detected"] is False


def test_hardon_is_sexual_energy_without_commercial_authority():
    semantics = GPTService._social_flirtation(SECOND)
    assert semantics["sexual"] is True
    assert semantics["commercial"] is False
    assert "ACKNOWLEDGE_SEXUAL_ENERGY" in GPTService._turn_obligations(
        SECOND, new_relationship=False,
    )


def test_sleep_answer_can_satisfy_the_personal_question_without_followup():
    style = GPTService._style_analysis(
        "Morning 😊 yeah, I slept pretty well last night—and you're sweet.",
        FIRST, pressure={}, ordinary=True, memory_callback=False,
        new_relationship=False, recent_responses=[],
    )
    assert style["turnObligationsSatisfied"] is True
    assert style["customerQuestionAnswered"] is True

