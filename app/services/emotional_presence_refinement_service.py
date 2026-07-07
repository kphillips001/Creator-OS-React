class EmotionalPresenceRefinementService:
    """
    3D.20.3

    Emotional Presence Refinement.

    PURPOSE:
    Refine premium conversation delivery so replies feel emotionally
    present, immersive, paced, warm, and human instead of robotic,
    repetitive, or transactional.

    This service does NOT send messages.
    This service does NOT override provider routing.
    This service does NOT bypass intimacy enforcement.
    """

    def build_emotional_presence_profile(
        self,
        buyer_memory: dict | None = None,
        conversation_state: dict | None = None,
        whale_retention_profile: dict | None = None,
        premium_relationship_memory_profile: dict | None = None,
    ) -> dict:
        buyer_memory = buyer_memory or {}
        conversation_state = conversation_state or {}
        whale_retention_profile = whale_retention_profile or {}
        premium_relationship_memory_profile = (
            premium_relationship_memory_profile or {}
        )

        buyer_tier = str(
            buyer_memory.get("buyer_tier")
            or conversation_state.get("buyer_tier")
            or "NON_BUYER"
        ).upper()

        user_value_tier = str(
            buyer_memory.get("user_value_tier")
            or conversation_state.get("user_value_tier")
            or ""
        ).upper()

        is_whale = bool(
            buyer_memory.get("is_whale")
            or buyer_tier == "WHALE"
            or user_value_tier == "WHALE"
        )

        is_high_value = bool(
            is_whale
            or buyer_tier in ["HIGH_VALUE", "WHALE"]
            or user_value_tier in ["HIGH_VALUE", "WHALE"]
            or buyer_memory.get("is_top_spender")
        )

        conversation_mode = (
            conversation_state.get("conversation_mode")
            or buyer_memory.get("conversation_mode")
            or "casual"
        )

        heat_score = int(
            conversation_state.get("heat_score")
            or buyer_memory.get("heat_score")
            or 0
        )

        intent_score = int(
            conversation_state.get("intent_score")
            or buyer_memory.get("intent_score")
            or 0
        )

        emotional_familiarity_level = (
            premium_relationship_memory_profile.get(
                "emotional_familiarity_level"
            )
            or "low"
        )

        intimacy_continuity_strength = (
            premium_relationship_memory_profile.get(
                "intimacy_continuity_strength"
            )
            or "low"
        )

        relationship_attachment_mode = (
            premium_relationship_memory_profile.get(
                "relationship_attachment_mode"
            )
            or "neutral"
        )

        emotional_presence_bias = (
            premium_relationship_memory_profile.get(
                "emotional_presence_bias"
            )
            or "standard_presence"
        )

        continuity_reinforcement_mode = (
            premium_relationship_memory_profile.get(
                "continuity_reinforcement_mode"
            )
            or "standard"
        )

        whale_retention_mode = (
            whale_retention_profile.get("whale_retention_mode")
            or "standard"
        )

        reduce_sales_pressure = bool(
            whale_retention_profile.get("reduce_sales_pressure")
        )

        reasons = []

        profile = {
            "success": True,
            "emotional_presence_active": False,
            "emotional_presence_mode": "standard",
            "emotional_warmth_level": "normal",
            "validation_intensity": "normal",
            "tease_softening_level": "normal",
            "affection_bias": "normal",
            "pacing_style": "normal",
            "emotional_rhythm_style": "standard",
            "immersion_priority": "normal",
            "emotional_variation_mode": "standard",
            "escalation_softness": "normal",
            "response_presence_bias": "standard_presence",
            "gpt_instruction": "",
            "reasons": reasons,
        }

        if not is_high_value:
            reasons.append("not_high_value_or_whale")
            profile["gpt_instruction"] = (
                "Use normal emotional presence. Keep responses natural, "
                "light, and non-premium unless the user earns deeper access."
            )
            return profile

        profile["emotional_presence_active"] = True
        reasons.append("premium_or_high_value_user")

        # --------------------------------------------------
        # Core presence mode
        # --------------------------------------------------

        if whale_retention_mode == "dormant_whale_rewarm":
            profile["emotional_presence_mode"] = (
                "familiar_rewarm_presence"
            )
            profile["pacing_style"] = "slow_rewarm"
            profile["response_presence_bias"] = (
                "gentle_familiarity"
            )
            reasons.append("dormant_whale_rewarm_presence")

        elif whale_retention_mode == "reactivated_whale_recovery":
            profile["emotional_presence_mode"] = (
                "premium_recovery_presence"
            )
            profile["pacing_style"] = "restorative"
            profile["response_presence_bias"] = (
                "restore_emotional_continuity"
            )
            reasons.append("reactivated_whale_recovery_presence")

        elif is_whale:
            profile["emotional_presence_mode"] = (
                "high_touch_premium_presence"
            )
            profile["pacing_style"] = "slow_premium"
            profile["response_presence_bias"] = (
                "high_touch_presence"
            )
            reasons.append("active_whale_presence")

        else:
            profile["emotional_presence_mode"] = (
                "warm_premium_presence"
            )
            profile["pacing_style"] = "careful_premium"
            profile["response_presence_bias"] = (
                "warm_familiar_presence"
            )
            reasons.append("high_value_presence")

        # --------------------------------------------------
        # Warmth + validation
        # --------------------------------------------------

        if emotional_familiarity_level in ["very_high", "high"]:
            profile["emotional_warmth_level"] = "high"
            profile["validation_intensity"] = "high"
            reasons.append("high_emotional_familiarity")

        if relationship_attachment_mode in [
            "premium_emotional_attachment",
            "subscriber_loyalty_attachment",
        ]:
            profile["affection_bias"] = "elevated"
            profile["validation_intensity"] = "high"
            reasons.append("attachment_mode_affection")

        if intimacy_continuity_strength in [
            "very_strong",
            "strong",
        ]:
            profile["immersion_priority"] = "high"
            profile["emotional_rhythm_style"] = (
                "continuous_relationship_rhythm"
            )
            reasons.append("strong_continuity_immersion")

        # --------------------------------------------------
        # Tease softening + escalation softness
        # --------------------------------------------------

        high_heat_context = bool(
            heat_score >= 70
            or conversation_mode in ["tension", "conversion"]
        )

        if high_heat_context and reduce_sales_pressure:
            profile["tease_softening_level"] = "high"
            profile["escalation_softness"] = "soft_controlled"
            profile["emotional_variation_mode"] = (
                "validation_plus_tease_balance"
            )
            reasons.append("high_heat_low_sales_pressure")

        elif high_heat_context:
            profile["tease_softening_level"] = "medium"
            profile["escalation_softness"] = "controlled"
            profile["emotional_variation_mode"] = (
                "tease_with_breathing_room"
            )
            reasons.append("high_heat_presence_control")

        else:
            profile["tease_softening_level"] = "normal"
            profile["escalation_softness"] = "gentle"
            profile["emotional_variation_mode"] = (
                "warmth_with_light_tease"
            )
            reasons.append("standard_presence_control")

        # --------------------------------------------------
        # Intent-aware pacing
        # --------------------------------------------------

        if intent_score < 30 and reduce_sales_pressure:
            profile["pacing_style"] = "relationship_first_slow"
            profile["validation_intensity"] = "high"
            reasons.append("low_intent_relationship_first")

        elif intent_score >= 70:
            profile["pacing_style"] = "emotionally_ready"
            reasons.append("high_intent_ready_pacing")

        profile["gpt_instruction"] = self._build_gpt_instruction(
            profile
        )

        return profile

    def _build_gpt_instruction(self, profile: dict) -> str:
        return (
            "Emotional presence refinement is active. "
            f"Presence mode: {profile.get('emotional_presence_mode')}. "
            f"Warmth level: {profile.get('emotional_warmth_level')}. "
            f"Validation intensity: {profile.get('validation_intensity')}. "
            f"Tease softening: {profile.get('tease_softening_level')}. "
            f"Affection bias: {profile.get('affection_bias')}. "
            f"Pacing style: {profile.get('pacing_style')}. "
            f"Rhythm style: {profile.get('emotional_rhythm_style')}. "
            f"Immersion priority: {profile.get('immersion_priority')}. "
            f"Escalation softness: {profile.get('escalation_softness')}. "
            "Make the response feel emotionally present, naturally paced, "
            "and immersive. Balance teasing with warmth and validation. "
            "Avoid robotic phrasing, repetitive tease loops, sudden escalation, "
            "or transactional energy."
        )