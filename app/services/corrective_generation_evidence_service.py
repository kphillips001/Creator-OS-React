"""Canonical evidence contract for one-shot ordinary-reply correction."""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


class CorrectiveGenerationEvidenceService:
    EXCLUSION_AUTHORITY = "FINAL_RESPONSE_EXACT_NOVELTY"

    @staticmethod
    def normalize_exact(value: Any) -> str:
        return " ".join(re.findall(r"[a-z0-9']+", str(value or "").lower()))

    @classmethod
    def exact_exclusions(cls, *values: Any, limit: int = 7) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            items = value if isinstance(value, (list, tuple)) else (value,)
            for item in items:
                text = str(item or "").strip()
                normalized = cls.normalize_exact(text)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                result.append(text)
                if len(result) >= limit:
                    return result
        return result

    @classmethod
    def build(cls, *, response_payload: Mapping[str, Any] | None,
              reasons: Iterable[str], recent_ava_responses: Iterable[str] = (),
              attempt: int = 2, source: str | None = None,
              original_operation_id: Any = None,
              original_inbound_message_id: Any = None,
              require_rejected_candidate: bool = False) -> dict[str, Any]:
        payload = dict(response_payload or {})
        diagnostics = dict(payload.get("diagnostic_metadata") or {})
        reason_list = list(dict.fromkeys(
            str(item) for item in reasons if str(item).strip()
        ))
        rejected = str(payload.get("response_text") or "").strip()
        if require_rejected_candidate and not rejected:
            raise ValueError(
                "HISTORICAL_CORRECTIVE_REJECTED_CANDIDATE_EVIDENCE_REQUIRED"
            )
        style = dict(diagnostics.get("conversationStyle") or {})
        coherence = dict(diagnostics.get("conversationCoherence") or {})
        evidence = {
            "required": True,
            "attempt": int(attempt),
            "blockingReasons": reason_list,
            "previousCandidateBlockedBeforeDelivery": True,
            "previousCandidateText": rejected,
            "excludedExactResponses": cls.exact_exclusions(
                rejected, tuple(recent_ava_responses)
            ),
            "exclusionAuthority": cls.EXCLUSION_AUTHORITY,
            "previousCandidateDiagnostics": diagnostics,
            "turnObligations": list(style.get("turnObligations") or ()),
            "semanticReferent": coherence.get("resolvedCustomerMeaning"),
            "personaDomain": coherence.get("resolvedPersonaDomain"),
            "canonicalKnownFacts": list(dict(
                diagnostics.get("avaPersonaRuntime") or {}
            ).get("selected_lifestyle_facts") or ()),
            "previousCandidateFailure": ",".join(reason_list),
            "offlineAccessAuthority": dict(
                diagnostics.get("offlineAccessAuthority") or {}
            ),
            "offlineAccessCorrection": {
                "required": "MISLEADING_OFFLINE_ENCOUNTER_EXPECTATION" in reason_list,
                "preserveWarmthAndFantasy": True,
                "removeRealWorldAvailability": True,
                "preferredBoundary": "Let's keep things online for now 😊",
                "maximumGenerationAttempts": 2,
            },
            "commercialAuthorityCorrection": {
                "required": (
                    "COMMERCIAL_MEDIA_WITHOUT_CURRENT_AUTHORITY" in reason_list
                ),
                "authority": "PRE_GENERATION_COMMERCIAL_DECISION",
                "conversationOnly": True,
                "textOnly": True,
                "preserveOrdinaryTurnObligations": True,
                "excludeRejectedCandidate": True,
                "maximumGenerationAttempts": 2,
            },
            "commercialAuthorization": {
                "decision": diagnostics.get("customer_sales_decision"),
                "reasonCode": diagnostics.get("customer_sales_reason_code"),
                "receptiveness": dict(
                    diagnostics.get("commercial_receptiveness") or {}
                ),
                "directQuestionPrecedence": dict(
                    diagnostics.get("direct_question_precedence") or {}
                ),
            },
        }
        if source:
            evidence["source"] = source
        if original_operation_id is not None:
            evidence["originalOperationId"] = str(original_operation_id)
        if original_inbound_message_id is not None:
            evidence["originalInboundMessageId"] = int(original_inbound_message_id)
        return evidence
