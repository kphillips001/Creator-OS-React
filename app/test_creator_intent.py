import importlib
import sys
import types
import unittest

from app.models.creator_intent import (
    CreatorContentType,
    CreatorIntent,
    normalize_creator_content_type,
)


class CreatorIntentTests(unittest.TestCase):
    def test_creator_intent_creation(self):
        intent = CreatorIntent.create(
            "PHOTOSHOOT",
            confirmed=True,
            override_active=True,
            notes="Use as a full shoot.",
            legacy_upload_intent="teaser_image",
        )

        self.assertEqual(intent.content_type, CreatorContentType.PHOTOSHOOT)
        self.assertTrue(intent.confirmed)
        self.assertTrue(intent.override_active)
        self.assertEqual(intent.notes, "Use as a full shoot.")
        self.assertEqual(intent.legacy_upload_intent, "teaser_image")
        self.assertEqual(intent.to_context()["owner"], "creator")

    def test_legacy_upload_intent_compatibility(self):
        intent = CreatorIntent.from_legacy("ppv_video")

        self.assertEqual(intent.content_type, CreatorContentType.SINGLE_ASSET)
        self.assertEqual(intent.legacy_upload_intent, "ppv_video")
        self.assertEqual(intent.to_legacy_upload_intent(), "ppv_video")

    def test_content_type_normalization(self):
        cases = {
            "single asset": CreatorContentType.SINGLE_ASSET,
            "photo_set": CreatorContentType.PHOTOSHOOT,
            "photoshoot": CreatorContentType.PHOTOSHOOT,
            "story": CreatorContentType.STORY,
            "collection": CreatorContentType.BUNDLE,
            "BUNDLE": CreatorContentType.BUNDLE,
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_creator_content_type(raw), expected)

    def test_cms_upload_creator_intent_creation(self):
        module_name = "app.dashboard.pages.cms_upload"
        sys.modules.pop(module_name, None)
        fake_streamlit = types.SimpleNamespace(
            session_state={},
            cache_data=lambda *args, **kwargs: (lambda fn: fn),
        )
        fake_publishing_module = types.ModuleType("app.services.publishing_service")

        class FakePublishingService:
            pass

        fake_publishing_module.PublishingService = FakePublishingService
        original_streamlit = sys.modules.get("streamlit")
        original_publishing = sys.modules.get("app.services.publishing_service")
        sys.modules["streamlit"] = fake_streamlit
        sys.modules["app.services.publishing_service"] = fake_publishing_module
        try:
            cms_upload = importlib.import_module(module_name)
            intent = cms_upload._creator_intent_from_selection(
                "Photo Set",
                upload_intent="teaser_image",
            )
        finally:
            sys.modules.pop(module_name, None)
            if original_streamlit is not None:
                sys.modules["streamlit"] = original_streamlit
            else:
                sys.modules.pop("streamlit", None)
            if original_publishing is not None:
                sys.modules["app.services.publishing_service"] = original_publishing
            else:
                sys.modules.pop("app.services.publishing_service", None)

        self.assertEqual(intent.content_type, CreatorContentType.PHOTOSHOOT)
        self.assertEqual(intent.legacy_upload_intent, "teaser_image")
        self.assertTrue(intent.confirmed)
        self.assertTrue(intent.override_active)


if __name__ == "__main__":
    unittest.main()
