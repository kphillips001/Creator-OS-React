class PremiumRelationshipMemoryService:
    """
    3D.20.2

    Premium Relationship Memory Reinforcement.

    PURPOSE:
    Build lightweight emotional continuity intelligence for
    premium/high-value users so conversations feel remembered,
    familiar, relationship-driven, and emotionally progressive.

    This service does NOT send messages.
    This service does NOT override provider routing.
    This service does NOT bypass intimacy enforcement.

    It only prepares relationship-memory context for:

    - DecisionEngine working_memory
    - GPT/Grok behavior_context
    - dashboard debug visibility
    """

    def build_relationship_memory_profile(
        self,
        buyer_memory: dict | None = None,
        conversation_state: dict | None = None,
        whale_retention_profile: dict | None = None,
    ) -> dict:
        buyer_memory = buyer_memory or {}
        conversation_state = conversation_state or {}
        whale_retention_profile = whale_retention_profile or {}

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

        total_spend = float(
            buyer_memory.get("total_spend") or 0
        )

        purchase_count = int(
            buyer_memory.get("purchase_count") or 0
        )

        conversation_streak = int(
            buyer_memory.get("conversation_streak") or 0
        )

        engagement_depth_score = int(
            buyer_memory.get("engagement_depth_score") or 0
        )

        relationship_depth_score = int(
            buyer_memory.get("relationship_depth_score") or 0
        )

        buyer_momentum_score = int(
            buyer_memory.get("buyer_momentum_score") or 0
        )

        preferred_intensity_score = int(
            buyer_memory.get("preferred_intensity_score") or 5
        )

        last_content_outcome = (
            buyer_memory.get("last_content_outcome")
            or "unknown"
        )

        subscriber_profile = (
            buyer_memory.get("subscriber_profile")
            or "none"
        )

        conversation_mode = (
            conversation_state.get("conversation_mode")
            or buyer_memory.get("conversation_mode")
            or "casual"
        )

        emotional_priority_level = (
            whale_retention_profile.get("emotional_priority_level")
            or "normal"
        )

        whale_retention_mode = (
            whale_retention_profile.get("whale_retention_mode")
            or "standard"
        )

        reasons = []

        profile = {
            "success": True,
            "premium_relationship_memory_active": False,
            "emotional_familiarity_level": "low",
            "remembered_dynamic_style": "standard",
            "intimacy_continuity_strength": "low",
            "relationship_attachment_mode": "neutral",
            "premium_memory_priority": "normal",
            "emotional_callback_candidates": [],
            "emotional_presence_bias": "standard_presence",
            "continuity_reinforcement_mode": "standard",
            "gpt_instruction": "",
            "reasons": reasons,
        }

        if not is_high_value:
            reasons.append("not_high_value_or_whale")
            profile["gpt_instruction"] = (
                "Use normal conversational memory. Do not imply a deeper "
                "premium relationship history unless it exists."
            )
            return profile

        profile["premium_relationship_memory_active"] = True
        reasons.append("premium_or_high_value_user")

        # --------------------------------------------------
        # Emotional familiarity level
        # --------------------------------------------------

        if (
            is_whale
            or total_spend >= 1000
            or purchase_count >= 10
            or relationship_depth_score >= 50
            or conversation_streak >= 20
        ):
            profile["emotional_familiarity_level"] = "very_high"
            reasons.append("very_high_familiarity_signal")

        elif (
            total_spend >= 300
            or purchase_count >= 5
            or relationship_depth_score >= 25
            or conversation_streak >= 10
        ):
            profile["emotional_familiarity_level"] = "high"
            reasons.append("high_familiarity_signal")

        else:
            profile["emotional_familiarity_level"] = "medium"
            reasons.append("medium_familiarity_signal")

        # --------------------------------------------------
        # Remembered dynamic style
        # --------------------------------------------------

        if preferred_intensity_score >= 8:
            profile["remembered_dynamic_style"] = "playful_high_heat"
            reasons.append("high_intensity_preference")

        elif preferred_intensity_score <= 3:
            profile["remembered_dynamic_style"] = "soft_emotional"
            reasons.append("soft_intensity_preference")

        elif conversation_mode in ["tension", "conversion"]:
            profile["remembered_dynamic_style"] = "warm_tension"
            reasons.append("tension_mode_dynamic")

        else:
            profile["remembered_dynamic_style"] = "balanced_flirty"
            reasons.append("balanced_dynamic_default")

        # --------------------------------------------------
        # Continuity strength
        # --------------------------------------------------

        continuity_score = (
            conversation_streak
            + engagement_depth_score
            + relationship_depth_score
            + buyer_momentum_score
        )

        if continuity_score >= 90:
            profile["intimacy_continuity_strength"] = "very_strong"
            reasons.append("very_strong_continuity_score")

        elif continuity_score >= 45:
            profile["intimacy_continuity_strength"] = "strong"
            reasons.append("strong_continuity_score")

        elif continuity_score >= 15:
            profile["intimacy_continuity_strength"] = "moderate"
            reasons.append("moderate_continuity_score")

        else:
            profile["intimacy_continuity_strength"] = "light"
            reasons.append("light_continuity_score")

        # --------------------------------------------------
        # Attachment mode
        # --------------------------------------------------

        if emotional_priority_level in ["very_high", "critical"]:
            profile["relationship_attachment_mode"] = (
                "premium_emotional_attachment"
            )
            reasons.append("high_emotional_priority_attachment")

        elif subscriber_profile == "HIGH_VALUE_SUBSCRIBER":
            profile["relationship_attachment_mode"] = (
                "subscriber_loyalty_attachment"
            )
            reasons.append("high_value_subscriber_attachment")

        elif last_content_outcome == "success":
            profile["relationship_attachment_mode"] = (
                "reward_reinforced_attachment"
            )
            reasons.append("successful_content_attachment")

        else:
            profile["relationship_attachment_mode"] = (
                "developing_attachment"
            )
            reasons.append("developing_attachment_default")

        # --------------------------------------------------
        # Memory priority
        # --------------------------------------------------

        if is_whale:
            profile["premium_memory_priority"] = "critical"

        elif buyer_tier == "HIGH_VALUE":
            profile["premium_memory_priority"] = "high"

        else:
            profile["premium_memory_priority"] = "medium"

        # --------------------------------------------------
        # Callback candidates
        # --------------------------------------------------

        callback_candidates = []

        last_user_message = buyer_memory.get("last_user_message")
        last_offer_content_tag = buyer_memory.get("last_offer_content_tag")
        last_content_tag = buyer_memory.get("last_content_tag")
        last_bot_response = buyer_memory.get("last_bot_response")

        if last_user_message:
            callback_candidates.append(
                {
                    "type": "last_user_message",
                    "value": str(last_user_message)[:160],
                }
            )

        if last_offer_content_tag:
            callback_candidates.append(
                {
                    "type": "last_offer_content_tag",
                    "value": str(last_offer_content_tag),
                }
            )

        if last_content_tag:
            callback_candidates.append(
                {
                    "type": "last_content_tag",
                    "value": str(last_content_tag),
                }
            )

        if last_bot_response:
            callback_candidates.append(
                {
                    "type": "last_bot_response",
                    "value": str(last_bot_response)[:160],
                }
            )

        profile["emotional_callback_candidates"] = callback_candidates[:4]

        # --------------------------------------------------
        # Presence bias + reinforcement mode
        # --------------------------------------------------

        if whale_retention_mode == "dormant_whale_rewarm":
            profile["emotional_presence_bias"] = "familiar_rewarm_presence"
            profile["continuity_reinforcement_mode"] = "rewarm_familiarity"
            reasons.append("dormant_whale_memory_rewarm")

        elif whale_retention_mode == "reactivated_whale_recovery":
            profile["emotional_presence_bias"] = "premium_recovery_presence"
            profile["continuity_reinforcement_mode"] = "restore_premium_continuity"
            reasons.append("reactivated_whale_memory_recovery")

        elif is_whale:
            profile["emotional_presence_bias"] = "high_touch_premium_presence"
            profile["continuity_reinforcement_mode"] = "active_whale_continuity"
            reasons.append("active_whale_memory_continuity")

        else:
            profile["emotional_presence_bias"] = "warm_premium_presence"
            profile["continuity_reinforcement_mode"] = "premium_familiarity"
            reasons.append("high_value_memory_continuity")

        profile["gpt_instruction"] = self._build_gpt_instruction(profile)

        return profile

    def _build_gpt_instruction(self, profile: dict) -> str:
        return (
            "Premium relationship memory is active. "
            f"Emotional familiarity level: "
            f"{profile.get('emotional_familiarity_level')}. "
            f"Remembered dynamic style: "
            f"{profile.get('remembered_dynamic_style')}. "
            f"Continuity strength: "
            f"{profile.get('intimacy_continuity_strength')}. "
            f"Attachment mode: "
            f"{profile.get('relationship_attachment_mode')}. "
            f"Presence bias: "
            f"{profile.get('emotional_presence_bias')}. "
            f"Reinforcement mode: "
            f"{profile.get('continuity_reinforcement_mode')}. "
            "Use subtle familiarity, emotional continuity, and callbacks "
            "when appropriate. Do not over-explain memory. Do not sound "
            "robotic. Make the user feel personally remembered without "
            "forcing references unnaturally."
        )