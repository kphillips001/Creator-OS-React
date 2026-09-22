from inspect import getsource
from types import SimpleNamespace

import pytest

from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.services.global_automation_safety_service import GlobalAutomationSafetyService
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService


class RecoveryRepository:
    def __init__(self):
        self.calls = []

    def recover_denied_optional_active_offer(self, **kwargs):
        self.calls.append(kwargs)
        return "RECOVERED" if kwargs["global_reply_authorized"] else None


class Permissions:
    def __init__(self, *, allowed=True, ignored=False, disposition="ACTIVE"):
        self.allowed = allowed
        self.ignored = ignored
        self.disposition = disposition

    def read(self, **_scope):
        return {
            "effective": {"chatAllowed": self.allowed},
            "communication": {
                "ignored": self.ignored,
                "disposition": self.disposition,
            },
        }


def operation():
    return SimpleNamespace(
        operation_id="4ebc689b-f062-4207-870b-7b2f6eb7971c",
        inbound_sender_telegram_user_id=8303003496,
        telegram_chat_id=8303003496,
    )


def service(repository, permissions):
    return OrdinaryChatReplyService(
        repository=repository,
        effective_permissions=permissions,
        creator_profile_id=2,
        fanvue_account_id=2,
    )


def allow_global(monkeypatch, allowed=True):
    monkeypatch.setattr(GlobalAutomationSafetyService, "refresh", lambda self: None)
    monkeypatch.setattr(
        GlobalAutomationSafetyService,
        "check_global_safety",
        lambda self: {"allowed": allowed},
    )


def test_exact_joseph_recovery_crosses_service_boundary(monkeypatch):
    allow_global(monkeypatch)
    repository = RecoveryRepository()
    assert service(repository, Permissions()).recover_denied_optional_active_offer(
        operation()
    ) == "RECOVERED"
    assert repository.calls == [{
        "operation_id": operation().operation_id,
        "creator_profile_id": 2,
        "fanvue_account_id": 2,
        "global_reply_authorized": True,
        "safety_authorized": True,
    }]


@pytest.mark.parametrize("permissions", [
    Permissions(allowed=False),
    Permissions(ignored=True),
    Permissions(disposition="IGNORED"),
])
def test_customer_control_blocks_recovery(monkeypatch, permissions):
    allow_global(monkeypatch)
    repository = RecoveryRepository()
    assert service(repository, permissions).recover_denied_optional_active_offer(
        operation()
    ) is None
    assert repository.calls[0]["global_reply_authorized"] is False


def test_global_safety_blocks_recovery(monkeypatch):
    allow_global(monkeypatch, allowed=False)
    repository = RecoveryRepository()
    assert service(repository, Permissions()).recover_denied_optional_active_offer(
        operation()
    ) is None


@pytest.mark.parametrize("required", [
    "target.state='SUPPRESSED'",
    "target.last_error='ACTIVE_OFFER_NUDGE_RESERVATION_DENIED'",
    "target.generation_attempt_count=0",
    "target.send_attempt_count=0",
    "target.response_payload IS NULL",
    "target.response_text IS NULL",
    "target.outbound_telegram_message_id IS NULL",
    "target.sent_confirmed_at IS NULL",
    "target.sending_at IS NULL",
    "target.lease_expires_at<=NOW()",
    "telegram_private_inbound_messages newer",
    "ordinary_chat_reply_operations newer",
    "ordinary_chat_reply_operations competing",
    "ordinary_chat_reply_operations answered",
    "telegram_operator_message_operations manual",
    "'AVA_AUTO')='AVA_AUTO'",
    "'ACTIVE')='ACTIVE'",
    "pg_advisory_xact_lock",
    "FOR UPDATE",
])
def test_repository_atomic_predicate_is_bounded(required):
    source = getsource(
        OrdinaryChatReplyRepository.recover_denied_optional_active_offer
    )
    assert required in source


def test_recovery_preserves_audit_and_releases_only_to_availability():
    source = getsource(
        OrdinaryChatReplyRepository.recover_denied_optional_active_offer
    )
    for evidence in (
        "originalState", "originalReason", "originalSuppressedAt",
        "originalGenerationAttemptCount", "originalSendAttemptCount",
        "originalCommercialDiagnostics", "commercialAuthorityGranted",
        "directGeneration", "directSend",
    ):
        assert evidence in source
    assert "state='RETRYABLE'" in source
    assert "last_error='availability_deferred'" in source
    assert "state='GENERATING'" not in source
    assert "state='SENDING'" not in source


def test_transition_is_not_a_generic_suppression_requeue():
    source = getsource(
        OrdinaryChatReplyRepository.recover_denied_optional_active_offer
    )
    assert "ACTIVE_OFFER_NUDGE_RESERVATION_DENIED" in source
    assert "operation_id=%s" in source


def recovery_audit_payload():
    return {
        "optionalActiveOfferSuppressionRecovery": {
            "authority": "OrdinaryChatReplyRepository",
            "originalState": "SUPPRESSED",
            "originalReason": "ACTIVE_OFFER_NUDGE_RESERVATION_DENIED",
            "originalSuppressedAt": "2026-09-17T09:50:06-05:00",
            "originalGenerationAttemptCount": 0,
            "originalSendAttemptCount": 0,
        },
        "preGenerationCommercialDecision": {
            "fresh_direct_intent": False,
            "current_commercial_interest": False,
            "active_offer_nudge_candidate": False,
            "active_offer_reservation_reason": (
                "OPTIONAL_NUDGE_AUTHORITY_DENIED_FALLTHROUGH"
            ),
        },
        "availability": {"obsoleteCurrentStageData": True},
    }


