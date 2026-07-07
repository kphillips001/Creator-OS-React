class ReactionExecutionService:
    """
    3D.13.1 — Reaction Execution Foundation

    Converts PostPurchaseDecisionService output into a safe,
    structured execution plan.

    IMPORTANT:
    This foundation does NOT send live Fanvue messages yet.
    It only decides what action should be executed later.
    """

    MESSAGE_ACTIONS = {
        "thank_you_only": "send_thank_you_message",
        "soft_continue": "send_soft_continue_message",
        "whale_retention": "send_whale_retention_message",
        "tip_reward": "send_tip_reward_message",
        "subscription_welcome": "send_subscription_welcome_message",
    }

    QUEUE_ACTIONS = {
        "premium_followup": "queue_premium_followup",
        "next_best_offer": "queue_next_best_offer",
    }

    def build_execution_plan(
        self,
        monetization_event: dict,
        post_purchase_decision: dict,
    ):
        if not monetization_event:
            return self._blocked("missing_monetization_event")

        if not post_purchase_decision:
            return self._blocked("missing_post_purchase_decision")

        decision_type = post_purchase_decision.get("decision")
        event_type = monetization_event.get("event_type")
        fanvue_user_id = monetization_event.get("fanvue_user_id")
        fanvue_account_id = monetization_event.get("fanvue_account_id")

        if not decision_type:
            return self._blocked("missing_decision_type")

        if not fanvue_user_id:
            return self._blocked("missing_fanvue_user_id")

        action_type = self._resolve_action_type(decision_type)

        if not action_type:
            return self._blocked(
                "unsupported_decision_type",
                {
                    "decision_type": decision_type,
                    "event_type": event_type,
                },
            )

        return {
            "success": True,
            "blocked": False,
            "executed": False,
            "execution_mode": "plan_only",
            "action_type": action_type,
            "decision_type": decision_type,
            "event_type": event_type,
            "fanvue_user_id": fanvue_user_id,
            "fanvue_account_id": fanvue_account_id,
            "should_send_message": action_type.startswith("send_"),
            "should_queue_followup": action_type.startswith("queue_"),
            "message_intent": self._resolve_message_intent(
                event_type,
                decision_type,
            ),
            "followup_mode": post_purchase_decision.get("followup_mode"),
            "next_best_offer": post_purchase_decision.get("next_best_offer"),
            "aggression_level": post_purchase_decision.get("aggression_level"),
            "pacing_profile": post_purchase_decision.get("pacing_profile"),
            "ppv_suppressed": post_purchase_decision.get("ppv_suppressed"),
            "escalation_paused": post_purchase_decision.get(
                "escalation_paused"
            ),
            "reasons": post_purchase_decision.get("reasons", []),
            "raw_decision": post_purchase_decision,
            "raw_event": monetization_event,
        }

    def _resolve_action_type(self, decision_type: str):
        if decision_type in self.MESSAGE_ACTIONS:
            return self.MESSAGE_ACTIONS[decision_type]

        if decision_type in self.QUEUE_ACTIONS:
            return self.QUEUE_ACTIONS[decision_type]

        return None

    def _resolve_message_intent(
        self,
        event_type: str | None,
        decision_type: str,
    ):
        if event_type in ("purchase_received", "purchase_created"):
            return "purchase_thank_you"

        if event_type == "unlock_confirmation":
            return "unlock_followup"

        if event_type == "tip_received":
            return "tip_thank_you"

        if event_type == "subscription_created":
            return "subscription_welcome"

        if decision_type == "whale_retention":
            return "whale_retention_message"

        if decision_type == "premium_followup":
            return "premium_followup"

        return "post_purchase_reaction"

    def _blocked(self, reason: str, extra: dict | None = None):
        result = {
            "success": False,
            "blocked": True,
            "executed": False,
            "execution_mode": "blocked",
            "reason": reason,
        }

        if extra:
            result.update(extra)

        return result