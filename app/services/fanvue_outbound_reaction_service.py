import uuid
from datetime import datetime


class FanvueOutboundReactionService:
    """
    3D.13.11 — Fanvue Outbound Send Integration

    Builds outbound-safe delivery payloads
    for monetization reaction execution.

    IMPORTANT:
    This does NOT send Fanvue messages yet.

    It only prepares outbound delivery structures.
    """

    def build_outbound_reaction(
        self,
        reaction_payload: dict,
    ):
        if not reaction_payload:
            return self._blocked(
                "missing_reaction_payload"
            )

        fanvue_user_id = reaction_payload.get(
            "fanvue_user_id"
        )

        if not fanvue_user_id:
            return self._blocked(
                "missing_fanvue_user_id"
            )

        payload_type = reaction_payload.get(
            "payload_type"
        )

        if not payload_type:
            return self._blocked(
                "missing_payload_type"
            )

        outbound_id = str(uuid.uuid4())

        created_at = datetime.utcnow().isoformat()

        return {
            "success": True,
            "blocked": False,
            "outbound_id": outbound_id,
            "fanvue_user_id": fanvue_user_id,
            "payload_type": payload_type,
            "delivery_status": "prepared",
            "created_at": created_at,
            "reaction_payload": reaction_payload,
            "requires_gpt_generation": (
                reaction_payload.get(
                    "requires_gpt_generation",
                    True,
                )
            ),
            "send_immediately": (
                reaction_payload.get(
                    "send_immediately",
                    False,
                )
            ),
            "queue_for_delivery": (
                reaction_payload.get(
                    "queue_for_delivery",
                    True,
                )
            ),
            "worker_claimed": False,
            "delivery_attempts": 0,
            "max_delivery_attempts": 3,
        }

    def _blocked(
        self,
        reason: str,
    ):
        return {
            "success": False,
            "blocked": True,
            "reason": reason,
        }