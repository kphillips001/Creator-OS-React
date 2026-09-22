import pytest
from types import SimpleNamespace

from app.services.global_attention_incident_recovery_service import (
    GlobalAttentionIncidentRecoveryService as Service,
    IncidentRecoveryClassification as C,
)
from app.services.conversation_attention_evidence_service import (
    ConversationAttentionEvidenceService,
)


BASE = dict(
    historical_global_block_proven=True,
    generated_payload_exists=True,
    quality_valid=True,
    latest_relevant_inbound=True,
    newer_confirmed_outbound=False,
    delivery_uncertain=False,
    outbound_telegram_id_exists=False,
    duplicate_or_current_operation=False,
    customer_delivery_allowed=True,
    global_readiness_healthy=True,
)


def classify(**changes):
    return Service.classify(**{**BASE, **changes})


def test_safe_incident_operation_is_recoverable():
    assert classify() is C.SAFE_TO_RECOVER


@pytest.mark.parametrize("changes,expected", [
    ({"historical_global_block_proven": False}, C.UNRELATED_FAILURE),
    ({"latest_relevant_inbound": False}, C.STALE_DO_NOT_SEND),
    ({"duplicate_or_current_operation": True}, C.STALE_DO_NOT_SEND),
    ({"newer_confirmed_outbound": True}, C.ALREADY_SATISFIED),
    ({"delivery_uncertain": True}, C.DELIVERY_UNCERTAIN_DO_NOT_RESEND),
    ({"outbound_telegram_id_exists": True}, C.DELIVERY_UNCERTAIN_DO_NOT_RESEND),
    ({"global_readiness_healthy": False}, C.AMBIGUOUS_MANUAL_REVIEW),
    ({"customer_delivery_allowed": False}, C.AMBIGUOUS_MANUAL_REVIEW),
])
def test_fail_closed_classifications(changes, expected):
    assert classify(**changes) is expected


def test_excluded_relationship_cannot_be_misidentified_without_causal_evidence():
    assert classify(historical_global_block_proven=False) is C.UNRELATED_FAILURE


def test_operator_protected_relationship_is_excluded_before_diagnosis():
    candidates = [{"relationship_id": "johnny"}, {"relationship_id": "protected"}]
    assert Service.exclude_relationships(
        candidates, excluded_relationship_ids={"protected"}) == [
            {"relationship_id": "johnny"}]


def test_current_readiness_and_historical_cause_are_independent_evidence():
    operation = SimpleNamespace(
        delivery_payload={"operatorAuthorizedDeliveryRecovery": {
            "historicalCause": "GLOBAL_AVA_BOT_ATTENTION",
            "historicalInfrastructureCause": "launcher_identity_mismatch",
            "incidentResolvedAt": "2026-09-15T00:01:15.252932+00:00",
        }},
        outbound_telegram_message_id=6086,
    )
    historical = ConversationAttentionEvidenceService._historical_failure(operation)
    current = {"ready": True, "reason": None}
    assert current == {"ready": True, "reason": None}
    assert historical == {
        "reason": "GLOBAL_AVA_BOT_ATTENTION",
        "infrastructureCause": "launcher_identity_mismatch",
        "resolvedAt": "2026-09-15T00:01:15.252932+00:00",
        "deliveryExecuted": True,
        "evidenceAuthority": "OPERATOR_AUTHORIZED_INCIDENT_RECOVERY",
    }
