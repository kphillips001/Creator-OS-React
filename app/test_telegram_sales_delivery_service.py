from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.telegram_sales_delivery_operation import (
    TelegramSalesDeliveryOperation, TelegramSalesDeliveryState,
)
from app.services.telegram_sales_delivery_service import TelegramSalesDeliveryService


NOW = datetime.now(timezone.utc)


def operation(state=TelegramSalesDeliveryState.CREATED, message_id=None):
    return TelegramSalesDeliveryOperation(
        operation_id=uuid4(), correlation_id="telegram:12:56",
        creator_profile_id=3, fanvue_account_id=2,
        conversation_thread_id=77, fanvue_user_id=9,
        telegram_chat_id=12, inbound_telegram_message_id=56,
        outbound_telegram_message_id=message_id,
        purchase_intent_id=uuid4(), commercial_offering_id=uuid4(),
        commercial_publication_id=uuid4(), response_text="Offer link",
        delivery_payload={"message_text": "Offer link"}, state=state,
        failure_reason=None, created_at=NOW, sending_at=None,
        telegram_accepted_at=(NOW if message_id is not None else None),
        confirmed_at=None, failed_at=None,
        updated_at=NOW,
    )


class MemoryRepository:
    def __init__(self, item=None):
        self.item = item
        self.events = []
        self.confirm_error = None

    def get_by_correlation(self, correlation):
        return self.item if self.item and self.item.correlation_id == correlation else None

    def claim_created(self, operation_id):
        if self.item.operation_id != operation_id or self.item.state not in {
            TelegramSalesDeliveryState.CREATED,
            TelegramSalesDeliveryState.RETRYABLE,
        }:
            return None
        self.item = replace(self.item, state=TelegramSalesDeliveryState.SENDING)
        return self.item

    def mark_accepted(self, operation_id, message_id):
        self.item = replace(self.item, state=TelegramSalesDeliveryState.TELEGRAM_ACCEPTED,
                            outbound_telegram_message_id=message_id)
        return self.item

    def mark_confirmed(self, operation_id):
        if self.confirm_error:
            raise self.confirm_error
        self.events.append("confirmed")
        self.item = replace(self.item, state=TelegramSalesDeliveryState.CONFIRMED)
        return self.item

    def confirm_purchase_acknowledgement(self, operation_id):
        if self.confirm_error:
            raise self.confirm_error
        self.events.extend(("confirmed", "acknowledged"))
        self.item = replace(
            self.item, state=TelegramSalesDeliveryState.CONFIRMED,
            confirmed_at=self.item.confirmed_at or NOW,
        )
        return self.item

    def mark_failed(self, operation_id, reason):
        self.item = replace(self.item, state=TelegramSalesDeliveryState.FAILED,
                            failure_reason=reason)
        return self.item

    def mark_ambiguous(self, operation_id, reason):
        self.item = replace(self.item, state=TelegramSalesDeliveryState.AMBIGUOUS,
                            failure_reason=reason)
        return self.item

    def mark_retryable(self, operation_id, reason):
        self.item = replace(self.item, state=TelegramSalesDeliveryState.RETRYABLE,
                            failure_reason=reason)
        return self.item

    def mark_sending_ambiguous(self):
        if self.item and self.item.state is TelegramSalesDeliveryState.SENDING:
            self.item = replace(self.item, state=TelegramSalesDeliveryState.AMBIGUOUS)
            return [self.item]
        return []

    def list_accepted(self, **_):
        return [self.item] if self.item and self.item.state is TelegramSalesDeliveryState.TELEGRAM_ACCEPTED else []

    def list_confirmed_unacknowledged_acknowledgements(self):
        return []


class Intents:
    def __init__(self, item):
        self.item = SimpleNamespace(purchase_intent_id=item.purchase_intent_id)
        self.presented = []

    def get(self, intent_id):
        assert intent_id == self.item.purchase_intent_id
        return self.item

    def confirm_delivery(self, intent, *, telegram_message_id, presented_at=None):
        self.presented.append(
            (intent.purchase_intent_id, telegram_message_id, presented_at)
        )


def test_crash_before_send_reclaims_created_operation_exactly_once():
    repo = MemoryRepository(operation())
    restarted = TelegramSalesDeliveryService(repository=repo)
    first = restarted.claim(restarted.get("telegram:12:56"))
    second = restarted.claim(restarted.get("telegram:12:56"))
    assert first.state is TelegramSalesDeliveryState.SENDING
    assert second is None


