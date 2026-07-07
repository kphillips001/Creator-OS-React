class AdvancedIntimacyGovernanceService:
    """
    3D.20.9

    Governs intimacy escalation across relationship,
    stability, dependency, burnout, and recovery systems.
    """

    def build_governance_profile(
        self,
        runtime_state: dict,
    ) -> dict:

        buyer_tier = str(
            runtime_state.get("buyer_tier") or "NON_BUYER"
        ).upper()

        runtime_mode = (
            runtime_state.get("runtime_mode")
            or "safe_chat"
        )

        stability_level = (
            runtime_state.get("stability_level")
            or "stable"
        )

        dependency_risk_level = (
            runtime_state.get("dependency_risk_level")
            or "low"
        )

        burnout_risk = (
            runtime_state.get("burnout_risk")
            or "low"
        )

        recovery_risk = (
            runtime_state.get("recovery_risk")
            or "low"
        )

        premium_intimacy_allowed = bool(
            runtime_mode == "premium_intimacy"
            and buyer_tier in [
                "ACTIVE_BUYER",
                "HIGH_VALUE",
                "WHALE",
            ]
        )

        intimacy_escalation_allowed = premium_intimacy_allowed

        governance_mode = "normal"

        if dependency_risk_level in ["high", "critical"]:
            intimacy_escalation_allowed = False
            governance_mode = "attachment_safe_grounding"

        elif burnout_risk in ["high", "critical"]:
            intimacy_escalation_allowed = False
            governance_mode = "burnout_safe_slowdown"

        elif recovery_risk in ["medium", "high"]:
            intimacy_escalation_allowed = False
            governance_mode = "recovery_first"

        elif stability_level in ["fragile", "active_stabilization"]:
            governance_mode = "stability_paced"

        escalation_ceiling = "standard"

        if not premium_intimacy_allowed:
            escalation_ceiling = "safe_chat_only"

        elif governance_mode in [
            "attachment_safe_grounding",
            "burnout_safe_slowdown",
            "recovery_first",
        ]:
            escalation_ceiling = "hold_current_level"

        elif governance_mode == "stability_paced":
            escalation_ceiling = "slow_increment"

        return {
            "advanced_intimacy_governance_active": True,
            "premium_intimacy_allowed": premium_intimacy_allowed,
            "intimacy_escalation_allowed": intimacy_escalation_allowed,
            "intimacy_governance_mode": governance_mode,
            "intimacy_escalation_ceiling": escalation_ceiling,
            "governance_reason": (
                "Advanced intimacy governance evaluated runtime safety layers."
            ),
            "gpt_instruction": (
                "Respect intimacy pacing, emotional safety, and relationship realism. "
                "Do not escalate intimacy when recovery, burnout, dependency, "
                "or stability systems require restraint."
            ),
        }