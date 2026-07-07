from app.repositories.content_repository import (
    get_tease_content_for_user,
    get_vip_content_for_user,
    get_premium_content_for_user,
)


class ContentGatingService:
    def __init__(self):
        pass

    def _get_gpt_result(self, working_memory: dict, intent_result: dict) -> dict:
        return (
            working_memory.get("gpt_classifier_result")
            or intent_result.get("classifier_result")
            or {}
        )

    def should_send_content(
        self,
        working_memory: dict,
        intent_result: dict,
        relationship_route: str,
    ) -> bool:
        """
        15.1 — GPT-driven content gate.

        Decides whether ANY content should be considered.
        """

        gpt_result = self._get_gpt_result(working_memory, intent_result)

        confidence = float(gpt_result.get("confidence", 0.0) or 0.0)
        intent_level = gpt_result.get("intent_level", "none")
        buyer_likelihood = gpt_result.get("buyer_likelihood", "low")
        buying_intent = bool(gpt_result.get("buying_intent", False))
        close_ready = bool(gpt_result.get("close_ready", False))
        exit_ready = bool(gpt_result.get("exit_ready", False))
        objection_type = gpt_result.get("objection_type")
        recommended_action = gpt_result.get("recommended_action")

        if confidence < 0.6:
            print("[CONTENT BLOCKED] low GPT confidence")
            return False

        if exit_ready:
            print("[CONTENT BLOCKED] exit_ready=True")
            return False

        if objection_type and objection_type != "none":
            print("[CONTENT BLOCKED] objection detected")
            return False

        if relationship_route == "follower" and buyer_likelihood != "high":
            print("[CONTENT BLOCKED] follower not hot enough")
            return False

        if (
            buying_intent
            or close_ready
            or intent_level == "high"
            or recommended_action in ["offer", "close"]
        ):
            print("[CONTENT ALLOWED]")
            return True

        print("[CONTENT BLOCKED] GPT says no strong intent")
        return False

    def select_content(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        intent_result: dict,
        working_memory: dict | None = None,
    ):
        """
        15.1 — Select the safest content tier.
        """

        working_memory = working_memory or {}
        gpt_result = self._get_gpt_result(working_memory, intent_result)

        intent_level = gpt_result.get("intent_level", "none")
        buyer_likelihood = gpt_result.get("buyer_likelihood", "low")
        close_ready = bool(gpt_result.get("close_ready", False))
        buying_intent = bool(gpt_result.get("buying_intent", False))

        if (intent_level == "high" and buyer_likelihood == "high") or close_ready or buying_intent:
            content = get_premium_content_for_user(
                fanvue_account_id,
                fanvue_user_id,
            )

            if content:
                print("[CONTENT SELECTED] PREMIUM")
                return content, "premium"

            content = get_vip_content_for_user(
                fanvue_account_id,
                fanvue_user_id,
            )

            if content:
                print("[CONTENT SELECTED] VIP")
                return content, "vip"

        if intent_level == "medium":
            content = get_vip_content_for_user(
                fanvue_account_id,
                fanvue_user_id,
            )

            if content:
                print("[CONTENT SELECTED] VIP")
                return content, "vip"

        content = get_tease_content_for_user(
            fanvue_account_id,
            fanvue_user_id,
        )

        if content:
            print("[CONTENT SELECTED] TEASE")
            return content, "tease"

        print("[CONTENT NONE AVAILABLE]")
        return None, None