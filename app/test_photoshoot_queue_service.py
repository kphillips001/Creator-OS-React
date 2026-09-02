import sys
import tempfile
import threading
import types
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
    psycopg.IntegrityError = type("IntegrityError", (Exception,), {})
    rows.dict_row = object()
    json_types.Json = lambda value: value
    json_types.Jsonb = lambda value: value
    errors.UniqueViolation = type("UniqueViolation", (Exception,), {})
    sys.modules["psycopg"] = psycopg
    sys.modules["psycopg.rows"] = rows
    sys.modules["psycopg.types"] = psycopg_types
    sys.modules["psycopg.types.json"] = json_types
    sys.modules["psycopg.errors"] = errors

from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationResult, GenerationStatus
from app.models.generation_library import GeneratedImageRecord
from app.models.photoshoot_queue import PHOTOSHOOT_ASSET_METADATA_KEY
from app.services.content_archive_service import ContentArchiveService
from app.services.generation_library_service import GenerationLibraryService
from app.services.generation_engine_service import GenerationEngineService
from app.services.photoshoot_queue_service import PhotoshootQueueService
from app.services.photoshoot_creative_director_service import PhotoshootCreativeDirectorWorkflowService
from app.services.photoshoot_manual_service import PhotoshootManualService
from app.services.photoshoot_summary_service import PhotoshootSummaryService
from app.services.creative_director_service import CreativeDirectorService


class NoReferenceLibraryService:
    def get_active_canonical_reference(self, *, creator_profile_id):
        return None

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


