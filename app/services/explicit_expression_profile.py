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

    # Explicit profiles describe emotional intent. Canonical facial anatomy and
    # natural human rendering are owned by the shared facial foundation.
    _PPV_FACE_MOOD = (
        "teasing, naughty, seductive, sexually enticing, appealing, and salacious"
    )
    _PPV_EYE_CONTACT = (
        "derive gaze naturally from the scene: teasing eye contact, a coy glance, an "
        "intimate off-camera look, or returning attention toward the viewer are all "
        "valid; preserve the scene's gaze direction and never force direct camera eye "
        "contact when the scene or operator requests otherwise"
    )
    _PPV_LIMITS = (
        "no default grinning, laughing, tongue-out goofy mugging, commercial "
        "adult-performer energy, vacant stare, deadpan blank face, rigid facial "
        "geometry, or exaggerated performance"
    )

    _SOFTCORE = ExplicitExpressionProfile(
        concept_tier="softcore",
        emotional_identity=(
            f"intimate private PPV energy that is {_PPV_FACE_MOOD}; "
            "emotionally engaged, restrained, and quietly confident"
        ),
        facial_expression=(
            f"natural scene-appropriate variation of {_PPV_FACE_MOOD} intent; use "
            "subtle wanting, playful seduction, coy warmth, or breathy intimacy as the "
            "scene supports, while keeping the performance believable"
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
            f"natural scene-appropriate variation of {_PPV_FACE_MOOD} intent with "
            "heightened arousal or stronger wanting where the scene supports it; keep "
            "the intensity believable rather than exaggerated"
        ),
        eye_contact=_PPV_EYE_CONTACT,
        performance_limits=_PPV_LIMITS,
    )

    @classmethod
    def build(
        cls,
        concept_tier: str | None,
        operator_expression: str | None = None,
        freeflow_expression: bool = False,
    ) -> ExplicitExpressionProfile:
        tier = str(concept_tier or "softcore").strip().lower()
        base = cls._HARDCORE if tier == "hardcore" else cls._SOFTCORE
        explicit_override = str(operator_expression or "").strip()
        if not explicit_override:
            return base
        eye_contact = (
            "follow the operator-requested facial performance and gaze direction "
            "exactly; do not replace it with default direct camera eye contact"
        )
        performance_limits = (
            "preserve exact facial identity and natural anatomy while honoring the "
            "operator's expression, gaze, eye, brow, and mouth direction"
        )
        if freeflow_expression:
            eye_contact = (
                "follow the operator-requested facial performance exactly, including its gaze direction; "
                "do not replace an averted, upward, downward, or returning gaze with default direct camera "
                "eye contact; preserve fully recognizable facial identity and natural, alert eyes"
            )
            performance_limits = (
                "preserve exact facial identity and anatomy while allowing the requested natural expression, "
                "gaze, mouth state, and head attitude; avoid random, exaggerated, cartoonish, goofy, blank, "
                "or commercial-performer behavior"
            )
        return ExplicitExpressionProfile(
            concept_tier=base.concept_tier,
            emotional_identity=base.emotional_identity,
            facial_expression=(
                f"{explicit_override}; preserve this operator-requested expression "
                "and gaze exactly as the authoritative facial-performance direction"
            ),
            eye_contact=eye_contact,
            performance_limits=performance_limits,
        )
