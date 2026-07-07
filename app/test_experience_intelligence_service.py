import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.experience import ExperienceType
from app.services.content_intelligence_service import ContentIntelligenceService
from app.services.experience_intelligence_service import (
    ExperienceIntelligenceService,
)


def understanding(
    asset_id,
    *,
    media_type="image",
    tags=("lace", "mirror"),
    themes=("lingerie",),
    summary="Soft mirror set.",
    setting="bedroom",
    outfit="lace set",
    activity=None,
    original_filename=None,
    created_at=None,
    similarity_group_id=None,
    perceptual_hash=None,
    checksum=None,
    mime_type="image/jpeg",
    width=1080,
    height=1350,
    duration_seconds=None,
):
    return SimpleNamespace(
        identity=SimpleNamespace(
            asset_id=asset_id,
            original_filename=original_filename,
            file_name=f"asset_{asset_id}.jpg",
            created_at=created_at,
        ),
        media=SimpleNamespace(
            media_type=media_type,
            mime_type=mime_type,
            width=width,
            height=height,
            duration_seconds=duration_seconds,
        ),
        visual=SimpleNamespace(
            suggested_tags=tags,
            detected_themes=themes,
            summary=summary,
            setting=setting,
            outfit=outfit,
            activity=activity,
        ),
        classification=SimpleNamespace(final_classification="VIP"),
        metadata=SimpleNamespace(
            similarity_group_id=similarity_group_id,
            perceptual_hash=perceptual_hash,
            checksum=checksum,
        ),
    )


