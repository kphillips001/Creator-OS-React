from app.services.gpt_intent_classifier_service import GPTIntentClassifierService
from app.config import settings


class IntentService:
    def __init__(self):
        self.classifier = GPTIntentClassifierService(settings.OPENAI_API_KEY)

    def detect_intent(
        self,
        message: str,
        memory: dict = None,
        classifier_result: dict = None,
    ) -> dict:
        """
        19B / 19G — GPT-based intent detection.

        Uses precomputed classifier_result when provided.
        Avoids duplicate GPT calls from DecisionEngine.
        """

        result = classifier_result or self.classifier.classify_message(message, memory)

        intent_level = result.get("intent_level", "none")
        buyer_likelihood = result.get("buyer_likelihood", "low")
        buying_intent = bool(result.get("buying_intent", False))
        close_ready = bool(result.get("close_ready", False))
        exit_ready = bool(result.get("exit_ready", False))
        recommended_action = result.get("recommended_action", "chat")
        objection_type = result.get("objection_type", "none")
        curiosity_level = result.get("curiosity_level", "none")
        confidence = float(result.get("confidence", 0.0) or 0.0)

        score_map = {
            "none": 0,
            "low": 15,
            "medium": 45,
            "high": 80,
        }

        likelihood_bonus = {
            "low": 0,
            "medium": 10,
            "high": 20,
        }

        message_score = score_map.get(intent_level, 0)
        behavior_score = likelihood_bonus.get(buyer_likelihood, 0)

        # -----------------------------------------
        # GPT INTENT BOOST
        # -----------------------------------------
        if confidence >= 0.6:
            if buying_intent:
                behavior_score += 25

            if close_ready:
                behavior_score += 40

            if recommended_action == "offer":
                behavior_score += 15

            if recommended_action == "close":
                behavior_score += 25

            if exit_ready or recommended_action == "exit":
                behavior_score += 10

        total_score = message_score + behavior_score

        if total_score >= 70:
            tier = "hot"
        elif total_score >= 30:
            tier = "medium"
        else:
            tier = "low"

        print(
            f"[INTENT BOOST] intent={intent_level} "
            f"buying={buying_intent} close={close_ready} "
            f"action={recommended_action} confidence={confidence} "
            f"score={total_score}"
        )

        signals = []

        if buying_intent:
            signals.append("buying_intent")

        if close_ready:
            signals.append("close_ready")

        if exit_ready:
            signals.append("exit_ready")

        if recommended_action:
            signals.append(recommended_action)

        if objection_type != "none":
            signals.append(f"objection_{objection_type}")

        if curiosity_level in ["medium", "high"]:
            signals.append("curiosity")

        signals = list(dict.fromkeys(signals))

        return {
            "tier": tier,
            "score": total_score,
            "message_score": message_score,
            "behavior_score": behavior_score,
            "signals": signals,
            "classifier_result": result,
        }