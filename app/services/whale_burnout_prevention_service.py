class WhaleBurnoutPreventionService:
    """
    3D.20.5

    Whale Burnout Prevention.

    PURPOSE:
    Detect when whales/high-value users may be experiencing
    monetization fatigue, emotional fatigue, overexposure, or
    excessive CTA pressure.

    This service does NOT send messages.
    This service does NOT override provider routing.
    This service does NOT bypass monetization safety.

    It only prepares burnout-prevention context for:

    - DecisionEngine working_memory
    - GPT/Grok behavior_context
    - dashboard debug visibility
    """

    def build_burnout_profile(
        self,
        buyer_memory: dict | None = None,
        conversation_state: dict | None = None,
        whale_retention_profile: dict | None = None,
        premium_relationship_memory_profile: dict | None = None,
        emotional_presence_profile: dict | None = None,
        premium_conversation_continuity_profile: dict | None = None,
    ) -> dict:
        buyer_memory = buyer_memory or {}
        conversation_state = conversation_state or {}
        whale_retention_profile = whale_retention_profile or {}
        premium_relationship_memory_profile = (
            premium_relationship_memory_profile or {}
        )
        emotional_presence_profile = emotional_presence_profile or {}
        premium_conversation_continuity_profile = (
            premium_conversation_continuity_profile or {}
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

        offers_shown_count = int(
            buyer_memory.get("offers_shown_count") or 0
        )

        post_offer_nudge_count = int(
            buyer_memory.get("post_offer_nudge_count") or 0
        )

        messages_since_last_offer = int(
            buyer_memory.get("messages_since_last_offer") or 0
        )

        conversation_streak = int(
            buyer_memory.get("conversation_streak") or 0
        )

        engagement_depth_score = int(
            buyer_memory.get("engagement_depth_score") or 0
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

        last_content_outcome = (
            buyer_memory.get("last_content_outcome")
            or "unknown"
        )

        last_route = (
            buyer_memory.get("last_route")
            or buyer_memory.get("current_route")
            or "chat"
        )

        offer_state = (
            buyer_memory.get("offer_state")
            or "none"
        )

        reduce_sales_pressure = bool(
            whale_retention_profile.get("reduce_sales_pressure")
        )

        continuity_cta_suppression = (
            premium_conversation_continuity_profile.get(
                "continuity_cta_suppression"
            )
            or "none"
        )

        emotional_presence_mode = (
            emotional_presence_profile.get(
                "emotional_presence_mode"
            )
            or "standard"
        )

        relationship_progression_mode = (
            premium_conversation_continuity_profile.get(
                "relationship_progression_mode"
            )
            or "standard"
        )

        emotional_familiarity_level = (
            premium_relationship_memory_profile.get(
                "emotional_familiarity_level"
            )
            or "low"
        )

        reasons = []

        profile = {
            "success": True,
            "whale_burnout_prevention_active": False,
            "burnout_risk": "none",
            "monetization_fatigue_level": "none",
            "emotional_fatigue_level": "none",
            "cta_fatigue_level": "none",
            "pacing_slowdown_required": False,
            "soft_presence_mode": False,
            "emotional_recovery_mode": "none",
            "offer_pressure_reduction": "none",
            "immersion_recovery_priority": "normal",
            "recommended_next_energy": "standard",
            "burnout_safe_response_bias": "standard",
            "gpt_instruction": "",
            "reasons": reasons,
        }

        if not is_high_value:
            reasons.append("not_high_value_or_whale")
            profile["gpt_instruction"] = (
                "Use normal pacing. Burnout prevention is not active "
                "for non-premium users."
            )
            return profile

        profile["whale_burnout_prevention_active"] = True
        reasons.append("premium_or_high_value_user")

        # --------------------------------------------------
        # Monetization fatigue
        # --------------------------------------------------

        heavy_offer_pressure = bool(
            offers_shown_count >= 4
            or post_offer_nudge_count >= 2
            or (
                last_route == "sales"
                and messages_since_last_offer <= 1
            )
            or offer_state in ["offered", "nudged"]
        )

        moderate_offer_pressure = bool(
            offers_shown_count >= 2
            or post_offer_nudge_count >= 1
            or messages_since_last_offer <= 2
        )

        if heavy_offer_pressure:
            profile["monetization_fatigue_level"] = "high"
            profile["cta_fatigue_level"] = "high"
            reasons.append("heavy_offer_pressure_detected")

        elif moderate_offer_pressure:
            profile["monetization_fatigue_level"] = "medium"
            profile["cta_fatigue_level"] = "medium"
            reasons.append("moderate_offer_pressure_detected")

        else:
            profile["monetization_fatigue_level"] = "low"
            profile["cta_fatigue_level"] = "low"
            reasons.append("low_offer_pressure")

        # --------------------------------------------------
        # Emotional fatigue
        # --------------------------------------------------

        low_engagement_after_pressure = bool(
            heavy_offer_pressure
            and engagement_depth_score <= 4
            and intent_score < 40
        )

        long_session_low_momentum = bool(
            conversation_streak >= 15
            and intent_score < 35
            and heat_score < 45
        )

        ignored_content_signal = bool(
            last_content_outcome == "ignored"
        )

        if low_engagement_after_pressure:
            profile["emotional_fatigue_level"] = "high"
            reasons.append("low_engagement_after_pressure")

        elif long_session_low_momentum:
            profile["emotional_fatigue_level"] = "medium"
            reasons.append("long_session_low_momentum")

        elif ignored_content_signal:
            profile["emotional_fatigue_level"] = "medium"
            reasons.append("ignored_content_signal")

        else:
            profile["emotional_fatigue_level"] = "low"
            reasons.append("low_emotional_fatigue")

        # --------------------------------------------------
        # Burnout risk
        # --------------------------------------------------

        if (
            profile["monetization_fatigue_level"] == "high"
            and profile["emotional_fatigue_level"] in ["high", "medium"]
        ):
            profile["burnout_risk"] = "high"
            reasons.append("high_burnout_risk")

        elif (
            profile["monetization_fatigue_level"] in ["high", "medium"]
            or profile["emotional_fatigue_level"] == "medium"
        ):
            profile["burnout_risk"] = "medium"
            reasons.append("medium_burnout_risk")

        else:
            profile["burnout_risk"] = "low"
            reasons.append("low_burnout_risk")

        # --------------------------------------------------
        # Burnout prevention actions
        # --------------------------------------------------

        if profile["burnout_risk"] == "high":
            profile["pacing_slowdown_required"] = True
            profile["soft_presence_mode"] = True
            profile["emotional_recovery_mode"] = (
                "active_recovery"
            )
            profile["offer_pressure_reduction"] = "maximum"
            profile["immersion_recovery_priority"] = "critical"
            profile["recommended_next_energy"] = (
                "soft_validating_presence"
            )
            profile["burnout_safe_response_bias"] = (
                "no_cta_emotional_recovery"
            )
            reasons.append("high_risk_recovery_actions")

        elif profile["burnout_risk"] == "medium":
            profile["pacing_slowdown_required"] = True
            profile["soft_presence_mode"] = True
            profile["emotional_recovery_mode"] = (
                "soft_rebalance"
            )
            profile["offer_pressure_reduction"] = "high"
            profile["immersion_recovery_priority"] = "high"
            profile["recommended_next_energy"] = (
                "warm_low_pressure"
            )
            profile["burnout_safe_response_bias"] = (
                "delay_cta_rebuild_warmth"
            )
            reasons.append("medium_risk_rebalance_actions")

        else:
            profile["emotional_recovery_mode"] = (
                "maintenance"
            )
            profile["offer_pressure_reduction"] = (
                "medium" if reduce_sales_pressure else "low"
            )
            profile["recommended_next_energy"] = (
                "relationship_first"
                if reduce_sales_pressure
                else "standard"
            )
            profile["burnout_safe_response_bias"] = (
                "relationship_first_pacing"
                if reduce_sales_pressure
                else "standard"
            )
            reasons.append("low_risk_maintenance_actions")

        # --------------------------------------------------
        # Continuity + presence modifiers
        # --------------------------------------------------

        if continuity_cta_suppression == "high":
            profile["offer_pressure_reduction"] = "maximum"
            profile["pacing_slowdown_required"] = True
            reasons.append("continuity_cta_suppression_applied")

        if emotional_presence_mode in [
            "familiar_rewarm_presence",
            "premium_recovery_presence",
        ]:
            profile["soft_presence_mode"] = True
            profile["immersion_recovery_priority"] = "high"
            reasons.append("recovery_presence_mode_applied")

        if relationship_progression_mode == "immersive_continuity":
            reasons.append("immersive_continuity_preserved")

        if emotional_familiarity_level in ["high", "very_high"]:
            reasons.append("familiarity_preserved_during_burnout_check")

        profile["gpt_instruction"] = self._build_gpt_instruction(
            profile
        )

        return profile

    def _build_gpt_instruction(self, profile: dict) -> str:
        return (
            "Whale burnout prevention is active. "
            f"Burnout risk: {profile.get('burnout_risk')}. "
            f"Monetization fatigue: "
            f"{profile.get('monetization_fatigue_level')}. "
            f"Emotional fatigue: "
            f"{profile.get('emotional_fatigue_level')}. "
            f"CTA fatigue: {profile.get('cta_fatigue_level')}. "
            f"Pacing slowdown required: "
            f"{profile.get('pacing_slowdown_required')}. "
            f"Emotional recovery mode: "
            f"{profile.get('emotional_recovery_mode')}. "
            f"Offer pressure reduction: "
            f"{profile.get('offer_pressure_reduction')}. "
            f"Recommended next energy: "
            f"{profile.get('recommended_next_energy')}. "
            "If burnout risk is medium or high, reduce selling pressure, "
            "avoid CTA loops, use softer emotional presence, rebuild warmth, "
            "and preserve immersion before attempting more monetization."
        )