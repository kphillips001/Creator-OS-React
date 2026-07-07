class AutomatedReactionTypeRouterService:
    """
    3D.18.2 — Reaction Type Router

    Converts realtime monetization events + post-purchase decisions
    into one standardized automated reaction type.

    This service does NOT send messages.
    It only decides which reaction type should be prepared.
    """

    SUPPORTED_REACTIONS = {
        "purchase_thank_you",
        "unlock_followup",
        "tip_thank_you",
        "subscription_welcome",
        "premium_followup",
        "whale_retention_message",
    }

    EVENT_REACTION_MAP = {
        "purchase_received": "purchase_thank_you",
        "purchase_created": "purchase_thank_you",
        "unlock_confirmation": "unlock_followup",
        "content_unlocked": "unlock_followup",
        "tip_received": "tip_thank_you",
        "tip_created": "tip_thank_you",
        "subscription_created": "subscription_welcome",
        "subscription_renewed": "subscription_welcome",
    }

    DECISION_REACTION_MAP = {
        "thank_you_only": "purchase_thank_you",
        "soft_continue": "purchase_thank_you",
        "tip_reward": "tip_thank_you",
        "subscription_welcome": "subscription_welcome",
        "premium_followup": "premium_followup",
        "whale_retention": "whale_retention_message",
    }

    def resolve_reaction_type(
        self,
        monetization_event: dict,
        post_purchase_decision: dict | None = None,
    ):
        if not monetization_event:
            return self._blocked(
                "missing_monetization_event"
            )

        post_purchase_decision = (
            post_purchase_decision or {}
        )

        explicit_reaction_type = (
            post_purchase_decision.get("reaction_type")
        )

        if explicit_reaction_type:
            return self._validate_reaction_type(
                explicit_reaction_type,
                "explicit_reaction_type",
            )

        decision = post_purchase_decision.get(
            "decision"
        )

        if decision in self.DECISION_REACTION_MAP:
            return self._validate_reaction_type(
                self.DECISION_REACTION_MAP[decision],
                "post_purchase_decision",
            )

        event_type = monetization_event.get(
            "event_type"
        )

        if event_type in self.EVENT_REACTION_MAP:
            return self._validate_reaction_type(
                self.EVENT_REACTION_MAP[event_type],
                "monetization_event",
            )

        return self._blocked(
            "unsupported_reaction_type",
            {
                "event_type": event_type,
                "decision": decision,
            },
        )

    def _validate_reaction_type(
        self,
        reaction_type: str,
        source: str,
    ):
        if reaction_type not in self.SUPPORTED_REACTIONS:
            return self._blocked(
                "unsupported_reaction_type",
                {
                    "reaction_type": reaction_type,
                    "source": source,
                },
            )

        return {
            "success": True,
            "blocked": False,
            "reaction_type": reaction_type,
            "source": source,
            "supported": True,
        }

    def _blocked(
        self,
        reason: str,
        extra: dict | None = None,
    ):
        result = {
            "success": False,
            "blocked": True,
            "reaction_type": None,
            "reason": reason,
        }

        if extra:
            result.update(extra)

        return result