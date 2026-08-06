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

    # PPV face mood stack: combine teasing + naughty + seductive + sexually enticing
    # + appealing + salacious. Eyes stay fully open and alert — never half-lidded.
    _PPV_FACE_MOOD = (
        "teasing, naughty, seductive, sexually enticing, appealing, and salacious"
    )
    _PPV_EYE_CONTACT = (
        "locked camera eye contact that feels teasing, naughty, seductive, sexually "
        "enticing, appealing, and salacious at once; fully open alert eyes with sharp "
        "focused pupils and knowing private PPV intensity; eyes must look engaged, "
        "awake, and intentional — never droopy, sleepy, heavy-lidded, half-lidded, "
        "half-closed, vacant, or unfocused; preserve any explicit off-camera gaze only "
        "when the scene demands it"
    )
    _PPV_LIMITS = (
        "no default grinning, laughing, tongue-out goofy mugging, commercial "
        "adult-performer energy, sleepy eyes, droopy lids, half-lidded eyes, vacant "
        "stare, or deadpan blank face"
    )

    _SOFTCORE = ExplicitExpressionProfile(
        concept_tier="softcore",
        emotional_identity=(
            f"intimate private PPV energy that is {_PPV_FACE_MOOD}; "
            "emotionally engaged, restrained, and quietly confident"
        ),
        facial_expression=(
            f"{_PPV_FACE_MOOD} expression with alert features, fully open eyes, "
            "sharp focused pupils, slight brow lift of intent, and lips softly parted"
        ),
        eye_contact=_PPV_EYE_CONTACT,
        performance_limits=_PPV_LIMITS,
    )
    _HARDCORE = ExplicitExpressionProfile(
        concept_tier="hardcore",
        emotional_identity=(
            f"intimate private PPV energy that is {_PPV_FACE_MOOD}; "
            "intensely aroused, emotionally engaged, restrained, and charged with "
            "stronger wanting"
        ),
        facial_expression=(
            f"{_PPV_FACE_MOOD} expression with heightened intensity, fully open eyes, "
            "sharp focused pupils, tense brows of wanting, and lips softly parted"
        ),
        eye_contact=_PPV_EYE_CONTACT,
        performance_limits=_PPV_LIMITS,
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
                "only exception to the default facial policy, but eyes must still "
                "stay fully open, alert, teasing, naughty, seductive, sexually "
                "enticing, appealing, and salacious — never droopy, sleepy, or half-lidded"
            ),
            eye_contact=base.eye_contact,
            performance_limits=(
                "avoid any goofy, blank, or commercial performer behavior not "
                "explicitly included in the operator request; never render droopy, "
                "sleepy, heavy-lidded, or half-lidded eyes unless the operator "
                "request explicitly asks for that look"
            ),
        )
