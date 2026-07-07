import unittest
from pathlib import Path


class CMSUploadPublishingBoundaryTests(unittest.TestCase):
    def test_cms_upload_uses_publishing_service_not_fanvue_services(self):
        source = Path("app/dashboard/pages/cms_upload.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("PublishingService", source)
        self.assertIn("upload_asset_media_item", source)
        self.assertIn("create_wall_post", source)
        self.assertNotIn("FanvueMediaUploadService", source)
        self.assertNotIn("FanvueAPIService", source)
        self.assertNotIn("fanvue_media_upload_service", source)
        self.assertNotIn("fanvue_api_service", source)
        self.assertNotIn(".upload_media_item(", source)


if __name__ == "__main__":
    unittest.main()

