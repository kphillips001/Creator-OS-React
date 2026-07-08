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


class GenerationLibraryServiceTests(unittest.TestCase):
    def make_service(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return GenerationLibraryService(storage_dir=Path(temp_dir.name) / "library")

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
        self.assertEqual(provider.total, 2)
        self.assertEqual(photoshoot.total, 2)
        self.assertEqual(sorted_result.records[0].provider_id, "flux")

    def test_bulk_selection_move_to_junk_and_archive(self):
        service = self.make_service()
        service.sync_job(successful_job())

        selected = service.bulk_select(GenerationLibraryFilter(status="active"))
        junked = service.move_to_junk(selected.image_ids[:1])
        archived = service.archive(selected.image_ids[1:])

        self.assertTrue(junked.success)
        self.assertTrue(archived.success)
        self.assertEqual(service.browse(GenerationLibraryFilter(status="junk")).total, 1)
        self.assertEqual(service.browse(GenerationLibraryFilter(status="archived")).total, 1)
        self.assertEqual(service.browse(GenerationLibraryFilter(selected_only=True)).total, 0)

    def test_restore_and_delete_generated_records(self):
        service = self.make_service()
        created = service.sync_job(successful_job())
        service.move_to_junk((created[0].image_id,))

        restored = service.restore((created[0].image_id,))
        deleted = service.delete((created[1].image_id,))

        self.assertTrue(restored.success)
        self.assertTrue(deleted.success)
        self.assertEqual(service.get(created[0].image_id).status, "active")
        with self.assertRaises(KeyError):
            service.get(created[1].image_id)

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
        after = service.get(record.image_id)

        self.assertIsNone(before.imported_asset_id)
        self.assertTrue(action.success)
        self.assertEqual(action.imported_asset_ids, (501,))
        self.assertEqual(len(ingestion.jobs), 1)
        self.assertEqual(ingestion.jobs[0].result.output_references, (record.output_reference,))
        self.assertEqual(after.status, "added_to_creator_os")
        self.assertEqual(after.imported_asset_id, 501)

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

    def test_content_studio_generation_library_ui_contract(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(encoding="utf-8")
        navigation = Path("app/dashboard/navigation.py").read_text(encoding="utf-8")
        main = Path("app/dashboard/main.py").read_text(encoding="utf-8")

        self.assertIn("Generation Library", source)
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
        self.assertIn("Publish X", source)
        self.assertIn("Published to X", source)
        self.assertIn("Open Prompt", source)
        self.assertIn("Open Reference", source)
        self.assertIn("Metadata", source)
        self.assertIn("Provider Metadata", source)
        self.assertIn("Generation Library", navigation)
        self.assertIn("Generation Library", main)


if __name__ == "__main__":
    unittest.main()
