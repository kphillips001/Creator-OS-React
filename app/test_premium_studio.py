import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

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

from app.dashboard.pages.content_studio import (
    PREMIUM_CREATIVE_MODE_LABELS,
    PREMIUM_PROVIDER_LABELS,
    create_premium_photoshoot_session,
    create_premium_studio_generation_request,
    default_provider_index,
    execute_generation_job_to_library,
    premium_studio_provider_options,
)
from app.models.asset_library import (
    AssetLibraryItem,
    AssetPublishingSummary,
    AssetRelationshipSummary,
)
from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationJob, GenerationRequest, GenerationResult, GenerationStatus
from app.models.reference_library import ReferenceAsset
from app.services.creative_director_service import CreativeDirectorService


def reference_asset(asset_id=55, creator_profile_id=7):
    item = AssetLibraryItem(
        asset_id=asset_id,
        file_name="premium-reference.png",
        media_type="image",
        classification="TEASE",
        status="approved",
        is_active=True,
        created_at=None,
        preview_path=f"C:/Creator-OS/data/cms/vault/originals/images/{asset_id}.png",
        original_path=f"C:/Creator-OS/data/cms/vault/originals/images/{asset_id}.png",
        tags=("reference", "premium"),
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
    )


class FakeReferenceLibrary:
    def __init__(self, active_reference=None):
        self.active_reference = active_reference
        self.calls = []

    def get_active_reference(self, *, creator_profile_id):
        self.calls.append(creator_profile_id)
        if self.active_reference and self.active_reference.creator_profile_id == creator_profile_id:
            return self.active_reference
        return None


class FakeCreativeDirector:
    def __init__(self):
        self.calls = []

    def normalize_tags(self, creative_tags):
        return tuple(tag.strip() for tag in str(creative_tags).replace("\n", ",").split(",") if tag.strip())

    def create_prompt_plan(self, *, creator_profile, creative_tags, creative_mode, prompt_count):
        self.calls.append(
            {
                "creator_profile": creator_profile,
                "creative_tags": creative_tags,
                "creative_mode": creative_mode,
                "prompt_count": prompt_count,
            }
        )
        return PromptPlan(
            plan_id=f"prompt_plan_premium_{len(self.calls)}",
            session_id=f"creative_session_premium_{len(self.calls)}",
            creator_profile_id=int(creator_profile["id"]),
            prompt_text="Premium provider-neutral prompt",
            creative_mode=creative_mode,
            creative_tags=self.normalize_tags(creative_tags),
            reference_asset_id=55,
            reference_asset_path="C:/Creator-OS/data/cms/vault/originals/images/55.png",
            creative_rationale="Created for Premium Studio.",
            prompt_metadata={"provider_neutral": True},
        )


class FakeRegistry:
    def provider_ids(self):
        return (
            "seedream_4_5",
            "wan_2_7_image_edit",
            "nano_banana_pro",
            "flux",
            "unknown_provider",
        )


class FakeGenerationEngine:
    def __init__(self):
        self.provider_registry = FakeRegistry()
        self.calls = []
        self.dispatched = []

    def queue_prompt_plan(self, **kwargs):
        self.calls.append(kwargs)
        request = GenerationRequest(
            request_id="generation_request_premium",
            creator_profile_id=int(kwargs["creator_profile"]["id"]),
            prompt_plan_id=kwargs["prompt_plan"].plan_id,
            prompt_text=kwargs["prompt_plan"].prompt_text,
            reference_asset_id=55,
            reference_asset_path="C:/Creator-OS/data/cms/vault/originals/images/55.png",
            provider_id=kwargs["provider_id"],
            generation_type=kwargs["generation_type"],
            media_type=kwargs["media_type"],
            image_count=kwargs["image_count"],
            metadata=kwargs["metadata"],
        )
        return GenerationJob(job_id="generation_job_premium", request=request)

    def dispatch_job(self, job_id):
        self.dispatched.append(job_id)
        request = self.queue_prompt_plan(**self.calls[-1]).request
        result = GenerationResult(
            result_id="generation_result_premium",
            request_id=request.request_id,
            job_id=job_id,
            provider_id=request.provider_id,
            status=GenerationStatus.SUCCEEDED.value,
            generation_metadata={"provider_response_id": "provider_premium"},
            output_references=("https://cdn.test/premium-output.png",),
        )
        return GenerationJob(
            job_id=job_id,
            request=request,
            status=GenerationStatus.SUCCEEDED.value,
            result=result,
        )


class FakeGenerationLibrary:
    def __init__(self):
        self.synced = []

    def sync_job(self, job):
        self.synced.append(job)
        return ("generated_image_premium",)