def test_definite_send_failure_is_failed_without_success_transcript_or_presented():
    repo = MemoryRepository(replace(operation(), state=TelegramSalesDeliveryState.SENDING))
    saved = []
    intents = Intents(repo.item)
    service = TelegramSalesDeliveryService(
        repository=repo, purchase_intent_service=intents,
        conversation_message_saver=lambda **row: saved.append(row),
    )
    result = service.failed(repo.item, RuntimeError("provider rejected"))
    assert result.state is TelegramSalesDeliveryState.FAILED
    assert saved == []
    assert intents.presented == []


def test_accepted_crash_recovers_intent_and_transcript_without_resend():
    repo = MemoryRepository(operation(TelegramSalesDeliveryState.TELEGRAM_ACCEPTED, 901))
    saved = []
    intents = Intents(repo.item)
    restarted = TelegramSalesDeliveryService(
        repository=repo, purchase_intent_service=intents,
        conversation_message_saver=lambda **row: saved.append(row),
    )
    recovered = restarted.recover_accepted()
    assert recovered[0].state is TelegramSalesDeliveryState.CONFIRMED
    assert intents.presented == [(repo.item.purchase_intent_id, 901, NOW)]
    assert len(saved) == 1
    assert saved[0]["raw_payload"]["telegram_message_id"] == 901
    assert saved[0]["raw_payload"]["commercial_offering_id"] == str(repo.item.commercial_offering_id)
    assert saved[0]["raw_payload"]["commercial_publication_id"] == str(repo.item.commercial_publication_id)
    assert saved[0]["text"] == repo.item.response_text
    assert restarted.claim(repo.item) is None


def test_recovery_after_intent_presented_repairs_transcript_idempotently():
    repo = MemoryRepository(operation(TelegramSalesDeliveryState.TELEGRAM_ACCEPTED, 902))
    saved = []
    intents = Intents(repo.item)
    intents.item.status = SimpleNamespace(value="PRESENTED")
    service = TelegramSalesDeliveryService(
        repository=repo, purchase_intent_service=intents,
        conversation_message_saver=lambda **row: saved.append(row),
    )
    assert service.confirm(repo.item).state is TelegramSalesDeliveryState.CONFIRMED
    assert intents.presented == []
    assert len(saved) == 1


@pytest.mark.parametrize("content_type", ["SINGLE_IMAGE", "BUNDLE", "SESSION_IMAGE"])
def test_paid_content_types_persist_exact_visible_text_and_identity(content_type):
    item = replace(
        operation(TelegramSalesDeliveryState.TELEGRAM_ACCEPTED, 904),
        response_text="Exact Ava presentation\n\nAuthoritative facts and link",
        delivery_payload={
            "delivery_type": content_type,
            "delivery_reason": "authoritative_commercial_offering",
            "message_text": "Exact Ava presentation\n\nAuthoritative facts and link",
            "metadata": {"price_minor": 1999, "currency": "USD"},
        },
    )
    repo = MemoryRepository(item); saved = []
    TelegramSalesDeliveryService(
        repository=repo, purchase_intent_service=Intents(item),
        conversation_message_saver=lambda **row: saved.append(row),
    ).confirm(item)
    assert len(saved) == 1
    assert saved[0]["text"] == item.response_text
    assert saved[0]["raw_payload"]["content_type"] == content_type
    assert saved[0]["raw_payload"]["price_minor"] == 1999
    assert saved[0]["raw_payload"]["currency"] == "USD"


def test_confirmed_replay_cannot_claim_or_duplicate_send():
    repo = MemoryRepository(operation(TelegramSalesDeliveryState.CONFIRMED, 901))
    service = TelegramSalesDeliveryService(repository=repo)
    assert service.get("telegram:12:56").state is TelegramSalesDeliveryState.CONFIRMED
    assert service.claim(repo.item) is None


def test_acknowledgement_confirmation_is_durable_before_acknowledgement():
    item = replace(
        operation(TelegramSalesDeliveryState.TELEGRAM_ACCEPTED, 905),
        delivery_payload={"message_text": "Got it", "metadata": {
            "message_purpose": "PURCHASE_ACKNOWLEDGEMENT",
        }},
    )
    repo = MemoryRepository(item)
    result = TelegramSalesDeliveryService(repository=repo).confirm(item)
    assert result.state is TelegramSalesDeliveryState.CONFIRMED
    assert repo.events == ["confirmed", "acknowledged"]


