"""Runtime-side ingestion for customer content requests.

This service detects likely content requests and records provider-neutral
Content Opportunity demand. It does not send messages, create offers, or change
DecisionEngine response ownership.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.models.content_opportunity import (
    ContentOpportunity,
    ContentOpportunitySource,
    ContentOpportunityStatus,
)
from app.services.content_opportunity_service import ContentOpportunityService


@dataclass(frozen=True)
class RuntimeContentOpportunityIngestionResult:
    detected: bool
    recorded: bool = False
    opportunity: ContentOpportunity | None = None
    safe_response_guidance: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ContentOpportunityRuntimeIngestionService:
    """Record customer content demand from runtime messages."""

    CONTENT_REQUEST_PATTERNS = (
        re.compile(r"\b(do you|u|you)\s+(have|got)\b", re.IGNORECASE),
        re.compile(r"\b(any|more)\s+.+\b(photo|photos|pic|pics|video|videos|clip|clips|set|story)\b", re.IGNORECASE),
        re.compile(r"\b(can|could)\s+i\s+(see|get|buy|unlock)\b", re.IGNORECASE),
        re.compile(r"\b(custom|request|looking for|want)\b.+\b(photo|photos|video|videos|clip|clips|content|set|story)\b", re.IGNORECASE),
    )

    SOFT_UNAVAILABLE_RESPONSE = (
        "I don't currently have that available, but I'll keep it in mind."
    )

    def __init__(
        self,
        *,
        content_opportunity_service: ContentOpportunityService | None = None,
    ) -> None:
        self.content_opportunity_service = (
            content_opportunity_service or ContentOpportunityService()
        )

    def ingest_message(
        self,
        *,
        customer_id: str,
        message_text: str,
        provider: str = "telegram",
        provider_customer_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
        creator_profile_id: int | None = None,
        source_metadata: Mapping[str, Any] | None = None,
        is_vip: bool = False,
    ) -> RuntimeContentOpportunityIngestionResult:
        if not self.is_content_request(message_text):
            return RuntimeContentOpportunityIngestionResult(
                detected=False,
                metadata={"read_only": True, "owner": "ContentOpportunityRuntimeIngestionService"},
            )

        opportunity = self.content_opportunity_service.record_content_request(
            customer_id=customer_id,
            provider=provider,
            provider_customer_id=provider_customer_id,
            request_text=message_text,
            creator_profile_id=creator_profile_id,
            requested_content_type=self._requested_content_type(message_text),
            requested_format=self._requested_format(message_text),
            source=ContentOpportunitySource.TELEGRAM,
            conversation_id=conversation_id,
            message_id=message_id,
            source_metadata=source_metadata,
            is_vip=is_vip,
            metadata={
                "runtime_ingestion": True,
                "read_only": True,
                "does_not_send_message": True,
                "decision_owner": "DecisionEngine",
            },
        )
        matched = opportunity.status == ContentOpportunityStatus.MATCHED
        guidance = (
            dict(ContentOpportunityService.MATCHED_GUIDANCE)
            if matched
            else {
                **dict(ContentOpportunityService.SAFE_UNMATCHED_GUIDANCE),
                "soft_response_suggestion": self.SOFT_UNAVAILABLE_RESPONSE,
                "must_not_promise_future_content": True,
            }
        )
        return RuntimeContentOpportunityIngestionResult(
            detected=True,
            recorded=True,
            opportunity=opportunity,
            safe_response_guidance=guidance,
            metadata={
                "read_only": True,
                "provider": provider,
                "matched": matched,
                "opportunity_id": opportunity.opportunity_id,
                "decision_owner": "DecisionEngine",
                "sends_messages": False,
            },
        )

    @classmethod
    def is_content_request(cls, message_text: str) -> bool:
        text = str(message_text or "").strip()
        if not text:
            return False
        return any(pattern.search(text) for pattern in cls.CONTENT_REQUEST_PATTERNS)

    @staticmethod
    def _requested_content_type(message_text: str) -> str | None:
        text = message_text.lower()
        if any(word in text for word in ("video", "clip", "story")):
            return "video"
        if any(word in text for word in ("photo", "pic", "image")):
            return "photo"
        return None

    @staticmethod
    def _requested_format(message_text: str) -> str | None:
        text = message_text.lower()
        if "story" in text:
            return "story"
        if "set" in text:
            return "set"
        if any(word in text for word in ("video", "clip")):
            return "video"
        if any(word in text for word in ("photo", "pic", "image")):
            return "photo"
        return None
