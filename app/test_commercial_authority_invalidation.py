from datetime import datetime, timezone
from uuid import uuid4

from app.repositories.ordinary_chat_reply_repository import (
    OrdinaryChatReplyRepository,
)


NOW = datetime(2026, 9, 17, 23, tzinfo=timezone.utc)
INTENT = uuid4()


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


def evidence(*, allowed=False):
    return {
        "authority": "CURRENT_CANONICAL_SALES_POLICY",
        "commercialAuthorityAllowed": allowed,
        "sexualSignalClass": "SEXUAL_ATTRACTIVE_COMPLIMENT",
        "directCommercialSignal": False,
        "sexualSalesOpportunityEligible": False,
        "activePresentationBridge": False,
        "reason": "SEXUAL_COMPLIMENT_ONLY",
    }


def operation(**changes):
    value = {
        "operation_id": uuid4(),
        "state": "RETRYABLE",
        "last_error": "TelegramOutboundSendError: sendPhoto failed",
        "telegram_account_scope": "AVA_TELETHON_PRIVATE",
        "telegram_chat_id": 10,
        "inbound_telegram_message_id": 20,
        "inbound_received_at": NOW,
        "response_payload": {"response_text": "existing"},
        "response_text": "existing",
        "response_content_sha256": "hash",
        "delivery_payload": {
            "delivery_method": "private_ppv_media",
            "metadata": {"private_ppv_presentation": {
                "purchase_intent_id": str(INTENT),
            }},
        },
        "outbound_telegram_message_id": None,
        "claim_owner": None,
        "claimed_at": None,
        "lease_expires_at": None,
        "uncertain_at": None,
        "sent_confirmed_at": None,
        "generation_attempt_count": 1,
        "send_attempt_count": 1,
    }
    value.update(changes)
    return value


def intent(**changes):
    value = {
        "status": "ABANDONED", "presented_at": None,
        "purchased_at": None, "telegram_message_id": None,
        "provider_transaction_order_id": None,
        "provider_payment_id": None, "provider_event_id": None,
        "purchase_acknowledged_at": None,
        "actual_charged_price_minor": None,
    }
    value.update(changes)
    return value


def repository(rows):
    result = OrdinaryChatReplyRepository(
        connection_factory=lambda: Connection(rows)
    )
    result._item = lambda row: row
    return result


def invalidate(repo, current):
    return repo.invalidate_commercial_authority(
        operation_id=current["operation_id"], inbound_message_id=20,
        purchase_intent_id=INTENT, revalidation_evidence=evidence(),
    )


def test_revoked_unsent_commercial_reply_invalidates_and_preserves_audit_fields():
    current = operation()
    updated = {**current, "state": "SUPPRESSED",
               "last_error": "COMMERCIAL_AUTHORITY_REVOKED_BEFORE_DELIVERY"}
    status, result = invalidate(repository([
        current, intent(), {"stale": False}, updated,
    ]), current)
    assert status == "INVALIDATED"
    assert result["response_text"] == current["response_text"]
    assert result["response_content_sha256"] == "hash"
    assert result["generation_attempt_count"] == 1
    assert result["send_attempt_count"] == 1


def test_current_authority_cannot_use_revocation_transition():
    current = operation()
    repo = repository([])
    status, result = repo.invalidate_commercial_authority(
        operation_id=current["operation_id"], inbound_message_id=20,
        purchase_intent_id=INTENT, revalidation_evidence=evidence(allowed=True),
    )
    assert (status, result) == ("CURRENT_AUTHORITY_NOT_DENIED", None)


def test_purchase_or_settlement_evidence_fails_closed():
    current = operation()
    status, result = invalidate(repository([
        current, intent(status="PURCHASED", purchased_at=NOW),
    ]), current)
    assert (status, result) == ("PURCHASE_OR_OWNERSHIP_EVIDENCE_PRESENT", None)


def test_newer_inbound_or_outbound_fails_freshness():
    current = operation()
    status, result = invalidate(repository([
        current, intent(), {"stale": True},
    ]), current)
    assert (status, result) == ("FRESHNESS_CHANGED", None)


def test_send_claim_or_provider_state_wins_over_invalidation():
    current = operation()
    status, result = invalidate(repository([
        current, intent(), {"stale": False}, None,
    ]), current)
    assert (status, result) == ("OPERATION_NOT_INVALIDATABLE", None)


def test_double_invalidation_is_idempotent_without_reopening():
    current = operation(
        state="SUPPRESSED",
        last_error="COMMERCIAL_AUTHORITY_REVOKED_BEFORE_DELIVERY",
    )
    status, result = invalidate(repository([current]), current)
    assert status == "ALREADY_INVALIDATED"
    assert result["state"] == "SUPPRESSED"
