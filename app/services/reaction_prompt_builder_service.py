class ReactionPromptBuilderService:
    """
    3D.19.12 — Reaction Prompt Builder Layer

    Converts reaction intelligence into LLM-ready prompts.

    IMPORTANT:
    This service DOES NOT call OpenAI.
    This service DOES NOT call Grok.
    This service DOES NOT send Fanvue messages.
    """

    def build_reaction_prompt(
        self,
        monetization_event: dict,
        reaction_intelligence: dict,
    ) -> dict:
        if not monetization_event:
            return self._blocked(
                "missing_monetization_event"
            )

        if not reaction_intelligence:
            return self._blocked(
                "missing_reaction_intelligence"
            )

        llm_routing = reaction_intelligence.get(
            "realtime_reaction_llm_routing",
            {},
        )

        premium_routing = reaction_intelligence.get(
            "premium_intimacy_routing",
            {},
        )

        reaction_profile = reaction_intelligence.get(
            "reaction_profile",
            {},
        )

        adaptive_tone = reaction_intelligence.get(
            "adaptive_reaction_tone",
            {},
        )

        cta = reaction_intelligence.get(
            "contextual_cta_injection",
            {},
        )

        followup = reaction_intelligence.get(
            "followup_chaining_logic",
            {},
        )

        whale_profile = reaction_intelligence.get(
            "whale_retention_profile",
            {},
        )

        provider = llm_routing.get(
            "llm_provider",
            "openai",
        )

        prompt_mode = llm_routing.get(
            "prompt_mode",
            "safe_flirty",
        )

        route = premium_routing.get(
            "route",
            "safe_chat_only",
        )

        adult_generation_allowed = bool(
            llm_routing.get(
                "adult_generation_allowed",
                False,
            )
        )

        if route == "safe_chat_only":
            provider = "openai"
            prompt_mode = "safe_emotional"
            adult_generation_allowed = False

        if (
            prompt_mode == "premium_intimacy"
            and not adult_generation_allowed
        ):
            provider = "openai"
            prompt_mode = "safe_emotional"

        generation_style = self._resolve_prompt_style(
            adaptive_tone=adaptive_tone,
            reaction_profile=reaction_profile,
            whale_profile=whale_profile,
        )

        cta_fragment = self._build_cta_fragment(
            cta=cta,
        )

        followup_fragment = (
            self._build_followup_fragment(
                followup=followup,
            )
        )

        if (
            provider == "grok"
            and adult_generation_allowed
        ):
            prompt_payload = (
                self._build_premium_intimacy_prompt(
                    monetization_event=monetization_event,
                    reaction_intelligence=(
                        reaction_intelligence
                    ),
                    generation_style=(
                        generation_style
                    ),
                    cta_fragment=cta_fragment,
                    followup_fragment=(
                        followup_fragment
                    ),
                )
            )
            temperature = 0.9

        else:
            prompt_payload = (
                self._build_safe_emotional_prompt(
                    monetization_event=monetization_event,
                    reaction_intelligence=(
                        reaction_intelligence
                    ),
                    generation_style=(
                        generation_style
                    ),
                    cta_fragment=cta_fragment,
                    followup_fragment=(
                        followup_fragment
                    ),
                )
            )
            temperature = 0.7

        return {
            "success": True,
            "blocked": False,
            "provider": provider,
            "prompt_mode": prompt_mode,
            "temperature": temperature,
            "generation_style": generation_style,
            "system_prompt": (
                prompt_payload["system_prompt"]
            ),
            "user_prompt": (
                prompt_payload["user_prompt"]
            ),
            "cta_included": bool(cta_fragment),
            "followup_attached": bool(
                followup_fragment
            ),
            "adult_generation_allowed": (
                adult_generation_allowed
            ),
            "send_allowed": False,
            "generation_allowed": False,
            "prompt_builder_note": (
                "prompt_only_no_generation_no_send"
            ),
        }

    def _build_safe_emotional_prompt(
        self,
        monetization_event: dict,
        reaction_intelligence: dict,
        generation_style: str,
        cta_fragment: str,
        followup_fragment: str,
    ) -> dict:
        buyer_tier = reaction_intelligence.get(
            "buyer_tier",
            "NON_BUYER",
        )

        event_type = monetization_event.get(
            "event_type",
            "unknown",
        )

        system_prompt = """
You are writing a short private creator reply.

Rules:
- Do not mention AI.
- Do not mention automation.
- Keep it natural, warm, and personal.
- Do not be explicit.
- Do not use crude language.
- Do not hard sell.
- Do not include hashtags.
"""

        user_prompt = f"""
Event type: {event_type}
Buyer tier: {buyer_tier}
Generation style: {generation_style}

Write one short, warm post-event reaction message.

CTA guidance:
{cta_fragment}

Follow-up guidance:
{followup_fragment}
"""

        return {
            "system_prompt": system_prompt.strip(),
            "user_prompt": user_prompt.strip(),
        }

    def _build_premium_intimacy_prompt(
        self,
        monetization_event: dict,
        reaction_intelligence: dict,
        generation_style: str,
        cta_fragment: str,
        followup_fragment: str,
    ) -> dict:
        buyer_tier = reaction_intelligence.get(
            "buyer_tier",
            "ACTIVE_BUYER",
        )

        event_type = monetization_event.get(
            "event_type",
            "unknown",
        )

        reinforcement = reaction_intelligence.get(
            "post_purchase_emotional_reinforcement",
            {},
        )

        reinforcement_level = reinforcement.get(
            "reinforcement_level",
            "premium_affection",
        )

        system_prompt = """
You are writing a private premium creator reply.

Rules:
- Do not mention AI.
- Do not mention automation.
- Keep it short and emotionally charged.
- Make it seductive, intimate, and premium-feeling.
- Avoid crude or generic wording.
- Do not include hashtags.
- Do not pressure the buyer.
- Do not imply anything was sent automatically.
"""

        user_prompt = f"""
Event type: {event_type}
Buyer tier: {buyer_tier}
Generation style: {generation_style}
Reinforcement level: {reinforcement_level}

Write one premium post-purchase reaction message.

CTA guidance:
{cta_fragment}

Follow-up guidance:
{followup_fragment}
"""

        return {
            "system_prompt": system_prompt.strip(),
            "user_prompt": user_prompt.strip(),
        }

    def _build_cta_fragment(
        self,
        cta: dict,
    ) -> str:
        if not cta:
            return ""

        if not cta.get("should_include_cta"):
            return (
                "Do not include a CTA. Keep the response "
                "emotional and relationship-focused."
            )

        cta_type = cta.get(
            "cta_type",
            "soft_continue",
        )

        if cta_type == "premium_curiosity_hook":
            return (
                "Include a very soft curiosity hook for "
                "continued premium interest."
            )

        if cta_type == "light_reward_tease":
            return (
                "Include a light reward-style tease, but "
                "do not hard sell."
            )

        if cta_type == "subscriber_warmup":
            return (
                "Welcome them warmly and make them feel "
                "noticed without selling."
            )

        return (
            "Use a soft emotional continuation, not a hard CTA."
        )

    def _build_followup_fragment(
        self,
        followup: dict,
    ) -> str:
        if not followup:
            return ""

        if not followup.get("should_chain_followup"):
            return (
                "No follow-up should be implied."
            )

        chain_type = followup.get(
            "chain_type",
            "soft_emotional_followup",
        )

        delay = followup.get(
            "followup_delay_minutes",
        )

        return (
            f"Tone should support a future {chain_type} "
            f"around {delay} minutes later, but do not "
            "mention timing."
        )

    def _resolve_prompt_style(
        self,
        adaptive_tone: dict,
        reaction_profile: dict,
        whale_profile: dict,
    ) -> str:
        if whale_profile.get("whale_mode"):
            return "exclusive_whale_retention"

        tone_style = adaptive_tone.get(
            "tone_style",
            "warm",
        )

        escalation_mode = reaction_profile.get(
            "escalation_mode",
            "controlled",
        )

        if escalation_mode == "emotionally_locked":
            return "emotionally_locked_attachment"

        return tone_style

    def _blocked(
        self,
        reason: str,
    ) -> dict:
        return {
            "success": False,
            "blocked": True,
            "reason": reason,
        }