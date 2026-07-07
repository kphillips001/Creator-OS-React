class PremiumConversationContinuityService:
    """
    3D.20.4

    Premium Conversation Continuity Layer.

    PURPOSE:
    Prevent premium conversations from feeling stateless,
    disconnected, repetitive, or emotionally reset every message.

    This service does NOT send messages.
    This service does NOT override provider routing.
    This service does NOT bypass monetization safety.
    """

    def build_continuity_profile(
        self,
        buyer_memory: dict | None = None,
        conversation_state: dict | None = None,
        whale_retention_profile: dict | None = None,
        premium_relationship_memory_profile: dict | None = None,
        emotional_presence_profile: dict | None = None,
    ) -> dict:
        buyer_memory = buyer_memory or {}
        conversation_state = conversation_state or {}
        whale_retention_profile = whale_retention_profile or {}
        premium_relationship_memory_profile = (
            premium_relationship_memory_profile or {}
        )
        emotional_presence_profile = emotional_presence_profile or {}

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

        offers_shown_count = int(
            buyer_memory.get("offers_shown_count") or 0
        )

        messages_since_last_offer = int(
            buyer_memory.get("messages_since_last_offer") or 0
        )

        post_offer_nudge_count = int(
            buyer_memory.get("post_offer_nudge_count") or 0
        )

        last_message_type = (
            buyer_memory.get("last_message_type") or "normal"
        )

        last_route = (
            buyer_memory.get("last_route")
            or buyer_memory.get("current_route")
            or "chat"
        )

        continuity_strength = (
            premium_relationship_memory_profile.get(
                "intimacy_continuity_strength"
            )
            or "low"
        )

        attachment_mode = (
            premium_relationship_memory_profile.get(
                "relationship_attachment_mode"
            )
            or "neutral"
        )

        emotional_presence_mode = (
            emotional_presence_profile.get(
                "emotional_presence_mode"
            )
            or "standard"
        )

        pacing_style = (
            emotional_presence_profile.get("pacing_style")
            or "normal"
        )

        emotional_rhythm_style = (
            emotional_presence_profile.get(
                "emotional_rhythm_style"
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
            "premium_continuity_active": False,
            "continuity_mode": "standard",
            "emotional_trajectory_state": "neutral",
            "pacing_continuity_bias": "normal",
            "escalation_transition_style": "standard",
            "continuity_cta_suppression": "none",
            "relationship_progression_mode": "standard",
            "continuity_memory_weight": "normal",
            "emotional_consistency_bias": "standard",
            "immersion_continuity_priority": "normal",
            "response_transition_style": "normal",
            "gpt_instruction": "",
            "reasons": reasons,
        }

        if not is_high_value:
            reasons.append("not_high_value_or_whale")
            profile["gpt_instruction"] = (
                "Use normal conversational continuity. Do not force "
                "premium relationship callbacks for non-premium users."
            )
            return profile

        profile["premium_continuity_active"] = True
        reasons.append("premium_or_high_value_user")

        # --------------------------------------------------
        # Continuity mode
        # --------------------------------------------------

        if whale_retention_mode == "dormant_whale_rewarm":
            profile["continuity_mode"] = "rewarm_continuity"
            profile["emotional_trajectory_state"] = "rebuilding_familiarity"
            profile["response_transition_style"] = "soft_reentry"
            reasons.append("dormant_whale_continuity")

        elif whale_retention_mode == "reactivated_whale_recovery":
            profile["continuity_mode"] = "restored_premium_continuity"
            profile["emotional_trajectory_state"] = "restoring_momentum"
            profile["response_transition_style"] = "restore_then_escalate"
            reasons.append("reactivated_whale_continuity")

        elif is_whale:
            profile["continuity_mode"] = "active_whale_continuity"
            profile["emotional_trajectory_state"] = "premium_relationship_flow"
            profile["response_transition_style"] = "smooth_premium_flow"
            reasons.append("active_whale_continuity")

        else:
            profile["continuity_mode"] = "high_value_continuity"
            profile["emotional_trajectory_state"] = "developing_premium_flow"
            profile["response_transition_style"] = "gentle_progression"
            reasons.append("high_value_continuity")

        # --------------------------------------------------
        # Pacing continuity
        # --------------------------------------------------

        if pacing_style in [
            "slow_premium",
            "relationship_first_slow",
            "slow_rewarm",
            "restorative",
        ]:
            profile["pacing_continuity_bias"] = "slow_consistent"
            profile["escalation_transition_style"] = "gradual_transition"
            reasons.append("slow_pacing_continuity")

        elif conversation_mode in ["tension", "conversion"]:
            profile["pacing_continuity_bias"] = "controlled_escalation"
            profile["escalation_transition_style"] = "smooth_escalation"
            reasons.append("controlled_escalation_continuity")

        else:
            profile["pacing_continuity_bias"] = "balanced_continuity"
            profile["escalation_transition_style"] = "gentle_transition"
            reasons.append("balanced_continuity")

        # --------------------------------------------------
        # Relationship progression
        # --------------------------------------------------

        if continuity_strength in ["very_strong", "strong"]:
            profile["relationship_progression_mode"] = (
                "immersive_continuity"
            )
            profile["continuity_memory_weight"] = "high"
            profile["immersion_continuity_priority"] = "high"
            reasons.append("strong_relationship_continuity")

        elif continuity_strength == "moderate":
            profile["relationship_progression_mode"] = (
                "moderate_continuity"
            )
            profile["continuity_memory_weight"] = "medium"
            reasons.append("moderate_relationship_continuity")

        else:
            profile["relationship_progression_mode"] = (
                "light_continuity"
            )
            profile["continuity_memory_weight"] = "light"
            reasons.append("light_relationship_continuity")

        # --------------------------------------------------
        # Emotional consistency
        # --------------------------------------------------

        if attachment_mode in [
            "premium_emotional_attachment",
            "subscriber_loyalty_attachment",
        ]:
            profile["emotional_consistency_bias"] = (
                "attachment_consistent"
            )
            reasons.append("attachment_consistency")

        elif emotional_presence_mode in [
            "high_touch_premium_presence",
            "warm_premium_presence",
            "premium_recovery_presence",
            "familiar_rewarm_presence",
        ]:
            profile["emotional_consistency_bias"] = (
                "presence_consistent"
            )
            reasons.append("presence_consistency")

        else:
            profile["emotional_consistency_bias"] = (
                "standard_consistency"
            )
            reasons.append("standard_consistency")

        # --------------------------------------------------
        # CTA suppression continuity
        # --------------------------------------------------

        repeated_cta_pressure = bool(
            offers_shown_count >= 3
            or post_offer_nudge_count >= 2
            or (
                last_route == "sales"
                and messages_since_last_offer <= 1
            )
        )

        if repeated_cta_pressure and reduce_sales_pressure:
            profile["continuity_cta_suppression"] = "high"
            reasons.append("repeated_cta_pressure_suppressed")

        elif reduce_sales_pressure:
            profile["continuity_cta_suppression"] = "medium"
            reasons.append("relationship_first_cta_reduction")

        elif intent_score >= 70 and heat_score >= 60:
            profile["continuity_cta_suppression"] = "low"
            reasons.append("high_intent_low_suppression")

        else:
            profile["continuity_cta_suppression"] = "normal"
            reasons.append("standard_cta_continuity")

        if last_message_type == "soft_transition":
            profile["response_transition_style"] = "continue_soft_transition"
            reasons.append("soft_transition_continuity")

        if emotional_rhythm_style == "continuous_relationship_rhythm":
            profile["emotional_trajectory_state"] = (
                "continuous_relationship_flow"
            )
            reasons.append("continuous_relationship_rhythm_applied")

        profile["gpt_instruction"] = self._build_gpt_instruction(
            profile
        )

        return profile

    def _build_gpt_instruction(self, profile: dict) -> str:
        return (
            "Premium conversation continuity is active. "
            f"Continuity mode: {profile.get('continuity_mode')}. "
            f"Emotional trajectory: "
            f"{profile.get('emotional_trajectory_state')}. "
            f"Pacing continuity: "
            f"{profile.get('pacing_continuity_bias')}. "
            f"Escalation transition: "
            f"{profile.get('escalation_transition_style')}. "
            f"CTA suppression: "
            f"{profile.get('continuity_cta_suppression')}. "
            f"Relationship progression: "
            f"{profile.get('relationship_progression_mode')}. "
            f"Response transition: "
            f"{profile.get('response_transition_style')}. "
            "Preserve emotional trajectory, avoid abrupt tone resets, "
            "avoid repetitive CTA loops, and make the conversation feel "
            "like it is continuing from prior emotional context."
        )