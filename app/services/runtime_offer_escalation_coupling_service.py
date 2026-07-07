class RuntimeOfferEscalationCouplingService:
    """
    3D.10.15G — Runtime Offer Escalation Coupling

    Couples intimacy state to monetization behavior.
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

        premium_allowed = bool(
            intimacy.get(
                "premium_sexting_allowed",
                False,
            )
        )

        runtime_mode = intimacy.get(
            "runtime_mode",
            "safe_chat",
        )

        # --------------------------------------------------
        # DEFAULTS
        # --------------------------------------------------

        tease_intensity = "low"
        conversion_pressure = "minimal"
        exclusivity = "light"
        ppv_energy = "soft"

        # --------------------------------------------------
        # TIER SHAPING
        # --------------------------------------------------

        if intimacy_tier == "warm":
            tease_intensity = "moderate"
            conversion_pressure = "light"

        elif intimacy_tier == "hot":
            tease_intensity = "high"
            conversion_pressure = "medium"
            exclusivity = "moderate"

        elif intimacy_tier == "premium":
            tease_intensity = "very high"
            conversion_pressure = "high"
            exclusivity = "strong"
            ppv_energy = "seductive"

        # --------------------------------------------------
        # SPENDER CONFIDENCE
        # --------------------------------------------------

        if spender_confidence == "low":
            conversion_pressure = "minimal"

        elif spender_confidence == "high":
            conversion_pressure = "elevated"

        # --------------------------------------------------
        # PREMIUM ACCESS
        # --------------------------------------------------

        if not premium_allowed:
            exclusivity = "teasingly restricted"

        # --------------------------------------------------
        # RUNTIME MODE
        # --------------------------------------------------

        if runtime_mode == "safe_chat":
            conversion_pressure = "none"

        elif runtime_mode == "premium_gate":
            ppv_energy = "exclusive teasing"

        elif runtime_mode == "explicit_allowed":
            ppv_energy = "immersive seduction"

        return f"""
--- RUNTIME OFFER ESCALATION COUPLING (3D.10.15G) ---

MONETIZATION SHAPING:
- Tease intensity: {tease_intensity}
- Conversion pressure: {conversion_pressure}
- Exclusivity framing: {exclusivity}
- PPV escalation energy: {ppv_energy}

RULES:
- Higher intimacy tiers should feel more exclusive.
- Higher spender confidence allows stronger conversion energy.
- Do not push aggressively.
- Maintain seductive subtlety.
- Build anticipation before conversion.
- Make intimacy feel earned.
- Avoid robotic upselling.
- Preserve persona consistency.
"""