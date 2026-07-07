from app.repositories.content_usage_repository import (
    has_user_seen_content,
    has_user_seen_content_tag,
)


class ContentDeliveryGuardService:
    """
    13F + 13G Guard Layer.
    """

    ALLOWED_DELIVERY = {
        "wall": ["wall_post"],
        "teaser": ["chat_teaser"],
        "vip": ["chat_ppv"],
        "premium": ["chat_ppv"],
    }

    def validate_destination_delivery(
        self,
        destination: str,
        requested_delivery: str,
    ) -> dict:
        destination = (destination or "").lower()
        requested_delivery = (requested_delivery or "").lower()

        allowed_deliveries = self.ALLOWED_DELIVERY.get(destination, [])

        print("[13F DELIVERY RULE CHECK]")
        print(f"destination={destination}")
        print(f"requested_delivery={requested_delivery}")
        print(f"allowed_deliveries={allowed_deliveries}")

        if destination not in self.ALLOWED_DELIVERY:
            return {
                "allowed": False,
                "reason": "unknown_destination",
                "destination": destination,
                "requested_delivery": requested_delivery,
                "allowed_deliveries": allowed_deliveries,
            }

        if requested_delivery not in allowed_deliveries:
            return {
                "allowed": False,
                "reason": "invalid_destination_for_delivery",
                "destination": destination,
                "requested_delivery": requested_delivery,
                "allowed_deliveries": allowed_deliveries,
            }

        return {
            "allowed": True,
            "destination": destination,
            "requested_delivery": requested_delivery,
            "allowed_deliveries": allowed_deliveries,
        }

    def validate_delivery(
        self,
        content_record: dict,
        requested_delivery: str,
    ) -> dict:
        destination = (content_record.get("destination") or "").lower()
        vault_folder_id = content_record.get("vault_folder_id")

        print("[13F DELIVERY GUARD]")
        print(f"destination={destination}")
        print(f"vault_folder_id={vault_folder_id}")
        print(f"requested_delivery={requested_delivery}")

        result = self.validate_destination_delivery(
            destination=destination,
            requested_delivery=requested_delivery,
        )

        if not result.get("allowed"):
            result["vault_folder_id"] = vault_folder_id
            return result

        return {
            "allowed": True,
            "destination": destination,
            "requested_delivery": requested_delivery,
            "vault_folder_id": vault_folder_id,
            "allowed_deliveries": result.get("allowed_deliveries", []),
        }

    def validate_upload_ready(self, content_record: dict) -> dict:
        upload_status = (content_record.get("upload_status") or "").lower()

        media_uuid = content_record.get("fanvue_media_uuid")
        preview_uuid = content_record.get("fanvue_preview_media_uuid")
        full_uuid = content_record.get("fanvue_full_media_uuid")

        print("[13G UPLOAD READY CHECK]")
        print(f"upload_status={upload_status}")
        print(f"fanvue_media_uuid={media_uuid}")
        print(f"fanvue_preview_media_uuid={preview_uuid}")
        print(f"fanvue_full_media_uuid={full_uuid}")

        if upload_status != "uploaded":
            return {
                "allowed": False,
                "reason": "content_not_uploaded",
                "upload_status": upload_status,
            }

        if not media_uuid and not preview_uuid and not full_uuid:
            return {
                "allowed": False,
                "reason": "missing_media_uuid",
                "upload_status": upload_status,
            }

        return {
            "allowed": True,
            "reason": "upload_ready",
            "upload_status": upload_status,
            "fanvue_media_uuid": media_uuid,
            "fanvue_preview_media_uuid": preview_uuid,
            "fanvue_full_media_uuid": full_uuid,
        }

    def validate_user_has_not_seen_content(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        content_record: dict,
    ) -> dict:
        content_item_id = content_record.get("content_item_id") or content_record.get("id")
        content_tag = (
            content_record.get("tag")
            or content_record.get("content_tag")
            or content_record.get("classification")
            or content_record.get("content_classification")
        )

        print("[13G DUPLICATE CONTENT CHECK]")
        print(f"fanvue_account_id={fanvue_account_id}")
        print(f"fanvue_user_id={fanvue_user_id}")
        print(f"content_item_id={content_item_id}")
        print(f"content_tag={content_tag}")

        if content_item_id:
            already_seen_content = has_user_seen_content(
                fanvue_account_id,
                fanvue_user_id,
                content_item_id,
            )

            if already_seen_content:
                return {
                    "allowed": False,
                    "reason": "duplicate_content_item",
                    "content_item_id": content_item_id,
                    "content_tag": content_tag,
                }

        if content_tag:
            already_seen_tag = has_user_seen_content_tag(
                fanvue_account_id,
                fanvue_user_id,
                content_tag,
            )

            if already_seen_tag:
                return {
                    "allowed": False,
                    "reason": "duplicate_content_tag",
                    "content_item_id": content_item_id,
                    "content_tag": content_tag,
                }

        return {
            "allowed": True,
            "reason": "content_not_seen",
            "content_item_id": content_item_id,
            "content_tag": content_tag,
        }

    def can_deliver_content(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        content_record: dict,
        requested_delivery: str,
    ) -> dict:
        print("[13G GLOBAL CONTENT DELIVERY GUARD]")
        print(f"fanvue_account_id={fanvue_account_id}")
        print(f"fanvue_user_id={fanvue_user_id}")
        print(f"requested_delivery={requested_delivery}")

        destination_result = self.validate_delivery(
            content_record=content_record,
            requested_delivery=requested_delivery,
        )

        if not destination_result.get("allowed"):
            return destination_result

        upload_result = self.validate_upload_ready(content_record)

        if not upload_result.get("allowed"):
            return upload_result

        duplicate_result = self.validate_user_has_not_seen_content(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            content_record=content_record,
        )

        if not duplicate_result.get("allowed"):
            return duplicate_result

        return {
            "allowed": True,
            "reason": "content_delivery_allowed",
            "destination": destination_result.get("destination"),
            "requested_delivery": requested_delivery,
            "vault_folder_id": destination_result.get("vault_folder_id"),
            "content_item_id": duplicate_result.get("content_item_id"),
            "content_tag": duplicate_result.get("content_tag"),
            "fanvue_media_uuid": upload_result.get("fanvue_media_uuid"),
            "fanvue_preview_media_uuid": upload_result.get("fanvue_preview_media_uuid"),
            "fanvue_full_media_uuid": upload_result.get("fanvue_full_media_uuid"),
        }