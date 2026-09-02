from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.models.purchase_intent import AttributionResult, PurchaseIntent, PurchaseIntentStatus
from app.services.purchase_intent_service import PurchaseIntentService


NOW = datetime.now(timezone.utc)
REASON = "CONTROLLED_TEST_FRESH_PRESENTATION_CERTIFICATION"


def intent(status=PurchaseIntentStatus.PRESENTED):
    return PurchaseIntent(
        purchase_intent_id=uuid4(), creator_profile_id=2, fanvue_account_id=2,
        telegram_identity_mapping_id=None, telegram_user_id=7857064998,
        telegram_chat_id=7857064998, external_fanvue_user_uuid=None,
        commercial_offering_id=uuid4(), commercial_publication_id=uuid4(),
        provider="FANVUE", provider_resource_id="resource", delivery_url="https://fanvue.com/x",
        telegram_message_id=5460, conversation_id="historical", correlation_id=uuid4(),
        expected_price_minor=300, expected_currency="USD", status=status,
        created_at=NOW, presented_at=NOW if status is not PurchaseIntentStatus.CREATED else None,
        clicked_at=None, expires_at=NOW + timedelta(days=2), abandoned_at=None,
        purchased_at=NOW if status is PurchaseIntentStatus.PURCHASED else None,
        provider_transaction_order_id=None, provider_payment_id=None, provider_event_id=None,
        attribution_result=(AttributionResult.ATTRIBUTED if status is PurchaseIntentStatus.PURCHASED else AttributionResult.PENDING),
        attribution_reason=None, created_metadata={"commercial_intelligence": {"decision": "PRESENT_OFFER"}},
        updated_at=NOW, configured_base_price_minor=300,
    )


class Repository:
    def __init__(self, item): self.item=item; self.calls=[]
    def get(self, _id): return self.item
    def close_administratively(self, intent_id, **values):
        self.calls.append((intent_id, values))
        if self.item.status is PurchaseIntentStatus.ADMIN_CLOSED:
            return self.item
        self.item=replace(self.item,status=PurchaseIntentStatus.ADMIN_CLOSED,
                          admin_closed_at=values["at"],administrative_close_reason=values["reason_code"])
        return self.item


def service(monkeypatch, status):
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TEST_ENABLED", "true")
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TELEGRAM_USER_ID", "7857064998")
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TELEGRAM_CHAT_ID", "7857064998")
    repo=Repository(intent(status))
    return PurchaseIntentService(repository=repo,learning_service=object(),
        commercial_eligibility=object(),customer_safety_service=object(),
        telegram_identity_repository=object(),clock=lambda: NOW),repo


@pytest.mark.parametrize("status", [PurchaseIntentStatus.CREATED, PurchaseIntentStatus.PRESENTED])
def test_controlled_admin_close_supports_created_and_presented(monkeypatch,status):
    svc,repo=service(monkeypatch,status); before=repo.item
    result=svc.close_administratively(before.purchase_intent_id,reason_code=REASON)
    assert result.status is PurchaseIntentStatus.ADMIN_CLOSED
    assert result.administrative_close_reason == REASON
    assert (result.purchase_intent_id,result.commercial_offering_id,result.expected_price_minor,
            result.expected_currency,result.telegram_message_id,result.provider_resource_id,
            result.created_metadata) == (before.purchase_intent_id,before.commercial_offering_id,
            before.expected_price_minor,before.expected_currency,before.telegram_message_id,
            before.provider_resource_id,before.created_metadata)


def test_purchased_cannot_be_admin_closed(monkeypatch):
    svc,repo=service(monkeypatch,PurchaseIntentStatus.PURCHASED)
    with pytest.raises(ValueError,match="Invalid Purchase Intent transition"):
        svc.close_administratively(repo.item.purchase_intent_id,reason_code=REASON)
    assert repo.calls == []


def test_admin_close_is_idempotent(monkeypatch):
    svc,repo=service(monkeypatch,PurchaseIntentStatus.PRESENTED)
    first=svc.close_administratively(repo.item.purchase_intent_id,reason_code=REASON)
    second=svc.close_administratively(repo.item.purchase_intent_id,reason_code=REASON)
    assert first == second
    assert len(repo.calls) == 2


def test_admin_close_requires_controlled_operator_boundary(monkeypatch):
    svc,repo=service(monkeypatch,PurchaseIntentStatus.PRESENTED)
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TEST_ENABLED", "false")
    with pytest.raises(PermissionError,match="authorization"):
        svc.close_administratively(repo.item.purchase_intent_id,reason_code=REASON)
    assert repo.calls == []


def test_schema_and_repository_define_atomic_preserving_close():
    root=Path(__file__).resolve().parents[1]
    migration=(root/"migrations/forward/20260827_097_purchase_intent_administrative_close.sql").read_text()
    repository=(root/"app/repositories/purchase_intent_repository.py").read_text()
    assert "'ADMIN_CLOSED'" in migration
    assert "admin_closed_at" in migration and "administrative_close_reason" in migration
    assert "FOR UPDATE" in repository
    assert "state='REVOKED'" in repository
    assert "use_count" not in repository[repository.index("def close_administratively"):repository.index("def get_active_for_buyer")]
    assert "DELETE" not in repository[repository.index("def close_administratively"):repository.index("def get_active_for_buyer")]


def test_admin_closed_is_not_active_and_remains_attribution_auditable():
    from app.models.purchase_intent import ACTIVE_PURCHASE_INTENT_STATUSES
    from app.services.commerce_signal_service import CommerceSignalService
    assert PurchaseIntentStatus.ADMIN_CLOSED not in ACTIVE_PURCHASE_INTENT_STATUSES
    source=Path(CommerceSignalService.__module__.replace('.', '/') + '.py')
    assert "ADMIN_CLOSED" in source.read_text()
