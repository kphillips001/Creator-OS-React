class AutomatedReactionTargetSafetyService:
    """
    3D.18.3 — Local User / Thread Mapping Safety

    Validates that an automated reaction has enough safe target
    information before any outbound reaction can be prepared.

    This service does NOT send anything.
    It only validates the outbound target safety context.
    """

    THREAD_KEYS = [
        "fanvue_thread_id",
        "fanvue_thread_uuid",
        "thread_id",
        "thread_uuid",
        "chat_thread_id",
        "chat_thread_uuid",
    ]

    def validate_target_safety(
        self,
        monetization_event: dict,
        user_memory: dict | None = None,
        runtime_state: dict | None = None,
        require_thread: bool = True,
    ):
        if not monetization_event:
            return self._blocked(
                "missing_monetization_event"
            )

        user_memory = user_memory or {}
        runtime_state = runtime_state or {}

        local_user_id = monetization_event.get(
            "local_user_id"
        )

        if not local_user_id:
            return self._blocked(
                "missing_local_user_mapping"
            )

        fanvue_user_id = monetization_event.get(
            "fanvue_user_id"
        )

        if not fanvue_user_id:
            return self._blocked(
                "missing_fanvue_user_id"
            )

        fanvue_account_id = monetization_event.get(
            "fanvue_account_id"
        )

        if not fanvue_account_id:
            return self._blocked(
                "missing_fanvue_account_id"
            )

        thread_context = self._resolve_thread_context(
            monetization_event=monetization_event,
            user_memory=user_memory,
            runtime_state=runtime_state,
        )

        if require_thread and not thread_context:
            return self._blocked(
                "missing_reaction_thread_context",
                {
                    "local_user_id": local_user_id,
                    "fanvue_user_id": fanvue_user_id,
                    "fanvue_account_id": fanvue_account_id,
                },
            )

        return {
            "success": True,
            "blocked": False,
            "target_safe": True,
            "local_user_id": local_user_id,
            "fanvue_user_id": fanvue_user_id,
            "fanvue_account_id": fanvue_account_id,
            "thread_context": thread_context,
            "reason": "target_mapping_valid",
        }

    def _resolve_thread_context(
        self,
        monetization_event: dict,
        user_memory: dict,
        runtime_state: dict,
    ):
        for key in self.THREAD_KEYS:
            value = monetization_event.get(key)

            if value:
                return {
                    "source": "monetization_event",
                    "key": key,
                    "value": value,
                }

        for key in self.THREAD_KEYS:
            value = runtime_state.get(key)

            if value:
                return {
                    "source": "runtime_state",
                    "key": key,
                    "value": value,
                }

        for key in self.THREAD_KEYS:
            value = user_memory.get(key)

            if value:
                return {
                    "source": "user_memory",
                    "key": key,
                    "value": value,
                }

        return None

    def _blocked(
        self,
        reason: str,
        extra: dict | None = None,
    ):
        result = {
            "success": False,
            "blocked": True,
            "target_safe": False,
            "reason": reason,
        }

        if extra:
            result.update(extra)

        return result