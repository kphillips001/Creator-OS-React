from app.services.gpt_intent_classifier_service import GPTIntentClassifierService
from app.config import settings


class SituationRoutingService:
    """
    19C / 19G — GPT-based situation routing.

    19G update:
    - Uses precomputed classifier_result when provided.
    - Avoids duplicate GPT calls from DecisionEngine.
    """

    VALID_ROUTES = {
        "chat",
        "sales",
        "support",
        "video_request",
        "custom_request",
        "reconnect",
    }

    def __init__(self):
        self.classifier = GPTIntentClassifierService(settings.OPENAI_API_KEY)

    def route_message(
        self,
        message: str,
        memory: dict = None,
        classifier_result: dict = None,
    ) -> dict:
        if not message or not str(message).strip():
            return {
                "route": "chat",
                "confidence": 0.50,
                "signals": ["empty_message_fallback"],
                "reason": "Empty message fell back to chat.",
                "scores": {
                    "chat": 50,
                    "sales": 0,
                    "support": 0,
                    "video_request": 0,
                    "custom_request": 0,
                    "reconnect": 0,
                },
            }

        result = classifier_result or self.classifier.classify_message(message, memory or {})

        route = result.get("route", "chat")
        confidence = float(result.get("confidence", 0.0) or 0.0)
        recommended_action = result.get("recommended_action", "chat")
        reason = result.get("reason", "GPT classifier routed message.")

        if route not in self.VALID_ROUTES:
            route = "chat"

        signals = self._build_signals(result)
        scores = self._build_scores(route, confidence)

        return {
            "route": route,
            "confidence": confidence,
            "signals": signals,
            "reason": reason,
            "scores": scores,
            "recommended_action": recommended_action,
            "classifier_result": result,
        }

    def _build_signals(self, result: dict) -> list:
        signals = []

        route = result.get("route")
        recommended_action = result.get("recommended_action")
        intent_level = result.get("intent_level")
        user_state = result.get("user_state")
        objection_type = result.get("objection_type")
        curiosity_level = result.get("curiosity_level")
        buyer_likelihood = result.get("buyer_likelihood")

        if route:
            signals.append(f"route_{route}")

        if recommended_action:
            signals.append(f"action_{recommended_action}")

        if intent_level and intent_level != "none":
            signals.append(f"intent_{intent_level}")

        if user_state and user_state != "cold":
            signals.append(f"user_state_{user_state}")

        if objection_type and objection_type != "none":
            signals.append(f"objection_{objection_type}")

        if curiosity_level and curiosity_level != "none":
            signals.append(f"curiosity_{curiosity_level}")

        if buyer_likelihood and buyer_likelihood != "low":
            signals.append(f"buyer_likelihood_{buyer_likelihood}")

        if result.get("buying_intent"):
            signals.append("buying_intent")

        if result.get("close_ready"):
            signals.append("close_ready")

        if result.get("exit_ready"):
            signals.append("exit_ready")

        if result.get("escalation_ready"):
            signals.append("escalation_ready")

        return list(dict.fromkeys(signals)) or ["gpt_default_chat"]

    def _build_scores(self, route: str, confidence: float) -> dict:
        base_scores = {
            "chat": 0,
            "sales": 0,
            "support": 0,
            "video_request": 0,
            "custom_request": 0,
            "reconnect": 0,
        }

        if route not in base_scores:
            base_scores["chat"] = 50
            return base_scores

        base_scores[route] = int(confidence * 100)

        return base_scores