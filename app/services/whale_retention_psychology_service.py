class WhaleRetentionPsychologyService:
    """
    3D.20.1

    Whale-aware premium relationship refinement layer.

    PURPOSE:
    Whales and high-value users should feel emotionally prioritized,
    exclusive, immersive, relationship-driven, and remembered — not
    constantly sold to.

    This service does NOT send messages.
    It only builds behavior/refinement context for DecisionEngine,
    GPT/Grok, and dashboard debug visibility.
    """

    def build_retention_profile(
        self,
        buyer_memory: dict | None = None,
        conversation_state: dict | None = None,
        runtime_state: dict | None = None,
    ) -> dict:
        buyer_memory = buyer_memory or {}
        conversation_state = conversation_state or {}
        runtime_state = runtime_state or {}

        buyer_tier = str(
            buyer_memory.get("buyer_tier")
            or runtime_state.get("buyer_tier")
            or "NON_BUYER"
        ).upper()

        user_value_tier = str(
            buyer_memory.get("user_value_tier")
            or runtime_state.get("user_value_tier")
            or ""
        ).upper()

        is_whale = bool(
            buyer_memory.get("is_whale")
            or runtime_state.get("is_whale")
            or buyer_tier == "WHALE"
            or user_value_tier == "WHALE"
        )

        is_high_value = bool(
            is_whale
            or buyer_tier in ["HIGH_VALUE", "WHALE"]
            or user_value_tier in ["HIGH_VALUE", "WHALE"]
            or buyer_memory.get("is_top_spender")
        )

        total_spend = float(buyer_memory.get("total_spend") or 0)
        purchase_count = int(buyer_memory.get("purchase_count") or 0)
        total_tip_amount = float(buyer_memory.get("total_tip_amount") or 0)

        recent_purchase_active = bool(
            buyer_memory.get("recent_purchase_active")
            or runtime_state.get("recent_purchase_active")
        )

        recent_tip_active = bool(
            buyer_memory.get("recent_tip_active")
            or runtime_state.get("recent_tip_active")
        )

        premium_freshness_state = (
            runtime_state.get("premium_freshness_state")
            or buyer_memory.get("premium_freshness_state")
            or "unknown"
        )

        dormant_whale = bool(
            runtime_state.get("dormant_whale")
            or buyer_memory.get("dormant_whale")
        )

        whale_reactivation_mode = bool(
            runtime_state.get("whale_reactivation_mode")
            or buyer_memory.get("whale_reactivation_mode")
        )

        sexual_engagement_only = bool(
            conversation_state.get("sexual_engagement_only")
            or buyer_memory.get("sexual_engagement_only")
        )

        monetization_intent = bool(
            conversation_state.get("monetization_intent")
            or buyer_memory.get("monetization_intent")
        )

        reasons = []

        profile = {
            "success": True,
            "whale_retention_mode": "standard",
            "premium_attention_priority": "normal",
            "reduce_sales_pressure": False,
            "emotional_priority_level": "normal",
            "relationship_first_response": False,
            "premium_pacing_preference": "normal",
            "sales_pressure_directive": "standard",
            "gpt_instruction": "",
            "reasons": reasons,
        }

        if not is_high_value:
            reasons.append("not_high_value_or_whale")
            profile["gpt_instruction"] = (
                "Use normal relationship-aware pacing."
            )
            return profile

        if is_whale:
            profile.update(
                {
                    "whale_retention_mode": "active_whale_retention",
                    "premium_attention_priority": "critical",
                    "reduce_sales_pressure": True,
                    "emotional_priority_level": "very_high",
                    "relationship_first_response": True,
                    "premium_pacing_preference": "slow_premium",
                    "sales_pressure_directive": "relationship_first_low_pressure",
                }
            )
            reasons.append("whale_detected")
        else:
            profile.update(
                {
                    "whale_retention_mode": "high_value_retention",
                    "premium_attention_priority": "high",
                    "reduce_sales_pressure": True,
                    "emotional_priority_level": "high",
                    "relationship_first_response": True,
                    "premium_pacing_preference": "careful_premium",
                    "sales_pressure_directive": "careful_low_pressure",
                }
            )
            reasons.append("high_value_detected")

        if total_spend >= 1000:
            reasons.append("total_spend_whale_threshold")

        if purchase_count >= 5:
            reasons.append("repeat_purchase_history")

        if total_tip_amount >= 100:
            reasons.append("tip_investment_detected")

        if recent_purchase_active or recent_tip_active:
            profile["emotional_priority_level"] = "very_high"
            profile["premium_attention_priority"] = "critical"
            reasons.append("recent_money_event")

        if sexual_engagement_only and not monetization_intent:
            profile["reduce_sales_pressure"] = True
            profile["relationship_first_response"] = True
            profile["sales_pressure_directive"] = (
                "continue_intimacy_without_cta"
            )
            reasons.append("explicit_without_buying_intent")

        if dormant_whale:
            profile["whale_retention_mode"] = "dormant_whale_rewarm"
            profile["premium_pacing_preference"] = "emotional_rewarm"
            profile["sales_pressure_directive"] = "no_immediate_cta"
            profile["reduce_sales_pressure"] = True
            reasons.append("dormant_whale_rewarm")

        if whale_reactivation_mode:
            profile["whale_retention_mode"] = "reactivated_whale_recovery"
            profile["premium_pacing_preference"] = "premium_recovery"
            reasons.append("whale_reactivation_mode")

        profile["premium_freshness_state"] = premium_freshness_state
        profile["gpt_instruction"] = self._build_gpt_instruction(profile)

        return profile

    def _build_gpt_instruction(self, profile: dict) -> str:
        return (
            "Whale retention psychology is active. "
            f"Mode: {profile.get('whale_retention_mode')}. "
            f"Premium attention priority: "
            f"{profile.get('premium_attention_priority')}. "
            f"Emotional priority: "
            f"{profile.get('emotional_priority_level')}. "
            f"Pacing: {profile.get('premium_pacing_preference')}. "
            f"Sales pressure directive: "
            f"{profile.get('sales_pressure_directive')}. "
            "Prioritize emotional presence, validation, exclusivity, "
            "and relationship continuity. Avoid generic teasing, "
            "spammy CTA pressure, or making the user feel processed."
        )