import uuid
from datetime import datetime


class DelayedFollowupSchedulerService:
    """
    3D.13.10 — Delayed Followup Scheduler

    Builds scheduler-safe delayed followup records.

    IMPORTANT:
    This does NOT execute followups yet.

    It only prepares future execution structures.
    """

    def build_scheduled_followup(
        self,
        queue_payload: dict,
    ):
        if not queue_payload:
            return self._blocked(
                "missing_queue_payload"
            )

        fanvue_user_id = queue_payload.get(
            "fanvue_user_id"
        )

        if not fanvue_user_id:
            return self._blocked(
                "missing_fanvue_user_id"
            )

        execute_at = queue_payload.get(
            "execute_at"
        )

        if not execute_at:
            return self._blocked(
                "missing_execute_at"
            )

        scheduler_id = str(uuid.uuid4())

        created_at = datetime.utcnow().isoformat()

        return {
            "success": True,
            "blocked": False,
            "scheduler_id": scheduler_id,
            "schedule_type": (
                "delayed_followup"
            ),
            "status": "scheduled",
            "fanvue_user_id": fanvue_user_id,
            "execute_at": execute_at,
            "created_at": created_at,
            "retry_count": 0,
            "max_retries": 3,
            "queue_payload": queue_payload,
            "execution_locked": False,
            "worker_claimed": False,
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