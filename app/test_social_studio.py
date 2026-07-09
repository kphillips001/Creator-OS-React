import sys
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

import app.dashboard.pages.content_studio as content_studio_page
from app.dashboard.pages.content_studio import (
    SOCIAL_PROVIDER_LABELS,
    create_social_studio_generation_request,
    default_provider_index,
    execute_generation_job_to_library,
    social_studio_provider_options,
)
from app.models.asset_library import AssetLibraryItem, AssetPublishingSummary, AssetRelationshipSummary
from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationJob, GenerationRequest, GenerationResult, GenerationStatus
from app.models.reference_library import ReferenceAsset


def reference_asset(asset_id=55, creator_profile_id=7):
    item = AssetLibraryItem(
        asset_id=asset_id,
        file_name="reference.png",
        media_type="image",
        classification="TEASE",
        status="approved",
        is_active=True,
        created_at=None,
        preview_path=f"C:/Creator-OS/data/cms/vault/originals/images/{asset_id}.png",
        original_path=f"C:/Creator-OS/data/cms/vault/originals/images/{asset_id}.png",
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
            plan_id="prompt_plan_social",
            session_id="creative_session_social",
            creator_profile_id=int(creator_profile["id"]),
            prompt_text="\n\n".join(
                f"Prompt {index}: Social-safe provider-neutral prompt {index}"
                for index in range(1, int(prompt_count or 1) + 1)
            ),
            creative_mode=creative_mode,
            creative_tags=tuple(tag.strip() for tag in creative_tags.split(",") if tag.strip()),
            reference_asset_id=55,
            reference_asset_path="C:/Creator-OS/data/cms/vault/originals/images/55.png",
            creative_rationale="Created for Social Studio.",
            prompt_metadata={
                "provider_neutral": True,
                "prompt_variations": tuple(
                    f"Social-safe provider-neutral prompt {index}"
                    for index in range(1, int(prompt_count or 1) + 1)
                ),
            },
        )


class FakeRegistry:
    def provider_ids(self):
        return (
            "seedream_4_5",
            "wan_2_7_image_edit",
            "nano_banana_pro",
            "flux",
        )


