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

from app.dashboard.pages.content_studio import (
    CONTENT_STUDIO_PAGES,
    _recent_generated_asset_items,
    filter_generation_jobs,
    generation_workspace_metrics,
)
from app.models.asset_library import AssetLibraryItem, AssetPublishingSummary, AssetRelationshipSummary
from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationFailure, GenerationResult, GenerationStatus
from app.models.generation_ingestion import GenerationAssetIngestionRecord
from app.services.generation_engine_service import GenerationEngineService


class NoReferenceLibraryService:
    def get_active_canonical_reference(self, *, creator_profile_id):
        return None


class FakeGenerationIngestion:
    def __init__(self):
        self.records = (
            GenerationAssetIngestionRecord(
                ingestion_id="ingestion_1",
                generation_job_id="generation_job_success",
                generation_request_id="generation_request_success",
                generation_result_id="generation_result_success",
                output_reference="https://cdn.test/generated.png",
                status="imported",
                asset_id=101,
            ),
        )

    def ingestion_status_for_job(self, generation_job_id):
        if generation_job_id == "generation_job_success":
            return {
                "status": "imported",
                "imported_asset_ids": (101,),
                "failed_messages": (),
            }
        if generation_job_id == "generation_job_failed":
            return {
                "status": "failed",
                "imported_asset_ids": (),
                "failed_messages": ("download failed",),
            }
        return {
            "status": "pending",
            "imported_asset_ids": (),
            "failed_messages": (),
        }

    def list_records(self):
        return self.records


class FakeAssetLibrary:
    def __init__(self):
        self.calls = []

    def get_asset_items(self, asset_ids):
        self.calls.append(tuple(asset_ids))
        return tuple(
            AssetLibraryItem(
                asset_id=asset_id,
                file_name=f"generated_{asset_id}.png",
                media_type="image",
                classification="TEASE",
                status="approved",
                is_active=True,
                created_at=None,
                preview_path=f"C:/Creator-OS/data/cms/vault/originals/images/{asset_id}.png",
                original_path=f"C:/Creator-OS/data/cms/vault/originals/images/{asset_id}.png",
                tags=("generated",),
                themes=("studio",),
                ready_for_rotation=True,
                relationship=AssetRelationshipSummary(),
                publishing=AssetPublishingSummary(status="Local asset only"),
            )
            for asset_id in asset_ids
        )


def prompt_plan(creator_profile_id=7, creative_mode="social_safe"):
    return PromptPlan(
        plan_id=f"prompt_plan_{creator_profile_id}_{creative_mode}",
        session_id=f"session_{creator_profile_id}",
        creator_profile_id=creator_profile_id,
        prompt_text=f"{creative_mode} prompt text",
        creative_mode=creative_mode,
        creative_tags=("window light",),
        reference_asset_id=55,
        reference_asset_path="https://cdn.test/reference.png",
        creative_rationale="Testing workspace.",
        prompt_metadata={"provider_neutral": True},
    )


