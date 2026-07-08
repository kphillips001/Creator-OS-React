import sys
import tempfile
import types
import unittest
from pathlib import Path

if "streamlit" not in sys.modules:
    streamlit = types.ModuleType("streamlit")
    sys.modules["streamlit"] = streamlit

if "psycopg" not in sys.modules:
    psycopg = types.ModuleType("psycopg")
    rows = types.ModuleType("psycopg.rows")
    psycopg_types = types.ModuleType("psycopg.types")
    json_types = types.ModuleType("psycopg.types.json")
    errors = types.ModuleType("psycopg.errors")
    psycopg.connect = lambda *args, **kwargs: None
    rows.dict_row = object()
    json_types.Json = lambda value: value
    errors.UniqueViolation = type("UniqueViolation", (Exception,), {})
    sys.modules["psycopg"] = psycopg
    sys.modules["psycopg.rows"] = rows
    sys.modules["psycopg.types"] = psycopg_types
    sys.modules["psycopg.types.json"] = json_types
    sys.modules["psycopg.errors"] = errors

from app.models.asset_library import (
    AssetLibraryItem,
    AssetPublishingSummary,
    AssetRelationshipSummary,
)
from app.models.creative_director import CreativeDirectorSettings
from app.models.reference_library import ReferenceAsset
from app.services.creative_director_service import CreativeDirectorService


def reference_asset(asset_id=55, creator_profile_id=7):
    item = AssetLibraryItem(
        asset_id=asset_id,
        file_name="reference.png",
        media_type="image",
        classification="TEASE",
        status="approved",
        is_active=True,
        created_at=None,
        preview_path="C:/Creator-OS/data/cms/vault/originals/images/55.png",
        original_path="C:/Creator-OS/data/cms/vault/originals/images/55.png",
        tags=("reference",),
        themes=("studio",),
        ready_for_rotation=True,
        relationship=AssetRelationshipSummary(),
        publishing=AssetPublishingSummary(status="Local asset only"),
        is_reference_image=True,
    )
    return ReferenceAsset(
        asset=item,
        creator_profile_id=creator_profile_id,
        is_active=True,
        is_favorite=True,
    )


class FakeReferenceLibraryService:
    def __init__(self, active_reference=None):
        self.active_reference = active_reference
        self.calls = []

    def get_active_reference(self, *, creator_profile_id):
        self.calls.append(creator_profile_id)
        if (
            self.active_reference
            and self.active_reference.creator_profile_id == creator_profile_id
        ):
            return self.active_reference
        return None


class CreativeDirectorServiceTests(unittest.TestCase):
    def make_service(self, active_reference=None):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        service = CreativeDirectorService(
            storage_dir=temp_dir.name,
            reference_library_service=FakeReferenceLibraryService(active_reference),
        )
        return service

    def test_creative_tags_are_normalized_and_deduped(self):
        service = self.make_service()

        tags = service.normalize_tags(
            "bedroom doorway, fitted crop top\nbedroom doorway; soft window light"
        )

        self.assertEqual(
            tags,
            ("bedroom doorway", "fitted crop top", "soft window light"),
        )

    def test_i_feel_lucky_is_provider_neutral(self):
        service = self.make_service()

        tags = service.i_feel_lucky(
            creator_profile={"display_name": "Ava"},
            creative_mode="premium_teaser",
            prompt_count=2,
        )

        self.assertEqual(len(tags), 2)
        self.assertIn("Ava style", tags[0])

        source = Path("app/services/creative_director_service.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("generate_prompts_with_grok", source)
        self.assertNotIn("OpenAI", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("Nano", source)
        self.assertNotIn("WAN", source)
        self.assertNotIn("Seedream", source)
        self.assertNotIn("Flux", source)

    def test_prompt_plan_generation_consumes_active_reference(self):
        active_reference = reference_asset()
        service = self.make_service(active_reference)

        plan = service.create_prompt_plan(
            creator_profile={"id": 7, "display_name": "Ava"},
            creative_tags="coffee at home, fitted tank top",
            creative_mode="social_safe",
            prompt_count=3,
        )

        self.assertEqual(plan.creator_profile_id, 7)
        self.assertEqual(plan.reference_asset_id, active_reference.asset_id)
        self.assertEqual(plan.reference_asset_path, active_reference.asset.original_path)
        self.assertEqual(plan.creative_mode, "social_safe")
        self.assertTrue(plan.prompt_metadata["provider_neutral"])
        self.assertEqual(plan.prompt_metadata["generation_execution"], "future")
        self.assertIn("Reference Asset #55", plan.prompt_text)

    def test_creative_session_persistence_and_history(self):
        service = self.make_service(reference_asset())

        plan = service.create_prompt_plan(
            creator_profile={"id": 7, "persona_name": "Ava"},
            creative_tags=["porch afternoon", "denim shorts"],
            creative_mode="spicy",
            prompt_count=4,
        )

        reloaded = CreativeDirectorService(
            storage_dir=service.storage_dir,
            reference_library_service=FakeReferenceLibraryService(reference_asset()),
        )
        history = reloaded.history(creator_profile_id=7)

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].session.creator_profile_id, 7)
        self.assertEqual(history[0].prompt_plan.plan_id, plan.plan_id)
        self.assertEqual(history[0].session.reference_asset_id, 55)

    def test_creator_specific_settings(self):
        service = self.make_service()
        service.save_settings(
            CreativeDirectorSettings(
                creator_profile_id=7,
                default_mode="premium_teaser",
                default_prompt_count=8,
                favorite_tags=("robe", "window light"),
            )
        )

        saved = service.load_settings(7)
        fallback = service.load_settings(8)

        self.assertEqual(saved.default_mode, "premium_teaser")
        self.assertEqual(saved.default_prompt_count, 8)
        self.assertEqual(saved.favorite_tags, ("robe", "window light"))
        self.assertEqual(fallback.creator_profile_id, 8)
        self.assertEqual(fallback.default_mode, "social_safe")

    def test_content_studio_integrates_creative_director_without_duplicate_state(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("CreativeDirectorService", source)
        self.assertIn("create_prompt_plan", source)
        self.assertIn("latest_session", source)
        self.assertIn("get_active_reference", source)
        self.assertIn('"Social Studio", "Premium Studio"', source)
        self.assertNotIn("generate_prompts_with_grok", source)
        self.assertNotIn("submit_wavespeed_task", source)


if __name__ == "__main__":
    unittest.main()