class FakeGenerationEngine:
    def __init__(self):
        self.provider_registry = FakeRegistry()
        self.calls = []
        self.dispatched = []

    def queue_prompt_plan(self, **kwargs):
        self.calls.append(kwargs)
        request = GenerationRequest(
            request_id="generation_request_social",
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
        return GenerationJob(job_id="generation_job_social", request=request)

    def dispatch_job(self, job_id, progress_callback=None):
        self.dispatched.append(job_id)
        request = self.queue_prompt_plan(**self.calls[-1]).request
        if progress_callback:
            progress_callback(
                current=1,
                total=request.image_count,
                message="Image 1 of 1 completed",
                output_references=("https://cdn.test/social-output.png",),
            )
        result = GenerationResult(
            result_id="generation_result_social",
            request_id=request.request_id,
            job_id=job_id,
            provider_id=request.provider_id,
            status=GenerationStatus.SUCCEEDED.value,
            generation_metadata={"provider_response_id": "provider_social"},
            output_references=("https://cdn.test/social-output.png",),
        )
        return GenerationJob(
            job_id=job_id,
            request=request,
            status=GenerationStatus.SUCCEEDED.value,
            progress=type(GenerationJob(job_id=job_id, request=request).progress)(
                current=1,
                total=1,
                percent=100,
                message="Succeeded",
            ),
            result=result,
        )


class FakeGenerationLibrary:
    def __init__(self):
        self.synced = []

    def sync_job(self, job):
        self.synced.append(job)
        return ("generated_image_social",)


class SocialStudioTests(unittest.TestCase):
    def test_reference_selection_required(self):
        with self.assertRaises(ValueError):
            create_social_studio_generation_request(
                creator_profile={"id": 7},
                reference_service=FakeReferenceLibrary(None),
                creative_director=FakeCreativeDirector(),
                generation_engine=FakeGenerationEngine(),
                creative_tags="coffee at home",
                creative_mode="social_safe",
                prompt_count=3,
                provider_id="seedream_4_5",
            )

    def test_prompt_creation_and_generation_request_submission(self):
        references = FakeReferenceLibrary(reference_asset())
        creative_director = FakeCreativeDirector()
        engine = FakeGenerationEngine()

        plan, job = create_social_studio_generation_request(
            creator_profile={"id": 7, "display_name": "Ava"},
            reference_service=references,
            creative_director=creative_director,
            generation_engine=engine,
            creative_tags="coffee at home, window light",
            creative_mode="social_safe",
            prompt_count=4,
            provider_id="seedream_4_5",
        )

        self.assertEqual(references.calls, [7])
        self.assertEqual(plan.plan_id, "prompt_plan_social")
        self.assertEqual(creative_director.calls[0]["creative_mode"], "social_safe")
        self.assertEqual(creative_director.calls[0]["prompt_count"], 4)
        self.assertEqual(job.job_id, "generation_job_social")
        self.assertEqual(engine.calls[0]["provider_id"], "seedream_4_5")
        self.assertEqual(engine.calls[0]["image_count"], 4)
        self.assertEqual(engine.calls[0]["metadata"]["source"], "social_studio")
        self.assertEqual(len(engine.calls[0]["metadata"]["prompt_variations"]), 4)

    def test_social_submit_can_execute_and_sync_generation_library(self):
        references = FakeReferenceLibrary(reference_asset())
        creative_director = FakeCreativeDirector()
        engine = FakeGenerationEngine()
        library = FakeGenerationLibrary()
        _plan, job = create_social_studio_generation_request(
            creator_profile={"id": 7, "display_name": "Ava"},
            reference_service=references,
            creative_director=creative_director,
            generation_engine=engine,
            creative_tags="coffee at home",
            creative_mode="social_safe",
            prompt_count=1,
            provider_id="seedream_4_5",
        )

        executed, records = execute_generation_job_to_library(
            job=job,
            generation_engine=engine,
            generation_library=library,
        )

        self.assertEqual(engine.dispatched, ["generation_job_social"])
        self.assertEqual(executed.status, GenerationStatus.SUCCEEDED.value)
        self.assertEqual(records, ("generated_image_social",))
        self.assertEqual(library.synced[0].result.output_references, ("https://cdn.test/social-output.png",))

    def test_provider_selection_filters_registered_social_providers(self):
        options = social_studio_provider_options(FakeGenerationEngine())

        self.assertIn(("seedream_4_5", SOCIAL_PROVIDER_LABELS["seedream_4_5"]), options)
        self.assertIn(("wan_2_7_image_edit", SOCIAL_PROVIDER_LABELS["wan_2_7_image_edit"]), options)
        self.assertIn(("nano_banana_pro", SOCIAL_PROVIDER_LABELS["nano_banana_pro"]), options)
        self.assertNotIn(("flux", "Flux"), options)

    def test_seedream_4_5_is_default_provider_when_available(self):
        provider_ids = tuple(provider_id for provider_id, _label in social_studio_provider_options(FakeGenerationEngine()))

        self.assertEqual(provider_ids[default_provider_index(provider_ids)], "seedream_4_5")

    def test_social_studio_ui_integration_and_handoffs(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(
            encoding="utf-8"
        )
        navigation = Path("app/dashboard/navigation.py").read_text(encoding="utf-8")

        self.assertIn("def _render_social_studio", source)
        self.assertIn("Active Reference", source)
        self.assertIn("Creative Tags", source)
        self.assertIn("Creative Director Tools", source)
        self.assertIn("Enhance Social Tags", source)
        self.assertIn("Surprise Me Tags", source)
        self.assertIn("social_studio_selected_tag_source", source)
        self.assertIn("I Feel Lucky", source)
        self.assertIn("Creative Mode", source)
        self.assertIn("Prompt Count", source)
        self.assertIn("Provider", source)
        self.assertIn("Prompt Preview", source)
        self.assertIn("expanded=False", source)
        self.assertIn("Copy Prompt Batch", source)
        self.assertIn("Regenerate Prompt Preview", source)
        self.assertIn("Advanced Details", source)
        self.assertIn("prompt_variations", source)
        self.assertIn('"Generate"', source)
        self.assertIn("Generation Progress", source)
        self.assertIn("Live Generated Images", source)
        self.assertIn("Generation Complete", source)
        self.assertIn("complete_preview", source)
        self.assertIn("time.sleep(5)", source)
        self.assertIn("Reset Session", source)
        self.assertIn("reset_content_studio_session_state", source)
        self.assertIn("content_studio_reset_requested", source)
        self.assertIn("Resume Previous Generation?", source)
        self.assertIn("No active Social Studio generation session.", source)
        self.assertIn("0 of", source)
        self.assertIn("remaining", source)
        self.assertIn("Imported Assets", source)
        self.assertIn("Generation Workspace", source)
        self.assertIn("Open Asset Library", source)
        self.assertIn("Creator Review", source)
        self.assertIn('"Social Studio"', navigation)
        self.assertNotIn("submit_wavespeed_task", source)
        self.assertNotIn("poll_wavespeed_result", source)
        self.assertNotIn("upload_to_imgbb", source)
        self.assertNotIn("save_generated_image_now", source)

    def test_content_studio_reset_clears_temporary_state_only(self):
        content_studio_page.st.session_state = {
            "social_studio_creative_tags": "temporary tags",
            "social_studio_latest_generation_job_id": "job_social",
            "premium_studio_prompt_batch": ("temporary prompt",),
            "premium_grok_anything_history": [{"answer": "temporary"}],
            "content_studio_active_photoshoot_session_id": "photoshoot_session",
            "content_studio_creator_review_asset_ids": (1, 2),
            "generation_library_selected_ids": ("generated_image",),
            "dashboard_page": "Social Studio",
            "active_creator_profile_id": 7,
        }

        cleared = content_studio_page.reset_content_studio_session_state()

        self.assertIn("social_studio_creative_tags", cleared)
        self.assertIn("premium_studio_prompt_batch", cleared)
        self.assertIn("premium_grok_anything_history", cleared)
        self.assertIn("content_studio_active_photoshoot_session_id", cleared)
        self.assertNotIn("social_studio_creative_tags", content_studio_page.st.session_state)
        self.assertNotIn("premium_studio_prompt_batch", content_studio_page.st.session_state)
        self.assertNotIn("content_studio_creator_review_asset_ids", content_studio_page.st.session_state)
        self.assertEqual(
            content_studio_page.st.session_state["generation_library_selected_ids"],
            ("generated_image",),
        )
        self.assertEqual(content_studio_page.st.session_state["dashboard_page"], "Social Studio")
        self.assertEqual(content_studio_page.st.session_state["active_creator_profile_id"], 7)


if __name__ == "__main__":
    unittest.main()
