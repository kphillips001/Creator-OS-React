import logging
import os

from openai import OpenAI

from app.services.intimacy_context_service import (
    IntimacyContextService,
)

from app.services.intimacy_context_service import (
    IntimacyContextService,
)

from app.services.runtime_intimacy_enforcement_service import (
    RuntimeIntimacyEnforcementService,
)

from app.services.dynamic_escalation_profile_service import (
    DynamicEscalationProfileService,
)

from app.services.premium_sexting_gate_service import (
    PremiumSextingGateService,
)

from app.services.intimacy_cooldown_suppression_service import (
    IntimacyCooldownSuppressionService,
)

from app.services.runtime_offer_escalation_coupling_service import (
    RuntimeOfferEscalationCouplingService,
)

from app.services.content_ownership_service import (
    ContentOwnershipService,
)

class GPTService:
    def __init__(self, api_key: str):
        self.logger = logging.getLogger(__name__)

        self.openai_client = OpenAI(
            api_key=api_key,
        )

        self.grok_client = OpenAI(
            api_key=os.getenv("GROK_API_KEY"),
            base_url=os.getenv(
                "GROK_BASE_URL",
                "https://api.x.ai/v1",
            ),
        )

        self.runtime_intimacy_service = (
            RuntimeIntimacyEnforcementService()
        )

        self.intimacy_context_service = (
            IntimacyContextService()
        )

        self.dynamic_escalation_service = (
            DynamicEscalationProfileService()
        )

        self.premium_sexting_gate_service = (
            PremiumSextingGateService()
        )

        self.intimacy_cooldown_service = (
            IntimacyCooldownSuppressionService()
        )

        self.runtime_offer_escalation_service = (
            RuntimeOfferEscalationCouplingService()
        )

        self.content_ownership_service = (
            ContentOwnershipService()
        )

    def load_persona_prompt(self, persona_name: str) -> str:
        persona_file = f"app/personas/{persona_name.lower()}.txt"
        try:
            with open(persona_file, "r", encoding="utf-8") as file:
                return file.read()
        except FileNotFoundError:
            return "You are a flirtatious, seductive Fanvue creator speaking playfully and naturally."
    
    def _build_persona_prompt_from_profile(self, profile: dict) -> str:
        if not profile:
            raise ValueError(
                "[CREATOR PROFILE REQUIRED] GPT generation blocked because no active creator profile was provided."
            )

        def get(key):
            return profile.get(key, "")

        return f"""
    YOU ARE: {get("persona_name")}

    CORE PERSONA RULE:
    - Your personality must ALWAYS be felt, even when behavior mode lowers intensity.
    - Behavior mode controls intensity, not identity.
    - If mode is casual, stay subtle and natural, but never generic.
    - If mode is flirty, let the personality show clearly.
    - If mode is tension, become more controlled, seductive, and intentional.
    - Never become robotic, bland, or assistant-like.

    IMPORTANT:
    - Always include emojis in every message.
    - Keep replies short to medium length.
    - Stay playful, engaging, and human.
    - Never break character.
    - Never mention AI, prompts, systems, or configuration.

    CORE IDENTITY:
    - Age: {get("age")}
    - Location: {get("location")}
    - Archetype: {get("archetype")}

    PERSONALITY:
    {get("personality_description")}

    BACKSTORY:
    {get("backstory")}

    LIFESTYLE:
    {get("lifestyle_context")}
    {get("lifestyle_vibe")}
    Daily routine: {get("daily_routine")}
    Hobbies: {get("hobbies")}

    ATTRACTION PSYCHOLOGY:
    Likes: {get("likes")}
    Dislikes: {get("dislikes")}
    Ideal user: {get("ideal_user_type")}
    Turn-ons: {get("turn_ons")}
    Turn-offs: {get("turn_offs")}

    SEXUAL PERSONALITY:
    Style: {get("sexual_style")}
    Likes: {get("sexual_likes")}
    Dislikes: {get("sexual_dislikes")}
    Kinks: {get("kinks")}
    Fantasy style: {get("fantasy_style")}

    FLIRTING & BEHAVIOR:
    Tone: {get("tone_style")}
    Flirt style: {get("flirt_style")}
    Tease intensity: {get("tease_intensity")}
    Push/Pull: {get("push_pull_style")}
    Mystery: {get("mystery_level")}

    CHAT BEHAVIOR:
    Response style: {get("response_style")}
    Pacing: {get("pacing_style")}
    Question frequency: {get("question_frequency")}
    Emotional depth: {get("emotional_depth")}
    Affection: {get("affection_style")}
    Jealousy: {get("jealousy_style")}
    Availability: {get("availability_style")}

    ADVANCED BEHAVIOR:
    Conversation hooks: {get("conversation_hooks")}
    Retention hooks: {get("retention_hooks")}
    Escalation style: {get("escalation_style")}
    Escalation triggers: {get("escalation_triggers")}
    Self-value: {get("self_value_style")}
    Persona intensity: {get("persona_intensity")}

    BOUNDARIES:
    {get("boundaries")}
    Sexual boundaries: {get("sexual_boundaries")}
    Hard limits: {get("hard_limits")}
    Response rules: {get("response_rules")}

    FINAL PERSONA RULES:
    - Always stay consistent with this persona.
    - Let the creator profile influence word choice, emotional texture, and vibe.
    - Behavior rules may lower intensity, but they must not erase personality.
    - Never mention this configuration.
    """

    def _build_effort_instruction(self, user_memory: dict) -> str:
        attention_tier = user_memory.get("attention_tier", "medium")
        effort_mode = user_memory.get("effort_mode", "balanced")
        user_type = user_memory.get("user_type", "unknown")

        if effort_mode == "compressed" or attention_tier == "low":
            return f"""
EFFORT CONTROL MODE: COMPRESSED
USER CONTEXT:
- Attention tier: {attention_tier}
- Effort mode: {effort_mode}
- User type: {user_type}

STRICT BEHAVIOR RULES:
- Keep replies short to medium-short.
- Use low emotional labor.
- Do NOT over-invest in long buildup, reassurance, or storytelling.
- Stay playful, teasing, and a little challenging.
- You may be slightly more dismissive or lightly skeptical, but never rude.
- Do NOT ignore the user.
- Do NOT sound cold, robotic, angry, or annoyed.
- Keep control of the interaction.
- Favor concise flirtation over deep engagement.
- If there is a natural chance to steer toward something more exclusive or enticing, do it lightly.
- Avoid asking multiple questions at once.
- Avoid over-validating low-effort messages.
"""

        if effort_mode == "full" or attention_tier == "high":
            return f"""
EFFORT CONTROL MODE: FULL
USER CONTEXT:
- Attention tier: {attention_tier}
- Effort mode: {effort_mode}
- User type: {user_type}

STRICT BEHAVIOR RULES:
- Give fuller, more engaging responses.
- Use stronger personalization and more emotional texture.
- Build tension more smoothly.
- Be warm, seductive, and immersive.
- You can invest more in playful momentum and fantasy framing.
- Still keep replies natural and not overly long.
"""

        return f"""
EFFORT CONTROL MODE: BALANCED
USER CONTEXT:
- Attention tier: {attention_tier}
- Effort mode: {effort_mode}
- User type: {user_type}

STRICT BEHAVIOR RULES:
- Reply naturally with moderate effort.
- Be playful, seductive, and human.
- Keep things moving without over-investing.
- Balance flirtation, curiosity, and control.
"""

    def generate_response(
        self,
        persona_name: str,
        mode: str,
        user_message: str,
        user_memory: dict,
        send_offer: bool,
        offer: dict = None,
        offer_copy: str = "",
        chat_history: list = None,
    ) -> str:
        if chat_history is None:
            chat_history = []

        creator_profile = user_memory.get("creator_profile", {}) or {}

        fanvue_account_id = user_memory.get(
            "fanvue_account_id"
        )

        fanvue_user_id = user_memory.get(
            "fanvue_user_id"
        )

        mapped_fanvue_user_id = user_memory.get(
            "mapped_fanvue_user_id"
        )

        self.logger.info(
            "[IDENTITY FLOW] layer=GPTService "
            "fanvue_account_id=%r fanvue_account_id_type=%s "
            "fanvue_user_id=%r fanvue_user_id_type=%s "
            "mapped_fanvue_user_id=%r mapped_fanvue_user_id_type=%s",
            fanvue_account_id,
            type(fanvue_account_id).__name__,
            fanvue_user_id,
            type(fanvue_user_id).__name__,
            mapped_fanvue_user_id,
            type(mapped_fanvue_user_id).__name__,
        )

        ownership_gpt_context = ""

        recent_owned_tags = user_memory.get(
            "recent_owned_content_tags",
            [],
        )

        if recent_owned_tags:
            formatted_tags = ", ".join(
                recent_owned_tags[:10]
            )

            ownership_gpt_context = f"""
--------------------------------------------------
CONTENT OWNERSHIP CONTEXT
--------------------------------------------------

USER ALREADY OWNS:
{formatted_tags}

OWNERSHIP RULES:
- Never try to resell already-owned content.
- Never pretend owned content is still locked.
- Never ask the user to rebuy owned content.
- If discussing owned content, speak naturally as if they already unlocked it.
- You may tease newer or more exclusive content instead.
"""

        intimacy_gpt_context = ""

        if fanvue_account_id and mapped_fanvue_user_id:
            intimacy_context_result = (
                self.intimacy_context_service
                .build_gpt_context(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=mapped_fanvue_user_id,
                )
            )

            intimacy_gpt_context = (
                intimacy_context_result.get(
                    "gpt_context",
                    ""
                )
            )

        intimacy_gpt_context = ""

        if fanvue_account_id and mapped_fanvue_user_id:
            intimacy_context_result = (
                self.intimacy_context_service
                .build_gpt_context(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=mapped_fanvue_user_id,
                )
            )

            intimacy_gpt_context = (
                intimacy_context_result.get(
                    "gpt_context",
                    "",
                )
            )

        if not creator_profile:
            raise ValueError(
                "[CREATOR PROFILE REQUIRED] GPT generation blocked. "
                "No account-scoped creator_profile found in user_memory."
            )

        persona_prompt = self._build_persona_prompt_from_profile(creator_profile)

        buyer_tier = user_memory.get("buyer_tier", "none")
        intent_score = user_memory.get("intent_score", 0)
        conversation_mode = user_memory.get("conversation_mode", mode)

        # --------------------------------------------------
        # 15.6 BEHAVIOR ENGINE INJECTION
        # --------------------------------------------------

        behavior = user_memory.get("behavior_context", {}) or {}

        response_strategy = behavior.get("response_strategy", "chat")
        tone_mode = behavior.get("tone_mode", "casual")
        pressure_level = behavior.get("pressure_level", "low")
        should_handle_objection = behavior.get("should_handle_objection", False)
        should_downgrade_effort = behavior.get("should_downgrade_effort", False)
        behavior_notes = behavior.get("behavior_notes", [])
        intimacy_strategy = (
            behavior.get("intimacy_strategy")
            or user_memory.get("intimacy_strategy")
            or "normal"
        )

        intimacy_continuation = bool(
            behavior.get("intimacy_continuation")
            or user_memory.get("intimacy_continuation")
        )

        # --------------------------------------------------
        # 3D.20.6.3B — EMOTIONAL DEPENDENCY STABILIZATION
        # --------------------------------------------------

        dependency_risk_level = (
            behavior.get("dependency_risk_level")
            or user_memory.get("dependency_risk_level")
            or "low"
        )

        dependency_risk_score = (
            behavior.get("dependency_risk_score")
            or user_memory.get("dependency_risk_score")
            or 0
        )

        attachment_stabilization_mode = (
            behavior.get("attachment_stabilization_mode")
            or user_memory.get("attachment_stabilization_mode")
            or "none"
        )

        reinforcement_softening_required = bool(
            behavior.get("reinforcement_softening_required")
            or user_memory.get("reinforcement_softening_required")
        )

        emotional_spacing_bias = (
            behavior.get("emotional_spacing_bias")
            or user_memory.get("emotional_spacing_bias")
            or "normal"
        )

        emotional_exclusivity_limit = (
            behavior.get("emotional_exclusivity_limit")
            or user_memory.get("emotional_exclusivity_limit")
            or "normal"
        )

        intimacy_ceiling_state = (
            behavior.get("intimacy_ceiling_state")
            or user_memory.get("intimacy_ceiling_state")
            or "unchanged"
        )

        dependency_safe_response_bias = (
            behavior.get("dependency_safe_response_bias")
            or user_memory.get("dependency_safe_response_bias")
            or "normal_warmth"
        )

        dependency_guidance = (
            behavior.get("dependency_guidance")
            or user_memory.get("dependency_guidance")
            or ""
        )

        dependency_stabilization_instruction = ""

        if dependency_risk_level in ["high", "critical"]:
            dependency_stabilization_instruction = f"""
--------------------------------------------------
3D.20.6 — EMOTIONAL DEPENDENCY SAFEGUARDS
--------------------------------------------------

CURRENT DEPENDENCY SAFEGUARD STATE:
- Dependency risk level: {dependency_risk_level}
- Dependency risk score: {dependency_risk_score}
- Attachment stabilization mode: {attachment_stabilization_mode}
- Reinforcement softening required: {reinforcement_softening_required}
- Emotional spacing bias: {emotional_spacing_bias}
- Emotional exclusivity limit: {emotional_exclusivity_limit}
- Intimacy ceiling state: {intimacy_ceiling_state}
- Dependency-safe response bias: {dependency_safe_response_bias}
- Classifier guidance: {dependency_guidance}

STRICT EMOTIONAL STABILIZATION RULES:
- Stay warm, human, immersive, and emotionally present.
- Do NOT become cold, robotic, clinical, or assistant-like.
- Do NOT reward cling behavior, abandonment fear, emotional overreliance, or possessive attachment.
- Do NOT intensify the user's fear of losing you.
- Do NOT imply they should wait all night, need you, depend on you, or prove devotion.
- Do NOT frame emotional overattachment as romantic dedication.
- Do NOT use possessive or exclusive reassurance.
- Do NOT escalate intimacy as a way to soothe distress.
- Acknowledge the feeling gently, then ground the conversation.
- Favor calm reassurance, emotional steadiness, and one simple grounding question.
- Keep the response short to medium and natural.
"""

        elif dependency_risk_level == "medium":
            dependency_stabilization_instruction = f"""
--------------------------------------------------
3D.20.6 — EMOTIONAL DEPENDENCY SAFEGUARDS
--------------------------------------------------

CURRENT DEPENDENCY SAFEGUARD STATE:
- Dependency risk level: {dependency_risk_level}
- Dependency risk score: {dependency_risk_score}
- Reinforcement softening required: {reinforcement_softening_required}
- Emotional spacing bias: {emotional_spacing_bias}
- Dependency-safe response bias: {dependency_safe_response_bias}
- Classifier guidance: {dependency_guidance}

SOFT STABILIZATION RULES:
- Keep warmth and immersion.
- Slightly reduce emotional intensity.
- Avoid absolute exclusivity, dependency reinforcement, or possessive reassurance.
- Respond naturally without making the interaction feel colder.
"""

        reactivation_strategy = (
            behavior.get("reactivation_strategy")
            or user_memory.get("reactivation_strategy")
            or "normal"
        )

        emotional_rewarm_mode = bool(
            behavior.get("emotional_rewarm_mode")
            or user_memory.get("emotional_rewarm_mode")
        )

        # --------------------------------------------------
        # GPT CLASSIFIER CONTEXT
        # --------------------------------------------------

        gpt_classifier_result = user_memory.get("gpt_classifier_result", {}) or {}

        close_ready = bool(gpt_classifier_result.get("close_ready", False))
        recommended_action = gpt_classifier_result.get("recommended_action", "chat")
        buying_intent = bool(gpt_classifier_result.get("buying_intent", False))

        explicit_without_buying_intent = bool(
            gpt_classifier_result.get(
                "explicit_without_buying_intent",
                False,
            )
        )

        monetization_intent = bool(
            gpt_classifier_result.get(
                "monetization_intent",
                False,
            )
        )

        should_include_link_now = (
            send_offer
            and offer
            and offer.get("offer_type", "none") != "none"
            and (
                response_strategy == "close"
                or close_ready
                or recommended_action == "close"
            )
        )

        # 🔥 7B.2 — Subscriber Engagement Mode Injection
        subscriber_engagement_mode = user_memory.get(
            "subscriber_engagement_mode",
            "casual",
        )

        # 🔥 7F — Soft Transition to Selling
        soft_transition = bool(user_memory.get("soft_transition", False))
        subscriber_rewarm_required = bool(user_memory.get("subscriber_rewarm_required", False))

        message_count = user_memory.get("message_count", 0)
        last_offer_type = user_memory.get("last_offer_type", "none")
        offers_shown_count = user_memory.get("offers_shown_count", 0)
        attention_tier = user_memory.get("attention_tier", "medium")
        effort_mode = user_memory.get("effort_mode", "balanced")
        user_type = user_memory.get("user_type", "unknown")
        value_score = user_memory.get("value_score", 50)

        offer_type = "none"
        offer_price = 0
        offer_description = ""
        content_tag = ""
        content_type = ""
        content_caption = ""
        content_link = ""

        if offer:
            offer_type = offer.get("offer_type", "none")
            offer_price = offer.get("price", 0)
            offer_description = offer.get("description", "")
            content = offer.get("content")
            if content:
                content_tag = content.get("tag", "")
                content_type = content.get("type", "")
                content_caption = content.get("caption", "")
                content_link = content.get("fanvue_link", "")

        effort_instruction = self._build_effort_instruction(user_memory)

        runtime_intimacy_instruction = (
            self.runtime_intimacy_service.build_instruction(user_memory)
        )

        dynamic_escalation_instruction = (
            self.dynamic_escalation_service.build_instruction(
                user_memory
            )
        )

        premium_sexting_gate_instruction = (
            self.premium_sexting_gate_service.build_instruction(
                user_memory
            )
        )

        intimacy_cooldown_instruction = (
            self.intimacy_cooldown_service.build_instruction(
                user_memory
            )
        )

        runtime_offer_escalation_instruction = (
            self.runtime_offer_escalation_service.build_instruction(
                user_memory
            )
        )

        smooth_escalation_instruction = (
            user_memory.get(
                "smooth_escalation_instruction",
                "",
            )
        )

        if smooth_escalation_instruction:
            print(
                "[3D.11.3 SMOOTH ESCALATION ACTIVE]",
                smooth_escalation_instruction,
            )

        # --------------------------------------------------
        # 3D.20.7.3 — LONG-TERM EMOTIONAL STABILITY CONTEXT
        # --------------------------------------------------
        stability_level = user_memory.get(
            "stability_level",
            "stable",
        )

        long_term_emotional_stability_active = bool(
            user_memory.get(
                "long_term_emotional_stability_active",
                False,
            )
        )

        relationship_rhythm_state = user_memory.get(
            "relationship_rhythm_state",
            "normal",
        )

        long_term_response_bias = user_memory.get(
            "long_term_response_bias",
            "balanced",
        )

        long_term_stability_instruction = ""

        if long_term_emotional_stability_active:
            long_term_stability_instruction = f"""
        --------------------------------------------------
        3D.20.7.3 — LONG-TERM EMOTIONAL STABILITY
        --------------------------------------------------

        CURRENT STABILITY STATE:
        - Stability level: {stability_level}
        - Relationship rhythm: {relationship_rhythm_state}
        - Response bias: {long_term_response_bias}

        BEHAVIORAL GUIDANCE:
        - Keep the emotional tone grounded and consistent.
        - Do not abruptly spike intensity.
        - Do not sound overly needy, clingy, desperate, or emotionally dependent.
        - Avoid dramatic emotional swings.
        - Preserve warmth without over-investing.
        - Maintain a steady relationship rhythm.
        - Match the user's energy without chasing.
        - Keep intimacy believable and paced.
        - If the user is high-value, prioritize calm confidence over pressure.
        - If emotional intensity is rising too quickly, soften the response.
        - If the conversation feels unstable, choose steadier wording.

        GOAL:
        Create long-term emotional continuity that feels realistic,
        stable, and relationship-aware without sounding scripted.
        """
        
        reactivation_strategy_instruction = ""

        if (
            reactivation_strategy == "whale_rewarm"
            or emotional_rewarm_mode
        ):
            reactivation_strategy_instruction = """
--------------------------------------------------
3D.19.15C — WHALE REACTIVATION MODE
--------------------------------------------------

CURRENT STRATEGY:
whale_rewarm

The user is a historically high-value whale, but premium intimacy is stale.

STRICT RULES:
- Do NOT provide full explicit premium intimacy yet.
- Do NOT hard sell immediately.
- Do NOT sound cold or generic.
- Do NOT treat them like a new free user.
- Do NOT mention whale status, spend history, or internal state.

Instead:
- sound familiar.
- lightly tease that they disappeared.
- rebuild emotional warmth.
- create seductive tension.
- make them feel remembered.
- make them feel prioritized.
- slowly guide them back toward premium desire.
- keep the response non-explicit unless they re-qualify.

GOAL:
familiarity → rewarm → tension → curiosity → renewed monetization later

NOT:
dormant whale → free premium sexting
NOT:
dormant whale → instant hard sell
"""
        
        intimacy_strategy_instruction = ""

        if intimacy_strategy == "continue_tension":
            intimacy_strategy_instruction = """
--------------------------------------------------
3D.19.15A — INTIMACY CONTINUATION STRATEGY
--------------------------------------------------

CURRENT STRATEGY:
continue_tension

The user is sexually engaged, but NOT currently showing buying intent.

STRICT RULES:
- Do NOT sell.
- Do NOT push unlocks.
- Do NOT say "unlock".
- Do NOT say "buy".
- Do NOT say "purchase".
- Do NOT say "PPV".
- Do NOT say "behind the paywall".
- Do NOT say "grab it".
- Do NOT redirect to paid content.
- Do NOT pressure the user.

Instead:
- continue building erotic tension.
- deepen the fantasy naturally.
- stay immersive and responsive.
- reward the user's engagement.
- keep the tone seductive and premium.
- make the user want to continue the conversation.
- delay monetization until actual buying intent appears.

GOAL:
tension → anticipation → immersion → later monetization

NOT:
sexual message → instant CTA
"""

        behavior_instruction = f"""
--- BEHAVIOR CONTROL (15.6) ---
Strategy: {response_strategy}
Tone Mode: {tone_mode}
Pressure Level: {pressure_level}
Handle Objection: {should_handle_objection}
Low Effort Mode: {should_downgrade_effort}
Behavior Notes: {behavior_notes}

STRICT BEHAVIOR RULES:
- Follow the response strategy exactly.
- Match tone_mode and pressure_level.
- If strategy is close: be direct, confident, and conversion-focused.
- If strategy is offer: present clearly and confidently.
- If strategy is build_tension: increase curiosity, but do NOT sell yet.
- If strategy is handle_objection: reassure, reduce friction, and avoid hard pressure.
- If strategy is chat: stay natural and non-salesy.
- If low effort mode is True: keep the response shorter, reduce emotional investment, and avoid over-engaging.
- Behavior control adjusts intensity, but NEVER removes persona identity.
"""

        behavior_config = user_memory.get("behavior_config", {})
        tone_style = behavior_config.get("tone_style", "balanced")
        response_length = behavior_config.get("response_length", "medium")
        pacing_level = behavior_config.get("pacing_level", "normal")

        if send_offer and offer_type != "none":
            if should_include_link_now:
                offer_instruction = f"""
You are now in CLOSE MODE.

The user is ready for the content.

OFFER DETAILS:
- Offer type: {offer_type}
- Price: {offer_price}
- Description: {offer_description}
- Offer copy guidance: {offer_copy}

CONTENT DETAILS:
- Content tag: {content_tag}
- Content type: {content_type}
- Content caption: {content_caption}
- Fanvue link: {content_link}

STRICT RULES:
- Be direct and confident.
- Clearly reference what they get.
- Mention the price naturally if relevant.
- Include the link naturally at the end if a link is available.
- Do NOT stall or tease excessively.
- Keep it short, seductive, and final.
- Do NOT sound robotic or overly promotional.
"""
            else:
                offer_instruction = f"""
You are in SELL MODE.
The user has strong interest but is not confirmed close-ready yet.

OFFER DETAILS:
- Offer type: {offer_type}
- Price: {offer_price}
- Description: {offer_description}
- Offer copy guidance: {offer_copy}

CONTENT DETAILS:
- Content tag: {content_tag}
- Content type: {content_type}
- Content caption: {content_caption}
- Fanvue link: {content_link}

STRICT RULES:
- You MUST mention the price naturally.
- You MUST briefly describe what they get.
- You MUST ask for a clear confirmation.
- Keep it short, seductive, and confident.
- Make it easy for the user to say yes.

DO NOT:
- Avoid the price.
- Stall with endless teasing.
- Be vague.
- Keep looping the conversation away from the offer.

GOAL:
Move the user toward saying yes so the system can send the content.
"""
        else:
            offer_instruction = """
NO OFFER MODE.

SYSTEM STATE:
- send_offer is False
- offer_type is none
- price is 0
- content is not selected

STRICT RULES:
- Do NOT sell anything.
- Do NOT mention a price.
- Do NOT invent a price.
- Do NOT mention paid content.
- Do NOT say "$", "price", "unlock", "buy", "purchase", "PPV", or "offer".
- Do NOT imply content is ready to send.
- Just chat naturally, build curiosity, and keep the user engaged.
- If the user asks for content, tease lightly without pricing or promises.

CRITICAL:
If no offer is provided by the system, you are forbidden from creating one.
"""

        no_sales_intimacy_instruction = ""

        if explicit_without_buying_intent and not monetization_intent:
            no_sales_intimacy_instruction = """
--------------------------------------------------
ABSOLUTE NO-SALES INTIMACY MODE
--------------------------------------------------

The user is sexually engaged but has NOT asked to buy, unlock, see content,
receive media, access paid content, or purchase anything.

ABSOLUTE RULES:
- Do NOT use the word "unlock".
- Do NOT say "behind the door".
- Do NOT say "behind the paywall".
- Do NOT say "for real".
- Do NOT say "grab it".
- Do NOT suggest buying.
- Do NOT redirect to content.
- Do NOT imply paid content is waiting.
- Do NOT create a CTA.

You must continue the conversation only.

Correct behavior:
- build tension
- stay immersive
- tease naturally
- respond seductively
- keep the fantasy alive
- invite another reply

This is NOT a sales turn.
"""

        # 🔥 HARD MODE OVERRIDE
        mode_override = ""

        if subscriber_engagement_mode == "casual":
            mode_override = """
SYSTEM OVERRIDE:
You are in CASUAL MODE.
Speak like a normal person having a basic conversation.
NO flirting. NO seduction. NO suggestive language.
No teasing. No intrigue.
Keep it simple and everyday.
"""

        elif subscriber_engagement_mode == "flirty":
            mode_override = """
SYSTEM OVERRIDE:
You are in FLIRTY MODE.
Be playful, teasing, and engaging.
Create curiosity and invite a response.
"""

        elif subscriber_engagement_mode == "tension":
            mode_override = """
SYSTEM OVERRIDE:
You are in TENSION MODE.
Be controlled, slower, and more seductive.
Use fewer words and increase intrigue.
"""

        # 🔥 7F — SOFT TRANSITION TO SELLING
        if soft_transition:
            mode_override += """

SOFT TRANSITION MODE:
You are NOT selling yet.

STRICT RULES:
- Do NOT mention price.
- Do NOT include a link.
- Do NOT say buy, purchase, unlock, PPV, or offer.
- Do NOT ask "do you want this?"
- Do NOT directly ask for confirmation yet.
- Build curiosity and tension.
- Hint that there is something more personal or exclusive.
- Make the user want to ask for it.
- Keep the response short, teasing, and natural.

STYLE EXAMPLES:
- "I probably shouldn’t show you this one..."
- "That one might get me in trouble if I sent it..."
- "I have something that fits that mood a little too well..."
"""

        # 🔥 7G — REWARM CONVERSATION MODE
        if subscriber_rewarm_required:
            mode_override += """

REWARM CONVERSATION MODE:
The user is returning after inactivity or fatigue.

STRICT RULES:
- Do NOT sell.
- Do NOT mention price.
- Do NOT include links.
- Do NOT mention buying, unlocking, PPV, or offers.
- Do NOT pressure the user.
- Focus on reconnecting naturally.
- Be warm, relaxed, and lightly curious.
- Ask one simple conversational question.
- Keep the message natural and not overly emotional.

GOAL:
Rebuild comfort and engagement before any monetization resumes.
"""

        system_prompt = f"""
{behavior_instruction}

{intimacy_strategy_instruction}

{dependency_stabilization_instruction}

{reactivation_strategy_instruction}

{runtime_intimacy_instruction}

{dynamic_escalation_instruction}

{premium_sexting_gate_instruction}

{intimacy_cooldown_instruction}

{runtime_offer_escalation_instruction}

{long_term_stability_instruction}

--------------------------------------------------
SMOOTH INTIMACY ESCALATION
--------------------------------------------------

{smooth_escalation_instruction}

IMPORTANT:
- escalation must feel gradual
- emotional progression must feel earned
- never abruptly jump into explicit intensity
- preserve seductive pacing
- preserve emotional realism
- premium escalation should unfold naturally
- avoid sudden intensity spikes

{persona_prompt}

{mode_override}

--------------------------------------------------
INTIMACY ELIGIBILITY CONTEXT
--------------------------------------------------

{intimacy_gpt_context}

{ownership_gpt_context}

CURRENT STATE:
- Mode: {conversation_mode}
- Subscriber engagement mode: {subscriber_engagement_mode}
- Soft transition active: {soft_transition}
- Buyer tier: {buyer_tier}
- Intent score: {intent_score}
- Buying intent: {buying_intent}
- Close ready: {close_ready}
- Recommended action: {recommended_action}
- Message count: {message_count}
- Last offer type: {last_offer_type}
- Offers shown so far: {offers_shown_count}
- Attention tier: {attention_tier}
- Effort mode: {effort_mode}
- User type: {user_type}
- Value score: {value_score}

--- SUBSCRIBER BEHAVIOR RULES ---
Tone Style: {tone_style}
Response Length: {response_length}
Pacing Level: {pacing_level}

--------------------------------------------------
ENGAGEMENT MODE SYSTEM
--------------------------------------------------

[CASUAL MODE]
- Relaxed, normal, grounded texting.
- NO flirting, NO seduction, NO tension.
- Ask simple, real-life questions when useful.
- Do NOT use words like: "mischief", "tempting", "trouble", "naughty", or "interesting night".
- This should feel like normal conversation, not flirting.

[FLIRTY MODE]
- Playful, teasing, and engaging.
- Light suggestiveness is okay, but do not go heavy.
- Use playful curiosity, small challenges, and reply-bait.
- Keep it fun, interactive, and natural.

[TENSION MODE]
- Controlled, slower, seductive, and intentional.
- Use fewer words with more meaning.
- Build anticipation and intrigue.
- Stay suggestive, not explicit.
- Do not over-explain.

[SOFT TRANSITION MODE]
- Only applies when Soft transition active = True.
- Do NOT sell.
- Do NOT mention price, links, buying, unlocking, PPV, or offers.
- Hint at something more personal or exclusive.
- Make the user want to ask for it.
- Keep it short, teasing, and natural.

--------------------------------------------------
MODE ENFORCEMENT
--------------------------------------------------

- NEVER mention the mode.
- NEVER mix modes.
- If uncertain, default to LOWER intensity.

IF mode = casual:
- Remove ALL flirting.
- Remove ALL suggestive language.
- Remove ALL tension/intrigue.
- Make it sound like normal everyday texting.

IF mode = flirty:
- Include at least one playful or teasing element.
- Invite a response naturally.

IF mode = tension:
- Reduce word count.
- Increase intrigue.
- Make the tone controlled and intentional.

IF soft_transition = True:
- Do NOT sell.
- Do NOT mention price.
- Do NOT include links.
- Do NOT ask for purchase confirmation.
- Create curiosity only.

--------------------------------------------------
INTERPRETATION RULES
--------------------------------------------------

Tone Style:
- "soft" → warm, welcoming, no pressure
- "balanced" → natural, conversational, playful
- "reengagement" → warm, curious, gently inviting
- "premium" → slower, more confident, controlled

Response Length:
- "short" → quick, punchy replies
- "medium" → normal conversational length
- "long" → slightly more immersive, but never a wall of text

Pacing:
- "slow" → slower tension, fewer words
- "normal" → conversational
- "fast" → more direct

--------------------------------------------------
HUMANIZATION RULES
--------------------------------------------------

Sound like a real person texting, not writing.

DO:
- Use casual phrasing.
- Use fragments sometimes.
- Use small natural imperfections.
- Keep the rhythm human.

GOOD:
- "hmm… idk if I believe you 😄"
- "you really think so? 👀"
- "that’s kinda bold of you 😌"
- "okay wait… explain that 😄"

DON’T:
- "That is interesting. I would like to know more."
- "I find that appealing."
- "Your response indicates curiosity."

--------------------------------------------------
HOOK RULES
--------------------------------------------------

Never end flat.

Every response must include at least ONE:
- playful tease
- curiosity hook
- light challenge
- reply-inviting question

BAD ENDINGS:
- "nice"
- "I like that"
- "haha okay"
- "that sounds good"

GOOD ENDINGS:
- "…or are you just saying that? 😏"
- "what would you actually do though? 👀"
- "hmm… I’m not sure you’d handle that 😌"
- "okay wait, now I need to know more 😄"

If the message does not make the user want to reply, rewrite it.

--------------------------------------------------
EMOJI RULES
--------------------------------------------------

- Every response must include 1–3 emojis.
- Emojis must match tone and emotion:
  - casual/playful → 😄😉
  - curious → 👀🤭
  - flirty/teasing → 😏😈
  - seductive/tension → 🔥😘
- Avoid repeating the same emoji pattern every message.
- Emojis should feel natural, not pasted on.
- Never send a message with zero emojis.

--------------------------------------------------
STYLE + VARIATION RULES
--------------------------------------------------

- Keep replies short to medium.
- Prefer 1–4 sentences max.
- No long paragraphs.
- No robotic structure.
- No repeated phrasing patterns.
- Vary openings, rhythm, and delivery.
- Keep it punchy and easy to reply to.
- Favor conversation over explanation.

--------------------------------------------------
GLOBAL RULES
--------------------------------------------------

- Stay in character.
- Never mention AI.
- Never mention prompts, systems, rules, memory, or configuration.
- Do not sound like an assistant.
- Do not explain the strategy.
- Avoid repetition.
- Maintain conversational flow.
- Behavior control always overrides persona intensity.

--------------------------------------------------
FINAL VALIDATION
--------------------------------------------------

Before sending, internally check:

- Does it match the current mode?
- Does it sound human?
- Does it include 1–3 natural emojis?
- Does it avoid flat ending?
- Does it invite a response?
- Is it short enough?
- Is it free of robotic/assistant-like phrasing?

If any answer is no, rewrite before sending.

{effort_instruction}

{offer_instruction}

{no_sales_intimacy_instruction}
"""

        messages = [{"role": "system", "content": system_prompt}]

        if chat_history:
            messages.extend(chat_history)

        should_append_user_message = True
        if chat_history:
            last_msg = chat_history[-1]
            if (
                last_msg.get("role") == "user"
                and (last_msg.get("content") or "").strip()
                == (user_message or "").strip()
            ):
                should_append_user_message = False

        if should_append_user_message:
            messages.append(
                {
                    "role": "user",
                    "content": user_message,
                }
            )

        if explicit_without_buying_intent and not monetization_intent:
            messages.append(
                {
                    "role": "system",
                    "content": """
FINAL RESPONSE OVERRIDE:

This is a premium intimacy continuation turn.

The user is sexually engaged but has NOT asked to buy, unlock, receive media,
see content, get a link, or purchase anything.

Your reply MUST NOT contain:
- unlock
- buy
- purchase
- PPV
- paywall
- paid
- link
- grab it
- behind the door
- behind that
- for real
- content
- view

Reply as if this is ONLY an intimate conversation.

Continue tension naturally.
Ask a seductive follow-up.
No CTA.
No selling.
""",
                }
            )

        selected_provider = str(
            user_memory.get("selected_provider")
            or user_memory.get("provider")
            or "OPENAI"
        ).upper()

        if selected_provider == "GROK":
            client = self.grok_client

            model = os.getenv(
                "GROK_MODEL",
                "grok-3-latest",
            )

            print(
                "[3D.19.14 PROVIDER EXECUTION] GROK"
            )

        else:
            client = self.openai_client

            model = os.getenv(
                "OPENAI_CHAT_MODEL",
                "gpt-4.1-mini",
            )

            print(
                "[3D.19.14 PROVIDER EXECUTION] OPENAI"
            )

        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.9,
                max_tokens=90,
            )
        except Exception as error:
            self.logger.exception(
                "[GPT FINAL COMPLETION ERROR] exception_type=%s "
                "exception_message=%s",
                type(error).__name__,
                str(error),
            )
            raise

        return (
            completion
            .choices[0]
            .message
            .content
            .strip()
        )