def test_acknowledgement_is_not_written_when_confirm_persistence_fails():
    item = replace(
        operation(TelegramSalesDeliveryState.TELEGRAM_ACCEPTED, 906),
        delivery_payload={"message_text": "Got it", "metadata": {
            "message_purpose": "PURCHASE_ACKNOWLEDGEMENT",
        }},
    )
    repo = MemoryRepository(item)
    repo.confirm_error = RuntimeError("synthetic confirmed persistence failure")
    with pytest.raises(RuntimeError, match="confirmed persistence failure"):
        TelegramSalesDeliveryService(repository=repo).confirm(item)
    assert repo.events == []
    assert repo.item.state is TelegramSalesDeliveryState.TELEGRAM_ACCEPTED


def test_startup_recovers_confirmed_but_unacknowledged_without_send():
    item = replace(
        operation(TelegramSalesDeliveryState.CONFIRMED, 907),
        confirmed_at=NOW,
        delivery_payload={"message_text": "Got it", "metadata": {
            "message_purpose": "PURCHASE_ACKNOWLEDGEMENT",
        }},
    )
    repo = MemoryRepository(item)
    repo.list_confirmed_unacknowledged_acknowledgements = lambda: [repo.item]
    recovered = TelegramSalesDeliveryService(repository=repo).recover_startup()
    assert len(recovered) == 1
    assert recovered[0].state is TelegramSalesDeliveryState.CONFIRMED
    assert repo.events == ["confirmed", "acknowledged"]
    assert TelegramSalesDeliveryService(repository=repo).claim(repo.item) is None


def test_ambiguous_send_is_visible_and_never_blindly_reclaimed():
    repo = MemoryRepository(replace(operation(), state=TelegramSalesDeliveryState.SENDING))
    service = TelegramSalesDeliveryService(repository=repo)
    ambiguous = service.failed(repo.item, TimeoutError("outcome unknown"))
    assert ambiguous.state is TelegramSalesDeliveryState.AMBIGUOUS
    assert ambiguous.failure_reason
    assert service.claim(ambiguous) is None


def test_business_peer_ineligible_preserves_retryable_operation():
    from app.integrations.telegram.bot_api_sender import (
        TelegramBusinessPeerUsageMissingError,
    )
    repo = MemoryRepository(replace(operation(), state=TelegramSalesDeliveryState.SENDING))
    service = TelegramSalesDeliveryService(repository=repo)
    retryable = service.failed(
        repo.item, TelegramBusinessPeerUsageMissingError("not eligible"),
    )
    assert retryable.state is TelegramSalesDeliveryState.RETRYABLE
    assert service.claim(retryable).state is TelegramSalesDeliveryState.SENDING


def test_startup_marks_orphaned_sending_ambiguous():
    repo = MemoryRepository(replace(operation(), state=TelegramSalesDeliveryState.SENDING))
    recovered = TelegramSalesDeliveryService(repository=repo).recover_startup()
    assert recovered[0].state is TelegramSalesDeliveryState.AMBIGUOUS


def test_noncommercial_result_does_not_create_operation():
    repo = SimpleNamespace(get_or_create=lambda **_: (_ for _ in ()).throw(AssertionError()))
    result = SimpleNamespace(diagnostic_metadata={}, correlation_id="telegram:12:56")
    payload = SimpleNamespace(telegram_chat_id=12, message_id=56)
    assert TelegramSalesDeliveryService(repository=repo).prepare(
        intent=None, result=result, payload=payload,
    ) == (None, False)


def test_migration_enforces_durable_correlation_and_inbound_uniqueness():
    sql = open(
        "migrations/forward/20260824_080_telegram_sales_delivery_operations.sql",
        encoding="utf-8",
    ).read()
    assert "idx_purchase_intents_telegram_correlation" in sql
    assert "correlation_id TEXT NOT NULL UNIQUE" in sql
    assert "UNIQUE (telegram_chat_id, inbound_telegram_message_id)" in sql
    assert "purchase_intent_id UUID NOT NULL UNIQUE" in sql
