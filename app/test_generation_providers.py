import os
import tempfile
import sys
import types
import unittest

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

from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationStatus
from app.providers.generation.base import GenerationProviderError
from app.providers.generation.nano_banana_provider import NanoBananaProvider
from app.providers.generation.provider_registry import ProviderRegistry, create_default_registry
from app.providers.generation.seedream_provider import Seedream45Provider
from app.providers.generation.wan_provider import WanImageEditProvider
from app.services.generation_engine_service import GenerationEngineService


class FakeResponse:
    def __init__(self, payload, status_code=200, url="https://example.test"):
        self.payload = payload
        self.status_code = status_code
        self.url = url
        self.text = str(payload)

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttpClient:
    def __init__(self, post_payload=None, get_payloads=None, post_status=200):
        self.post_payload = post_payload or {"data": {"id": "provider_request_1"}}
        self.get_payloads = list(
            get_payloads
            or [{"data": {"status": "completed", "outputs": ["https://cdn.test/output.png"]}}]
        )
        self.post_status = post_status
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse(self.post_payload, self.post_status, url)

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        payload = self.get_payloads.pop(0) if self.get_payloads else {"data": {"status": "completed"}}
        return FakeResponse(payload, 200, url)


class FakeUploadHttpClient(FakeHttpClient):
    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if "imgbb.com" in url:
            return FakeResponse({"data": {"url": "https://cdn.test/hosted-reference.png"}}, 200, url)
        return FakeResponse(self.post_payload, self.post_status, url)


def prompt_plan():
    return PromptPlan(
        plan_id="plan_provider",
        session_id="session_provider",
        creator_profile_id=7,
        prompt_text="Provider-neutral prompt text",
        creative_mode="social_safe",
        creative_tags=("window light",),
        reference_asset_id=55,
        reference_asset_path="https://cdn.test/reference.png",
        creative_rationale="Testing provider dispatch.",
        prompt_metadata={"provider_neutral": True},
    )


class NoReferenceLibraryService:
    def get_active_reference(self, *, creator_profile_id):
        return None


