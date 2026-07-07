class RuntimeBuyerStateRefreshService:
    """
    3D.17.3

    Recalculates realtime buyer runtime state immediately
    after monetization events complete.

    PURPOSE:
    - refresh buyer tier runtime state
    - refresh intimacy escalation eligibility
    - refresh premium routing eligibility
    - refresh PPV suppression state
    - refresh continuation eligibility

    IMPORTANT:
    This service does NOT send outbound messages.
    It only recalculates runtime behavior state.
    """

    def refresh_runtime_state(
        self,
        buyer_memory_context: dict | None,
    ):
        if not buyer_memory_context:
            return {
                "success": False,
                "reason": "missing_buyer_memory_context",
            }

        buyer_tier = buyer_memory_context.get(
            "buyer_tier",
            "LOW",
        )

        total_spend = float(
            buyer_memory_context.get(
                "total_spend",
                0,
            ) or 0
        )

        owned_content_count = int(
            buyer_memory_context.get(
                "owned_content_count",
                0,
            ) or 0
        )

        repeat_purchase_score = int(
            buyer_memory_context.get(
                "repeat_purchase_score",
                0,
            ) or 0
        )

        is_whale = bool(
            buyer_memory_context.get(
                "is_whale",
                False,
            )
        )

        is_subscriber = bool(
            buyer_memory_context.get(
                "is_subscriber",
                False,
            )
        )

        # ------------------------------------------
        # DEFAULTS
        # ------------------------------------------

        runtime_mode = "safe_chat"

        spender_confidence = "low"

        premium_allowed = False

        continuation_eligible = False

        mass_ppv_blocked = False

        cooldowns_active = True

        # ------------------------------------------
        # ACTIVE BUYER
        # ------------------------------------------

        if buyer_tier in [
            "ACTIVE_BUYER",
            "HIGH_VALUE",
        ]:
            spender_confidence = "medium"

            continuation_eligible = True

            cooldowns_active = False

        # ------------------------------------------
        # PREMIUM ELIGIBILITY
        # ------------------------------------------

        if (
            total_spend >= 100
            or owned_content_count >= 5
            or repeat_purchase_score >= 30
        ):
            premium_allowed = True

            runtime_mode = "premium_gate"

        # ------------------------------------------
        # WHALE
        # ------------------------------------------

        if is_whale:
            spender_confidence = "high"

            premium_allowed = True

            runtime_mode = "explicit_allowed"

            mass_ppv_blocked = True

            continuation_eligible = True

            cooldowns_active = False

        # ------------------------------------------
        # SUBSCRIBERS
        # ------------------------------------------

        if is_subscriber and runtime_mode == "safe_chat":
            runtime_mode = "warm_subscriber"

        return {
            "success": True,
            "buyer_tier": buyer_tier,
            "spender_confidence": spender_confidence,
            "runtime_mode": runtime_mode,
            "premium_allowed": premium_allowed,
            "continuation_eligible": (
                continuation_eligible
            ),
            "mass_ppv_blocked": mass_ppv_blocked,
            "cooldowns_active": cooldowns_active,
            "total_spend": total_spend,
            "owned_content_count": owned_content_count,
            "repeat_purchase_score": (
                repeat_purchase_score
            ),
        }