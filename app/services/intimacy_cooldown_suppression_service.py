from datetime import datetime, timezone


class IntimacyCooldownSuppressionService:
    """
    3D.10.15F — Intimacy Cooldown Suppression

    Prevents nonstop escalation and emotional overexposure.
    """

    COOLDOWN_MINUTES = 45

    def build_instruction(
        self,
        user_memory: dict,
    ) -> str:

        intimacy = (
            user_memory.get("intimacy_context", {})
            or {}
        )

        last_escalation_at = intimacy.get(
            "last_escalation_at"
        )

        if not last_escalation_at:
            return """
--- INTIMACY COOLDOWN SUPPRESSION (3D.10.15F) ---

No active intimacy cooldown.
Normal escalation pacing allowed.
"""

        try:
            last_dt = datetime.fromisoformat(
                last_escalation_at
            )

            now = datetime.now(timezone.utc)

            minutes_since = (
                now - last_dt
            ).total_seconds() / 60

        except Exception:
            return """
--- INTIMACY COOLDOWN SUPPRESSION (3D.10.15F) ---

Cooldown parsing failed.
Use normal pacing.
"""

        # --------------------------------------------------
        # ACTIVE COOLDOWN
        # --------------------------------------------------

        if minutes_since < self.COOLDOWN_MINUTES:

            remaining = int(
                self.COOLDOWN_MINUTES - minutes_since
            )

            return f"""
--- INTIMACY COOLDOWN SUPPRESSION (3D.10.15F) ---

ACTIVE COOLDOWN DETECTED:
- Last escalation was recent.
- Remaining cooldown: {remaining} minutes.

SUPPRESSION RULES:
- Reduce seductive intensity.
- Avoid immersive escalation.
- Avoid emotionally overwhelming intimacy.
- Avoid rapid tension stacking.
- Shift toward playful warmth.
- Create anticipation instead of payoff.
- Slow pacing naturally.
- Maintain flirtation without deep escalation.

IMPORTANT:
- Do not mention cooldowns.
- Do not sound robotic.
- Maintain natural persona behavior.
"""

        # --------------------------------------------------
        # COOLDOWN EXPIRED
        # --------------------------------------------------

        return """
--- INTIMACY COOLDOWN SUPPRESSION (3D.10.15F) ---

Cooldown expired.

Escalation pacing may resume naturally.
"""