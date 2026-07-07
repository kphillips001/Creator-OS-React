class ReactionDuplicateGuardService:
    """
    3D.13.3 — Duplicate Reaction Protection

    Prevents duplicate automated reactions for the same monetization event.
    """

    def validate_duplicate_safety(
        self,
        execution_plan: dict,
        reaction_history: list[dict] | None = None,
    ):
        if not execution_plan:
            return self._blocked("missing_execution_plan")

        reaction_history = reaction_history or []

        event_type = execution_plan.get("event_type")
        fanvue_user_id = execution_plan.get("fanvue_user_id")
        action_type = execution_plan.get("action_type")

        raw_event = execution_plan.get("raw_event", {})
        external_event_id = raw_event.get("external_event_id")

        if not fanvue_user_id:
            return self._blocked("missing_fanvue_user_id")

        if not action_type:
            return self._blocked("missing_action_type")

        for item in reaction_history:
            if external_event_id and item.get("external_event_id") == external_event_id:
                return self._blocked(
                    "duplicate_external_event_reaction",
                    {
                        "external_event_id": external_event_id,
                    },
                )

            same_user = item.get("fanvue_user_id") == fanvue_user_id
            same_action = item.get("action_type") == action_type
            same_event = item.get("event_type") == event_type

            if same_user and same_action and same_event:
                return self._blocked(
                    "duplicate_user_action_event_reaction",
                    {
                        "fanvue_user_id": fanvue_user_id,
                        "action_type": action_type,
                        "event_type": event_type,
                    },
                )

        return {
            "success": True,
            "blocked": False,
            "duplicate": False,
            "reason": None,
            "fanvue_user_id": fanvue_user_id,
            "action_type": action_type,
            "event_type": event_type,
            "external_event_id": external_event_id,
        }

    def _blocked(self, reason: str, extra: dict | None = None):
        result = {
            "success": False,
            "blocked": True,
            "duplicate": True,
            "reason": reason,
        }

        if extra:
            result.update(extra)

        return result