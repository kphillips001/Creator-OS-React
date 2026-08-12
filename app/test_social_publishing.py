import sys
import tempfile
import types
import unittest
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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

from app.providers.social import telegram_provider as telegram_provider_module
from app.providers.social.telegram_provider import TelegramPublishingProvider
from app.providers.social.x_provider import XPublishError, XPublishResult, XPublishingProvider
from app.services.content_archive_service import ContentArchiveService
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


class FakeTelegramProvider:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    def publish(
        self,
        *,
        image_reference,
        caption,
        post_to="main",
        cta_enabled=False,
        cta_label="",
        cta_url="",
    ):
        self.calls.append(
            {
                "image_reference": image_reference,
                "caption": caption,
                "post_to": post_to,
                "cta_enabled": cta_enabled,
                "cta_label": cta_label,
                "cta_url": cta_url,
            }
        )
        if self.fail:
            raise RuntimeError("Telegram provider failed")
        return SimpleNamespace(
            success=True,
            post_to=post_to,
            provider_post_id="telegram_message_123",
            message="Posted to Telegram.",
            metadata={"status_code": 200},
        )


class FakeArchiveResponse:
    content = b"fake-image"

    def raise_for_status(self):
        return None


class FakeArchiveHttp:
    def get(self, url, **kwargs):
        return FakeArchiveResponse()


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


class FakeTelegramResponse:
    status_code = 200
    text = '{"ok": true}'

    def json(self):
        return {"ok": True, "result": {"message_id": 789}}


class FakeTelegramHttp:
    def __init__(self):
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeTelegramResponse()

    def get(self, url, **kwargs):
        return FakeArchiveResponse()


