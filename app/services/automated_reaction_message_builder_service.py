class AutomatedReactionMessageBuilderService:
    """
    3D.18.9 — Reaction Message Builder

    Builds safe automated reaction message payloads.

    IMPORTANT:
    This service does NOT send anything.
    It only prepares message text + metadata.
    """

    MESSAGE_TEMPLATES = {
        "purchase_thank_you": (
            "Aww thank you babe 💕 I love that you wanted that one."
        ),
        "unlock_followup": (
            "Mmm you unlocked it 😏 I was hoping you’d see that one."
        ),
        "tip_thank_you": (
            "You’re too sweet for that tip 🥰 thank you, babe."
        ),
        "subscription_welcome": (
            "Welcome in babe 💕 I’m happy you’re here."
        ),
        "premium_followup": (
            "I saved something a little more exclusive for you 😏"
        ),
        "whale_retention_message": (
            "You always know how to get my attention 💕 I like keeping you close."
        ),
    }

    def build_message(
        self,
        reaction_type: str,
        monetization_event: dict | None = None,
        buyer_context: dict | None = None,
    ):
        if not reaction_type:
            return self._blocked("missing_reaction_type")

        if reaction_type not in self.MESSAGE_TEMPLATES:
            return self._blocked(
                "unsupported_reaction_type",
                {
                    "reaction_type": reaction_type,
                },
            )

        monetization_event = monetization_event or {}
        buyer_context = buyer_context or {}

        message_text = self.MESSAGE_TEMPLATES[reaction_type]

        return {
            "success": True,
            "blocked": False,
            "message_built": True,
            "reaction_type": reaction_type,
            "message_text": message_text,
            "fanvue_user_id": monetization_event.get("fanvue_user_id"),
            "local_user_id": monetization_event.get("local_user_id"),
            "fanvue_account_id": monetization_event.get("fanvue_account_id"),
            "external_event_id": monetization_event.get("external_event_id"),
            "buyer_tier": buyer_context.get("buyer_tier"),
            "dry_run_safe": True,
            "reason": "reaction_message_built",
        }

    def _blocked(
        self,
        reason: str,
        extra: dict | None = None,
    ):
        result = {
            "success": False,
            "blocked": True,
            "message_built": False,
            "reason": reason,
        }

        if extra:
            result.update(extra)

        return result