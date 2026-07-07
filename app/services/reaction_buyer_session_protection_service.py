class ReactionBuyerSessionProtectionService:
    """
    3D.13.5 — Buyer Session Protection

    Prevents post-purchase automation from interfering with:

    - active buyer sessions
    - active escalation
    - live close flows
    - runtime intimacy progression
    - active DecisionEngine monetization

    IMPORTANT:
    This is NOT the same as the earlier Safety Gate.

    This service specifically protects:
    LIVE conversational monetization state.
    """

    BLOCKED_MODES = {
        "close_mode",
        "conversion_mode",
        "high_escalation",
    }

    def validate_session_safety(
        self,
        execution_plan: dict,
        user_memory: dict | None = None,
        runtime_state: dict | None = None,
    ):
        if not execution_plan:
            return self._blocked(
                "missing_execution_plan"
            )

        user_memory = user_memory or {}
        runtime_state = runtime_state or {}

        fanvue_user_id = execution_plan.get(
            "fanvue_user_id"
        )

        if not fanvue_user_id:
            return self._blocked(
                "missing_fanvue_user_id"
            )

        buyer_session_active = user_memory.get(
            "buyer_session_active",
            False,
        )

        if not buyer_session_active:
            return {
                "success": True,
                "blocked": False,
                "safe_to_execute": True,
                "reason": None,
                "fanvue_user_id": fanvue_user_id,
            }

        conversation_mode = runtime_state.get(
            "conversation_mode",
            "casual",
        )

        close_ready = runtime_state.get(
            "close_ready",
            False,
        )

        escalation_active = runtime_state.get(
            "escalation_active",
            False,
        )

        if conversation_mode in self.BLOCKED_MODES:
            return self._blocked(
                "protected_conversation_mode",
                {
                    "conversation_mode": conversation_mode,
                },
            )

        if close_ready:
            return self._blocked(
                "close_flow_active"
            )

        if escalation_active:
            return self._blocked(
                "runtime_escalation_active"
            )

        return {
            "success": True,
            "blocked": False,
            "safe_to_execute": True,
            "reason": None,
            "fanvue_user_id": fanvue_user_id,
            "conversation_mode": conversation_mode,
        }

    def _blocked(
        self,
        reason: str,
        extra: dict | None = None,
    ):
        result = {
            "success": False,
            "blocked": True,
            "safe_to_execute": False,
            "reason": reason,
        }

        if extra:
            result.update(extra)

        return result