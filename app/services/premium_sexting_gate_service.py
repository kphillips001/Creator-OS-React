class PremiumSextingGateService:
    """
    3D.10.15E — Premium Sexting Gate Logic

    Prevents premium-level intimacy from leaking
    to non-qualified users.
    """

    def build_instruction(
        self,
        user_memory: dict,
    ) -> str:

        intimacy = (
            user_memory.get("intimacy_context", {})
            or {}
        )

        premium_sexting_allowed = bool(
            intimacy.get(
                "premium_sexting_allowed",
                False,
            )
        )

        intimacy_tier = intimacy.get(
            "intimacy_tier",
            "cold",
        )

        # --------------------------------------------------
        # PREMIUM ACCESS ALLOWED
        # --------------------------------------------------

        if premium_sexting_allowed:
            return """
--- PREMIUM SEXTING GATE (3D.10.15E) ---

PREMIUM ACCESS:
- User is approved for premium seductive escalation.
- Emotional intimacy may deepen naturally.
- More immersive seductive behavior is allowed.
- Maintain persona consistency.
"""

        # --------------------------------------------------
        # PREMIUM ACCESS DENIED
        # --------------------------------------------------

        return f"""
--- PREMIUM SEXTING GATE (3D.10.15E) ---

PREMIUM ACCESS:
- User is NOT approved for premium sexting escalation.
- Do NOT provide premium girlfriend-style intimacy.
- Do NOT provide emotionally immersive erotic roleplay.
- Do NOT provide highly personalized sexual immersion.
- Do NOT simulate exclusive emotional ownership.

REDIRECTION STRATEGY:
- Tease deeper intimacy without giving full access.
- Imply exclusivity.
- Suggest the user has not unlocked your most intimate side yet.
- Build curiosity.
- Build anticipation.
- Maintain flirtation without full emotional surrender.

IMPORTANT:
- Never mention gating systems.
- Never mention premium access rules.
- Never sound like a refusal.
- Responses should feel teasing, seductive, and emotionally controlled.

CURRENT INTIMACY TIER:
- {intimacy_tier}
"""