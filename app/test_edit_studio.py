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
    EDIT_MODE_LABELS,
    create_edit_studio_generation_request,
    execute_generation_job_to_library,
)
from app.models.generation_engine import (
    GenerationJob,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)
from app.models.generation_library import GeneratedImageRecord
from app.services.edit_studio_service import EditStudioService
from app.services.generation_library_service import GenerationLibraryService


def generated_record(image_id="generated_image_1", creator_profile_id=7, output_reference="https://cdn.test/image-1.png"):
    return GeneratedImageRecord(
        image_id=image_id,
        generation_job_id=f"{image_id}_job",
        generation_request_id=f"{image_id}_request",
        generation_result_id=f"{image_id}_result",
        output_reference=output_reference,
        creator_profile_id=creator_profile_id,
        provider_id="wan_2_7_image_edit",
        prompt_plan_id=f"{image_id}_plan",
        prompt_text="Original generated prompt",
        creative_mode="premium_teaser",
        reference_asset_id=55,
        prompt_metadata={"creative_tags": ("studio",)},
        generation_metadata={"request_metadata": {"source": "premium_studio"}},
    )


def successful_edit_job():
    request = GenerationRequest(
        request_id="edit_generation_request",
        creator_profile_id=7,
        prompt_plan_id="edit_prompt_plan",
        prompt_text="Edit Studio image edit prompt",
        reference_asset_id=55,
        reference_asset_path=None,
        provider_id="wan_2_7_image_edit",
        generation_type="image_to_image",
        media_type="image",
        image_count=1,
        metadata={
            "source": "edit_studio",
            "edit_session_id": "edit_session_1",
            "edit_request_id": "edit_request_1",
            "edit_mode": "single_image",
        },
    )
    result = GenerationResult(
        result_id="edit_generation_result",
        request_id=request.request_id,
        job_id="edit_generation_job",
        provider_id=request.provider_id,
        status=GenerationStatus.SUCCEEDED.value,
        output_references=("https://cdn.test/edited.png",),
    )
    return GenerationJob(
        job_id="edit_generation_job",
        request=request,
        status=GenerationStatus.SUCCEEDED.value,
        result=result,
    )


class FakeGenerationEngine:
    def __init__(self, jobs=()):
        self.calls = []
        self.jobs = tuple(jobs)

    def queue_prompt_plan(self, **kwargs):
        self.calls.append(kwargs)
        request = GenerationRequest(
            request_id="generation_request_edit",
            creator_profile_id=int(kwargs["creator_profile"]["id"]),
            prompt_plan_id=kwargs["prompt_plan"].plan_id,
            prompt_text=kwargs["prompt_plan"].prompt_text,
            reference_asset_id=kwargs["prompt_plan"].reference_asset_id,
            reference_asset_path=None,
            provider_id=kwargs["provider_id"],
            generation_type=kwargs["generation_type"],
            media_type=kwargs["media_type"],
            image_count=kwargs["image_count"],
            metadata=kwargs["metadata"],
        )
        return GenerationJob(job_id=f"generation_job_edit_{len(self.calls)}", request=request)

    def list_jobs(self):
        return self.jobs

    def dispatch_job(self, job_id):
        if self.jobs:
            return self.jobs[0]
        request = self.queue_prompt_plan(**self.calls[-1]).request
        result = GenerationResult(
            result_id="edit_generation_result",
            request_id=request.request_id,
            job_id=job_id,
            provider_id=request.provider_id,
            status=GenerationStatus.SUCCEEDED.value,
            output_references=("https://cdn.test/edited-live.png",),
        )
        return GenerationJob(
            job_id=job_id,
            request=request,
            status=GenerationStatus.SUCCEEDED.value,
            result=result,
        )


