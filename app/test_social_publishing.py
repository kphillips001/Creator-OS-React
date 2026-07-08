import sys
import tempfile
import types
import unittest
import os
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

from app.models.generation_engine import (
    GenerationJob,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)
from app.models.generation_ingestion import GenerationResultIngestionResult
from app.models.generation_library import GeneratedImageRecord
from app.models.social_publishing import SocialPlatform, SocialPublishStatus
from PIL import Image

from app.providers.social.x_provider import XPublishResult, XPublishingProvider
from app.services.generation_library_service import GenerationLibraryService
from app.services.social_publishing_service import SocialPublishingService


def generated_record(image_id="generated_image_social_1"):
    return GeneratedImageRecord(
        image_id=image_id,
        generation_job_id="generation_job_social",
        generation_request_id="generation_request_social",
        generation_result_id="generation_result_social",
        output_reference="https://cdn.test/social.png",
        creator_profile_id=7,
        provider_id="seedream_4_5",
        prompt_plan_id="prompt_plan_social",
        prompt_text="Social-safe marketing prompt",
        creative_mode="social_safe",
        reference_asset_id=55,
        provider_metadata={"provider_response_id": "provider_123"},
        prompt_metadata={"creative_tags": ("coffee", "window light")},
        generation_metadata={"request_metadata": {"source": "social_studio"}},
    )


def successful_job():
    request = GenerationRequest(
        request_id="generation_request_social",
        creator_profile_id=7,
        prompt_plan_id="prompt_plan_social",
        prompt_text="Social-safe marketing prompt",
        reference_asset_id=55,
        reference_asset_path=None,
        provider_id="seedream_4_5",
        generation_type="image_to_image",
        media_type="image",
        image_count=1,
        metadata={"source": "social_studio"},
    )
    result = GenerationResult(
        result_id="generation_result_social",
        request_id=request.request_id,
        job_id="generation_job_social",
        provider_id=request.provider_id,
        status=GenerationStatus.SUCCEEDED.value,
        output_references=("https://cdn.test/social.png",),
    )
    return GenerationJob(
        job_id="generation_job_social",
        request=request,
        status=GenerationStatus.SUCCEEDED.value,
        result=result,
    )


class FakeGenerationEngine:
    def get_job(self, job_id):
        if job_id != "generation_job_social":
            raise KeyError(job_id)
        return successful_job()


class FakeIngestionService:
    def ingest_job(self, job):
        return GenerationResultIngestionResult(
            success=True,
            generation_job_id=job.job_id,
            imported_asset_ids=(901,),
        )


class FakeXProvider:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    def account_names(self):
        return ("AvaBlackthorne", "AvaBlackthorneX")

    def publish(self, *, image_reference, caption, account_name=None):
        self.calls.append(
            {
                "image_reference": image_reference,
                "caption": caption,
                "account_name": account_name,
            }
        )
        if self.fail:
            raise RuntimeError("X provider failed")
        return XPublishResult(
            success=True,
            account_name=account_name or "AvaBlackthorne",
            provider_post_id="tweet_123",
            provider_media_id="media_123",
            provider_output_url="https://x.com/AvaBlackthorne/status/tweet_123",
            message="Posted to X.",
        )


class FakeTweepy:
    class OAuth1UserHandler:
        def __init__(self, *args):
            self.args = args

    class API:
        def __init__(self, auth):
            self.auth = auth

        def media_upload(self, image_path):
            return SimpleNamespace(media_id="media_456")

    class Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def create_tweet(self, *, text, media_ids):
            return SimpleNamespace(data={"id": "tweet_456", "text": text, "media_ids": media_ids})


