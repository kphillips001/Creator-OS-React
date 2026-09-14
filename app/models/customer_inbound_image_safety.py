"""Provider-neutral safety and response-policy contracts for customer images."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping, Sequence


class CustomerImageSafetyState(str, Enum):
    NORMAL_NON_EXPLICIT = "NORMAL_NON_EXPLICIT"
    SUGGESTIVE_NON_EXPLICIT = "SUGGESTIVE_NON_EXPLICIT"
    NUDITY_NON_GENITAL = "NUDITY_NON_GENITAL"
    EXPLICIT_GENITAL = "EXPLICIT_GENITAL"
    AMBIGUOUS_REVIEW_REQUIRED = "AMBIGUOUS_REVIEW_REQUIRED"
    UNCLASSIFIABLE = "UNCLASSIFIABLE"


class ImageSolicitationState(str, Enum):
    CLEARLY_SOLICITED = "CLEARLY_SOLICITED"
    UNSOLICITED = "UNSOLICITED"


class CustomerImageResponsePolicy(str, Enum):
    NORMAL_VISUAL_RESPONSE_ALLOWED = "NORMAL_VISUAL_RESPONSE_ALLOWED"
    SELFIE_COMPLIMENT_ELIGIBLE = "SELFIE_COMPLIMENT_ELIGIBLE"
    SUGGESTIVE_VISUAL_RESPONSE = "SUGGESTIVE_VISUAL_RESPONSE"
    NUDITY_RESPONSE_REQUIRED = "NUDITY_RESPONSE_REQUIRED"
    POLITE_EXPLICIT_BOUNDARY = "POLITE_EXPLICIT_BOUNDARY"
    FIRM_EXPLICIT_BOUNDARY = "FIRM_EXPLICIT_BOUNDARY"
    SOLICITED_EXPLICIT_MEDIA = "SOLICITED_EXPLICIT_MEDIA"
    AMBIGUOUS_SAFE_RESPONSE = "AMBIGUOUS_SAFE_RESPONSE"
    UNCLASSIFIABLE_SAFE_RESPONSE = "UNCLASSIFIABLE_SAFE_RESPONSE"


@dataclass(frozen=True)
class BoundedSafetyLabel:
    label: str
    confidence: float
    threshold: float


@dataclass(frozen=True)
class CustomerImageSafetyResult:
    attachment_id: str
    state: CustomerImageSafetyState
    classifier: str
    classifier_version: str
    labels: tuple[BoundedSafetyLabel, ...]
    classified_at: datetime


@dataclass(frozen=True)
class CustomerImagePolicyResult:
    safety_state: CustomerImageSafetyState
    solicitation_state: ImageSolicitationState
    policy: CustomerImageResponsePolicy
    selfie_eligible: bool
    boundary_occurrence: int = 0
    generation_allowed: bool = False
    response_text: str = ""


def clear_ava_explicit_solicitation(messages: Sequence[Mapping]) -> bool:
    """Accept only immediate structured Ava-authored solicitation evidence."""
    for message in reversed(tuple(messages)[-3:]):
        if str(message.get("direction") or "").lower() == "inbound":
            continue
        if str(message.get("sender_type") or "").lower() not in {"ava", "assistant"}:
            continue
        evidence = message.get("metadata") or message.get("raw_payload") or {}
        requested = str(evidence.get("customer_image_solicitation") or "").upper()
        return requested in {"EXPLICIT_IMAGE", "EXPLICIT_GENITAL_IMAGE"}
    return False