class EditStudioTests(unittest.TestCase):
    def make_services(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        edit_studio = EditStudioService(storage_dir=Path(temp_dir.name) / "edit")
        generation_library = GenerationLibraryService(storage_dir=Path(temp_dir.name) / "library")
        generation_library._write_records(
            [
                generated_record("generated_image_1", output_reference="https://cdn.test/source.png"),
                generated_record("generated_image_2", output_reference="https://cdn.test/reference.png"),
            ]
        )
        return edit_studio, generation_library

    def test_single_image_edit_request_submits_generation_job(self):
        edit_studio, generation_library = self.make_services()
        engine = FakeGenerationEngine()

        edit_item, job = create_edit_studio_generation_request(
            creator_profile={"id": 7},
            edit_studio=edit_studio,
            generation_library=generation_library,
            generation_engine=engine,
            source_image_ids=("generated_image_1",),
            edit_mode="single_image",
            edit_prompt="Change the dress color to black.",
            provider_id="wan_2_7_image_edit",
            batch_size=1,
        )

        self.assertEqual(edit_item.edit_mode, "single_image")
        self.assertEqual(job.job_id, "generation_job_edit_1")
        self.assertEqual(engine.calls[0]["metadata"]["source"], "edit_studio")
        self.assertEqual(engine.calls[0]["metadata"]["edit_request_id"], edit_item.edit_request_id)
        self.assertEqual(engine.calls[0]["prompt_plan"].prompt_metadata["source_image_ids"], ("generated_image_1",))
        self.assertEqual(len(edit_studio.history(creator_profile_id=7)), 1)

    def test_multi_edit_uses_reference_generated_image(self):
        edit_studio, generation_library = self.make_services()
        engine = FakeGenerationEngine()

        edit_item, _ = create_edit_studio_generation_request(
            creator_profile={"id": 7},
            edit_studio=edit_studio,
            generation_library=generation_library,
            generation_engine=engine,
            source_image_ids=("generated_image_1",),
            edit_mode="multi_image",
            edit_prompt="Replace the outfit using the reference image.",
            provider_id="nano_banana_pro",
            reference_image_id="generated_image_2",
            batch_size=1,
        )

        self.assertEqual(edit_item.reference_image_id, "generated_image_2")
        self.assertEqual(engine.calls[0]["metadata"]["reference_image_id"], "generated_image_2")
        self.assertIn("secondary visual reference", engine.calls[0]["prompt_plan"].prompt_text)

    def test_face_replacement_and_reference_asset_handling(self):
        edit_studio, generation_library = self.make_services()
        engine = FakeGenerationEngine()

        edit_item, _ = create_edit_studio_generation_request(
            creator_profile={"id": 7},
            edit_studio=edit_studio,
            generation_library=generation_library,
            generation_engine=engine,
            source_image_ids=("generated_image_1",),
            edit_mode="face_replacement",
            edit_prompt="Use the reference face while preserving pose and lighting.",
            provider_id="seedream_4_5",
            reference_image_id="generated_image_2",
            reference_asset_id=55,
        )

        self.assertEqual(edit_item.edit_mode, "face_replacement")
        self.assertEqual(edit_item.reference_asset_id, 55)
        self.assertEqual(engine.calls[0]["prompt_plan"].reference_asset_id, 55)
        self.assertEqual(engine.calls[0]["metadata"]["reference_asset_id"], 55)

    def test_batch_edit_submits_one_job_for_selected_images(self):
        edit_studio, generation_library = self.make_services()
        engine = FakeGenerationEngine()

        edit_item, job = edit_studio.batch_edit(
            creator_profile={"id": 7},
            source_image_ids=("generated_image_1", "generated_image_2"),
            edit_prompt="Create matching variations with the same lighting.",
            provider_id="flux",
            generation_library=generation_library,
            generation_engine=engine,
        )

        self.assertEqual(edit_item.edit_mode, "multi_image")
        self.assertEqual(edit_item.batch_size, 2)
        self.assertEqual(job.request.image_count, 2)
        self.assertEqual(engine.calls[0]["metadata"]["source_image_ids"], ("generated_image_1", "generated_image_2"))

    def test_generation_library_integration_indexes_completed_edit_results(self):
        edit_studio, generation_library = self.make_services()
        engine = FakeGenerationEngine(jobs=(successful_edit_job(),))

        created = edit_studio.sync_generation_library(
            generation_engine=engine,
            generation_library=generation_library,
        )
        records = generation_library.browse().records

        self.assertEqual(len(created), 1)
        self.assertTrue(any(record.output_reference == "https://cdn.test/edited.png" for record in records))
        edited = next(record for record in records if record.output_reference == "https://cdn.test/edited.png")
        self.assertEqual(edited.generation_metadata["request_metadata"]["source"], "edit_studio")

    def test_edit_execution_returns_results_to_generation_library(self):
        edit_studio, generation_library = self.make_services()
        engine = FakeGenerationEngine()
        _edit_item, job = create_edit_studio_generation_request(
            creator_profile={"id": 7},
            edit_studio=edit_studio,
            generation_library=generation_library,
            generation_engine=engine,
            source_image_ids=("generated_image_1",),
            edit_mode="variation",
            edit_prompt="Make a close variation with warmer light.",
            provider_id="seedream_4_5",
            batch_size=1,
        )

        executed, records = execute_generation_job_to_library(
            job=job,
            generation_engine=engine,
            generation_library=generation_library,
        )

        self.assertEqual(executed.status, GenerationStatus.SUCCEEDED.value)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].output_reference, "https://cdn.test/edited-live.png")
        self.assertEqual(records[0].generation_metadata["workflow_type"], "edit")

    def test_edit_studio_ui_contract(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(encoding="utf-8")
        navigation = Path("app/dashboard/navigation.py").read_text(encoding="utf-8")

        self.assertIn("def _render_edit_studio", source)
        self.assertIn("Single Image Edit", source)
        self.assertIn("Multi Image Edit", source)
        self.assertIn("Face Replacement", source)
        self.assertIn("Style Transfer", source)
        self.assertIn("Variation", source)
        self.assertIn("Edit Prompt", source)
        self.assertIn("Edit History", source)
        self.assertIn("Reference Image Selection", source)
        self.assertIn("Batch Edit", source)
        self.assertIn("Original", source)
        self.assertIn("Edited", source)
        self.assertIn("Running Edit Request through Generation Engine", source)
        self.assertIn("Generation Library", source)
        self.assertIn('"Edit Studio"', navigation)
        for mode in EDIT_MODE_LABELS:
            self.assertIn(mode, source)
        self.assertNotIn("upload_to_imgbb", source)
        self.assertNotIn("submit_multi_edit_task", source)
        self.assertNotIn("poll_multi_edit_result", source)
        self.assertNotIn("Sent-to-Edit", source)


if __name__ == "__main__":
    unittest.main()
