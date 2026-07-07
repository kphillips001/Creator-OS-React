from app.repositories.automated_reaction_repository import (
    create_automated_reaction_log,
)


class AutomatedReactionPersistenceService:
    """
    3D.18.10 — Outbound Reaction Persistence

    Persists automated reaction attempts locally before any
    Fanvue outbound send is attempted.

    This supports:
    - audit history
    - duplicate protection
    - retry visibility
    - blocked-send visibility
    - dry-run tracking
    """

    def persist_reaction(
        self,
        message_payload: dict,
        execution_mode_result: dict | None = None,
        status: str = "planned",
        blocked_reason: str | None = None,
    ):
        if not message_payload:
            return self._blocked("missing_message_payload")

        reaction_type = message_payload.get("reaction_type")

        if not reaction_type:
            return self._blocked("missing_reaction_type")

        execution_mode_result = execution_mode_result or {}

        reaction_payload = {
            "external_event_id": message_payload.get("external_event_id"),
            "fanvue_user_id": message_payload.get("fanvue_user_id"),
            "fanvue_account_id": message_payload.get("fanvue_account_id"),
            "local_user_id": message_payload.get("local_user_id"),
            "reaction_type": reaction_type,
            "message_text": message_payload.get("message_text"),
            "status": status,
            "execution_mode": execution_mode_result.get("execution_mode"),
            "blocked_reason": blocked_reason,
            "message_payload": message_payload,
            "execution_mode_result": execution_mode_result,
        }

        reaction_id = create_automated_reaction_log(
            reaction_payload
        )

        return {
            "success": True,
            "blocked": False,
            "persisted": True,
            "reaction_id": reaction_id,
            "reaction_type": reaction_type,
            "status": status,
            "execution_mode": execution_mode_result.get("execution_mode"),
            "reason": "reaction_persisted",
        }

    def _blocked(
        self,
        reason: str,
    ):
        return {
            "success": False,
            "blocked": True,
            "persisted": False,
            "reason": reason,
        }