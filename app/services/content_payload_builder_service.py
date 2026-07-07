from app.services.content_delivery_guard_service import ContentDeliveryGuardService


class ContentPayloadBuilderService:
    def __init__(self):
        self.guard_service = ContentDeliveryGuardService()

    def build_wall_post_payload(self, content_record: dict, caption: str = "") -> dict:
        guard = self.guard_service.validate_delivery(
            content_record=content_record,
            requested_delivery="wall_post",
        )

        if not guard.get("allowed"):
            return {"success": False, "reason": guard}

        media_uuid = content_record.get("fanvue_media_uuid")

        if not media_uuid:
            return {"success": False, "reason": "missing_fanvue_media_uuid"}

        return {
            "success": True,
            "payload_type": "wall_post",
            "content_item_id": content_record.get("content_item_id"),
            "caption": caption,
            "media_uuid": media_uuid,
            "media_uuids": [media_uuid],
            "destination": content_record.get("destination"),
            "vault_folder_id": content_record.get("vault_folder_id"),
        }

    def build_chat_teaser_payload(
        self,
        content_record: dict,
        caption: str = "",
        fanvue_account_id: int | None = None,
        fanvue_user_id: int | None = None,
        enforce_usage_guard: bool = False,
    ) -> dict:
        if enforce_usage_guard:
            guard = self.guard_service.can_deliver_content(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
                content_record=content_record,
                requested_delivery="chat_teaser",
            )
        else:
            guard = self.guard_service.validate_delivery(
                content_record=content_record,
                requested_delivery="chat_teaser",
            )

        if not guard.get("allowed"):
            return {"success": False, "reason": guard}

        preview_uuid = content_record.get("fanvue_preview_media_uuid")

        if not preview_uuid:
            return {"success": False, "reason": "missing_preview_media_uuid"}

        return {
            "success": True,
            "payload_type": "chat_teaser",
            "content_item_id": content_record.get("content_item_id"),
            "content_tag": guard.get("content_tag") or content_record.get("content_tag"),
            "text": caption,
            "preview_media_uuid": preview_uuid,
            "media_uuids": [preview_uuid],
            "is_paid": False,
            "destination": content_record.get("destination"),
            "vault_folder_id": content_record.get("vault_folder_id"),
        }

    def build_chat_ppv_payload(
        self,
        content_record: dict,
        caption: str = "",
        price: float = 9.99,
        fanvue_account_id: int | None = None,
        fanvue_user_id: int | None = None,
        enforce_usage_guard: bool = False,
    ) -> dict:
        if enforce_usage_guard:
            guard = self.guard_service.can_deliver_content(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
                content_record=content_record,
                requested_delivery="chat_ppv",
            )
        else:
            guard = self.guard_service.validate_delivery(
                content_record=content_record,
                requested_delivery="chat_ppv",
            )

        if not guard.get("allowed"):
            return {"success": False, "reason": guard}

        preview_uuid = content_record.get("fanvue_preview_media_uuid")
        full_uuid = content_record.get("fanvue_full_media_uuid")

        if not preview_uuid:
            return {"success": False, "reason": "missing_preview_media_uuid"}

        if not full_uuid:
            return {"success": False, "reason": "missing_full_media_uuid"}

        return {
            "success": True,
            "payload_type": "chat_ppv",
            "content_item_id": content_record.get("content_item_id"),
            "content_tag": guard.get("content_tag") or content_record.get("content_tag"),
            "text": caption,
            "preview_media_uuid": preview_uuid,
            "full_media_uuid": full_uuid,
            "price": price,
            "is_paid": True,
            "destination": content_record.get("destination"),
            "vault_folder_id": content_record.get("vault_folder_id"),
        }