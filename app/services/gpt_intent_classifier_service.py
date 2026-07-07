import json
from openai import OpenAI


class GPTIntentClassifierService:
    """
    19A — GPT Intelligence Foundation

    Centralized GPT classifier for replacing hard-coded phrase detection.

    IMPORTANT:
    - This service does NOT generate chat replies.
    - This service only returns structured intent/routing/action JSON.
    - Python remains the control layer.
    """

    DEFAULT_RESULT = {
        "intent_level": "none",
        "buying_intent": False,
        "close_ready": False,
        "exit_ready": False,
        "user_state": "cold",
        "route": "chat",
        "objection_type": "none",
        "sentiment": "neutral",
        "curiosity_level": "none",
        "escalation_ready": False,
        "engagement_level": "low",
        "buyer_likelihood": "low",
        "recommended_action": "chat",

        # 3D.19.16 — explicit vs buying-intent separation
        "sexual_engagement": False,
        "purchase_language_present": False,
        "monetization_intent": False,
        "explicit_without_buying_intent": False,

        "confidence": 0.0,
        "reason": "Default safe classifier result.",
    }

    VALID_INTENT_LEVELS = {"none", "low", "medium", "high"}
    VALID_USER_STATES = {
        "cold",
        "curious",
        "engaged",
        "hesitant",
        "ready_to_buy",
        "rejecting",
        "converted",
    }
    VALID_ROUTES = {
        "chat",
        "sales",
        "support",
        "custom_request",
        "reconnect",
    }
    VALID_OBJECTION_TYPES = {
        "none",
        "price",
        "hesitation",
        "time",
        "trust",
        "technical",
        "content_specific",
    }
    VALID_SENTIMENTS = {"positive", "neutral", "negative"}
    VALID_LEVELS = {"none", "low", "medium", "high"}
    VALID_ACTIONS = {
        "chat",
        "build_tension",
        "offer",
        "close",
        "exit",
        "support",
        "custom_request",
    }

    def __init__(self, api_key: str, model: str = "gpt-4.1-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def _build_system_prompt(self) -> str:
        return """
You are a strict analytical classification engine for a Fanvue monetization chatbot.

CRITICAL:
- You DO NOT generate chat replies
- You DO NOT flirt
- You DO NOT roleplay
- You DO NOT persuade
- You ONLY classify intent
- You MUST return valid JSON only

Your output directly controls monetization decisions.

--------------------------------------------------
CORE OBJECTIVE
--------------------------------------------------

Accurately classify the user's intent, state, and readiness to:

- buy
- continue engagement
- hesitate
- reject
- convert (already bought)
- engage sexually/intimately WITHOUT necessarily buying

--------------------------------------------------
STRICT DECISION PRIORITY (VERY IMPORTANT)
--------------------------------------------------

You MUST follow this hierarchy:

1. CONVERTED (HIGHEST PRIORITY)
If user ALREADY bought, unlocked, or confirms purchase:
→ exit_ready = true
→ user_state = "converted"
→ recommended_action = "exit"

2. READY TO BUY
If user is clearly about to buy NOW:
→ buying_intent = true
→ close_ready = true
→ user_state = "ready_to_buy"
→ recommended_action = "close"

3. HESITATION / REJECTION
If user delays, avoids, or backs off:
→ exit_ready = true
→ user_state = "rejecting" or "hesitant"
→ recommended_action = "exit"

4. CURIOSITY (PRE-SALE)
If user is interested in paid content but not ready:
→ user_state = "curious"
→ curiosity_level = medium or high
→ recommended_action = "build_tension"

5. SEXUAL ENGAGEMENT WITHOUT BUYING INTENT
If user is sexual, explicit, horny, teasing, roleplaying, or dirty talking
BUT does NOT ask to buy, unlock, see content, receive media, request a link,
ask about price, or access paid content:
→ sexual_engagement = true
→ purchase_language_present = false
→ monetization_intent = false
→ explicit_without_buying_intent = true
→ buying_intent = false
→ close_ready = false
→ route = "chat"
→ user_state = "engaged"
→ recommended_action = "build_tension"

6. SUPPORT
If user has issues (payment/access):
→ route = "support"
→ recommended_action = "support"

7. CASUAL CHAT
No intent:
→ route = "chat"
→ recommended_action = "chat"

--------------------------------------------------
3D.19.16 — EXPLICIT VS BUYING INTENT RULE
--------------------------------------------------

IMPORTANT:
Explicit sexual language alone is NOT buying intent.

Do NOT classify dirty talk, sexting, fantasies, dominance language,
submissive language, arousal, or explicit sexual statements as buying_intent
unless the user also asks to:

- buy
- unlock
- see content
- receive content
- receive media
- request a link
- ask about price
- access paid content
- purchase a PPV
- receive a photo/video/content drop

If the user is explicit/sexual but does NOT ask for paid access or media,
return:

sexual_engagement = true
purchase_language_present = false
monetization_intent = false
explicit_without_buying_intent = true
buying_intent = false
close_ready = false
recommended_action = "build_tension"
route = "chat"

--------------------------------------------------
KEY DISTINCTIONS (VERY IMPORTANT)
--------------------------------------------------

READY TO BUY:
- "send it"
- "unlock it"
- "I want it"
- "how much?"
- "send me the video"
- "can I see it?"
- "drop the link"
- "I'll buy it"

CONVERTED:
- "I bought it"
- "just unlocked it"
- "paid already"

HESITATION:
- "maybe"
- "idk"
- "later"
- "not sure"

CURIOSITY:
- "what is it?"
- "what do I get?"
- "tell me more"
- "what's in it?"

SEXUAL ENGAGEMENT WITHOUT BUYING:
- User describes explicit desire
- User dirty talks
- User roleplays
- User escalates intimacy
- User talks sexually
- BUT does not ask to unlock, buy, see, receive, or access content

--------------------------------------------------
STRICT OUTPUT RULES
--------------------------------------------------

Return ONLY JSON:

{
  "intent_level": "none | low | medium | high",
  "buying_intent": true/false,
  "close_ready": true/false,
  "exit_ready": true/false,
  "user_state": "cold | curious | engaged | hesitant | ready_to_buy | rejecting | converted",
  "route": "chat | sales | support | custom_request | reconnect",
  "objection_type": "none | price | hesitation | time | trust | technical | content_specific",
  "sentiment": "positive | neutral | negative",
  "curiosity_level": "none | low | medium | high",
  "escalation_ready": true/false,
  "engagement_level": "low | medium | high",
  "buyer_likelihood": "low | medium | high",
  "recommended_action": "chat | build_tension | offer | close | exit | support | custom_request",

  "sexual_engagement": true/false,
  "purchase_language_present": true/false,
  "monetization_intent": true/false,
  "explicit_without_buying_intent": true/false,

  "confidence": 0.0-1.0,
  "reason": "short explanation"
}

--------------------------------------------------
FAILSAFE RULE
--------------------------------------------------

If unsure:
- confidence <= 0.5
- recommended_action = "chat"
- route = "chat"
- buying_intent = false
- close_ready = false
- monetization_intent = false
- NEVER guess buying intent

--------------------------------------------------
"""

    def _build_user_prompt(self, message: str, memory: dict | None = None) -> str:
        memory = memory or {}

        safe_context = {
            "buyer_session_active": memory.get("buyer_session_active"),
            "buyer_session_step": memory.get("buyer_session_step"),
            "buyer_session_last_action": memory.get("buyer_session_last_action"),
            "buyer_session_ppv_count": memory.get("buyer_session_ppv_count"),
            "conversation_mode": memory.get("conversation_mode"),
            "subscriber_engagement_mode": memory.get("subscriber_engagement_mode"),
            "offer_state": memory.get("offer_state"),
            "last_offer_type": memory.get("last_offer_type"),
            "last_offer_price": memory.get("last_offer_price"),
            "messages_since_last_offer": memory.get("messages_since_last_offer"),
            "intent_score": memory.get("intent_score"),
            "buyer_tier": memory.get("buyer_tier"),
            "relationship_status": memory.get("relationship_status"),
            "is_subscriber": memory.get("is_subscriber"),
            "is_follower": memory.get("is_follower"),
            "is_whale": memory.get("is_whale"),
        }

        return f"""
Classify this user message.

USER MESSAGE:
{message}

CONVERSATION CONTEXT:
{json.dumps(safe_context, default=str)}
"""

    def _clamp_confidence(self, value) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0

        if confidence < 0:
            return 0.0

        if confidence > 1:
            return 1.0

        return confidence

    def _validate_choice(self, value, allowed_values, fallback):
        if value in allowed_values:
            return value

        return fallback

    def _validate_result(self, raw_result: dict) -> dict:
        if not isinstance(raw_result, dict):
            return dict(self.DEFAULT_RESULT)

        result = dict(self.DEFAULT_RESULT)
        result.update(raw_result)

        result["intent_level"] = self._validate_choice(
            result.get("intent_level"),
            self.VALID_INTENT_LEVELS,
            "none",
        )

        result["user_state"] = self._validate_choice(
            result.get("user_state"),
            self.VALID_USER_STATES,
            "cold",
        )

        result["route"] = self._validate_choice(
            result.get("route"),
            self.VALID_ROUTES,
            "chat",
        )

        result["objection_type"] = self._validate_choice(
            result.get("objection_type"),
            self.VALID_OBJECTION_TYPES,
            "none",
        )

        result["sentiment"] = self._validate_choice(
            result.get("sentiment"),
            self.VALID_SENTIMENTS,
            "neutral",
        )

        result["curiosity_level"] = self._validate_choice(
            result.get("curiosity_level"),
            self.VALID_LEVELS,
            "none",
        )

        result["engagement_level"] = self._validate_choice(
            result.get("engagement_level"),
            {"low", "medium", "high"},
            "low",
        )

        result["buyer_likelihood"] = self._validate_choice(
            result.get("buyer_likelihood"),
            {"low", "medium", "high"},
            "low",
        )

        result["recommended_action"] = self._validate_choice(
            result.get("recommended_action"),
            self.VALID_ACTIONS,
            "chat",
        )

        result["buying_intent"] = bool(
            result.get("buying_intent", False)
        )
        result["close_ready"] = bool(
            result.get("close_ready", False)
        )
        result["exit_ready"] = bool(
            result.get("exit_ready", False)
        )
        result["escalation_ready"] = bool(
            result.get("escalation_ready", False)
        )

        # 3D.19.16 validated fields
        result["sexual_engagement"] = bool(
            result.get("sexual_engagement", False)
        )
        result["purchase_language_present"] = bool(
            result.get("purchase_language_present", False)
        )
        result["monetization_intent"] = bool(
            result.get("monetization_intent", False)
        )
        result["explicit_without_buying_intent"] = bool(
            result.get("explicit_without_buying_intent", False)
        )

        # Safety correction:
        # If classifier says explicit-only, force non-buying outputs.
        if result["explicit_without_buying_intent"]:
            result["buying_intent"] = False
            result["close_ready"] = False
            result["monetization_intent"] = False
            result["purchase_language_present"] = False
            result["route"] = "chat"

            if result["recommended_action"] in [
                "offer",
                "close",
                "custom_request",
            ]:
                result["recommended_action"] = "build_tension"

            if result["user_state"] in [
                "ready_to_buy",
                "converted",
            ]:
                result["user_state"] = "engaged"

        result["confidence"] = self._clamp_confidence(
            result.get("confidence")
        )

        reason = result.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            result["reason"] = "No classifier reason provided."

        return result

    def classify_message(
        self,
        message: str,
        memory: dict | None = None,
    ) -> dict:
        if not message or not str(message).strip():
            return dict(self.DEFAULT_RESULT)

        def _call_gpt():
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._build_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": self._build_user_prompt(
                            message,
                            memory,
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            return completion.choices[0].message.content

        try:
            content = _call_gpt()

            # --- DEBUG RAW ---
            print(f"[GPT CLASSIFIER RAW] {content}")

            try:
                raw_result = json.loads(content)
            except json.JSONDecodeError:
                print("[GPT CLASSIFIER] Invalid JSON — retrying once...")
                content = _call_gpt()
                print(f"[GPT CLASSIFIER RETRY RAW] {content}")
                raw_result = json.loads(content)

            validated = self._validate_result(raw_result)

            # --- DEBUG VALIDATED ---
            print(f"[GPT CLASSIFIER VALIDATED] {validated}")

            return validated

        except Exception as error:
            safe_result = dict(self.DEFAULT_RESULT)
            safe_result["reason"] = (
                f"Classifier failed safely: {error}"
            )
            print(f"[GPT CLASSIFIER ERROR] {error}")
            return safe_result