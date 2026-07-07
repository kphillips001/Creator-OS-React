from app.repositories.wall_post_repository import (
    fetch_due_wall_post_queue,
    mark_wall_post_processing,
    mark_wall_post_completed,
    mark_wall_post_failed,
    mark_wall_content_posted,
)

from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)


class WallWorkerService:

    def __init__(self):

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

        queue_items = (
            fetch_due_wall_post_queue(
                limit=limit,
            )
        )

        processed = []
        failed = []

        for item in queue_items:

            queue_id = item["id"]

            try:

                # =========================================
                # MARK PROCESSING
                # =========================================

                mark_wall_post_processing(
                    queue_id
                )

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

                    raise Exception(
                        "Global automation "
                        "safety blocked "
                        "wall execution."
                    )

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
                    mark_wall_post_completed(
                        queue_id
                    )
                )

                processed.append(
                    completed
                )

            except Exception as e:

                failed_result = (
                    mark_wall_post_failed(
                        queue_id=queue_id,
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