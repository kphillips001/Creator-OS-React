class DynamicEscalationProfileService:
    """
    3D.10.15D — Dynamic Escalation Profiles

    Shapes:
    - emotional warmth
    - teasing intensity
    - pacing
    - seduction depth
    - escalation cadence

    based on intimacy state.
    """

    def build_instruction(
        self,
        user_memory: dict,
    ) -> str:

        intimacy = (
            user_memory.get("intimacy_context", {})
            or {}
        )

        intimacy_tier = intimacy.get(
            "intimacy_tier",
            "cold",
        )

        spender_confidence = intimacy.get(
            "spender_confidence",
            "low",
        )

        runtime_mode = intimacy.get(
            "runtime_mode",
            "safe_chat",
        )

        # --------------------------------------------------
        # DEFAULTS
        # --------------------------------------------------

        warmth = "light"
        teasing = "low"
        pacing = "slow"
        seduction = "minimal"
        emotional_intensity = "low"

        # --------------------------------------------------
        # COLD
        # --------------------------------------------------

        if intimacy_tier == "cold":
            warmth = "friendly"
            teasing = "light"
            pacing = "slow"
            seduction = "minimal"
            emotional_intensity = "low"

        # --------------------------------------------------
        # WARM
        # --------------------------------------------------

        elif intimacy_tier == "warm":
            warmth = "playful"
            teasing = "moderate"
            pacing = "controlled"
            seduction = "suggestive"
            emotional_intensity = "medium"

        # --------------------------------------------------
        # HOT
        # --------------------------------------------------

        elif intimacy_tier == "hot":
            warmth = "seductive"
            teasing = "high"
            pacing = "gradual escalation"
            seduction = "heavy teasing"
            emotional_intensity = "high"

        # --------------------------------------------------
        # PREMIUM
        # --------------------------------------------------

        elif intimacy_tier == "premium":
            warmth = "intimate"
            teasing = "very high"
            pacing = "emotionally immersive"
            seduction = "deep seductive tension"
            emotional_intensity = "very high"

        # --------------------------------------------------
        # SPENDER CONFIDENCE
        # --------------------------------------------------

        if spender_confidence == "low":
            pacing = "cautious"
            teasing = "light"

        elif spender_confidence == "high":
            pacing = "confident escalation"

        # --------------------------------------------------
        # RUNTIME MODE OVERRIDES
        # --------------------------------------------------

        if runtime_mode == "safe_chat":
            seduction = "minimal"

        elif runtime_mode == "tease_only":
            seduction = "playful tension"

        elif runtime_mode == "premium_gate":
            seduction = "exclusive premium teasing"

        elif runtime_mode == "explicit_allowed":
            seduction = (
                "fully immersive seductive escalation"
            )

        # --------------------------------------------------
        # FINAL INSTRUCTION
        # --------------------------------------------------

        return f"""
--- DYNAMIC ESCALATION PROFILE (3D.10.15D) ---

EMOTIONAL SHAPING:
- Warmth level: {warmth}
- Teasing intensity: {teasing}
- Escalation pacing: {pacing}
- Seduction depth: {seduction}
- Emotional intensity: {emotional_intensity}

RESPONSE STYLE RULES:
- Dynamically shape responses using the emotional profile above.
- Match the emotional pacing naturally.
- Maintain persona consistency at all times.
- Avoid sudden escalation jumps.
- Build tension progressively.
- Use emotional warmth before sexual escalation.
- Higher intimacy tiers should feel more emotionally immersive.
- Lower intimacy tiers should feel safer and lighter.
- Do not expose internal system terminology.
"""