"""Bounded creator-owned publication reference resolution contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class CreatorContentReferenceCandidate:
    publication_id: str
    score: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class CreatorContentReferenceResolution:
    disposition: str
    reference_intent_detected: bool
    method: str = "NONE"
    confidence: float = 0.0
    context: Mapping[str, Any] = field(default_factory=dict)
    candidates: tuple[CreatorContentReferenceCandidate, ...] = ()
    evidence: tuple[str, ...] = ()
    entry_provenance: Mapping[str, Any] = field(default_factory=dict)
    cta_provenance_participated: bool = False
    explicit_reference_overrode_cta: bool = False
    reply_provenance_overrode_cta: bool = False
    version: str = "creator_content_reference_v2"

    def diagnostics(self) -> dict[str, Any]:
        entry = dict(self.entry_provenance or {})
        return {
            "entryAttributionAvailable": bool(entry),
            "entryPublicationId": entry.get("publicationId"),
            "entryObservedAt": (
                entry.get("observedAt").isoformat()
                if hasattr(entry.get("observedAt"), "isoformat") else entry.get("observedAt")
            ),
            "entryProvenanceMethod": entry.get("provenanceMethod"),
            "entryAttributionId": entry.get("attributionId"),
            "entryEventId": entry.get("entryEventId"),
            "referenceIntentDetected": self.reference_intent_detected,
            "disposition": self.disposition,
            "resolutionDisposition": self.disposition,
            "resolutionMethod": self.method,
            "selectedPublicationId": self.context.get("publicationId"),
            "currentReferencedPublicationId": self.context.get("publicationId"),
            "selectedTelegramMessageId": self.context.get("telegramMessageId"),
            "confidence": self.confidence,
            "resolutionConfidence": self.confidence,
            "candidatePublicationIds": tuple(item.publication_id for item in self.candidates),
            "candidateScores": tuple({"publicationId": item.publication_id,
                "score": item.score, "reasons": item.reasons} for item in self.candidates),
            "supportingEvidence": self.evidence,
            "ctaProvenanceParticipated": self.cta_provenance_participated,
            "explicitReferenceOverrodeCTA": self.explicit_reference_overrode_cta,
            "replyProvenanceOverrodeCTA": self.reply_provenance_overrode_cta,
            "contentContextVersion": self.version,
        }