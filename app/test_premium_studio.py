import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

if "streamlit" not in sys.modules:
    streamlit = types.ModuleType("streamlit")
    sys.modules["streamlit"] = streamlit
if "streamlit.components" not in sys.modules:
    sys.modules["streamlit.components"] = types.ModuleType("streamlit.components")
if "streamlit.components.v1" not in sys.modules:
    sys.modules["streamlit.components.v1"] = types.ModuleType("streamlit.components.v1")

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
    _apply_pending_premium_prompt_source,
    _premium_prompt_source_text,
    _select_premium_prompt_source_on_next_run,
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
from app.prompts.seedream_premium_prompt_builder import (
    build_seedream_premium_prompt,
)
from app.services.creative_director_service import CreativeDirectorService
from app.services.premium_director_service import generate_premium_prompts
from app.services.premium_tag_enhancer_service import build_premium_tag_enhancer_prompt


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

    def get_active_canonical_reference(self, *, creator_profile_id):
        return self.get_active_reference(creator_profile_id=creator_profile_id)


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
            prompt_text="\n\n".join(
                f"Prompt {index}: Premium provider-neutral prompt {index}"
                for index in range(1, int(prompt_count or 1) + 1)
            ),
            creative_mode=creative_mode,
            creative_tags=self.normalize_tags(creative_tags),
            reference_asset_id=55,
            reference_asset_path="C:/Creator-OS/data/cms/vault/originals/images/55.png",
            creative_rationale="Created for Premium Studio.",
            prompt_metadata={
                "provider_neutral": True,
                "prompt_variations": tuple(
                    f"Premium provider-neutral prompt {index}"
                    for index in range(1, int(prompt_count or 1) + 1)
                ),
            },
        )


