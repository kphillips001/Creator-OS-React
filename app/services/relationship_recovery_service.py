class RelationshipRecoveryService:
    """
    3D.20.8

    Detects relationship drift and determines
    intelligent emotional recovery behavior.

    PURPOSE:

    Prevent:
    - emotional detachment
    - fading immersion
    - whale cooling
    - intimacy stagnation
    - silent disengagement

    while preserving:
    - relationship continuity
    - emotional realism
    - monetization pacing
    - immersion quality
    """

    def build_recovery_profile(
        self,
        buyer_memory: dict,
        conversation_state: dict,
        long_term_stability_profile: dict,
        burnout_profile: dict,
    ) -> dict:

        conversation_streak = int(
            conversation_state.get(
                "conversation_streak",
                0,
            )
            or 0
        )

        engagement_depth_score = int(
            conversation_state.get(
                "engagement_depth_score",
                0,
            )
            or 0
        )

        emotional_fatigue_level = (
            burnout_profile.get(
                "emotional_fatigue_level"
            )
            or "low"
        )

        stability_level = (
            long_term_stability_profile.get(
                "stability_level"
            )
            or "stable"
        )

        recovery_risk = "low"

        if (
            conversation_streak <= 2
            and engagement_depth_score <= 2
        ):
            recovery_risk = "medium"

        if (
            emotional_fatigue_level == "high"
            or stability_level == "fragile"
        ):
            recovery_risk = "high"

        recovery_mode = "none"

        if recovery_risk == "medium":
            recovery_mode = "warm_reengagement"

        elif recovery_risk == "high":
            recovery_mode = "soft_emotional_recovery"

        reduce_pressure = (
            recovery_risk != "low"
        )

        increase_presence = (
            recovery_risk in [
                "medium",
                "high",
            ]
        )

        recovery_cta_suppression = (
            recovery_risk == "high"
        )

        return {
            "relationship_recovery_active": True,
            "recovery_risk": recovery_risk,
            "recovery_mode": recovery_mode,
            "reduce_pressure": reduce_pressure,
            "increase_presence": increase_presence,
            "recovery_cta_suppression": (
                recovery_cta_suppression
            ),
            "gpt_instruction": (
                "Focus on rebuilding emotional momentum naturally "
                "without aggressive selling."
            ),
        }