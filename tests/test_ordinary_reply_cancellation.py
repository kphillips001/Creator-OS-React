from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.ordinary_reply_cancellation_service import (
    OrdinaryReplyCancellationError,
    OrdinaryReplyCancellationService,
)


class Repository:
    def __init__(self, outcome="CANCELLED"):
        self.outcome = outcome
        self.calls = []
        self.operation = SimpleNamespace(
            operation_id=uuid4(), state=SimpleNamespace(value="SUPPRESSED"),
            last_error="OPERATOR_CANCELLED_PREPARED_REPLY",
        )

    def cancel_operator_reply(self, **values):
        self.calls.append(values)
        return self.outcome, None if self.outcome == "AUTHORITY_MISMATCH" else self.operation


def test_exact_reply_cancel_uses_relationship_and_inbound_authority():
    repository = Repository()
    service = OrdinaryReplyCancellationService(repository=repository)
    operation, changed = service.cancel(
        operation_id=repository.operation.operation_id,
        telegram_chat_id=44, telegram_user_id=33, inbound_message_id=22,
    )
    assert changed is True
    assert operation is repository.operation
    assert repository.calls == [{
        "operation_id": repository.operation.operation_id,
        "account_scope": "AVA_TELETHON_PRIVATE",
        "chat_id": 44, "sender_user_id": 33, "inbound_message_id": 22,
        "cancelled_by": "CREATOR_OS_OPERATOR",
    }]


def test_double_cancel_is_idempotent():
    operation, changed = OrdinaryReplyCancellationService(
        repository=Repository("ALREADY_CANCELLED")).cancel(
            operation_id=uuid4(), telegram_chat_id=4,
            telegram_user_id=3, inbound_message_id=2)
    assert changed is False
    assert operation.last_error == "OPERATOR_CANCELLED_PREPARED_REPLY"


@pytest.mark.parametrize("outcome", ["AUTHORITY_MISMATCH", "DELIVERY_OR_LIFECYCLE_WON"])
def test_wrong_authority_or_send_winner_refuses_cancel(outcome):
    with pytest.raises(OrdinaryReplyCancellationError):
        OrdinaryReplyCancellationService(repository=Repository(outcome)).cancel(
            operation_id=uuid4(), telegram_chat_id=4,
            telegram_user_id=3, inbound_message_id=2)


def test_repository_transition_preserves_audit_and_excludes_delivery_states():
    from pathlib import Path
    source = Path("app/repositories/ordinary_chat_reply_repository.py").read_text()
    method = source[source.index("def cancel_operator_reply"):source.index(
        "def reserve_english_only_notice")]
    assert "state IN ('PENDING_GENERATION','GENERATED','RETRYABLE')" in method
    assert "outbound_telegram_message_id IS NULL" in method
    assert "send_attempt_count=0" in method
    assert "uncertain_at IS NULL AND sending_at IS NULL" in method
    assert "claim_owner IS NULL" in method
    assert "operatorCancellation" in method
    assert "'reason',%s::text" in method
    assert "'cancelledBy',%s::text" in method
    assert "previousState" in method and "cancelledAt" in method
    assert "response_text=NULL" not in method
    assert "response_payload=NULL" not in method
