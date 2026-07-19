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
from app.models.creative_director import PromptPlan
from app.models.generation_engine import (
    GenerationFailure,
    GenerationResult,
    GenerationStatus,
    GenerationType,
    new_generation_id,
)
from app.models.reference_library import ReferenceAsset
from app.providers.generation.base import (
    ProviderCapabilities,
    ProviderPollResult,
    ProviderSubmission,
    WaveSpeedProviderBase,
)
from app.services.generation_engine_service import GenerationEngineService


def prompt_plan(creator_profile_id=7, reference_asset_id=55):
    return PromptPlan(
        plan_id=f"plan_{creator_profile_id}",
        session_id=f"session_{creator_profile_id}",
        creator_profile_id=creator_profile_id,
        prompt_text="Provider-neutral prompt text",
        creative_mode="social_safe",
        creative_tags=("window light", "portrait"),
        reference_asset_id=reference_asset_id,
        reference_asset_path=f"C:/Creator-OS/data/cms/vault/originals/images/{reference_asset_id}.png",
        creative_rationale="Testing prompt planning handoff.",
        prompt_metadata={"provider_neutral": True},
    )


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
        is_favorite=False,
    )


class FakeReferenceLibraryService:
    def __init__(self, active_reference=None):
        self.active_reference = active_reference
        self.calls = []

    def get_active_reference(self, *, creator_profile_id):
        self.calls.append(creator_profile_id)
        if self.active_reference and self.active_reference.creator_profile_id == creator_profile_id:
            return self.active_reference
        return None


class FakeGenerationProvider:
    provider_id = "fake_provider"

    def __init__(self):
        self.requests = []

    def dispatch(self, request):
        self.requests.append(request)
        return GenerationResult(
            result_id=new_generation_id("generation_result"),
            request_id=request.request_id,
            job_id="pending",
            provider_id=self.provider_id,
            status=GenerationStatus.SUCCEEDED.value,
            generation_metadata={"provider": "fake_provider"},
            execution_metadata={"external_api_called": False},
            image_metadata={"count": request.image_count},
            output_references=("future_asset_reference",),
        )


class FakeResilientWaveProvider(WaveSpeedProviderBase):
    provider_id = "fake_resilient_wave"
    display_name = "Fake Resilient Wave"
    endpoint = "https://example.test/generate"
    capabilities = ProviderCapabilities(
        supported_generation_types=(GenerationType.IMAGE_TO_IMAGE.value,),
        max_images=1,
    )

    def __init__(self, *, fail_submissions=(), fail_polls=()):
        super().__init__(api_key="test-key")
        self.fail_submissions = set(fail_submissions)
        self.fail_polls = set(fail_polls)
        self.submission_count = 0

    def validate_request(self, request):
        return None

    def submit_generation(self, request):
        self.submission_count += 1
        index = self.submission_count
        if index in self.fail_submissions:
            raise RuntimeError(f"submit failed {index}")
        return ProviderSubmission(
            provider_request_id=f"provider-{index}",
            raw_response={"index": index},
        )

    def poll_status(self, submission):
        index = int(submission.provider_request_id.rsplit("-", 1)[1])
        if index in self.fail_polls:
            return ProviderPollResult(
                provider_request_id=submission.provider_request_id,
                status=GenerationStatus.FAILED.value,
                raw_response={"index": index, "status": "failed"},
                failure_reason=f"poll failed {index}",
            )
        return ProviderPollResult(
            provider_request_id=submission.provider_request_id,
            status=GenerationStatus.SUCCEEDED.value,
            raw_response={"index": index, "status": "succeeded"},
            output_references=(f"generated-{index}.png",),
        )


