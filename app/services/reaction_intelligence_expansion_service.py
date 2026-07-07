class ReactionIntelligenceExpansionService:
    """
    3D.19.1 — Reaction Intelligence Expansion Foundation

    Intelligence-only layer for automated monetization reactions.

    This service does NOT:
    - send Fanvue messages
    - bypass safety gates
    - trigger outbound automation
    """

    def build_reaction_intelligence(
        self,
        monetization_event: dict,
        buyer_memory: dict | None = None,
        runtime_state: dict | None = None,
        spend_profile: dict | None = None,
    ) -> dict:
        if not monetization_event:
            return self._blocked(
                "missing_monetization_event"
            )

        buyer_memory = buyer_memory or {}
        runtime_state = runtime_state or {}
        spend_profile = spend_profile or {}

        event_type = monetization_event.get("event_type")

        buyer_tier = (
            spend_profile.get("buyer_tier")
            or buyer_memory.get("buyer_tier")
            or "NON_BUYER"
        )

        buyer_tier = str(buyer_tier).upper()

        reaction_profile = self._build_reaction_profile(
            buyer_tier=buyer_tier,
            event_type=event_type,
            runtime_state=runtime_state,
            buyer_memory=buyer_memory,
        )

        premium_intimacy_routing = (
            self._build_premium_intimacy_routing(
                buyer_tier=buyer_tier,
                runtime_state=runtime_state,
                buyer_memory=buyer_memory,
                spend_profile=spend_profile,
            )
        )

        whale_retention_profile = (
            self._build_whale_retention_profile(
                buyer_tier=buyer_tier,
                runtime_state=runtime_state,
                buyer_memory=buyer_memory,
                spend_profile=spend_profile,
            )
        )

        adaptive_reaction_tone = (
            self._build_adaptive_reaction_tone(
                buyer_tier=buyer_tier,
                reaction_profile=reaction_profile,
                premium_intimacy_routing=(
                    premium_intimacy_routing
                ),
                whale_retention_profile=(
                    whale_retention_profile
                ),
            )
        )

        reaction_timing_intelligence = (
            self._build_reaction_timing_intelligence(
                reaction_profile=reaction_profile,
                adaptive_reaction_tone=(
                    adaptive_reaction_tone
                ),
                whale_retention_profile=(
                    whale_retention_profile
                ),
                premium_intimacy_routing=(
                    premium_intimacy_routing
                ),
            )
        )

        contextual_cta_injection = (
            self._build_contextual_cta_injection(
                event_type=event_type,
                buyer_tier=buyer_tier,
                reaction_profile=reaction_profile,
                premium_intimacy_routing=(
                    premium_intimacy_routing
                ),
                whale_retention_profile=(
                    whale_retention_profile
                ),
            )
        )

        followup_chaining_logic = (
            self._build_followup_chaining_logic(
                event_type=event_type,
                buyer_tier=buyer_tier,
                reaction_profile=reaction_profile,
                premium_intimacy_routing=(
                    premium_intimacy_routing
                ),
                whale_retention_profile=(
                    whale_retention_profile
                ),
                contextual_cta_injection=(
                    contextual_cta_injection
                ),
            )
        )

        post_purchase_emotional_reinforcement = (
            self._build_post_purchase_emotional_reinforcement(
                buyer_tier=buyer_tier,
                reaction_profile=reaction_profile,
                whale_retention_profile=(
                    whale_retention_profile
                ),
                adaptive_reaction_tone=(
                    adaptive_reaction_tone
                ),
            )
        )

        realtime_reaction_llm_routing = (
            self._build_realtime_reaction_llm_routing(
                premium_intimacy_routing=(
                    premium_intimacy_routing
                ),
                adaptive_reaction_tone=(
                    adaptive_reaction_tone
                ),
                whale_retention_profile=(
                    whale_retention_profile
                ),
                reaction_profile=reaction_profile,
            )
        )

        return {
            "success": True,
            "blocked": False,
            "event_type": event_type,
            "buyer_tier": buyer_tier,
            "reaction_tone": self._resolve_reaction_tone(
                event_type,
                buyer_tier,
            ),
            "emotional_continuation": (
                self._resolve_emotional_continuation(
                    event_type,
                    buyer_tier,
                )
            ),
            "cta_strategy": self._resolve_cta_strategy(
                event_type,
                buyer_tier,
            ),
            "timing_profile": self._resolve_timing_profile(
                event_type,
                buyer_tier,
                runtime_state,
            ),
            "premium_positioning": buyer_tier in (
                "ACTIVE_BUYER",
                "HIGH_VALUE",
                "WHALE",
            ),
            "whale_sensitive": buyer_tier == "WHALE",
            "should_hard_sell": False,
            "safety_note": (
                "intelligence_only_no_outbound_send"
            ),
            "reaction_profile": reaction_profile,
            "premium_intimacy_routing": (
                premium_intimacy_routing
            ),
            "whale_retention_profile": (
                whale_retention_profile
            ),
            "adaptive_reaction_tone": (
                adaptive_reaction_tone
            ),
            "reaction_timing_intelligence": (
                reaction_timing_intelligence
            ),
            "contextual_cta_injection": (
                contextual_cta_injection
            ),
            "followup_chaining_logic": (
                followup_chaining_logic
            ),
            "post_purchase_emotional_reinforcement": (
                post_purchase_emotional_reinforcement
            ),
            "realtime_reaction_llm_routing": (
                realtime_reaction_llm_routing
            ),
        }

    def _resolve_reaction_tone(
        self,
        event_type: str | None,
        buyer_tier: str,
    ) -> str:
        if buyer_tier == "WHALE":
            return "exclusive_soft_retention"

        if buyer_tier == "HIGH_VALUE":
            return "premium_appreciative"

        if event_type == "tip_received":
            return "warm_grateful"

        if event_type == "subscription_created":
            return "welcoming_personal"

        if event_type == "unlock_confirmation":
            return "playful_continuation"

        return "soft_appreciative"

    def _resolve_emotional_continuation(
        self,
        event_type: str | None,
        buyer_tier: str,
    ) -> str:
        if buyer_tier == "WHALE":
            return "preserve_exclusivity_and_attachment"

        if buyer_tier == "HIGH_VALUE":
            return "deepen_premium_relationship"

        if event_type == "tip_received":
            return "reward_emotional_investment"

        if event_type == "subscription_created":
            return "begin_subscriber_warmup"

        if event_type == "unlock_confirmation":
            return "continue_after_content_unlock"

        return "maintain_post_purchase_momentum"

    def _resolve_cta_strategy(
        self,
        event_type: str | None,
        buyer_tier: str,
    ) -> str:
        if buyer_tier == "WHALE":
            return "no_immediate_cta"

        if buyer_tier == "HIGH_VALUE":
            return "soft_future_premium_hint"

        if event_type == "unlock_confirmation":
            return "contextual_next_step_tease"

        if event_type == "tip_received":
            return "light_reward_tease"

        if event_type == "subscription_created":
            return "subscriber_warmup_no_sell"

        return "soft_continuation_no_hard_sell"

    def _resolve_timing_profile(
        self,
        event_type: str | None,
        buyer_tier: str,
        runtime_state: dict,
    ) -> str:
        if runtime_state.get("buyer_session_active"):
            return "session_protected"

        if buyer_tier == "WHALE":
            return "slow_personalized"

        if buyer_tier == "HIGH_VALUE":
            return "soft_delayed"

        if event_type == "tip_received":
            return "immediate_acknowledgement"

        return "natural_short_delay"

    def _build_reaction_profile(
        self,
        buyer_tier: str,
        event_type: str | None,
        runtime_state: dict,
        buyer_memory: dict,
    ) -> dict:
        profile = {
            "emotional_warmth": "medium",
            "reward_depth": "light",
            "continuation_pressure": "soft",
            "premium_positioning": False,
            "hard_sell_allowed": False,
            "exclusivity_level": "low",
            "retention_priority": "normal",
            "emotional_intensity": "moderate",
            "intimacy_level": "guarded",
            "escalation_mode": "controlled",
            "session_awareness": False,
            "close_mode_protection": False,
        }

        if buyer_tier == "LOW_SPENDER":
            profile.update(
                {
                    "emotional_warmth": "warm",
                    "reward_depth": "medium",
                    "continuation_pressure": "soft",
                }
            )

        elif buyer_tier == "ACTIVE_BUYER":
            profile.update(
                {
                    "emotional_warmth": "warmer",
                    "reward_depth": "high",
                    "premium_positioning": True,
                    "continuation_pressure": "moderate",
                    "exclusivity_level": "medium",
                }
            )

        elif buyer_tier == "HIGH_VALUE":
            profile.update(
                {
                    "emotional_warmth": "premium",
                    "reward_depth": "high",
                    "premium_positioning": True,
                    "continuation_pressure": "low",
                    "exclusivity_level": "high",
                    "retention_priority": "high",
                }
            )

        elif buyer_tier == "WHALE":
            profile.update(
                {
                    "emotional_warmth": "exclusive",
                    "reward_depth": "premium",
                    "premium_positioning": True,
                    "continuation_pressure": "minimal",
                    "hard_sell_allowed": False,
                    "exclusivity_level": "very_high",
                    "retention_priority": "critical",
                }
            )

        if event_type == "tip_received":
            profile["reward_depth"] = "enhanced"

        heat_score = (
            runtime_state.get("heat_score")
            or buyer_memory.get("heat_score")
            or 0
        )

        sexual_intensity = (
            runtime_state.get("sexual_intensity")
            or buyer_memory.get("sexual_intensity")
            or 0
        )

        buyer_session_active = runtime_state.get(
            "buyer_session_active",
            False,
        )

        close_mode_active = runtime_state.get(
            "close_mode_active",
            False,
        )

        if buyer_session_active:
            profile["session_awareness"] = True
            profile["continuation_pressure"] = "minimal"

        if close_mode_active:
            profile["close_mode_protection"] = True
            profile["hard_sell_allowed"] = False

        if heat_score >= 80:
            profile["emotional_intensity"] = "very_high"
            profile["escalation_mode"] = "emotionally_locked"

        elif heat_score >= 60:
            profile["emotional_intensity"] = "high"

        elif heat_score >= 40:
            profile["emotional_intensity"] = "elevated"

        if sexual_intensity >= 80:
            profile["intimacy_level"] = "very_intimate"

        elif sexual_intensity >= 60:
            profile["intimacy_level"] = "intimate"

        elif sexual_intensity >= 40:
            profile["intimacy_level"] = "flirty"

        return profile

    def _build_premium_intimacy_routing(
        self,
        buyer_tier: str,
        runtime_state: dict,
        buyer_memory: dict,
        spend_profile: dict,
    ) -> dict:
        premium_sexting_allowed = bool(
            runtime_state.get("premium_sexting_allowed")
            or buyer_memory.get("premium_sexting_allowed")
            or spend_profile.get("premium_sexting_allowed")
        )

        explicit_allowed = bool(
            runtime_state.get("explicit_allowed")
            or buyer_memory.get("explicit_allowed")
            or spend_profile.get("explicit_allowed")
        )

        runtime_mode = (
            runtime_state.get("runtime_mode")
            or buyer_memory.get("runtime_mode")
            or spend_profile.get("runtime_mode")
            or "safe_chat"
        )

        intimacy_tier = (
            runtime_state.get("intimacy_tier")
            or buyer_memory.get("intimacy_tier")
            or spend_profile.get("intimacy_tier")
            or "none"
        )

        route = "safe_chat_only"

        if buyer_tier in ("HIGH_VALUE", "WHALE"):
            route = "premium_retention"

        elif premium_sexting_allowed:
            route = "premium_eligible"

        elif runtime_mode == "premium_gate":
            route = "premium_gate_tease"

        elif buyer_tier in ("LOW_SPENDER", "ACTIVE_BUYER"):
            route = "tease_to_premium"

        return {
            "route": route,
            "runtime_mode": runtime_mode,
            "intimacy_tier": intimacy_tier,
            "premium_sexting_allowed": premium_sexting_allowed,
            "explicit_allowed": explicit_allowed,
            "adult_model_allowed": (
                premium_sexting_allowed
                and explicit_allowed
                and buyer_tier in (
                    "ACTIVE_BUYER",
                    "HIGH_VALUE",
                    "WHALE",
                )
            ),
            "safe_fallback": route == "safe_chat_only",
            "routing_note": (
                "premium_intimacy_sync_only_no_model_call"
            ),
        }

    def _build_whale_retention_profile(
        self,
        buyer_tier: str,
        runtime_state: dict,
        buyer_memory: dict,
        spend_profile: dict,
    ) -> dict:
        total_spend = (
            spend_profile.get("total_spend")
            or buyer_memory.get("total_spend")
            or 0
        )

        purchase_count = (
            spend_profile.get("purchase_count")
            or buyer_memory.get("purchase_count")
            or 0
        )

        emotional_attachment_score = (
            runtime_state.get(
                "emotional_attachment_score"
            )
            or buyer_memory.get(
                "emotional_attachment_score"
            )
            or 0
        )

        whale_mode = buyer_tier == "WHALE"

        retention_mode = "standard"

        if whale_mode:
            retention_mode = "vip_retention"

        elif buyer_tier == "HIGH_VALUE":
            retention_mode = "premium_retention"

        low_pressure_mode = (
            whale_mode
            or emotional_attachment_score >= 70
        )

        return {
            "retention_mode": retention_mode,
            "whale_mode": whale_mode,
            "low_pressure_mode": low_pressure_mode,
            "avoid_hard_sell": True,
            "premium_only_behavior": whale_mode,
            "emotional_attachment_score": (
                emotional_attachment_score
            ),
            "vip_treatment": whale_mode,
            "relationship_priority": (
                emotional_attachment_score >= 60
            ),
            "high_value_buyer": buyer_tier in (
                "HIGH_VALUE",
                "WHALE",
            ),
            "purchase_depth": purchase_count,
            "total_spend": total_spend,
            "retention_note": (
                "retention_intelligence_only"
            ),
        }

    def _build_adaptive_reaction_tone(
        self,
        buyer_tier: str,
        reaction_profile: dict,
        premium_intimacy_routing: dict,
        whale_retention_profile: dict,
    ) -> dict:
        emotional_intensity = (
            reaction_profile.get(
                "emotional_intensity",
                "moderate",
            )
        )

        intimacy_level = (
            reaction_profile.get(
                "intimacy_level",
                "guarded",
            )
        )

        escalation_mode = (
            reaction_profile.get(
                "escalation_mode",
                "controlled",
            )
        )

        whale_mode = (
            whale_retention_profile.get(
                "whale_mode",
                False,
            )
        )

        premium_route = (
            premium_intimacy_routing.get(
                "route",
                "safe_chat_only",
            )
        )

        tone_style = "warm"

        if whale_mode:
            tone_style = "exclusive_emotional"

        elif premium_route == "premium_eligible":
            tone_style = "seductive_premium"

        elif emotional_intensity == "very_high":
            tone_style = "emotionally_attached"

        elif intimacy_level in (
            "intimate",
            "very_intimate",
        ):
            tone_style = "playfully_intimate"

        if escalation_mode == "emotionally_locked":
            tone_style = (
                "emotionally_locked_attachment"
            )

        emoji_intensity = "medium"

        if emotional_intensity == "very_high":
            emoji_intensity = "high"

        elif whale_mode:
            emoji_intensity = "low"

        message_pacing = "balanced"

        if whale_mode:
            message_pacing = "slow_premium"

        elif premium_route == "premium_eligible":
            message_pacing = "seductive"

        elif emotional_intensity == "very_high":
            message_pacing = "emotionally_slow"

        return {
            "tone_style": tone_style,
            "emoji_intensity": emoji_intensity,
            "message_pacing": message_pacing,
            "emotionally_adaptive": True,
            "whale_sensitive_tone": whale_mode,
            "premium_tone": (
                premium_route
                == "premium_eligible"
            ),
            "tone_note": (
                "adaptive_reaction_tone_only"
            ),
        }

    def _build_reaction_timing_intelligence(
        self,
        reaction_profile: dict,
        adaptive_reaction_tone: dict,
        whale_retention_profile: dict,
        premium_intimacy_routing: dict,
    ) -> dict:
        emotional_intensity = (
            reaction_profile.get(
                "emotional_intensity",
                "moderate",
            )
        )

        escalation_mode = (
            reaction_profile.get(
                "escalation_mode",
                "controlled",
            )
        )

        whale_mode = (
            whale_retention_profile.get(
                "whale_mode",
                False,
            )
        )

        premium_route = (
            premium_intimacy_routing.get(
                "route",
                "safe_chat_only",
            )
        )

        tone_style = (
            adaptive_reaction_tone.get(
                "tone_style",
                "warm",
            )
        )

        delay_strategy = "natural"

        if whale_mode:
            delay_strategy = "slow_premium"

        elif (
            escalation_mode
            == "emotionally_locked"
        ):
            delay_strategy = "emotionally_attached"

        elif premium_route == "premium_eligible":
            delay_strategy = "seductive_pacing"

        elif emotional_intensity == "very_high":
            delay_strategy = "slow_emotional"

        minimum_delay_seconds = 30
        maximum_delay_seconds = 180

        if whale_mode:
            minimum_delay_seconds = 180
            maximum_delay_seconds = 600

        elif (
            escalation_mode
            == "emotionally_locked"
        ):
            minimum_delay_seconds = 90
            maximum_delay_seconds = 300

        elif premium_route == "premium_eligible":
            minimum_delay_seconds = 45
            maximum_delay_seconds = 180

        elif tone_style == (
            "emotionally_locked_attachment"
        ):
            minimum_delay_seconds = 120
            maximum_delay_seconds = 360

        return {
            "delay_strategy": delay_strategy,
            "minimum_delay_seconds": (
                minimum_delay_seconds
            ),
            "maximum_delay_seconds": (
                maximum_delay_seconds
            ),
            "emotionally_timed": True,
            "premium_timing": (
                premium_route
                == "premium_eligible"
            ),
            "whale_timing": whale_mode,
            "timing_note": (
                "timing_intelligence_only"
            ),
        }

    def _build_contextual_cta_injection(
        self,
        event_type: str | None,
        buyer_tier: str,
        reaction_profile: dict,
        premium_intimacy_routing: dict,
        whale_retention_profile: dict,
    ) -> dict:
        route = premium_intimacy_routing.get(
            "route",
            "safe_chat_only",
        )

        whale_mode = whale_retention_profile.get(
            "whale_mode",
            False,
        )

        continuation_pressure = reaction_profile.get(
            "continuation_pressure",
            "soft",
        )

        emotional_intensity = reaction_profile.get(
            "emotional_intensity",
            "moderate",
        )

        cta_type = "soft_continue"
        should_include_cta = True

        if whale_mode:
            cta_type = "no_sell_emotional_continuation"
            should_include_cta = False

        elif event_type == "tip_received":
            cta_type = "light_reward_tease"

        elif event_type == "subscription_created":
            cta_type = "subscriber_warmup"

        elif route == "premium_eligible":
            cta_type = "premium_curiosity_hook"

        elif route == "premium_gate_tease":
            cta_type = "premium_gate_tease"

        elif continuation_pressure == "minimal":
            cta_type = "emotional_continuation_only"
            should_include_cta = False

        elif emotional_intensity in (
            "high",
            "very_high",
        ):
            cta_type = "emotional_hook"

        return {
            "cta_type": cta_type,
            "should_include_cta": should_include_cta,
            "cta_pressure": (
                "none"
                if not should_include_cta
                else "soft"
            ),
            "cta_allowed": not whale_mode,
            "whale_safe": whale_mode,
            "contextual_cta_note": (
                "cta_intelligence_only_no_send"
            ),
        }

    def _build_followup_chaining_logic(
        self,
        event_type: str | None,
        buyer_tier: str,
        reaction_profile: dict,
        premium_intimacy_routing: dict,
        whale_retention_profile: dict,
        contextual_cta_injection: dict,
    ) -> dict:
        route = premium_intimacy_routing.get(
            "route",
            "safe_chat_only",
        )

        cta_type = contextual_cta_injection.get(
            "cta_type",
            "soft_continue",
        )

        whale_mode = whale_retention_profile.get(
            "whale_mode",
            False,
        )

        emotional_intensity = reaction_profile.get(
            "emotional_intensity",
            "moderate",
        )

        chain_type = "none"
        should_chain_followup = False
        followup_delay_minutes = None

        if whale_mode:
            chain_type = "whale_retention_followup"
            should_chain_followup = True
            followup_delay_minutes = 180

        elif event_type == "tip_received":
            chain_type = "tip_reward_followup"
            should_chain_followup = True
            followup_delay_minutes = 45

        elif event_type == "subscription_created":
            chain_type = "subscriber_warmup_followup"
            should_chain_followup = True
            followup_delay_minutes = 60

        elif route == "premium_eligible":
            chain_type = "premium_curiosity_followup"
            should_chain_followup = True
            followup_delay_minutes = 90

        elif cta_type == "emotional_hook":
            chain_type = "emotional_continuation_followup"
            should_chain_followup = True
            followup_delay_minutes = 75

        elif emotional_intensity == "very_high":
            chain_type = "soft_emotional_followup"
            should_chain_followup = True
            followup_delay_minutes = 120

        return {
            "chain_type": chain_type,
            "should_chain_followup": (
                should_chain_followup
            ),
            "followup_delay_minutes": (
                followup_delay_minutes
            ),
            "chain_priority": (
                "high"
                if should_chain_followup
                else "none"
            ),
            "queue_write_allowed": False,
            "send_allowed": False,
            "followup_note": (
                "followup_intelligence_only_no_queue_no_send"
            ),
        }

    def _build_post_purchase_emotional_reinforcement(
        self,
        buyer_tier: str,
        reaction_profile: dict,
        whale_retention_profile: dict,
        adaptive_reaction_tone: dict,
    ) -> dict:
        emotional_intensity = (
            reaction_profile.get(
                "emotional_intensity",
                "moderate",
            )
        )

        escalation_mode = (
            reaction_profile.get(
                "escalation_mode",
                "controlled",
            )
        )

        whale_mode = (
            whale_retention_profile.get(
                "whale_mode",
                False,
            )
        )

        premium_tone = (
            adaptive_reaction_tone.get(
                "premium_tone",
                False,
            )
        )

        reinforcement_level = "light"

        if whale_mode:
            reinforcement_level = (
                "deep_retention"
            )

        elif (
            escalation_mode
            == "emotionally_locked"
        ):
            reinforcement_level = (
                "emotionally_attached"
            )

        elif emotional_intensity == (
            "very_high"
        ):
            reinforcement_level = (
                "high_emotional"
            )

        elif premium_tone:
            reinforcement_level = (
                "premium_affection"
            )

        emotional_bonding = (
            reinforcement_level
            != "light"
        )

        attachment_reinforcement = (
            reinforcement_level
            in (
                "emotionally_attached",
                "deep_retention",
            )
        )

        return {
            "reinforcement_level": (
                reinforcement_level
            ),
            "emotional_bonding": (
                emotional_bonding
            ),
            "attachment_reinforcement": (
                attachment_reinforcement
            ),
            "relationship_progression": (
                emotional_bonding
            ),
            "loyalty_strengthening": True,
            "premium_emotional_mode": (
                premium_tone
            ),
            "reinforcement_note": (
                "emotional_reinforcement_only"
            ),
        }

    def _build_realtime_reaction_llm_routing(
        self,
        premium_intimacy_routing: dict,
        adaptive_reaction_tone: dict,
        whale_retention_profile: dict,
        reaction_profile: dict,
    ) -> dict:
        route = premium_intimacy_routing.get(
            "route",
            "safe_chat_only",
        )

        whale_mode = whale_retention_profile.get(
            "whale_mode",
            False,
        )

        tone_style = adaptive_reaction_tone.get(
            "tone_style",
            "warm",
        )

        emotional_intensity = (
            reaction_profile.get(
                "emotional_intensity",
                "moderate",
            )
        )

        llm_provider = "openai"
        prompt_mode = "safe_flirty"

        if whale_mode:
            llm_provider = "grok"
            prompt_mode = (
                "emotional_retention"
            )

        elif route == "premium_eligible":
            llm_provider = "grok"
            prompt_mode = (
                "premium_intimacy"
            )

        elif emotional_intensity in (
            "high",
            "very_high",
        ):
            llm_provider = "grok"
            prompt_mode = (
                "emotionally_attached"
            )

        elif tone_style == (
            "emotionally_locked_attachment"
        ):
            llm_provider = "grok"
            prompt_mode = (
                "emotionally_locked"
            )

        adult_generation_allowed = (
            llm_provider == "grok"
            and route != "safe_chat_only"
        )

        return {
            "llm_provider": llm_provider,
            "prompt_mode": prompt_mode,
            "adult_generation_allowed": (
                adult_generation_allowed
            ),
            "safe_mode": (
                not adult_generation_allowed
            ),
            "execution_ready": False,
            "send_allowed": False,
            "llm_routing_note": (
                "routing_only_no_generation"
            ),
        }

    def _blocked(
        self,
        reason: str,
    ) -> dict:
        return {
            "success": False,
            "blocked": True,
            "reason": reason,
        }