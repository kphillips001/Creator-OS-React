import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.services.content_intelligence_service import ContentIntelligenceService


class FakeAssetUnderstandingService:
    def __init__(self, understanding):
        self.understanding = understanding
        self.get_calls = []
        self.build_calls = []

    def get_understanding(self, asset_id):
        self.get_calls.append(asset_id)
        return self.understanding

    def build_from_asset(self, asset):
        self.build_calls.append(asset)
        return self.understanding


def make_understanding():
    return SimpleNamespace(
        identity=SimpleNamespace(asset_id=42),
        media=SimpleNamespace(
            media_type="image",
            local_vault_path="vault/42.jpg",
            runtime_path="vault/42.jpg",
            runtime_source="media_metadata.local_vault_path",
            runtime_exists=True,
            mime_type="image/jpeg",
            size_bytes=12345,
            width=1200,
            height=1600,
            aspect_ratio="3:4",
        ),
        visual=SimpleNamespace(
            summary="Soft mirror set.",
            detected_themes=("lingerie", "mirror"),
            suggested_tags=("vip", "lace"),
            mood="warm",
            setting="bedroom",
            outfit="lace set",
            pose="mirror selfie",
            activity="posing",
            objects=("mirror",),
            gpt_vision_result={
                "model": "gpt-4.1-mini",
                "keywords": ("soft", "mirror"),
            },
        ),
        classification=SimpleNamespace(
            classification="VIP",
            final_classification="VIP",
            confidence=0.91,
            classification_result={"rule_applied": None},
        ),
        metadata=SimpleNamespace(
            media_metadata={"local_vault_path": "vault/42.jpg"},
            duplicate_detection_status="not_available",
            similarity_group_id="group-1",
            perceptual_hash="hash",
            checksum="checksum",
        ),
        provenance=SimpleNamespace(
            source="cms_upload",
            analysis_version="phase_2c_ai_product_drafting_v1",
            vision_model="gpt-4.1-mini",
            nudenet_enabled=True,
        ),
        readiness=SimpleNamespace(
            has_runtime_media=True,
            has_visual_summary=True,
            has_classification=True,
            needs_review=False,
        ),
    )


class ContentIntelligenceServiceTests(unittest.TestCase):
    def test_get_asset_intelligence_reuses_existing_asset_understanding(self):
        understanding = make_understanding()
        asset_understanding = FakeAssetUnderstandingService(understanding)
        service = ContentIntelligenceService(
            asset_understanding_service=asset_understanding
        )

        record = service.get_asset_intelligence(42)

        self.assertEqual(asset_understanding.get_calls, [42])
        self.assertIs(record.asset_understanding, understanding)
        self.assertEqual(record.asset_id, 42)
        self.assertEqual(record.summary, "Soft mirror set.")
        self.assertEqual(record.classification, "VIP")
        self.assertEqual(record.confidence, 0.91)
        self.assertEqual(record.themes, ("lingerie", "mirror"))
        self.assertEqual(record.tags, ("vip", "lace"))
        self.assertEqual(record.setting, "bedroom")
        self.assertEqual(record.environment, "bedroom")
        self.assertEqual(record.activities, ("posing",))
        self.assertEqual(record.clothing, "lace set")
        self.assertIn("vip", record.keywords)
        self.assertIn("lingerie", record.keywords)
        self.assertIn("soft", record.keywords)
        self.assertEqual(record.technical_quality["has_runtime_media"], True)
        self.assertEqual(record.technical_quality["width"], 1200)
        self.assertTrue(record.suggested_cover_image.recommended)
        self.assertEqual(record.suggested_cover_image.asset_id, 42)
        self.assertGreaterEqual(record.suggested_cover_image.confidence, 0.65)
        self.assertIn(
            "Asset media type is image.",
            record.suggested_cover_image.rationale,
        )
        self.assertIs(
            record.recommendations["suggested_cover_image"],
            record.suggested_cover_image,
        )
        self.assertEqual(record.technical_metadata["width"], 1200)
        self.assertEqual(
            record.ai_metadata["gpt_vision_result"],
            {
                "model": "gpt-4.1-mini",
                "keywords": ("soft", "mirror"),
            },
        )
        self.assertEqual(
            record.ownership["content_intelligence_owner"],
            "ContentIntelligenceService",
        )
        self.assertEqual(
            record.ownership["experience_owner"],
            "ExperienceService",
        )

    def test_build_from_asset_does_not_duplicate_analysis(self):
        understanding = make_understanding()
        asset = SimpleNamespace(id=42)
        asset_understanding = FakeAssetUnderstandingService(understanding)
        service = ContentIntelligenceService(
            asset_understanding_service=asset_understanding
        )

        record = service.build_from_asset(asset)

        self.assertEqual(asset_understanding.build_calls, [asset])
        self.assertIs(record.asset_understanding, understanding)

    def test_generation_does_not_fabricate_missing_business_metadata(self):
        understanding = SimpleNamespace(
            identity=SimpleNamespace(asset_id=77),
            media=SimpleNamespace(),
            visual=SimpleNamespace(gpt_vision_result={}),
            classification=SimpleNamespace(),
            metadata=SimpleNamespace(),
            provenance=SimpleNamespace(),
            readiness=SimpleNamespace(),
        )
        service = ContentIntelligenceService(
            asset_understanding_service=FakeAssetUnderstandingService(
                understanding
            )
        )

        record = service.get_asset_intelligence(77)

        self.assertIsNone(record.environment)
        self.assertEqual(record.activities, ())
        self.assertIsNone(record.clothing)
        self.assertEqual(record.keywords, ())
        self.assertEqual(record.technical_quality, {})
        self.assertFalse(record.suggested_cover_image.recommended)
        self.assertIsNone(record.suggested_cover_image.asset_id)
        self.assertLess(record.suggested_cover_image.confidence, 0.65)

    def test_cover_image_recommendation_respects_review_state(self):
        understanding = make_understanding()
        understanding.readiness.needs_review = True
        service = ContentIntelligenceService(
            asset_understanding_service=FakeAssetUnderstandingService(
                understanding
            )
        )

        record = service.get_asset_intelligence(42)

        self.assertFalse(record.suggested_cover_image.recommended)
        self.assertIsNone(record.suggested_cover_image.asset_id)
        self.assertLessEqual(record.suggested_cover_image.confidence, 0.45)
        self.assertIn(
            "Asset is marked as needing review.",
            record.suggested_cover_image.rationale,
        )

    def test_service_imports_do_not_cross_business_boundaries(self):
        path = Path("app/services/content_intelligence_service.py")
        tree = ast.parse(path.read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        forbidden_fragments = (
            "product",
            "publishing",
            "telegram",
            "decision_engine",
            "experience_service",
        )
        for module in imports:
            with self.subTest(module=module):
                self.assertFalse(
                    any(fragment in module for fragment in forbidden_fragments),
                    module,
                )


if __name__ == "__main__":
    unittest.main()
