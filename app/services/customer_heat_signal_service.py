"""Canonical current-turn customer heat projection.

This projection can make commercial evaluation relevant. It never selects an
offering, creates an intent, or authorizes delivery.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence


class CustomerHeatSignalService:
    """Compose route semantics with bounded deterministic evidence."""

    AROUSAL = re.compile(
        r"\b(?:frisk(?:y|ier)|horny|turned on|aroused|tingl(?:e|ing)|hot and bothered)\b",
        re.I,
    )
    PHYSICAL_PRESENCE = re.compile(
        r"\b(?:wish|want|need)\s+you\s+(?:were\s+)?(?:here|with me|beside me|next to me)\b",
        re.I,
    )
    FANTASY = re.compile(
        r"\b(?:fantas(?:y|ize|ising|izing)|naughty thoughts?|imagin(?:e|ing)\s+you|"
        r"dream(?:ing)?\s+about\s+you)\b",
        re.I,
    )
    INTIMATE_CONTENT = re.compile(
        r"\b(?:sexy|intimate|private|naughty|nude|naked)\s+"
        r"(?:photo(?:s)?|pic(?:s|tures?)?|content|video(?:s)?|set)\b",
        re.I,
    )
    CONTENT_REQUEST = re.compile(
        r"\b(?:show|send|let me see|can i see|want to see|unlock|buy)\b.{0,36}"
        r"\b(?:photo(?:s)?|pic(?:s|tures?)?|content|video(?:s)?|set|you)\b",
        re.I,
    )
    ORDINARY_COMPLIMENT = re.compile(
        r"^\s*(?:you(?:'re| are)|u r)?\s*(?:so\s+)?"
        r"(?:beautiful|pretty|gorgeous|cute|lovely)(?:\s+today)?[.!\s\U0001f600-\U0001faff]*$",
        re.I,
    )
    AVA_HEAT = re.compile(
        r"(?:\U0001f60f|\U0001f609|\U0001f525)|\b(?:naughty|trouble|teas(?:e|ing)|"
        r"tempting|want me|craving|turn(?:ed|ing)? on|sexy|intimate)\b",
        re.I,
    )

    def project(self, *, message: str, classifier_result: Mapping | None = None,
                contextual_tone: Mapping | None = None,
                recent_transcript: Sequence[Mapping] = ()) -> dict:
        text = str(message or "").strip()
        classifier = dict(classifier_result or {})
        tone = dict(contextual_tone or {})
        evidence: list[str] = []
        content_request = bool(self.CONTENT_REQUEST.search(text))
        direct_commercial = bool(
            classifier.get("buying_intent") is True
            or classifier.get("monetization_intent") is True
            or classifier.get("content_request") is True
            or content_request
        )
        content_interest = bool(self.INTIMATE_CONTENT.search(text))
        arousal = bool(self.AROUSAL.search(text))
        physical = bool(self.PHYSICAL_PRESENCE.search(text))
        fantasy = bool(self.FANTASY.search(text))
        deterministic_hot = tone.get("sexualOrProvocative") is True
        semantic_sexual = classifier.get("sexual_engagement") is True
        semantic_confidence = float(classifier.get("confidence") or 0.0)
        semantic_strong = bool(
            classifier.get("explicit_without_buying_intent") is True
            or classifier.get("escalation_ready") is True
            or str(classifier.get("recommended_action") or "").lower()
               in {"build_tension", "offer", "close", "custom_request"}
        )
        semantic_qualified = bool(
            semantic_sexual and semantic_strong and semantic_confidence >= 0.72
        )
        checks = (
            (direct_commercial, "CURRENT_COMMERCIAL_INTEREST"),
            (content_request, "INTIMATE_CONTENT_REQUEST"),
            (content_interest, "INTIMATE_CONTENT_INTEREST"),
            (fantasy, "SEXUAL_FANTASY"),
            (arousal, "SEXUAL_AROUSAL"),
            (physical, "PHYSICAL_PRESENCE_SUGGESTION"),
            (deterministic_hot and semantic_strong, "STRONG_CUSTOMER_ESCALATION"),
            (semantic_qualified, "PLAYFUL_SUGGESTIVE"),
        )
        signal_type = next((kind for matched, kind in checks if matched), "NONE")
        for matched, label in (
            (semantic_sexual, "SEMANTIC_ROUTE_SEXUAL_ENGAGEMENT"),
            (semantic_strong, "SEMANTIC_ROUTE_STRONG_CURRENT_TURN"),
            (deterministic_hot, "DETERMINISTIC_CURRENT_HOT_TONE"),
            (arousal, "CURRENT_AROUSAL_SEMANTICS"),
            (physical, "CURRENT_PHYSICAL_PRESENCE_SUGGESTION"),
            (fantasy, "CURRENT_FANTASY_SEMANTICS"),
            (content_interest, "CURRENT_INTIMATE_CONTENT_INTEREST"),
            (direct_commercial, "CURRENT_COMMERCIAL_OR_CONTENT_REQUEST"),
        ):
            if matched:
                evidence.append(label)
        detected = signal_type != "NONE"
        ordinary_compliment = bool(self.ORDINARY_COMPLIMENT.fullmatch(text))
        prior_ava_heat = any(
            str(item.get("role") or "").lower() in {"assistant", "ava"}
            and bool(self.AVA_HEAT.search(str(item.get("content") or "")))
            for item in tuple(recent_transcript or ())[-4:]
            if isinstance(item, Mapping)
        )
        semantic_material_escalation = bool(
            semantic_qualified and semantic_confidence >= 0.90
            and len(re.findall(r'\w+', text)) >= 8
            and classifier.get('escalation_ready') is True
            and classifier.get('explicit_without_buying_intent') is True
        )
        if semantic_material_escalation:
            evidence.append('CURRENT_SEMANTIC_MATERIAL_ESCALATION')
        material_escalation = bool(
            direct_commercial or content_interest or arousal or physical or fantasy
            or semantic_material_escalation
        )
        initiation_source = (
            "CUSTOMER_ESCALATED" if prior_ava_heat and material_escalation
            else "AVA_INITIATED_RECIPROCATION" if prior_ava_heat and detected
            else "CUSTOMER_INITIATED" if detected
            else "AMBIGUOUS"
        )
        strong = bool(
            direct_commercial or content_interest or arousal or physical or fantasy
            or semantic_qualified
        ) and not ordinary_compliment
        confidence = semantic_confidence if semantic_sexual else 0.0
        confidence = max(0.0, min(1.0, confidence or (0.86 if strong else 0.0)))
        eligible = bool(
            text and detected and strong
            and initiation_source in {"CUSTOMER_INITIATED", "CUSTOMER_ESCALATED"}
        )
        return {
            "detected": detected,
            "customerInitiated": initiation_source == "CUSTOMER_INITIATED",
            "customerEscalated": initiation_source == "CUSTOMER_ESCALATED",
            "initiationSource": initiation_source,
            "type": signal_type,
            "strength": "STRONG" if eligible else "MODERATE" if detected else "NONE",
            "confidence": confidence,
            "currentTurnEvidence": tuple(dict.fromkeys(evidence)),
            "warmupOverrideEligible": eligible,
            "currentTurn": True,
            "historicalEvidenceUsedForOverride": False,
            "rejectionReasons": tuple(
                ["SEMANTIC_CONFIDENCE_BELOW_THRESHOLD"]
                if semantic_sexual and semantic_strong and not semantic_qualified
                and not (direct_commercial or content_interest or arousal or physical or fantasy)
                else ["AVA_INITIATED_RECIPROCATION_NOT_AUTHORITATIVE"]
                if initiation_source == "AVA_INITIATED_RECIPROCATION" else []
            ),
            "authority": "CUSTOMER_HEAT_SIGNAL_CANONICAL_V1",
        }
