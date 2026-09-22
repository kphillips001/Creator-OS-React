from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.purchase_intent import PurchaseIntentStatus
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.services.purchase_intent_service import PurchaseIntentService
from app.services.telegram_purchase_intent_service import TelegramPurchaseIntentService


NOW = datetime(2026, 9, 17, 23, 0, tzinfo=timezone.utc)


class FinalizingRepository:
    def __init__(self, status=PurchaseIntentStatus.CREATED):
        self.item = SimpleNamespace(
            purchase_intent_id=uuid4(), status=status, abandoned_at=None,
        )
        self.calls = 0

    def get(self, _intent_id):
        return self.item

    def finalize_delivery_failed(self, _intent_id, *, at):
        self.calls += 1
        if self.item.status is PurchaseIntentStatus.ABANDONED:
            return self.item, False
        if self.item.status not in {
            PurchaseIntentStatus.CREATED,
            PurchaseIntentStatus.PRESENTED,
            PurchaseIntentStatus.CLICKED,
        }:
            raise ValueError(
                "Purchase Intent delivery-failure finalization conflicts "
                f"with terminal state {self.item.status}."
            )
        self.item = SimpleNamespace(
            **{
                **vars(self.item),
                "status": PurchaseIntentStatus.ABANDONED,
                "abandoned_at": at,
            }
        )
        return self.item, True


class Learning:
    def __init__(self):
        self.events = []

    def observe_purchase_intent(self, intent, outcome, **_kwargs):
        self.events.append((intent.purchase_intent_id, outcome))


def lifecycle(repository, learning):
    return PurchaseIntentService(
        repository=repository, learning_service=learning,
        commercial_eligibility=object(), customer_safety_service=object(),
        telegram_identity_repository=object(), clock=lambda: NOW,
    )


def test_initial_delivery_failure_abandons_and_repeat_is_idempotent():
    repository, learning = FinalizingRepository(), Learning()
    service = lifecycle(repository, learning)

    first = service.mark_delivery_failed(repository.item.purchase_intent_id)
    second = service.mark_delivery_failed(repository.item.purchase_intent_id)

    assert first.status is second.status is PurchaseIntentStatus.ABANDONED
    assert first.abandoned_at == second.abandoned_at == NOW
    assert repository.calls == 2
    assert learning.events == [(first.purchase_intent_id, "DELIVERY_FAILED")]


@pytest.mark.parametrize(
    "status",
    [
        PurchaseIntentStatus.PURCHASED,
        PurchaseIntentStatus.EXPIRED,
        PurchaseIntentStatus.SUPERSEDED,
        PurchaseIntentStatus.ADMIN_CLOSED,
        PurchaseIntentStatus.UNKNOWN,
    ],
)
def test_conflicting_terminal_state_fails_closed(status):
    repository, learning = FinalizingRepository(status), Learning()
    with pytest.raises(ValueError, match="conflicts with terminal state"):
        lifecycle(repository, learning).mark_delivery_failed(
            repository.item.purchase_intent_id
        )
    assert repository.item.status is status
    assert learning.events == []


def test_telegram_delivery_failure_uses_technical_idempotent_boundary():
    calls = []
    intent = SimpleNamespace(purchase_intent_id=uuid4())
    service = TelegramPurchaseIntentService.__new__(TelegramPurchaseIntentService)
    service.intents = SimpleNamespace(
        mark_delivery_failed=lambda intent_id: calls.append(intent_id) or intent
    )
    service._advance_linked_session = lambda *_args, **_kwargs: None

    assert service.abandon_delivery(intent) is intent
    assert calls == [intent.purchase_intent_id]


def canonical_row(status):
    intent_id = uuid4()
    return {
        "purchase_intent_id": intent_id,
        "creator_profile_id": 2,
        "fanvue_account_id": 2,
        "telegram_identity_mapping_id": None,
        "telegram_user_id": 10,
        "telegram_chat_id": 10,
        "external_fanvue_user_uuid": None,
        "commercial_offering_id": uuid4(),
        "commercial_publication_id": uuid4(),
        "provider": "FANVUE",
        "provider_resource_id": "resource",
        "delivery_url": "https://example.test/delivery",
        "telegram_message_id": None,
        "conversation_id": "telegram:10:1",
        "correlation_id": uuid4(),
        "expected_price_minor": 999,
        "expected_currency": "USD",
        "status": status.value,
        "created_at": NOW,
        "presented_at": NOW if status is not PurchaseIntentStatus.CREATED else None,
        "clicked_at": NOW if status in {
            PurchaseIntentStatus.CLICKED, PurchaseIntentStatus.PURCHASED,
        } else None,
        "expires_at": NOW,
        "abandoned_at": NOW if status is PurchaseIntentStatus.ABANDONED else None,
        "purchased_at": NOW if status is PurchaseIntentStatus.PURCHASED else None,
        "provider_transaction_order_id": (
            "order" if status is PurchaseIntentStatus.PURCHASED else None
        ),
        "provider_payment_id": None,
        "provider_event_id": None,
        "attribution_result": (
            "ATTRIBUTED" if status is PurchaseIntentStatus.PURCHASED else "PENDING"
        ),
        "attribution_reason": None,
        "created_metadata": None,
        "updated_at": NOW,
        "purchase_acknowledged_at": None,
        "configured_base_price_minor": None,
        "actual_charged_price_minor": None,
        "identity_bootstrap_mode": "NONE",
        "admin_closed_at": None,
        "administrative_close_reason": None,
    }


class Cursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.current = None

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, *_args): self.current = next(self.rows)
    def fetchone(self): return self.current


class Connection:
    def __init__(self, rows): self.rows = rows
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return Cursor(self.rows)


@pytest.mark.parametrize(
    "status",
    [
        PurchaseIntentStatus.PRESENTED,
        PurchaseIntentStatus.CLICKED,
        PurchaseIntentStatus.ABANDONED,
        PurchaseIntentStatus.PURCHASED,
    ],
)
def test_atomic_finalizer_uses_canonical_repository_mapper(status):
    row = canonical_row(status)
    returned = dict(row)
    if status in {PurchaseIntentStatus.PRESENTED, PurchaseIntentStatus.CLICKED}:
        returned["status"] = PurchaseIntentStatus.ABANDONED.value
        returned["abandoned_at"] = NOW
    rows = [returned] if status in {
        PurchaseIntentStatus.PRESENTED, PurchaseIntentStatus.CLICKED,
    } else [None, row]
    repository = PurchaseIntentRepository(
        connection_factory=lambda: Connection(rows)
    )
    if status in {PurchaseIntentStatus.PRESENTED, PurchaseIntentStatus.CLICKED}:
        result, changed = repository.finalize_delivery_failed(
            row["purchase_intent_id"], at=NOW
        )
        assert changed is True
        assert result.status is PurchaseIntentStatus.ABANDONED
    elif status is PurchaseIntentStatus.ABANDONED:
        result, changed = repository.finalize_delivery_failed(
            row["purchase_intent_id"], at=NOW
        )
        assert changed is False
        assert result.status is PurchaseIntentStatus.ABANDONED
        assert result.created_metadata == {}
    else:
        with pytest.raises(ValueError, match="conflicts with terminal state"):
            repository.finalize_delivery_failed(row["purchase_intent_id"], at=NOW)
