from app.services.content_payload_builder_service import ContentPayloadBuilderService
from app.services.content_media_delivery_service import ContentMediaDeliveryService
from app.services.global_automation_safety_service import GlobalAutomationSafetyService
from app.services.global_send_execution_guard_service import GlobalSendExecutionGuardService
from app.services.publishing_service import PublishingService

from app.repositories.wall_post_repository import (
    has_wall_content_been_used,
    mark_wall_content_posted,
)


class ContentSendService:
    def __init__(
        self,
        fanvue_account_id: int,
    ):
        self.fanvue_account_id = fanvue_account_id

        self.media_service = ContentMediaDeliveryService()
        self.payload_builder = ContentPayloadBuilderService()

        self.publishing = PublishingService()

        self.global_safety = GlobalAutomationSafetyService()
        self.execution_guard = GlobalSendExecutionGuardService()

    def send_wall_post(
        self,
        fanvue_account_id: int,
        caption: str = "",
        dry_run: bool = True,
    ) -> dict:
        """
        13F-3.2 — Send wall post content with repost protection.

        Flow:
        - fetch valid wall media
        - skip content already posted/scheduled
        - build payload
        - dry run OR live send
        - mark posted after successful live send
        """

        if fanvue_account_id != self.fanvue_account_id:
            return {
                "success": False,
                "status": "blocked",
                "reason": "fanvue_account_id_mismatch",
                "service_account_id": self.fanvue_account_id,
                "requested_account_id": fanvue_account_id,
            }

        print("\n[13F SEND WALL POST START]")
        print(f"fanvue_account_id={fanvue_account_id}")
        print(f"dry_run={dry_run}")

        media_result = self.media_service.get_media_for_delivery(
            fanvue_account_id=fanvue_account_id,
            destination="wall",
            requested_delivery="wall_post",
            limit=10,
        )

        media_records = media_result.get("media", [])

        if not media_records:
            return {
                "success": False,
                "reason": "no_wall_media_available",
            }

        selected_record = None
        skipped_used = []

        for record in media_records:
            content_item_id = record.get("content_item_id")

            already_used = has_wall_content_been_used(
                fanvue_account_id=fanvue_account_id,
                content_item_id=content_item_id,
            )

            if already_used:
                print(f"[13F SKIP USED WALL CONTENT] content_item_id={content_item_id}")
                skipped_used.append(content_item_id)
                continue

            selected_record = record
            break

        if not selected_record:
            return {
                "success": False,
                "reason": "all_wall_media_already_used",
                "skipped_content_item_ids": skipped_used,
            }
        
        content_item_id = selected_record.get("content_item_id")

        print(f"[13F SELECTED CONTENT] content_item_id={content_item_id}")

        payload_result = self.payload_builder.build_wall_post_payload(
            content_record=selected_record,
            caption=caption,
        )

        if not payload_result.get("success"):
            return payload_result

        payload = payload_result

        print("[13F PAYLOAD BUILT]")
        print(payload)

        safety_result = self.global_safety.check_global_safety()

        execution_guard_result = self.execution_guard.validate_execution(
            execution_type="wall_post",
            safety_result=safety_result,
            content_guard_result=media_result,
            dry_run=dry_run,
        )

        if not execution_guard_result.get("allowed"):
            print("[13F WALL POST BLOCKED BY EXECUTION GUARD]")
            return {
                "success": False,
                "status": "blocked",
                "reason": execution_guard_result.get("reason"),
                "execution_guard_result": execution_guard_result,
                "payload": payload,
                "skipped_content_item_ids": skipped_used,
            }

        if dry_run:
            print("[13F DRY RUN — NOT SENDING]")
            return {
                "success": True,
                "mode": "dry_run",
                "payload": payload,
                "skipped_content_item_ids": skipped_used,
            }

        print("[13F SENDING TO FANVUE...]")

        response = self.publishing.create_wall_post(
            fanvue_account_id=fanvue_account_id,
            text=payload.get("caption"),
            media_ids=payload.get("media_uuids"),
            execution_origin="autonomous",
        )

        if not response.get("success"):
            return {
                "success": False,
                "reason": "fanvue_wall_post_failed",
                "fanvue_response": response,
                "payload": payload,
            }

        fanvue_post_uuid = response.get("post_uuid")

        posted_log = mark_wall_content_posted(
            fanvue_account_id=fanvue_account_id,
            content_item_id=content_item_id,
            delivery_method="post_now",
            fanvue_post_uuid=fanvue_post_uuid,
        )

        return {
            "success": True,
            "mode": "live",
            "fanvue_response": response,
            "content_item_id": content_item_id,
            "fanvue_post_uuid": fanvue_post_uuid,
            "posted_log": posted_log,
            "skipped_content_item_ids": skipped_used,
        }
