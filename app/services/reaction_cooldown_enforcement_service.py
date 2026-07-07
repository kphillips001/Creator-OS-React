from datetime import datetime, timedelta


class ReactionCooldownEnforcementService:
    """
    3D.13.4 — Cooldown Enforcement

    Determines whether post-purchase reactions should:

    - execute immediately
    - delay execution
    - suppress execution temporarily

    based on monetization pacing rules.
    """

    DEFAULT_DELAY_MINUTES = 15

    WHALE_DELAY_MINUTES = 45

    PREMIUM_DELAY_MINUTES = 30

    DECOMPRESSION_DELAY_MINUTES = 60

    def evaluate_cooldown(
        self,
        execution_plan: dict,
        spend_profile: dict | None = None,
    ):
        if not execution_plan:
            return self._blocked(
                "missing_execution_plan"
            )

        spend_profile = spend_profile or {}

        decision_type = execution_plan.get(
            "decision_type"
        )

        buyer_tier = spend_profile.get(
            "buyer_tier",
            "NON_BUYER",
        )

        pacing_profile = execution_plan.get(
            "pacing_profile",
            "normal",
        )

        should_slow_down = execution_plan.get(
            "should_slow_down",
            False,
        )

        delay_minutes = self.DEFAULT_DELAY_MINUTES

        cooldown_reason = "standard_delay"

        if buyer_tier == "WHALE":
            delay_minutes = self.WHALE_DELAY_MINUTES
            cooldown_reason = "whale_decompression"

        elif pacing_profile == "premium":
            delay_minutes = self.PREMIUM_DELAY_MINUTES
            cooldown_reason = "premium_spacing"

        elif pacing_profile == "decompression":
            delay_minutes = (
                self.DECOMPRESSION_DELAY_MINUTES
            )
            cooldown_reason = (
                "post_purchase_decompression"
            )

        if should_slow_down:
            delay_minutes += 20

        execute_at = (
            datetime.utcnow()
            + timedelta(minutes=delay_minutes)
        ).isoformat()

        return {
            "success": True,
            "blocked": False,
            "delay_required": True,
            "delay_minutes": delay_minutes,
            "cooldown_reason": cooldown_reason,
            "execute_at": execute_at,
            "decision_type": decision_type,
            "buyer_tier": buyer_tier,
            "pacing_profile": pacing_profile,
        }

    def _blocked(
        self,
        reason: str,
    ):
        return {
            "success": False,
            "blocked": True,
            "delay_required": False,
            "reason": reason,
        }