from uuid import uuid4

from app.repositories.wall_post_repository import claim_due_items, renew_claim, release_claim, complete_claim, fail_claim, mark_wall_content_posted

from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)


class WallWorkerService:

    def __init__(self, worker_instance_id: str | None = None):

        self.worker_instance_id = worker_instance_id or f"wall-worker-{uuid4()}"

        self.global_safety_service = (
            GlobalAutomationSafetyService()
        )

    # =====================================================
    # PROCESS WALL QUEUE
    # =====================================================

    def process_wall_queue(
        self,
        limit: int = 10,
    ) -> dict:

        global_result = self.global_safety_service.check_global_safety()
        if not global_result.get("allowed", False):
            return {
                "success": True, "blocked": True,
                "reason": global_result.get("reason"),
                "processed_count": 0, "failed_count": 0,
            }

        queue_items = (
            claim_due_items(worker_instance_id=self.worker_instance_id, limit=limit)
        )

        processed = []
        failed = []

        for item in queue_items:

            queue_id = item["id"]

            try:

                # =========================================
                # MARK PROCESSING
                # =========================================

                if not renew_claim(queue_id, worker_instance_id=self.worker_instance_id):
                    continue

                # =========================================
                # GLOBAL SAFETY CHECK
                # =========================================

                safety_result = (
                    self.global_safety_service
                    .check_global_safety()
                )

                if not safety_result.get(
                    "allowed",
                    False,
                ):
                    release_claim(queue_id, worker_instance_id=self.worker_instance_id)
                    continue

                # =========================================
                # PLACEHOLDER WALL POST EXECUTION
                # =========================================

                # IMPORTANT:
                # Live Fanvue wall posting
                # integration comes later.
                #
                # For now:
                # validate worker lifecycle.

                fake_post_uuid = (
                    f"wall_post_"
                    f"{queue_id}"
                )

                # =========================================
                # MARK CONTENT POSTED
                # =========================================

                mark_wall_content_posted(
                    fanvue_account_id=item[
                        "fanvue_account_id"
                    ],
                    content_item_id=item[
                        "content_item_id"
                    ],
                    delivery_method=(
                        "scheduled_worker"
                    ),
                    fanvue_post_uuid=(
                        fake_post_uuid
                    ),
                )

                # =========================================
                # MARK COMPLETED
                # =========================================

                completed = (
                    complete_claim(queue_id, worker_instance_id=self.worker_instance_id)
                )

                processed.append(
                    completed
                )

            except Exception as e:

                failed_result = (
                    fail_claim(
                        queue_id=queue_id,
                        worker_instance_id=self.worker_instance_id,
                        error_message=str(e),
                        retry=True,
                    )
                )

                failed.append(
                    failed_result
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