class GenerationEngineServiceTests(unittest.TestCase):
    def make_service(self, active_reference=None, providers=None):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return GenerationEngineService(
            storage_dir=temp_dir.name,
            reference_library_service=FakeReferenceLibraryService(active_reference),
            providers=providers,
        )

    def test_generation_request_creation_uses_prompt_plan_and_active_reference(self):
        service = self.make_service(reference_asset(asset_id=99, creator_profile_id=7))

        request = service.create_request(
            creator_profile={"id": 7, "display_name": "Ava"},
            prompt_plan=prompt_plan(creator_profile_id=7, reference_asset_id=55),
            provider_id="future_provider",
            image_count=3,
        )

        self.assertEqual(request.creator_profile_id, 7)
        self.assertEqual(request.prompt_plan_id, "plan_7")
        self.assertEqual(request.prompt_text, "Provider-neutral prompt text")
        self.assertEqual(request.reference_asset_id, 99)
        self.assertIn("99.png", request.reference_asset_path)
        self.assertEqual(request.provider_id, "future_provider")
        self.assertEqual(request.generation_type, "image_to_image")
        self.assertEqual(request.media_type, "image")
        self.assertEqual(request.image_count, 3)
        self.assertTrue(request.metadata["provider_neutral"])
        self.assertIn("99.png", request.metadata["canonical_reference_image_url"])

    def test_canonical_reference_changes_are_resolved_for_each_new_request(self):
        references = FakeReferenceLibraryService(reference_asset(asset_id=99, creator_profile_id=7))
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        service = GenerationEngineService(storage_dir=temp_dir.name, reference_library_service=references, providers={})
        first = service.create_request(creator_profile={"id": 7}, prompt_plan=prompt_plan(), provider_id="future_provider")
        references.active_reference = reference_asset(asset_id=100, creator_profile_id=7)
        second = service.create_request(creator_profile={"id": 7}, prompt_plan=prompt_plan(), provider_id="future_provider")

        self.assertIn("99.png", first.metadata["canonical_reference_image_url"])
        self.assertIn("100.png", second.metadata["canonical_reference_image_url"])

    def test_generation_job_lifecycle(self):
        service = self.make_service()
        request = service.create_request(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(),
            provider_id="future_provider",
        )

        queued = service.enqueue(request)
        running = service.start_job(queued.job_id)
        completed = service.complete_job(running.job_id)

        self.assertEqual(queued.status, GenerationStatus.QUEUED.value)
        self.assertEqual(running.status, GenerationStatus.RUNNING.value)
        self.assertIsNotNone(running.started_at)
        self.assertEqual(completed.status, GenerationStatus.SUCCEEDED.value)
        self.assertEqual(completed.progress.percent, 100.0)
        self.assertIsNotNone(completed.completed_at)
        self.assertIsNotNone(completed.result)

    def test_queue_behavior_is_fifo_and_creator_scoped(self):
        service = self.make_service()
        first = service.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(creator_profile_id=7),
        )
        second = service.queue_prompt_plan(
            creator_profile={"id": 8},
            prompt_plan=prompt_plan(creator_profile_id=8, reference_asset_id=88),
        )

        self.assertEqual(service.next_queued_job().job_id, first.job_id)
        self.assertEqual([job.job_id for job in service.list_jobs()], [first.job_id, second.job_id])
        self.assertEqual(service.list_jobs(creator_profile_id=8)[0].job_id, second.job_id)

    def test_provider_dispatch_abstraction(self):
        provider = FakeGenerationProvider()
        service = self.make_service(providers={provider.provider_id: provider})
        job = service.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(),
            provider_id=provider.provider_id,
            image_count=2,
        )

        dispatched = service.dispatch_job(job.job_id)

        self.assertEqual(dispatched.status, GenerationStatus.SUCCEEDED.value)
        self.assertEqual(dispatched.result.provider_id, provider.provider_id)
        self.assertEqual(dispatched.result.image_metadata["count"], 2)
        self.assertEqual(provider.requests[0].prompt_plan_id, "plan_7")

    def test_generation_provider_continues_after_per_image_failures(self):
        provider = FakeResilientWaveProvider(fail_submissions=(2,), fail_polls=(3,))
        service = self.make_service(providers={provider.provider_id: provider})
        events = []
        job = service.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(),
            provider_id=provider.provider_id,
            image_count=4,
        )

        dispatched = service.dispatch_job(job.job_id, progress_callback=lambda **event: events.append(event))

        self.assertEqual(dispatched.status, GenerationStatus.SUCCEEDED.value)
        self.assertEqual(dispatched.result.output_references, ("generated-1.png", "generated-4.png"))
        self.assertEqual(dispatched.result.image_metadata["completed_count"], 2)
        self.assertEqual(dispatched.result.image_metadata["failed_count"], 2)
        self.assertEqual(dispatched.result.image_metadata["processed_count"], 4)
        self.assertTrue(dispatched.result.generation_metadata["partial_success"])
        self.assertEqual(events[-1]["processed_count"], 4)
        self.assertEqual(events[-1]["failed_count"], 2)

    def test_generation_provider_reports_complete_failure_only_when_all_images_fail(self):
        provider = FakeResilientWaveProvider(fail_submissions=(1, 2))
        service = self.make_service(providers={provider.provider_id: provider})
        job = service.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(),
            provider_id=provider.provider_id,
            image_count=2,
        )

        dispatched = service.dispatch_job(job.job_id)

        self.assertEqual(dispatched.status, GenerationStatus.FAILED.value)
        self.assertIn("submit failed 1", dispatched.failure.reason)
        self.assertNotIn("Generation provider returned a failure result.", dispatched.failure.reason)

    def test_retry_state_and_failure_are_tracked(self):
        service = self.make_service()
        job = service.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(),
            max_retries=1,
        )

        retry = service.fail_job(job.job_id, GenerationFailure(reason="temporary"))
        failed = service.fail_job(job.job_id, GenerationFailure(reason="permanent"))

        self.assertEqual(retry.status, GenerationStatus.RETRY.value)
        self.assertEqual(retry.retry_count, 1)
        self.assertEqual(failed.status, GenerationStatus.FAILED.value)
        self.assertEqual(failed.failure.reason, "permanent")

    def test_content_studio_creates_generation_requests_without_provider_calls(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(
            encoding="utf-8"
        )
        engine_source = Path("app/services/generation_engine_service.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("GenerationEngineService", source)
        self.assertIn("queue_prompt_plan", source)
        self.assertIn("latest_job_for_prompt_plan", source)
        self.assertIn('"Social Studio", "Premium Studio", "Creative Director"', source)
        self.assertNotIn("submit_wavespeed_task", source)
        self.assertNotIn("poll_status(", source)
        self.assertNotIn("submit_generation(", source)
        self.assertNotIn("Nano Banana", engine_source)
        self.assertNotIn("Seedream", engine_source)
        self.assertNotIn("Flux", engine_source)
        self.assertNotIn("WAN", engine_source)


if __name__ == "__main__":
    unittest.main()
