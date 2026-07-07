from app.repositories.outreach_queue_repository import (
    fetch_due_outreach_queue,
    mark_outreach_processing,
    mark_outreach_completed,
    mark_outreach_failed,
)

from app.services.outreach_service import (
    OutreachService,
)

from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)


class OutreachWorkerService:

    def __init__(self):

        self.outreach_service = (
            OutreachService()
        )

        self.global_safety_service = (
            GlobalAutomationSafetyService()
        )

    def process_outreach_queue(
        self,
        limit: int = 25,
    ) -> dict:

        queue_items = (
            fetch_due_outreach_queue(
                limit=limit,
            )
        )

        processed = []
        failed = []

        for item in queue_items:

            queue_id = item["id"]

            try:

                mark_outreach_processing(
                    queue_id
                )

                # ==================================================
                # Outreach Safety Enforcement
                # ==================================================

                safety_result = (
                    self.global_safety_service
                    .can_send_outreach()
                )

                if not safety_result.get(
                    "allowed",
                    False,
                ):
                    raise Exception(
                        safety_result.get(
                            "reason",
                            "outreach_automation_blocked",
                        )
                    )

                # ==================================================
                # Existing outreach execution layer
                # will be wired into live send orchestration later.
                # ==================================================

                result = {
                    "success": True,
                }

                if not result.get(
                    "success",
                    False,
                ):
                    raise Exception(
                        result.get(
                            "reason",
                            "outreach_failed",
                        )
                    )

                completed = (
                    mark_outreach_completed(
                        queue_id
                    )
                )

                processed.append(
                    completed
                )

            except Exception as e:

                failed_item = (
                    mark_outreach_failed(
                        queue_id=queue_id,
                        error_message=str(e),
                        retry=True,
                    )
                )

                failed.append(
                    failed_item
                )

        return {
            "success": True,
            "processed_count": len(
                processed
            ),
            "failed_count": len(
                failed
            ),
            "processed": processed,
            "failed": failed,
        }