"""Authority boundary between visual observations and durable customer knowledge."""
from __future__ import annotations

from enum import Enum
import re
from typing import Any, Mapping, Sequence


class VisualEvidenceClass(str, Enum):
    EPHEMERAL_VISUAL_CONTEXT = "EPHEMERAL_VISUAL_CONTEXT"
    TEXT_SUPPORTED_MEMORY_EVIDENCE = "TEXT_SUPPORTED_MEMORY_EVIDENCE"
    DURABLE_INTELLIGENCE_ELIGIBLE = "DURABLE_INTELLIGENCE_ELIGIBLE"
    PROHIBITED_VISUAL_INFERENCE = "PROHIBITED_VISUAL_INFERENCE"


class CustomerVisualEvidencePolicy:
    """Vision is descriptive current-turn context, never persistence authority."""

    ALLOWED_OBSERVATION_FIELDS = frozenset({
        "attachment_id", "person_visible", "person_count", "dog_visible",
        "animal_visible", "animals", "objects", "activity", "broad_scene", "smiling",
        "style_or_clothing_summary", "screenshot_or_meme", "visible_text_summary",
        "confidence",
    })
    PROHIBITED_FIELDS = frozenset({
        "race", "ethnicity", "religion", "health", "health_condition", "disability",
        "sexual_orientation", "sex_life", "political_affiliation", "trade_union",
        "criminal_history", "financial_status", "income", "wealth", "precise_location",
        "home_address", "identity", "identified_person", "person_name", "biometric",
        "face_embedding", "face_geometry", "identity_vector", "psychological_diagnosis",
        "personality_diagnosis", "age", "relationship_status", "relationship",
        "employment", "citizenship", "nationality", "ownership", "owner",
        "genital_description", "body_measurements", "sexual_attributes", "exif", "gps",
    })
    _SENSITIVE_VALUE_TERMS = (
        "race:", "ethnicity:", "religion:", "sexual orientation:", "political",
        "diagnosed", "home address:", "gps:", "face embedding", "genital",
    )

    @staticmethod
    def self_presentation(message, history=()):
        text = str(message or "").replace("’", "'")
        # Explicit alternate identity / ambiguity overrides self wording.
        if re.search(r"\b(?:not me|isn't me|is not me|my (?:friend|brother|sister|cousin)|celebrity|meme|someone else|random (?:guy|person)|could be me|might be me|pretend|joking|joke)\b", text, re.I):
            return False
        if re.search(r"\b(?:this is me|that'?s me|here'?s me|pic(?:ture)? of me|photo of me|selfie|my (?:ugly )?mug|here'?s what i look like|yours truly|putting a face to (?:the|a) name|see who (?:you(?:'re| are) (?:talking|chatting) to|is chatting you up))\b", text, re.I):
            return True
        return any(str((item.get('metadata') or {}).get('customer_image_solicitation') or '').upper() == 'NORMAL_IMAGE'
                   and str(item.get('sender_type') or '').lower() in {'ava', 'assistant'}
                   for item in list(history)[-3:] if isinstance(item, dict))

    @staticmethod
    def self_photo_established(context):
        evidence = dict((context or {}).get('self_photo_evidence') or {})
        return (evidence.get('version') == 'SELF_PHOTO_V1'
                and evidence.get('personVisible') is True
                and evidence.get('senderPresentation') is True
                and evidence.get('validatedCurrentTurn') is True)

    @classmethod
    def classify(cls, *, source: str, field: str | None = None) -> VisualEvidenceClass:
        normalized_source = str(source or "").upper()
        normalized_field = str(field or "").lower()
        if normalized_field in cls.PROHIBITED_FIELDS:
            return VisualEvidenceClass.PROHIBITED_VISUAL_INFERENCE
        if normalized_source == "CUSTOMER_TEXT":
            return VisualEvidenceClass.TEXT_SUPPORTED_MEMORY_EVIDENCE
        if normalized_source == "OPERATOR_AUTHORITY":
            return VisualEvidenceClass.DURABLE_INTELLIGENCE_ELIGIBLE
        return VisualEvidenceClass.EPHEMERAL_VISUAL_CONTEXT

    @classmethod
    def sanitize_observations(
        cls, observations: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        accepted: list[dict[str, Any]] = []
        discarded_fields: set[str] = set()
        malformed = False
        if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
            observations = []
            malformed = True
        for item in observations:
            if not isinstance(item, Mapping):
                malformed = True
                continue
            row: dict[str, Any] = {}
            for key, value in item.items():
                name = str(key).lower()
                if name not in cls.ALLOWED_OBSERVATION_FIELDS:
                    discarded_fields.add(name)
                    continue
                if cls._contains_sensitive_value(value):
                    discarded_fields.add(name)
                    continue
                row[name] = value
            accepted.append(row)
        return accepted, {
            "unknown_or_prohibited_fields_discarded": sorted(discarded_fields),
            "malformed_observations_rejected": malformed,
            "persistence_authority": False,
            "evidence_class": VisualEvidenceClass.EPHEMERAL_VISUAL_CONTEXT.value,
        }

    @classmethod
    def minimum_persisted_result(cls, context: Mapping[str, Any]) -> dict[str, Any]:
        """Keep only correlation/policy state needed for delivery recovery and audit."""
        allowed = (
            "operation_id", "safety_state", "response_policy", "solicitation_state",
            "partial_failure", "creator_profile_id", "fanvue_account_id", "telegram_user_id",
        )
        result = {key: context.get(key) for key in allowed if context.get(key) is not None}
        if cls.self_photo_established(context):
            result['self_photo_evidence'] = dict(context['self_photo_evidence'])
        result.update({
            "visual_evidence_scope": VisualEvidenceClass.EPHEMERAL_VISUAL_CONTEXT.value,
            "customer_identity_authority": False,
            "customer_intelligence_created": False,
            "visual_observations_persisted": False,
        })
        return result

    @classmethod
    def _contains_sensitive_value(cls, value: Any) -> bool:
        values = value if isinstance(value, (list, tuple, set)) else (value,)
        text = " ".join(str(item).lower() for item in values)
        return any(term in text for term in cls._SENSITIVE_VALUE_TERMS)