class SocialPublishingTests(unittest.TestCase):
    def make_services(self, *, x_provider=None, telegram_provider=None):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        archive = ContentArchiveService(
            storage_dir=Path(temp_dir.name) / "archive_data",
            content_root=Path(temp_dir.name) / "Content",
            http_client=FakeArchiveHttp(),
        )
        generation_library = GenerationLibraryService(
            storage_dir=Path(temp_dir.name) / "library",
            archive_service=archive,
        )
        generation_library._write_records([generated_record()])
        social_publishing = SocialPublishingService(
            storage_dir=Path(temp_dir.name) / "social",
            x_provider=x_provider,
            telegram_provider=telegram_provider,
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

        self.assertTrue(result.success)
        self.assertEqual(result.imported_asset_ids, (901,))
        with self.assertRaises(KeyError):
            generation_library.get("generated_image_social_1")
        imported = generation_library.archive_service.list_records(archive_type="imported")[0]
        self.assertEqual(imported.imported_asset_id, 901)
        self.assertTrue(any(entry.status == "sent_to_creator_os" for entry in social_publishing.list_history()))

    def test_platform_selection_and_session_models(self):
        social_publishing, generation_library = self.make_services()
        self.assertIn(SocialPlatform.BLUESKY.value, social_publishing.platform_options())
        self.assertIn(SocialPlatform.TIKTOK.value, social_publishing.platform_options())
        self.assertIn(SocialPlatform.TELEGRAM.value, social_publishing.platform_options())

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

    def test_x_provider_reports_runtime_python_when_tweepy_is_missing(self):
        provider = XPublishingProvider()

        missing = ModuleNotFoundError("No module named 'tweepy'", name="tweepy")
        with patch("app.providers.social.x_provider.import_module", side_effect=missing):
            with self.assertRaises(XPublishError) as caught:
                provider._load_tweepy()

        message = str(caught.exception)
        self.assertIn("X publishing dependency missing.", message)
        self.assertIn("Runtime interpreter:", message)
        self.assertIn("python -m pip install tweepy==4.15.0", message)
        self.assertIn(" -m pip install tweepy==4.15.0", message)

    def test_x_provider_runtime_diagnostic_reports_missing_tweepy(self):
        missing = ModuleNotFoundError("No module named 'tweepy'", name="tweepy")

        with patch("app.providers.social.x_provider.import_module", side_effect=missing):
            diagnostic = XPublishingProvider.runtime_dependency_diagnostic()

        self.assertFalse(diagnostic.tweepy_installed)
        self.assertIn("Not Installed", diagnostic.format())
        self.assertTrue(diagnostic.runtime_interpreter)

    def test_x_provider_runtime_diagnostic_reports_installed_tweepy(self):
        fake_tweepy = SimpleNamespace(__version__="4.15.0", __file__="runtime/site-packages/tweepy/__init__.py")

        with patch("app.providers.social.x_provider.import_module", return_value=fake_tweepy):
            diagnostic = XPublishingProvider.runtime_dependency_diagnostic()

        self.assertTrue(diagnostic.tweepy_installed)
        self.assertEqual(diagnostic.tweepy_version, "4.15.0")
        self.assertIn("Installed", diagnostic.format())

    def test_telegram_provider_prepares_image_and_sends_photo_with_cta(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "transparent.png"
            Image.new("RGBA", (5000, 3000), (255, 0, 0, 128)).save(image_path)
            http = FakeTelegramHttp()
            provider = TelegramPublishingProvider(http_client=http)
            values = {
                "TELEGRAM_BOT_TOKEN_AVA": "bot-token",
                "TELEGRAM_CHAT_ID_AVA": "main-chat",
                "TELEGRAM_VAULT_CHANNEL_ID": "vault-chat",
            }
            old = {key: getattr(telegram_provider_module.settings, key) for key in values}
            try:
                for key, value in values.items():
                    setattr(telegram_provider_module.settings, key, value)
                result = provider.publish(
                    image_reference=str(image_path),
                    caption="Manual Telegram caption",
                    post_to="vault",
                    cta_enabled=True,
                    cta_label="Open",
                    cta_url="https://example.test",
                )
            finally:
                for key, value in old.items():
                    setattr(telegram_provider_module.settings, key, value)

        self.assertTrue(result.success)
        self.assertEqual(result.post_to, "vault")
        url, kwargs = http.posts[0]
        self.assertIn("/sendPhoto", url)
        self.assertEqual(kwargs["data"]["chat_id"], "vault-chat")
        self.assertEqual(kwargs["data"]["caption"], "Manual Telegram caption")
        self.assertIn("reply_markup", kwargs["data"])
        self.assertIn("photo", kwargs["files"])

    def test_telegram_provider_reports_friendly_missing_configuration(self):
        provider = TelegramPublishingProvider(http_client=FakeTelegramHttp())
        old_token = telegram_provider_module.settings.TELEGRAM_BOT_TOKEN_AVA
        try:
            telegram_provider_module.settings.TELEGRAM_BOT_TOKEN_AVA = ""
            with self.assertRaises(Exception) as caught:
                provider.publish(caption="Manual Telegram caption")
        finally:
            telegram_provider_module.settings.TELEGRAM_BOT_TOKEN_AVA = old_token

        self.assertIn("Telegram bot token is not configured.", str(caught.exception))

    def test_telegram_cta_validation(self):
        provider = TelegramPublishingProvider(http_client=FakeTelegramHttp())

        with self.assertRaises(Exception):
            provider.build_inline_keyboard(
                cta_enabled=True,
                cta_label="Open",
                cta_url="not-a-url",
            )

    def test_telegram_publish_success_history_and_retry(self):
        fake_telegram = FakeTelegramProvider()
        social_publishing, generation_library = self.make_services(telegram_provider=fake_telegram)
        item = social_publishing.create_queue_item(
            generated_image_id="generated_image_social_1",
            generation_library=generation_library,
            platform=SocialPlatform.TELEGRAM.value,
        )

        posted = social_publishing.publish_now(
            item.queue_item_id,
            caption_text="Manual Telegram caption",
            telegram_post_to="vault",
            telegram_cta_enabled=True,
            telegram_cta_label="Open",
            telegram_cta_url="https://example.test",
            audit_metadata={"offering_id": "offering-1", "asset_id": 42, "teaser_id": "teaser-1"},
        )
        archive = generation_library.mark_published(
            item.generated_image_id,
            platform=SocialPlatform.TELEGRAM.value,
            caption="Manual Telegram caption",
            metadata={"post_to": "vault", "social_queue_item_id": item.queue_item_id},
        )
        failed_service, failed_library = self.make_services(telegram_provider=FakeTelegramProvider(fail=True))
        failed_item = failed_service.create_queue_item(
            generated_image_id="generated_image_social_1",
            generation_library=failed_library,
            platform=SocialPlatform.TELEGRAM.value,
        )
        failed = failed_service.publish_now(failed_item.queue_item_id, caption_text="Manual Telegram caption")
        retried = failed_service.retry_queue_item(failed_item.queue_item_id)

        self.assertEqual(posted.status, SocialPublishStatus.POSTED.value)
        self.assertEqual(fake_telegram.calls[0]["post_to"], "vault")
        self.assertEqual(social_publishing.list_publish_items()[0].metadata["telegram_post_to"], "vault")
        self.assertEqual(social_publishing.list_publish_items()[0].metadata["offering_id"], "offering-1")
        self.assertEqual(social_publishing.list_history()[0].metadata["teaser_id"], "teaser-1")
        self.assertEqual(social_publishing.list_history()[0].status, SocialPublishStatus.POSTED.value)
        self.assertTrue(archive.success)
        archive_record = generation_library.archive_service.list_records(archive_type="published_telegram")[0]
        self.assertIn("Telegram", archive_record.current_file_path)
        self.assertIn("Vault", archive_record.current_file_path)
        self.assertEqual(failed.status, SocialPublishStatus.FAILED.value)
        self.assertEqual(retried.status, SocialPublishStatus.QUEUED.value)

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

    def test_successful_x_publish_schedules_exact_x_auto_callback(self):
        social_publishing, generation_library = self.make_services(x_provider=FakeXProvider())
        item = social_publishing.create_queue_item(
            generated_image_id="generated_image_social_1",
            generation_library=generation_library,
            platform=SocialPlatform.X.value,
        )

        with patch.object(
            SocialPublishingService, "_schedule_x_auto_callback"
        ) as callback:
            posted = social_publishing.publish_now(
                item.queue_item_id,
                caption_text="A little moment worth saving.",
                account_name="AvaBlackthorne",
            )

        self.assertEqual(posted.status, SocialPublishStatus.POSTED.value)
        payload = callback.call_args.args[0]
        self.assertEqual(
            payload,
            {
                "platform": "x",
                "account_name": "AvaBlackthorne",
                "tweet_id": "tweet_123",
                "published_at": payload["published_at"],
            },
        )
        self.assertTrue(str(payload["published_at"]).endswith("+00:00"))

    def test_callback_start_failure_does_not_change_successful_publish(self):
        social_publishing, generation_library = self.make_services(x_provider=FakeXProvider())
        item = social_publishing.create_queue_item(
            generated_image_id="generated_image_social_1",
            generation_library=generation_library,
            platform=SocialPlatform.X.value,
        )

        with patch.object(
            SocialPublishingService,
            "_schedule_x_auto_callback",
            side_effect=RuntimeError("thread unavailable"),
        ):
            posted = social_publishing.publish_now(
                item.queue_item_id,
                caption_text="A little moment worth saving.",
                account_name="AvaBlackthorne",
            )

        self.assertEqual(posted.status, SocialPublishStatus.POSTED.value)

    @patch("app.services.social_publishing_service.sleep")
    @patch("app.services.social_publishing_service.requests.post")
    def test_x_auto_callback_failure_retries_once_after_five_seconds(self, post, wait):
        accepted = Mock(status_code=200)
        accepted.raise_for_status.return_value = None
        post.side_effect = [RuntimeError("X_AUTO unavailable"), accepted]
        payload = {
            "platform": "x",
            "tweet_id": "2079000000000000000",
            "published_at": "2026-07-18T18:00:00+00:00",
        }

        SocialPublishingService._send_x_auto_callback(payload)

        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:8765/api/publish/x")
        self.assertEqual(post.call_args.kwargs["json"], payload)
        wait.assert_called_once_with(5)

    @patch("app.services.social_publishing_service.sleep")
    @patch("app.services.social_publishing_service.requests.post")
    def test_x_auto_callback_final_failure_does_not_change_publish_result(self, post, wait):
        post.side_effect = RuntimeError("X_AUTO unavailable")
        social_publishing, generation_library = self.make_services(x_provider=FakeXProvider())
        item = social_publishing.create_queue_item(
            generated_image_id="generated_image_social_1",
            generation_library=generation_library,
            platform=SocialPlatform.X.value,
        )

        with patch(
            "app.services.social_publishing_service.Thread.start",
            lambda thread: thread.run(),
        ):
            posted = social_publishing.publish_now(
                item.queue_item_id,
                caption_text="A little moment worth saving.",
                account_name="AvaBlackthorne",
            )

        self.assertEqual(posted.status, SocialPublishStatus.POSTED.value)
        self.assertEqual(post.call_count, 2)
        wait.assert_called_once_with(5)

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
        content_studio_navigation = navigation.split(
            'DashboardNavigationGroup(\n        "Content Creation"',
            1,
        )[1].split(
            'DashboardNavigationGroup(\n        "Experiences"',
            1,
        )[0]

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
        self.assertIn("Previous publish failure:", source)
        self.assertIn("Clear previous failure", source)
        self.assertIn("_x_dependency_blocking_message", source)
        self.assertIn("_is_stale_x_dependency_message", source)
        self.assertIn('st.session_state.pop("generation_library_x_publish_message", None)', source)
        self.assertIn("_sanitize_historical_publish_message", source)
        self.assertIn("[previous runtime interpreter]", source)
        self.assertNotIn("X publishing dependency missing.", source)
        self.assertNotIn("Fanvue" + "-Chatbot", source)
        self.assertIn('"Social Publishing"', navigation)
        self.assertNotIn("Social Publishing", content_studio_navigation)
        self.assertIn('"Social Publishing"', main)
        self.assertNotIn('"Staging"', navigation)
        self.assertNotIn('"Staging"', main)
        self.assertNotIn("publish_to_x", source)
        self.assertNotIn("publish_to_telegram", source)
        self.assertNotIn("caption_image_with_joycaption", source)


if __name__ == "__main__":
    unittest.main()
