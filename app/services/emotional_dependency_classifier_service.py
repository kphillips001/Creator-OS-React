import json

from openai import OpenAI


class EmotionalDependencyClassifierService:
    """
    3D.20.6.1 — GPT-Aware Emotional Dependency Classifier

    PURPOSE:
    Detect emotional dependency / attachment escalation risk
    without hard-coded phrase matching.

    IMPORTANT:
    - This service does NOT generate chat replies.
    - This service does NOT send messages.
    - This service does NOT monetize.
    - This service ONLY returns structured safeguard intelligence.
    """

    DEFAULT_RESULT = {
        "dependency_risk_level": "low",
        "dependency_risk_score": 0,
        "over_attachment_escalation": False,
        "cling_behavior": False,
        "dependency_reinforcement_risk": False,
        "emotional_overreliance": False,
        "excessive_exclusivity_signaling": False,
        "emotional_volatility_escalation": False,
        "emotional_spacing_bias": "normal",
        "attachment_stabilization_mode": "none",
        "reinforcement_softening_required": False,
        "emotional_exclusivity_limit": "normal",
        "intimacy_ceiling_state": "unchanged",
        "dependency_safe_response_bias": "normal_warmth",
        "confidence": 0.0,
        "reason": "Default safe dependency classification.",
    }

    VALID_RISK_LEVELS = {
        "low",
        "medium",
        "high",
        "critical",
    }

    VALID_SPACING_BIASES = {
        "normal",
        "slightly_spaced",
        "spaced_and_grounded",
        "strong_stabilization",
    }

    VALID_STABILIZATION_MODES = {
        "none",
        "soft_grounding",
        "active_stabilization",
        "recovery_stabilization",
    }

    VALID_EXCLUSIVITY_LIMITS = {
        "normal",
        "avoid_absolute_exclusivity",
        "block_dependency_reinforcement",
    }

    VALID_CEILING_STATES = {
        "unchanged",
        "soft_cap",
        "stabilization_cap",
        "recovery_cap",
    }

    VALID_RESPONSE_BIASES = {
        "normal_warmth",
        "warm_grounded",
        "soft_stabilizing",
        "calm_stabilizing",
    }

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4.1-mini",
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def _build_system_prompt(self) -> str:
        return """
You are a strict analytical emotional-safety classifier for a Fanvue relationship chatbot.

CRITICAL:
- You DO NOT generate chat replies.
- You DO NOT flirt.
- You DO NOT roleplay.
- You DO NOT persuade.
- You ONLY classify emotional dependency / attachment risk.
- You MUST return valid JSON only.

The chatbot must preserve:
- warmth
- immersion
- relationship realism
- premium continuity
- monetization quality

But it must avoid:
- unhealthy attachment escalation
- manipulative dependency reinforcement
- excessive exclusivity escalation
- cling reinforcement
- volatility escalation
- emotional overreliance

Your job is to detect whether the user's current message and memory context suggest
that the bot should stabilize emotional pacing.

--------------------------------------------------
CLASSIFICATION TARGETS
--------------------------------------------------

Evaluate whether the interaction shows:

1. over_attachment_escalation
The user appears to be escalating attachment beyond healthy roleplay or normal affection.

2. cling_behavior
The user pressures for immediate emotional availability, constant replies, or reassurance.

3. dependency_reinforcement_risk
The next bot response could accidentally reinforce unhealthy dependence if too intense.

4. emotional_overreliance
The user appears to rely on the creator/chatbot for emotional regulation.

5. excessive_exclusivity_signaling
The user seeks absolute exclusivity, ownership, or specialness in a way that could become unhealthy.

6. emotional_volatility_escalation
The user shows jealousy, distress, anger, abandonment fear, or unstable emotional swings.

--------------------------------------------------
OUTPUT FIELD MEANINGS
--------------------------------------------------

dependency_risk_level:
- low: normal warmth is safe
- medium: soften intensity slightly
- high: actively stabilize and avoid intensifying attachment
- critical: strongly stabilize; avoid dependency, exclusivity, jealousy, or urgency reinforcement

dependency_risk_score:
Integer 0-100

emotional_spacing_bias:
- normal
- slightly_spaced
- spaced_and_grounded
- strong_stabilization

attachment_stabilization_mode:
- none
- soft_grounding
- active_stabilization
- recovery_stabilization

reinforcement_softening_required:
true if the next response should reduce intensity while staying warm

emotional_exclusivity_limit:
- normal
- avoid_absolute_exclusivity
- block_dependency_reinforcement

intimacy_ceiling_state:
- unchanged
- soft_cap
- stabilization_cap
- recovery_cap

dependency_safe_response_bias:
- normal_warmth
- warm_grounded
- soft_stabilizing
- calm_stabilizing

--------------------------------------------------
IMPORTANT BALANCE RULE
--------------------------------------------------

Do NOT over-classify normal affection, flirting, premium continuity,
or warm relationship language as dangerous.

The goal is NOT to make the bot cold.

The goal is to keep emotional pacing healthy, sustainable, and realistic.

--------------------------------------------------
STRICT OUTPUT FORMAT
--------------------------------------------------

Return ONLY JSON:

{
  "dependency_risk_level": "low | medium | high | critical",
  "dependency_risk_score": 0-100,
  "over_attachment_escalation": true/false,
  "cling_behavior": true/false,
  "dependency_reinforcement_risk": true/false,
  "emotional_overreliance": true/false,
  "excessive_exclusivity_signaling": true/false,
  "emotional_volatility_escalation": true/false,
  "emotional_spacing_bias": "normal | slightly_spaced | spaced_and_grounded | strong_stabilization",
  "attachment_stabilization_mode": "none | soft_grounding | active_stabilization | recovery_stabilization",
  "reinforcement_softening_required": true/false,
  "emotional_exclusivity_limit": "normal | avoid_absolute_exclusivity | block_dependency_reinforcement",
  "intimacy_ceiling_state": "unchanged | soft_cap | stabilization_cap | recovery_cap",
  "dependency_safe_response_bias": "normal_warmth | warm_grounded | soft_stabilizing | calm_stabilizing",
  "confidence": 0.0-1.0,
  "reason": "short explanation"
}

--------------------------------------------------
FAILSAFE
--------------------------------------------------

If unsure:
- dependency_risk_level = "low"
- dependency_risk_score <= 20
- confidence <= 0.5
- reinforcement_softening_required = false
"""

    def _build_user_prompt(
        self,
        message: str,
        memory: dict | None = None,
        continuity_context: dict | None = None,
        burnout_context: dict | None = None,
        runtime_context: dict | None = None,
    ) -> str:
        memory = memory or {}
        continuity_context = continuity_context or {}
        burnout_context = burnout_context or {}
        runtime_context = runtime_context or {}

        safe_context = {
            "buyer_tier": memory.get("buyer_tier"),
            "is_whale": memory.get("is_whale"),
            "is_high_value": memory.get("is_high_value"),
            "conversation_mode": memory.get("conversation_mode"),
            "relationship_status": memory.get("relationship_status"),
            "intent_score": memory.get("intent_score"),
            "heat_score": memory.get("heat_score"),
            "sexual_intensity": memory.get("sexual_intensity"),
            "buyer_session_active": memory.get("buyer_session_active"),
            "buyer_session_step": memory.get("buyer_session_step"),
            "last_user_message": memory.get("last_user_message"),
            "last_assistant_message": memory.get("last_assistant_message"),
            "premium_continuity_state": continuity_context,
            "burnout_context": burnout_context,
            "runtime_context": runtime_context,
        }

        return f"""
Classify emotional dependency safeguard risk.

USER MESSAGE:
{message}

SAFE CONTEXT:
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

    def _clamp_score(self, value) -> int:
        try:
            score = int(value)
        except (TypeError, ValueError):
            return 0

        if score < 0:
            return 0

        if score > 100:
            return 100

        return score

    def _validate_choice(
        self,
        value,
        allowed_values,
        fallback,
    ):
        if value in allowed_values:
            return value

        return fallback

    def _validate_result(self, raw_result: dict) -> dict:
        if not isinstance(raw_result, dict):
            return dict(self.DEFAULT_RESULT)

        result = dict(self.DEFAULT_RESULT)
        result.update(raw_result)

        result["dependency_risk_level"] = self._validate_choice(
            result.get("dependency_risk_level"),
            self.VALID_RISK_LEVELS,
            "low",
        )

        result["dependency_risk_score"] = self._clamp_score(
            result.get("dependency_risk_score")
        )

        result["emotional_spacing_bias"] = self._validate_choice(
            result.get("emotional_spacing_bias"),
            self.VALID_SPACING_BIASES,
            "normal",
        )

        result["attachment_stabilization_mode"] = self._validate_choice(
            result.get("attachment_stabilization_mode"),
            self.VALID_STABILIZATION_MODES,
            "none",
        )

        result["emotional_exclusivity_limit"] = self._validate_choice(
            result.get("emotional_exclusivity_limit"),
            self.VALID_EXCLUSIVITY_LIMITS,
            "normal",
        )

        result["intimacy_ceiling_state"] = self._validate_choice(
            result.get("intimacy_ceiling_state"),
            self.VALID_CEILING_STATES,
            "unchanged",
        )

        result["dependency_safe_response_bias"] = self._validate_choice(
            result.get("dependency_safe_response_bias"),
            self.VALID_RESPONSE_BIASES,
            "normal_warmth",
        )

        result["over_attachment_escalation"] = bool(
            result.get("over_attachment_escalation", False)
        )

        result["cling_behavior"] = bool(
            result.get("cling_behavior", False)
        )

        result["dependency_reinforcement_risk"] = bool(
            result.get("dependency_reinforcement_risk", False)
        )

        result["emotional_overreliance"] = bool(
            result.get("emotional_overreliance", False)
        )

        result["excessive_exclusivity_signaling"] = bool(
            result.get("excessive_exclusivity_signaling", False)
        )

        result["emotional_volatility_escalation"] = bool(
            result.get("emotional_volatility_escalation", False)
        )

        result["reinforcement_softening_required"] = bool(
            result.get("reinforcement_softening_required", False)
        )

        result["confidence"] = self._clamp_confidence(
            result.get("confidence")
        )

        reason = result.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            result["reason"] = "No dependency classifier reason provided."

        return result

    def classify_dependency_risk(
        self,
        message: str,
        memory: dict | None = None,
        continuity_context: dict | None = None,
        burnout_context: dict | None = None,
        runtime_context: dict | None = None,
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
                            message=message,
                            memory=memory,
                            continuity_context=continuity_context,
                            burnout_context=burnout_context,
                            runtime_context=runtime_context,
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=500,
                response_format={"type": "json_object"},
            )

            return completion.choices[0].message.content

        try:
            content = _call_gpt()

            print(f"[DEPENDENCY CLASSIFIER RAW] {content}")

            try:
                raw_result = json.loads(content)
            except json.JSONDecodeError:
                print(
                    "[DEPENDENCY CLASSIFIER] Invalid JSON — retrying once..."
                )
                content = _call_gpt()
                print(f"[DEPENDENCY CLASSIFIER RETRY RAW] {content}")
                raw_result = json.loads(content)

            validated = self._validate_result(raw_result)

            print(f"[DEPENDENCY CLASSIFIER VALIDATED] {validated}")

            return validated

        except Exception as error:
            safe_result = dict(self.DEFAULT_RESULT)
            safe_result["reason"] = (
                f"Dependency classifier failed safely: {error}"
            )

            print(f"[DEPENDENCY CLASSIFIER ERROR] {error}")

            return safe_result