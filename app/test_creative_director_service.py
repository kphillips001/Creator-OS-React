import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

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

        with patch(
            "app.services.creative_director_service.generate_lucky_premium_tags",
            return_value="hotel mirror warmth\nwindow seat tease",
        ) as lucky:
            tags = service.i_feel_lucky(
                creator_profile={"display_name": "Ava"},
                creative_mode="premium_teaser",
                prompt_count=2,
            )

        self.assertEqual(len(tags), 2)
        self.assertEqual(tags, ("hotel mirror warmth", "window seat tease"))
        lucky.assert_called_once()

        source = Path("app/services/creative_director_service.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("generate_prompts_with_grok", source)
        self.assertIn("build_chatgpt_prompt", source)
        self.assertIn("generate_premium_prompts", source)
        self.assertIn("premium_tag_enhancer_service", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("Nano", source)
        self.assertNotIn("WAN", source)
        self.assertNotIn("Seedream", source)
        self.assertNotIn("Flux", source)

    def test_prompt_plan_generation_consumes_active_reference(self):
        active_reference = reference_asset()
        service = self.make_service(active_reference)

        with patch(
            "app.services.creative_director_service.generate_prompts_with_grok",
            return_value=[
                "coffee at home shot one with a natural smile and window light",
                "coffee at home shot two with a seated pose and soft lamp light",
                "coffee at home shot three with a playful glance and kitchen background",
            ],
        ):
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
        self.assertEqual(plan.prompt_metadata["generation_brain"], "wavespeed_canonical")
        self.assertEqual(plan.prompt_metadata["prompt_builder"], "wavespeed_social_prompt_builder")
        self.assertEqual(plan.prompt_metadata["reference_conditioning"], "wavespeed")
        self.assertIn("prompt_variations", plan.prompt_metadata)
        self.assertEqual(len(plan.prompt_metadata["prompt_variations"]), 3)
        self.assertIn("coffee at home shot one", plan.prompt_metadata["prompt_variations"][0])
        self.assertIn("same natural sun-kissed skin tone", plan.prompt_metadata["prompt_variations"][0])

    def test_social_tag_helpers_use_wavespeed_continuity_and_grok(self):
        service = self.make_service()

        enhanced = service.enhance_social_tags(
            simple_tags="coffee at home, fitted tank top",
            creator_profile={"display_name": "Ava"},
        )
        with patch.dict("os.environ", {"GROK_API_KEY": "test-key"}), patch(
            "app.services.creative_director_service.generate_prompts_with_grok",
            return_value=["porch afternoon with a playful lean and warm light"],
        ):
            surprise = service.surprise_social_tags(
                simple_tags="porch afternoon",
                creator_profile={"display_name": "Ava"},
            )

        self.assertIn("coffee at home", enhanced)
        self.assertIn("same natural sun-kissed skin tone", enhanced)
        self.assertIn("porch afternoon", surprise)
        self.assertIn("same natural sun-kissed skin tone", surprise)

    def test_premium_tag_helpers_delegate_to_wavespeed_brain(self):
        service = self.make_service(reference_asset())

        with patch(
            "app.services.creative_director_service.wavespeed_enhance_premium_tags",
            return_value="enhanced premium crop tank with medium-close creator framing",
        ):
            enhanced = service.enhance_premium_tags(
                simple_tags="Ribbed or Mesh Crop Tank + Low-Rise Cargo Mini Skirt",
                creator_profile={"id": 7, "display_name": "Ava"},
            )
        with patch(
            "app.services.creative_director_service.generate_premium_prompts",
            return_value=[
                "premium prompt one with medium-close creator framing and wardrobe continuity",
                "premium prompt two with head-to-hips framing and warm bedroom light",
            ],
        ):
            plan = service.create_prompt_plan(
                creator_profile={"id": 7, "display_name": "Ava"},
                creative_tags=enhanced,
                creative_mode="premium_teaser",
                prompt_count=2,
            )
        variations = plan.prompt_metadata["prompt_variations"]

        self.assertEqual(enhanced, "enhanced premium crop tank with medium-close creator framing")
        self.assertEqual(plan.prompt_metadata["generation_brain"], "wavespeed_canonical")
        self.assertEqual(plan.prompt_metadata["prompt_builder"], "wavespeed_premium_prompt_builder")
        self.assertIn("medium-close creator framing", variations[0])

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

    def test_ask_anything_uses_provider_or_grok_configuration(self):
        service = self.make_service()

        with patch.dict("os.environ", {"GROK_API_KEY": ""}):
            with self.assertRaises(ValueError):
                service.ask_anything(
                    question="Brainstorm premium mirror shots",
                    image_name="pose.png",
                )

        provider_service = CreativeDirectorService(
            storage_dir=service.storage_dir,
            reference_library_service=FakeReferenceLibraryService(),
            ask_anything_provider=lambda **kwargs: f"provider answer: {kwargs['question']}",
        )

        provider_answer = provider_service.ask_anything(
            question="Rewrite this caption",
        )

        self.assertEqual(provider_answer, "provider answer: Rewrite this caption")

    def test_content_studio_integrates_creative_director_without_duplicate_state(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("CreativeDirectorService", source)
        self.assertIn("create_prompt_plan", source)
        self.assertIn("latest_session", source)
        self.assertIn("get_active_reference", source)
        self.assertIn('"Social Studio", "Premium Studio"', source)
        self.assertNotIn("submit_wavespeed_task", source)


if __name__ == "__main__":
    unittest.main()
