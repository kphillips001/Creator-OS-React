from datetime import datetime


class AutomatedReactionDuplicateProtectionService:
    """
    3D.18.4 — Duplicate Reaction Protection

    Prevents duplicate automated monetization reactions.

    Protects against:
    - duplicated webhook events
    - repeated thank-you sends
    - retry replay spam
    - duplicate unlock followups
    """

    def validate_duplicate_reaction(
        self,
        monetization_event: dict,
        reaction_type: str,
        reaction_history: list[dict] | None = None,
    ):
        if not monetization_event:
            return self._blocked(
                "missing_monetization_event"
            )

        if not reaction_type:
            return self._blocked(
                "missing_reaction_type"
            )

        reaction_history = reaction_history or []

        event_id = (
            monetization_event.get("external_event_id")
            or monetization_event.get("event_id")
            or monetization_event.get("id")
        )

        fanvue_user_id = monetization_event.get(
            "fanvue_user_id"
        )

        for reaction in reaction_history:
            existing_reaction_type = reaction.get(
                "reaction_type"
            )

            existing_event_id = reaction.get(
                "event_id"
            )

            existing_fanvue_user_id = reaction.get(
                "fanvue_user_id"
            )

            if (
                existing_event_id
                and event_id
                and existing_event_id == event_id
            ):
                return self._blocked(
                    "duplicate_event_reaction",
                    {
                        "event_id": event_id,
                        "reaction_type": reaction_type,
                    },
                )

            if (
                existing_reaction_type == reaction_type
                and existing_fanvue_user_id
                == fanvue_user_id
            ):
                return self._blocked(
                    "duplicate_user_reaction_type",
                    {
                        "fanvue_user_id": (
                            fanvue_user_id
                        ),
                        "reaction_type": (
                            reaction_type
                        ),
                    },
                )

        return {
            "success": True,
            "blocked": False,
            "duplicate_safe": True,
            "reaction_type": reaction_type,
            "fanvue_user_id": fanvue_user_id,
            "event_id": event_id,
            "checked_at": (
                datetime.utcnow().isoformat()
            ),
        }

    def _blocked(
        self,
        reason: str,
        extra: dict | None = None,
    ):
        result = {
            "success": False,
            "blocked": True,
            "duplicate_safe": False,
            "reason": reason,
        }

        if extra:
            result.update(extra)

        return result