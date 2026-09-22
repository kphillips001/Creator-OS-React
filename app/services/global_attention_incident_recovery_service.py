"""Fail-closed classification for the bounded GLOBAL_AVA_BOT_ATTENTION incident."""
from __future__ import annotations

from enum import Enum


class IncidentRecoveryClassification(str, Enum):
    SAFE_TO_RECOVER = "SAFE_TO_RECOVER"
    STALE_DO_NOT_SEND = "STALE_DO_NOT_SEND"
    ALREADY_SATISFIED = "ALREADY_SATISFIED"
    DELIVERY_UNCERTAIN_DO_NOT_RESEND = "DELIVERY_UNCERTAIN_DO_NOT_RESEND"
    UNRELATED_FAILURE = "UNRELATED_FAILURE"
    AMBIGUOUS_MANUAL_REVIEW = "AMBIGUOUS_MANUAL_REVIEW"


class GlobalAttentionIncidentRecoveryService:
    """Classify supplied authoritative facts; never mutate or send."""

    @staticmethod
    def exclude_relationships(candidates, *, excluded_relationship_ids):
        """Exclude operator-protected relationships before individual diagnosis."""
        excluded = {str(value) for value in excluded_relationship_ids}
        return [candidate for candidate in candidates if str(
            candidate.get("relationship_id")) not in excluded]

    @staticmethod
    def classify(*, historical_global_block_proven: bool,
                 generated_payload_exists: bool, quality_valid: bool,
                 latest_relevant_inbound: bool, newer_confirmed_outbound: bool,
                 delivery_uncertain: bool, outbound_telegram_id_exists: bool,
                 duplicate_or_current_operation: bool,
                 customer_delivery_allowed: bool,
                 global_readiness_healthy: bool):
        C = IncidentRecoveryClassification
        if not historical_global_block_proven:
            return C.UNRELATED_FAILURE
        if delivery_uncertain or outbound_telegram_id_exists:
            return C.DELIVERY_UNCERTAIN_DO_NOT_RESEND
        if newer_confirmed_outbound:
            return C.ALREADY_SATISFIED
        if not latest_relevant_inbound or duplicate_or_current_operation:
            return C.STALE_DO_NOT_SEND
        if not (generated_payload_exists and quality_valid
                and customer_delivery_allowed and global_readiness_healthy):
            return C.AMBIGUOUS_MANUAL_REVIEW
        return C.SAFE_TO_RECOVER