def generated_record(image_id="generated_image_seed"):
    return GeneratedImageRecord(
        image_id=image_id,
        generation_job_id=f"generation_job_{image_id}",
        generation_request_id=f"generation_request_{image_id}",
        generation_result_id=f"generation_result_{image_id}",
        output_reference=f"https://cdn.test/{image_id}.png",
        creator_profile_id=7,
        provider_id="seedream_5_0_pro",
        prompt_plan_id=f"prompt_plan_{image_id}",
        prompt_text="Seed image prompt",
        creative_mode="spicy",
        reference_asset_id=55,
        prompt_metadata={"creative_tags": ("garden",)},
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

    def make_generation_library(self):
        storage_dir = tempfile.TemporaryDirectory()
        content_root = tempfile.TemporaryDirectory()
        self.addCleanup(storage_dir.cleanup)
        self.addCleanup(content_root.cleanup)
        archive = ContentArchiveService(
            storage_dir=Path(storage_dir.name) / "archive",
            content_root=content_root.name,
        )
        return GenerationLibraryService(
            storage_dir=storage_dir.name,
            archive_service=archive,
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
        self.assertEqual(session.target_shot_count, 5)
        self.assertEqual(session.creative_continuity["target_shot_count"], 5)
        self.assertEqual(session.creative_continuity["generation_mode_behavior"], "photoshoot_queue")
        self.assertEqual(session.creative_continuity["wavespeed_generation_mode_key"], "photoshoot_set")
        self.assertIn("preserve the same selected-shot", session.creative_continuity["continuity"])
        self.assertIn("Do not use normal generation scene-hopping", session.creative_continuity["normal_generation_boundary"])
        self.assertEqual(tuple(request.sequence_index for request in requests), (1, 2, 3))
        self.assertEqual(tuple(request.prompt_plan_id for request in requests), ("prompt_plan_1", "prompt_plan_2", "prompt_plan_3"))
        self.assertEqual(service.next_queued_request(session.session_id).prompt_plan_id, "prompt_plan_1")

    def test_canonical_session_remains_readable_while_replacement_is_being_written(self):
        service = self.make_service()
        session = service.create_session(
            creator_profile_id=7,
            prompt_plans=[prompt_plan(1)],
            provider_id="seedream_4_5",
        )
        write_started = threading.Event()
        allow_write = threading.Event()
        original_dump = __import__("json").dump

        def delayed_dump(data, file, *args, **kwargs):
            write_started.set()
            self.assertTrue(allow_write.wait(timeout=2))
            return original_dump(data, file, *args, **kwargs)

        writer = threading.Thread(
            target=service._write_sessions,
            args=(list(service.list_sessions()),),
        )
        read_result = []
        reader = threading.Thread(
            target=lambda: read_result.append(service.get_session(session.session_id).session_id),
        )
        with patch("app.services.photoshoot_queue_service.json.dump", side_effect=delayed_dump):
            writer.start()
            self.assertTrue(write_started.wait(timeout=2))
            # Readers participate in the same cross-process contract and wait
            # for the atomic replacement instead of holding a conflicting JSON handle.
            reader.start()
            self.assertTrue(reader.is_alive())
            allow_write.set()
            writer.join(timeout=2)
            reader.join(timeout=2)

        self.assertFalse(writer.is_alive())
        self.assertFalse(reader.is_alive())
        self.assertEqual(read_result, [session.session_id])
        self.assertEqual(service.get_session(session.session_id).session_id, session.session_id)

    def test_custom_target_shot_count_persists_when_session_is_reloaded(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        service = PhotoshootQueueService(
            storage_dir=temp_dir.name,
            generation_ingestion_service=FakeIngestion(),
            asset_repository=FakeAssetRepository(),
        )
        session = service.create_session(
            creator_profile_id=7,
            prompt_plans=[prompt_plan(1)],
            provider_id="seedream_4_5",
        )

        service.update_session_settings(session.session_id, target_shot_count=27)
        reloaded = PhotoshootQueueService(
            storage_dir=temp_dir.name,
            generation_ingestion_service=FakeIngestion(),
            asset_repository=FakeAssetRepository(),
        ).get_session(session.session_id)

        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.target_shot_count, 27)
        self.assertEqual(reloaded.creative_continuity["target_shot_count"], 27)

    def test_target_extension_is_durable_one_shot_and_retry_idempotent(self):
        service = self.make_service()
        session = service.create_session(
            creator_profile_id=7, prompt_plans=[prompt_plan(index) for index in range(1, 6)],
            target_shot_count=5,
        )
        for request in service.requests_for_session(session.session_id):
            service._replace_request(replace(request, status="approved"))

        extended, changed = service.extend_target_one_shot(
            session.session_id, expected_target_shot_count=5,
        )
        retried, retry_changed = service.extend_target_one_shot(
            session.session_id, expected_target_shot_count=5,
        )

        self.assertTrue(changed)
        self.assertFalse(retry_changed)
        self.assertEqual(extended.target_shot_count, 6)
        self.assertEqual(retried.target_shot_count, 6)
        self.assertEqual(service.get_session(session.session_id).target_shot_count, 6)
        self.assertEqual(extended.creative_continuity["target_shot_count"], 6)

        sixth = service.add_studio_shot_request(
            session_id=session.session_id, prompt_text="Shot 6", shot_direction="Continue",
        )
        service._replace_request(replace(sixth, status="approved"))
        seventh_target, changed_again = service.extend_target_one_shot(
            session.session_id, expected_target_shot_count=6,
        )
        self.assertTrue(changed_again)
        self.assertEqual(seventh_target.target_shot_count, 7)
        self.assertEqual(seventh_target.session_id, session.session_id)
        self.assertEqual(seventh_target.provider_id, session.provider_id)
        self.assertEqual(seventh_target.creative_mode, session.creative_mode)

    def test_extension_requires_reached_active_idle_progression_session(self):
        service = self.make_service()
        session = service.create_session(
            creator_profile_id=7, prompt_plans=[prompt_plan(1)], target_shot_count=5,
        )
        request = service.requests_for_session(session.session_id)[0]
        service._replace_request(replace(request, status="rejected"))
        with self.assertRaisesRegex(ValueError, "has not been reached"):
            service.extend_target_one_shot(session.session_id, expected_target_shot_count=5)
        request = service.requests_for_session(session.session_id)[0]
        service._replace_request(replace(request, status="awaiting_review"))
        with self.assertRaisesRegex(ValueError, "current shot"):
            service.extend_target_one_shot(session.session_id, expected_target_shot_count=5)

    def test_existing_fifteen_shot_session_remains_valid(self):
        service = self.make_service()
        session = service.create_session(
            creator_profile_id=7, prompt_plans=[prompt_plan(1)], target_shot_count=15,
        )
        self.assertEqual(service.get_session(session.session_id).target_shot_count, 15)

    def test_open_ended_target_persists_when_session_is_reloaded(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        service = PhotoshootQueueService(
            storage_dir=temp_dir.name,
            generation_ingestion_service=FakeIngestion(),
            asset_repository=FakeAssetRepository(),
        )
        session = service.create_session(
            creator_profile_id=7, prompt_plans=[prompt_plan(1)], provider_id="seedream_4_5",
            target_shot_count=0,
        )

        reloaded = PhotoshootQueueService(
            storage_dir=temp_dir.name,
            generation_ingestion_service=FakeIngestion(),
            asset_repository=FakeAssetRepository(),
        ).get_session(session.session_id)

        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.target_shot_count, 0)
        self.assertEqual(reloaded.creative_continuity["target_shot_count"], 0)

        progress = PhotoshootCreativeDirectorWorkflowService(
            queue=service, library=SimpleNamespace(), creative_director=SimpleNamespace(), summary_service=SimpleNamespace(),
        )._planning_progress(reloaded)
        self.assertEqual(progress["target_shot_count"], 0)
        self.assertEqual(progress["remaining_shots"], 0)
        self.assertEqual(progress["editorial_stage"], "Open-ended")
        self.assertNotIn("of 0", PhotoshootCreativeDirectorWorkflowService._planner_explanation(progress))

    def test_target_switching_changes_semantics_without_resetting_continuity(self):
        service = self.make_service()
        session = service.create_session(
            creator_profile_id=7, prompt_plans=[prompt_plan(1)], provider_id="seedream_4_5",
            target_shot_count=5,
            creative_continuity={
                "current_shot_image_id": "approved-image",
                "approved_directions": ({"title": "Washing hair"},),
                "progression_stage": 3,
            },
        )

        freeflow = service.update_session_settings(session.session_id, target_shot_count=0)
        self.assertEqual(freeflow.target_shot_count, 0)
        self.assertEqual(freeflow.creative_continuity["current_shot_image_id"], "approved-image")
        self.assertEqual(freeflow.creative_continuity["approved_directions"][0]["title"], "Washing hair")
        self.assertEqual(freeflow.creative_continuity["progression_stage"], 3)
        freeflow_context = PhotoshootCreativeDirectorWorkflowService._ai_context(
            "shower", {}, "", progression_stage=3, current_shot=2, target_shot_count=0,
        )
        self.assertFalse(freeflow_context["progression_enabled"])
        self.assertIsNone(freeflow_context["progression_stage"])

        restored = service.update_session_settings(session.session_id, target_shot_count=10)
        self.assertEqual(restored.target_shot_count, 10)
        self.assertEqual(restored.creative_continuity["current_shot_image_id"], "approved-image")
        self.assertEqual(restored.creative_continuity["approved_directions"][0]["title"], "Washing hair")
        restored_context = PhotoshootCreativeDirectorWorkflowService._ai_context(
            "shower", {}, "", progression_stage=3, current_shot=2,
            editorial_stage="Beginning", target_shot_count=10,
        )
        self.assertTrue(restored_context["progression_enabled"])
        self.assertEqual(restored_context["progression_stage"], 3)
        self.assertEqual(restored_context["remaining_shots"], 8)

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
        self.assertEqual(first_job.request.metadata["generation_mode_behavior"], "photoshoot_queue")
        self.assertEqual(first_job.request.metadata["wavespeed_generation_mode_key"], "photoshoot_set")
        self.assertIn("same environment", first_job.request.metadata["wavespeed_mode_decision"])
        self.assertIn("scene-hopping", first_job.request.metadata["wavespeed_mode_decision"])
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
        self.assertIsNone(service.current_session(creator_profile_id=7))

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
        service.update_session_settings(
            session.session_id,
            inspiration_ideas=("Closer portrait", "Window profile"),
            inspiration_planning_shot=2,
            selected_inspiration="Closer portrait",
            workflow_stage="direction_approved",
        )
        rejected = service.reject_request(second.request_id)
        after_rejection = service.get_session(session.session_id)
        regenerated = service.regenerate_request(second.request_id)

        self.assertEqual(approved.status, "approved")
        self.assertEqual(next_job.request.metadata["photoshoot_sequence_index"], 2)
        self.assertEqual(rejected.status, "rejected")
        self.assertIsNone(after_rejection.current_request_id)
        self.assertEqual(after_rejection.creative_continuity["workflow_stage"], "ready_for_next_shot")
        self.assertFalse(after_rejection.creative_continuity["direction_approved"])
        self.assertEqual(tuple(after_rejection.creative_continuity["inspiration_ideas"]), ("Closer portrait", "Window profile"))
        self.assertEqual(after_rejection.creative_continuity["selected_inspiration"], "Closer portrait")
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

    def test_approve_request_accepts_canonical_asset_ids_at_approval_boundary(self):
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

        approved = service.approve_request(request.request_id, imported_asset_ids=(101,))
        result = service.result(session.session_id)

        self.assertEqual(approved.status, "approved")
        self.assertEqual(approved.imported_asset_ids, (101,))
        self.assertEqual(result.approved_asset_ids, (101,))
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

    def test_photoshoot_studio_seed_persists_and_session_finishes(self):
        service = self.make_service()
        seed = generated_record()

        session, created = service.start_studio_session_from_generated_image(
            seed,
            canonical_identity_reference={"asset_id": 55, "path": "https://cdn.test/frozen-identity.png"},
        )
        reopened, duplicate_created = service.start_studio_session_from_generated_image(
            seed,
            canonical_identity_reference={"asset_id": 99, "path": "https://cdn.test/new-active-identity.png"},
        )
        seed_request = service.requests_for_session(session.session_id)[0]
        shot_request = service.add_studio_shot_request(
            session_id=session.session_id,
            prompt_text="Create one closer portrait while preserving the same garden photoshoot.",
            shot_direction="Closer portrait",
            provider_id="seedream_5_0_pro",
            active_reference_image_id="generated_image_shot_reference",
            active_reference_output_reference="https://cdn.test/selected-reference.png",
        )
        engine = self.make_engine()
        job = service.queue_next_prompt(
            session_id=session.session_id,
            generation_engine=engine,
        )
        completed_request = service.mark_generation_complete(
            generation_job_id=job.job_id,
            generated_image_ids=("generated_image_shot_1",),
        )
        approved_request = service.approve_request(completed_request.request_id)

        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(reopened.session_id, session.session_id)
        self.assertEqual(session.creative_continuity["seed_image_id"], seed.image_id)
        self.assertEqual(session.creative_continuity["canonical_identity_reference"]["asset_id"], 55)
        self.assertEqual(session.creative_continuity["canonical_identity_reference"]["path"], "https://cdn.test/frozen-identity.png")
        self.assertTrue(session.creative_continuity["canonical_identity_reference_frozen"])
        self.assertEqual(reopened.creative_continuity["canonical_identity_reference"]["asset_id"], 55)
        self.assertIn("session_defaults", session.creative_continuity)
        self.assertEqual(session.creative_continuity["progression_stage"], 0)
        self.assertEqual(seed_request.status, "approved")
        self.assertTrue(seed_request.metadata["is_seed_image"])
        self.assertEqual(tuple(seed_request.metadata["generated_image_ids"]), (seed.image_id,))
        self.assertEqual(shot_request.status, "queued")
        self.assertEqual(shot_request.metadata["shot_direction"], "Closer portrait")
        self.assertEqual(shot_request.metadata["active_reference_image_id"], "generated_image_shot_reference")
        self.assertEqual(job.request.metadata["reference_image_url"], "https://cdn.test/selected-reference.png")
        self.assertEqual(job.request.metadata["photoshoot_continuity_reference_image_url"], "https://cdn.test/selected-reference.png")
        self.assertEqual(job.request.metadata["canonical_reference_image_url"], "https://cdn.test/frozen-identity.png")
        self.assertEqual(job.request.metadata["original_photoshoot_seed_reference_image_url"], seed.output_reference)
        self.assertEqual(job.request.metadata["original_photoshoot_seed_image_id"], seed.image_id)
        self.assertEqual(job.request.metadata["previous_approved_continuity_reference_image_url"], "https://cdn.test/selected-reference.png")
        self.assertEqual(job.request.reference_asset_id, 55)
        self.assertEqual(completed_request.status, "awaiting_review")
        self.assertEqual(completed_request.metadata["generated_image_ids"], ("generated_image_shot_1",))
        self.assertEqual(approved_request.status, "approved")
        updated_session = service.record_creative_direction(
            session_id=session.session_id,
            recommendation={
                "title": "Balcony lean",
                "creative_direction": "Move her closer to the balcony door while preserving wardrobe.",
                "reasoning": "Natural continuation.",
                "continuity_notes": "Keep wardrobe and hair.",
                "camera_framing": "Close-medium",
                "lighting": "Same soft light",
                "emotion": "Playful",
                "pose_composition": "Lean toward camera",
                "creative_mode": "premium",
                "continuity_locks": {"wardrobe": True},
            },
            final_prompt="canonical photoshoot prompt",
        )

        self.assertEqual(updated_session.creative_continuity["progression_stage"], 3)
        self.assertIn("canonical photoshoot prompt", updated_session.creative_continuity["approved_prompts"])
        self.assertIn(
            "Create one closer portrait while preserving the same garden photoshoot.",
            updated_session.creative_continuity["approved_prompts"],
        )
        self.assertEqual(updated_session.creative_continuity["approved_directions"][0]["title"], "Balcony lean")
        finished = service.finish_session(session.session_id)

        self.assertEqual(finished.status, "completed")
        self.assertIsNone(service.current_session(creator_profile_id=7))

    def test_later_photoshoot_requests_keep_seed_and_advance_only_previous_approved_reference(self):
        service = self.make_service()
        seed = generated_record()
        session, _ = service.start_studio_session_from_generated_image(
            seed,
            canonical_identity_reference={"asset_id": 93, "path": "https://cdn.test/asset-93.png"},
        )
        engine = self.make_engine()
        previous_id = seed.image_id
        previous_url = seed.output_reference

        for shot_number in (2, 3, 4, 5):
            request = service.add_studio_shot_request(
                session_id=session.session_id,
                prompt_text=f"Shot {shot_number}",
                shot_direction=f"Direction {shot_number}",
                active_reference_image_id=previous_id,
                active_reference_output_reference=previous_url,
            )
            job = service.queue_next_prompt(session_id=session.session_id, generation_engine=engine)
            metadata = job.request.metadata
            self.assertEqual(metadata["canonical_reference_image_url"], "https://cdn.test/asset-93.png")
            self.assertEqual(metadata["original_photoshoot_seed_reference_image_url"], seed.output_reference)
            self.assertEqual(metadata["previous_approved_continuity_reference_image_url"], previous_url)
            service.mark_generation_complete(
                generation_job_id=job.job_id, generated_image_ids=(f"shot-{shot_number}",),
            )
            service.approve_request(request.request_id)
            previous_id = f"shot-{shot_number}"
            previous_url = f"https://cdn.test/shot-{shot_number}.png"

        extended, changed = service.extend_target_one_shot(
            session.session_id, expected_target_shot_count=5,
        )
        self.assertTrue(changed)
        self.assertEqual(extended.target_shot_count, 6)
        extension = service.add_studio_shot_request(
            session_id=session.session_id,
            prompt_text="Extended shot 6",
            shot_direction="Direction 6",
            active_reference_image_id=previous_id,
            active_reference_output_reference=previous_url,
        )
        extension_job = service.queue_next_prompt(session_id=session.session_id, generation_engine=engine)
        self.assertEqual(extension_job.request.metadata["original_photoshoot_seed_reference_image_url"], seed.output_reference)
        self.assertEqual(extension_job.request.metadata["previous_approved_continuity_reference_image_id"], "shot-5")
        self.assertEqual(extension.request_id, extension_job.request.metadata["photoshoot_request_id"])

    def test_return_seed_request_removes_seed_from_active_timeline(self):
        service = self.make_service()
        seed = generated_record()
        session, _created = service.start_studio_session_from_generated_image(seed)
        seed_request = service.requests_for_session(session.session_id)[0]
        shot_request = service.add_studio_shot_request(
            session_id=session.session_id,
            prompt_text="Continue with a second shot.",
            shot_direction="Second shot",
            provider_id="seedream_5_0_pro",
            active_reference_image_id=seed.image_id,
            active_reference_output_reference=seed.output_reference,
        )
        service._replace_request(
            replace(
                shot_request,
                status="approved",
                review_status="approved",
                metadata={
                    **dict(shot_request.metadata or {}),
                    "generated_image_ids": ("generated_image_second_shot",),
                },
            )
        )

        returned = service.return_seed_request_to_library(seed_request.request_id)
        updated_session = service.get_session(session.session_id)
        approved_requests = tuple(
            request
            for request in service.requests_for_session(session.session_id)
            if request.status == "approved"
        )

        self.assertEqual(returned.status, "returned_to_library")
        self.assertEqual(returned.review_status, "returned_to_library")
        self.assertEqual(tuple(request.request_id for request in approved_requests), (shot_request.request_id,))
        self.assertNotIn("seed_image_id", updated_session.creative_continuity)
        self.assertNotIn("seed_output_reference", updated_session.creative_continuity)
        self.assertEqual(updated_session.creative_continuity["current_shot_image_id"], "generated_image_second_shot")
        self.assertEqual(updated_session.status, "running")

    def test_return_seed_request_ends_session_when_seed_is_only_shot(self):
        service = self.make_service()
        seed = generated_record()
        session, _created = service.start_studio_session_from_generated_image(seed)
        seed_request = service.requests_for_session(session.session_id)[0]

        returned = service.return_seed_request_to_library(seed_request.request_id)
        updated_session = service.get_session(session.session_id)

        self.assertEqual(returned.status, "returned_to_library")
        self.assertEqual(updated_session.status, "cancelled")
        self.assertIsNone(updated_session.creative_continuity["current_shot_image_id"])
        self.assertEqual(updated_session.creative_continuity["workflow_stage"], "seed_returned")

    def test_direction_approval_persists_and_clears_after_shot_approval(self):
        service = self.make_service()
        seed = generated_record()
        session, _created = service.start_studio_session_from_generated_image(seed)
        approved_direction = service.record_creative_direction(
            session_id=session.session_id,
            recommendation={
                "title": "Window turn",
                "creative_direction": "Turn toward the window with stronger eye contact.",
                "reasoning": "Progresses the session.",
                "continuity_notes": "Keep room and lighting.",
                "camera_framing": "Medium portrait",
                "lighting": "Window light",
                "emotion": "Confident",
                "pose_composition": "Turned shoulders",
                "creative_mode": "premium",
            },
            final_prompt="canonical approved prompt",
        )

        self.assertTrue(approved_direction.creative_continuity["direction_approved"])
        self.assertEqual(approved_direction.creative_continuity["current_prompt"], "canonical approved prompt")
        self.assertEqual(approved_direction.creative_continuity["current_direction"]["title"], "Window turn")
        self.assertEqual(approved_direction.creative_continuity["workflow_stage"], "direction_approved")

        shot_request = service.add_studio_shot_request(
            session_id=session.session_id,
            prompt_text="canonical approved prompt edited by creator",
            shot_direction="Turn toward the window with stronger eye contact.",
            provider_id="seedream_5_0_pro",
            active_reference_image_id=seed.image_id,
            active_reference_output_reference=seed.output_reference,
            creative_direction=approved_direction.creative_continuity["current_direction"],
        )
        service._replace_request(
            replace(
                shot_request,
                status="awaiting_review",
                metadata={
                    **dict(shot_request.metadata or {}),
                    "generated_image_ids": ("generated_image_window_turn",),
                },
            )
        )
        completed = service.get_request(shot_request.request_id)
        approved = service.approve_request(completed.request_id)
        refreshed = service.get_session(session.session_id)

        self.assertEqual(approved.status, "approved")
        self.assertFalse(refreshed.creative_continuity["direction_approved"])
        self.assertEqual(refreshed.creative_continuity["current_prompt"], "")
        self.assertEqual(refreshed.creative_continuity["current_direction"], {})
        self.assertEqual(refreshed.creative_continuity["workflow_stage"], "ready_for_next_shot")
        self.assertEqual(refreshed.creative_continuity["current_shot_image_id"], "generated_image_window_turn")
        self.assertEqual(refreshed.creative_continuity["selected_timeline_index"], 1)
        approved_requests = tuple(
            request
            for request in service.requests_for_session(session.session_id)
            if request.status == "approved"
        )
        approved_image_ids = tuple(
            image_id
            for request in approved_requests
            for image_id in tuple((request.metadata or {}).get("generated_image_ids") or ())
        )
        self.assertIn(seed.image_id, approved_image_ids)
        self.assertIn("generated_image_window_turn", approved_image_ids)

    def test_replace_approved_shot_restores_previous_continuity_and_invalidates_downstream(self):
        service = self.make_service()
        seed = generated_record()
        session, _created = service.start_studio_session_from_generated_image(seed)
        created = []
        reference_id = seed.image_id
        for index in (2, 3, 4):
            request = service.add_studio_shot_request(
                session_id=session.session_id, prompt_text=f"Shot {index} prompt",
                shot_direction=f"Direction {index}", active_reference_image_id=reference_id,
                active_reference_output_reference=f"/shot-{index - 1}.png",
                creative_direction={"title": f"Shot {index}", "creative_direction": f"Direction {index}"},
            )
            service._replace_request(replace(request, status="awaiting_review", metadata={
                **dict(request.metadata or {}), "generated_image_ids": (f"shot-{index}",),
            }))
            service.approve_request(request.request_id)
            created.append(request)
            reference_id = f"shot-{index}"

        service.update_session_settings(session.session_id, target_shot_count=5)
        replaced, invalidated, restored = PhotoshootManualService(
            queue=service,
            engine=SimpleNamespace(),
            library=SimpleNamespace(),
            summary_service=PhotoshootSummaryService(queue=service),
        ).replace_shot(
            creator_profile_id=session.creator_profile_id,
            session_id=session.session_id,
            request_id=created[1].request_id,
        )
        planning = PhotoshootCreativeDirectorWorkflowService(
            queue=service, library=SimpleNamespace(), creative_director=SimpleNamespace(), summary_service=SimpleNamespace(),
        )._planning_progress(restored)

        self.assertEqual(replaced.status, "replacement_pending")
        self.assertEqual(tuple(item.request_id for item in invalidated), (created[2].request_id,))
        self.assertEqual(service.get_request(created[2].request_id).status, "continuity_invalidated")
        self.assertEqual(restored.creative_continuity["current_shot_image_id"], "shot-2")
        self.assertEqual(restored.creative_continuity["replacement_sequence_index"], 3)
        self.assertEqual(restored.target_shot_count, 5)
        self.assertEqual(restored.creative_continuity["current_prompt"], "")
        self.assertEqual(restored.creative_continuity["current_direction"], {})
        self.assertEqual(restored.creative_continuity["inspiration_ideas"], [])
        self.assertEqual(restored.creative_continuity["selected_inspiration"], "")
        self.assertEqual(restored.creative_continuity["inspiration_planning_shot"], 0)
        self.assertEqual(restored.creative_continuity["workflow_stage"], "ready_for_next_shot")
        self.assertFalse(restored.creative_continuity["direction_approved"])
        self.assertEqual(restored.creative_continuity["approved_prompts"], ["Seed image prompt", "Shot 2 prompt"])
        self.assertEqual(len(restored.creative_continuity["approved_directions"]), 1)
        self.assertEqual(restored.creative_continuity["photoshoot_summary"]["approved_shot_count"], 2)
        self.assertNotIn("Shot 3", restored.creative_continuity["photoshoot_summary"]["summary_text"])
        self.assertEqual(planning, {"current_shot": 2, "planning_shot": 3, "target_shot_count": 5, "remaining_shots": 3, "editorial_stage": "Middle"})

    def test_frame_by_frame_editorial_stage_uses_approved_request_positions(self):
        service = self.make_service()
        session, _created = service.start_studio_session_from_generated_image(generated_record())
        session = service.update_session_settings(session.session_id, target_shot_count=5)
        workflow = PhotoshootCreativeDirectorWorkflowService(
            queue=service, library=SimpleNamespace(), creative_director=SimpleNamespace(), summary_service=SimpleNamespace(),
        )
        self.assertEqual(workflow._planning_progress(session)["editorial_stage"], "Beginning")
        for index, expected in ((2, "Middle"), (3, "Late"), (4, "Finale")):
            request = service.add_studio_shot_request(
                session_id=session.session_id, prompt_text=f"Shot {index}", shot_direction=f"Direction {index}",
            )
            service._replace_request(replace(request, status="awaiting_review", metadata={
                **dict(request.metadata or {}), "generated_image_ids": (f"missing-media-{index}",),
            }))
            service.approve_request(request.request_id)
            progress = workflow._planning_progress(service.get_session(session.session_id))
            self.assertEqual(progress["planning_shot"], index + 1)
            self.assertEqual(progress["editorial_stage"], expected)

    def test_creative_director_progress_uses_timeline_approved_ordinals(self):
        service = self.make_service()
        session, _created = service.start_studio_session_from_generated_image(generated_record())
        rejected = service.add_studio_shot_request(
            session_id=session.session_id, prompt_text="Rejected attempt", shot_direction="Attempt",
        )
        service._replace_request(replace(rejected, status="rejected", review_status="rejected"))
        approved = service.add_studio_shot_request(
            session_id=session.session_id, prompt_text="Approved next shot", shot_direction="Next shot",
        )
        service._replace_request(replace(approved, status="awaiting_review", metadata={
            **dict(approved.metadata or {}), "generated_image_ids": ("approved-after-rejection",),
        }))
        service.approve_request(approved.request_id)
        session = service.update_session_settings(session.session_id, target_shot_count=5)
        workflow = PhotoshootCreativeDirectorWorkflowService(
            queue=service, library=SimpleNamespace(), creative_director=SimpleNamespace(), summary_service=SimpleNamespace(),
        )

        progress = workflow._planning_progress(session)

        self.assertEqual(approved.sequence_index, 3)
        self.assertEqual(progress, {
            "current_shot": 2,
            "planning_shot": 3,
            "target_shot_count": 5,
            "remaining_shots": 3,
            "editorial_stage": "Middle",
        })

    def test_latest_approved_shot_is_structured_continuity_contract(self):
        service = self.make_service()
        session, _created = service.start_studio_session_from_generated_image(generated_record())
        request = service.add_studio_shot_request(
            session_id=session.session_id,
            prompt_text="Warm bedroom, black lingerie, seated three-quarter pose.",
            shot_direction="Remain seated and turn slightly toward camera.",
            creative_direction={
                "title": "Seated turn",
                "creative_direction": "Remain seated and turn slightly toward camera.",
                "pose_composition": "Seated, torso three-quarter right, left hand on thigh.",
                "emotion": "Soft confident smile.",
                "camera_framing": "Eye-level medium shot.",
                "lighting": "Warm window light.",
            },
        )
        service._replace_request(replace(request, status="awaiting_review", metadata={
            **dict(request.metadata or {}), "generated_image_ids": ("latest-shot",),
        }))
        service.approve_request(request.request_id)
        session = service.get_session(session.session_id)
        workflow = PhotoshootCreativeDirectorWorkflowService(
            queue=service, library=SimpleNamespace(), creative_director=SimpleNamespace(), summary_service=SimpleNamespace(),
        )
        latest = workflow._latest_approved_shot_summary(session, {
            "overall_theme": "Intimate bedroom editorial",
            "current_location": "bedroom",
            "current_wardrobe": "black lingerie",
            "lighting": "warm window light",
            "visual_style": "intimate medium portrait",
        })

        self.assertEqual(set(latest), {
            "environment", "location", "wardrobe", "clothing_state", "pose", "body_orientation",
            "hand_placement", "facial_expression", "camera_angle", "framing", "lighting", "progression_stage",
        })
        self.assertEqual(latest["location"], "bedroom")
        self.assertEqual(latest["clothing_state"], "black lingerie")
        self.assertIn("left hand on thigh", latest["hand_placement"].lower())
        context = workflow._ai_context("original", {}, "", latest_approved_shot=latest)
        prompt = CreativeDirectorService._build_photoshoot_creative_director_prompt(
            session_context=context, approved_history=(), creative_mode="premium",
            session_direction="", creative_hint="", continuity_locks={},
        )
        self.assertIn('"latest_approved_shot"', prompt)
        self.assertIn('"body_orientation"', prompt)
        self.assertIn("Never begin a new composition, wardrobe, location, or camera setup", prompt)
        self.assertIn("Target shot count is advisory only", prompt)

    def test_pending_recommendation_persists_without_approved_history(self):
        service = self.make_service()
        seed = generated_record()
        session, _created = service.start_studio_session_from_generated_image(seed)

        updated = service.record_pending_recommendation(
            session_id=session.session_id,
            recommendation={
                "title": "Mirror pose",
                "creative_direction": "Turn toward the mirror while preserving continuity.",
                "reasoning": "Adds variety without changing the room.",
            },
        )
        restarted = PhotoshootQueueService(
            storage_dir=service.storage_dir,
            generation_ingestion_service=FakeIngestion(),
            asset_repository=FakeAssetRepository(),
        )
        restored = restarted.get_session(session.session_id)

        self.assertEqual(updated.creative_continuity["workflow_stage"], "recommendation_ready")
        self.assertEqual(restored.creative_continuity["current_direction"]["title"], "Mirror pose")
        self.assertEqual(restored.creative_continuity["current_prompt"], "")
        self.assertFalse(restored.creative_continuity["direction_approved"])
        self.assertEqual(tuple(restored.creative_continuity["approved_directions"]), ())

    def test_studio_session_uses_one_canonical_seed_prompt_field(self):
        service = self.make_service()
        seed = generated_record()

        session, created = service.start_studio_session_from_generated_image(seed)

        self.assertTrue(created)
        self.assertEqual(session.creative_continuity["seed_prompt_text"], seed.prompt_text)
        self.assertNotIn("original_photoshoot_direction", session.creative_continuity)
        summary = session.creative_continuity["canonical_seed_summary"]
        self.assertTrue(summary["scene"])
        self.assertNotIn("PROVIDER OPTIMIZATION", summary["scene"])

    def test_another_idea_clears_pending_recommendation_until_new_recommendation_returns(self):
        service = self.make_service()
        seed = generated_record()
        session, _created = service.start_studio_session_from_generated_image(seed)
        ready = service.record_pending_recommendation(
            session_id=session.session_id,
            recommendation={
                "title": "Window idea",
                "creative_direction": "Move toward the window while preserving continuity.",
            },
        )

        cleared = service.clear_workspace_state(session.session_id, workflow_stage="ready_for_direction")
        refreshed = service.record_pending_recommendation(
            session_id=session.session_id,
            recommendation={
                "title": "Bedside idea",
                "creative_direction": "Shift to the bedside with the same outfit and lighting.",
            },
        )

        self.assertEqual(ready.creative_continuity["workflow_stage"], "recommendation_ready")
        self.assertEqual(cleared.creative_continuity["workflow_stage"], "ready_for_direction")
        self.assertEqual(cleared.creative_continuity["current_direction"], {})
        self.assertFalse(cleared.creative_continuity["direction_approved"])
        self.assertEqual(refreshed.creative_continuity["workflow_stage"], "recommendation_ready")
        self.assertEqual(refreshed.creative_continuity["current_direction"]["title"], "Bedside idea")

    def test_approve_and_generate_service_flow_is_idempotent(self):
        service = self.make_service()
        engine = self.make_engine()
        seed = generated_record()
        session, _created = service.start_studio_session_from_generated_image(seed)
        recommendation = {
            "title": "Window turn",
            "creative_direction": "Turn toward the window with stronger eye contact.",
        }

        approved_direction = service.record_creative_direction(
            session_id=session.session_id,
            recommendation=recommendation,
            final_prompt="canonical approved prompt",
        )
        first_request = service.add_studio_shot_request(
            session_id=session.session_id,
            prompt_text="canonical approved prompt",
            shot_direction="Turn toward the window with stronger eye contact.",
            provider_id="seedream_5_0_pro",
            active_reference_image_id=seed.image_id,
            active_reference_output_reference=seed.output_reference,
            creative_direction=approved_direction.creative_continuity["current_direction"],
        )
        duplicate_request = service.add_studio_shot_request(
            session_id=session.session_id,
            prompt_text="canonical approved prompt",
            shot_direction="Turn toward the window with stronger eye contact.",
            provider_id="seedream_5_0_pro",
            active_reference_image_id=seed.image_id,
            active_reference_output_reference=seed.output_reference,
            creative_direction=approved_direction.creative_continuity["current_direction"],
        )
        job = service.queue_next_prompt(session_id=session.session_id, generation_engine=engine)
        duplicate_job = service.queue_next_prompt(session_id=session.session_id, generation_engine=engine)
        generating_session = service.get_session(session.session_id)

        self.assertEqual(first_request.request_id, duplicate_request.request_id)
        self.assertIsNotNone(job)
        self.assertIsNone(duplicate_job)
        self.assertEqual(generating_session.creative_continuity["workflow_stage"], "generating")
        self.assertEqual(len(tuple(request for request in service.requests_for_session(session.session_id) if request.status == "generating")), 1)

    def test_generation_failure_preserves_prompt_and_reenables_recommendation(self):
        service = self.make_service()
        engine = self.make_engine()
        seed = generated_record()
        session, _created = service.start_studio_session_from_generated_image(seed)
        recommendation = {
            "title": "Window turn",
            "creative_direction": "Turn toward the window with stronger eye contact.",
        }
        approved_direction = service.record_creative_direction(
            session_id=session.session_id,
            recommendation=recommendation,
            final_prompt="canonical approved prompt",
        )
        service.add_studio_shot_request(
            session_id=session.session_id,
            prompt_text="canonical approved prompt",
            shot_direction="Turn toward the window with stronger eye contact.",
            provider_id="seedream_5_0_pro",
            active_reference_image_id=seed.image_id,
            active_reference_output_reference=seed.output_reference,
            creative_direction=approved_direction.creative_continuity["current_direction"],
        )
        job = service.queue_next_prompt(session_id=session.session_id, generation_engine=engine)

        failed = service.mark_generation_failed(job.job_id, reason="Provider failed")
        restored = service.get_session(session.session_id)

        self.assertEqual(failed.status, "queued")
        self.assertEqual(restored.creative_continuity["workflow_stage"], "recommendation_ready")
        self.assertEqual(restored.creative_continuity["current_prompt"], "canonical approved prompt")
        self.assertEqual(restored.creative_continuity["current_direction"]["title"], "Window turn")
        self.assertFalse(restored.creative_continuity["direction_approved"])

    def test_photoshoot_session_settings_restore_after_restart(self):
        service = self.make_service()
        seed = generated_record()
        session, _created = service.start_studio_session_from_generated_image(seed)

        updated = service.update_session_settings(
            session.session_id,
            provider_id="wan_2_7_image_edit",
            creative_mode="explicit",
            continuity_locks={
                "location": True,
                "wardrobe": False,
                "lighting": True,
                "hairstyle": True,
                "makeup": True,
                "camera_style": True,
            },
            selected_timeline_index=6,
            workflow_stage="ready_for_next_shot",
        )
        restarted = PhotoshootQueueService(
            storage_dir=service.storage_dir,
            generation_ingestion_service=FakeIngestion(),
            asset_repository=FakeAssetRepository(),
        )
        restored = restarted.current_session(creator_profile_id=7)

        self.assertEqual(updated.provider_id, "wan_2_7_image_edit")
        self.assertEqual(restored.session_id, session.session_id)
        self.assertEqual(restored.provider_id, "wan_2_7_image_edit")
        self.assertEqual(restored.creative_mode, "explicit")
        self.assertFalse(restored.creative_continuity["continuity_locks"]["wardrobe"])
        self.assertEqual(restored.creative_continuity["selected_timeline_index"], 6)
        self.assertEqual(restored.creative_continuity["workflow_stage"], "ready_for_next_shot")

    def test_current_session_restores_most_recent_incomplete_session(self):
        service = self.make_service()
        first, _ = service.start_studio_session_from_generated_image(generated_record("seed_first"))
        second, _ = service.start_studio_session_from_generated_image(generated_record("seed_second"))
        service.update_session_settings(first.session_id, workflow_stage="older")
        latest = service.update_session_settings(second.session_id, workflow_stage="newer")

        restored = service.current_session(creator_profile_id=7)

        self.assertEqual(restored.session_id, latest.session_id)

    def test_candidate_review_stage_restores_after_restart(self):
        service = self.make_service()
        seed = generated_record()
        session, _created = service.start_studio_session_from_generated_image(seed)
        request = service.add_studio_shot_request(
            session_id=session.session_id,
            prompt_text="candidate prompt",
            shot_direction="candidate direction",
            provider_id="seedream_5_0_pro",
            active_reference_image_id=seed.image_id,
            active_reference_output_reference=seed.output_reference,
        )
        service._replace_request(
            replace(
                request,
                status="awaiting_review",
                metadata={
                    **dict(request.metadata or {}),
                    "generated_image_ids": ("candidate_image",),
                },
            )
        )
        service.update_session_settings(session.session_id, workflow_stage="review_candidate")
        restarted = PhotoshootQueueService(
            storage_dir=service.storage_dir,
            generation_ingestion_service=FakeIngestion(),
            asset_repository=FakeAssetRepository(),
        )

        restored_session = restarted.current_session(creator_profile_id=7)
        restored_candidate = next(
            request
            for request in reversed(restarted.requests_for_session(restored_session.session_id))
            if request.status == "awaiting_review"
        )

        self.assertEqual(restored_session.creative_continuity["workflow_stage"], "review_candidate")
        self.assertEqual(tuple(restored_candidate.metadata["generated_image_ids"]), ("candidate_image",))

    def test_photoshoot_junk_preserves_metadata_and_removes_from_timeline(self):
        queue = self.make_service()
        library = self.make_generation_library()
        seed = generated_record()
        session, _created = queue.start_studio_session_from_generated_image(seed)
        request = queue.add_studio_shot_request(
            session_id=session.session_id,
            prompt_text="approved prompt",
            shot_direction="approved direction",
            provider_id="seedream_5_0_pro",
            active_reference_image_id=seed.image_id,
            active_reference_output_reference=seed.output_reference,
            creative_direction={"title": "Approved direction"},
        )
        queue._replace_request(
            replace(
                request,
                status="approved",
                review_status="approved",
                metadata={
                    **dict(request.metadata or {}),
                    "generated_image_ids": ("generated_image_junk_me",),
                },
            )
        )
        request = queue.get_request(request.request_id)
        image_path = Path(library.storage_dir) / "generated_image_junk_me.png"
        image_path.write_bytes(b"fake image")
        library._write_records(
            [
                generated_record("generated_image_junk_me").__class__(
                    **{
                        **generated_record("generated_image_junk_me").__dict__,
                        "output_reference": str(image_path),
                        "status": "photoshoot_session",
                        "photoshoot_session_id": session.session_id,
                        "photoshoot_request_id": request.request_id,
                        "generation_metadata": {"creative_direction": {"title": "Approved direction"}},
                    }
                )
            ]
        )

        action = library.move_photoshoot_records_to_junk(
            ("generated_image_junk_me",),
            session_id=session.session_id,
            session_title="Hotel Bedroom Session",
        )
        junked = queue.junk_request(request.request_id)
        junk_record = library.get("generated_image_junk_me")
        junk_path = Path(junk_record.output_reference)

        self.assertTrue(action.success)
        self.assertEqual(junked.status, "junked")
        self.assertEqual(junk_record.status, "photoshoot_junk")
        self.assertIn("Generation", junk_path.parts)
        self.assertIn("Photoshoot", junk_path.parts)
        self.assertIn("Junk", junk_path.parts)
        self.assertEqual(junk_path.parent.name, "Hotel Bedroom Session")
        self.assertTrue(junk_path.exists())
        self.assertFalse(library.browse().records)
        self.assertEqual(junk_record.generation_metadata["photoshoot_session_id"], session.session_id)
        self.assertEqual(junk_record.generation_metadata["photoshoot_junk_reason"], "photoshoot_junk")

    def test_photoshoot_storage_approves_rejects_and_completes_session_folders(self):
        library = self.make_generation_library()
        session_id = "photoshoot_session_storage"
        session_title = "Hotel Bedroom Session"
        active_source = library.archive_service.content_paths()["generation_active"]
        active_source.mkdir(parents=True, exist_ok=True)
        candidate_path = active_source / "candidate.png"
        rejected_path = active_source / "rejected.png"
        candidate_path.write_bytes(b"approved image")
        rejected_path.write_bytes(b"rejected image")
        approved_record = replace(
            generated_record("generated_image_approved"),
            output_reference=str(candidate_path),
            photoshoot_session_id=session_id,
            photoshoot_request_id="photoshoot_request_approved",
            generation_metadata={"creative_direction": {"title": "Approved direction"}},
        )
        rejected_record = replace(
            generated_record("generated_image_rejected"),
            output_reference=str(rejected_path),
            photoshoot_session_id=session_id,
            photoshoot_request_id="photoshoot_request_rejected",
            generation_metadata={"creative_direction": {"title": "Rejected direction"}},
        )
        library._write_records([approved_record, rejected_record])

        isolated = library.mark_photoshoot_session_records(
            (approved_record.image_id, rejected_record.image_id),
            session_id=session_id,
            session_title=session_title,
        )
        self.assertTrue(isolated.success)
        self.assertFalse(candidate_path.exists())
        self.assertFalse(rejected_path.exists())
        for image_id in (approved_record.image_id, rejected_record.image_id):
            isolated_record = library.get(image_id)
            isolated_path = Path(isolated_record.output_reference)
            self.assertIn("Generation", isolated_path.parts)
            self.assertIn("Photoshoot", isolated_path.parts)
            self.assertIn("Active", isolated_path.parts)
            self.assertEqual(isolated_path.parent.name, session_title)
            self.assertTrue(isolated_path.exists())
        self.assertFalse(library.browse().records)

        approved = library.approve_photoshoot_records(
            (approved_record.image_id,),
            session_id=session_id,
            session_title=session_title,
        )
        approved_after = library.get(approved_record.image_id)
        approved_path = Path(approved_after.output_reference)
        self.assertTrue(approved.success)
        self.assertEqual(approved_after.review_state, "photoshoot_approved")
        self.assertEqual(approved_after.generation_metadata["photoshoot_shot_number"], 1)
        self.assertEqual(approved_path.name, "Shot_001.png")
        self.assertTrue(approved_path.exists())
        self.assertTrue(approved_path.with_suffix(".json").exists())
        self.assertNotIn("Generation\\Active", str(approved_path))

        rejected = library.move_photoshoot_records_to_junk(
            (rejected_record.image_id,),
            session_id=session_id,
            session_title=session_title,
            reason="photoshoot_rejected",
        )
        rejected_after = library.get(rejected_record.image_id)
        rejected_after_path = Path(rejected_after.output_reference)
        self.assertTrue(rejected.success)
        self.assertEqual(rejected_after.status, "photoshoot_junk")
        self.assertIn("Junk", rejected_after_path.parts)
        self.assertEqual(rejected_after_path.parent.name, session_title)
        self.assertTrue(rejected_after_path.exists())

        completed = library.finish_photoshoot_session(
            session_id=session_id,
            approved_image_ids=(approved_record.image_id,),
            session_title=session_title,
        )
        completed_after = library.get(approved_record.image_id)
        completed_path = Path(completed_after.output_reference)
        self.assertTrue(completed.success)
        self.assertEqual(completed_after.status, "photoshoot_completed")
        self.assertIn("Gallery", completed_path.parts)
        self.assertEqual(completed_path.parent.name, session_title)
        self.assertTrue(completed_path.exists())
        self.assertTrue((completed_path.parent / "session.json").exists())
        self.assertFalse((library.photoshoot_root / "Active" / session_title).exists())
        self.assertFalse(library.browse().records)

        junked_completed = library.move_completed_photoshoot_session_to_junk(
            session_id=session_id,
            approved_image_ids=(approved_record.image_id,),
            session_title=session_title,
        )
        junked_completed_after = library.get(approved_record.image_id)
        junked_completed_path = Path(junked_completed_after.output_reference)
        self.assertTrue(junked_completed.success)
        self.assertEqual(junked_completed_after.status, "photoshoot_junk")
        self.assertIn("Junk", junked_completed_path.parts)
        self.assertEqual(junked_completed_path.parent.name, session_title)
        self.assertTrue(junked_completed_path.exists())
        self.assertTrue((junked_completed_path.parent / "session.json").exists())
        self.assertFalse(completed_path.parent.exists())
        self.assertEqual(
            junked_completed_after.generation_metadata["photoshoot_junk_reason"],
            "completed_session_junk",
        )

    def test_completed_photoshoot_session_can_be_marked_junked(self):
        service = self.make_service()
        session = service.create_session(
            creator_profile_id=7,
            title="Completed Session",
            prompt_plans=(prompt_plan("plan_complete"),),
        )
        completed = service.finish_session(session.session_id)

        junked = service.junk_completed_session(completed.session_id, notes="Gallery cleanup.")

        self.assertEqual(junked.status, "junked")
        self.assertEqual(junked.metadata["junk_notes"], "Gallery cleanup.")
        self.assertTrue(junked.metadata["junked_at"])
        self.assertEqual(
            tuple(item.session_id for item in service.list_sessions() if item.status == "completed"),
            (),
        )
        self.assertIsNone(service.current_session(creator_profile_id=7))

    def test_content_studio_integration(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(
            encoding="utf-8"
        )
        photoshoot_source = source.split("def _render_photoshoot_queue(", 1)[1].split(
            "def _render_placeholder_lanes",
            1,
        )[0]

        self.assertIn("PhotoshootQueueService", source)
        self.assertIn("Photoshoot Studio", photoshoot_source)
        timeline_source = source.split("def _render_photoshoot_timeline(", 1)[1].split(
            "def _render_photoshoot_preview_image",
            1,
        )[0]
        self.assertNotIn("### Seed Image", photoshoot_source)
        self.assertIn("Photoshoot Timeline", photoshoot_source)
        self.assertIn("📷 Shot", source)
        self.assertNotIn("⭐ Seed", photoshoot_source)
        self.assertNotIn("_render_photoshoot_filmstrip(", photoshoot_source)
        self.assertNotIn("photoshoot_studio_selected_photo_", photoshoot_source)
        self.assertNotIn("Current Reference", photoshoot_source)
        self.assertIn("selected_record = timeline_items[-1][1] if timeline_items else seed_record", photoshoot_source)
        self.assertIn("if request.status != \"approved\":", source)
        self.assertIn("shot_number += 1", source)
        self.assertIn("Starting Image", source)
        self.assertIn("★ Active", source)
        self.assertIn("overflow-x: auto", source)
        self.assertIn("overflow-y: hidden", source)
        self.assertIn("display: flex", source)
        self.assertIn("flex-wrap: nowrap", source)
        self.assertIn("flex: 0 0 auto", source)
        self.assertIn("width: 168px", source)
        self.assertIn("def _render_photoshoot_shot_preview(", source)
        self.assertIn("def _render_photoshoot_preview_image(", source)
        self.assertIn("preview_key = f\"photoshoot_timeline_preview_{current.session_id}\"", photoshoot_source)
        self.assertIn("selected_index_key = f\"{preview_key}_selected_index\"", photoshoot_source)
        self.assertIn("if st.session_state.get(reset_fields_key):", photoshoot_source)
        self.assertIn("latest_index = max(0, len(timeline_items) - 1)", photoshoot_source)
        self.assertIn("st.session_state[selected_index_key] = latest_index", photoshoot_source)
        self.assertIn("selected_timeline_index=latest_index", photoshoot_source)
        self.assertLess(
            photoshoot_source.index("st.session_state[selected_index_key] = latest_index"),
            photoshoot_source.index("_render_photoshoot_timeline(timeline_items, horizontal=True, preview_key=preview_key)"),
        )
        self.assertIn("_render_photoshoot_timeline(timeline_items, horizontal=True, preview_key=preview_key)", photoshoot_source)
        self.assertIn("_render_photoshoot_shot_preview(", photoshoot_source)
        self.assertIn("👁 Preview", source)
        self.assertNotIn("👁 Preview Selected Shot", source)
        self.assertIn("selected_key = f\"{preview_key}_selected_index\"", source)
        self.assertNotIn("key=f\"{preview_key}_select_{index}\"", source)
        self.assertNotIn("type=button_type", timeline_source)
        self.assertIn("key=f\"{preview_key}_button\"", source)
        self.assertNotIn("key=f\"{preview_key}_button_{index}\"", source)
        self.assertNotIn("def _consume_photoshoot_preview_query(", source)
        self.assertNotIn("def _clear_photoshoot_preview_query(", source)
        self.assertNotIn("photoshoot_preview_key", source)
        self.assertNotIn("target=\"_parent\"", source)
        self.assertIn("max-width: 85%", source)
        self.assertIn("max-height: 410px", source)
        self.assertIn("height=455", source)
        self.assertIn('@dialog("Photoshoot Preview")', source)
        self.assertNotIn('dialog("Photoshoot Preview", width="large")', source)
        self.assertIn("◀ Previous", source)
        self.assertIn("Next ▶", source)
        self.assertIn("✕ Close", source)
        self.assertIn("📤 Return to Generation Library", source)
        self.assertIn("return_seed_request_to_library", source)
        self.assertIn("This will end the current Photoshoot because the seed image is being removed.", source)
        self.assertIn("The seed image is being removed.", source)
        self.assertIn("🗑 Delete", source)
        self.assertNotIn("🗑 Move to Photoshoot Junk", source)
        self.assertIn("move_photoshoot_records_to_junk", source)
        self.assertIn("photoshoot_queue.junk_request", source)
        self.assertIn("Photoshoot Preview", source)
        preview_source = source.split("def _render_photoshoot_shot_preview(", 1)[1].split(
            "def _photoshoot_candidate_request",
            1,
        )[0]
        self.assertNotIn("Renderer:", preview_source)
        self.assertNotIn("Creative Mode:", preview_source)
        self.assertNotIn("Canonical Prompt", preview_source)
        self.assertNotIn("Generation Settings", preview_source)
        self.assertNotIn("Reasoning:", preview_source)
        self.assertNotIn("Continuity Notes:", preview_source)
        self.assertIn("_render_edit_studio_image(", photoshoot_source)
        self.assertIn("Creative Direction", photoshoot_source)
        self.assertIn("Direction Mode", photoshoot_source)
        self.assertIn("🎬 Shot Director", photoshoot_source)
        self.assertIn("Session Direction (Optional)", photoshoot_source)
        self.assertIn("Creative Hint (Optional)", photoshoot_source)
        self.assertIn("Selected Grok idea or manual direction for Shot Director / generate...", photoshoot_source)
        self.assertIn("Ask Grok Guidance (Optional)", photoshoot_source)
        self.assertIn("photoshoot_creative_hint_", photoshoot_source)
        self.assertIn("creative_hint=creative_hint", photoshoot_source)
        self.assertIn("direction_approved_key", photoshoot_source)
        self.assertIn("current_prompt", photoshoot_source)
        self.assertIn("current_direction", photoshoot_source)
        self.assertIn("Creative Mode", photoshoot_source)
        self.assertIn("persisted_creative_mode", photoshoot_source)
        self.assertIn("st.session_state[creative_mode_key] = mode_options", photoshoot_source)
        self.assertIn("Continuity", photoshoot_source)
        self.assertIn("Keep location", photoshoot_source)
        self.assertIn("persisted_locks = dict(continuity.get(\"continuity_locks\") or {})", photoshoot_source)
        self.assertIn("st.session_state[widget_key] = bool(persisted_locks.get(lock_key, True))", photoshoot_source)
        self.assertIn("photoshoot_queue.update_session_settings", photoshoot_source)
        self.assertIn("provider_id=selected_provider", photoshoot_source)
        self.assertIn("creative_mode=creative_mode", photoshoot_source)
        self.assertIn("continuity_locks=continuity_locks", photoshoot_source)
        self.assertIn("📸 Resumed Photoshoot", photoshoot_source)
        self.assertIn("💡 Ask Grok", photoshoot_source)
        self.assertIn("🎬 Shot Director", photoshoot_source)
        self.assertIn("suggest_photoshoot_inspiration", photoshoot_source)
        self.assertIn("provider_context=provider_labels.get(selected_provider, selected_provider)", photoshoot_source)
        self.assertNotIn("Use as Creative Hint", photoshoot_source)
        self.assertIn("apply_selected_grok_idea_to_hint", photoshoot_source)
        self.assertIn("on_change=apply_selected_grok_idea_to_hint", photoshoot_source)
        self.assertIn("st.session_state[pending_creative_hint_key] = str(grok_ideas[0] or \"\").strip()", photoshoot_source)
        self.assertIn("Grok Ideas", photoshoot_source)
        self.assertIn("idea_count=8", photoshoot_source)
        self.assertIn("timeline_images=timeline_images", photoshoot_source)
        self.assertIn("Next scene options", photoshoot_source)
        self.assertNotIn("✅ Approve Direction", photoshoot_source)
        self.assertIn("🚀 Approve & Generate", photoshoot_source)
        self.assertIn("_valid_photoshoot_recommendation", photoshoot_source)
        self.assertIn("def _photoshoot_approve_generate_disabled(", source)
        approve_block = photoshoot_source.split('approve_direction_col.button(', 1)[1].split(
            'key=f"photoshoot_approve_direction_',
            1,
        )[0]
        self.assertIn("_photoshoot_approve_generate_disabled(", approve_block)
        self.assertIn("recommendation_ready=recommendation_ready", approve_block)
        self.assertIn("direction_approved=direction_approved", approve_block)
        self.assertIn("candidate_request_present=candidate_request is not None", approve_block)
        self.assertNotIn('direction_mode != "🎬 Shot Director"', approve_block)
        self.assertIn("if recommendation_ready", photoshoot_source)
        self.assertIn("Another Idea", photoshoot_source)
        self.assertIn("🔄 Another Idea", photoshoot_source)
        self.assertIn("another_idea_col, approve_direction_col = st.columns(2)", photoshoot_source)
        self.assertIn("approve_direction_clicked", photoshoot_source)
        self.assertNotIn("🪄 Generate Prompt", photoshoot_source)
        self.assertNotIn("photoshoot_generate_prompt_", photoshoot_source)
        self.assertNotIn("prompt_col.button", photoshoot_source)
        self.assertIn("Generated Prompt", photoshoot_source)
        self.assertIn("_build_photoshoot_prompt(", photoshoot_source)
        self.assertIn("creative_director.plan_prompts", source)
        self.assertIn("record_creative_direction", photoshoot_source)
        self.assertIn("record_pending_recommendation", photoshoot_source)
        self.assertIn("execute_photoshoot_next_to_library", photoshoot_source)
        self.assertIn("Generate Shot", photoshoot_source)
        self.assertIn('if direction_mode == "🎬 Shot Director":', photoshoot_source)
        self.assertIn("disabled=not str(prompt_text).strip() or active_candidate or generation_running", photoshoot_source)
        self.assertIn("Review Candidate", photoshoot_source)
        self.assertIn("Approve Shot", photoshoot_source)
        self.assertIn("Reject Shot", photoshoot_source)
        self.assertIn("Regenerate", photoshoot_source)
        self.assertIn("Complete Photoshoot", photoshoot_source)
        self.assertIn("Photoshoot Gallery", source)
        gallery_source = source.split("def _render_photoshoot_gallery(", 1)[1].split(
            "def _render_placeholder_lanes",
            1,
        )[0]
        gallery_card_source = source.split("def _render_photoshoot_gallery_session_card(", 1)[1].split(
            "def _photoshoot_fanvue_upload_metadata",
            1,
        )[0]
        gallery_publish_prototype_source = source.split("def _render_photoshoot_gallery_publish_prototype(", 1)[1].split(
            "def _photoshoot_fanvue_upload_metadata",
            1,
        )[0]
        gallery_publish_dialog_source = source.split("def _render_photoshoot_gallery_publish_dialog(", 1)[1].split(
            "def _render_photoshoot_gallery_publish_prototype",
            1,
        )[0]
        gallery_delete_prototype_source = source.split("def _render_photoshoot_gallery_delete_prototype(", 1)[1].split(
            "def _photoshoot_fanvue_upload_metadata",
            1,
        )[0]
        gallery_delete_dialog_source = source.split("def _render_photoshoot_gallery_delete_dialog(", 1)[1].split(
            "def _render_photoshoot_gallery_publish_prototype",
            1,
        )[0]
        gallery_contact_sheet_source = source.split("def _render_photoshoot_gallery_contact_sheet(", 1)[1].split(
            "def _render_photoshoot_gallery(",
            1,
        )[0]
        self.assertIn("_render_photoshoot_gallery_session_card(", gallery_source)
        self.assertIn('st.columns([0.55, 20, 0.55], gap="small")', gallery_card_source)
        self.assertIn("_render_photoshoot_gallery_contact_sheet(timeline_items)", gallery_card_source)
        self.assertIn("_render_photoshoot_gallery_publish_prototype(", gallery_card_source)
        self.assertIn("active_account=active_account", gallery_card_source)
        self.assertIn("_render_photoshoot_gallery_delete_prototype(", gallery_card_source)
        self.assertNotIn("_render_photoshoot_fanvue_upload_action(", gallery_card_source)
        self.assertIn('photoshoot_gallery_destination_{session.session_id}', gallery_publish_prototype_source)
        self.assertIn('st.button(\n        "📤"', gallery_publish_prototype_source)
        self.assertIn('help="Publish this completed photoshoot"', gallery_publish_prototype_source)
        self.assertIn("_render_gallery_icon_button_style(button_key)", gallery_publish_prototype_source)
        self.assertIn("_render_gallery_icon_button_style(button_key)", gallery_delete_prototype_source)
        self.assertIn('st.button(\n        "🗑"', gallery_delete_prototype_source)
        self.assertIn('help="Move this completed photoshoot to Junk"', gallery_delete_prototype_source)
        self.assertIn('@st.dialog("Delete Photoshoot?")', source)
        self.assertIn("Move this completed photoshoot to the Junk folder?", gallery_delete_dialog_source)
        self.assertIn("Move to Junk", gallery_delete_dialog_source)
        self.assertIn("move_completed_photoshoot_session_to_junk", gallery_delete_dialog_source)
        self.assertIn("photoshoot_queue.junk_completed_session", gallery_delete_dialog_source)
        self.assertIn('height:36px', gallery_publish_prototype_source)
        self.assertIn("min-height:112px", gallery_publish_prototype_source)
        self.assertIn('status_icon = "🟢"', gallery_publish_prototype_source)
        self.assertIn("Assigned to Wall", gallery_publish_prototype_source)
        self.assertIn("Assigned to Chat", gallery_publish_prototype_source)
        self.assertNotIn("📤 Publish", gallery_publish_prototype_source)
        self.assertNotIn("🟢 Wall", gallery_publish_prototype_source)
        self.assertNotIn("🔵 Chat", gallery_publish_prototype_source)
        self.assertIn("🟢 Wall", gallery_publish_dialog_source)
        self.assertIn("🔵 Chat", gallery_publish_dialog_source)
        self.assertIn("FANVUE_WALL_FOLDER", gallery_publish_dialog_source)
        self.assertIn("PhotoshootFanvueUploadService(folder_name=FANVUE_WALL_FOLDER)", gallery_publish_dialog_source)
        self.assertIn("service.upload_completed_session(", gallery_publish_dialog_source)
        self.assertIn("reuse_existing_upload_metadata=False", gallery_publish_dialog_source)
        self.assertIn("_photoshoot_gallery_wall_upload_records(timeline_items)", gallery_publish_dialog_source)
        self.assertIn("_fanvue_account_oauth_connected(active_account)", gallery_publish_dialog_source)
        self.assertIn("Fanvue OAuth is not connected for the selected account.", gallery_publish_dialog_source)
        self.assertIn("Chat publishing is not implemented yet.", gallery_publish_dialog_source)
        self.assertIn("Fanvue accepted the upload but did not finish processing the media. Please try again.", gallery_publish_dialog_source)
        self.assertIn("Wall upload did not complete.", gallery_publish_dialog_source)
        self.assertIn('@st.dialog("Publish Destination")', source)
        self.assertIn("Cancel", gallery_publish_dialog_source)
        self.assertIn("_render_photoshoot_gallery_publish_dialog(", gallery_publish_prototype_source)
        self.assertIn("def _photoshoot_gallery_wall_upload_records", source)
        self.assertNotIn('if not bool((request.metadata or {}).get("is_seed_image"))', gallery_publish_dialog_source)
        self.assertNotIn("PhotoshootFanvueUploadService", gallery_publish_prototype_source)
        self.assertNotIn("record_fanvue_upload_result", gallery_publish_prototype_source)
        self.assertNotIn("record_fanvue_upload_result", gallery_publish_dialog_source)
        self.assertNotIn("PhotoshootFanvueUploadService", gallery_delete_prototype_source)
        self.assertNotIn("record_fanvue_upload_result", gallery_delete_prototype_source)
        self.assertNotIn("PhotoshootFanvueUploadService", gallery_delete_dialog_source)
        self.assertNotIn("record_fanvue_upload_result", gallery_delete_dialog_source)
        self.assertIn("for index, (_request, record, _label) in enumerate(timeline_items, start=1)", gallery_contact_sheet_source)
        self.assertIn('loading="lazy"', gallery_contact_sheet_source)
        self.assertIn("max-height: 620px", gallery_contact_sheet_source)
        self.assertIn("overflow-y: auto", gallery_contact_sheet_source)
        self.assertIn("grid-template-columns: repeat(auto-fill, minmax(112px, 1fr))", gallery_contact_sheet_source)
        self.assertIn("aspect-ratio: 1 / 1", gallery_contact_sheet_source)
        self.assertNotIn("st.button(", gallery_contact_sheet_source)
        self.assertNotIn("st.link_button(", gallery_source)
        self.assertNotIn("image_select", gallery_source)
        self.assertNotIn("photoshoot_gallery_open_session_id", gallery_source)
        self.assertNotIn("photoshoot_gallery_preview_", gallery_source)
        self.assertNotIn("Completed {str(session.updated_at or session.created_at)[:10]}", gallery_source)
        self.assertNotIn('button("Open"', gallery_source)
        self.assertNotIn('caption(f"{len(timeline_items)} Shots")', gallery_source)
        self.assertIn("overflow-x: auto", source)
        self.assertIn("overflow-y: hidden", source)
        self.assertIn("flex-wrap: nowrap", source)
        self.assertNotIn("### Shot Details", gallery_source)
        self.assertNotIn("_render_edit_studio_image(record.output_reference, alt=label, max_height=520)", gallery_source)
        self.assertIn("Return to Library", photoshoot_source)
        self.assertIn("photoshoot_return_to_library_", photoshoot_source)
        self.assertIn("generation_library.return_photoshoot_seed_to_library", photoshoot_source)
        self.assertIn("generation_library.finish_photoshoot_session", photoshoot_source)
        self.assertIn("generation_library.discard_temporary_records", photoshoot_source)
        self.assertIn("photoshoot_studio_reset_fields_", photoshoot_source)
        self.assertIn("photoshoot_studio_pending_direction_", photoshoot_source)
        self.assertIn("photoshoot_studio_pending_prompt_", photoshoot_source)
        self.assertIn("restore_workspace_state = candidate_request is not None", photoshoot_source)
        self.assertIn("persisted_workflow_stage in {", photoshoot_source)
        self.assertIn("st.session_state[reset_fields_key] = True", photoshoot_source)
        self.assertIn("_clear_photoshoot_one_shot_workspace_state(current.session_id, preview_key=preview_key)", photoshoot_source)
        reset_helper_source = source.split("def _clear_photoshoot_one_shot_workspace_state(", 1)[1].split(
            "def _image_bytes_for_grok",
            1,
        )[0]
        self.assertIn("photoshoot_creative_hint_", reset_helper_source)
        self.assertIn("photoshoot_pending_creative_hint_", reset_helper_source)
        self.assertIn("photoshoot_grok_guidance_", reset_helper_source)
        self.assertIn("photoshoot_grok_idea_", reset_helper_source)
        self.assertIn("photoshoot_grok_idea_select_", reset_helper_source)
        self.assertIn("photoshoot_studio_recommendation_", reset_helper_source)
        self.assertIn("photoshoot_direction_approved_", reset_helper_source)
        self.assertIn("photoshoot_studio_prompt_", reset_helper_source)
        self.assertIn("photoshoot_studio_pending_prompt_", reset_helper_source)
        self.assertNotIn("photoshoot_studio_direction_", reset_helper_source)
        self.assertNotIn("photoshoot_studio_pending_direction_", reset_helper_source)
        self.assertNotIn("_selected_index", reset_helper_source)
        self.assertNotIn('st.session_state[direction_key] = ""', photoshoot_source)
        self.assertNotIn('st.session_state[prompt_key] = ""', photoshoot_source)
        self.assertIn('st.session_state["dashboard_page"] = "Generation Library"', photoshoot_source)
        complete_block = photoshoot_source.split('key=f"photoshoot_complete_confirm_button_', 1)[1].split(
            "st.rerun()",
            1,
        )[0]
        self.assertIn('st.session_state.pop("content_studio_active_photoshoot_session_id", None)', complete_block)
        self.assertIn('st.session_state["dashboard_page"] = "Photoshoot Studio"', complete_block)
        self.assertNotIn('st.session_state["dashboard_page"] = "Photoshoot Gallery"', complete_block)
        self.assertIn("No active photoshoot.", source)
        self.assertIn("Start New Photoshoot", source)
        self.assertIn("Open Photoshoot Gallery", source)
        self.assertNotIn('with st.expander("Diagnostics"', photoshoot_source)
        self.assertNotIn("Session History", photoshoot_source)
        self.assertIn("Start Photoshoot", source)
        self.assertIn("Continue Photoshoot", source)
        self.assertIn("Open Existing Photoshoot", source)
        self.assertIn("Approve", source)
        self.assertIn("Reject", source)
        self.assertNotIn("submit_wavespeed_task", source)
        self.assertNotIn("poll_wavespeed_result", source)


if __name__ == "__main__":
    unittest.main()
