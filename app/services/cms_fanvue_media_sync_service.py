from app.services.publishing_service import PublishingService


class CMSFanvueMediaSyncService:
    def __init__(
        self,
        *,
        publishing_service: PublishingService | None = None,
        upload_link_service=None,
    ):
        self.publishing_service = publishing_service or PublishingService()
        if upload_link_service is None:
            from app.services.cms_fanvue_upload_link_service import (
                CMSFanvueUploadLinkService,
            )

            upload_link_service = CMSFanvueUploadLinkService()
        self.upload_link_service = upload_link_service

    def upload_and_store_media_ids(
        self,
        content_item: dict,
        fanvue_account_id: int,
        upload_intent: str | None = None,
        delivery_method: str | None = None,
    ) -> dict:
        """
        13E — Upload CMS media to Fanvue and store returned media UUIDs.
        """

        content_item_id = content_item.get("id")

        print("[13E MEDIA ID STORAGE START]")
        print(f"content_item_id={content_item_id}")
        print(f"fanvue_account_id={fanvue_account_id}")
        print(f"upload_intent={upload_intent}")
        print(f"delivery_method={delivery_method}")

        if not content_item_id:
            return {
                "success": False,
                "reason": "missing_content_item_id",
            }

        upload_link = self.upload_link_service.create_upload_link(
            content_item_id=content_item_id,
            fanvue_account_id=fanvue_account_id,
            upload_intent=upload_intent,
            delivery_method=delivery_method,
        )

        self.upload_link_service.mark_uploading(
            content_item_id=content_item_id,
            fanvue_account_id=fanvue_account_id,
        )

        upload_result = self.publishing_service.upload_asset_media_item(
            fanvue_account_id=fanvue_account_id,
            item=content_item,
        )

        if not upload_result.get("success"):
            self.upload_link_service.mark_failed(
                content_item_id=content_item_id,
                fanvue_account_id=fanvue_account_id,
                error_message=str(upload_result.get("error")),
            )

            return {
                "success": False,
                "reason": "fanvue_upload_failed",
                "upload_result": upload_result,
            }

        media_uuid = upload_result.get("media_uuid")
        preview_uuid = upload_result.get("preview_uuid") or media_uuid
        full_uuid = upload_result.get("full_uuid") or media_uuid

        updated_link = self.upload_link_service.mark_uploaded(
            content_item_id=content_item_id,
            fanvue_account_id=fanvue_account_id,
            fanvue_media_uuid=media_uuid,
            fanvue_preview_media_uuid=preview_uuid,
            fanvue_full_media_uuid=full_uuid,
            vault_folder_id=upload_link.get("vault_folder_id"),
            destination=upload_link.get("destination"),
            delivery_method=upload_link.get("delivery_method"),
        )

        print("[13E MEDIA IDS STORED]")
        print(updated_link)

        return {
            "success": True,
            "content_item_id": content_item_id,
            "media_uuid": media_uuid,
            "preview_uuid": preview_uuid,
            "full_uuid": full_uuid,
            "upload_link": updated_link,
            "upload_result": upload_result,
        }
