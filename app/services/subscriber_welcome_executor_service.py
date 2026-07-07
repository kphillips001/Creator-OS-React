class SubscriberWelcomeExecutorService:
    """
    3D.13.8 — Subscriber Welcome Executor

    Builds structured onboarding payloads
    for new subscriber reactions.

    IMPORTANT:
    This service does NOT send Fanvue messages yet.

    It only prepares outbound welcome behavior.
    """

    def build_welcome_payload(
        self,
        execution_plan: dict,
        spend_profile: dict | None = None,
        subscription_event: dict | None = None,
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

        spend_profile = spend_profile or {}
        subscription_event = (
            subscription_event or {}
        )

        buyer_tier = spend_profile.get(
            "buyer_tier",
            "NEW_SUBSCRIBER",
        )

        is_returning = subscription_event.get(
            "is_returning_subscriber",
            False,
        )

        welcome_style = (
            self._resolve_welcome_style(
                buyer_tier=buyer_tier,
                is_returning=is_returning,
            )
        )

        emotional_tone = (
            self._resolve_emotional_tone(
                welcome_style
            )
        )

        onboarding_type = (
            self._resolve_onboarding_type(
                buyer_tier
            )
        )

        return {
            "success": True,
            "blocked": False,
            "payload_type": "subscriber_welcome",
            "fanvue_user_id": fanvue_user_id,
            "buyer_tier": buyer_tier,
            "is_returning_subscriber": (
                is_returning
            ),
            "welcome_style": welcome_style,
            "emotional_tone": emotional_tone,
            "onboarding_type": onboarding_type,
            "requires_gpt_generation": True,
            "queue_for_delivery": True,
            "send_immediately": False,
        }

    def _resolve_welcome_style(
        self,
        buyer_tier: str,
        is_returning: bool,
    ):
        if is_returning:
            return "warm_reunion"

        if buyer_tier == "WHALE":
            return "vip_welcome"

        if buyer_tier == "HIGH_VALUE":
            return "premium_attention"

        return "playful_onboarding"

    def _resolve_emotional_tone(
        self,
        welcome_style: str,
    ):
        if welcome_style == "warm_reunion":
            return "emotionally_warm"

        if welcome_style == "vip_welcome":
            return "luxury_affection"

        if welcome_style == "premium_attention":
            return "personal_attention"

        return "cute_flirty"

    def _resolve_onboarding_type(
        self,
        buyer_tier: str,
    ):
        if buyer_tier == "WHALE":
            return "vip_path"

        if buyer_tier in {
            "HIGH_VALUE",
            "ACTIVE_BUYER",
        }:
            return "premium_path"

        return "standard_path"

    def _blocked(
        self,
        reason: str,
    ):
        return {
            "success": False,
            "blocked": True,
            "reason": reason,
        }