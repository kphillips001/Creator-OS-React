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

from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationResult, GenerationStatus
from app.models.photoshoot_queue import PHOTOSHOOT_ASSET_METADATA_KEY
from app.services.generation_engine_service import GenerationEngineService
from app.services.photoshoot_queue_service import PhotoshootQueueService


class NoReferenceLibraryService:
    def get_active_reference(self, *, creator_profile_id):
        return None


class FakeIngestion:
    def __init__(self):
        self.status_by_job = {}

    def ingestion_status_for_job(self, generation_job_id):
        return self.status_by_job.get(
            generation_job_id,
            {"status": "pending", "imported_asset_ids": (), "failed_messages": ()},
        )


class FakeAssetRepository:
    def __init__(self):
        self.updated = []
        self.assets = {
            101: SimpleNamespace(id=101, media_metadata={}),
            102: SimpleNamespace(id=102, media_metadata={}),
        }

    def get_by_id(self, asset_id):
        return self.assets[int(asset_id)]

    def update_media_metadata(self, asset_id, media_metadata):
        self.updated.append((int(asset_id), media_metadata))
        self.assets[int(asset_id)] = SimpleNamespace(
            id=int(asset_id),
            media_metadata=media_metadata,
        )


def prompt_plan(index, creator_profile_id=7):
    return PromptPlan(
        plan_id=f"prompt_plan_{index}",
        session_id=f"creative_session_{index}",
        creator_profile_id=creator_profile_id,
        prompt_text=f"Shot {index} prompt",
        creative_mode="social_safe",
        creative_tags=(f"shot {index}",),
        reference_asset_id=55,
        reference_asset_path="C:/Creator-OS/data/cms/vault/originals/images/55.png",
        creative_rationale="Testing photoshoot queue.",
        prompt_metadata={"provider_neutral": True},
    )


