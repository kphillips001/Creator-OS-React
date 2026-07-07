from datetime import datetime, timedelta, UTC

from app.repositories.outreach_queue_repository import (
    enqueue_outreach,
)

from app.services.outreach_service import (
    OutreachService,
)

from app.services.outreach_mass_ppv_coordination_service import (
    OutreachMassPPVCoordinationService,
)


class OutreachSchedulerService:
    def __init__(self):
        self.outreach_service = OutreachService()
        self.outreach_mass_ppv_coordination_service = (
            OutreachMassPPVCoordinationService()
        )

    def schedule_outreach(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        outreach_type: str = "reactivation",
        user_memory: dict | None = None,
    ) -> dict:
        user_memory = user_memory or {}

        enriched_memory = {
            **user_memory,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
        }

        coordination_result = (
            self.outreach_mass_ppv_coordination_service.evaluate(
                user_memory=enriched_memory,
            )
        )

        if not coordination_result.get("allow_outreach", False):
            return {
                "success": False,
                "reason": "outreach_suppressed_by_coordination",
                "coordination_result": coordination_result,
            }

        scheduled_for = datetime.now(UTC) + timedelta(minutes=5)

        queue_item = enqueue_outreach(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            outreach_type=outreach_type,
            scheduled_for=scheduled_for,
        )

        return {
            "success": True,
            "queue_item": queue_item,
            "coordination_result": coordination_result,
        }