class SocialPublishingTests(unittest.TestCase):
    def make_services(self, *, x_provider=None):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        generation_library = GenerationLibraryService(storage_dir=Path(temp_dir.name) / "library")
        generation_library._write_records([generated_record()])
        social_publishing = SocialPublishingService(
            storage_dir=Path(temp_dir.name) / "social",
            x_provider=x_provider,
        )
        return social_publishing, generation_library

    def test_queue_creation_preserves_generation_metadata(self):
        social_publishing, generation_library = self.make_services()

        item = social_publishing.create_queue_item(
            generated_image_id="generated_image_social_1",
            generation_library=generation_library,
            platform=SocialPlatform.X.value,
            creator_notes="Launch teaser",
        )

        self.assertEqual(item.generated_image_id, "generated_image_social_1")
        self.assertEqual(item.platform, SocialPlatform.X.value)
        self.assertEqual(item.status, SocialPublishStatus.QUEUED.value)
        self.assertEqual(item.creator_notes, "Launch teaser")
        self.assertEqual(item.reference_asset_id, 55)
        self.assertEqual(item.creative_mode, "social_safe")
        self.assertEqual(item.generation_metadata["generation_job_id"], "generation_job_social")
        self.assertEqual(item.generation_metadata["provider_id"], "seedream_4_5")

    def test_queue_removal_archive_and_move_back(self):
        social_publishing, generation_library = self.make_services()
        item = social_publishing.create_queue_item(
            generated_image_id="generated_image_social_1",
            generation_library=generation_library,
            platform=SocialPlatform.INSTAGRAM.value,
        )

        archived = social_publishing.archive_queue_item(item.queue_item_id)
        moved = social_publishing.move_back_to_generation_library(item.queue_item_id)

        self.assertEqual(archived.status, SocialPublishStatus.ARCHIVED.value)
        self.assertEqual(moved.generated_image_id, "generated_image_social_1")
        self.assertEqual(social_publishing.list_queue_items(), ())
        self.assertTrue(any(entry.status == "moved_back" for entry in social_publishing.list_history()))

    def test_send_to_creator_os_uses_generation_library_ingestion_boundary(self):
        social_publishing, generation_library = self.make_services()
        item = social_publishing.create_queue_item(
            generated_image_id="generated_image_social_1",
            generation_library=generation_library,
            platform=SocialPlatform.THREADS.value,
        )

        result = social_publishing.send_to_creator_os(
            item.queue_item_id,
            generation_library=generation_library,
            generation_engine=FakeGenerationEngine(),
            ingestion_service=FakeIngestionService(),
        )
        record = generation_library.get("generated_image_social_1")

        self.assertTrue(result.success)
        self.assertEqual(result.imported_asset_ids, (901,))
        self.assertEqual(record.imported_asset_id, 901)
        self.assertTrue(any(entry.status == "sent_to_creator_os" for entry in social_publishing.list_history()))

    def test_platform_selection_and_session_models(self):
        social_publishing, generation_library = self.make_services()
        self.assertIn(SocialPlatform.BLUESKY.value, social_publishing.platform_options())
        self.assertIn(SocialPlatform.TIKTOK.value, social_publishing.platform_options())

        item = social_publishing.create_queue_item(
            generated_image_id="generated_image_social_1",
            generation_library=generation_library,
            platform="not-real",
        )
        session = social_publishing.create_session(
            creator_profile_id=7,
            queue_item_ids=(item.queue_item_id,),
            platform=SocialPlatform.FACEBOOK.value,
        )
        publish_item = social_publishing.create_publish_item(
            queue_item_id=item.queue_item_id,
            platform=SocialPlatform.FACEBOOK.value,
        )

        self.assertEqual(item.platform, SocialPlatform.FUTURE_PROVIDER.value)
        self.assertEqual(session.platform, SocialPlatform.FACEBOOK.value)
        self.assertFalse(publish_item.metadata["posting_implemented"])

    def test_x_account_selection_and_publish_success(self):
        fake_x = FakeXProvider()
        social_publishing, generation_library = self.make_services(x_provider=fake_x)
        item = social_publishing.create_queue_item(
            generated_image_id="generated_image_social_1",
            generation_library=generation_library,
            platform=SocialPlatform.X.value,
        )

        posted = social_publishing.publish_now(
            item.queue_item_id,
            caption_text="A little moment worth saving.",
            account_name="AvaBlackthorneX",
            caption_id="caption_1",
        )
        publish_item = social_publishing.list_publish_items()[0]
        history = social_publishing.list_history()[0]

        self.assertEqual(social_publishing.x_account_options(), ("AvaBlackthorne", "AvaBlackthorneX"))
        self.assertEqual(posted.status, SocialPublishStatus.POSTED.value)
        self.assertEqual(fake_x.calls[0]["account_name"], "AvaBlackthorneX")
        self.assertEqual(fake_x.calls[0]["image_reference"], "https://cdn.test/social.png")
        self.assertEqual(publish_item.status, SocialPublishStatus.POSTED.value)
        self.assertEqual(publish_item.metadata["provider_post_id"], "tweet_123")
        self.assertEqual(history.status, SocialPublishStatus.POSTED.value)
        self.assertEqual(history.metadata["caption_id"], "caption_1")

    def test_x_provider_credential_lookup_and_dispatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "source.png"
            Image.new("RGB", (32, 32), "white").save(image_path)
            env = {
                "X_CONSUMER_KEY": "consumer",
                "X_CONSUMER_SECRET": "secret",
                "X_ACCESS_TOKEN": "token",
                "X_ACCESS_TOKEN_SECRET": "token-secret",
            }
            old = {key: os.environ.get(key) for key in env}
            os.environ.update(env)
            try:
                provider = XPublishingProvider(tweepy_module=FakeTweepy)
                result = provider.publish(
                    image_reference=str(image_path),
                    caption="Testing X publish",
                    account_name="AvaBlackthorne",
                )
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertTrue(result.success)
        self.assertEqual(result.provider_post_id, "tweet_456")
        self.assertEqual(result.provider_media_id, "media_456")

    def test_x_publish_failure_and_retry(self):
        social_publishing, generation_library = self.make_services(x_provider=FakeXProvider(fail=True))
        item = social_publishing.create_queue_item(
            generated_image_id="generated_image_social_1",
            generation_library=generation_library,
            platform=SocialPlatform.X.value,
        )

        failed = social_publishing.publish_now(
            item.queue_item_id,
            caption_text="A little moment worth saving.",
            account_name="AvaBlackthorne",
        )
        retried = social_publishing.retry_queue_item(item.queue_item_id)

        self.assertEqual(failed.status, SocialPublishStatus.FAILED.value)
        self.assertEqual(retried.status, SocialPublishStatus.QUEUED.value)
        self.assertTrue(any(entry.status == SocialPublishStatus.FAILED.value for entry in social_publishing.list_history()))
        self.assertTrue(any(entry.status == SocialPublishStatus.QUEUED.value for entry in social_publishing.list_history()))

    def test_scheduled_state_is_tracked(self):
        social_publishing, generation_library = self.make_services(x_provider=FakeXProvider())
        item = social_publishing.create_queue_item(
            generated_image_id="generated_image_social_1",
            generation_library=generation_library,
            platform=SocialPlatform.X.value,
        )

        scheduled = social_publishing.schedule_queue_item(
            item.queue_item_id,
            scheduled_for="2026-07-08T10:00:00",
        )

        self.assertEqual(scheduled.status, SocialPublishStatus.SCHEDULED.value)
        self.assertEqual(scheduled.scheduled_for, "2026-07-08T10:00:00")
        self.assertEqual(social_publishing.list_history()[0].status, SocialPublishStatus.SCHEDULED.value)

    def test_social_publishing_navigation_and_ui_contract(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(encoding="utf-8")
        navigation = Path("app/dashboard/navigation.py").read_text(encoding="utf-8")
        main = Path("app/dashboard/main.py").read_text(encoding="utf-8")

        self.assertIn("Social Publishing", source)
        self.assertIn("Social Queue", source)
        self.assertIn("Queued Images", source)
        self.assertIn("Platform", source)
        self.assertIn("Scheduled", source)
        self.assertIn("Posted", source)
        self.assertIn("Failed", source)
        self.assertIn("Archived", source)
        self.assertIn("Creator Notes", source)
        self.assertIn("Generation Metadata", source)
        self.assertIn("Reference Image", source)
        self.assertIn("Creative Mode", source)
        self.assertIn("Send to Social Publishing", source)
        self.assertIn("Move Back to Generation Library", source)
        self.assertIn("Send to Creator OS", source)
        self.assertIn("X Account", source)
        self.assertIn("Generate Caption", source)
        self.assertIn("Publish Now", source)
        self.assertIn("Retry", source)
        self.assertIn("Schedule", source)
        self.assertIn("Select Caption", source)
        self.assertIn("Published to X", source)
        self.assertIn('"Social Publishing"', navigation)
        self.assertIn('"Social Publishing"', main)
        self.assertNotIn('"Staging"', navigation)
        self.assertNotIn('"Staging"', main)
        self.assertNotIn("publish_to_x", source)
        self.assertNotIn("publish_to_telegram", source)
        self.assertNotIn("caption_image_with_joycaption", source)


if __name__ == "__main__":
    unittest.main()