class PhotoshootQueueServiceTests(unittest.TestCase):
    def make_service(self, ingestion=None, assets=None):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return PhotoshootQueueService(
            storage_dir=temp_dir.name,
            generation_ingestion_service=ingestion or FakeIngestion(),
            asset_repository=assets or FakeAssetRepository(),
        )

    def make_engine(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return GenerationEngineService(
            storage_dir=temp_dir.name,
            reference_library_service=NoReferenceLibraryService(),
            providers={},
        )

    def test_photoshoot_creation_and_queue_ordering(self):
        service = self.make_service()

        session = service.create_session(
            creator_profile_id=7,
            prompt_plans=[prompt_plan(1), prompt_plan(2), prompt_plan(3)],
            provider_id="seedream_4_5",
            reference_asset_id=55,
            creator_notes="keep a sunny park sequence",
        )
        requests = service.requests_for_session(session.session_id)

        self.assertEqual(session.creator_profile_id, 7)
        self.assertEqual(session.provider_id, "seedream_4_5")
        self.assertEqual(tuple(request.sequence_index for request in requests), (1, 2, 3))
        self.assertEqual(tuple(request.prompt_plan_id for request in requests), ("prompt_plan_1", "prompt_plan_2", "prompt_plan_3"))
        self.assertEqual(service.next_queued_request(session.session_id).prompt_plan_id, "prompt_plan_1")

    def test_generation_engine_integration_consumes_one_prompt_at_a_time(self):
        service = self.make_service()
        engine = self.make_engine()
        session = service.create_session(
            creator_profile_id=7,
            prompt_plans=[prompt_plan(1), prompt_plan(2)],
            provider_id="seedream_4_5",
            reference_asset_id=55,
        )

        first_job = service.queue_next_prompt(
            session_id=session.session_id,
            generation_engine=engine,
        )
        blocked_job = service.queue_next_prompt(
            session_id=session.session_id,
            generation_engine=engine,
        )

        self.assertIsNotNone(first_job)
        self.assertIsNone(blocked_job)
        self.assertEqual(len(engine.list_jobs()), 1)
        self.assertEqual(first_job.request.metadata["source"], "photoshoot_queue")
        self.assertEqual(first_job.request.metadata["photoshoot_session_id"], session.session_id)
        self.assertEqual(first_job.request.metadata["photoshoot_sequence_index"], 1)

    def test_pause_resume_and_cancel(self):
        service = self.make_service()
        session = service.create_session(
            creator_profile_id=7,
            prompt_plans=[prompt_plan(1)],
        )

        paused = service.pause_session(session.session_id)
        resumed = service.resume_session(session.session_id)
        cancelled = service.cancel_session(session.session_id)

        self.assertEqual(paused.status, "paused")
        self.assertEqual(resumed.status, "queued")
        self.assertEqual(cancelled.status, "cancelled")

    def test_creator_review_approve_reject_regenerate_continue(self):
        service = self.make_service()
        engine = self.make_engine()
        session = service.create_session(
            creator_profile_id=7,
            prompt_plans=[prompt_plan(1), prompt_plan(2)],
        )
        job = service.queue_next_prompt(
            session_id=session.session_id,
            generation_engine=engine,
        )

        completed = engine.complete_job(
            job.job_id,
            GenerationResult(
                result_id="generation_result_1",
                request_id=job.request.request_id,
                job_id=job.job_id,
                provider_id=job.request.provider_id,
                status=GenerationStatus.SUCCEEDED.value,
                output_references=("https://cdn.test/shot1.png",),
            ),
        )
        request = service.mark_generation_complete(
            generation_job_id=completed.job_id,
            imported_asset_ids=(101,),
        )
        approved = service.approve_request(request.request_id)
        next_job = service.queue_next_prompt(
            session_id=session.session_id,
            generation_engine=engine,
        )
        second = service.mark_generation_complete(
            generation_job_id=next_job.job_id,
            imported_asset_ids=(102,),
        )
        rejected = service.reject_request(second.request_id)
        regenerated = service.regenerate_request(second.request_id)

        self.assertEqual(approved.status, "approved")
        self.assertEqual(next_job.request.metadata["photoshoot_sequence_index"], 2)
        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(regenerated.status, "queued")
        self.assertEqual(regenerated.review_status, "regenerate")

    def test_generated_images_are_available_for_creator_review_before_asset_import(self):
        service = self.make_service()
        engine = self.make_engine()
        session = service.create_session(
            creator_profile_id=7,
            prompt_plans=[prompt_plan(1)],
        )
        job = service.queue_next_prompt(
            session_id=session.session_id,
            generation_engine=engine,
        )

        request = service.mark_generation_complete(
            generation_job_id=job.job_id,
            generated_image_ids=("generated_image_photoshoot_1",),
        )
        approved = service.approve_request(request.request_id)
        progress = service.progress(session.session_id)
        result = service.result(session.session_id)

        self.assertEqual(approved.status, "approved")
        self.assertEqual(progress.approved_images, 1)
        self.assertEqual(result.metadata["approved_generated_image_ids"], ("generated_image_photoshoot_1",))

    def test_session_history_statistics_and_asset_association(self):
        assets = FakeAssetRepository()
        service = self.make_service(assets=assets)
        engine = self.make_engine()
        session = service.create_session(
            creator_profile_id=7,
            prompt_plans=[prompt_plan(1), prompt_plan(2)],
        )
        job = service.queue_next_prompt(
            session_id=session.session_id,
            generation_engine=engine,
        )
        request = service.mark_generation_complete(
            generation_job_id=job.job_id,
            imported_asset_ids=(101,),
        )
        service.approve_request(request.request_id)

        history = service.list_sessions(creator_profile_id=7)
        progress = service.progress(session.session_id)
        result = service.result(session.session_id)

        self.assertEqual(history[0].session_id, session.session_id)
        self.assertEqual(progress.approved_images, 1)
        self.assertEqual(progress.imported_assets, 1)
        self.assertEqual(result.approved_asset_ids, (101,))
        self.assertEqual(
            assets.updated[0][1][PHOTOSHOOT_ASSET_METADATA_KEY]["session_id"],
            session.session_id,
        )

    def test_sync_ingested_assets_associates_assets(self):
        ingestion = FakeIngestion()
        assets = FakeAssetRepository()
        service = self.make_service(ingestion=ingestion, assets=assets)
        engine = self.make_engine()
        session = service.create_session(
            creator_profile_id=7,
            prompt_plans=[prompt_plan(1)],
        )
        job = service.queue_next_prompt(
            session_id=session.session_id,
            generation_engine=engine,
        )
        ingestion.status_by_job[job.job_id] = {
            "status": "imported",
            "imported_asset_ids": (101,),
            "failed_messages": (),
        }

        synced = service.sync_ingested_assets_for_session(session.session_id)

        self.assertEqual(synced, (101,))
        self.assertEqual(
            assets.updated[0][1][PHOTOSHOOT_ASSET_METADATA_KEY]["request_id"],
            service.requests_for_session(session.session_id)[0].request_id,
        )

    def test_content_studio_integration(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("PhotoshootQueueService", source)
        self.assertIn("Start Photoshoot", source)
        self.assertIn("Continue Photoshoot", source)
        self.assertIn("Open Existing Photoshoot", source)
        self.assertIn("Queue Next Prompt", source)
        self.assertIn("Running next Photoshoot prompt", source)
        self.assertIn("Generated Image IDs", source)
        self.assertIn("Batch Review", source)
        self.assertIn("Approve", source)
        self.assertIn("Reject", source)
        self.assertIn("Regenerate", source)
        self.assertNotIn("submit_wavespeed_task", source)
        self.assertNotIn("poll_wavespeed_result", source)


if __name__ == "__main__":
    unittest.main()
