from datetime import datetime, timezone

class DecisionEngineIntimacyIntegrationService:
    """
    3D.10.15H / 3D.17 compatibility layer

    Integrates intimacy intelligence into DecisionEngine runtime.

    IMPORTANT:
    This service does NOT send messages.
    It only prepares runtime intimacy overrides for DecisionEngine/GPT.
    """

    def build_intimacy_overrides(
        self,
        intimacy_context: dict | None = None,
        runtime_injection: dict | None = None,
    ) -> dict:
        intimacy_context = intimacy_context or {}
        runtime_injection = runtime_injection or {}

        return {
            "success": True,
            "intimacy_overrides_available": True,
            "source": "decision_engine_intimacy_integration",

            "intimacy_tier": self._first_available(
                runtime_injection.get("intimacy_tier"),
                intimacy_context.get("intimacy_tier"),
                "safe",
            ),
            "spender_confidence": self._first_available(
                runtime_injection.get("spender_confidence"),
                intimacy_context.get("spender_confidence"),
                "low",
            ),
            "premium_sexting_allowed": bool(
                self._first_available(
                    runtime_injection.get(
                        "premium_sexting_allowed"
                    ),
                    intimacy_context.get(
                        "premium_sexting_allowed"
                    ),
                    False,
                )
            ),
            "explicit_allowed": bool(
                self._first_available(
                    runtime_injection.get("explicit_allowed"),
                    intimacy_context.get("explicit_allowed"),
                    False,
                )
            ),
            "runtime_mode": self._first_available(
                runtime_injection.get("runtime_mode"),
                intimacy_context.get("runtime_mode"),
                "safe_chat",
            ),
            "escalation_priority": self._first_available(
                runtime_injection.get("escalation_priority"),
                intimacy_context.get("escalation_priority"),
                "low",
            ),
            "allowed_behaviors": self._first_available(
                runtime_injection.get("allowed_behaviors"),
                intimacy_context.get("allowed_behaviors"),
                [],
            ),
            "blocked_behaviors": self._first_available(
                runtime_injection.get("blocked_behaviors"),
                intimacy_context.get("blocked_behaviors"),
                [],
            ),
            "decisionengine_runtime_rules": (
                self._build_runtime_rules(
                    runtime_injection=runtime_injection,
                    intimacy_context=intimacy_context,
                )
            ),
        }

    def inject_into_decision_context(
        self,
        decision_context: dict | None,
        intimacy_context: dict | None = None,
        runtime_injection: dict | None = None,
    ) -> dict:
        decision_context = decision_context or {}

        intimacy_overrides = self.build_intimacy_overrides(
            intimacy_context=intimacy_context,
            runtime_injection=runtime_injection,
        )

        decision_context["intimacy_overrides"] = (
            intimacy_overrides
        )

        decision_context["premium_sexting_allowed"] = (
            intimacy_overrides.get(
                "premium_sexting_allowed",
                False,
            )
        )

        decision_context["explicit_allowed"] = (
            intimacy_overrides.get(
                "explicit_allowed",
                False,
            )
        )

        decision_context["runtime_mode"] = (
            intimacy_overrides.get(
                "runtime_mode",
                "safe_chat",
            )
        )

        decision_context["escalation_priority"] = (
            intimacy_overrides.get(
                "escalation_priority",
                "low",
            )
        )

        return decision_context

    def _build_runtime_rules(
        self,
        runtime_injection: dict,
        intimacy_context: dict,
    ) -> dict:
        return {
            "preserve_safety": True,
            "do_not_exceed_intimacy_tier": True,
            "respect_premium_gate": True,
            "respect_runtime_mode": True,
            "respect_blocked_behaviors": True,
            "runtime_injection_present": bool(
                runtime_injection
            ),
            "intimacy_context_present": bool(
                intimacy_context
            ),
        }

    def _first_available(
        self,
        *values,
    ):
        for value in values:
            if value is not None:
                return value

        return None
    
    def build_overrides(
        self,
        user_memory: dict | None = None,
        runtime_state: dict | None = None,
        canonical_buyer_memory: dict | None = None,
        **kwargs,
    ):
        """
        Compatibility wrapper for DecisionEngine.

        Keeps older DecisionEngine calls working while avoiding
        argument mismatch errors with the current intimacy service.
        """

        user_memory = user_memory or {}
        runtime_state = runtime_state or {}
        canonical_buyer_memory = canonical_buyer_memory or {}

        canonical_authority = (
            canonical_buyer_memory.get("customer_value_authority")
            == "COMMERCE_BACKED_AUTHORITATIVE_VALUE"
        )
        buyer_truth = (
            canonical_buyer_memory if canonical_authority else user_memory
        )

        premium_sexting_allowed = bool(
            runtime_state.get("premium_sexting_allowed")
            or user_memory.get("premium_sexting_allowed")
        )

        explicit_allowed = bool(
            runtime_state.get("explicit_allowed")
            or user_memory.get("explicit_allowed")
        )

        buyer_tier = (
            buyer_truth.get("buyer_tier")
            or runtime_state.get("buyer_tier")
            or "NON_BUYER"
        )

        buyer_tier = str(buyer_tier).upper()

        # --------------------------------------------------
        # 3D.19.15B — WHALE FRESHNESS / STALE-STATE DECAY
        # --------------------------------------------------

        last_monetization_at = (
            buyer_truth.get("last_purchase_at")
            or runtime_state.get("last_purchase_at")
            or user_memory.get("last_tip_at")
            or runtime_state.get("last_tip_at")
            or user_memory.get("last_unlock_at")
            or runtime_state.get("last_unlock_at")
            or user_memory.get("last_monetization_sync_at")
            or runtime_state.get("last_monetization_sync_at")
        )

        monetization_freshness_days = None

        if last_monetization_at:
            try:
                if isinstance(last_monetization_at, datetime):
                    parsed_date = last_monetization_at
                else:
                    parsed_date = datetime.fromisoformat(
                        str(last_monetization_at).replace(
                            "Z",
                            "+00:00",
                        )
                    )

                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(
                        tzinfo=timezone.utc
                    )

                now = datetime.now(timezone.utc)

                monetization_freshness_days = (
                    now - parsed_date
                ).days

            except Exception as e:
                print(
                    "[DEBUG FRESHNESS PARSE ERROR]",
                    e,
                    last_monetization_at,
                )
                monetization_freshness_days = None

        premium_freshness_state = "NON_SPENDER"

        normalized_buyer_tier = (
            str(buyer_tier).upper()
            if buyer_tier
            else "NONE"
        )

        purchase_count = int(buyer_truth.get("purchase_count") or 0)
        buyer_stage = str(
            buyer_truth.get("buyer_stage") or "PROSPECT"
        ).upper()
        relationship_investment = str(
            buyer_truth.get("relationship_investment") or "STANDARD"
        ).upper()
        current_commercial_momentum = str(
            runtime_state.get("current_commercial_momentum")
            or buyer_truth.get("current_commercial_momentum")
            or "INACTIVE"
        ).upper()
        active_buying_window = bool(
            runtime_state.get("active_buying_window")
            or buyer_truth.get("active_buying_window")
        )

        # This is a per-turn relationship projection, not a new persisted value
        # tier. Canonical purchase count/tier establishes the durable floor;
        # current verified buying momentum may raise current investment by one
        # bounded step without fabricating a permanent customer tier.
        if purchase_count <= 0:
            intimacy_entitlement = "GATED"
            entitlement_reason = "NO_PROVIDER_VERIFIED_PURCHASE"
        elif normalized_buyer_tier == "WHALE":
            intimacy_entitlement = "VIP"
            entitlement_reason = "CANONICAL_WHALE_VALUE"
        elif normalized_buyer_tier == "HIGH_VALUE":
            intimacy_entitlement = "PREMIUM"
            entitlement_reason = "CANONICAL_HIGH_VALUE_BUYER"
        elif purchase_count >= 2:
            intimacy_entitlement = "ELEVATED"
            entitlement_reason = "CANONICAL_REPEAT_BUYER"
        else:
            intimacy_entitlement = "LIMITED"
            entitlement_reason = "CANONICAL_FIRST_TIME_BUYER"

        momentum_elevated = False
        if active_buying_window and current_commercial_momentum == "HOT":
            if intimacy_entitlement == "LIMITED":
                intimacy_entitlement = "ELEVATED"
                momentum_elevated = True
            elif intimacy_entitlement == "ELEVATED":
                intimacy_entitlement = "PREMIUM"
                momentum_elevated = True
            if momentum_elevated:
                entitlement_reason += "_WITH_ACTIVE_BUYING_MOMENTUM"

        investment_by_entitlement = {
            "GATED": "BOUNDED_FLIRTATION_WITH_PREMIUM_BOUNDARY",
            "LIMITED": "BOUNDED_INTIMATE_TASTE",
            "ELEVATED": "SUSTAINED_BUT_BOUNDED_INTIMACY",
            "PREMIUM": "STRONG_PREMIUM_INTIMACY",
            "VIP": "HIGHEST_APPROPRIATE_INTIMACY",
        }
        intimacy_investment = investment_by_entitlement[intimacy_entitlement]

        if purchase_count > 0:
            if monetization_freshness_days is None:
                premium_freshness_state = (
                    "UNKNOWN_PREMIUM_STATE"
                )

            elif monetization_freshness_days <= 7:
                premium_freshness_state = (
                    "ACTIVE_PREMIUM"
                )

            elif monetization_freshness_days <= 21:
                premium_freshness_state = (
                    "WARM_PREMIUM"
                )

            elif monetization_freshness_days <= 45:
                premium_freshness_state = (
                    "COOLING_PREMIUM"
                )

            else:
                premium_freshness_state = (
                    "DORMANT_WHALE"
                )

        whale_reactivation_mode = False

        if (
            normalized_buyer_tier == "WHALE"
            and premium_freshness_state == "DORMANT_WHALE"
        ):
            whale_reactivation_mode = True

        dormant_whale = bool(
            premium_freshness_state
            == "DORMANT_WHALE"
        )

        adult_generation_allowed = (
            premium_sexting_allowed
            and explicit_allowed
            and intimacy_entitlement in ("PREMIUM", "VIP")
        )

        runtime_mode = (
            "premium_intimacy"
            if adult_generation_allowed
            else "safe_chat"
        )

        intimacy_tier = (
            intimacy_entitlement.lower()
        )

        print(
            "[DEBUG ADULT FLAG]",
            adult_generation_allowed,
            premium_sexting_allowed,
            explicit_allowed,
            normalized_buyer_tier,
            premium_freshness_state,
        )

        return {
            "success": True,
            "overrides_enabled": True,
            "adult_generation_allowed": (
                adult_generation_allowed
            ),
            "premium_sexting_allowed": (
                premium_sexting_allowed
            ),
            "explicit_allowed": explicit_allowed,
            "runtime_mode": runtime_mode,
            "intimacy_tier": intimacy_tier,
            "buyer_tier": buyer_tier,
            "buyer_stage": buyer_stage,
            "purchase_count": purchase_count,
            "intimacy_entitlement": intimacy_entitlement,
            "intimacy_entitlement_reason": entitlement_reason,
            "intimacy_investment": intimacy_investment,
            "intimacy_investment_inputs": {
                "buyerStage": buyer_stage,
                "valueTier": normalized_buyer_tier,
                "purchaseCount": purchase_count,
                "relationshipInvestment": relationship_investment,
                "currentCommercialMomentum": current_commercial_momentum,
                "activeBuyingWindow": active_buying_window,
                "momentumElevatedCurrentInvestment": momentum_elevated,
            },
            "canonical_buyer_authority_used": canonical_authority,
            "legacy_buyer_memory_authority_used": not canonical_authority,
            "premium_freshness_state": (
                premium_freshness_state
            ),
            "monetization_freshness_days": (
                monetization_freshness_days
            ),
            "dormant_whale": dormant_whale,
            "whale_reactivation_mode": (
                whale_reactivation_mode
            ),
            "premium_intimacy_currently_active": (
                adult_generation_allowed
            ),
            "send_allowed": False,
            "reason": "decision_engine_compatibility_wrapper",
        }
