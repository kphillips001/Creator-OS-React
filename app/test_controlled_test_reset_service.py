from app.services.controlled_test_reset_service import ControlledTestResetService
from app.models.telegram_inbound import TelegramInboundPayload
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from datetime import datetime, timezone
import pytest


class Boundary:
    def __init__(self, identity): self.identity = identity
    def configured_identity(self): return self.identity


def service(identity=(12345, 12345)):
    return ControlledTestResetService(boundary=Boundary(identity))


def clean_checks(**changes):
    values = {"configured_identity_match": True, "mapping_count": 0,
        "purchase_intent_count": 0, "settled_purchase_intent_count": 0,
        "customer_transaction_count": 0, "purchased_fingerprint_count": 0,
        "active_runtime_media_link_count": 0, "session_purchase_count": 0}
    values.update(changes); return values


def test_reset_preview_allows_only_clean_configured_identity():
    result = service()._preview(12345, clean_checks(), {"ordinaryReplyOperations": 2})
    assert result["allowed"] is True
    assert result["identity"] != "12345"
    assert "unrelated commerce records" in result["wouldPreserve"]


def test_reset_precondition_blockers_fail_closed():
    cases = {
        "mapping_count": "controlled customer is mapped",
        "settled_purchase_intent_count": "a settled PurchaseIntent exists",
        "customer_transaction_count": "a customer transaction exists",
        "purchased_fingerprint_count": "a purchased fingerprint exists",
        "active_runtime_media_link_count": "an active/purchased runtime Media Link exists",
        "session_purchase_count": "a Session purchase exists",
    }
    for key, message in cases.items():
        result = service()._preview(12345, clean_checks(**{key: 1}), {})
        assert result["allowed"] is False and message in result["blockers"]


def test_unsettled_purchase_intent_is_preserved_and_blocks_reset():
    result = service()._preview(12345, clean_checks(purchase_intent_count=1), {})
    assert result["allowed"] is False
    assert "not every controlled PurchaseIntent is proven disposable" in result["blockers"]


def disposable_intent(**changes):
    values = {
        "status": "CREATED", "telegram_user_id": 12345,
        "telegram_chat_id": 12345, "purchased_at": None,
        "purchase_acknowledged_at": None, "provider_transaction_order_id": None,
        "provider_payment_id": None, "provider_event_id": None,
        "actual_charged_price_minor": None, "presented_at": None,
        "clicked_at": None, "attribution_result": "PENDING",
    }
    values.update(changes)
    return values


def disposable_evidence(**changes):
    values = {
        "controlled_scope": True, "successful_delivery": False,
        "consumed_unlock": False, "purchased_fingerprint": False,
        "provider_runtime_evidence": False, "attribution_audit_count": 0,
        "provider_runtime_operation_evidence": False,
        "attributed_reconciliation_count": 0, "session_association_count": 0,
        "session_history_count": 0, "photoshoot_lifecycle_count": 0,
        "photoshoot_lifecycle_event_count": 0, "provider_ownership_count": 0,
        "entitlement_count": 0, "provisional_session_count": 0,
        "disposable_provisional_session_count": 0,
    }
    values.update(changes)
    return values


def test_created_unsettled_controlled_intent_is_explicitly_disposable():
    result = service()._disposal_eligibility(
        disposable_intent(), disposable_evidence(), 12345, 12345,
    )
    assert result["eligible"] is True
    checks = clean_checks(
        purchase_intent_count=1,
        disposable_purchase_intents=[{
            "purchase_intent_id": "intent-1", "state": "CREATED",
            "reason": result["reason"],
        }],
        purchase_intent_disposal_blockers=[],
    )
    assert service()._preview(12345, checks, {})["allowed"] is True


