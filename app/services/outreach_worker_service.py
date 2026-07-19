from uuid import uuid4

from app.repositories.outreach_queue_repository import claim_due_items, renew_claim, release_claim, complete_claim, fail_claim

from app.services.outreach_service import (
    OutreachService,
)

from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)


class OutreachWorkerService:

    def __init__(self, worker_instance_id: str | None = None):

        self.worker_instance_id = worker_instance_id or f"outreach-{uuid4()}"

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

        global_result = self.global_safety_service.check_global_safety()
        if not global_result.get("allowed", False):
            return {
                "success": True, "blocked": True,
                "reason": global_result.get("reason"),
                "processed_count": 0, "failed_count": 0,
                "processed": [], "failed": [],
            }

        queue_items = (
            claim_due_items(worker_instance_id=self.worker_instance_id, limit=limit)
        )

        processed = []
        failed = []

        for item in queue_items:

            queue_id = item["id"]

            try:

                if not renew_claim(queue_id, worker_instance_id=self.worker_instance_id):
                    continue

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
                    release_claim(queue_id, worker_instance_id=self.worker_instance_id)
                    continue

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
                    complete_claim(queue_id, worker_instance_id=self.worker_instance_id)
                )

                processed.append(
                    completed
                )

            except Exception as e:

                failed_item = (
                    fail_claim(
                        queue_id=queue_id,
                        worker_instance_id=self.worker_instance_id,
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
