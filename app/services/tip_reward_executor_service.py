class TipRewardExecutorService:
    """
    3D.13.7 — Tip Reward Executor

    Builds structured reward payloads
    for monetization tip reactions.

    IMPORTANT:
    This does NOT send Fanvue messages yet.

    It only prepares outbound reward behavior.
    """

    def build_tip_reward_payload(
        self,
        execution_plan: dict,
        spend_profile: dict | None = None,
        monetization_event: dict | None = None,
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
        monetization_event = monetization_event or {}

        buyer_tier = spend_profile.get(
            "buyer_tier",
            "NON_BUYER",
        )

        tip_amount = monetization_event.get(
            "amount",
            0,
        )

        reward_level = self._resolve_reward_level(
            tip_amount=tip_amount,
            buyer_tier=buyer_tier,
        )

        emotional_tone = (
            self._resolve_emotional_tone(
                reward_level
            )
        )

        tease_level = self._resolve_tease_level(
            reward_level
        )

        return {
            "success": True,
            "blocked": False,
            "payload_type": "tip_reward",
            "fanvue_user_id": fanvue_user_id,
            "buyer_tier": buyer_tier,
            "tip_amount": tip_amount,
            "reward_level": reward_level,
            "emotional_tone": emotional_tone,
            "tease_level": tease_level,
            "requires_gpt_generation": True,
            "queue_for_delivery": True,
            "send_immediately": False,
        }

    def _resolve_reward_level(
        self,
        tip_amount: float,
        buyer_tier: str,
    ):
        if buyer_tier == "WHALE":
            return "vip_reward"

        if tip_amount >= 100:
            return "high_reward"

        if tip_amount >= 25:
            return "medium_reward"

        return "light_reward"

    def _resolve_emotional_tone(
        self,
        reward_level: str,
    ):
        if reward_level == "vip_reward":
            return "deeply_appreciative"

        if reward_level == "high_reward":
            return "playfully_excited"

        if reward_level == "medium_reward":
            return "warm_flirty"

        return "cute_appreciation"

    def _resolve_tease_level(
        self,
        reward_level: str,
    ):
        if reward_level == "vip_reward":
            return "premium_tease"

        if reward_level == "high_reward":
            return "high_tease"

        if reward_level == "medium_reward":
            return "moderate_tease"

        return "light_tease"

    def _blocked(
        self,
        reason: str,
    ):
        return {
            "success": False,
            "blocked": True,
            "reason": reason,
        }