class FakeRegistry:
    def provider_ids(self):
        return (
            "seedream_4_5",
            "seedream_5_0_pro",
            "wan_2_7_image_edit",
            "nano_banana_pro",
            "nano_banana",
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

    def dispatch_job(self, job_id, progress_callback=None):
        self.dispatched.append(job_id)
        request = self.queue_prompt_plan(**self.calls[-1]).request
        if progress_callback:
            progress_callback(
                current=1,
                total=request.image_count,
                message="Image 1 of 1 completed",
                output_references=("https://cdn.test/premium-output.png",),
            )
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
    def test_enhanced_prompt_source_preserves_original_wardrobe_provenance(self):
        import streamlit as st

        original_state = getattr(st, "session_state", None)
        try:
            st.session_state = {
                "premium_studio_enhanced_tags": (
                    "beach boardwalk, shimmering coral halter crop top, "
                    "high-waisted white micro-shorts"
                )
            }

            source = _premium_prompt_source_text(
                "Enhanced Tags",
                creative_tags="tight shorts\nmicro crop top",
            )

            self.assertIn("ORIGINAL USER TAGS", source)
            self.assertIn("tight shorts, micro crop top", source)
            self.assertIn("ENHANCED SUGGESTIONS", source)
            self.assertIn("shimmering coral halter crop top", source)
        finally:
            if original_state is None:
                delattr(st, "session_state")
            else:
                st.session_state = original_state

    def test_tag_enhancer_keeps_broad_wardrobe_categories_open_for_variation(self):
        prompt = build_premium_tag_enhancer_prompt("tight shorts\nmicro crop top")

        self.assertIn("keep broad user wardrobe categories broad", prompt)
        self.assertIn('"tight shorts, micro crop top"', prompt)
        self.assertIn("do not turn it into one coral halter top with white high-waisted shorts", prompt)
        self.assertIn("wardrobe colors the user did not request", prompt)

    def test_tag_enhancer_preserves_explicit_wardrobe_details(self):
        prompt = build_premium_tag_enhancer_prompt("black leather mini skirt")

        self.assertIn('"black leather mini skirt" must remain black, leather, and a mini skirt', prompt)
        self.assertIn("preserve that exact requested detail", prompt)

    def test_premium_prompt_contract_varies_only_unspecified_wardrobe_details(self):
        broad_prompt = build_seedream_premium_prompt(
            creative_tags=(
                "[ORIGINAL USER TAGS — mandatory: tight shorts, micro crop top] "
                "[ENHANCED SUGGESTIONS — vary: coral halter top, white high-waisted shorts]"
            ),
            prompt_count=5,
        )
        explicit_prompt = build_seedream_premium_prompt(
            creative_tags="black leather mini skirt",
            prompt_count=5,
        )

        self.assertIn("CONTENT STUDIO WARDROBE VARIATION CONTRACT", broad_prompt)
        self.assertIn("only ORIGINAL USER TAGS define mandatory wardrobe", broad_prompt)
        self.assertIn("intentionally vary it across the batch", broad_prompt)
        self.assertIn('"tight shorts, micro crop top" requires tight shorts and a micro crop top', broad_prompt)
        self.assertIn('"black leather mini skirt" requires a black leather mini skirt', explicit_prompt)

    def test_premium_prompt_batch_accepts_varied_broad_wardrobe_outputs(self):
        varied_response = [
            "Black racerback micro crop top with white fitted shorts in window light.",
            "Cream tied-front micro crop top with olive tight shorts on a balcony.",
            "Coral halter micro crop top with black fitted shorts beside a pool.",
            "White cropped tank-style micro top with denim tight shorts on a boardwalk.",
            "Pink scoop-neck micro crop top with khaki fitted shorts in a kitchen doorway.",
        ]

        with patch(
            "app.services.premium_director_service.generate_prompts_with_grok",
            return_value=varied_response,
        ) as grok:
            prompts = generate_premium_prompts(
                creative_tags="tight shorts, micro crop top",
                prompt_count=5,
            )

        self.assertEqual(prompts, varied_response)
        self.assertEqual(len({prompt.split()[0] for prompt in prompts}), 5)
        self.assertIn("CONTENT STUDIO WARDROBE VARIATION CONTRACT", grok.call_args.args[0])

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
        self.assertEqual(len(engine.calls[0]["metadata"]["prompt_variations"]), 6)

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

    def test_provider_selection_exposes_only_seedream_5_0_pro(self):
        options = premium_studio_provider_options(FakeGenerationEngine())

        self.assertEqual(
            options,
            (("seedream_5_0_pro", PREMIUM_PROVIDER_LABELS["seedream_5_0_pro"]),),
        )

    def test_seedream_5_0_pro_is_default_provider_when_available(self):
        provider_ids = tuple(provider_id for provider_id, _label in premium_studio_provider_options(FakeGenerationEngine()))

        self.assertEqual(
            provider_ids[default_provider_index(provider_ids, preferred_provider_id="seedream_5_0_pro")],
            "seedream_5_0_pro",
        )

    def test_prompt_workshop_selection_is_staged_before_radio_render(self):
        import streamlit as st

        original_state = getattr(st, "session_state", None)
        try:
            st.session_state = {}

            _select_premium_prompt_source_on_next_run("Prompt Workshop")
            self.assertEqual(st.session_state["premium_studio_pending_tag_source"], "Prompt Workshop")

            _apply_pending_premium_prompt_source()

            self.assertEqual(st.session_state["premium_studio_selected_tag_source"], "Prompt Workshop")
            self.assertNotIn("premium_studio_pending_tag_source", st.session_state)
        finally:
            if original_state is None:
                delattr(st, "session_state")
            else:
                st.session_state = original_state

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
        premium_source = source.split("def _render_premium_studio", 1)[1].split("def _render_edit_studio", 1)[0]
        navigation = Path("app/dashboard/navigation.py").read_text(encoding="utf-8")

        self.assertIn("def _render_premium_studio", source)
        self.assertIn("Premium Creative Mode", premium_source)
        self.assertIn("Premium Creative Tags", premium_source)
        self.assertIn("Prompt Count", premium_source)
        self.assertIn("Provider", premium_source)
        self.assertIn("Prompt Preview", premium_source)
        self.assertIn("expanded=True", premium_source)
        self.assertIn("Copy Prompt Batch", source)
        self.assertIn("Regenerate Premium Prompt Preview", premium_source)
        self.assertIn("Advanced Details", source)
        self.assertIn("prompt_variations", source)
        self.assertIn("Generate Premium Images", premium_source)
        self.assertIn("Live Generated Images", premium_source)
        self.assertIn("complete_preview", premium_source)
        self.assertIn("preview_placeholder.empty()", source)
        self.assertNotIn("time.sleep(5)", source)
        self.assertNotIn("Start Premium Photoshoot", premium_source)
        self.assertNotIn("Continue Photoshoot", premium_source)
        self.assertNotIn("Open Existing Photoshoot", premium_source)
        self.assertNotIn("Current Photoshoot", premium_source)
        self.assertNotIn("Generation Status", premium_source)
        self.assertNotIn("Open Generation Library", premium_source)
        self.assertNotIn("Reset Session", premium_source)
        self.assertNotIn("Resume Previous Generation?", premium_source)
        self.assertNotIn("No active Content Studio generation session.", premium_source)
        self.assertIn("Creative Director Tools", premium_source)
        self.assertIn("Enhance Premium Tags", premium_source)
        self.assertIn("Surprise Me", premium_source)
        self.assertIn("Enhanced Explicit Tags", premium_source)
        self.assertIn("Prompt Workshop", source)
        self.assertIn("Canonical Prompt Planner Q&A", source)
        self.assertIn("premium_grok_anything_history", source)
        self.assertIn("Prompt Workshop Brief", source)
        self.assertIn("Accept Selected", source)
        self.assertIn("Prompt Workshop Archive", source)
        self.assertIn("Manual Prompt", premium_source)
        self.assertIn("premium_studio", premium_source)
        self.assertIn('DashboardNavigationItem("Content Studio", "Premium Studio")', navigation)
        self.assertIn('"Premium Studio": "Content Creation: Content Studio"', navigation)
        self.assertIn('st.title("Content Studio")', premium_source)
        self.assertNotIn("Premium generated images will appear here", source)
        for mode in PREMIUM_CREATIVE_MODE_LABELS:
            self.assertIn(mode, source)
        self.assertNotIn("generate_premium_images(", source)
        self.assertNotIn("premium_output_dir", source)
        self.assertNotIn("upload_to_imgbb", source)
        self.assertNotIn("submit_wavespeed_task", source)

    def test_creative_director_premium_helpers_delegate_to_wavespeed_brain(self):
        service = CreativeDirectorService(storage_dir=tempfile.mkdtemp())
        profile = {"id": 7, "display_name": "Ava"}

        with patch(
            "app.services.creative_director_service.wavespeed_enhance_premium_tags",
            return_value="enhanced hotel mirror with black lace and medium-close creator framing",
        ):
            enhanced = service.enhance_premium_tags(
                simple_tags="hotel mirror, black lace",
                creator_profile=profile,
            )
        with patch(
            "app.services.creative_director_service.wavespeed_surprise_premium_tags",
            return_value="surprise premium hotel window seat variation",
        ):
            surprise = service.surprise_premium_tags(
                simple_tags="hotel mirror",
                creator_profile=profile,
            )
        with patch(
            "app.services.creative_director_service.enhance_explicit_tags",
            return_value="explicit shower topless prompt direction",
        ):
            explicit = service.enhance_premium_tags(
                simple_tags="shower, topless",
                creator_profile=profile,
                explicit=True,
            )
        with patch(
            "app.services.creative_director_service.generate_lucky_premium_tags",
            return_value="premium lucky one\npremium lucky two",
        ):
            lucky = service.premium_lucky_tags(
                creator_profile=profile,
                prompt_count=2,
            )

        self.assertIn("medium-close creator framing", enhanced)
        self.assertEqual(surprise, "surprise premium hotel window seat variation")
        self.assertEqual(explicit, "explicit shower topless prompt direction")
        self.assertEqual(len(lucky.splitlines()), 2)

    def test_ask_grok_prompt_assistant_archive_and_apply_contract(self):
        service = CreativeDirectorService(storage_dir=tempfile.mkdtemp())
        profile = {"id": 7, "display_name": "Ava"}

        with patch(
            "app.services.canonical_prompt_planner.generate_premium_prompts",
            return_value=[
                "hotel mirror lingerie canonical prompt 1",
                "hotel mirror lingerie canonical prompt 2",
                "hotel mirror lingerie canonical prompt 3",
            ],
        ):
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

    def test_premium_prompt_plan_uses_seedream_canonical_builder(self):
        service = CreativeDirectorService(
            storage_dir=tempfile.mkdtemp(),
            reference_library_service=FakeReferenceLibrary(reference_asset()),
        )

        with patch(
            "app.services.canonical_prompt_planner.generate_premium_prompts",
            return_value=[
                "premium hotel mirror prompt with medium-close creator framing",
                "premium black lace prompt with head-to-hips crop",
            ],
        ):
            plan = service.create_prompt_plan(
                creator_profile={"id": 7, "display_name": "Ava"},
                creative_tags="hotel mirror, black lace",
                creative_mode="premium_teaser",
                prompt_count=2,
            )

        self.assertIn("premium hotel mirror prompt", plan.prompt_text)
        self.assertEqual(plan.prompt_metadata["generation_brain"], "seedream_premium_canonical")
        self.assertEqual(plan.prompt_metadata["prompt_builder"], "canonical_seedream_premium_planner")
        self.assertEqual(plan.prompt_metadata["reference_conditioning"], "seedream_5_0_pro")
        self.assertIn("medium-close creator framing", plan.prompt_text)


if __name__ == "__main__":
    unittest.main()
