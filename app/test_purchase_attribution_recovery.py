from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.purchase_attribution_recovery_service import PurchaseAttributionRecoveryService


NOW = datetime.now(timezone.utc)
BUYER = uuid4()
RECONCILIATION = uuid4()
INTENT = uuid4()


def review(**changes):
    values = {
        "reconciliation_id": RECONCILIATION, "state": "VERIFIED",
        "attribution_state": "UNKNOWN", "attribution_reason": "MULTIPLE_HARD_MATCHING_CANDIDATES",
        "last_error": None, "display_name": "Buyer", "handle": "buyer",
        "telegram_user_id": 123, "external_fanvue_user_uuid": BUYER,
        "transaction_order_id": "order-1", "payment_timestamp": NOW,
        "gross_minor": 999, "net_minor": 800, "expected_amount_minor": 999,
        "earnings_record": {"currency": "USD"}, "purchase_source": "media",
        "purchase_type": "media", "fanvue_account_id": 7,
        "customer_commerce_profile_id": uuid4(),
    }
    values.update(changes)
    return values


def candidate(state="CONFIRMED", **changes):
    values = {
        "purchase_intent_id": INTENT, "commercial_offering_id": uuid4(),
        "commercial_publication_id": uuid4(), "offering_title": "Gold Single",
        "offering_type": "SINGLE_IMAGE", "expected_price_minor": 999,
        "expected_currency": "USD", "external_product_id": "link-1",
        "provider_resource_id": "link-1", "publication_delivery_url": "https://fanvue.com/link-1",
        "delivery_url": "https://fanvue.com/link-1", "presented_at": NOW,
        "telegram_delivery_state": state, "outbound_telegram_message_id": 901,
        "telegram_message_id": 901, "sales_session_id": None,
        "source_photoshoot_deliverable_id": uuid4(),
    }
    values.update(changes)
    return values


class Repository:
    def __init__(self, item=None, candidates=None, error=None):
        self.item = item or review(); self.candidates = candidates or [candidate()]
        self.error = error; self.commits = 0; self.audit = None
    def list_unresolved(self, **_): return [self.item]
    def get_unresolved(self, **_): return self.item
    def list_candidates(self, **_): return self.candidates
    def commit_manual(self, **values):
        if self.error: raise ValueError(self.error)
        self.commits += 1
        if self.audit is None:
            self.audit = {"resolution_id": uuid4(), "reconciliation_id": RECONCILIATION,
                          "purchase_intent_id": values["purchase_intent_id"],
                          "transaction_order_id": "order-1",
                          "downstream_completed_at": None}
        return (self.audit, self.commits > 1)
    def mark_downstream_completed(self, _):
        self.audit = {**self.audit, "downstream_completed_at": NOW}
        return self.audit


class Intents:
    def __init__(self, offering_type="SINGLE_IMAGE"):
        self.item = SimpleNamespace(
            purchase_intent_id=INTENT, status=SimpleNamespace(value="PURCHASED"),
            attribution_result=SimpleNamespace(value="ATTRIBUTED"),
            commercial_offering_id=uuid4(), offering_type=offering_type,
        )
        self.observed = []
    def get(self, _): return self.item
    def observe(self, *args, **kwargs): self.observed.append((args, kwargs))


class Lifecycles:
    def __init__(self): self.calls = []
    def synchronize_attributed_purchase(self, **values): self.calls.append(values); return object()


def build(repo=None, offering_type="SINGLE_IMAGE"):
    intents = Intents(offering_type); lifecycles = Lifecycles()
    service = PurchaseAttributionRecoveryService(
        repository=repo or Repository(), intent_repository=intents,
        intent_service=intents, photoshoot_lifecycle_service=lifecycles,
    )
    return service, intents, lifecycles


def test_pending_and_unknown_queue_contains_human_evidence():
    service, _, _ = build()
    item = service.queue(creator_profile_id=2)["items"][0]
    assert item["attributionState"] == "UNKNOWN"
    assert item["transactionOrderId"] == "order-1"
    assert item["customer"] == "Buyer"


def test_confirmed_and_ambiguous_telegram_evidence_are_distinct():
    repo = Repository(candidates=[candidate("CONFIRMED"), candidate(
        "AMBIGUOUS", purchase_intent_id=uuid4(), outbound_telegram_message_id=None
    )])
    service, _, _ = build(repo)
    items = service.detail(creator_profile_id=2, reconciliation_id=RECONCILIATION)["candidates"]
    assert "Telegram message confirmed" in items[0]["supportingEvidence"]
    assert "Telegram message confirmed" not in items[1]["supportingEvidence"]
    assert any("No confirmed Telegram" in value for value in items[1]["warnings"])