class FakePhotoshootQueue:
    def __init__(self):
        self.calls = []

    def create_session(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            session_id="photoshoot_session_premium",
            title=kwargs["title"],
            provider_id=kwargs["provider_id"],
            reference_asset_id=kwargs["reference_asset_id"],
            creative_continuity=kwargs["creative_continuity"],
        )


class PremiumStudioTests(unittest.TestCase):
    def test_premium_workflow_requires_active_reference(self):
        with self.assertRaises(ValueError):
            create_premium_studio_generation_request(
                creator_profile={"id": 7},
                reference_service=FakeReferenceLibrary(None),
                creative_director=FakeCreativeDirector(),
                generation_engine=FakeGenerationEngine(),
                creative_tags="hotel room, satin robe",
                creative_mode="premium_teaser",
                prompt_count=4,
                provider_id="wan_2_7_image_edit",
            )

    def test_prompt_creation_and_generation_submission(self):
        references = FakeReferenceLibrary(reference_asset())
        creative_director = FakeCreativeDirector()
        engine = FakeGenerationEngine()

        plan, job = create_premium_studio_generation_request(
            creator_profile={"id": 7, "display_name": "Ava"},
            reference_service=references,
            creative_director=creative_director,
            generation_engine=engine,
            creative_tags="hotel room, satin robe, warm window light",
            creative_mode="premium_teaser",
            prompt_count=6,
            provider_id="wan_2_7_image_edit",
        )

        self.assertEqual(references.calls, [7])
        self.assertEqual(plan.creative_mode, "premium_teaser")
        self.assertEqual(creative_director.calls[0]["prompt_count"], 6)
        self.assertEqual(job.job_id, "generation_job_premium")
        self.assertEqual(engine.calls[0]["provider_id"], "wan_2_7_image_edit")
        self.assertEqual(engine.calls[0]["image_count"], 6)
        self.assertEqual(engine.calls[0]["metadata"]["source"], "premium_studio")
        self.assertTrue(engine.calls[0]["metadata"]["premium_workflow"])

    def test_premium_submit_can_execute_and_sync_generation_library(self):
        references = FakeReferenceLibrary(reference_asset())
        creative_director = FakeCreativeDirector()
        engine = FakeGenerationEngine()
        library = FakeGenerationLibrary()
        _plan, job = create_premium_studio_generation_request(
            creator_profile={"id": 7, "display_name": "Ava"},
            reference_service=references,
            creative_director=creative_director,
            generation_engine=engine,
            creative_tags="hotel room, satin robe",
            creative_mode="premium_teaser",
            prompt_count=1,
            provider_id="wan_2_7_image_edit",
        )

        executed, records = execute_generation_job_to_library(
            job=job,
            generation_engine=engine,
            generation_library=library,
        )

        self.assertEqual(engine.dispatched, ["generation_job_premium"])
        self.assertEqual(executed.status, GenerationStatus.SUCCEEDED.value)
        self.assertEqual(records, ("generated_image_premium",))
        self.assertEqual(library.synced[0].result.output_references, ("https://cdn.test/premium-output.png",))

    def test_provider_selection_includes_premium_providers(self):
        options = premium_studio_provider_options(FakeGenerationEngine())

        self.assertIn(("seedream_4_5", PREMIUM_PROVIDER_LABELS["seedream_4_5"]), options)
        self.assertIn(("wan_2_7_image_edit", PREMIUM_PROVIDER_LABELS["wan_2_7_image_edit"]), options)
        self.assertIn(("nano_banana_pro", PREMIUM_PROVIDER_LABELS["nano_banana_pro"]), options)
        self.assertIn(("flux", PREMIUM_PROVIDER_LABELS["flux"]), options)
        self.assertNotIn(("unknown_provider", "unknown_provider"), options)

    def test_seedream_4_5_is_default_provider_when_available(self):
        provider_ids = tuple(provider_id for provider_id, _label in premium_studio_provider_options(FakeGenerationEngine()))

        self.assertEqual(provider_ids[default_provider_index(provider_ids)], "seedream_4_5")

    def test_photoshoot_integration_creates_premium_sequence(self):
        references = FakeReferenceLibrary(reference_asset())
        creative_director = FakeCreativeDirector()
        photoshoot_queue = FakePhotoshootQueue()

        session = create_premium_photoshoot_session(
            creator_profile={"id": 7},
            reference_service=references,
            creative_director=creative_director,
            photoshoot_queue=photoshoot_queue,
            creative_tags="black lace, hotel mirror, premium teaser",
            creative_mode="spicy",
            prompt_count=3,
            provider_id="nano_banana_pro",
            creator_notes="Premium run",
        )

        self.assertEqual(session.title, "Premium Photoshoot")
        self.assertEqual(session.provider_id, "nano_banana_pro")
        self.assertEqual(len(creative_director.calls), 3)
        self.assertEqual(len(photoshoot_queue.calls[0]["prompt_plans"]), 3)
        self.assertTrue(photoshoot_queue.calls[0]["creative_continuity"]["premium_workflow"])
        self.assertEqual(photoshoot_queue.calls[0]["creative_continuity"]["source"], "premium_studio")

    def test_premium_studio_ui_contract_and_generation_library_integration(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(encoding="utf-8")
        navigation = Path("app/dashboard/navigation.py").read_text(encoding="utf-8")

        self.assertIn("def _render_premium_studio", source)
        self.assertIn("Premium Creative Mode", source)
        self.assertIn("Premium Creative Tags", source)
        self.assertIn("Prompt Count", source)
        self.assertIn("Provider", source)
        self.assertIn("Prompt Preview", source)
        self.assertIn("Generate Premium Images", source)
        self.assertIn("Start Premium Photoshoot", source)
        self.assertIn("Generation Status", source)
        self.assertIn("Generation Library", source)
        self.assertIn("Creative Director Tools", source)
        self.assertIn("Enhance Premium Tags", source)
        self.assertIn("Surprise Me", source)
        self.assertIn("Enhanced Explicit Tags", source)
        self.assertIn("Ask Grok / Prompt Assistant", source)
        self.assertIn("Ask Grok for Shot Cards", source)
        self.assertIn("Apply to Premium Tags", source)
        self.assertIn("Prompt Archive", source)
        self.assertIn("Manual Prompt", source)
        self.assertIn("generation_library.sync_jobs", source)
        self.assertIn("premium_studio", source)
        self.assertIn('"Premium Studio"', navigation)
        for mode in PREMIUM_CREATIVE_MODE_LABELS:
            self.assertIn(mode, source)
        self.assertNotIn("generate_premium_images(", source)
        self.assertNotIn("premium_output_dir", source)
        self.assertNotIn("upload_to_imgbb", source)
        self.assertNotIn("submit_wavespeed_task", source)

    def test_creative_director_premium_enhanced_tags_and_surprise_workflow(self):
        service = CreativeDirectorService(storage_dir=tempfile.mkdtemp())
        profile = {"id": 7, "display_name": "Ava"}

        enhanced = service.enhance_premium_tags(
            simple_tags="hotel mirror, black lace",
            creator_profile=profile,
        )
        surprise = service.surprise_premium_tags(
            simple_tags="hotel mirror",
            creator_profile=profile,
        )
        explicit = service.enhance_premium_tags(
            simple_tags="shower, topless",
            creator_profile=profile,
            explicit=True,
        )
        lucky = service.premium_lucky_tags(
            creator_profile=profile,
            prompt_count=2,
        )

        self.assertIn("hotel mirror", enhanced)
        self.assertIn("premium teaser", enhanced)
        self.assertIn("same reference identity", enhanced)
        self.assertIn("unexpected premium variation", surprise)
        self.assertIn("explicit-ready premium", explicit)
        self.assertEqual(len(lucky.splitlines()), 2)

    def test_ask_grok_prompt_assistant_archive_and_apply_contract(self):
        service = CreativeDirectorService(storage_dir=tempfile.mkdtemp())
        profile = {"id": 7, "display_name": "Ava"}

        batch = service.ask_prompt_assistant(
            creator_profile=profile,
            request_text="hotel mirror lingerie",
            lane="premium",
            prompt_count=3,
        )
        service.mark_prompt_assistant_used(batch.batch_id, 2)
        history = service.prompt_assistant_history(creator_profile_id=7)

        self.assertEqual(len(batch.prompts), 3)
        self.assertIn("hotel mirror lingerie", batch.prompts[0])
        self.assertEqual(history[0].batch_id, batch.batch_id)
        self.assertIn(2, history[0].used_prompt_numbers)

    def test_premium_prompt_plan_contains_old_premium_guidance(self):
        service = CreativeDirectorService(
            storage_dir=tempfile.mkdtemp(),
            reference_library_service=FakeReferenceLibrary(reference_asset()),
        )

        plan = service.create_prompt_plan(
            creator_profile={"id": 7, "display_name": "Ava"},
            creative_tags="hotel mirror, black lace",
            creative_mode="premium_teaser",
            prompt_count=2,
        )

        self.assertIn("Premium guidance", plan.prompt_text)
        self.assertIn("active reference", plan.prompt_text.lower())
        self.assertIn("premium_guidance", plan.prompt_metadata)


if __name__ == "__main__":
    unittest.main()
