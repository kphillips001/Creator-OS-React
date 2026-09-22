"""Block customer-facing narration of internal conversation policy."""
from __future__ import annotations

import re


class PolicyNarrationQualityService:
    """Detect policy narration while preserving independently required safety."""

    NARRATION = re.compile(
        r"\b(?:"
        r"(?:that\s+)?(?:more\s+)?intimate\s+side\s+of\s+me\s+is\s+for\s+supporters?|"
        r"(?:real\s+)?supporters?\s+(?:only|pay|buy|get\s+(?:that|this)\s+side)|"
        r"keep\s+(?:it|things|this|the\s+conversation)\s+(?:non[- ]?sexual|clean|appropriate)|"
        r"(?:let(?:'s|\s+us)|we(?:'ll|\s+will))\s+keep\s+it\s+non[- ]?sexual|"
        r"(?:my|the)\s+(?:content\s+)?entitlement\s+policy|"
        r"(?:moderation|internal\s+commercial|sales)\s+(?:policy|restriction)|"
        r"i\s+can(?:not|'t)\s+engage\s+(?:sexually|in\s+explicit\s+conversation)\s+"
        r"because\s+of\s+(?:policy|your\s+(?:buyer|supporter)\s+status)"
        r")\b",
        re.I,
    )

    @staticmethod
    def safety_boundary_required(diagnostics: dict) -> bool:
        safety = dict(diagnostics.get("safetyBoundary") or {})
        return bool(
            diagnostics.get("independentSafetyBoundaryRequired") is True
            or diagnostics.get("requiredSafetyBoundary") is True
            or safety.get("required") is True
            or safety.get("independentlyRequired") is True
        )

    @staticmethod
    def premium_value_boundary_authorized(diagnostics: dict) -> bool:
        policy = dict(
            diagnostics.get("post_nudge_conversation_policy")
            or diagnostics.get("postNudgeConversationPolicy") or {}
        )
        return bool(
            policy.get("premiumValueBoundaryAuthorized") is True
            and policy.get("responsePurpose") == "PREMIUM_VALUE_BOUNDARY"
        )

    @classmethod
    def violation(cls, text: str, *, diagnostics=None) -> bool:
        evidence = dict(diagnostics or {})
        value = str(text or "")
        match = cls.NARRATION.search(value)
        if not match or cls.safety_boundary_required(evidence):
            return False
        if cls.premium_value_boundary_authorized(evidence):
            return bool(re.search(
                r"keep\s+(?:it|things|this|the\s+conversation)\s+"
                r"(?:non[- ]?sexual|clean|appropriate)", value, re.I,
            ))
        return True
