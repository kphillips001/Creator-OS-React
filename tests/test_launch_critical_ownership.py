from types import SimpleNamespace
from uuid import uuid4

from app.models.sales_session import SalesSessionState
from app.services.customer_contact_authority_service import CustomerContactAuthorityService
from app.models.customer_contact import ContactPurpose, ContactPolicyResult
from app.services.customer_value_attention_service import CustomerValueAttentionService
from app.services.telegram_purchase_intent_service import TelegramPurchaseIntentService


def canonical_value(*, purchases, spend=0):
    return CustomerValueAttentionService().project(commerce_memory={
        "schemaVersion": "test", "verifiedPurchaseCount": purchases,
        "lifetimeGrossMinor": spend, "lastPurchaseAt": "2026-08-29T00:00:00+00:00",
    }).to_mapping()


def test_all_verified_buyer_stages_retain_meaningful_treatment():
    first = canonical_value(purchases=1, spend=300)
    repeat = canonical_value(purchases=3, spend=1200)
    high = canonical_value(purchases=4, spend=20_000)
    whale = canonical_value(purchases=8, spend=60_000)
    assert first["buyerStage"] == "FIRST_TIME_BUYER"
    assert first["buyerProtectionApplied"] is True
    assert repeat["valueTier"] == "REPEAT_BUYER"
    assert repeat["relationshipInvestment"] != "LOW"
    assert high["valueTier"] == "HIGH_VALUE"
    assert whale["valueTier"] == "WHALE"


def test_legacy_whale_and_memory_cannot_create_or_override_purchase_truth():
    projection = CustomerValueAttentionService().project(
        commerce_memory={"schemaVersion": "test", "verifiedPurchaseCount": 0,
                         "lifetimeGrossMinor": 0},
        legacy={"is_whale": True, "buyer_tier": "WHALE", "purchase_count": 99},
    ).to_mapping()
    assert projection["buyerStatus"] == "NONBUYER"
    assert projection["purchaseCount"] == 0
    assert projection["valueTier"] != "WHALE"
    assert "PROVIDER_SPEND_OVERRIDES_LEGACY_WHALE_FLAG" in projection["conflictResolution"]


def test_whale_cannot_bypass_contact_cadence():
    decision = CustomerContactAuthorityService().decide(
        purpose=ContactPurpose.OUTREACH,
        evidence={"buyer_value_tier": "WHALE", "cooldown_active": True},
    )
    assert decision.result is ContactPolicyResult.DEFER


class SessionRepository:
    def __init__(self, session_id): self.session_id = session_id
    def purchase_intent_association(self, _intent_id): return self.session_id, 1


class Sessions:
    def __init__(self):
        self.session_id = uuid4(); self.state = SalesSessionState.ACTIVE
        self.repository = SessionRepository(self.session_id); self.transitions = []
    def get(self, **_): return SimpleNamespace(state=self.state)
    def advance(self, *, state, **_):
        self.transitions.append((self.state.value, state))
        self.state = SalesSessionState(state)
        return SimpleNamespace(state=self.state)


class Intents:
    def __init__(self, intent): self.intent = intent
    def confirm_presented(self, *_args, **_kwargs):
        return type(self.intent)(self.intent.purchase_intent_id, "PRESENTED")
    def acknowledge_purchase(self, *_args, **_kwargs):
        return type(self.intent)(self.intent.purchase_intent_id, "PURCHASED")


def test_session_progression_survives_presentation_and_purchase_acknowledgement():
    intent = SimpleNamespace(purchase_intent_id=uuid4(), status="CREATED")
    # SimpleNamespace cannot be dataclass-replaced; use an immutable tiny record.
    from dataclasses import dataclass
    @dataclass(frozen=True)
    class Intent:
        purchase_intent_id: object
        status: str
    durable = Intent(intent.purchase_intent_id, "CREATED")
    sessions = Sessions()
    service = TelegramPurchaseIntentService(
        creator_profile_id=1, fanvue_account_id=2,
        identity_repository=SimpleNamespace(),
        purchase_intent_service=Intents(durable),
        sales_session_service=sessions,
    )
    service._advance_linked_session(
        durable, target="OFFERING", reason="test")
    presented = service.confirm_delivery(durable, telegram_message_id=9)
    assert presented.status == "PRESENTED"
    acknowledged = service.acknowledge_purchase(durable.purchase_intent_id)
    assert acknowledged.status == "PURCHASED"
    assert sessions.transitions == [
        ("ACTIVE", "OFFERING"),
        ("OFFERING", "AWAITING_PAYMENT"),
        ("AWAITING_PAYMENT", "CONTINUING"),
    ]


def test_active_session_suppresses_free_teaser_but_session_contact_is_allowed():
    authority = CustomerContactAuthorityService()
    teaser = authority.decide(
        purpose=ContactPurpose.FREE_ENGAGEMENT,
        evidence={"active_session": True},
    )
    continuation = authority.decide(
        purpose=ContactPurpose.SESSION_CONTINUATION,
        evidence={"active_session": True},
    )
    assert teaser.result is ContactPolicyResult.SUPPRESS
    assert continuation.result is ContactPolicyResult.ALLOW
