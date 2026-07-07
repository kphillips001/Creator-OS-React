import unittest
from types import SimpleNamespace

from app.services.publishing_state_service import (
    FANVUE_STATUS_FAILED,
    FANVUE_STATUS_NOT_UPLOADED,
    FANVUE_STATUS_UPLOADED,
    FANVUE_STATUS_URL_AVAILABLE,
    fanvue_asset_status,
    fanvue_media_uuid,
    fanvue_product_status,
    has_fanvue_media,
    product_has_provider_url,
)


class PublishingStateServiceTests(unittest.TestCase):
    def asset(self, **overrides):
        values = {
            "fanvue_media_preview_uuid": None,
            "fanvue_media_full_uuid": None,
            "fanvue_upload_status": None,
            "fanvue_upload_error": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def product(self, media_link=None):
        return SimpleNamespace(media_link=media_link)

    def test_missing_asset_is_not_uploaded(self):
        self.assertEqual(
            fanvue_asset_status(None),
            (FANVUE_STATUS_NOT_UPLOADED, "No local asset is attached."),
        )

    def test_failed_asset_prefers_error_detail(self):
        self.assertEqual(
            fanvue_asset_status(
                self.asset(
                    fanvue_upload_status="completed",
                    fanvue_upload_error="timeout",
                )
            ),
            (FANVUE_STATUS_FAILED, "timeout"),
        )

    def test_failed_status_without_error_uses_status_detail(self):
        self.assertEqual(
            fanvue_asset_status(self.asset(fanvue_upload_status="failed")),
            (FANVUE_STATUS_FAILED, "failed"),
        )

    def test_media_uuid_prefers_full_over_preview(self):
        asset = self.asset(
            fanvue_media_preview_uuid="preview-uuid",
            fanvue_media_full_uuid="full-uuid",
        )

        self.assertTrue(has_fanvue_media(asset))
        self.assertEqual(fanvue_media_uuid(asset), "full-uuid")
        self.assertEqual(
            fanvue_asset_status(asset),
            (FANVUE_STATUS_UPLOADED, "full-uuid"),
        )

    def test_product_provider_url_takes_precedence(self):
        product = self.product("https://fanvue.example/media")

        self.assertTrue(product_has_provider_url(product))
        self.assertEqual(
            fanvue_product_status(product, []),
            (FANVUE_STATUS_URL_AVAILABLE, "https://fanvue.example/media"),
        )

    def test_product_status_rolls_up_asset_state(self):
        uploaded = self.asset(fanvue_media_full_uuid="full-uuid")
        pending = self.asset()
        failed = self.asset(fanvue_upload_status="failed")

        self.assertEqual(
            fanvue_product_status(None, [uploaded, uploaded]),
            (FANVUE_STATUS_UPLOADED, "All attached assets have Fanvue media IDs."),
        )
        self.assertEqual(
            fanvue_product_status(None, [uploaded, pending]),
            (FANVUE_STATUS_UPLOADED, "Some attached assets have Fanvue media IDs."),
        )
        self.assertEqual(
            fanvue_product_status(None, [pending]),
            (FANVUE_STATUS_NOT_UPLOADED, "Local asset only"),
        )
        self.assertEqual(
            fanvue_product_status(None, [failed, uploaded]),
            (FANVUE_STATUS_FAILED, "At least one asset failed upload."),
        )


if __name__ == "__main__":
    unittest.main()
