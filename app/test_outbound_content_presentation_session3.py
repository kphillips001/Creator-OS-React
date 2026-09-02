from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.services.customer_content_presentation_validator import CustomerContentPresentationValidator
from app.services.telegram_purchase_intent_service import TelegramPurchaseIntentService


def test_nudge_repetition_and_near_repetition_fail_closed():
    validator = CustomerContentPresentationValidator()
    offering = SimpleNamespace(price_minor=1999)
    lifecycle = {"messagePurpose": "NUDGE", "originalPresentation": "You sure you're ready for this one?"}
    for text in ("You sure you're ready for this one?", "You sure you're ready for this one 😏"):
        result = validator.validate_paid(text, offering=offering, presentation_context={"lifecycle": lifecycle})
        assert result.reason == "PAID_PRESENTATION_REPEATS_ORIGINAL"
    assert validator.validate_paid(
        "I keep thinking about how you reacted to it 😏", offering=offering,
        presentation_context={"lifecycle": lifecycle},
    ).valid


def test_finale_acknowledgement_cannot_imply_another_step():
    result = CustomerContentPresentationValidator().validate_lifecycle(
        "Wait until you see the next one.",
        lifecycle={"purchaseKind": "SESSION_FINALE_PURCHASE"},
    )
    assert result.reason == "PURCHASE_ACKNOWLEDGEMENT_FINALE_CONTINUATION_CLAIM"


def test_nudge_and_acknowledgement_reuse_existing_purchase_intent():
    intent_id = uuid4(); existing = SimpleNamespace(purchase_intent_id=intent_id)
    service = TelegramPurchaseIntentService.__new__(TelegramPurchaseIntentService)
    service.get = lambda value: existing if str(value) == str(intent_id) else None
    payload = SimpleNamespace()
    nudge = SimpleNamespace(diagnostic_metadata={
        "customer_sales_decision": "NUDGE_ACTIVE_OFFER",
        "active_purchase_intent_id": str(intent_id),
    })
    acknowledgement = SimpleNamespace(diagnostic_metadata={
        "customer_sales_decision": "CONGRATULATE_PURCHASE",
        "purchase_acknowledgement_intent_id": str(intent_id),
    })
    assert service.create_before_delivery(nudge, payload) is existing
    assert service.create_before_delivery(acknowledgement, payload) is existing


def test_migration_allows_multiple_crash_safe_lifecycle_deliveries_per_intent():
    sql = Path("migrations/forward/20260824_089_offer_lifecycle_deliveries.sql").read_text()
    assert "DROP CONSTRAINT IF EXISTS telegram_sales_delivery_operations_purchase_intent_id_key" in sql
    assert "idx_telegram_sales_delivery_purchase_intent" in sql
