"""Single facial-expression authority for canonical explicit prompts."""

from __future__ import annotations

from dataclasses import dataclass


EXPLICIT_EXPRESSION_SECTION = "EXPLICIT EXPRESSION PROFILE"


@dataclass(frozen=True)
class ExplicitExpressionProfile:
    """Deterministic emotional performance, independent of scene construction."""

    concept_tier: str
    emotional_identity: str
    facial_expression: str
    eye_contact: str
    performance_limits: str

    def render(self) -> str:
        return "\n".join(
            (
                f"Emotional identity: {self.emotional_identity}",
                f"Facial expression: {self.facial_expression}",
                f"Eye contact: {self.eye_contact}",
                f"Performance limits: {self.performance_limits}",
            )
        )


class ExplicitExpressionProfileService:
    """Build the one canonical expression profile for an explicit prompt."""

    _SOFTCORE = ExplicitExpressionProfile(
        concept_tier="softcore",
        emotional_identity=(
            "sensual, intimate, emotionally engaged, restrained, and quietly confident"
        ),
        facial_expression=(
            "serious seductive expression with relaxed features, bedroom eyes, "
            "and lips softly parted"
        ),
        eye_contact=(
            "intimate, emotionally connected eye contact when appropriate, while "
            "preserving any explicit off-camera gaze"
        ),
        performance_limits=(
            "no default smiling, grinning, laughing, tongue-out teasing, goofy "
            "mugging, playful performer expression, or commercial adult-performer energy"
        ),
    )
    _HARDCORE = ExplicitExpressionProfile(
        concept_tier="hardcore",
        emotional_identity=(
            "sensual, intimate, emotionally engaged, intensely aroused, restrained, "
            "and charged with stronger emotional tension"
        ),
        facial_expression=(
            "serious seductive expression with heightened intensity, bedroom eyes, "
            "and lips softly parted"
        ),
        eye_contact=(
            "strong emotionally connected eye contact when appropriate, while "
            "preserving any explicit off-camera gaze"
        ),
        performance_limits=(
            "no default smiling, grinning, laughing, tongue-out teasing, goofy "
            "mugging, playful performer expression, or commercial adult-performer energy"
        ),
    )

    @classmethod
    def build(
        cls,
        concept_tier: str | None,
        operator_expression: str | None = None,
    ) -> ExplicitExpressionProfile:
        tier = str(concept_tier or "softcore").strip().lower()
        base = cls._HARDCORE if tier == "hardcore" else cls._SOFTCORE
        explicit_override = str(operator_expression or "").strip()
        if not explicit_override:
            return base
        return ExplicitExpressionProfile(
            concept_tier=base.concept_tier,
            emotional_identity=base.emotional_identity,
            facial_expression=(
                f"{explicit_override}; this operator-requested expression is the "
                "only exception to the default facial policy"
            ),
            eye_contact=base.eye_contact,
            performance_limits=(
                "avoid any smiling, tongue, playful, goofy, or commercial performer "
                "behavior not explicitly included in the operator request"
            ),
        )
