class AutomatedReactionBuyerSessionSafetyService:
    """
    3D.18.6 — Buyer Session Protection

    Prevents automated reactions from interrupting active
    buyer-session monetization flows.

    This service does NOT send anything.
    It only decides whether a reaction is safe during the
    current buyer-session state.
    """

    HARD_BLOCKED_STEPS = {
        "close",
        "close_mode",
        "controlled_ppv",
        "premium_upsell",
        "payment_pending",
    }

    SOFT_ALLOWED_REACTIONS = {
        "purchase_thank_you",
        "tip_thank_you",
        "subscription_welcome",
    }

    def validate_buyer_session_safety(
        self,
        reaction_type: str,
        runtime_state: dict | None = None,
        user_memory: dict | None = None,
    ):
        if not reaction_type:
            return self._blocked(
                "missing_reaction_type"
            )

        runtime_state = runtime_state or {}
        user_memory = user_memory or {}

        session_active = (
            runtime_state.get("buyer_session_active")
            or user_memory.get("buyer_session_active")
            or False
        )

        session_step = (
            runtime_state.get("buyer_session_step")
            or user_memory.get("buyer_session_step")
            or None
        )

        close_mode = (
            runtime_state.get("close_mode")
            or user_memory.get("close_mode")
            or False
        )

        if not session_active and not close_mode:
            return self._allowed(
                reaction_type=reaction_type,
                session_active=False,
                session_step=session_step,
                close_mode=False,
                reason="no_active_buyer_session",
            )

        if close_mode:
            if reaction_type in self.SOFT_ALLOWED_REACTIONS:
                return self._allowed(
                    reaction_type=reaction_type,
                    session_active=session_active,
                    session_step=session_step,
                    close_mode=True,
                    reason="soft_reaction_allowed_during_close_mode",
                    protected=True,
                )

            return self._blocked(
                "close_mode_reaction_blocked",
                {
                    "reaction_type": reaction_type,
                    "buyer_session_active": session_active,
                    "buyer_session_step": session_step,
                    "close_mode": True,
                },
            )

        if session_step in self.HARD_BLOCKED_STEPS:
            if reaction_type in self.SOFT_ALLOWED_REACTIONS:
                return self._allowed(
                    reaction_type=reaction_type,
                    session_active=session_active,
                    session_step=session_step,
                    close_mode=close_mode,
                    reason="soft_reaction_allowed_during_session",
                    protected=True,
                )

            return self._blocked(
                "buyer_session_reaction_blocked",
                {
                    "reaction_type": reaction_type,
                    "buyer_session_active": session_active,
                    "buyer_session_step": session_step,
                    "close_mode": close_mode,
                },
            )

        return self._allowed(
            reaction_type=reaction_type,
            session_active=session_active,
            session_step=session_step,
            close_mode=close_mode,
            reason="buyer_session_reaction_safe",
        )

    def _allowed(
        self,
        reaction_type: str,
        session_active: bool,
        session_step: str | None,
        close_mode: bool,
        reason: str,
        protected: bool = False,
    ):
        return {
            "success": True,
            "blocked": False,
            "buyer_session_safe": True,
            "reaction_type": reaction_type,
            "buyer_session_active": session_active,
            "buyer_session_step": session_step,
            "close_mode": close_mode,
            "protected_session": protected,
            "reason": reason,
        }

    def _blocked(
        self,
        reason: str,
        extra: dict | None = None,
    ):
        result = {
            "success": False,
            "blocked": True,
            "buyer_session_safe": False,
            "reason": reason,
        }

        if extra:
            result.update(extra)

        return result