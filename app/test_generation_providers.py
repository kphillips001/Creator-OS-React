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
from app.providers.generation.seedream_provider import Seedream45Provider, Seedream50ProProvider
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
    def get_active_canonical_reference(self, *, creator_profile_id):
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
        self.assertIn("seedream_5_0_pro", provider_ids)
        self.assertIn("flux", provider_ids)
        self.assertFalse(registry.require("flux").metadata().enabled)
        self.assertEqual(registry.require("seedream_5_0_pro").capabilities.max_reference_images, 10)

    def test_seedream_5_photoshoot_payload_orders_identity_then_continuity_reference(self):
        provider = Seedream50ProProvider(api_key="test-key", http_client=FakeHttpClient())
        engine = self.make_engine(ProviderRegistry({provider.provider_id: provider}))
        for creative_mode in ("safe", "premium", "explicit"):
            request = engine.create_request(
                creator_profile={"id": 7}, prompt_plan=prompt_plan(), provider_id=provider.provider_id,
                metadata={
                    "workflow_type": "photoshoot", "creative_mode": creative_mode,
                    "canonical_reference_image_url": "https://cdn.test/canonical.png",
                    "reference_image_url": "https://cdn.test/latest-shot.png",
                    "photoshoot_continuity_reference_image_url": "https://cdn.test/latest-shot.png",
                },
            )
            self.assertEqual(provider.build_payload(request)["images"], [
                "https://cdn.test/canonical.png", "https://cdn.test/latest-shot.png",
            ])
            role_guidance = provider.build_payload(request)["prompt"]
            self.assertIn("Image 1 is the canonical creator identity reference", role_guidance)
            self.assertIn("Image 1 controls identity", role_guidance)
            self.assertIn("Image 2 is the latest approved Photoshoot image", role_guidance)
            self.assertIn("Image 2 controls Photoshoot continuity", role_guidance)
            self.assertIn("Do not use Image 2 to redefine the creator's facial identity", role_guidance)

    def test_single_reference_provider_keeps_latest_photoshoot_shot(self):
        provider = Seedream45Provider(api_key="test-key", http_client=FakeHttpClient())
        request = self.make_engine(ProviderRegistry({provider.provider_id: provider})).create_request(
            creator_profile={"id": 7}, prompt_plan=prompt_plan(), provider_id=provider.provider_id,
            metadata={
                "workflow_type": "photoshoot",
                "canonical_reference_image_url": "https://cdn.test/canonical.png",
                "reference_image_url": "https://cdn.test/latest-shot.png",
                "photoshoot_continuity_reference_image_url": "https://cdn.test/latest-shot.png",
            },
        )
        payload = provider.build_payload(request)
        self.assertEqual(payload["images"], ["https://cdn.test/latest-shot.png"])
        self.assertNotIn("Image 1 is the canonical creator identity reference", payload["prompt"])

    def test_seedream_5_non_photoshoot_prompt_has_no_photoshoot_reference_roles(self):
        provider = Seedream50ProProvider(api_key="test-key", http_client=FakeHttpClient())
        request = self.make_engine(ProviderRegistry({provider.provider_id: provider})).create_request(
            creator_profile={"id": 7}, prompt_plan=prompt_plan(), provider_id=provider.provider_id,
            metadata={
                "workflow_type": "content_studio",
                "canonical_reference_image_url": "https://cdn.test/canonical.png",
                "reference_image_url": "https://cdn.test/canonical.png",
            },
        )
        payload = provider.build_payload(request)
        self.assertEqual(payload["images"], ["https://cdn.test/canonical.png"])
        self.assertNotIn("Image 1 is the canonical creator identity reference", payload["prompt"])

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
        self.assertIn("Provider-neutral prompt text", http.posts[0][1]["json"]["prompt"])
        self.assertIn("SOCIAL CLOSE-FRAMING LOCK", http.posts[0][1]["json"]["prompt"])
        self.assertEqual(http.posts[0][1]["json"]["images"], ["https://cdn.test/reference.png"])
        self.assertEqual(completed.result.output_references, ("https://cdn.test/output.png",))

    def test_provider_submits_prompt_variation_per_image(self):
        http = FakeHttpClient(
            get_payloads=[
                {"data": {"status": "completed", "outputs": ["https://cdn.test/output-1.png"]}},
                {"data": {"status": "completed", "outputs": ["https://cdn.test/output-2.png"]}},
            ]
        )
        provider = Seedream45Provider(
            api_key="test-key",
            http_client=http,
            poll_interval_seconds=0,
            max_poll_attempts=1,
        )
        registry = ProviderRegistry({provider.provider_id: provider})
        engine = self.make_engine(registry)
        plan = prompt_plan()
        plan = type(plan)(
            **{
                **plan.__dict__,
                "prompt_text": "Prompt 1: varied shot one\n\nPrompt 2: varied shot two",
                "prompt_metadata": {
                    **dict(plan.prompt_metadata),
                    "prompt_variations": ("varied shot one", "varied shot two"),
                },
            }
        )
        job = engine.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=plan,
            provider_id=provider.provider_id,
            image_count=2,
        )

        completed = engine.dispatch_job(job.job_id)

        payloads = [post[1]["json"]["prompt"] for post in http.posts]
        self.assertIn("varied shot one", payloads[0])
        self.assertIn("varied shot two", payloads[1])
        self.assertIn("SOCIAL CLOSE-FRAMING LOCK", payloads[0])
        self.assertIn("SOCIAL CLOSE-FRAMING LOCK", payloads[1])
        self.assertIn("Avoid visible phone/cellphone/selfie-device poses", payloads[0])
        self.assertNotIn("varied shot two", payloads[0])
        self.assertNotIn("varied shot one", payloads[1])
        self.assertEqual(completed.result.output_references, ("https://cdn.test/output-1.png", "https://cdn.test/output-2.png"))

    def test_premium_payload_applies_body_and_topless_render_locks(self):
        http = FakeHttpClient()
        provider = WanImageEditProvider(
            api_key="test-key",
            http_client=http,
            poll_interval_seconds=0,
            max_poll_attempts=1,
        )
        registry = ProviderRegistry({provider.provider_id: provider})
        engine = self.make_engine(registry)
        plan = prompt_plan()
        plan = type(plan)(
            **{
                **plan.__dict__,
                "prompt_text": "topless private premium prompt, bare breasts visible",
                "creative_mode": "premium_teaser",
                "prompt_metadata": {
                    **dict(plan.prompt_metadata),
                    "prompt_variations": ("topless private premium prompt, bare breasts visible",),
                },
            }
        )
        job = engine.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=plan,
            provider_id=provider.provider_id,
            metadata={"workflow_type": "premium", "creative_mode": "premium_teaser"},
        )

        completed = engine.dispatch_job(job.job_id)
        prompt_payload = http.posts[0][1]["json"]["prompt"]

        self.assertEqual(completed.status, GenerationStatus.SUCCEEDED.value)
        self.assertIn("FINAL REFERENCE BODY LOCK", prompt_payload)
        self.assertIn("Keep the scalp area natural and low-profile", prompt_payload)
        self.assertIn("Unless the prompt explicitly asks for a wide shot", prompt_payload)
        self.assertIn("TOPLESS RENDER LOCK", prompt_payload)
        self.assertIn("EXPLICIT EXPRESSION VARIATION", prompt_payload)

    def test_premium_clothed_teaser_payload_preserves_requested_wardrobe(self):
        http = FakeHttpClient()
        provider = Seedream45Provider(
            api_key="test-key",
            http_client=http,
            poll_interval_seconds=0,
            max_poll_attempts=1,
        )
        registry = ProviderRegistry({provider.provider_id: provider})
        engine = self.make_engine(registry)
        plan = prompt_plan()
        prompt_text = (
            "Ribbed or Mesh Crop Tank + Low-Rise Cargo Mini Skirt, premium teaser, "
            "non-explicit wardrobe lock, no nudity, no topless result, no bare breasts, "
            "unless nudity was explicitly requested"
        )
        plan = type(plan)(
            **{
                **plan.__dict__,
                "prompt_text": prompt_text,
                "creative_mode": "premium_teaser",
                "prompt_metadata": {
                    **dict(plan.prompt_metadata),
                    "prompt_variations": (prompt_text,),
                },
            }
        )
        job = engine.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=plan,
            provider_id=provider.provider_id,
            metadata={"workflow_type": "premium", "creative_mode": "premium_teaser"},
        )

        completed = engine.dispatch_job(job.job_id)
        prompt_payload = http.posts[0][1]["json"]["prompt"]

        self.assertEqual(completed.status, GenerationStatus.SUCCEEDED.value)
        self.assertIn("FINAL REFERENCE BODY LOCK", prompt_payload)
        self.assertIn("Crop Tank", prompt_payload)
        self.assertIn("Mini Skirt", prompt_payload)
        self.assertIn("TOPLESS RENDER LOCK", prompt_payload)
        self.assertNotIn("WAN BUST VISIBILITY LOCK", prompt_payload)
        self.assertIn("EXPLICIT EXPRESSION VARIATION", prompt_payload)

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
        self.assertEqual(http.posts[0][1]["params"], {"key": "imgbb-test-key"})
        upload_name, upload_bytes, upload_type = http.posts[0][1]["files"]["image"]
        self.assertEqual(upload_name, "reference.jpg")
        self.assertEqual(upload_bytes, b"fake image bytes")
        self.assertEqual(upload_type, "image/jpeg")
        self.assertEqual(http.posts[0][1]["data"], {"name": "reference"})
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
