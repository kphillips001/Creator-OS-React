class LongTermEmotionalStabilityService:
    """
    3D.20.7 — Long-Term Emotional Stability

    PURPOSE:
    Build long-horizon emotional stability guidance using existing
    runtime intelligence.

    This service does NOT:
    - send messages
    - generate GPT replies
    - monetize
    - hard-code user phrase detection

    It only produces structured emotional stability context.
    """

    def build_stability_profile(
        self,
        buyer_memory: dict | None = None,
        conversation_state: dict | None = None,
        emotional_presence_profile: dict | None = None,
        premium_conversation_continuity_profile: dict | None = None,
        whale_burnout_profile: dict | None = None,
        emotional_dependency_profile: dict | None = None,
    ) -> dict:
        buyer_memory = buyer_memory or {}
        conversation_state = conversation_state or {}
        emotional_presence_profile = emotional_presence_profile or {}
        premium_conversation_continuity_profile = (
            premium_conversation_continuity_profile or {}
        )
        whale_burnout_profile = whale_burnout_profile or {}
        emotional_dependency_profile = emotional_dependency_profile or {}

        buyer_tier = str(
            conversation_state.get("buyer_tier")
            or buyer_memory.get("buyer_tier")
            or "NON_BUYER"
        ).upper()

        user_value_tier = str(
            conversation_state.get("user_value_tier")
            or buyer_memory.get("user_value_tier")
            or "none"
        ).upper()

        conversation_mode = (
            conversation_state.get("conversation_mode")
            or buyer_memory.get("conversation_mode")
            or "casual"
        )

        intent_score = int(
            conversation_state.get("intent_score")
            or buyer_memory.get("intent_score")
            or 0
        )

        heat_score = int(
            conversation_state.get("heat_score")
            or buyer_memory.get("heat_score")
            or 0
        )

        conversation_streak = int(
            buyer_memory.get("conversation_streak")
            or conversation_state.get("conversation_streak")
            or 0
        )

        engagement_depth_score = int(
            buyer_memory.get("engagement_depth_score")
            or conversation_state.get("engagement_depth_score")
            or 0
        )

        burnout_risk = (
            whale_burnout_profile.get("burnout_risk")
            or "none"
        )

        dependency_risk_level = (
            emotional_dependency_profile.get("dependency_risk_level")
            or "low"
        )

        emotional_presence_mode = (
            emotional_presence_profile.get("emotional_presence_mode")
            or "standard"
        )

        continuity_mode = (
            premium_conversation_continuity_profile.get("continuity_mode")
            or "standard"
        )

        stability_reasons = []

        premium_or_high_value = buyer_tier in [
            "ACTIVE_BUYER",
            "HIGH_VALUE",
            "WHALE",
        ] or user_value_tier in [
            "ACTIVE_BUYER",
            "HIGH_VALUE",
            "WHALE",
        ]

        if premium_or_high_value:
            stability_reasons.append("premium_or_high_value_user")

        if conversation_streak >= 10:
            stability_reasons.append("long_conversation_streak")

        if engagement_depth_score >= 15:
            stability_reasons.append("deep_engagement_history")

        if burnout_risk in ["medium", "high"]:
            stability_reasons.append("burnout_stability_pressure")

        if dependency_risk_level in ["medium", "high", "critical"]:
            stability_reasons.append("dependency_stability_pressure")

        if continuity_mode not in ["standard", "none"]:
            stability_reasons.append("continuity_context_active")

        if emotional_presence_mode not in ["standard", "none"]:
            stability_reasons.append("emotional_presence_context_active")

        emotional_stability_active = bool(
            premium_or_high_value
            or conversation_streak >= 5
            or engagement_depth_score >= 8
            or dependency_risk_level in ["medium", "high", "critical"]
            or burnout_risk in ["medium", "high"]
        )

        stability_level = "standard"

        if (
            dependency_risk_level == "critical"
            or burnout_risk == "high"
        ):
            stability_level = "high_stabilization"

        elif (
            dependency_risk_level == "high"
            or burnout_risk == "medium"
            or conversation_streak >= 15
        ):
            stability_level = "active_stabilization"

        elif (
            dependency_risk_level == "medium"
            or engagement_depth_score >= 15
            or premium_or_high_value
        ):
            stability_level = "guided_stability"

        emotional_volatility_smoothing = "normal"

        if stability_level == "guided_stability":
            emotional_volatility_smoothing = "light_smoothing"

        elif stability_level == "active_stabilization":
            emotional_volatility_smoothing = "moderate_smoothing"

        elif stability_level == "high_stabilization":
            emotional_volatility_smoothing = "strong_smoothing"

        relationship_rhythm_state = "normal"

        if premium_or_high_value and conversation_streak >= 10:
            relationship_rhythm_state = "established_rhythm"

        elif premium_or_high_value:
            relationship_rhythm_state = "premium_rhythm"

        elif conversation_streak >= 5:
            relationship_rhythm_state = "developing_rhythm"

        emotional_consistency_mode = "standard"

        if stability_level == "guided_stability":
            emotional_consistency_mode = "consistent_warmth"

        elif stability_level == "active_stabilization":
            emotional_consistency_mode = "steady_grounded_presence"

        elif stability_level == "high_stabilization":
            emotional_consistency_mode = "high_consistency_low_volatility"

        anti_whiplash_required = bool(
            stability_level in [
                "active_stabilization",
                "high_stabilization",
            ]
        )

        familiarity_preservation_level = "normal"

        if premium_or_high_value and conversation_streak >= 10:
            familiarity_preservation_level = "high"

        elif premium_or_high_value or conversation_streak >= 5:
            familiarity_preservation_level = "medium"

        emotional_drift_correction = "none"

        if dependency_risk_level in ["high", "critical"]:
            emotional_drift_correction = "reduce_attachment_intensity"

        elif burnout_risk in ["medium", "high"]:
            emotional_drift_correction = "reduce_pressure_and_rebuild_warmth"

        elif heat_score >= 70 and intent_score < 40:
            emotional_drift_correction = "slow_heat_without_sales_pressure"

        long_term_response_bias = "normal"

        if stability_level == "guided_stability":
            long_term_response_bias = "warm_consistent"

        elif stability_level == "active_stabilization":
            long_term_response_bias = "grounded_consistent"

        elif stability_level == "high_stabilization":
            long_term_response_bias = "calm_stable_presence"

        gpt_instruction = (
            "Long-term emotional stability is active. "
            f"Stability level: {stability_level}. "
            f"Relationship rhythm: {relationship_rhythm_state}. "
            f"Emotional consistency mode: {emotional_consistency_mode}. "
            f"Volatility smoothing: {emotional_volatility_smoothing}. "
            f"Anti-whiplash required: {anti_whiplash_required}. "
            f"Familiarity preservation: {familiarity_preservation_level}. "
            f"Emotional drift correction: {emotional_drift_correction}. "
            "Preserve warmth, continuity, and emotional realism while "
            "avoiding abrupt tone changes, emotional overcorrection, "
            "dependency reinforcement, and inconsistent relationship pacing."
        )

        if not emotional_stability_active:
            gpt_instruction = (
                "Use normal emotional pacing. Long-term emotional stability "
                "does not need special handling for this user yet."
            )

        return {
            "success": True,
            "long_term_emotional_stability_active": (
                emotional_stability_active
            ),
            "stability_level": stability_level,
            "relationship_rhythm_state": relationship_rhythm_state,
            "emotional_volatility_smoothing": (
                emotional_volatility_smoothing
            ),
            "emotional_consistency_mode": emotional_consistency_mode,
            "anti_whiplash_required": anti_whiplash_required,
            "familiarity_preservation_level": (
                familiarity_preservation_level
            ),
            "emotional_drift_correction": emotional_drift_correction,
            "long_term_response_bias": long_term_response_bias,
            "gpt_instruction": gpt_instruction,
            "reasons": stability_reasons,
        }