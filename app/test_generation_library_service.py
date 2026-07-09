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

from app.models.generation_engine import (
    GenerationJob,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)
from app.models.generation_ingestion import GenerationResultIngestionResult
from app.models.generation_library import GenerationLibraryFilter
from app.services.content_archive_service import ContentArchiveService
from app.services.generation_library_service import GenerationLibraryService


def successful_job(
    *,
    job_id="generation_job_1",
    creator_profile_id=7,
    provider_id="seedream_4_5",
    output_references=("https://cdn.test/generated-1.png", "https://cdn.test/generated-2.png"),
    creative_mode="social_safe",
    photoshoot_session_id="photoshoot_1",
):
    request = GenerationRequest(
        request_id=f"{job_id}_request",
        creator_profile_id=creator_profile_id,
        prompt_plan_id=f"{job_id}_plan",
        prompt_text=f"{creative_mode} portrait with window light",
        reference_asset_id=55,
        reference_asset_path="C:/Creator-OS/data/cms/vault/originals/images/55.png",
        provider_id=provider_id,
        generation_type="image_to_image",
        media_type="image",
        image_count=len(output_references),
        metadata={
            "creative_mode": creative_mode,
            "creative_tags": ("window light", "portrait"),
            "prompt_metadata": {"provider_neutral": True},
            "photoshoot_session_id": photoshoot_session_id,
            "photoshoot_request_id": "photoshoot_item_1",
        },
    )
    result = GenerationResult(
        result_id=f"{job_id}_result",
        request_id=request.request_id,
        job_id=job_id,
        provider_id=provider_id,
        status=GenerationStatus.SUCCEEDED.value,
        generation_metadata={"provider_response_id": "provider_123"},
        execution_metadata={"duration_seconds": 12.5},
        image_metadata={"width": 1024, "height": 1024},
        output_references=tuple(output_references),
    )
    return GenerationJob(
        job_id=job_id,
        request=request,
        status=GenerationStatus.SUCCEEDED.value,
        result=result,
    )


class FakeGenerationEngine:
    def __init__(self, job):
        self.job = job
        self.queued = []

    def get_job(self, job_id):
        if job_id != self.job.job_id:
            raise KeyError(job_id)
        return self.job

    def queue_prompt_plan(self, **kwargs):
        self.queued.append(kwargs)
        return SimpleNamespace(job_id=f"queued_regeneration_{len(self.queued)}")


class FakeIngestionService:
    def __init__(self, *, success=True):
        self.success = success
        self.jobs = []

    def ingest_job(self, job):
        self.jobs.append(job)
        if not self.success:
            return GenerationResultIngestionResult(
                success=False,
                generation_job_id=job.job_id,
                errors=("download failed",),
            )
        return GenerationResultIngestionResult(
            success=True,
            generation_job_id=job.job_id,
            imported_asset_ids=(501,),
        )


class FakeArchiveResponse:
    content = b"fake-image"

    def raise_for_status(self):
        return None


class FakeArchiveHttp:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeArchiveResponse()


