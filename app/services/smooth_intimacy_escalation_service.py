class SmoothIntimacyEscalationService:
    """
    3D.11.1

    Prevents abrupt intimacy jumps.

    This service converts spend/intimacy/momentum signals into a smooth
    escalation profile that DecisionEngine + GPTService can safely use.
    """

    def build_escalation_profile(
        self,
        intimacy_context: dict | None = None,
        spend_profile: dict | None = None,
        buyer_memory: dict | None = None,
        conversation_state: dict | None = None,
    ) -> dict:
        intimacy_context = intimacy_context or {}
        spend_profile = spend_profile or {}
        buyer_memory = buyer_memory or {}
        conversation_state = conversation_state or {}

        intimacy_tier = str(
            intimacy_context.get("intimacy_tier")
            or spend_profile.get("intimacy_tier")
            or "safe"
        ).lower()

        buyer_tier = str(
            spend_profile.get("buyer_tier")
            or buyer_memory.get("buyer_tier")
            or "NON_BUYER"
        ).upper()

        runtime_mode = str(
            intimacy_context.get("runtime_mode")
            or buyer_memory.get("runtime_mode")
            or "safe_chat"
        ).lower()

        spender_confidence = str(
            intimacy_context.get("spender_confidence")
            or buyer_memory.get("spender_confidence")
            or "low"
        ).lower()

        recent_purchase_active = bool(
            spend_profile.get("recent_purchase_active")
            or buyer_memory.get("recent_purchase_active")
        )

        recent_tip_active = bool(
            spend_profile.get("recent_tip_active")
            or buyer_memory.get("recent_tip_active")
        )

        purchase_count = int(
            spend_profile.get("purchase_count")
            or buyer_memory.get("purchase_count")
            or 0
        )

        total_spend = float(
            spend_profile.get("total_spend")
            or buyer_memory.get("total_spend")
            or 0
        )

        heat_score = float(
            conversation_state.get("heat_score")
            or buyer_memory.get("heat_score")
            or 0
        )

        intent_score = float(
            conversation_state.get("intent_score")
            or buyer_memory.get("intent_score")
            or 0
        )

        buyer_momentum_score = float(
            conversation_state.get("buyer_momentum_score")
            or buyer_memory.get("buyer_momentum_score")
            or 0
        )

        relationship_depth_score = float(
            conversation_state.get("relationship_depth_score")
            or buyer_memory.get("relationship_depth_score")
            or 0
        )

        conversation_streak = int(
            conversation_state.get("conversation_streak")
            or buyer_memory.get("conversation_streak")
            or 0
        )

        engagement_depth_score = float(
            conversation_state.get("engagement_depth_score")
            or buyer_memory.get("engagement_depth_score")
            or 0
        )

        tip_count = int(
            spend_profile.get("tip_count")
            or buyer_memory.get("tip_count")
            or 0
        )

        intimacy_cooldown_active = bool(
            conversation_state.get("intimacy_cooldown_active")
            or buyer_memory.get("intimacy_cooldown_active")
        )

        recent_escalation_active = bool(
            conversation_state.get("recent_escalation_active")
            or buyer_memory.get("recent_escalation_active")
        )

        cooldown_decay_level = float(
            conversation_state.get("cooldown_decay_level")
            or buyer_memory.get("cooldown_decay_level")
            or 0
        )

        post_purchase_cooldown = bool(
            conversation_state.get("post_purchase_cooldown")
            or buyer_memory.get("post_purchase_cooldown")
        )

        conversation_mode = str(
            conversation_state.get("conversation_mode")
            or buyer_memory.get("conversation_mode")
            or "casual"
        ).lower()

        buyer_session_active = bool(
            conversation_state.get("buyer_session_active")
            or buyer_memory.get("buyer_session_active")
        )

        buyer_session_step = int(
            conversation_state.get("buyer_session_step")
            or buyer_memory.get("buyer_session_step")
            or 0
        )

        buyer_session_action = str(
            conversation_state.get("buyer_session_action")
            or buyer_memory.get("buyer_session_action")
            or ""
        ).lower()

        reasons = []

        stage = "soft_flirt"
        max_intensity = "low"
        pacing = "slow"
        explicit_jump_blocked = True

        if intimacy_tier in ["safe", "0", "tease_only"]:
            stage = "soft_flirt"
            max_intensity = "low"
            pacing = "slow"
            reasons.append("free_or_safe_tier")

        elif intimacy_tier in ["warm", "1"]:
            stage = "warm_tease"
            max_intensity = "medium_low"
            pacing = "gradual"
            reasons.append("warm_low_spender_tier")

        elif intimacy_tier in ["hot", "2"]:
            stage = "strong_tension"
            max_intensity = "medium"
            pacing = "controlled"
            reasons.append("active_buyer_intimacy")

        elif intimacy_tier in ["premium", "3"]:
            stage = "premium_build"
            max_intensity = "medium_high"
            pacing = "smooth"
            reasons.append("premium_intimacy_eligible")

        if buyer_tier in ["HIGH_VALUE", "WHALE"]:
            stage = "exclusive_premium"
            max_intensity = "high"
            pacing = "slow_premium"
            reasons.append("high_value_or_whale")

        if recent_purchase_active and purchase_count <= 1:
            pacing = "post_purchase_slow_build"
            max_intensity = self._cap_intensity(max_intensity, "medium")
            explicit_jump_blocked = True
            reasons.append("recent_first_purchase_prevents_abrupt_jump")

        if recent_tip_active and spender_confidence in ["medium", "high"]:
            if stage in ["soft_flirt", "warm_tease"]:
                stage = "warm_tease"
            pacing = "warmer_but_controlled"
            reasons.append("recent_tip_adds_warmth")

        if heat_score >= 75 and intent_score >= 70:
            if stage == "soft_flirt":
                stage = "warm_tease"
            elif stage == "warm_tease":
                stage = "strong_tension"
            reasons.append("high_heat_and_intent_allow_gradual_step_up")

        # --------------------------------------------------
        # 3D.11.6 — MOMENTUM & RELATIONSHIP DEPTH
        # --------------------------------------------------

        relationship_strength = (
            buyer_momentum_score
            + relationship_depth_score
            + engagement_depth_score
        )

        if conversation_streak >= 5:
            relationship_strength += 10

        if purchase_count >= 3:
            relationship_strength += 15

        if tip_count >= 3:
            relationship_strength += 10

        # -----------------------------------------
        # STRONG RELATIONSHIP MOMENTUM
        # -----------------------------------------

        if relationship_strength >= 75:

            if max_intensity == "medium_low":
                max_intensity = "medium"

            elif max_intensity == "medium":
                max_intensity = "medium_high"

            reasons.append(
                "high_relationship_momentum"
            )

        # -----------------------------------------
        # VERY STRONG RELATIONSHIP
        # -----------------------------------------

        if relationship_strength >= 120:

            if spender_confidence in [
                "medium",
                "high",
            ]:
                explicit_jump_blocked = False

            reasons.append(
                "deep_relationship_progression"
            )
        
        # --------------------------------------------------
        # 3D.11.9 — PREMIUM ESCALATION SAFEGUARDS
        # --------------------------------------------------

        premium_guard_triggered = False

        # -----------------------------------------
        # LOW RELATIONSHIP PROTECTION
        # -----------------------------------------

        if (
            intimacy_tier in ["premium", "3"]
            and relationship_strength < 40
        ):
            premium_guard_triggered = True

            explicit_jump_blocked = True

            max_intensity = self._cap_intensity(
                max_intensity,
                "medium",
            )

            reasons.append(
                "premium_guard_low_relationship"
            )

        # -----------------------------------------
        # LOW PURCHASE HISTORY PROTECTION
        # -----------------------------------------

        if (
            intimacy_tier in ["premium", "3"]
            and purchase_count <= 1
        ):
            premium_guard_triggered = True

            explicit_jump_blocked = True

            max_intensity = self._cap_intensity(
                max_intensity,
                "medium",
            )

            reasons.append(
                "premium_guard_low_purchase_history"
            )

        # -----------------------------------------
        # LOW SPENDER CONFIDENCE PROTECTION
        # -----------------------------------------

        if spender_confidence == "low":

            premium_guard_triggered = True

            explicit_jump_blocked = True

            max_intensity = self._cap_intensity(
                max_intensity,
                "medium_low",
            )

            reasons.append(
                "premium_guard_low_confidence"
            )

        # -----------------------------------------
        # CONVERSATION SAFETY PROTECTION
        # -----------------------------------------

        if conversation_mode in [
            "casual",
            "support",
        ]:

            max_intensity = self._cap_intensity(
                max_intensity,
                "medium_low",
            )

            reasons.append(
                "premium_guard_safe_mode"
            )

        # -----------------------------------------
        # FINAL SAFETY CAP
        # -----------------------------------------

        if (
            premium_guard_triggered
            and max_intensity == "high"
        ):
            max_intensity = "medium_high"

            reasons.append(
                "premium_guard_final_cap"
            )
        
        # --------------------------------------------------
        # 3D.11.7 — COOLDOWN & ESCALATION DECAY
        # --------------------------------------------------

        if intimacy_cooldown_active:

            pacing = "cooldown"

            explicit_jump_blocked = True

            reasons.append(
                "intimacy_cooldown_active"
            )

            # -----------------------------------------
            # HEAVY DECAY
            # -----------------------------------------

            if cooldown_decay_level >= 70:

                max_intensity = "low"

                reasons.append(
                    "heavy_escalation_decay"
                )

            # -----------------------------------------
            # MEDIUM DECAY
            # -----------------------------------------

            elif cooldown_decay_level >= 40:

                max_intensity = self._cap_intensity(
                    max_intensity,
                    "medium_low",
                )

                reasons.append(
                    "medium_escalation_decay"
                )

            # -----------------------------------------
            # LIGHT DECAY
            # -----------------------------------------

            else:
                max_intensity = self._cap_intensity(
                    max_intensity,
                    "medium",
                )

                reasons.append(
                    "light_escalation_decay"
                )

        # -----------------------------------------
        # RECENT ESCALATION STABILIZATION
        # -----------------------------------------

        if recent_escalation_active:

            pacing = "stabilized"

            reasons.append(
                "recent_escalation_stabilization"
            )

        
        # --------------------------------------------------
        # 3D.11.4 — CONVERSATION MODE SHAPING
        # --------------------------------------------------

        if conversation_mode in ["casual", "support"]:
            pacing = "slow"
            max_intensity = self._cap_intensity(
                max_intensity,
                "medium_low",
            )

            explicit_jump_blocked = True

            reasons.append(
                "casual_mode_limits_escalation"
            )

        elif conversation_mode == "flirty":
            pacing = "gradual"

            max_intensity = self._cap_intensity(
                max_intensity,
                "medium",
            )

            reasons.append(
                "flirty_mode_gradual_progression"
            )

        elif conversation_mode == "tension":
            pacing = "controlled"

            if max_intensity == "medium_low":
                max_intensity = "medium"

            reasons.append(
                "tension_mode_allows_controlled_heat"
            )

        elif conversation_mode in [
            "conversion",
            "close",
            "pre_sell",
        ]:
            pacing = "smooth_conversion"

            if (
                intimacy_tier in ["premium", "3"]
                and spender_confidence in ["medium", "high"]
            ):
                explicit_jump_blocked = False

            reasons.append(
                "conversion_mode_allows_escalation"
            )

        # --------------------------------------------------
        # 3D.11.5 — BUYER SESSION SYNCHRONIZATION
        # --------------------------------------------------

        if buyer_session_active:

            reasons.append(
                "buyer_session_active"
            )

            # -----------------------------------------
            # SESSION STEP 1
            # -----------------------------------------

            if buyer_session_step == 1:
                pacing = "slow_build"

                max_intensity = self._cap_intensity(
                    max_intensity,
                    "medium",
                )

                explicit_jump_blocked = True

                reasons.append(
                    "buyer_session_step_1_bridge"
                )

            # -----------------------------------------
            # SESSION STEP 2
            # -----------------------------------------

            elif buyer_session_step == 2:
                pacing = "controlled_ppv_build"

                max_intensity = self._cap_intensity(
                    max_intensity,
                    "medium_high",
                )

                reasons.append(
                    "buyer_session_step_2_ppv_build"
                )

            # -----------------------------------------
            # SESSION STEP 3+
            # -----------------------------------------

            elif buyer_session_step >= 3:
                pacing = "conversion_locked"

                if spender_confidence in [
                    "medium",
                    "high",
                ]:
                    explicit_jump_blocked = False

                reasons.append(
                    "buyer_session_conversion_phase"
                )

            # -----------------------------------------
            # CLOSE MODE
            # -----------------------------------------

            if buyer_session_action == "close_mode":
                pacing = "close_mode"

                if spender_confidence == "high":
                    explicit_jump_blocked = False

                reasons.append(
                    "buyer_session_close_mode"
                )

            # -----------------------------------------
            # EXIT MODE
            # -----------------------------------------

            elif buyer_session_action == "exit_session":
                pacing = "decompression"

                max_intensity = "low"

                explicit_jump_blocked = True

                reasons.append(
                    "buyer_session_exit_decompression"
                )

        # -----------------------------------------
        # POST PURCHASE DECOMPRESSION
        # -----------------------------------------

        if post_purchase_cooldown:

            pacing = "post_purchase_decompression"

            explicit_jump_blocked = True

            max_intensity = self._cap_intensity(
                max_intensity,
                "medium",
            )

            reasons.append(
                "post_purchase_cooldown_active"
            )


        if runtime_mode in ["premium_gate", "premium"]:
            if conversation_mode in ["casual", "support"]:
                explicit_jump_blocked = True
                reasons.append("casual_mode_overrides_premium_gate")

            elif (
                total_spend >= 75
                or purchase_count >= 2
            ):
                if (
                    buyer_session_active
                    and buyer_session_step <= 1
                ):
                    explicit_jump_blocked = True

                    reasons.append(
                        "buyer_session_prevents_fast_jump"
                    )

                else:
                    explicit_jump_blocked = False

                    reasons.append(
                        "earned_premium_continuity_allowed"
                    )
            else:
                explicit_jump_blocked = True
                pacing = "post_purchase_slow_build"
                reasons.append("premium_gate_requires_smooth_build")

        return {
            "success": True,
            "escalation_stage": stage,
            "max_intimacy_intensity": max_intensity,
            "pacing_directive": pacing,
            "explicit_jump_blocked": explicit_jump_blocked,
            "should_smooth_escalation": True,
            "gpt_instruction": self._build_instruction(
                stage=stage,
                max_intensity=max_intensity,
                pacing=pacing,
                explicit_jump_blocked=explicit_jump_blocked,
            ),
            "reasons": reasons,
            "premium_guard_triggered": premium_guard_triggered,
        }

    def _cap_intensity(self, current: str, cap: str) -> str:
        order = {
            "low": 1,
            "medium_low": 2,
            "medium": 3,
            "medium_high": 4,
            "high": 5,
        }

        current_score = order.get(current, 1)
        cap_score = order.get(cap, 1)

        if current_score <= cap_score:
            return current

        for key, value in order.items():
            if value == cap_score:
                return key

        return "low"

    def _build_instruction(
        self,
        stage: str,
        max_intensity: str,
        pacing: str,
        explicit_jump_blocked: bool,
    ) -> str:
        blocked_text = (
            "Do not jump abruptly into explicit or advanced intimacy. "
            if explicit_jump_blocked
            else "Premium escalation is allowed, but still build naturally. "
        )

        return (
            "Smooth intimacy escalation is active. "
            f"Current escalation stage: {stage}. "
            f"Maximum intimacy intensity: {max_intensity}. "
            f"Pacing directive: {pacing}. "
            f"{blocked_text}"
            "Progress naturally from playful to warmer to more intimate. "
            "Keep the tone emotionally believable and avoid sudden intensity spikes."
        )