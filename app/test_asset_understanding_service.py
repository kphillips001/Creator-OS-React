import unittest
from pathlib import Path
from types import SimpleNamespace

from app.services.asset_understanding_service import AssetUnderstandingService


class FakeRuntimeResolver:
    def resolve_original(self, asset, *, require_exists=False):
        return SimpleNamespace(
            path=Path(asset.media_metadata["local_vault_path"]),
            path_string=asset.media_metadata["local_vault_path"],
            source="media_metadata.local_vault_path",
            exists=True,
            candidates=(),
        )


class FakeAssets:
    def __init__(self, asset):
        self.asset = asset

    def get_by_id(self, asset_id):
        if self.asset.id == asset_id:
            return self.asset
        return None


def make_asset():
    return SimpleNamespace(
        id=42,
        creator_profile_id=7,
        file_name="vault-import.jpg",
        file_path="data/uploads/vault-import.jpg",
        upload_intent="ppv_image",
        created_at=None,
        media_type="image",
        media_metadata={
            "original_filename": "creator original.jpg",
            "local_vault_path": "data/cms/vault/originals/images/42.jpg",
            "mime_type": "image/jpeg",
            "file_extension": ".jpg",
            "size_bytes": 12345,
            "duplicate_detection_status": "not_available",
        },
        gpt_vision_result={
            "classification": "VIP",
            "confidence": 0.91,
            "detected_themes": ["lingerie", "mirror"],
            "suggested_tags": ["vip", "lace"],
            "risk_flags": ["manual_review_optional"],
            "short_safe_summary": "Soft mirror set.",
            "reasoning": "Suggestive but not explicit.",
        },
        nudenet_result=[
            {"class": "FEMALE_BREAST_COVERED", "score": 0.88},
        ],
        classification_result={
            "raw_gpt_classification": "VIP",
            "final_classification": "VIP",
            "rule_applied": None,
        },
        classification="VIP",
        confidence=0.91,
        detected_themes=("lingerie", "mirror"),
        suggested_tags=("vip", "lace"),
        risk_flags=("manual_review_optional",),
        summary="Soft mirror set.",
        reasoning="Suggestive but not explicit.",
        analysis_provenance={
            "source": "cms_upload",
            "analysis_version": "phase_2c_ai_product_drafting_v1",
            "vision_model": "gpt-4.1-mini",
            "nudenet_enabled": True,
            "upload_intent": "ppv_image",
        },
        nudity_labels=("FEMALE_BREAST_COVERED",),
        nudity_level="covered",
        sexual_intensity="medium",
        is_explicit=False,
        status="approved",
        is_active=True,
        is_test=False,
        ready_for_rotation=True,
        local_vault_path="data/cms/vault/originals/images/42.jpg",
    )


class AssetUnderstandingServiceTests(unittest.TestCase):
    def test_build_from_asset_normalizes_existing_ai_outputs(self):
        asset = make_asset()
        service = AssetUnderstandingService(
            runtime_media_resolver=FakeRuntimeResolver(),
        )

        understanding = service.build_from_asset(asset)

        self.assertEqual(understanding.identity.asset_id, 42)
        self.assertEqual(
            understanding.identity.original_filename,
            "creator original.jpg",
        )
        self.assertEqual(understanding.media.media_type, "image")
        self.assertEqual(understanding.media.mime_type, "image/jpeg")
        self.assertEqual(understanding.media.size_bytes, 12345)
        self.assertEqual(
            understanding.media.runtime_source,
            "media_metadata.local_vault_path",
        )
        self.assertEqual(understanding.visual.summary, "Soft mirror set.")
        self.assertEqual(understanding.visual.detected_themes, ("lingerie", "mirror"))
        self.assertEqual(understanding.visual.suggested_tags, ("vip", "lace"))
        self.assertEqual(
            understanding.safety.nudity_labels,
            ("FEMALE_BREAST_COVERED",),
        )
        self.assertEqual(understanding.safety.nudity_level, "covered")
        self.assertEqual(understanding.safety.sexual_intensity, "medium")
        self.assertEqual(understanding.classification.final_classification, "VIP")
        self.assertEqual(understanding.classification.confidence, 0.91)
        self.assertEqual(understanding.provenance.vision_model, "gpt-4.1-mini")
        self.assertFalse(understanding.readiness.needs_review)
        self.assertTrue(understanding.readiness.has_runtime_media)

    def test_get_understanding_loads_asset_from_repository(self):
        asset = make_asset()
        service = AssetUnderstandingService(
            asset_repository=FakeAssets(asset),
            runtime_media_resolver=FakeRuntimeResolver(),
        )

        understanding = service.get_understanding(42)

        self.assertIsNotNone(understanding)
        self.assertEqual(understanding.identity.asset_id, 42)


if __name__ == "__main__":
    unittest.main()
