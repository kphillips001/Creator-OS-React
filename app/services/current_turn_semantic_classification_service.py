"""One-shot, operation-bound semantic classification for a current chat turn."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from datetime import datetime, timezone


class CurrentTurnSemanticClassificationService:
    """Compute once and expose only the bounded fields downstream policies need."""

    AUTHORITY = "CURRENT_TURN_SEMANTIC_CLASSIFICATION_V1"
    VERSION = 1
    FIELDS = (
        "sexual_engagement",
        "explicit_without_buying_intent",
        "escalation_ready",
        "recommended_action",
        "confidence",
        "buying_intent",
        "monetization_intent",
        "purchase_language_present",
        "content_request",
        "route",
    )

    def classify(
        self,
        *,
        message: str,
        correlation_id: str,
        classifier: Callable[..., Mapping] | None,
        classified_at: datetime | None = None,
        creator_content_context: Mapping | None = None,
    ) -> tuple[dict, dict | None]:
        now = classified_at or datetime.now(timezone.utc)
        binding = {
            "authority": self.AUTHORITY,
            "version": self.VERSION,
            "correlationId": str(correlation_id),
            "messageSha256": hashlib.sha256(
                str(message or "").encode("utf-8")
            ).hexdigest(),
            "classifiedAt": now.isoformat(),
        }
        if not str(message or "").strip():
            return ({**binding, "status": "UNAVAILABLE",
                     "failureReason": "EMPTY_CURRENT_MESSAGE"}, None)
        if not callable(classifier):
            return ({**binding, "status": "UNAVAILABLE",
                     "failureReason": "CLASSIFIER_UNAVAILABLE"}, None)
        try:
            import inspect
            parameters = inspect.signature(classifier).parameters
            arguments = {"message": message}
            if "creator_content_context" in parameters:
                arguments["creator_content_context"] = dict(creator_content_context or {})
            raw = classifier(**arguments)
        except Exception as error:
            return ({**binding, "status": "UNAVAILABLE",
                     "failureReason": "CLASSIFIER_EXCEPTION",
                     "errorType": type(error).__name__}, None)
        if not isinstance(raw, Mapping):
            return ({**binding, "status": "UNAVAILABLE",
                     "failureReason": "CLASSIFIER_MALFORMED_RESULT"}, None)
        reason = str(raw.get("reason") or "")
        if reason.startswith("Classifier failed safely:"):
            return ({**binding, "status": "UNAVAILABLE",
                     "failureReason": "CLASSIFIER_FAILED_SAFE"}, None)
        sanitized = {
            key: raw.get(key)
            for key in self.FIELDS
            if key in raw
        }
        if "confidence" in sanitized:
            try:
                sanitized["confidence"] = max(
                    0.0, min(1.0, float(sanitized["confidence"] or 0.0))
                )
            except (TypeError, ValueError):
                return ({**binding, "status": "UNAVAILABLE",
                         "failureReason": "CLASSIFIER_INVALID_CONFIDENCE"}, None)
        binding["creatorContentContextSupplied"] = bool(creator_content_context)
        # The full validated result is reused in memory by Decision Engine so
        # existing routing behavior is preserved.  Only the bounded projection
        # is durable/auditable.
        return ({**binding, "status": "AVAILABLE", "result": sanitized}, dict(raw))
