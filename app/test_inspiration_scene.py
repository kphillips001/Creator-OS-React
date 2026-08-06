import unittest

from app.models.inspiration_scene import InspirationSceneAnalysis
from app.api.content_studio import _has_supported_image_signature


class InspirationSceneAnalysisTests(unittest.TestCase):
    def test_excludes_uploaded_subject_identity(self):
        result = InspirationSceneAnalysis.from_mapping({
            "scene": "studio portrait", "pose": "seated",
            "elements_to_preserve": ["rim lighting", "subject face", "skin tone"],
            "elements_to_ignore": ["logo"], "identity_transfer_prohibited": False,
            "confidence": 1.4,
        })
        self.assertEqual(result.elements_to_preserve, ("rim lighting",))
        self.assertTrue(result.identity_transfer_prohibited)
        self.assertIn("uploaded subject recognizable identity", result.elements_to_ignore)
        self.assertEqual(result.confidence, 1.0)

    def test_normalizes_malformed_optional_values(self):
        result = InspirationSceneAnalysis.from_mapping({"confidence": "unknown"})
        self.assertEqual(result.confidence, 0.0)
        self.assertTrue(result.identity_transfer_prohibited)

    def test_rejects_malformed_and_accepts_supported_image_signatures(self):
        self.assertFalse(_has_supported_image_signature(b"not an image", "image/png"))
        self.assertTrue(_has_supported_image_signature(b"\x89PNG\r\n\x1a\ncontent", "image/png"))
