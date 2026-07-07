class PostPurchaseDecisionService:
    """
    3D.12.1 - 3D.12.9

    Determines the next monetization behavior after realtime
    purchase, unlock, tip, or subscription events.

    This service only decides what should happen next.
    It does NOT send messages.
    It does NOT call Fanvue.
    It does NOT mutate database state directly.
    """

    def decide_next_action(
        self,
        event_type: str,
        amount: float = 0,
        buyer_tier: str = "NON_BUYER",
        heat_score: int = 0,
        intent_score: int = 0,
        last_offer: dict | None = None,
        last_purchase: dict | None = None,
        pending_ppv: dict | None = None,
        content_purchased: dict | None = None,
        conversation_mode: str = "casual",
        buyer_session_state: dict | None = None,
    ) -> dict:
        event_type = event_type or ""
        buyer_tier = (buyer_tier or "NON_BUYER").upper()
        conversation_mode = (conversation_mode or "casual").lower()

        last_offer = last_offer or {}
        last_purchase = last_purchase or {}
        pending_ppv = pending_ppv or {}
        content_purchased = content_purchased or {}
        buyer_session_state = buyer_session_state or {}

        amount = float(amount or 0)
        heat_score = int(heat_score or 0)
        intent_score = int(intent_score or 0)

        reasons = []

        action = "thank_you_only"
        aggression_level = "low"
        should_escalate = False
        should_slow_down = True
        allow_followup = True
        pacing_profile = "neutral"

        followup_mode = "standard"
        ppv_suppressed = False
        escalation_paused = False
        next_best_offer = None

        # --------------------------------------------------
        # 3D.12.2 — ROUTING REFINEMENT SIGNALS
        # --------------------------------------------------

        buyer_tier_score = {
            "NON_BUYER": 0,
            "LOW_SPENDER": 1,
            "ACTIVE_BUYER": 2,
            "HIGH_VALUE": 3,
            "WHALE": 4,
        }.get(buyer_tier, 0)

        relationship_depth = buyer_session_state.get(
            "relationship_depth_score",
            0,
        )

        buyer_momentum = buyer_session_state.get(
            "buyer_momentum_score",
            0,
        )

        cooldown_active = buyer_session_state.get(
            "post_purchase_cooldown",
            False,
        )

        recent_offer_pressure = buyer_session_state.get(
            "recent_offer_pressure",
            0,
        )

        recent_purchase_count = buyer_session_state.get(
            "recent_purchase_count",
            0,
        )

        recent_tip_count = buyer_session_state.get(
            "recent_tip_count",
            0,
        )

        recent_unlock_count = buyer_session_state.get(
            "recent_unlock_count",
            0,
        )

        last_offer_type = (
            buyer_session_state.get(
                "last_offer_type"
            )
            or ""
        )

        last_content_purchased = (
            buyer_session_state.get(
                "last_content_purchased"
            )
            or ""
        )

        emotional_engagement_score = buyer_session_state.get(
            "emotional_engagement_score",
            0,
        )

        cooldown_decay_level = buyer_session_state.get(
            "cooldown_decay_level",
            0,
        )

        whale_protection_mode = buyer_tier in [
            "WHALE",
            "HIGH_VALUE",
        ]

        # keep these intentionally available for later scoring
        _buyer_tier_score = buyer_tier_score
        _recent_tip_count = recent_tip_count
        _last_purchase = last_purchase
        _last_content_purchased = last_content_purchased

        # --------------------------------------------------
        # BUYER SESSION SAFETY
        # --------------------------------------------------

        if buyer_session_state.get("buyer_session_active"):
            reasons.append("buyer_session_active")

            return self._result(
                action="thank_you_only",
                aggression_level="low",
                should_escalate=False,
                should_slow_down=True,
                allow_followup=False,
                pacing_profile="slow",
                followup_mode="session_protected",
                ppv_suppressed=True,
                escalation_paused=True,
                next_best_offer="no_offer_session_protected",
                reasons=reasons,
            )

        # --------------------------------------------------
        # COOLDOWN ROUTING
        # --------------------------------------------------

        if cooldown_active:
            reasons.append("cooldown_active")

            action = "soft_continue"
            aggression_level = "low"
            should_escalate = False
            should_slow_down = True

        # --------------------------------------------------
        # PENDING PPV SAFETY
        # --------------------------------------------------

        if pending_ppv.get("active"):
            reasons.append("pending_ppv_active")

            return self._result(
                action="soft_continue",
                aggression_level="low",
                should_escalate=False,
                should_slow_down=True,
                allow_followup=allow_followup,
                pacing_profile="slow",
                followup_mode="pending_ppv_protected",
                ppv_suppressed=True,
                escalation_paused=True,
                next_best_offer="no_offer_pending_ppv",
                reasons=reasons,
            )

        # --------------------------------------------------
        # CORE EVENT DECISIONING
        # --------------------------------------------------

        if event_type in [
            "purchase_created",
            "purchase_received",
            "unlock_confirmed",
            "content_unlocked",
        ]:
            reasons.append("purchase_or_unlock_event")

            content_tier = (
                content_purchased.get("content_tier")
                or content_purchased.get("tier")
                or last_offer.get("offer_type")
                or ""
            ).lower()

            if whale_protection_mode:
                action = "whale_retention"
                aggression_level = "low"
                should_escalate = False
                should_slow_down = True

                reasons.append(
                    "high_value_or_whale_retention"
                )

                if (
                    relationship_depth >= 70
                    and buyer_momentum >= 70
                    and recent_offer_pressure <= 20
                ):
                    action = "premium_followup"
                    aggression_level = "medium"
                    should_escalate = True
                    should_slow_down = False

                    reasons.append(
                        "healthy_whale_continuation"
                    )

            elif content_tier in [
                "vip",
                "vip_offer",
            ]:
                action = "vip_to_premium_upsell"
                aggression_level = "medium"
                should_escalate = True
                should_slow_down = False

                reasons.append(
                    "vip_purchase_can_lead_to_premium"
                )

            elif content_tier in [
                "premium",
                "premium_offer",
            ]:
                action = "premium_followup"
                aggression_level = "low"
                should_escalate = False
                should_slow_down = True

                reasons.append(
                    "premium_purchase_retention"
                )

            elif (
                amount >= 75
                or heat_score >= 70
                or intent_score >= 70
            ):
                action = "soft_continue"
                aggression_level = "medium"
                should_escalate = True
                should_slow_down = False

                reasons.append(
                    "strong_purchase_or_intent_signal"
                )

            else:
                action = "thank_you_only"
                aggression_level = "low"
                should_escalate = False
                should_slow_down = True

                reasons.append(
                    "standard_purchase_thank_you"
                )

        elif event_type in [
            "tip_created",
            "tip_received",
        ]:
            reasons.append("tip_event")

            if buyer_tier in [
                "WHALE",
                "HIGH_VALUE",
            ] or amount >= 50:
                action = "tip_reward"
                aggression_level = "medium"
                should_escalate = True
                should_slow_down = False

                reasons.append(
                    "high_value_tip_reward"
                )

            else:
                action = "thank_you_only"
                aggression_level = "low"
                should_escalate = False
                should_slow_down = True

                reasons.append(
                    "standard_tip_thank_you"
                )

        elif event_type in [
            "subscription_created",
            "subscription_renewed",
        ]:
            reasons.append("subscription_event")

            action = "subscription_welcome"
            aggression_level = "low"
            should_escalate = False
            should_slow_down = True

            reasons.append(
                "subscriber_welcome_path"
            )

        else:
            reasons.append("unknown_event_safe_default")

        # --------------------------------------------------
        # CONVERSATION MODE LIMITS
        # --------------------------------------------------

        if conversation_mode in [
            "casual",
            "support",
        ]:
            aggression_level = self._cap_aggression(
                aggression_level,
                "low",
            )

            should_slow_down = True

            reasons.append(
                "conversation_mode_limits_aggression"
            )

        # --------------------------------------------------
        # OFFER PRESSURE SUPPRESSION
        # --------------------------------------------------

        if recent_offer_pressure >= 80:
            aggression_level = "low"
            should_escalate = False
            should_slow_down = True

            reasons.append(
                "high_offer_pressure_suppression"
            )

        # --------------------------------------------------
        # HEAT / INTENT CONTINUATION
        # --------------------------------------------------

        if (
            heat_score >= 80
            and intent_score >= 75
            and allow_followup
        ):
            if whale_protection_mode and not (
                relationship_depth >= 70
                and buyer_momentum >= 70
                and recent_offer_pressure <= 20
            ):
                reasons.append(
                    "whale_protection_blocks_heat_override"
                )

            elif recent_offer_pressure >= 80:
                reasons.append(
                    "offer_pressure_blocks_heat_override"
                )

            else:
                if action == "thank_you_only":
                    action = "soft_continue"

                if aggression_level == "low":
                    aggression_level = "medium"

                should_escalate = True
                should_slow_down = False

                reasons.append(
                    "high_heat_intent_allows_continue"
                )

        # --------------------------------------------------
        # 3D.12.3 — BUYER TIER DECISION SHAPING
        # --------------------------------------------------

        if buyer_tier == "LOW_SPENDER":
            if aggression_level == "high":
                aggression_level = "medium"

            if should_escalate:
                should_slow_down = True

            reasons.append(
                "low_spender_pacing_control"
            )

        elif buyer_tier == "NON_BUYER":
            aggression_level = "low"
            should_escalate = False
            should_slow_down = True

            if action not in [
                "thank_you_only",
                "subscription_welcome",
            ]:
                action = "soft_continue"

            reasons.append(
                "non_buyer_restriction"
            )

        elif buyer_tier == "ACTIVE_BUYER":
            if (
                heat_score >= 60
                and intent_score >= 60
                and not cooldown_active
            ):
                should_escalate = True

                if aggression_level == "low":
                    aggression_level = "medium"

                reasons.append(
                    "active_buyer_continuation_bias"
                )

        elif buyer_tier == "HIGH_VALUE":
            if relationship_depth >= 60:
                should_escalate = True

                if aggression_level == "low":
                    aggression_level = "medium"

                reasons.append(
                    "high_value_relationship_building"
                )

        elif buyer_tier == "WHALE":
            if recent_offer_pressure >= 50:
                should_slow_down = True
                should_escalate = False
                aggression_level = "low"

                reasons.append(
                    "whale_pressure_protection"
                )

            elif relationship_depth >= 80:
                should_escalate = True
                should_slow_down = False

                if aggression_level == "low":
                    aggression_level = "medium"

                reasons.append(
                    "whale_relationship_continuation"
                )

        # --------------------------------------------------
        # 3D.12.8 — COOLDOWN & FOLLOW-UP INTELLIGENCE
        # --------------------------------------------------

        if cooldown_active:
            followup_mode = "cooldown"
            ppv_suppressed = True
            escalation_paused = True
            should_slow_down = True
            should_escalate = False
            aggression_level = "low"

            reasons.append(
                "cooldown_followup_suppression"
            )

        if recent_offer_pressure >= 70:
            followup_mode = "decompression"
            ppv_suppressed = True
            should_slow_down = True
            aggression_level = "low"

            reasons.append(
                "high_pressure_followup_decompression"
            )

        if recent_purchase_count >= 2:
            followup_mode = "retention"
            ppv_suppressed = True
            should_slow_down = True

            reasons.append(
                "multiple_recent_purchases_retention_mode"
            )

        if recent_unlock_count >= 2:
            followup_mode = "ownership_continuation"
            should_slow_down = True

            reasons.append(
                "multiple_recent_unlocks_soft_continuation"
            )

        if (
            emotional_engagement_score >= 75
            and relationship_depth >= 70
            and recent_offer_pressure <= 30
            and not cooldown_active
        ):
            followup_mode = "emotional_continuation"
            ppv_suppressed = False
            escalation_paused = False

            reasons.append(
                "emotional_continuation_allowed"
            )

        if cooldown_decay_level >= 70:
            followup_mode = "deep_cooldown"
            ppv_suppressed = True
            escalation_paused = True
            should_escalate = False
            should_slow_down = True
            aggression_level = "low"

            reasons.append(
                "deep_cooldown_active"
            )

        # --------------------------------------------------
        # 3D.12.4 — OFFER AGGRESSION PACING
        # --------------------------------------------------

        if should_slow_down:
            pacing_profile = "slow"

        elif should_escalate:
            pacing_profile = "active"

        if amount >= 100:
            pacing_profile = "premium"

            reasons.append(
                "high_purchase_amount_pacing"
            )

        if amount >= 250:
            pacing_profile = "whale"
            aggression_level = "low"
            should_slow_down = True

            reasons.append(
                "massive_purchase_requires_soft_handling"
            )

        if recent_offer_pressure >= 70:
            pacing_profile = "decompression"
            aggression_level = "low"
            should_slow_down = True

            reasons.append(
                "offer_pressure_decompression"
            )

        if conversation_mode in [
            "casual",
            "support",
        ]:
            if pacing_profile not in [
                "slow",
                "decompression",
            ]:
                pacing_profile = "casual"

            reasons.append(
                "casual_mode_throttles_pacing"
            )

        if (
            relationship_depth >= 75
            and buyer_momentum >= 70
            and recent_offer_pressure <= 25
            and not cooldown_active
        ):
            if pacing_profile not in [
                "whale",
                "decompression",
            ]:
                pacing_profile = "relationship"

            reasons.append(
                "relationship_based_continuation"
            )

        # --------------------------------------------------
        # 3D.12.9 — NEXT-BEST-OFFER SEQUENCING
        # --------------------------------------------------

        if (
            action == "vip_to_premium_upsell"
            or last_offer_type.lower() == "vip"
        ):
            next_best_offer = "premium_followup_offer"

            reasons.append(
                "vip_to_premium_sequence"
            )

        elif (
            action == "premium_followup"
            and recent_purchase_count >= 3
        ):
            next_best_offer = "exclusive_retention_offer"

            reasons.append(
                "premium_retention_sequence"
            )

        elif (
            action == "tip_reward"
            and amount >= 50
        ):
            next_best_offer = "reward_tease_sequence"

            reasons.append(
                "high_tip_reward_sequence"
            )

        elif action == "subscription_welcome":
            next_best_offer = "subscriber_warmup_sequence"

            reasons.append(
                "subscriber_sequence_started"
            )

        elif ppv_suppressed or escalation_paused:
            next_best_offer = "no_offer_cooldown"

            reasons.append(
                "cooldown_blocks_offer_sequence"
            )

        else:
            next_best_offer = "standard_relationship_build"

            reasons.append(
                "default_relationship_sequence"
            )

        return self._result(
            action=action,
            aggression_level=aggression_level,
            should_escalate=should_escalate,
            should_slow_down=should_slow_down,
            allow_followup=allow_followup,
            pacing_profile=pacing_profile,
            followup_mode=followup_mode,
            ppv_suppressed=ppv_suppressed,
            escalation_paused=escalation_paused,
            next_best_offer=next_best_offer,
            reasons=reasons,
        )

    def _result(
        self,
        action: str,
        aggression_level: str,
        should_escalate: bool,
        should_slow_down: bool,
        allow_followup: bool,
        reasons: list,
        pacing_profile: str = "neutral",
        followup_mode: str = "standard",
        ppv_suppressed: bool = False,
        escalation_paused: bool = False,
        next_best_offer: str | None = None,
    ) -> dict:
        return {
            "success": True,
            "next_action": action,
            "aggression_level": aggression_level,
            "should_escalate": should_escalate,
            "should_slow_down": should_slow_down,
            "allow_followup": allow_followup,
            "pacing_profile": pacing_profile,
            "followup_mode": followup_mode,
            "ppv_suppressed": ppv_suppressed,
            "escalation_paused": escalation_paused,
            "next_best_offer": next_best_offer,
            "reasons": reasons,
        }

    def _cap_aggression(
        self,
        current: str,
        cap: str,
    ) -> str:
        order = {
            "low": 1,
            "medium": 2,
            "high": 3,
        }

        current_score = order.get(
            current,
            1,
        )

        cap_score = order.get(
            cap,
            1,
        )

        if current_score <= cap_score:
            return current

        return cap