class GenerationWorkspaceTests(unittest.TestCase):
    def make_engine(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return GenerationEngineService(
            storage_dir=temp_dir.name,
            reference_library_service=NoReferenceLibraryService(),
            providers={},
        )

    def make_jobs(self):
        engine = self.make_engine()
        queued = engine.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(creative_mode="social_safe"),
            provider_id="seedream_4_5",
        )
        running = engine.queue_prompt_plan(
            creator_profile={"id": 8},
            prompt_plan=prompt_plan(8, "premium_teaser"),
            provider_id="wan_2_7_image_edit",
        )
        running = engine.start_job(running.job_id)
        success = engine.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(creative_mode="social_safe"),
            provider_id="seedream_4_5",
        )
        success = engine.complete_job(
            success.job_id,
            GenerationResult(
                result_id="generation_result_success",
                request_id=success.request.request_id,
                job_id=success.job_id,
                provider_id=success.request.provider_id,
                status=GenerationStatus.SUCCEEDED.value,
                output_references=("https://cdn.test/generated.png",),
                duration_seconds=4.0,
            ),
        )
        success = success.__class__(
            **{
                **success.__dict__,
                "job_id": "generation_job_success",
                "request": success.request.__class__(
                    **{
                        **success.request.__dict__,
                        "request_id": "generation_request_success",
                    }
                ),
            }
        )
        failed = engine.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(creative_mode="premium_teaser"),
            provider_id="seedream_4_5",
        )
        failed = engine.fail_job(
            failed.job_id,
            GenerationFailure(reason="provider failed", retryable=False),
        )
        failed = failed.__class__(
            **{
                **failed.__dict__,
                "job_id": "generation_job_failed",
            }
        )
        retry = engine.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(creative_mode="story_sequence"),
            provider_id="nano_banana",
        )
        retry = engine.retry_job(retry.job_id)
        return engine, (queued, running, success, failed, retry)

    def test_job_history_and_queue_metrics(self):
        _, jobs = self.make_jobs()

        metrics = generation_workspace_metrics(jobs, FakeGenerationIngestion())

        self.assertGreaterEqual(metrics["jobs_today"], 5)
        self.assertEqual(metrics["failed_jobs"], 1)
        self.assertEqual(metrics["generated_assets"], 1)
        self.assertEqual(metrics["imported_assets"], 1)
        self.assertEqual(metrics["queue_depth"], 2)
        self.assertEqual(metrics["average_generation_time"], 4.0)
        self.assertEqual(metrics["success_rate"], 50.0)

    def test_search_and_filters(self):
        _, jobs = self.make_jobs()

        provider_filtered = filter_generation_jobs(jobs, provider="wan_2_7_image_edit")
        status_filtered = filter_generation_jobs(jobs, status="failed")
        creator_filtered = filter_generation_jobs(jobs, creator_profile_id=8)
        mode_filtered = filter_generation_jobs(jobs, creative_mode="story_sequence")
        search_filtered = filter_generation_jobs(jobs, search="provider failed")

        self.assertEqual(len(provider_filtered), 1)
        self.assertEqual(provider_filtered[0].status, "running")
        self.assertEqual(len(status_filtered), 1)
        self.assertEqual(status_filtered[0].job_id, "generation_job_failed")
        self.assertEqual(len(creator_filtered), 1)
        self.assertEqual(creator_filtered[0].request.creator_profile_id, 8)
        self.assertEqual(len(mode_filtered), 1)
        self.assertEqual(mode_filtered[0].status, "retry")
        self.assertEqual(len(search_filtered), 1)

    def test_retry_and_cancel_actions_are_generation_engine_lifecycle(self):
        engine = self.make_engine()
        queued = engine.queue_prompt_plan(
            creator_profile={"id": 7},
            prompt_plan=prompt_plan(),
        )
        failed = engine.fail_job(
            queued.job_id,
            GenerationFailure(reason="temporary", retryable=False),
        )

        retry = engine.retry_job(failed.job_id)
        cancelled = engine.cancel_job(retry.job_id)

        self.assertEqual(retry.status, "retry")
        self.assertIsNone(retry.failure)
        self.assertEqual(cancelled.status, "cancelled")

    def test_recent_generated_asset_links_use_asset_library(self):
        asset_library = FakeAssetLibrary()

        items = _recent_generated_asset_items(
            generation_ingestion=FakeGenerationIngestion(),
            asset_library=asset_library,
        )

        self.assertEqual(asset_library.calls, [(101,)])
        self.assertEqual(items[0].asset_id, 101)
        self.assertEqual(items[0].file_name, "generated_101.png")

    def test_content_studio_integration(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(
            encoding="utf-8"
        )
        navigation = Path("app/dashboard/navigation.py").read_text(encoding="utf-8")
        main = Path("app/dashboard/main.py").read_text(encoding="utf-8")

        self.assertIn("Generation Workspace", CONTENT_STUDIO_PAGES)
        self.assertIn("Queued Jobs", source)
        self.assertIn("Running Jobs", source)
        self.assertIn("Completed Jobs", source)
        self.assertIn("Failed Jobs", source)
        self.assertIn("Retry Queue", source)
        self.assertIn("Generation History", source)
        self.assertIn("Recent Generated Assets", source)
        self.assertIn("Generation Workspace", navigation)
        self.assertIn("Generation Workspace", main)
        self.assertNotIn("PublishingService", source)
        self.assertNotIn("ProductRepository", source)


if __name__ == "__main__":
    unittest.main()
