from datetime import datetime, timedelta


class PremiumFollowupQueueService:
    """
    3D.13.9 — Premium Followup Queue

    Builds queued premium continuation payloads.

    IMPORTANT:
    This does NOT execute scheduling yet.

    It only prepares queue-ready followup data.
    """

    DEFAULT_DELAY_MINUTES = 45

    WHALE_DELAY_MINUTES = 90

    PREMIUM_DELAY_MINUTES = 60

    def build_followup_queue_payload(
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

        spend_profile = spend_profile or {}

        buyer_tier = spend_profile.get(
            "buyer_tier",
            "LOW_SPENDER",
        )

        pacing_profile = execution_plan.get(
            "pacing_profile",
            "normal",
        )

        followup_type = (
            self._resolve_followup_type(
                buyer_tier,
                pacing_profile,
            )
        )

        delay_minutes = self._resolve_delay(
            buyer_tier,
            pacing_profile,
        )

        emotional_goal = (
            self._resolve_emotional_goal(
                followup_type
            )
        )

        execute_at = (
            datetime.utcnow()
            + timedelta(minutes=delay_minutes)
        ).isoformat()

        return {
            "success": True,
            "blocked": False,
            "payload_type": "premium_followup_queue",
            "fanvue_user_id": fanvue_user_id,
            "buyer_tier": buyer_tier,
            "pacing_profile": pacing_profile,
            "followup_type": followup_type,
            "delay_minutes": delay_minutes,
            "execute_at": execute_at,
            "emotional_goal": emotional_goal,
            "requires_gpt_generation": True,
            "queue_only": True,
            "send_immediately": False,
        }

    def _resolve_followup_type(
        self,
        buyer_tier: str,
        pacing_profile: str,
    ):
        if buyer_tier == "WHALE":
            return "vip_continuation"

        if pacing_profile == "decompression":
            return "soft_reengagement"

        if buyer_tier in {
            "HIGH_VALUE",
            "ACTIVE_BUYER",
        }:
            return "premium_reengagement"

        return "light_followup"

    def _resolve_delay(
        self,
        buyer_tier: str,
        pacing_profile: str,
    ):
        if buyer_tier == "WHALE":
            return self.WHALE_DELAY_MINUTES

        if pacing_profile == "premium":
            return self.PREMIUM_DELAY_MINUTES

        return self.DEFAULT_DELAY_MINUTES

    def _resolve_emotional_goal(
        self,
        followup_type: str,
    ):
        if followup_type == "vip_continuation":
            return "relationship_retention"

        if followup_type == "soft_reengagement":
            return "emotional_rewarm"

        if followup_type == "premium_reengagement":
            return "premium_reactivation"

        return "light_continuation"

    def _blocked(
        self,
        reason: str,
    ):
        return {
            "success": False,
            "blocked": True,
            "reason": reason,
        }