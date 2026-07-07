from app.repositories.content_usage_repository import has_user_seen_content


class PayloadBuilderService:
    def __init__(self):
        pass

    def build_paid_ppv_payload(
        self,
        fanvue_account_id: int,
        fanvue_user_uuid: str,
        content_item: dict,
        caption: str,
        price: float,
        sending_message_uuid: str,
    ) -> dict | None:
        """
        Builds Fanvue paid PPV payload.

        ⚠️ DOES NOT SEND — only builds payload.

        Returns:
            dict payload OR None if blocked by duplicate protection
        """

        content_item_id = content_item.get("id")

        if not content_item_id:
            raise ValueError("content_item missing id")

        seen = has_user_seen_content(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_uuid,  # 🔥 SAME VARIABLE, NEW PARAM NAME
            content_item_id=content_item_id,
        )

        if seen:
            print("[DUPLICATE BLOCKED] Content already seen by user")
            return None

        preview_uuid = (
            content_item.get("fanvue_preview_media_uuid")
            or content_item.get("fanvue_media_preview_uuid")
        )

        full_uuid = (
            content_item.get("fanvue_full_media_uuid")
            or content_item.get("fanvue_media_full_uuid")
        )

        if not preview_uuid or not full_uuid:
            raise ValueError("Missing Fanvue media UUIDs on content item")

        payload = {
            "recipientUuid": fanvue_user_uuid,
            "message": caption,
            "mediaPreviewUuid": preview_uuid,
            "mediaUuids": [full_uuid],
            "price": int(float(price) * 100),
            "sendingMessageUuid": sending_message_uuid,
        }

        print("[PAYLOAD BUILT - PAID PPV]")
        print(payload)

        return payload