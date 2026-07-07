from app.repositories.cms_fanvue_upload_repository import (
    create_or_get_upload_link,
    get_upload_link,
    update_upload_link_status,
)

from app.services.fanvue_vault_assignment_service import FanvueVaultAssignmentService


class CMSFanvueUploadLinkService:
    """
    Fanvue-specific publishing link service.

    This is close to a future provider publishing record, but remains
    content-item and Fanvue named for Phase 1 compatibility.
    """

    def __init__(self):
        self.vault_assignment_service = FanvueVaultAssignmentService()

    def create_upload_link(
        self,
        content_item_id: int,
        fanvue_account_id: int,
        upload_intent: str | None = None,
        delivery_method: str | None = None,
    ) -> dict:
        print("[13C/13D CREATE CMS → FANVUE UPLOAD LINK]")
        print(f"content_item_id={content_item_id}")
        print(f"fanvue_account_id={fanvue_account_id}")
        print(f"upload_intent={upload_intent}")
        print(f"delivery_method={delivery_method}")

        destination = None
        vault_folder_id = None
        resolved_delivery_method = delivery_method

        if upload_intent:
            assignment = self.vault_assignment_service.assign_destination(
                upload_intent=upload_intent,
                delivery_method=delivery_method,
            )

            destination = assignment.get("destination")
            vault_folder_id = assignment.get("vault_folder")
            resolved_delivery_method = assignment.get("delivery_method")

            print("[13D ASSIGNMENT]")
            print(assignment)

        return create_or_get_upload_link(
            content_item_id=content_item_id,
            fanvue_account_id=fanvue_account_id,
            upload_status="pending",
            destination=destination,
            delivery_method=resolved_delivery_method,
            vault_folder_id=vault_folder_id,
        )

    def get_upload_link(
        self,
        content_item_id: int,
        fanvue_account_id: int,
    ) -> dict | None:
        return get_upload_link(
            content_item_id=content_item_id,
            fanvue_account_id=fanvue_account_id,
        )

    def mark_uploading(
        self,
        content_item_id: int,
        fanvue_account_id: int,
    ) -> dict:
        return update_upload_link_status(
            content_item_id=content_item_id,
            fanvue_account_id=fanvue_account_id,
            upload_status="uploading",
        )

    def mark_uploaded(
        self,
        content_item_id: int,
        fanvue_account_id: int,
        fanvue_media_uuid: str,
        fanvue_preview_media_uuid: str | None = None,
        fanvue_full_media_uuid: str | None = None,
        vault_folder_id: str | None = None,
        destination: str | None = None,
        delivery_method: str | None = None,
    ) -> dict:
        return update_upload_link_status(
            content_item_id=content_item_id,
            fanvue_account_id=fanvue_account_id,
            upload_status="uploaded",
            destination=destination,
            delivery_method=delivery_method,
            fanvue_media_uuid=fanvue_media_uuid,
            fanvue_preview_media_uuid=fanvue_preview_media_uuid,
            fanvue_full_media_uuid=fanvue_full_media_uuid,
            vault_folder_id=vault_folder_id,
        )

    def mark_failed(
        self,
        content_item_id: int,
        fanvue_account_id: int,
        error_message: str,
    ) -> dict:
        return update_upload_link_status(
            content_item_id=content_item_id,
            fanvue_account_id=fanvue_account_id,
            upload_status="failed",
            error_message=error_message,
        )