class GenerationProviderTests(unittest.TestCase):
    def make_engine(self, registry):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return GenerationEngineService(
            storage_dir=temp_dir.name,
            reference_library_service=NoReferenceLibraryService(),
            provider_registry=registry,
        )

    def test_default_provider_registration(self):
        registry = create_default_registry(api_key="test-key", poll_interval_seconds=0, max_poll_attempts=1)

        provider_ids = registry.provider_ids()
        self.assertIn("nano_banana", provider_ids)
        self.assertIn("nano_banana_pro", provider_ids)
        self.assertIn("wan_2_7_image_edit", provider_ids)
        self.assertIn("seedream_4_5", provider_ids)
        self.assertIn("seedream_5_0_lite", provider_ids)
        self.assertIn("flux", provider_ids)
        self.assertFalse(registry.require("flux").metadata().enabled)

    def test_provider_selection_and_payload_creation(self):
        http = FakeHttpClient()
        provider = NanoBananaProvider(
            api_key="test-key",
            http_client=http,
            poll_interval_seconds=0,
            max_poll_attempts=1,
        )
        registry = ProviderRegistry({provider.provider_id: provider})
        engine = self.make_engine(registry)
        job = engine.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(),
            provider_id="nano_banana",
        )

        completed = engine.dispatch_job(job.job_id)

        self.assertEqual(completed.status, GenerationStatus.SUCCEEDED.value)
        self.assertEqual(http.posts[0][0], provider.endpoint)
        self.assertEqual(http.posts[0][1]["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(http.posts[0][1]["json"]["prompt"], "Provider-neutral prompt text")
        self.assertEqual(http.posts[0][1]["json"]["images"], ["https://cdn.test/reference.png"])
        self.assertEqual(completed.result.output_references, ("https://cdn.test/output.png",))

    def test_local_reference_uploads_before_provider_submit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reference_path = os.path.join(temp_dir, "reference.png")
            with open(reference_path, "wb") as file:
                file.write(b"fake image bytes")

            plan = prompt_plan()
            plan = type(plan)(
                **{
                    **plan.__dict__,
                    "reference_asset_path": reference_path,
                }
            )
            http = FakeUploadHttpClient()
            provider = NanoBananaProvider(
                api_key="test-key",
                http_client=http,
                poll_interval_seconds=0,
                max_poll_attempts=1,
            )
            registry = ProviderRegistry({provider.provider_id: provider})
            engine = self.make_engine(registry)
            job = engine.queue_prompt_plan(
                creator_profile={"id": 7},
                prompt_plan=plan,
                provider_id=provider.provider_id,
            )

            old_key = os.environ.get("IMGBB_API_KEY")
            os.environ["IMGBB_API_KEY"] = "imgbb-test-key"
            try:
                completed = engine.dispatch_job(job.job_id)
            finally:
                if old_key is None:
                    os.environ.pop("IMGBB_API_KEY", None)
                else:
                    os.environ["IMGBB_API_KEY"] = old_key

        self.assertEqual(completed.status, GenerationStatus.SUCCEEDED.value)
        self.assertEqual(http.posts[0][0], "https://api.imgbb.com/1/upload")
        self.assertEqual(http.posts[1][0], provider.endpoint)
        self.assertEqual(http.posts[1][1]["json"]["images"], ["https://cdn.test/hosted-reference.png"])

    def test_prompt_count_fans_out_provider_calls_and_merges_outputs(self):
        http = FakeHttpClient(
            post_payload={"data": {"id": "provider_request"}},
            get_payloads=[
                {"data": {"status": "completed", "outputs": ["https://cdn.test/output-1.png"]}},
                {"data": {"status": "completed", "outputs": ["https://cdn.test/output-2.png"]}},
                {"data": {"status": "completed", "outputs": ["https://cdn.test/output-3.png"]}},
            ],
        )
        provider = Seedream45Provider(
            api_key="test-key",
            http_client=http,
            poll_interval_seconds=0,
            max_poll_attempts=1,
        )
        engine = self.make_engine(ProviderRegistry({provider.provider_id: provider}))
        job = engine.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(),
            provider_id=provider.provider_id,
            image_count=3,
        )

        completed = engine.dispatch_job(job.job_id)

        self.assertEqual(completed.status, GenerationStatus.SUCCEEDED.value)
        self.assertEqual(len(http.posts), 3)
        self.assertEqual(
            completed.result.output_references,
            (
                "https://cdn.test/output-1.png",
                "https://cdn.test/output-2.png",
                "https://cdn.test/output-3.png",
            ),
        )

    def test_polling_parses_running_then_completed(self):
        http = FakeHttpClient(
            get_payloads=[
                {"data": {"status": "processing"}},
                {"data": {"status": "completed", "outputs": [{"url": "https://cdn.test/final.png"}]}},
            ]
        )
        provider = Seedream45Provider(
            api_key="test-key",
            http_client=http,
            poll_interval_seconds=0,
            max_poll_attempts=2,
        )
        engine = self.make_engine(ProviderRegistry({provider.provider_id: provider}))
        job = engine.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(),
            provider_id=provider.provider_id,
        )

        completed = engine.dispatch_job(job.job_id)

        self.assertEqual(len(http.gets), 2)
        self.assertEqual(completed.status, GenerationStatus.SUCCEEDED.value)
        self.assertEqual(completed.result.output_references, ("https://cdn.test/final.png",))

    def test_retry_behavior_when_provider_api_fails(self):
        http = FakeHttpClient(post_status=500)
        provider = WanImageEditProvider(
            api_key="test-key",
            http_client=http,
            poll_interval_seconds=0,
            max_poll_attempts=1,
        )
        engine = self.make_engine(ProviderRegistry({provider.provider_id: provider}))
        job = engine.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(),
            provider_id=provider.provider_id,
            max_retries=1,
        )

        retry = engine.dispatch_job(job.job_id)

        self.assertEqual(retry.status, GenerationStatus.RETRY.value)
        self.assertEqual(retry.retry_count, 1)
        self.assertIn("WaveSpeed submit failed", retry.failure.reason)

    def test_provider_validation_blocks_unsupported_request(self):
        provider = NanoBananaProvider(api_key="test-key", http_client=FakeHttpClient())
        request = self.make_engine(ProviderRegistry({provider.provider_id: provider})).create_request(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(),
            provider_id=provider.provider_id,
            generation_type="text_to_video",
        )

        with self.assertRaises(GenerationProviderError):
            provider.validate_request(request)

    def test_generation_engine_has_no_provider_specific_implementation(self):
        with open("app/services/generation_engine_service.py", encoding="utf-8") as file:
            source = file.read()

        self.assertIn("ProviderRegistry", source)
        self.assertNotIn("api.wavespeed.ai", source)
        self.assertNotIn("WAVESPEED_API_KEY", source)
        self.assertNotIn("NanoBananaProvider", source)
        self.assertNotIn("Seedream45Provider", source)
        self.assertNotIn("WanImageEditProvider", source)


if __name__ == "__main__":
    unittest.main()
