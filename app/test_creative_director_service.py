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

    def get_active_canonical_reference(self, *, creator_profile_id):
        self.calls.append(creator_profile_id)
        if (
            self.active_reference
            and self.active_reference.creator_profile_id == creator_profile_id
        ):
            return self.active_reference
        return None

    def get_active_reference(self, **_kwargs):
        raise AssertionError("prompt planning must not use full enrichment")

    def list_references(self, *_args, **_kwargs):
        raise AssertionError("prompt planning must not enumerate references")


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
        self.assertIn("CanonicalPromptPlanner", source)
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
            "app.services.canonical_prompt_planner.generate_premium_prompts",
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
        self.assertEqual(plan.prompt_metadata["generation_brain"], "seedream_premium_canonical")
        self.assertEqual(plan.prompt_metadata["prompt_builder"], "canonical_seedream_premium_planner")
        self.assertIn("medium-close creator framing", variations[0])

    def test_photoshoot_creative_director_returns_structured_direction(self):
        captured = {}

        def fake_provider(**_kwargs):
            captured.update(_kwargs)
            return """
{
  "title": "Balcony Door Tease",
  "creative_direction": "Move her closer to the balcony door while keeping the same lingerie and hairstyle.",
  "reasoning": "It progresses the shoot without breaking continuity.",
  "continuity_notes": "Keep wardrobe, lighting, makeup, and camera style.",
  "camera_framing": "Close-medium head-to-hips framing",
  "lighting": "Same warm window light",
  "emotion": "Soft playful confidence",
  "pose_composition": "One hand near the door frame, body angled toward camera"
}
"""

        service = CreativeDirectorService(
            storage_dir=tempfile.mkdtemp(),
            ask_anything_provider=fake_provider,
        )

        direction = service.recommend_photoshoot_direction(
            image_bytes=b"fake-image",
            image_mime_type="image/png",
            session_context={"session_defaults": {"wardrobe": "same outfit"}},
            approved_history=(),
            creative_mode="premium",
            session_direction="Move to the balcony",
            creative_hint="mirror, window",
            continuity_locks={"wardrobe": True, "lighting": True},
        )

        self.assertEqual(direction.title, "Balcony Door Tease")
        self.assertIn("same lingerie", direction.creative_direction)
        self.assertEqual(direction.creative_mode, "premium")
        self.assertTrue(direction.continuity_locks["wardrobe"])
        self.assertIn("head-to-hips", direction.camera_framing)
        self.assertIn("Creative Hint:", captured["question"])
        self.assertIn("mirror, window", captured["question"])
        self.assertIn("Creative Hint represents user-approved creative intent", captured["question"])
        self.assertIn("Never reject it because of continuity", captured["question"])
        self.assertIn("Priority Order:", captured["question"])
        self.assertIn("1. Creative Hint, if provided.", captured["question"])
        self.assertIn("2. Session Direction.", captured["question"])
        self.assertIn("3. Continuity Locks.", captured["question"])
        self.assertIn("preserving every remaining locked attribute", captured["question"])
        self.assertIn("The Shot Director still owns", captured["question"])
        self.assertIn("next frame of a professionally directed photoshoot", captured["question"])
        self.assertIn("latest approved shot, session history, creative mode, Creative Hint", captured["question"])
        self.assertIn("Avoid repetitive poses", captured["question"])
        self.assertIn("In premium mode, progress through tasteful intimacy", captured["question"])

    def test_photoshoot_ask_grok_inspiration_uses_vision_context_without_prompt_planner(self):
        captured = {}

        def fake_provider(**_kwargs):
            captured.update(_kwargs)
            return (
                "1. Try a softer mirror moment that keeps the same mood.\n"
                "2. Slide one hand lower while holding eye contact.\n"
                "3. Arch her back and open her thighs a little more.\n"
                "4. Use both hands to tease her chest and hips.\n"
                "5. Shift onto her side and look back over her shoulder.\n"
                "6. Pull the fabric aside just enough to feel riskier.\n"
                "7. Bring her free hand to her mouth while she stays posed.\n"
                "8. Let the next beat feel hungrier and more deliberate."
            )

        service = CreativeDirectorService(
            storage_dir=tempfile.mkdtemp(),
            ask_anything_provider=fake_provider,
        )
        service.plan_prompts = lambda *_args, **_kwargs: self.fail("Ask Grok must not invoke the Canonical Prompt Planner")

        ideas = service.suggest_photoshoot_inspiration(
            image_bytes=b"fake-image",
            image_mime_type="image/png",
            session_context={"progression_stage": 4},
            approved_history=({"title": "Shot 4"},),
            creative_mode="premium",
            session_direction="Keep the bedroom set",
            creative_hint="mirror",
            continuity_locks={"wardrobe": True, "lighting": True},
            provider_context="Seedream 5.0 Pro",
            idea_count=8,
            timeline_images=(
                {"bytes": b"shot-1", "mime_type": "image/png", "label": "Shot 1 (Seed)"},
                {"bytes": b"shot-2", "mime_type": "image/png", "label": "Shot 2"},
                {"bytes": b"fake-image", "mime_type": "image/png", "label": "Shot 3 — current"},
            ),
        )

        self.assertEqual(len(ideas), 8)
        self.assertIn("mirror moment", ideas[0])
        self.assertEqual(captured["image_bytes"], b"fake-image")
        self.assertEqual(captured["image_mime_type"], "image/png")
        self.assertEqual(len(captured["images"]), 3)
        self.assertEqual(captured["images"][0]["bytes"], b"shot-1")
        self.assertIn("exactly 8 distinct next-scene ideas", captured["question"])
        self.assertIn("Creative inspiration only", captured["question"])
        self.assertIn("Do not write a renderer prompt", captured["question"])
        self.assertIn("progression_stage", captured["question"])
        self.assertIn("Shot 4", captured["question"])
        self.assertIn("mirror", captured["question"])
        self.assertIn("Seedream 5.0 Pro", captured["question"])
        self.assertIn("Premium mode intensity rules", captured["question"])
        self.assertIn("Shot 1 (Seed)", captured["question"])
        self.assertIn("compact Photoshoot Summary", captured["question"])
        self.assertIn("Do not request or reconstruct complete prompt history", captured["question"])

    def test_photoshoot_ask_grok_explicit_mode_requests_escalating_nsfw_options(self):
        captured = {}

        def fake_provider(**_kwargs):
            captured.update(_kwargs)
            return (
                "1. She spreads her pussy with two fingers and keeps staring at the camera.\n"
                "2. She starts slow circular clit rubs while pinching a nipple.\n"
                "3. She slides two fingers inside and fucks herself for the next frame.\n"
                "4. She grinds her palm against her pussy and lifts her hips.\n"
                "5. She switches to a toy and presses the tip against her entrance.\n"
                "6. She fingers herself deeper with her legs wider and mouth open.\n"
                "7. She edges herself, pulling her fingers out shiny and showing them.\n"
                "8. She builds toward orgasm, hips shaking, still holding eye contact."
            )

        service = CreativeDirectorService(
            storage_dir=tempfile.mkdtemp(),
            ask_anything_provider=fake_provider,
        )

        ideas = service.suggest_photoshoot_inspiration(
            image_bytes=b"fake-image",
            creative_mode="explicit",
            approved_history=({"title": "Shot 5"}, {"title": "Shot 6"}),
            idea_count=8,
            timeline_images=(
                {"bytes": b"s1", "label": "Shot 1 (Seed)"},
                {"bytes": b"s2", "label": "Shot 2"},
                {"bytes": b"s3", "label": "Shot 3"},
                {"bytes": b"fake-image", "label": "Shot 4 — current"},
            ),
        )

        self.assertEqual(len(ideas), 8)
        self.assertIn("progressive photoshoot ladder", captured["question"].lower())
        self.assertIn("ONE stage", captured["question"])
        self.assertIn("Never jump from early stages", captured["question"])
        self.assertIn("Active masturbation", captured["question"])
        self.assertIn("exactly 8 distinct next-scene ideas", captured["question"])
        self.assertIn("Measure the actual rate of escalation", captured["question"])
        self.assertIn("Facial expression progression", captured["question"])
        self.assertIn("MUST include a concrete facial expression", captured["question"])
        self.assertIn("Shot 1 (Seed)", captured["question"])
        self.assertEqual(len(captured["images"]), 4)
        self.assertIn("fingers inside", ideas[2].lower())

    def test_photoshoot_ask_grok_caps_very_long_timelines_but_keeps_arc(self):
        service = CreativeDirectorService(storage_dir=tempfile.mkdtemp())
        timeline = [
            {"bytes": bytes([index]), "mime_type": "image/png", "label": f"Shot {index}"}
            for index in range(1, 21)
        ]
        selected = CreativeDirectorService._select_timeline_vision_images(
            timeline_images=timeline,
            fallback_bytes=b"fallback",
            max_images=12,
        )
        self.assertEqual(len(selected), 12)
        self.assertEqual(selected[0]["label"], "Shot 1")
        self.assertEqual(selected[-1]["label"], "Shot 20")

    def test_photoshoot_creative_hint_blank_preserves_prompt_shape(self):
        captured = {}

        def fake_provider(**_kwargs):
            captured.update(_kwargs)
            return "{}"

        service = CreativeDirectorService(
            storage_dir=tempfile.mkdtemp(),
            ask_anything_provider=fake_provider,
        )

        service.recommend_photoshoot_direction(
            image_bytes=b"fake-image",
            image_mime_type="image/png",
            session_context={"session_defaults": {"wardrobe": "same outfit"}},
            approved_history=(),
            creative_mode="premium",
            session_direction="",
            creative_hint="",
            continuity_locks={"wardrobe": True},
        )

        self.assertNotIn("Creative Hint:", captured["question"])
        self.assertIn("Session Direction override: None. Maintain the current setting and outfit.", captured["question"])

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
        self.assertIn("get_active_canonical_reference", source)
        self.assertIn('"Social Studio", "Premium Studio"', source)
        self.assertNotIn("submit_wavespeed_task", source)


if __name__ == "__main__":
    unittest.main()
