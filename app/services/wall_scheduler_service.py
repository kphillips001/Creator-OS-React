from datetime import datetime

from app.repositories.wall_post_repository import (
    has_wall_content_been_used,
    enqueue_wall_post,
)


class WallSchedulerService:

    # =====================================================
    # SCHEDULE WALL POST
    # =====================================================

    def schedule_wall_post(
        self,
        fanvue_account_id: int,
        content_item_id: int,
        scheduled_for: datetime,
    ) -> dict:

        # =================================================
        # DUPLICATE PROTECTION
        # =================================================

        already_used = (
            has_wall_content_been_used(
                fanvue_account_id=fanvue_account_id,
                content_item_id=content_item_id,
            )
        )

        if already_used:
            return {
                "success": False,
                "reason": (
                    "wall_content_already_used"
                ),
            }

        # =================================================
        # CREATE QUEUE ITEM
        # =================================================

        queue_item = enqueue_wall_post(
            fanvue_account_id=fanvue_account_id,
            content_item_id=content_item_id,
            scheduled_for=scheduled_for,
        )

        return {
            "success": True,
            "queue_item": queue_item,
        }