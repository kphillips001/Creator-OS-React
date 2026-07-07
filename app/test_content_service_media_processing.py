import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.services.content_service import ContentService
from app.services.media_processing_service import MediaProcessingService


class FakeMediaProcessingService:
    def __init__(self, derivative_path=None):
        self.derivative_path = derivative_path
        self.calls = []

    def resolve_derivative(self, media, derivative_type):
        self.calls.append((media, derivative_type))
        return self.derivative_path


class ContentServiceMediaProcessingTests(unittest.TestCase):
    def test_cms_content_preview_uses_media_processing_service(self):
        selected_content = {
            "id": 44,
            "classification": "TEASE",
            "file_path": "original.jpg",
            "file_name": "original.jpg",
            "blurred_preview_path": "legacy_blurred.jpg",
            "fanvue_media_preview_uuid": "preview",
            "fanvue_media_full_uuid": "full",
        }
        media_processing = FakeMediaProcessingService(
            derivative_path="vault/blurred/original_blurred.jpg",
        )
        service = ContentService(media_processing_service=media_processing)
        service._persist_content_personalization = lambda *args, **kwargs: None

        with patch(
            "app.repositories.content_repository.get_tease_content_for_user",
            return_value=selected_content,
        ):
            result = service.get_content(
                "tease",
                user_memory={
                    "fanvue_account_id": 1,
                    "fanvue_user_id": 2,
                },
            )

        self.assertEqual(
            result["blurred_preview_path"],
            "vault/blurred/original_blurred.jpg",
        )
        self.assertEqual(
            media_processing.calls,
            [(selected_content, "blurred_preview")],
        )

    def test_cms_content_preview_legacy_path_is_resolved_by_media_processing(self):
        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "legacy_blurred.jpg"
            preview_path.write_bytes(b"preview")
            selected_content = {
                "id": 45,
                "classification": "TEASE",
                "file_path": "original.jpg",
                "file_name": "original.jpg",
                "blurred_preview_path": str(preview_path),
            }
            service = ContentService(
                media_processing_service=MediaProcessingService()
            )
            service._persist_content_personalization = lambda *args, **kwargs: None

            with patch(
                "app.repositories.content_repository.get_tease_content_for_user",
                return_value=selected_content,
            ):
                result = service.get_content(
                    "tease",
                    user_memory={
                        "fanvue_account_id": 1,
                        "fanvue_user_id": 2,
                    },
                )

        self.assertEqual(result["blurred_preview_path"], str(preview_path))

    def test_cms_content_preview_does_not_fallback_outside_media_processing(self):
        selected_content = {
            "id": 46,
            "classification": "TEASE",
            "file_path": "original.jpg",
            "file_name": "original.jpg",
            "blurred_preview_path": "legacy_blurred.jpg",
        }
        media_processing = FakeMediaProcessingService(derivative_path=None)
        service = ContentService(media_processing_service=media_processing)
        service._persist_content_personalization = lambda *args, **kwargs: None

        with patch(
            "app.repositories.content_repository.get_tease_content_for_user",
            return_value=selected_content,
        ):
            result = service.get_content(
                "tease",
                user_memory={
                    "fanvue_account_id": 1,
                    "fanvue_user_id": 2,
                },
            )

        self.assertIsNone(result["blurred_preview_path"])


if __name__ == "__main__":
    unittest.main()
