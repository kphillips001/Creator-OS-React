from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.purchase_intent import PurchaseIntentStatus
from app.services.private_chat_unlock_gateway_service import (
    PrivateChatUnlockGatewayService,
    UnlockUnavailableError,
)
from app.services.purchase_intent_service import PurchaseIntentService


CLICKED_AT = datetime(2026, 8, 27, 18, 59, 34, tzinfo=timezone.utc)


class IntentRepository:
    def __init__(self, status=PurchaseIntentStatus.PRESENTED, clicked_at=None):
        self.item = SimpleNamespace(
            purchase_intent_id=uuid4(), status=status, clicked_at=clicked_at,
        )
        self.mark_calls = []

    def get(self, _intent_id):
        return self.item

    def mark_clicked(self, _intent_id, *, at):
        self.mark_calls.append(at)
        if self.item.status is PurchaseIntentStatus.PRESENTED:
            self.item = SimpleNamespace(
                **{**vars(self.item), "status": PurchaseIntentStatus.CLICKED,
                   "clicked_at": self.item.clicked_at or at}
            )
        return self.item


def lifecycle(repository):
    return PurchaseIntentService(
        repository=repository, learning_service=SimpleNamespace(
            observe_purchase_intent=lambda *_args, **_kwargs: None
        ), commercial_eligibility=object(), customer_safety_service=object(),
        telegram_identity_repository=object(),
    )


def test_presented_unlock_records_first_click_timestamp_and_repeat_is_idempotent():
    repository = IntentRepository()
    service = lifecycle(repository)
    first = service.record_click(repository.item.purchase_intent_id, clicked_at=CLICKED_AT)
    second = service.record_click(
        repository.item.purchase_intent_id,
        clicked_at=CLICKED_AT.replace(second=55),
    )
    assert first.status is second.status is PurchaseIntentStatus.CLICKED
    assert second.clicked_at == CLICKED_AT
    assert repository.mark_calls == [CLICKED_AT]


def test_purchased_intent_never_regresses_to_clicked():
    purchased_at = CLICKED_AT.replace(minute=1)
    repository = IntentRepository(
        PurchaseIntentStatus.PURCHASED, clicked_at=CLICKED_AT,
    )
    repository.item.purchased_at = purchased_at
    result = lifecycle(repository).record_click(
        repository.item.purchase_intent_id, clicked_at=CLICKED_AT.replace(hour=20)
    )
    assert result.status is PurchaseIntentStatus.PURCHASED
    assert result.clicked_at == CLICKED_AT
    assert repository.mark_calls == []


def evidence(*, complete=True, purchased=False):
    intent_id, grant_id, reservation_id = uuid4(), uuid4(), uuid4()
    intent = SimpleNamespace(
        purchase_intent_id=intent_id,
        status=PurchaseIntentStatus.PRESENTED,
        purchased_at=(CLICKED_AT if purchased else None),
        provider_transaction_order_id=None, provider_payment_id=None,
        provider_event_id=None,
    )
    grant = SimpleNamespace(
        unlock_grant_id=grant_id, purchase_intent_id=intent_id,
        state="ACTIVE", use_count=1, last_used_at=CLICKED_AT,
    )
    reservation = SimpleNamespace(
        fingerprint_reservation_id=reservation_id,
        purchase_intent_id=intent_id, state="ACTIVE",
    ) if complete else None
    runtime = SimpleNamespace(
        purchase_intent_id=intent_id,
        fingerprint_reservation_id=reservation_id, state="ACTIVE",
    ) if complete else None
    repository = SimpleNamespace(
        get_grant_for_intent=lambda _: grant,
        get_reservation_for_intent=lambda _: reservation,
        get_runtime_link_for_intent=lambda _: runtime,
    )
    intents = SimpleNamespace(get=lambda _: intent)
    calls = []
    gateway = PrivateChatUnlockGatewayService(
        repository=repository, intent_repository=intents,
        purchase_intent_lifecycle=SimpleNamespace(
            record_click=lambda item_id, clicked_at: calls.append(
                (item_id, clicked_at)
            ) or intent
        ),
    )
    return gateway, intent, grant, calls


def test_turn11_style_evidence_reconciles_through_canonical_lifecycle():
    gateway, intent, grant, calls = evidence()
    gateway.reconcile_persisted_click(
        intent.purchase_intent_id, unlock_grant_id=grant.unlock_grant_id,
    )
    assert calls == [(intent.purchase_intent_id, CLICKED_AT)]


@pytest.mark.parametrize("complete,purchased", [(False, False), (True, True)])
def test_reconciliation_rejects_incomplete_or_purchase_evidence(complete, purchased):
    gateway, intent, grant, calls = evidence(
        complete=complete, purchased=purchased,
    )
    with pytest.raises(ValueError):
        gateway.reconcile_persisted_click(
            intent.purchase_intent_id, unlock_grant_id=grant.unlock_grant_id,
        )
    assert calls == []


def test_invalid_or_revoked_grant_never_records_click(monkeypatch):
    calls = []
    gateway = PrivateChatUnlockGatewayService(
        repository=SimpleNamespace(resolve_grant=lambda _: None),
        purchase_intent_lifecycle=SimpleNamespace(
            record_click=lambda *_args, **_kwargs: calls.append(True)
        ),
    )
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    with pytest.raises(UnlockUnavailableError):
        gateway.resolve("x" * 64)
    assert calls == []


def test_destination_failure_occurs_after_durable_valid_click(monkeypatch):
    gateway, intent, grant, calls = evidence()
    grant.telegram_user_id = 5; grant.telegram_chat_id = 5
    grant.commercial_offering_id = uuid4(); grant.commercial_publication_id = uuid4()
    grant.fanvue_account_id = 7; grant.currency = "USD"
    intent.telegram_user_id = 5; intent.telegram_chat_id = 5
    intent.commercial_offering_id = grant.commercial_offering_id
    intent.commercial_publication_id = grant.commercial_publication_id
    intent.fanvue_account_id = 7; intent.expected_currency = "USD"
    gateway.repository.resolve_grant = lambda _: grant
    gateway.identities = SimpleNamespace(
        get_verified_by_telegram_user_id=lambda _: object()
    )
    gateway._eligible_publication = lambda _: {
        "delivery_url": "http://127.0.0.1/unsafe", "media_uuids": ("m",),
    }
    gateway._require_controlled_identity_when_enabled = lambda _: None
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    with pytest.raises(UnlockUnavailableError):
        gateway.resolve("x" * 64)
    assert calls == [(intent.purchase_intent_id, CLICKED_AT)]
