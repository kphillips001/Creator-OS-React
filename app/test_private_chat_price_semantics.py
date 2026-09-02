from pathlib import Path
import pytest

from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.testing.postgres_safety import require_isolated_test_database_url


def test_unlock_creation_never_writes_actual_charged_price():
    source = Path("app/services/private_chat_unlock_gateway_service.py").read_text()
    assert "actual_charged_price_minor=reservation.exact_price_minor" not in source
    assert 'identity_bootstrap_mode="PRIVATE_CHAT_FINGERPRINT"' in source


def test_provider_settlement_is_actual_charged_price_authority():
    source = Path("app/services/private_chat_purchase_settlement_service.py").read_text()
    assert "actual_charged_price_minor=%s" in source
    assert "gross_minor, intent[\"purchase_intent_id\"]" in source


def test_reconciliation_is_narrow_and_idempotent():
    source = Path("app/repositories/purchase_intent_repository.py").read_text()
    method = source[source.index("def clear_unsettled_actual_charged_price"):]
    for guard in (
        "intent.status='CLICKED'", "intent.purchased_at IS NULL",
        "intent.provider_transaction_order_id IS NULL",
        "intent.provider_payment_id IS NULL", "intent.provider_event_id IS NULL",
        "intent.purchase_acknowledged_at IS NULL",
        "intent.attribution_result='PENDING'", "reservation.state='ACTIVE'",
        "session.state='AWAITING_PAYMENT'",
        "session.actual_fingerprint_price_minor IS NULL",
        "actual_charged_price_minor=NULL",
    ):
        assert guard in method


def test_test_database_guard_rejects_production_and_non_test_names():
    production = "postgresql://operator:secret@localhost:5432/creator_os"
    with pytest.raises(ValueError):
        require_isolated_test_database_url(production, production)
    with pytest.raises(ValueError):
        require_isolated_test_database_url(
            "postgresql://operator:secret@localhost:5432/another_database",
            production,
        )
    assert require_isolated_test_database_url(
        "postgresql://operator:secret@localhost:5432/creator_os_test",
        production,
    ).endswith("/creator_os_test")
