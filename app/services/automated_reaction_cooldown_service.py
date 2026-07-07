from datetime import datetime, timedelta


class AutomatedReactionCooldownService:
    """
    3D.18.5 — Cooldown + Recent Outbound Protection

    Prevents automated monetization reactions from sending
    too frequently or overlapping with recent outbound activity.
    """

    DEFAULT_COOLDOWN_MINUTES = 10
    RECENT_OUTBOUND_MINUTES = 5

    def validate_cooldown(
        self,
        reaction_type: str,
        user_memory: dict | None = None,
        outbound_history: list[dict] | None = None,
        now: datetime | None = None,
    ):
        if not reaction_type:
            return self._blocked(
                "missing_reaction_type"
            )

        user_memory = user_memory or {}
        outbound_history = outbound_history or []
        now = now or datetime.utcnow()

        cooldown_check = (
            self._validate_reaction_cooldown(
                reaction_type=reaction_type,
                user_memory=user_memory,
                now=now,
            )
        )

        if cooldown_check.get("blocked"):
            return cooldown_check

        outbound_check = (
            self._validate_recent_outbound_activity(
                outbound_history=outbound_history,
                now=now,
            )
        )

        if outbound_check.get("blocked"):
            return outbound_check

        return {
            "success": True,
            "blocked": False,
            "cooldown_safe": True,
            "reaction_type": reaction_type,
            "checked_at": now.isoformat(),
        }

    def _validate_reaction_cooldown(
        self,
        reaction_type: str,
        user_memory: dict,
        now: datetime,
    ):
        cooldown_key = (
            f"last_{reaction_type}_at"
        )

        last_reaction_at = user_memory.get(
            cooldown_key
        )

        if not last_reaction_at:
            return {
                "success": True,
                "blocked": False,
            }

        try:
            parsed = datetime.fromisoformat(
                last_reaction_at
            )
        except Exception:
            return self._blocked(
                "invalid_cooldown_timestamp",
                {
                    "reaction_type": reaction_type,
                    "value": last_reaction_at,
                },
            )

        delta = now - parsed

        if delta < timedelta(
            minutes=self.DEFAULT_COOLDOWN_MINUTES
        ):
            return self._blocked(
                "reaction_cooldown_active",
                {
                    "reaction_type": reaction_type,
                    "minutes_remaining": round(
                        (
                            self.DEFAULT_COOLDOWN_MINUTES
                            - delta.total_seconds()
                            / 60
                        ),
                        2,
                    ),
                },
            )

        return {
            "success": True,
            "blocked": False,
        }

    def _validate_recent_outbound_activity(
        self,
        outbound_history: list[dict],
        now: datetime,
    ):
        for outbound in outbound_history:
            outbound_timestamp = outbound.get(
                "sent_at"
            )

            if not outbound_timestamp:
                continue

            try:
                parsed = datetime.fromisoformat(
                    outbound_timestamp
                )
            except Exception:
                continue

            delta = now - parsed

            if delta < timedelta(
                minutes=self.RECENT_OUTBOUND_MINUTES
            ):
                return self._blocked(
                    "recent_outbound_activity",
                    {
                        "minutes_since_outbound": round(
                            delta.total_seconds()
                            / 60,
                            2,
                        ),
                    },
                )

        return {
            "success": True,
            "blocked": False,
        }

    def _blocked(
        self,
        reason: str,
        extra: dict | None = None,
    ):
        result = {
            "success": False,
            "blocked": True,
            "cooldown_safe": False,
            "reason": reason,
        }

        if extra:
            result.update(extra)

        return result