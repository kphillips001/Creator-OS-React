class PostPurchaseContinuationService:
    """
    3D.17.4

    Determines intelligent continuation behavior after
    monetization events complete.

    IMPORTANT:
    This service does NOT send outbound messages.
    It only determines safe continuation routing.
    """

    def determine_continuation(
        self,
        monetization_event: dict,
        buyer_memory_context: dict,
        runtime_buyer_state: dict,
    ):
        if not monetization_event:
            return {
                "success": False,
                "reason": "missing_monetization_event",
            }

        event_type = monetization_event.get(
            "event_type",
            "",
        )

        buyer_tier = buyer_memory_context.get(
            "buyer_tier",
            "LOW",
        )

        runtime_mode = runtime_buyer_state.get(
            "runtime_mode",
            "safe_chat",
        )

        premium_allowed = runtime_buyer_state.get(
            "premium_allowed",
            False,
        )

        continuation_eligible = (
            runtime_buyer_state.get(
                "continuation_eligible",
                False,
            )
        )

        total_spend = float(
            buyer_memory_context.get(
                "total_spend",
                0,
            ) or 0
        )

        # ------------------------------------------
        # DEFAULT
        # ------------------------------------------

        continuation_type = "thank_you_only"

        escalation_level = "none"

        retention_mode = "standard"

        suppression_active = False

        # ------------------------------------------
        # NOT ELIGIBLE
        # ------------------------------------------

        if not continuation_eligible:
            suppression_active = True

            return {
                "success": True,
                "continuation_eligible": False,
                "continuation_type": (
                    "suppressed"
                ),
                "escalation_level": "none",
                "retention_mode": "cooldown",
                "suppression_active": True,
            }

        # ------------------------------------------
        # PURCHASE / UNLOCK
        # ------------------------------------------

        if event_type in [
            "purchase_created",
            "content_unlock",
            "unlock_completed",
        ]:
            continuation_type = "soft_continue"

            escalation_level = "light"

        # ------------------------------------------
        # TIP EVENTS
        # ------------------------------------------

        if event_type in [
            "tip_received",
            "tip_created",
        ]:
            continuation_type = "tip_reinforcement"

            escalation_level = "medium"

        # ------------------------------------------
        # SUBSCRIPTIONS
        # ------------------------------------------

        if event_type in [
            "subscription_created",
        ]:
            continuation_type = (
                "subscriber_retention"
            )

            escalation_level = "light"

            retention_mode = "subscriber"

        # ------------------------------------------
        # PREMIUM BUYERS
        # ------------------------------------------

        if premium_allowed:
            continuation_type = (
                "premium_continuation"
            )

            escalation_level = "high"

            retention_mode = "premium"

        # ------------------------------------------
        # WHALES
        # ------------------------------------------

        if buyer_tier == "WHALE":
            continuation_type = (
                "whale_retention"
            )

            escalation_level = "exclusive"

            retention_mode = "whale"

        # ------------------------------------------
        # HIGH SPENDERS
        # ------------------------------------------

        elif total_spend >= 250:
            escalation_level = "elevated"

        return {
            "success": True,
            "continuation_eligible": (
                continuation_eligible
            ),
            "continuation_type": (
                continuation_type
            ),
            "escalation_level": (
                escalation_level
            ),
            "retention_mode": (
                retention_mode
            ),
            "suppression_active": (
                suppression_active
            ),
            "runtime_mode": runtime_mode,
            "premium_allowed": (
                premium_allowed
            ),
            "buyer_tier": buyer_tier,
        }