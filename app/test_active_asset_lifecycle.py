import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.content_classification_service import classify_content_image


class ActiveAssetLifecycleTests(unittest.TestCase):
    def _temp_media_path(self, suffix: str) -> Path:
        media = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        media.write(b"test media")
        media.close()
        self.addCleanup(lambda: Path(media.name).unlink(missing_ok=True))
        return Path(media.name)

    def test_ppv_video_import_becomes_active(self):
        media_path = self._temp_media_path(".mp4")
        captured_payloads = []

        def capture_insert(payload):
            captured_payloads.append(payload)
            return 101

        with patch(
            "app.services.content_classification_service.insert_content_item",
            side_effect=capture_insert,
        ):
            result = classify_content_image(
                media_path,
                save_to_db=True,
                upload_intent="ppv_video",
                fanvue_upload_enabled=False,
                creator_profile_id=2,
                fanvue_account_id=1,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["db_save_result"]["content_id"], 101)
        self.assertEqual(len(captured_payloads), 1)

        payload = captured_payloads[0]
        self.assertEqual(payload["upload_intent"], "ppv_video")
        self.assertEqual(payload["status"], "approved")
        self.assertTrue(payload["ready_for_rotation"])
        self.assertFalse(payload["requires_blur"])
        self.assertEqual(payload["fanvue_upload_status"], "not_requested")

    def test_ppv_image_import_becomes_active_after_classification(self):
        media_path = self._temp_media_path(".jpg")
        captured_payloads = []

        def capture_insert(payload):
            captured_payloads.append(payload)
            return 202

        gpt_result = {
            "classification": "PREMIUM",
            "confidence": 0.93,
            "detected_themes": ["lingerie"],
            "suggested_tags": ["vip"],
            "short_safe_summary": "Premium image set.",
            "risk_flags": [],
            "reasoning": "Classified as premium.",
        }

        with (
            patch(
                "app.services.content_classification_service.run_nudenet",
                return_value=[],
            ),
            patch(
                "app.services.content_classification_service.run_gpt_vision",
                return_value=gpt_result,
            ),
            patch(
                "app.services.content_classification_service.insert_content_item",
                side_effect=capture_insert,
            ),
        ):
            result = classify_content_image(
                media_path,
                save_to_db=True,
                upload_intent="ppv_image",
                fanvue_upload_enabled=False,
                creator_profile_id=2,
                fanvue_account_id=1,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["db_save_result"]["content_id"], 202)
        self.assertEqual(len(captured_payloads), 1)

        payload = captured_payloads[0]
        self.assertEqual(payload["upload_intent"], "ppv_image")
        self.assertEqual(payload["status"], "approved")
        self.assertTrue(payload["ready_for_rotation"])
        self.assertTrue(payload["requires_blur"])
        self.assertTrue(payload["requires_nudenet"])
        self.assertEqual(payload["classification"], "PREMIUM")
        self.assertEqual(payload["fanvue_upload_status"], "not_requested")


if __name__ == "__main__":
    unittest.main()