class GenerationLibraryServiceTests(unittest.TestCase):
    def make_service(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        archive = ContentArchiveService(
            storage_dir=Path(temp_dir.name) / "archive_data",
            content_root=Path(temp_dir.name) / "Content",
            http_client=FakeArchiveHttp(),
        )
        return GenerationLibraryService(
            storage_dir=Path(temp_dir.name) / "library",
            archive_service=archive,
        )

    def test_library_browsing_indexes_successful_generated_images(self):
        service = self.make_service()

        created = service.sync_job(successful_job())
        duplicate = service.sync_job(successful_job())
        result = service.browse(GenerationLibraryFilter(status="active"))

        self.assertEqual(len(created), 2)
        self.assertEqual(duplicate, ())
        self.assertEqual(result.total, 2)
        self.assertEqual(result.records[0].provider_id, "seedream_4_5")
        self.assertEqual(result.records[0].reference_asset_id, 55)
        self.assertEqual(result.records[0].photoshoot_session_id, "photoshoot_1")
        self.assertTrue(Path(result.records[0].output_reference).exists())
        self.assertIn("Generation", result.records[0].output_reference)
        self.assertIn("Social", result.records[0].output_reference)
        original_references = {
            record.generation_metadata["original_output_reference"]
            for record in result.records
        }
        self.assertIn("https://cdn.test/generated-1.png", original_references)

    def test_search_filtering_and_sorting(self):
        service = self.make_service()
        service.sync_job(successful_job(job_id="social_job", provider_id="seedream_4_5"))
        service.sync_job(
            successful_job(
                job_id="premium_job",
                provider_id="flux",
                creative_mode="premium_editorial",
                photoshoot_session_id="photoshoot_2",
            )
        )

        searched = service.browse(GenerationLibraryFilter(search="premium_editorial"))
        provider = service.browse(GenerationLibraryFilter(provider_id="flux"))
        photoshoot = service.browse(GenerationLibraryFilter(photoshoot_session_id="photoshoot_2"))
        sorted_result = service.browse(GenerationLibraryFilter(sort="provider"))

        self.assertEqual(searched.total, 2)
        self.assertTrue(all(record.creative_mode == "premium_editorial" for record in searched.records))
        self.assertTrue(all("Premium" in record.output_reference for record in searched.records))
        self.assertEqual(provider.total, 2)
        self.assertEqual(photoshoot.total, 2)
        self.assertEqual(sorted_result.records[0].provider_id, "flux")

    def test_bulk_selection_move_to_junk_and_archive_removes_from_active_library(self):
        service = self.make_service()
        service.sync_job(successful_job())

        selected = service.bulk_select(GenerationLibraryFilter(status="active"))
        junked = service.move_to_junk(selected.image_ids[:1])
        archived = service.archive(selected.image_ids[1:])

        self.assertTrue(junked.success)
        self.assertTrue(archived.success)
        self.assertEqual(service.browse().total, 0)
        self.assertEqual(len(service.archive_service.list_records(archive_type="junk")), 1)
        self.assertEqual(len(service.archive_service.list_records(archive_type="archived")), 1)
        self.assertEqual(service.browse(GenerationLibraryFilter(selected_only=True)).total, 0)

    def test_restore_and_delete_uses_archive_junk(self):
        service = self.make_service()
        created = service.sync_job(successful_job())
        service.move_to_junk((created[0].image_id,))

        restored = service.restore((created[0].image_id,))
        deleted = service.delete((created[1].image_id,))

        self.assertTrue(restored.success)
        self.assertTrue(deleted.success)
        self.assertEqual(service.get(created[0].image_id).status, "active")
        self.assertEqual(service.get(created[0].image_id).review_state, "restored")
        with self.assertRaises(KeyError):
            service.get(created[1].image_id)
        self.assertEqual(len(service.archive_service.list_records(archive_type="junk")), 1)

    def test_add_to_creator_os_is_explicit_and_uses_ingestion_boundary(self):
        job = successful_job()
        service = self.make_service()
        record = service.sync_job(job)[0]
        engine = FakeGenerationEngine(job)
        ingestion = FakeIngestionService()

        before = service.get(record.image_id)
        action = service.add_to_creator_os(
            (record.image_id,),
            generation_engine=engine,
            ingestion_service=ingestion,
        )

        self.assertIsNone(before.imported_asset_id)
        self.assertTrue(action.success)
        self.assertEqual(action.imported_asset_ids, (501,))
        self.assertEqual(len(ingestion.jobs), 1)
        self.assertEqual(ingestion.jobs[0].result.output_references, (record.output_reference,))
        with self.assertRaises(KeyError):
            service.get(record.image_id)
        archive_record = service.archive_service.list_records(archive_type="imported")[0]
        self.assertEqual(archive_record.imported_asset_id, 501)
        self.assertIn("Archive", archive_record.destination)
        self.assertIn("Imported", archive_record.destination)

    def test_failed_add_to_creator_os_preserves_library_record(self):
        job = successful_job()
        service = self.make_service()
        record = service.sync_job(job)[0]

        action = service.add_to_creator_os(
            (record.image_id,),
            generation_engine=FakeGenerationEngine(job),
            ingestion_service=FakeIngestionService(success=False),
        )
        after = service.get(record.image_id)

        self.assertFalse(action.success)
        self.assertIn("download failed", action.errors[0])
        self.assertEqual(after.status, "active")
        self.assertIsNone(after.imported_asset_id)

    def test_regenerate_queues_provider_neutral_generation_request(self):
        job = successful_job()
        service = self.make_service()
        record = service.sync_job(job)[0]
        engine = FakeGenerationEngine(job)

        action = service.regenerate((record.image_id,), generation_engine=engine)
        updated = service.get(record.image_id)

        self.assertTrue(action.success)
        self.assertEqual(action.image_ids, ("queued_regeneration_1",))
        self.assertEqual(len(engine.queued), 1)
        self.assertEqual(engine.queued[0]["provider_id"], "seedream_4_5")
        self.assertEqual(engine.queued[0]["prompt_plan"].reference_asset_id, 55)
        self.assertEqual(updated.review_state, "regenerate_requested")

    def test_publish_moves_to_posted_x_and_preserves_metadata(self):
        service = self.make_service()
        record = service.sync_job(successful_job())[0]

        action = service.mark_published(
            record.image_id,
            platform="x",
            caption="A little moment worth saving.",
            metadata={"account_name": "AvaBlackthorne"},
        )

        self.assertTrue(action.success)
        with self.assertRaises(KeyError):
            service.get(record.image_id)
        archive_record = service.archive_service.list_records(archive_type="published_x")[0]
        self.assertEqual(archive_record.platform, "X")
        self.assertEqual(archive_record.caption, "A little moment worth saving.")
        self.assertIn("Posted", archive_record.current_file_path)
        self.assertIn("X", archive_record.current_file_path)
        self.assertIn("Main", archive_record.current_file_path)
        self.assertEqual(archive_record.provider_id, "seedream_4_5")
        self.assertEqual(archive_record.prompt_text, record.prompt_text)

    def test_configurable_content_root_moves_local_file(self):
        service = self.make_service()
        local_source = service.archive_service.content_root.parent / "generated-local.jpg"
        local_source.write_bytes(b"local-image")
        record = service.sync_job(
            successful_job(
                job_id="local_job",
                output_references=(str(local_source),),
            )
        )[0]

        action = service.mark_published(record.image_id, platform="x", caption="Local publish")

        archive_record = service.archive_service.list_records(archive_type="published_x")[0]
        self.assertTrue(action.success)
        self.assertFalse(local_source.exists())
        self.assertTrue(Path(archive_record.current_file_path).exists())
        self.assertFalse(Path(record.output_reference).exists())
        self.assertTrue(str(archive_record.current_file_path).startswith(str(service.archive_service.content_root)))

    def test_telegram_publish_moves_to_posted_telegram(self):
        service = self.make_service()
        record = service.sync_job(successful_job())[0]

        action = service.mark_published(record.image_id, platform="telegram", caption="Telegram caption")

        self.assertTrue(action.success)
        archive_record = service.archive_service.list_records(archive_type="published_telegram")[0]
        self.assertEqual(archive_record.platform, "Telegram")
        self.assertIn("Telegram", archive_record.current_file_path)

    def test_edit_original_moves_to_archive_edited(self):
        service = self.make_service()
        record = service.sync_job(successful_job())[0]

        action = service.mark_edited((record.image_id,), metadata={"edit_request_id": "edit_1"})

        self.assertTrue(action.success)
        with self.assertRaises(KeyError):
            service.get(record.image_id)
        archive_record = service.archive_service.list_records(archive_type="edited_original")[0]
        self.assertIn("Archive", archive_record.current_file_path)
        self.assertIn("Edited", archive_record.current_file_path)
        self.assertEqual(archive_record.metadata["edit_request_id"], "edit_1")

    def test_content_studio_generation_library_ui_contract(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(encoding="utf-8")
        navigation = Path("app/dashboard/navigation.py").read_text(encoding="utf-8")
        main = Path("app/dashboard/main.py").read_text(encoding="utf-8")

        self.assertIn("Generation Library", source)
        self.assertIn("Archive", source)
        self.assertIn("Permanent Content Studio history", source)
        self.assertIn("_render_archive_page", source)
        self.assertIn("Published - X", source)
        self.assertIn("Published - Telegram", source)
        self.assertIn("Edited", source)
        self.assertIn("Imported", source)
        self.assertIn("Junk", source)
        self.assertIn("Permanent Delete", source)
        self.assertIn("Thumbnail Grid", source)
        self.assertIn("Preview", source)
        self.assertIn("Page Size", source)
        self.assertIn("Page {int(page_number)}", source)
        self.assertIn("Multi-select", source)
        self.assertIn("Add to Creator OS", source)
        self.assertIn("Both", source)
        self.assertIn("Move to Junk", source)
        self.assertIn("Restore", source)
        self.assertIn("Delete", source)
        self.assertIn("Archive", source)
        self.assertIn("Multi Edit", source)
        self.assertIn("Regenerate", source)
        self.assertIn("_render_generation_publish_modal", source)
        self.assertIn("_open_generation_publish_modal", source)
        self.assertIn("Where would you like to publish this image?", source)
        self.assertIn("Publish to X", source)
        self.assertIn("Publish to Telegram", source)
        self.assertIn("Cancel", source)
        self.assertIn("_render_telegram_publish_dialog", source)
        self.assertIn("Publish to Telegram", source)
        self.assertIn("generate_telegram_vision_themes", source)
        self.assertIn("Caption Editor", source)
        self.assertIn("Select a generated caption above or write your own.", source)
        self.assertIn("_render_x_engagement_publish_dialog", source)
        self.assertIn("X Publish", source)
        self.assertIn("Generate Captions", source)
        self.assertIn("Grok Vision analyzes the actual image first", source)
        self.assertIn("Generate Different Ideas", source)
        self.assertIn("Caption Editor", source)
        self.assertIn("Publish to AvaBlackthorne", source)
        self.assertIn('account_name="AvaBlackthorne"', source)
        self.assertIn("generate_x_engagement_themes", source)
        self.assertIn("select_caption", source)
        self.assertIn("caption_text=selected_caption", source)
        self.assertIn("social_publishing.create_queue_item", source)
        self.assertIn("social_publishing.publish_now", source)
        self.assertIn("generation_library_publish_context", source)
        self.assertIn("generation_library_publish_destination", source)
        self.assertIn("generation_library_x_selected_caption", source)
        self.assertIn("generated_image_id", source)
        self.assertIn("image_reference", source)
        self.assertIn("prompt_metadata", source)
        self.assertIn("generation_metadata", source)
        self.assertIn('a3.button("Publish"', source)
        self.assertNotIn("Generated Image: {context", source)
        self.assertNotIn("Provider: {context", source)
        self.assertNotIn("Workflow: {context", source)
        self.assertNotIn("Creative Mode: {context", source)
        self.assertNotIn("Selected Image Context", source)
        self.assertNotIn("generation_library_publish_x_", source)
        self.assertNotIn("Quick published from Generation Library.", source)
        self.assertNotIn("caption_studio.generate_for_social_queue(\n                    queue_item_id=item.queue_item_id", source)
        self.assertIn("Published to X", source)
        self.assertIn("Open Prompt", source)
        self.assertIn("Open Reference", source)
        self.assertIn("Metadata", source)
        self.assertIn("Provider Metadata", source)
        self.assertIn("Generation Library", navigation)
        self.assertIn("Archive", navigation)
        self.assertIn("Generation Library", main)


if __name__ == "__main__":
    unittest.main()
