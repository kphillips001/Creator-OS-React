class DecisionEngineContinuationInjectionService:
    """
    3D.17.6

    Converts refresh-hook continuation intelligence into
    DecisionEngine-ready runtime overrides.

    IMPORTANT:
    This service does NOT send messages.
    This service does NOT call Fanvue.
    This service only prepares runtime intelligence.
    """

    def build_injection(
        self,
        refresh_payload: dict | None,
    ) -> dict:
        if not refresh_payload:
            return self._safe_default("missing_refresh_payload")

        continuation_route = refresh_payload.get(
            "continuation_route"
        ) or {}

        retention_route = refresh_payload.get(
            "retention_route"
        ) or {}

        monetization_event = refresh_payload.get(
            "monetization_event"
        ) or {}

        event_type = monetization_event.get("event_type")
        buyer_tier = self._extract_buyer_tier(refresh_payload)

        response_strategy = self._determine_response_strategy(
            event_type=event_type,
            continuation_route=continuation_route,
            retention_route=retention_route,
            buyer_tier=buyer_tier,
        )

        escalation_level = self._determine_escalation_level(
            event_type=event_type,
            buyer_tier=buyer_tier,
            continuation_route=continuation_route,
        )

        return {
            "success": True,
            "injection_enabled": True,
            "source": "realtime_monetization_refresh",

            "event_type": event_type,
            "buyer_tier": buyer_tier,

            "response_strategy": response_strategy,
            "escalation_level": escalation_level,

            "retention_mode": retention_route.get(
                "retention_mode",
                self._default_retention_mode(buyer_tier),
            ),

            "ppv_energy": self._determine_ppv_energy(
                buyer_tier=buyer_tier,
                continuation_route=continuation_route,
            ),

            "emotional_continuation": self._determine_emotional_continuation(
                event_type=event_type,
                buyer_tier=buyer_tier,
            ),

            "followup_behavior": continuation_route.get(
                "followup_behavior",
                self._default_followup_behavior(event_type),
            ),

            "premium_routing": self._determine_premium_routing(
                buyer_tier=buyer_tier,
                continuation_route=continuation_route,
            ),

            "cooldown_sensitivity": self._determine_cooldown_sensitivity(
                buyer_tier=buyer_tier,
                continuation_route=continuation_route,
            ),

            "suppression_handling": self._determine_suppression_handling(
                buyer_tier=buyer_tier,
                continuation_route=continuation_route,
            ),

            "automation_note": (
                "DecisionEngine injection only. "
                "No outbound automation enabled here."
            ),

            "reasons": self._build_reasons(
                event_type=event_type,
                buyer_tier=buyer_tier,
                continuation_route=continuation_route,
                retention_route=retention_route,
            ),
        }

    def _extract_buyer_tier(self, refresh_payload: dict) -> str:
        buyer_state = refresh_payload.get("buyer_state") or {}
        buyer_memory = refresh_payload.get("buyer_memory") or {}

        return (
            buyer_state.get("buyer_tier")
            or buyer_memory.get("buyer_tier")
            or "UNKNOWN"
        )

    def _determine_response_strategy(
        self,
        event_type: str | None,
        continuation_route: dict,
        retention_route: dict,
        buyer_tier: str,
    ) -> str:
        if buyer_tier in ("WHALE", "HIGH_VALUE"):
            return "premium_retention"

        route = continuation_route.get("route")

        if route:
            return route

        if event_type in ("purchase_received", "purchase_created"):
            return "post_purchase_soft_continue"

        if event_type in ("unlock_confirmation", "unlock_confirmed"):
            return "unlock_continuation"

        if event_type in ("tip_received", "tip_created"):
            return "tip_reward_continue"

        if event_type == "subscription_created":
            return "subscriber_welcome_continue"

        if retention_route.get("route"):
            return retention_route.get("route")

        return "relationship_continue"

    def _determine_escalation_level(
        self,
        event_type: str | None,
        buyer_tier: str,
        continuation_route: dict,
    ) -> str:
        override = continuation_route.get("escalation_level")

        if override:
            return override

        if buyer_tier == "WHALE":
            return "premium_controlled"

        if buyer_tier == "HIGH_VALUE":
            return "high_controlled"

        if event_type in ("purchase_received", "purchase_created"):
            return "medium_high"

        if event_type in ("tip_received", "tip_created"):
            return "warm_high"

        if event_type == "subscription_created":
            return "warm"

        return "controlled"

    def _default_retention_mode(self, buyer_tier: str) -> str:
        if buyer_tier == "WHALE":
            return "whale_retention"

        if buyer_tier == "HIGH_VALUE":
            return "high_value_retention"

        if buyer_tier == "ACTIVE_BUYER":
            return "active_buyer_retention"

        return "standard_retention"

    def _determine_ppv_energy(
        self,
        buyer_tier: str,
        continuation_route: dict,
    ) -> str:
        override = continuation_route.get("ppv_energy")

        if override:
            return override

        if buyer_tier in ("WHALE", "HIGH_VALUE"):
            return "premium_only_low_pressure"

        if buyer_tier == "ACTIVE_BUYER":
            return "selective_premium"

        return "soft_tease"

    def _determine_emotional_continuation(
        self,
        event_type: str | None,
        buyer_tier: str,
    ) -> str:
        if buyer_tier == "WHALE":
            return "exclusive_emotional_continuity"

        if event_type in ("purchase_received", "purchase_created"):
            return "appreciative_flirty_continuation"

        if event_type in ("tip_received", "tip_created"):
            return "warm_reward_continuation"

        if event_type == "subscription_created":
            return "welcome_relationship_continuation"

        return "soft_relationship_continuation"

    def _default_followup_behavior(
        self,
        event_type: str | None,
    ) -> str:
        if event_type in ("purchase_received", "purchase_created"):
            return "thank_you_then_soft_continue"

        if event_type in ("unlock_confirmation", "unlock_confirmed"):
            return "acknowledge_unlock_then_continue"

        if event_type in ("tip_received", "tip_created"):
            return "thank_tip_then_reward_energy"

        if event_type == "subscription_created":
            return "welcome_then_warmup"

        return "continue_without_send"

    def _determine_premium_routing(
        self,
        buyer_tier: str,
        continuation_route: dict,
    ) -> str:
        override = continuation_route.get("premium_routing")

        if override:
            return override

        if buyer_tier == "WHALE":
            return "premium_retention_only"

        if buyer_tier == "HIGH_VALUE":
            return "premium_priority"

        if buyer_tier == "ACTIVE_BUYER":
            return "premium_eligible"

        return "not_forced"

    def _determine_cooldown_sensitivity(
        self,
        buyer_tier: str,
        continuation_route: dict,
    ) -> str:
        override = continuation_route.get("cooldown_sensitivity")

        if override:
            return override

        if buyer_tier in ("WHALE", "HIGH_VALUE"):
            return "high"

        if buyer_tier == "ACTIVE_BUYER":
            return "medium"

        return "standard"

    def _determine_suppression_handling(
        self,
        buyer_tier: str,
        continuation_route: dict,
    ) -> str:
        override = continuation_route.get("suppression_handling")

        if override:
            return override

        if buyer_tier in ("WHALE", "HIGH_VALUE", "ACTIVE_BUYER"):
            return "suppress_mass_ppv_and_preserve_premium_flow"

        return "standard_suppression"

    def _build_reasons(
        self,
        event_type: str | None,
        buyer_tier: str,
        continuation_route: dict,
        retention_route: dict,
    ) -> list[str]:
        reasons = [
            "realtime_monetization_event_detected",
            f"event_type:{event_type or 'unknown'}",
            f"buyer_tier:{buyer_tier}",
        ]

        if continuation_route:
            reasons.append("continuation_route_available")

        if retention_route:
            reasons.append("retention_route_available")

        return reasons

    def _safe_default(self, reason: str) -> dict:
        return {
            "success": False,
            "injection_enabled": False,
            "source": "realtime_monetization_refresh",
            "response_strategy": "safe_default",
            "escalation_level": "none",
            "retention_mode": "none",
            "ppv_energy": "none",
            "emotional_continuation": "none",
            "followup_behavior": "none",
            "premium_routing": "none",
            "cooldown_sensitivity": "standard",
            "suppression_handling": "standard",
            "reason": reason,
            "automation_note": (
                "No outbound automation performed."
            ),
        }