class ExperienceIntelligenceServiceTests(unittest.TestCase):
    def test_single_asset_recommends_standalone(self):
        service = ExperienceIntelligenceService()

        result = service.recommend_for_understandings(
            [understanding(1, original_filename="soft mirror.jpg")]
        )

        self.assertEqual(result.experience_type, ExperienceType.STANDALONE)
        self.assertEqual(result.asset_ids, (1,))
        self.assertEqual(result.suggested_cover_asset_id, 1)
        self.assertEqual(result.suggested_name, "Soft Mirror")
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.suggested_themes, ("lingerie",))
        self.assertIn("lace", result.suggested_keywords)
        self.assertEqual(result.mood, None)
        self.assertEqual(result.setting, "bedroom")
        self.assertFalse(result.intelligence_provenance["new_ai_analysis"])

    def test_photo_set_batch_recommends_photoshoot(self):
        service = ExperienceIntelligenceService()

        result = service.recommend_for_understandings(
            [
                understanding(1),
                understanding(2),
                understanding(3),
            ],
            package_type="photo_set",
        )

        self.assertEqual(result.experience_type, ExperienceType.PHOTOSHOOT)
        self.assertEqual(result.asset_ids, (1, 2, 3))
        self.assertEqual(result.suggested_cover_asset_id, 1)
        self.assertGreater(result.confidence, 0.8)
        self.assertIn("Photo Set", result.suggested_name)
        self.assertEqual(result.visual_continuity["setting"], "bedroom")
        self.assertIn("themes", result.visual_continuity["signals"])
        self.assertEqual(result.intelligence_metadata["asset_count"], 3)

    def test_story_markers_and_mixed_media_recommend_story(self):
        service = ExperienceIntelligenceService()

        result = service.recommend_for_understandings(
            [
                understanding(
                    1,
                    tags=("story", "morning"),
                    themes=("sequence",),
                    activity="getting ready",
                ),
                understanding(
                    2,
                    media_type="video",
                    tags=("story", "morning"),
                    themes=("sequence",),
                    activity="behind the scenes",
                ),
                understanding(
                    3,
                    tags=("story", "morning"),
                    themes=("sequence",),
                    activity="final reveal",
                ),
            ],
            package_type="story",
        )

        self.assertEqual(result.experience_type, ExperienceType.STORY)
        self.assertEqual(result.asset_ids, (1, 2, 3))
        self.assertIn("Story", result.suggested_name)
        self.assertGreater(result.confidence, 0.8)

    def test_import_session_and_existing_metadata_add_detection_evidence(self):
        service = ExperienceIntelligenceService()
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        result = service.recommend_for_understandings(
            [
                understanding(
                    1,
                    original_filename="shoot_001.jpg",
                    created_at=now,
                    similarity_group_id="set-1",
                    perceptual_hash="hash-a",
                ),
                understanding(
                    2,
                    original_filename="shoot_002.jpg",
                    created_at=now + timedelta(seconds=30),
                    similarity_group_id="set-1",
                    perceptual_hash="hash-a",
                ),
            ],
            import_session_id="session-1",
        )

        reasons = {item.reason for item in result.evidence}
        self.assertEqual(result.experience_type, ExperienceType.PHOTOSHOOT)
        self.assertIn("import_session", reasons)
        self.assertIn("timestamp_proximity", reasons)
        self.assertIn("filename_sequence", reasons)
        self.assertIn("similarity_match", reasons)
        self.assertIn("technical_metadata", reasons)
        self.assertIn("visual_continuity", reasons)
        self.assertEqual(result.metadata["import_session_id"], "session-1")

    def test_filename_timestamp_and_activity_progression_improve_story_detection(self):
        service = ExperienceIntelligenceService()
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        result = service.recommend_for_understandings(
            [
                understanding(
                    1,
                    original_filename="story_001.jpg",
                    created_at=now,
                    activity="getting ready",
                    tags=("morning",),
                    themes=("sequence",),
                ),
                understanding(
                    2,
                    media_type="video",
                    original_filename="story_002.mp4",
                    created_at=now + timedelta(minutes=2),
                    activity="behind the scenes",
                    tags=("morning",),
                    themes=("sequence",),
                    mime_type="video/mp4",
                    duration_seconds=8.0,
                ),
                understanding(
                    3,
                    original_filename="story_003.jpg",
                    created_at=now + timedelta(minutes=4),
                    activity="final reveal",
                    tags=("morning",),
                    themes=("sequence",),
                ),
            ],
        )

        reasons = {item.reason for item in result.evidence}
        self.assertEqual(result.experience_type, ExperienceType.STORY)
        self.assertIn("filename_sequence", reasons)
        self.assertIn("timestamp_proximity", reasons)
        self.assertIn("story_progression", reasons)
        self.assertIn("ordered_story_progression", reasons)
        self.assertTrue(result.story_progression["filename_sequence"])
        self.assertTrue(result.story_progression["activity_progression"])
        self.assertIn("video/mp4", result.technical_continuity["mime_types"])

    def test_reusable_experience_intelligence_is_metadata_projected(self):
        service = ExperienceIntelligenceService()

        result = service.recommend_for_understandings(
            [
                understanding(1, tags=("lace", "mirror"), themes=("boudoir",)),
                understanding(2, tags=("lace", "mirror"), themes=("boudoir",)),
            ],
            import_session_id="session-42",
        )

        profile = result.metadata["experience_intelligence"]
        self.assertEqual(profile["suggested_themes"], ("boudoir",))
        self.assertIn("mirror", profile["suggested_keywords"])
        self.assertEqual(profile["setting"], "bedroom")
        self.assertEqual(
            profile["intelligence_provenance"]["inputs"],
            ("content_intelligence", "asset_understanding"),
        )
        self.assertFalse(profile["intelligence_provenance"]["new_ai_analysis"])

    def test_recommendation_accepts_content_intelligence_read_model(self):
        service = ExperienceIntelligenceService()
        content = ContentIntelligenceService().build_from_understanding(
            understanding(11, original_filename="content intelligence.jpg")
        )

        result = service.recommend_for_understandings([content])

        self.assertEqual(result.asset_ids, (11,))
        self.assertEqual(result.suggested_name, "Content Intelligence")
        self.assertEqual(result.suggested_themes, ("lingerie",))
        self.assertEqual(result.setting, "bedroom")
        self.assertEqual(
            result.intelligence_provenance["inputs"],
            ("content_intelligence", "asset_understanding"),
        )


if __name__ == "__main__":
    unittest.main()
