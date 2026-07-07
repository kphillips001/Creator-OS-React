import unittest
from typing import get_type_hints

from app.providers.publishing import (
    FanvuePublishingProvider,
    PublishingProvider,
    PublishingProviderCapabilities,
)
from app.providers.publishing import base as provider_base


class FakeUploader:
    def __init__(self, *, fanvue_account_id=None):
        self.fanvue_account_id = fanvue_account_id
        self.calls = []

    def upload_media_item(self, item):
        self.calls.append(item)
        if "preview" in item["file_path"]:
            return {
                "success": True,
                "media_uuid": "preview-media",
                "preview_uuid": "preview-id",
                "status": "uploaded",
            }
        return {
            "success": True,
            "media_uuid": "full-media",
            "full_uuid": "full-id",
            "status": "uploaded",
            }


class FakeApi:
    def __init__(self, *, fanvue_account_id=None):
        self.fanvue_account_id = fanvue_account_id
        self.calls = []

    def create_wall_post(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "success": True,
            "sent": True,
            "payload": kwargs,
        }


class PublishingProviderFoundationTests(unittest.TestCase):
    def test_fanvue_provider_satisfies_publishing_provider_contract(self):
        provider: PublishingProvider = FanvuePublishingProvider(
            media_upload_service_factory=lambda **_: FakeUploader()
        )

        self.assertEqual(provider.provider_name, "fanvue")
        self.assertIsNone(provider.get_publishing_status(None))
        self.assertIsNone(provider.get_upload_status(None))

    def test_publishing_provider_contract_exposes_neutral_capabilities(self):
        contract_methods = {
            name
            for name, value in PublishingProvider.__dict__.items()
            if callable(value) and not name.startswith("_")
        }

        self.assertIn("publish_media_item", contract_methods)
        self.assertIn("get_upload_status", contract_methods)
        self.assertIn("normalize_provider_response", contract_methods)
        self.assertIn("retrieve_provider_output", contract_methods)
        self.assertIn("get_capabilities", contract_methods)
        self.assertEqual(
            get_type_hints(provider_base.PublishingProvider.get_capabilities)["return"],
            PublishingProviderCapabilities,
        )

    def test_fanvue_provider_wraps_existing_upload_service(self):
        uploaders = []

        def factory(*, fanvue_account_id=None):
            uploader = FakeUploader(fanvue_account_id=fanvue_account_id)
            uploaders.append(uploader)
            return uploader

        provider = FanvuePublishingProvider(
            media_upload_service_factory=factory,
        )

        result = provider.publish(
            asset_id=22,
            provider_account_id=9,
            preview_path="data/previews/22_preview.jpg",
            full_path="data/uploads/22_full.jpg",
            classification="PREMIUM",
        )

        self.assertTrue(result["success"])
        self.assertEqual(uploaders[0].fanvue_account_id, 9)
        self.assertEqual(
            uploaders[0].calls,
            [
                {
                    "id": 22,
                    "file_path": "data/previews/22_preview.jpg",
                    "classification": "PREMIUM",
                },
                {
                    "id": 22,
                    "file_path": "data/uploads/22_full.jpg",
                    "classification": "PREMIUM",
                },
            ],
        )

    def test_fanvue_provider_publishes_single_media_item(self):
        uploaders = []

        def factory(*, fanvue_account_id=None):
            uploader = FakeUploader(fanvue_account_id=fanvue_account_id)
            uploaders.append(uploader)
            return uploader

        provider = FanvuePublishingProvider(
            media_upload_service_factory=factory,
        )

        result = provider.publish_media_item(
            provider_account_id=9,
            item={
                "id": 22,
                "file_path": "data/uploads/22_full.jpg",
                "classification": "PREMIUM",
            },
        )

        self.assertTrue(result["success"])
        self.assertEqual(uploaders[0].fanvue_account_id, 9)
        self.assertEqual(
            uploaders[0].calls,
            [
                {
                    "id": 22,
                    "file_path": "data/uploads/22_full.jpg",
                    "classification": "PREMIUM",
                }
            ],
        )

    def test_fanvue_provider_creates_wall_post_through_api_service(self):
        apis = []

        def api_factory(*, fanvue_account_id=None):
            api = FakeApi(fanvue_account_id=fanvue_account_id)
            apis.append(api)
            return api

        provider = FanvuePublishingProvider(api_service_factory=api_factory)

        result = provider.create_wall_post(
            provider_account_id=9,
            text="hello",
            media_ids=["media-1"],
            audience="followers-and-subscribers",
        )

        self.assertTrue(result["success"])
        self.assertEqual(apis[0].fanvue_account_id, 9)
        self.assertEqual(
            apis[0].calls,
            [
                {
                    "text": "hello",
                    "media_uuids": ["media-1"],
                    "audience": "followers-and-subscribers",
                }
            ],
        )

    def test_normalizes_fanvue_upload_response_to_provider_fields(self):
        provider = FanvuePublishingProvider()

        payload = provider.normalize_provider_response(
            {
                "success": True,
                "media_uuid": "media",
                "preview_uuid": None,
                "full_uuid": "full",
                "status": None,
            },
            default_status="uploaded",
        )

        self.assertEqual(payload["provider_status"], "uploaded")
        self.assertEqual(payload["provider_media_id"], "media")
        self.assertEqual(payload["provider_preview_media_id"], "media")
        self.assertEqual(payload["provider_full_media_id"], "full")
        self.assertIsNone(payload["provider_error"])
        self.assertEqual(payload["provider_metadata"]["media_uuid"], "media")

    def test_status_and_output_read_provider_neutral_record_fields(self):
        provider = FanvuePublishingProvider()
        record = {
            "provider_status": "uploaded",
            "provider_output_url": "https://fanvue.example/media",
        }

        self.assertEqual(provider.get_publishing_status(record), "uploaded")
        self.assertEqual(provider.get_upload_status(record), "uploaded")
        self.assertEqual(
            provider.retrieve_provider_output(record),
            "https://fanvue.example/media",
        )

    def test_fanvue_provider_reports_compatibility_capabilities(self):
        capabilities = FanvuePublishingProvider().get_capabilities()

        self.assertTrue(capabilities.uploads)
        self.assertTrue(capabilities.upload_status)
        self.assertTrue(capabilities.provider_metadata)
        self.assertTrue(capabilities.provider_media_id)
        self.assertTrue(capabilities.provider_output_url)
        self.assertTrue(capabilities.provider_error)
        self.assertTrue(capabilities.retry)
        self.assertTrue(capabilities.manual_media_link)
        self.assertTrue(capabilities.wall_posts)

    def test_update_and_delete_are_controlled_unsupported_operations(self):
        provider = FanvuePublishingProvider()

        self.assertEqual(
            provider.update({"id": "record"}, {"provider_status": "retrying"})[
                "reason"
            ],
            "provider_update_not_supported",
        )
        self.assertEqual(
            provider.delete({"id": "record"})["reason"],
            "provider_delete_not_supported",
        )


if __name__ == "__main__":
    unittest.main()
