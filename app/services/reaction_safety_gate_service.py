from datetime import datetime, timedelta


class ReactionSafetyGateService:
    """
    3D.13.2 — Reaction Safety Gate

    Prevents unsafe automated monetization reactions.

    IMPORTANT:
    This service does NOT execute reactions.

    It only determines whether execution is allowed.
    """

    DEFAULT_REACTION_COOLDOWN_MINUTES = 10

    def validate_execution(
        self,
        execution_plan: dict,
        user_memory: dict | None = None,
        system_config: dict | None = None,
    ):
        if not execution_plan:
            return self._blocked("missing_execution_plan")

        if execution_plan.get("blocked") is True:
            return self._blocked("execution_plan_already_blocked")

        fanvue_user_id = execution_plan.get("fanvue_user_id")

        if not fanvue_user_id:
            return self._blocked("missing_fanvue_user_id")

        if system_config:
            automation_enabled = system_config.get(
                "ENABLE_POST_PURCHASE_AUTOMATION",
                True,
            )

            if not automation_enabled:
                return self._blocked(
                    "post_purchase_automation_disabled"
                )

        user_memory = user_memory or {}

        buyer_session_active = user_memory.get(
            "buyer_session_active",
            False,
        )

        if buyer_session_active:
            return self._blocked(
                "buyer_session_active"
            )

        cooldown_until = user_memory.get(
            "reaction_cooldown_until"
        )

        if self._is_cooldown_active(cooldown_until):
            return self._blocked(
                "reaction_cooldown_active",
                {
                    "cooldown_until": cooldown_until,
                },
            )

        recent_reaction_sent = user_memory.get(
            "recent_reaction_sent",
            False,
        )

        if recent_reaction_sent:
            return self._blocked(
                "recent_reaction_already_sent"
            )

        return {
            "success": True,
            "blocked": False,
            "allowed": True,
            "reason": None,
            "fanvue_user_id": fanvue_user_id,
            "validated_at": datetime.utcnow().isoformat(),
        }

    def build_cooldown_expiration(
        self,
        minutes: int | None = None,
    ):
        minutes = (
            minutes
            or self.DEFAULT_REACTION_COOLDOWN_MINUTES
        )

        return (
            datetime.utcnow()
            + timedelta(minutes=minutes)
        ).isoformat()

    def _is_cooldown_active(
        self,
        cooldown_until,
    ):
        if not cooldown_until:
            return False

        try:
            cooldown_dt = datetime.fromisoformat(
                cooldown_until
            )

            return cooldown_dt > datetime.utcnow()

        except Exception:
            return False

    def _blocked(
        self,
        reason: str,
        extra: dict | None = None,
    ):
        result = {
            "success": False,
            "blocked": True,
            "allowed": False,
            "reason": reason,
        }

        if extra:
            result.update(extra)

        return result