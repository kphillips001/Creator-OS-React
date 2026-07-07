import unittest
from pathlib import Path

from app.services.cms_fanvue_media_sync_service import CMSFanvueMediaSyncService


class FakePublishingService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def upload_asset_media_item(self, *, fanvue_account_id, item):
        self.calls.append(
            {
                "fanvue_account_id": fanvue_account_id,
                "item": item,
            }
        )
        return dict(self.result)


class FakeUploadLinkService:
    def __init__(self):
        self.calls = []

    def create_upload_link(
        self,
        *,
        content_item_id,
        fanvue_account_id,
        upload_intent=None,
        delivery_method=None,
    ):
        self.calls.append(
            (
                "create",
                content_item_id,
                fanvue_account_id,
                upload_intent,
                delivery_method,
            )
        )
        return {
            "vault_folder_id": "folder-1",
            "destination": "wall",
            "delivery_method": "wall_post",
        }

    def mark_uploading(self, *, content_item_id, fanvue_account_id):
        self.calls.append(("uploading", content_item_id, fanvue_account_id))
        return {"status": "uploading"}

    def mark_uploaded(
        self,
        *,
        content_item_id,
        fanvue_account_id,
        fanvue_media_uuid,
        fanvue_preview_media_uuid=None,
        fanvue_full_media_uuid=None,
        vault_folder_id=None,
        destination=None,
        delivery_method=None,
    ):
        self.calls.append(
            (
                "uploaded",
                content_item_id,
                fanvue_account_id,
                fanvue_media_uuid,
                fanvue_preview_media_uuid,
                fanvue_full_media_uuid,
                vault_folder_id,
                destination,
                delivery_method,
            )
        )
        return {"status": "uploaded"}

    def mark_failed(self, *, content_item_id, fanvue_account_id, error_message):
        self.calls.append(
            ("failed", content_item_id, fanvue_account_id, error_message)
        )
        return {"status": "failed"}


class PublishingWorkflowCleanupTests(unittest.TestCase):
    def test_content_classification_uses_publishing_service_boundary(self):
        source = Path("app/services/content_classification_service.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("PublishingService", source)
        self.assertIn("upload_asset_media_item", source)
        self.assertIn("record_asset_upload_payload", source)
        self.assertNotIn("FanvueMediaUploadService", source)
        self.assertNotIn("fanvue_media_upload_service", source)
        self.assertNotIn("update_content_fanvue_upload_result", source)
        self.assertNotIn(".upload_media_item(", source)

    def test_content_send_wall_post_uses_publishing_service_boundary(self):
        source = Path("app/services/content_send_service.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("PublishingService", source)
        self.assertIn("create_wall_post", source)
        self.assertNotIn("FanvueAPIService", source)
        self.assertNotIn("fanvue_api_service", source)

    def test_cms_fanvue_media_sync_delegates_upload_to_publishing_service(self):
        publishing = FakePublishingService(
            {
                "success": True,
                "media_uuid": "media-1",
                "preview_uuid": "preview-1",
                "full_uuid": "full-1",
            }
        )
        upload_links = FakeUploadLinkService()
        service = CMSFanvueMediaSyncService(
            publishing_service=publishing,
            upload_link_service=upload_links,
        )

        result = service.upload_and_store_media_ids(
            {"id": 44, "file_path": "asset.jpg"},
            fanvue_account_id=7,
            upload_intent="wall_image",
            delivery_method="wall_post",
        )

        self.assertTrue(result["success"])
        self.assertEqual(
            publishing.calls,
            [
                {
                    "fanvue_account_id": 7,
                    "item": {"id": 44, "file_path": "asset.jpg"},
                }
            ],
        )
        self.assertIn(
            (
                "uploaded",
                44,
                7,
                "media-1",
                "preview-1",
                "full-1",
                "folder-1",
                "wall",
                "wall_post",
            ),
            upload_links.calls,
        )

    def test_cms_fanvue_media_sync_marks_failed_uploads(self):
        publishing = FakePublishingService(
            {
                "success": False,
                "error": "timeout",
            }
        )
        upload_links = FakeUploadLinkService()
        service = CMSFanvueMediaSyncService(
            publishing_service=publishing,
            upload_link_service=upload_links,
        )

        result = service.upload_and_store_media_ids(
            {"id": 45, "file_path": "asset.jpg"},
            fanvue_account_id=7,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "fanvue_upload_failed")
        self.assertIn(("failed", 45, 7, "timeout"), upload_links.calls)


if __name__ == "__main__":
    unittest.main()