def test_generated_payload_preserves_recovery_and_fallthrough_audit():
    merged = OrdinaryChatReplyRepository.merge_current_delivery_with_durable_audit(
        recovery_audit_payload(),
        {"type": "MESSAGE_TEXT", "message_text": "current response"},
    )
    assert merged["optionalActiveOfferSuppressionRecovery"]["originalState"] == "SUPPRESSED"
    assert merged["preGenerationCommercialDecision"][
        "active_offer_reservation_reason"
    ] == "OPTIONAL_NUDGE_AUTHORITY_DENIED_FALLTHROUGH"
    assert merged["message_text"] == "current response"
    assert "availability" not in merged


def test_current_delivery_fields_replace_stale_values_without_deep_merge():
    merged = OrdinaryChatReplyRepository.merge_current_delivery_with_durable_audit(
        {**recovery_audit_payload(), "message_text": "stale", "metadata": {"old": 1}},
        {"message_text": "fresh", "metadata": {"current": 2}},
    )
    assert merged["message_text"] == "fresh"
    assert merged["metadata"] == {"current": 2}


def test_repeated_persistence_is_idempotent_and_does_not_duplicate_audit():
    first = OrdinaryChatReplyRepository.merge_current_delivery_with_durable_audit(
        recovery_audit_payload(), {"message_text": "first"},
    )
    second = OrdinaryChatReplyRepository.merge_current_delivery_with_durable_audit(
        first, {"message_text": "second"},
    )
    assert second["optionalActiveOfferSuppressionRecovery"] == (
        first["optionalActiveOfferSuppressionRecovery"]
    )
    assert isinstance(second["optionalActiveOfferSuppressionRecovery"], dict)
    assert second["message_text"] == "second"


@pytest.mark.parametrize("terminal_state", [
    "RETRYABLE", "TERMINAL_FAILED", "SEND_UNCERTAIN", "SENT_CONFIRMED",
])
def test_later_state_transitions_can_retain_same_audit_payload(terminal_state):
    persisted = OrdinaryChatReplyRepository.merge_current_delivery_with_durable_audit(
        recovery_audit_payload(), {"message_text": "accepted"},
    )
    operation = {"state": terminal_state, "delivery_payload": persisted}
    assert operation["delivery_payload"]["optionalActiveOfferSuppressionRecovery"]
    assert operation["delivery_payload"]["preGenerationCommercialDecision"]


def test_complete_recovery_generation_confirmation_fixture_preserves_authority():
    operation = {
        "state": "SUPPRESSED",
        "last_error": "ACTIVE_OFFER_NUDGE_RESERVATION_DENIED",
        "generation_attempt_count": 0,
        "send_attempt_count": 0,
        "delivery_payload": recovery_audit_payload(),
    }
    operation.update(state="RETRYABLE", last_error="availability_deferred")
    operation["state"] = "GENERATING"
    operation["generation_attempt_count"] += 1
    operation["delivery_payload"] = (
        OrdinaryChatReplyRepository.merge_current_delivery_with_durable_audit(
            operation["delivery_payload"],
            {
                "message_text": "accepted",
                "delivery_reason": "ordinary_chat",
                "diagnostics": {"candidate": "current"},
            },
        )
    )
    operation.update(
        state="SENT_CONFIRMED", send_attempt_count=1,
        outbound_telegram_message_id=999, response_text="accepted",
        response_payload={"text": "accepted", "diagnostics": {"candidate": "current"}},
        response_content_sha256="current-response-hash",
    )
    audit = operation["delivery_payload"]["optionalActiveOfferSuppressionRecovery"]
    commercial = operation["delivery_payload"]["preGenerationCommercialDecision"]
    assert audit["originalReason"] == "ACTIVE_OFFER_NUDGE_RESERVATION_DENIED"
    assert audit["originalSuppressedAt"]
    assert audit["originalGenerationAttemptCount"] == 0
    assert commercial["active_offer_reservation_reason"] == (
        "OPTIONAL_NUDGE_AUTHORITY_DENIED_FALLTHROUGH"
    )
    assert operation == {**operation, "generation_attempt_count": 1,
                         "send_attempt_count": 1,
                         "outbound_telegram_message_id": 999}
    assert operation["response_payload"]["text"] == "accepted"
    assert operation["response_content_sha256"] == "current-response-hash"
    assert operation["delivery_payload"]["diagnostics"] == {"candidate": "current"}
    assert operation["delivery_payload"]["delivery_reason"] == "ordinary_chat"


def test_replacement_boundaries_use_canonical_preservation_authority():
    for method in (
        OrdinaryChatReplyRepository.store_suppressed_generation,
        OrdinaryChatReplyRepository.schedule_quality_correction,
        OrdinaryChatReplyRepository.update_generated_payload,
        OrdinaryChatReplyRepository.requeue_empty_generation,
        OrdinaryChatReplyRepository.requeue_suppressed_engine_exception,
        OrdinaryChatReplyRepository.reconcile_confirmed_commercial_edit,
    ):
        assert "merge_current_delivery_with_durable_audit" in getsource(method)