@pytest.mark.parametrize(("intent_change", "evidence_change"), (
    ({"status": "PURCHASED", "purchased_at": datetime.now(timezone.utc)}, {}),
    ({"provider_transaction_order_id": "transaction"}, {}),
    ({}, {"purchased_fingerprint": True}),
    ({}, {"provider_runtime_evidence": True}),
    ({}, {"successful_delivery": True}),
    ({"purchase_acknowledged_at": datetime.now(timezone.utc)}, {}),
    ({}, {"session_association_count": 1}),
    ({}, {"provider_ownership_count": 1}),
    ({}, {"entitlement_count": 1}),
    ({}, {"attributed_reconciliation_count": 1}),
))
def test_purchase_or_delivery_evidence_blocks_disposal(intent_change, evidence_change):
    result = service()._disposal_eligibility(
        disposable_intent(**intent_change), disposable_evidence(**evidence_change),
        12345, 12345,
    )
    assert result["eligible"] is False


def test_other_account_or_customer_scope_cannot_be_disposed():
    result = service()._disposal_eligibility(
        disposable_intent(), disposable_evidence(controlled_scope=False),
        12345, 12345,
    )
    assert result["eligible"] is False


def test_unmapped_identity_still_requires_exact_private_chat_scope():
    result = service()._disposal_eligibility(
        disposable_intent(telegram_chat_id=99999),
        disposable_evidence(controlled_scope=False), 12345, 12345,
    )
    assert result["eligible"] is False


def test_disposable_cleanup_is_empty_idempotent_and_preserves_commerce_authorities():
    class Cursor:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("empty cleanup must not execute SQL")
    removed = service()._delete_disposable_intents(Cursor(), [])
    assert removed["disposablePurchaseIntents"] == 0
    preview = service()._preview(12345, clean_checks(), {})
    assert preview["allowed"] is True
    assert "unrelated commerce records" in preview["wouldPreserve"]
    assert "Content Vault" in preview["wouldPreserve"]
    assert any("$3 SINGLE" in item for item in preview["wouldPreserve"])


def test_disposable_cleanup_reports_dependents_and_is_repeatable():
    class Cursor:
        def __init__(self):
            self.remaining = {
                "fanvue_runtime_media_link_operations": 1,
                "fanvue_runtime_media_links": 1,
                "telegram_unlock_grants": 1,
                "fanvue_fingerprint_reservations": 1,
                "telegram_sales_delivery_operations": 1,
                "commerce_recommendation_outcomes": 1,
                "telegram_provisional_sales_sessions": 1,
                "purchase_intents": 1,
            }
            self.rowcount = 0

        def execute(self, sql, _params):
            table = next(name for name in self.remaining if f"DELETE FROM {name}" in sql)
            self.rowcount = self.remaining[table]
            self.remaining[table] = 0

    cursor = Cursor()
    disposable = [{
        "purchase_intent_id": "intent-1", "state": "CREATED",
        "reason": "provably disposable",
    }]
    first = service()._delete_disposable_intents(cursor, disposable)
    second = service()._delete_disposable_intents(cursor, disposable)
    assert first["disposablePurchaseIntents"] == 1
    assert first["dependentUnlockGrants"] == 1
    assert first["dependentFingerprintReservations"] == 1
    assert first["dependentRuntimeMediaLinks"] == 1
    assert first["dependentRuntimeMediaLinkOperations"] == 1
    assert first["dependentPaidDeliveryOperations"] == 1
    assert first["dependentProvisionalSessions"] == 1
    assert second["disposablePurchaseIntents"] == 0


def test_browser_cannot_supply_an_arbitrary_reset_identity():
    assert service()._identity() == (12345, 12345)
    assert not hasattr(service(), "telegram_user_id")


def test_inbound_capture_is_passed_to_canonical_idempotent_operation_key():
    class Repository:
        def get_or_create(self, **values):
            self.values = values
            return object(), True
    repository = Repository()
    received = datetime(2026, 8, 26, tzinfo=timezone.utc)
    payload = TelegramInboundPayload(telegram_user_id=12345, telegram_chat_id=12345,
        message_text="exact text", message_id=77, received_at=received)
    OrdinaryChatReplyService(repository=repository).begin(payload)
    assert repository.values["account_scope"] == "AVA_TELETHON_PRIVATE"
    assert repository.values["chat_id"] == 12345
    assert repository.values["inbound_message_id"] == 77
    assert repository.values["inbound_message_text"] == "exact text"
    assert repository.values["inbound_received_at"] == received
