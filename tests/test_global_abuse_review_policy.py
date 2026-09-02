from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.contextual_customer_tone_service import ContextualCustomerToneService
from app.services.customer_abuse_policy_service import CustomerAbusePolicyService
from app.services.commercial_receptiveness_service import CommercialReceptivenessService
from app.services.customer_value_attention_service import CustomerValueAttentionService
from app.services.gpt_service import GPTService
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService


class FakeProspects:
    def __init__(self): self.block = None
    def contact_block(self, prospect): return self.block
    def record_contact_block(self, **values):
        self.block = {"state": "PERMANENT_BLOCKED", "reason": values["reason"]}


class FakeRepository:
    def __init__(self): self.incident = None; self.created = 0
    def active_for_customer(self, **_): return self.incident
    def create_or_append_open(self, **values):
        if self.incident:
            self.incident["evidence_count"] += 1
            return {**self.incident, "created": False}
        self.created += 1
        self.incident = {**values, "incident_id": uuid4(), "review_status": "OPEN",
                         "interaction_hold_active": True, "evidence_count": 1}
        return {**self.incident, "created": True}
    def resolve(self, *, target_status, **_):
        if not self.incident or self.incident["review_status"] != "OPEN": return None
        self.incident.update(review_status=target_status,
                             interaction_hold_active=target_status == "MANUALLY_BLOCKED")
        return self.incident


class FakeAlerts:
    def __init__(self, state="SENT_CONFIRMED"): self.calls = 0; self.state = state
    def authorize_and_attempt(self, **_):
        self.calls += 1
        return {"state": self.state, "attempted_at": object()}


def _evaluate(service, *, mapped=False, message="you are a worthless idiot"):
    identity = SimpleNamespace(fanvue_account_id=2, local_fanvue_user_id=3) if mapped else None
    return service.evaluate_current(
        creator_profile_id=1, fanvue_account_id=2, telegram_user_id=99,
        telegram_chat_id=99, inbound_message_id=7, correlation_id="in:7",
        message=message, canonical_identity=identity, recent_transcript=[],
        prospect=SimpleNamespace(relationship_state={}), telegram_username="test",
    )


@pytest.mark.parametrize("message", [
    "no thanks", "that's too expensive", "this is disappointing",
    "seriously?", "you're trying too hard",
])
def test_mild_negativity_never_qualifies(message):
    result = ContextualCustomerToneService().classify(message=message)
    assert result["qualifyingAbuse"] is False


def test_unmapped_qualifying_abuse_durably_blocks():
    prospects = FakeProspects()
    service = CustomerAbusePolicyService(repository=FakeRepository(),
        prospect_service=prospects, alert_service=FakeAlerts())
    decision = _evaluate(service)
    assert decision.suppressed is True
    assert decision.code == "TELEGRAM_ABUSE_AUTO_BLOCKED"
    assert prospects.block["state"] == "PERMANENT_BLOCKED"
    future = service.existing_authority(creator_profile_id=1, fanvue_account_id=2,
        telegram_user_id=99, canonical_identity=None,
        prospect=SimpleNamespace(relationship_state={}))
    assert future.suppressed is True


def test_mapped_abuse_opens_hold_and_deduplicates_alert():
    repository, alerts = FakeRepository(), FakeAlerts()
    service = CustomerAbusePolicyService(repository=repository,
        prospect_service=FakeProspects(), alert_service=alerts)
    first = _evaluate(service, mapped=True)
    second = _evaluate(service, mapped=True)
    assert first.code == "CUSTOMER_ABUSE_REVIEW_HOLD"
    assert first.diagnostics["operatorAlertConfirmed"] is True
    assert second.suppressed is True
    assert repository.created == 1
    assert alerts.calls == 1


def test_mapped_alert_failure_preserves_hold_not_permanent_block():
    repository = FakeRepository()
    service = CustomerAbusePolicyService(repository=repository,
        prospect_service=FakeProspects(), alert_service=FakeAlerts("FAILED"))
    result = _evaluate(service, mapped=True)
    assert result.diagnostics["operatorAlertFailed"] is True
    assert repository.incident["review_status"] == "OPEN"


def test_operator_release_and_manual_block_are_distinct():
    repository = FakeRepository()
    service = CustomerAbusePolicyService(repository=repository,
        prospect_service=FakeProspects(), alert_service=FakeAlerts())
    incident = _evaluate(service, mapped=True).diagnostics["abuseReviewIncidentId"]
    released = service.release(incident_id=incident, reviewed_by="op", reason="reviewed")
    assert released["review_status"] == "RELEASED"
    repository.incident = None
    incident = _evaluate(service, mapped=True).diagnostics["abuseReviewIncidentId"]
    blocked = service.manual_block(incident_id=incident, reviewed_by="op", reason="reviewed")
    assert blocked["review_status"] == "MANUALLY_BLOCKED"
    assert blocked["interaction_hold_active"] is True


@pytest.mark.parametrize(("message", "expected"), [
    ("what are you offering?", "COMMERCIAL_CURIOSITY"),
    ("I want to see your private content", "DIRECT_CONTENT_INTENT"),
    ("how much is it?", "PRICE_REQUEST"),
    ("send me the link", "SEND_OR_LINK_REQUEST"),
    ("sold, I'll buy it", "PURCHASE_ACCEPTANCE"),
    ("how was your day?", "NONE"),
])
def test_semantic_commercial_interest_types(message, expected):
    assert CommercialReceptivenessService.commercial_interest_type(message) == expected


def test_semantic_interest_bypasses_low_cost_nurture_without_forcing_buying_intent():
    projection = CustomerValueAttentionService().project(
        commerce_memory={"verifiedPurchaseCount": 0},
        behavior={"inbound_message_count": 12,
                  "failed_nonconverted_opportunity_count": 2,
                  "rejection_count": 2,
                  "commercial_interest_type": "COMMERCIAL_CURIOSITY"},
    )
    assert projection.low_cost_nurture_eligible is True
    assert projection.nurture_bypassed_for_commercial_intent is True
    assert projection.fresh_commercial_intent_detected is False


def test_supporter_boundary_prompt_is_semantic_and_not_repeated():
    first = GPTService._build_supporter_attention_instruction({
        "customer_value_attention": {"lowCostNurtureActive": True},
        "conversational_memory": {},
    })
    later = GPTService._build_supporter_attention_instruction({
        "customer_value_attention": {"lowCostNurtureActive": True},
        "conversational_memory": {"supporterAttentionBoundary": {"delivered": True}},
    })
    assert "own varied wording" in first
    assert "Do not repeat" in later


def test_supporter_boundary_persists_only_after_confirmed_delivery():
    calls = []
    service = OrdinaryChatReplyService(
        repository=SimpleNamespace(),
        prospect_service=SimpleNamespace(
            record_supporter_boundary_delivery=lambda **values: calls.append(values)
        ),
    )
    operation = SimpleNamespace(correlation_id="op:1", response_payload={
        "diagnostic_metadata": {
            "supporter_attention_boundary_pending_confirmation": True,
            "pending_supporter_attention_boundary_context": {
                "creator_profile_id": 1, "fanvue_account_id": 2,
                "telegram_user_id": 3, "correlation_id": "in:1",
            },
        }
    })
    assert calls == []
    service._finalize_confirmed_supporter_boundary(operation, telegram_message_id=44)
    assert calls[0]["provider_message_id"] == 44