@pytest.mark.parametrize("state", ["CREATED", "SENDING", "AMBIGUOUS", "FAILED", None])
def test_unproven_delivery_cannot_be_selected_for_manual_attribution(state):
    service, _, _ = build(Repository(candidates=[candidate(state)]))
    item = service.detail(
        creator_profile_id=2, reconciliation_id=RECONCILIATION
    )["candidates"][0]
    assert item["canManuallyAttribute"] is False
    assert item["warnings"] == [
        "Cannot attribute: No confirmed Telegram presentation evidence."
    ]


@pytest.mark.parametrize("state", ["TELEGRAM_ACCEPTED", "CONFIRMED"])
def test_provider_proven_delivery_is_manual_presentation_evidence(state):
    service, _, _ = build(Repository(candidates=[candidate(state)]))
    item = service.detail(
        creator_profile_id=2, reconciliation_id=RECONCILIATION
    )["candidates"][0]
    assert item["canManuallyAttribute"] is True
    assert item["warnings"] == []


@pytest.mark.parametrize("offering_type", ["SINGLE_IMAGE", "BUNDLE", "SESSION_STEP"])
def test_manual_single_bundle_and_session_converge_through_canonical_lifecycle(offering_type):
    service, intents, lifecycles = build(offering_type=offering_type)
    result = service.attribute(
        creator_profile_id=2, reconciliation_id=RECONCILIATION,
        purchase_intent_id=INTENT, operator_note="Reviewed evidence",
    )
    assert result["attributionState"] == "MANUALLY_ATTRIBUTED"
    assert len(lifecycles.calls) == 1
    assert len(intents.observed) == 1


def test_duplicate_manual_submission_does_not_repeat_downstream_effects():
    repo = Repository(); service, intents, lifecycles = build(repo)
    first = service.attribute(creator_profile_id=2, reconciliation_id=RECONCILIATION,
                              purchase_intent_id=INTENT)
    second = service.attribute(creator_profile_id=2, reconciliation_id=RECONCILIATION,
                               purchase_intent_id=INTENT)
    assert first["idempotentReplay"] is False
    assert second["idempotentReplay"] is True
    assert len(lifecycles.calls) == 1
    assert len(intents.observed) == 1


@pytest.mark.parametrize("reason", [
    "Customer does not match the unresolved transaction.",
    "Creator does not match the unresolved transaction.",
    "Fanvue account does not match the unresolved transaction.",
    "Purchase amount does not match the Purchase Intent.",
    "Purchase currency does not match the Purchase Intent.",
    "Authoritative purchase currency is unavailable.",
    "No confirmed Telegram presentation evidence.",
    "Purchase Intent was created after the transaction.",
    "Fanvue provider resource does not match the Purchase Intent.",
    "Transaction is already attributed to another Purchase Intent.",
])
def test_hard_integrity_rejections_are_propagated(reason):
    service, _, lifecycles = build(Repository(error=reason))
    with pytest.raises(ValueError, match=reason.replace(".", "\\.")):
        service.attribute(creator_profile_id=2, reconciliation_id=RECONCILIATION,
                          purchase_intent_id=INTENT)
    assert lifecycles.calls == []


def test_leaving_unresolved_has_no_downstream_effect():
    service, intents, lifecycles = build()
    service.detail(creator_profile_id=2, reconciliation_id=RECONCILIATION)
    assert lifecycles.calls == []
    assert intents.observed == []


def test_migration_and_repository_encode_hard_invariants_and_audit():
    migration = open("migrations/forward/20260824_081_purchase_attribution_recovery.sql", encoding="utf-8").read()
    repository = open("app/repositories/purchase_attribution_recovery_repository.py", encoding="utf-8").read()
    assert "purchase_attribution_resolution_audit" in migration
    assert "MANUALLY_ATTRIBUTED" in migration
    for evidence in ("Creator does not match", "Fanvue account does not match",
                     "Customer does not match", "Purchase amount does not match",
                     "Purchase currency does not match", "already attributed",
                     "No confirmed Telegram presentation evidence",
                     "state IN ('TELEGRAM_ACCEPTED','CONFIRMED')"):
        assert evidence in repository
