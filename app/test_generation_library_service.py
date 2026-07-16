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
from app.services.photoshoot_queue_service import PhotoshootQueueService


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
        self.assertIn("Active", result.records[0].output_reference)
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
        self.assertTrue(all("Active" in record.output_reference for record in searched.records))
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

    def test_creator_approval_wrapper_is_idempotent_without_removing_record(self):
        job = successful_job()
        service = self.make_service()
        record = service.sync_job(job)[0]
        engine = FakeGenerationEngine(job)
        ingestion = FakeIngestionService()

        first = service.approve_creator_content(
            (record.image_id,),
            source_workflow="generation_library",
            generation_engine=engine,
            ingestion_service=ingestion,
        )
        second = service.approve_creator_content(
            (record.image_id,),
            source_workflow="generation_library",
            generation_engine=engine,
            ingestion_service=ingestion,
        )

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(first.imported_asset_ids, (501,))
        self.assertEqual(second.imported_asset_ids, (501,))
        self.assertEqual(len(ingestion.jobs), 1)
        self.assertEqual(service.get(record.image_id).imported_asset_id, 501)

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
        self.assertEqual(
            Path(archive_record.current_file_path).parent,
            service.archive_service.content_root / "Posted" / "X" / "Main",
        )
        self.assertTrue(Path(archive_record.current_file_path).exists())
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
        job = successful_job(output_references=("https://cdn.test/generated-telegram.png",))
        record = service.sync_job(job)[0]
        active_path = Path(record.output_reference)

        action = service.mark_published(record.image_id, platform="telegram", caption="Telegram caption")
        recreated = service.sync_job(job)
        result = service.browse(GenerationLibraryFilter(status="active"))

        self.assertTrue(action.success)
        archive_record = service.archive_service.list_records(archive_type="published_telegram")[0]
        self.assertEqual(archive_record.platform, "Telegram")
        self.assertIn("Telegram", archive_record.current_file_path)
        self.assertIn("Main", archive_record.current_file_path)
        self.assertEqual(
            Path(archive_record.current_file_path).parent,
            service.archive_service.content_root / "Posted" / "Telegram" / "Main",
        )
        self.assertTrue(Path(archive_record.current_file_path).exists())
        self.assertFalse(active_path.exists())
        self.assertEqual(recreated, ())
        self.assertEqual(result.total, 0)
        with self.assertRaises(KeyError):
            service.get(record.image_id)

    def test_telegram_vault_publish_moves_to_posted_telegram_vault(self):
        service = self.make_service()
        job = successful_job(
            job_id="telegram_vault_job",
            output_references=("https://cdn.test/generated-telegram-vault.png",),
        )
        record = service.sync_job(job)[0]

        action = service.mark_published(
            record.image_id,
            platform="telegram",
            caption="Telegram vault caption",
            metadata={"post_to": "vault"},
        )

        self.assertTrue(action.success)
        archive_record = service.archive_service.list_records(archive_type="published_telegram")[0]
        self.assertEqual(archive_record.platform, "Telegram")
        self.assertEqual(
            Path(archive_record.current_file_path).parent,
            service.archive_service.content_root / "Posted" / "Telegram" / "Vault",
        )
        self.assertTrue(Path(archive_record.current_file_path).exists())

    def test_generation_library_image_can_be_added_to_photoshoot_queue_once(self):
        service = self.make_service()
        queue_dir = tempfile.TemporaryDirectory()
        self.addCleanup(queue_dir.cleanup)
        photoshoot_queue = PhotoshootQueueService(storage_dir=queue_dir.name)
        record = service.sync_job(successful_job(output_references=("https://cdn.test/photoshoot-source.png",)))[0]

        request, created = photoshoot_queue.queue_generated_image(record)
        duplicate_request, duplicate_created = photoshoot_queue.queue_generated_image(record)
        result = service.browse(GenerationLibraryFilter(status="active"))

        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(request.request_id, duplicate_request.request_id)
        self.assertEqual(len(photoshoot_queue.list_sessions()), 1)
        self.assertEqual(len(photoshoot_queue.list_requests()), 1)
        self.assertEqual(request.status, "awaiting_review")
        self.assertEqual(request.metadata["generated_image_ids"], (record.image_id,))
        self.assertEqual(result.total, 1)
        self.assertEqual(result.records[0].image_id, record.image_id)

    def test_video_queue_moves_asset_to_pending_video(self):
        service = self.make_service()
        record = service.sync_job(successful_job(output_references=("https://cdn.test/video-source.png",)))[0]

        pending = service.send_to_pending_video(record.image_id)
        active = service.browse(GenerationLibraryFilter(status="active"))
        video_queue = service._read_json(service.video_queue_path, [])

        self.assertEqual(pending.status, "pending_video")
        self.assertEqual(pending.review_state, "pending_video")
        self.assertIn("Pending_Video", pending.output_reference)
        self.assertTrue(Path(pending.output_reference).exists())
        self.assertEqual(active.total, 0)
        self.assertEqual(len(video_queue), 1)
        self.assertEqual(video_queue[0]["image_id"], record.image_id)
        self.assertEqual(video_queue[0]["workflow"], "video")

    def test_missing_active_file_is_hidden_and_not_publishable(self):
        service = self.make_service()
        record = service.sync_job(successful_job(output_references=("https://cdn.test/missing-active.png",)))[0]
        Path(record.output_reference).unlink()

        active = service.browse(GenerationLibraryFilter(status="active"))
        publishable = service.resolve_publishable_image_reference(record.image_id)

        self.assertEqual(active.total, 0)
        self.assertIsNone(publishable)

    def test_pending_photoshoot_sync_does_not_recreate_active_record_and_return_restores_publishable_path(self):
        service = self.make_service()
        job = successful_job(output_references=("https://cdn.test/photoshoot-pending.png",))
        record = service.sync_job(job)[0]

        pending = service.send_to_pending_photoshoot(record.image_id)
        recreated = service.sync_job(job)
        active_while_pending = service.browse(GenerationLibraryFilter(status="active"))
        publishable_while_pending = service.resolve_publishable_image_reference(record.image_id)
        returned = service.return_photoshoot_seed_to_library(record.image_id)
        active_after_return = service.browse(GenerationLibraryFilter(status="active"))
        publishable_after_return = service.resolve_publishable_image_reference(record.image_id)

        self.assertEqual(pending.status, "pending_photoshoot")
        self.assertEqual(recreated, ())
        self.assertEqual(active_while_pending.total, 0)
        self.assertIsNone(publishable_while_pending)
        self.assertTrue(returned.success)
        self.assertEqual(active_after_return.total, 1)
        self.assertIsNotNone(publishable_after_return)
        self.assertTrue(Path(publishable_after_return).exists())

    def test_photoshoot_session_records_stay_hidden_after_completion(self):
        service = self.make_service()
        seed, shot = service.sync_job(
            successful_job(
                output_references=(
                    "https://cdn.test/photoshoot-seed.png",
                    "https://cdn.test/photoshoot-shot.png",
                )
            )
        )

        pending_seed = service.send_to_pending_photoshoot(seed.image_id)
        isolated = service.mark_photoshoot_session_records((shot.image_id,), session_id="photoshoot_1")
        active_before_finish = service.browse(GenerationLibraryFilter(status="active"))
        finish = service.finish_photoshoot_session(
            session_id="photoshoot_1",
            approved_image_ids=(pending_seed.image_id, shot.image_id),
        )
        active_after_finish = service.browse(GenerationLibraryFilter(status="active"))

        self.assertEqual(pending_seed.status, "pending_photoshoot")
        self.assertIn("Pending_Photoshoot", pending_seed.output_reference)
        self.assertTrue(isolated.success)
        self.assertEqual(active_before_finish.total, 0)
        self.assertTrue(finish.success)
        completed = {record.image_id: record for record in service.list_records() if record.image_id in {seed.image_id, shot.image_id}}

        self.assertEqual(set(finish.image_ids), {seed.image_id, shot.image_id})
        self.assertEqual(active_after_finish.total, 0)
        self.assertEqual({record.status for record in completed.values()}, {"photoshoot_completed"})
        self.assertTrue(all(record.photoshoot_session_id == "photoshoot_1" for record in completed.values()))

    def test_return_photoshoot_seed_keeps_active_image_once_and_discards_candidate(self):
        service = self.make_service()
        created = service.sync_job(
            successful_job(
                output_references=(
                    "https://cdn.test/photoshoot-seed.png",
                    "https://cdn.test/photoshoot-candidate.png",
                )
            )
        )
        seed, candidate = created

        returned = service.return_photoshoot_seed_to_library(seed.image_id)
        discarded = service.discard_temporary_records((candidate.image_id,))
        active = service.browse(GenerationLibraryFilter(status="active"))

        self.assertTrue(returned.success)
        self.assertTrue(discarded.success)
        self.assertEqual(discarded.image_ids, (candidate.image_id,))
        self.assertEqual(active.total, 1)
        self.assertEqual(active.records[0].image_id, seed.image_id)
        with self.assertRaises(KeyError):
            service.get(candidate.image_id)

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
        content_studio_navigation = navigation.split(
            'DashboardNavigationGroup(\n        "Content Creation"',
            1,
        )[1].split(
            'DashboardNavigationGroup(\n        "Experiences"',
            1,
        )[0]

        self.assertIn("Generation Library", source)
        generation_library_source = source.split("def _render_generation_library(", 1)[1].split(
            "def _render_archive_page",
            1,
        )[0]
        gallery_source = source.split("page_size = 18", 1)[1].split(
            "def _render_archive_page",
            1,
        )[0]
        self.assertIn("Archive", source)
        self.assertIn("Permanent Content Creation history", source)
        self.assertIn("_render_archive_page", source)
        self.assertIn("Published - X", source)
        self.assertIn("Published - Telegram", source)
        self.assertIn("Edited", source)
        self.assertIn("Imported", source)
        self.assertIn("Junk", source)
        self.assertIn("Permanent Delete", source)
        self.assertIn("Preview", source)
        self.assertNotIn("Preview", generation_library_source)
        self.assertIn("page_size = 18", generation_library_source)
        self.assertIn("generation_library_pagination_top", generation_library_source)
        self.assertIn("generation_library_pagination_bottom", generation_library_source)
        self.assertIn("◀ Previous", source)
        self.assertIn("Next ▶", source)
        self.assertIn("current_page <= 1", source)
        self.assertIn("current_page >= total_pages", source)
        self.assertNotIn("Thumbnail Grid", generation_library_source)
        self.assertNotIn("Page Size", generation_library_source)
        self.assertNotIn("number_input", generation_library_source)
        self.assertNotIn("Page {int(page_number)}", generation_library_source)
        for removed_control in (
            'text_input("Search"',
            'selectbox("Provider"',
            'selectbox("Status"',
            'selectbox("Creative Mode"',
            '"Photoshoot Session"',
            '"Sort"',
            "generated image(s)",
            '"Multi-select"',
            '"Social Platform"',
            '"Add to Creator OS"',
            '"Move to Junk"',
            '"Restore"',
            '"Archive"',
            '"Multi Edit"',
            '"Regenerate"',
            '"Send to Social Publishing"',
            '"Both"',
        ):
            self.assertNotIn(removed_control, generation_library_source)
        self.assertNotIn('key="generation_library_delete"', generation_library_source)
        self.assertIn('a1.button("🚀"', generation_library_source)
        self.assertIn('help="Publish"', generation_library_source)
        self.assertIn('a2.button("✏️"', generation_library_source)
        self.assertIn('help="Edit Image"', generation_library_source)
        self.assertIn('a3.button("📸"', generation_library_source)
        self.assertIn('help="Create Photoshoot"', generation_library_source)
        self.assertIn('a4.button("🎬"', generation_library_source)
        self.assertIn('help="Create Story"', generation_library_source)
        self.assertIn('a5.button("🎥"', generation_library_source)
        self.assertIn('help="Create Video"', generation_library_source)
        self.assertIn('a6.button(', generation_library_source)
        self.assertIn('"⭐"', generation_library_source)
        self.assertIn('help="Register Asset"', generation_library_source)
        self.assertIn('help="Already Registered"', generation_library_source)
        self.assertIn('a7.button("🗑️"', generation_library_source)
        self.assertIn('help="Delete Image"', generation_library_source)
        self.assertIn("generation_library.send_to_pending_photoshoot(record.image_id)", generation_library_source)
        self.assertIn("photoshoot_queue.start_studio_session_from_generated_image(photoshoot_record)", generation_library_source)
        self.assertNotIn("generation_library.send_to_pending_story(record.image_id)", generation_library_source)
        self.assertIn("Story Studio has not been implemented yet.", generation_library_source)
        self.assertIn("Your image remains safely in the Generation Library.", generation_library_source)
        self.assertIn("generation_library.send_to_pending_video(record.image_id)", generation_library_source)
        self.assertIn("Added to Photoshoot Studio.", generation_library_source)
        self.assertIn("Image is already in Photoshoot Studio.", generation_library_source)
        self.assertIn('st.session_state["dashboard_page"] = "Photoshoot Studio"', generation_library_source)
        self.assertIn("PUBLISH_IMAGE_UNAVAILABLE_MESSAGE", source)
        self.assertIn("_render_publish_image_preview(", source)
        self.assertIn("generation_library.resolve_publishable_image_reference", source)
        self.assertIn("disabled=not image_available", source)
        self.assertIn("disabled=not selected_caption or bool(x_blocking_message) or not image_available", source)
        self.assertIn("disabled=not selected_caption or not image_available", source)
        self.assertLess(generation_library_source.index('a1.button("🚀"'), generation_library_source.index('a2.button("✏️"'))
        self.assertLess(generation_library_source.index('a2.button("✏️"'), generation_library_source.index('a3.button("📸"'))
        self.assertLess(generation_library_source.index('a3.button("📸"'), generation_library_source.index('a4.button("🎬"'))
        self.assertLess(generation_library_source.index('a4.button("🎬"'), generation_library_source.index('a5.button("🎥"'))
        self.assertLess(generation_library_source.index('a5.button("🎥"'), generation_library_source.index('elif a6.button('))
        self.assertLess(generation_library_source.index('elif a6.button('), generation_library_source.index('a7.button("🗑️"'))
        self.assertIn("_render_generation_publish_modal", source)
        self.assertIn("_open_generation_publish_modal", source)
        self.assertIn("GENERATION_LIBRARY_PUBLISH_TRANSIENT_KEYS", source)
        self.assertIn("GENERATION_LIBRARY_PUBLISH_TRANSIENT_PREFIXES", source)
        self.assertIn("def _clear_generation_publish_state", source)
        self.assertIn("_clear_generation_publish_state()", source)
        self.assertIn('if page_name != "Generation Library":', source)
        self.assertIn("Where would you like to publish this image?", source)
        self.assertIn("Publish to X", source)
        self.assertIn("Publish to Telegram", source)
        self.assertIn("Cancel", source)
        self.assertIn("_render_telegram_publish_dialog", source)
        self.assertIn("Publish to Telegram", source)
        self.assertIn("generate_telegram_vision_themes", source)
        self.assertIn("Enter Your Own Caption", source)
        self.assertIn("Type or paste your own Telegram caption here.", source)
        self.assertIn("_render_x_engagement_publish_dialog", source)
        self.assertIn("X Publish", source)
        self.assertIn("Generate Captions", source)
        self.assertIn("Grok Vision uses the image as context", source)
        self.assertIn("Regenerate Captions", source)
        self.assertIn("Enter Your Own Caption", source)
        self.assertIn("Type or paste your own X caption here.", source)
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
        self.assertIn('"generation_library_x_custom_caption_"', source)
        self.assertIn('"generation_library_telegram_caption_"', source)
        self.assertIn('"generation_library_telegram_post_to_"', source)
        self.assertIn('"generation_library_telegram_cta_enabled_"', source)
        self.assertIn('"generation_library_telegram_cta_label_"', source)
        self.assertIn('"generation_library_telegram_cta_url_"', source)
        self.assertIn('st.session_state.pop("generation_library_x_publish_message", None)', source)
        self.assertIn("st.session_state.pop(message_key, None)", source)
        self.assertIn("generated_image_id", source)
        self.assertIn("image_reference", source)
        self.assertIn("prompt_metadata", source)
        self.assertIn("generation_metadata", source)
        self.assertIn('a1.button("🚀"', generation_library_source)
        self.assertNotIn("Generated Image: {context", source)
        self.assertNotIn("Provider: {context", source)
        self.assertNotIn("Workflow: {context", source)
        self.assertNotIn("Creative Mode: {context", source)
        self.assertNotIn("Selected Image Context", source)
        self.assertNotIn("generation_library_publish_x_", source)
        self.assertNotIn("Quick published from Generation Library.", source)
        self.assertNotIn("caption_studio.generate_for_social_queue(\n                    queue_item_id=item.queue_item_id", source)
        self.assertIn("Published to X", source)
        self.assertNotIn("filename = (", gallery_source)
        self.assertNotIn("st.write(filename)", gallery_source)
        self.assertNotIn("st.write(record.image_id)", gallery_source)
        self.assertNotIn("Open Prompt", gallery_source)
        self.assertNotIn("Open Reference", gallery_source)
        self.assertNotIn("Provider Metadata", gallery_source)
        self.assertNotIn('with st.expander("Metadata"', gallery_source)
        self.assertIn("Generation Library", navigation)
        self.assertIn("Archive", navigation)
        self.assertIn("Content Creation", navigation)
        self.assertIn("📸", navigation)
        expected_navigation_order = (
            "Content Studio",
            "Generation Library",
            "Edit Studio",
            "Photoshoot Studio",
            "Reference Library",
            "Archive",
            "Diagnostics",
        )
        last_index = -1
        for page_name in expected_navigation_order:
            current_index = content_studio_navigation.index(page_name)
            self.assertGreater(current_index, last_index)
            last_index = current_index
        for hidden_page_name in (
            "Creative Director",
            "Social Studio",
            "Social Publishing",
            "Caption Studio",
            "Prompt History",
            "Settings",
        ):
            self.assertNotIn(hidden_page_name, content_studio_navigation)
        self.assertIn("Generation Library", main)


if __name__ == "__main__":
    unittest.main()
