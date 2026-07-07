class ThankYouMessageExecutorService:
    """
    3D.13.6 — Thank-You Message Executor

    Builds structured outbound thank-you reactions.

    IMPORTANT:
    This service does NOT send Fanvue messages yet.

    It only prepares outbound execution payloads.
    """

    def build_thank_you_payload(
        self,
        execution_plan: dict,
        spend_profile: dict | None = None,
    ):
        if not execution_plan:
            return self._blocked(
                "missing_execution_plan"
            )

        fanvue_user_id = execution_plan.get(
            "fanvue_user_id"
        )

        if not fanvue_user_id:
            return self._blocked(
                "missing_fanvue_user_id"
            )

        decision_type = execution_plan.get(
            "decision_type"
        )

        spend_profile = spend_profile or {}

        buyer_tier = spend_profile.get(
            "buyer_tier",
            "NON_BUYER",
        )

        pacing_profile = execution_plan.get(
            "pacing_profile",
            "normal",
        )

        aggression_level = execution_plan.get(
            "aggression_level",
            "low",
        )

        message_style = self._resolve_message_style(
            buyer_tier=buyer_tier,
            pacing_profile=pacing_profile,
            aggression_level=aggression_level,
        )

        return {
            "success": True,
            "blocked": False,
            "payload_type": "thank_you_message",
            "fanvue_user_id": fanvue_user_id,
            "decision_type": decision_type,
            "buyer_tier": buyer_tier,
            "message_style": message_style,
            "pacing_profile": pacing_profile,
            "aggression_level": aggression_level,
            "requires_gpt_generation": True,
            "send_immediately": False,
            "queue_for_delivery": True,
            "suggested_emotional_tone": (
                self._resolve_emotional_tone(
                    pacing_profile
                )
            ),
        }

    def _resolve_message_style(
        self,
        buyer_tier: str,
        pacing_profile: str,
        aggression_level: str,
    ):
        if buyer_tier == "WHALE":
            return "warm_appreciative"

        if pacing_profile == "decompression":
            return "soft_affectionate"

        if aggression_level == "high":
            return "playful_excited"

        return "flirty_grateful"

    def _resolve_emotional_tone(
        self,
        pacing_profile: str,
    ):
        if pacing_profile == "decompression":
            return "emotionally_soft"

        if pacing_profile == "premium":
            return "luxury_attention"

        return "playful_appreciation"

    def _blocked(
        self,
        reason: str,
    ):
        return {
            "success": False,
            "blocked": True,
            "reason": reason,
        }