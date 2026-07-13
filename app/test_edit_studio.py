import sys
import tempfile
import types
import unittest
from pathlib import Path

if "streamlit" not in sys.modules:
    streamlit = types.ModuleType("streamlit")
    sys.modules["streamlit"] = streamlit
    components = types.ModuleType("streamlit.components")
    components_v1 = types.ModuleType("streamlit.components.v1")
    sys.modules["streamlit.components"] = components
    sys.modules["streamlit.components.v1"] = components_v1

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
    EDIT_STUDIO_DEFAULT_PROVIDER_ID,
    EDIT_MODE_LABELS,
    create_edit_studio_generation_request,
    default_provider_index,
    edit_studio_provider_options,
    execute_edit_generation_for_review,
    execute_generation_job_to_library,
)
from app.models.generation_engine import (
    GenerationJob,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)
from app.models.generation_library import GeneratedImageRecord
from app.services.content_archive_service import ContentArchiveService
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
    def __init__(self, jobs=(), provider_ids=None):
        self.calls = []
        self.jobs = tuple(jobs)
        if provider_ids is not None:
            self.provider_registry = types.SimpleNamespace(
                provider_ids=lambda: tuple(provider_ids),
            )

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


class FakeArchiveResponse:
    content = b"fake-image"

    def raise_for_status(self):
        return None


class FakeArchiveHttp:
    def get(self, url, **kwargs):
        return FakeArchiveResponse()


class EditStudioTests(unittest.TestCase):
    def make_services(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        edit_studio = EditStudioService(storage_dir=Path(temp_dir.name) / "edit")
        archive = ContentArchiveService(
            storage_dir=Path(temp_dir.name) / "archive_data",
            content_root=Path(temp_dir.name) / "Content",
            http_client=FakeArchiveHttp(),
        )
        generation_library = GenerationLibraryService(
            storage_dir=Path(temp_dir.name) / "library",
            archive_service=archive,
        )
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
        self.assertEqual(generation_library.get("generated_image_1").status, "active")
        self.assertEqual(len(generation_library.archive_service.list_records(archive_type="edited_original")), 0)

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
        self.assertTrue(any("Generation" in record.output_reference for record in records))
        edited = next(
            record
            for record in records
            if record.generation_metadata.get("original_output_reference") == "https://cdn.test/edited.png"
        )
        self.assertTrue(Path(edited.output_reference).exists())
        self.assertEqual(edited.generation_metadata["original_output_reference"], "https://cdn.test/edited.png")
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
        self.assertTrue(Path(records[0].output_reference).exists())
        self.assertIn("Generation", records[0].output_reference)
        self.assertEqual(records[0].generation_metadata["original_output_reference"], "https://cdn.test/edited-live.png")
        self.assertEqual(records[0].generation_metadata["workflow_type"], "edit")

    def test_edit_execution_for_review_creates_hidden_candidate(self):
        edit_studio, generation_library = self.make_services()
        engine = FakeGenerationEngine()
        _edit_item, job = create_edit_studio_generation_request(
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

        executed, candidates = execute_edit_generation_for_review(
            job=job,
            generation_engine=engine,
            generation_library=generation_library,
        )

        self.assertEqual(executed.status, GenerationStatus.SUCCEEDED.value)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].status, "edit_candidate")
        self.assertEqual(candidates[0].review_state, "pending_edit_approval")
        active_ids = tuple(record.image_id for record in generation_library.browse().records)
        self.assertIn("generated_image_1", active_ids)
        self.assertNotIn(candidates[0].image_id, active_ids)

    def test_send_to_edit_moves_asset_to_pending_edit_and_hides_from_library(self):
        _edit_studio, generation_library = self.make_services()
        content_root = generation_library.archive_service.content_root
        active_path = content_root / "Generation" / "Active" / "source.png"
        active_path.parent.mkdir(parents=True, exist_ok=True)
        active_path.write_bytes(b"original")
        generation_library._write_records(
            [generated_record("generated_image_1", output_reference=str(active_path))]
        )

        pending = generation_library.send_to_pending_edit("generated_image_1")

        self.assertEqual(pending.status, "pending_edit")
        self.assertIn("Pending_Edit", pending.output_reference)
        self.assertTrue(Path(pending.output_reference).exists())
        self.assertFalse(active_path.exists())
        self.assertEqual(generation_library.browse().records, ())

    def test_pending_edit_survives_refresh_and_restart(self):
        _edit_studio, generation_library = self.make_services()
        content_root = generation_library.archive_service.content_root
        active_path = content_root / "Generation" / "Active" / "source.png"
        active_path.parent.mkdir(parents=True, exist_ok=True)
        active_path.write_bytes(b"original")
        generation_library._write_records(
            [generated_record("generated_image_1", output_reference=str(active_path))]
        )
        pending = generation_library.send_to_pending_edit("generated_image_1")

        refreshed = generation_library.pending_edit_record(creator_profile_id=7)
        restarted_archive = ContentArchiveService(
            storage_dir=generation_library.archive_service.storage_dir,
            content_root=content_root,
            http_client=FakeArchiveHttp(),
        )
        restarted_library = GenerationLibraryService(
            storage_dir=generation_library.storage_dir,
            archive_service=restarted_archive,
        )
        restarted = restarted_library.pending_edit_record(creator_profile_id=7)

        self.assertEqual(refreshed.image_id, pending.image_id)
        self.assertEqual(restarted.image_id, pending.image_id)
        self.assertEqual(restarted.status, "pending_edit")

    def test_return_to_library_restores_original_asset_and_empties_pending_edit(self):
        _edit_studio, generation_library = self.make_services()
        content_root = generation_library.archive_service.content_root
        active_path = content_root / "Generation" / "Active" / "source.png"
        active_path.parent.mkdir(parents=True, exist_ok=True)
        active_path.write_bytes(b"original")
        generation_library._write_records(
            [generated_record("generated_image_1", output_reference=str(active_path))]
        )
        pending = generation_library.send_to_pending_edit("generated_image_1")

        result = generation_library.return_pending_edit_to_library(pending.image_id)

        self.assertTrue(result.success, result.errors)
        restored = generation_library.get("generated_image_1")
        self.assertEqual(restored.status, "active")
        self.assertIn("Generation\\Active", restored.output_reference)
        self.assertTrue(Path(restored.output_reference).exists())
        self.assertEqual(tuple((content_root / "Pending_Edit").glob("*")), ())
        self.assertEqual(tuple(record.image_id for record in generation_library.browse().records), ("generated_image_1",))

    def test_pending_edit_lifecycle_survives_restart_sync_and_return_to_library(self):
        _edit_studio, generation_library = self.make_services()
        content_root = generation_library.archive_service.content_root
        active_path = content_root / "Generation" / "Active" / "source.png"
        active_path.parent.mkdir(parents=True, exist_ok=True)
        active_path.write_bytes(b"original")
        source_url = "https://cdn.test/source.png"
        record = generated_record(
            "generated_image_1",
            output_reference=str(active_path),
        )
        generation_library._write_records(
            [
                GeneratedImageRecord(
                    **{
                        **record.__dict__,
                        "generation_job_id": "source_job",
                        "generation_metadata": {
                            **dict(record.generation_metadata or {}),
                            "original_output_reference": source_url,
                            "output_reference": str(active_path),
                        },
                    }
                )
            ]
        )
        source_job = successful_edit_job()
        source_job = GenerationJob(
            job_id="source_job",
            request=GenerationRequest(
                request_id="source_request",
                creator_profile_id=7,
                prompt_plan_id="source_plan",
                prompt_text="Original generated prompt",
                reference_asset_id=55,
                reference_asset_path=None,
                provider_id="wan_2_7_image_edit",
                generation_type="image_to_image",
                media_type="image",
                image_count=1,
                metadata={"source": "premium_studio"},
            ),
            status=GenerationStatus.SUCCEEDED.value,
            result=GenerationResult(
                result_id="source_result",
                request_id="source_request",
                job_id="source_job",
                provider_id="wan_2_7_image_edit",
                status=GenerationStatus.SUCCEEDED.value,
                output_references=(source_url, str(active_path)),
            ),
        )

        pending = generation_library.send_to_pending_edit("generated_image_1")
        pending_path = Path(pending.output_reference)

        self.assertFalse(active_path.exists())
        self.assertTrue(pending_path.exists())
        self.assertEqual(generation_library.get("generated_image_1").status, "pending_edit")
        self.assertEqual(generation_library.browse().records, ())

        restarted_archive = ContentArchiveService(
            storage_dir=generation_library.archive_service.storage_dir,
            content_root=content_root,
            http_client=FakeArchiveHttp(),
        )
        restarted_library = GenerationLibraryService(
            storage_dir=generation_library.storage_dir,
            archive_service=restarted_archive,
        )
        restored_pending = restarted_library.pending_edit_record(creator_profile_id=7)
        created_after_sync = restarted_library.sync_jobs((source_job,))
        still_pending = restarted_library.pending_edit_record(creator_profile_id=7)

        self.assertEqual(restored_pending.image_id, "generated_image_1")
        self.assertEqual(created_after_sync, ())
        self.assertEqual(still_pending.image_id, "generated_image_1")
        self.assertEqual(still_pending.status, "pending_edit")
        self.assertEqual(restarted_library.browse().records, ())

        returned = restarted_library.return_pending_edit_to_library("generated_image_1")
        active_records = restarted_library.browse().records

        self.assertTrue(returned.success, returned.errors)
        self.assertEqual(len(active_records), 1)
        self.assertEqual(active_records[0].image_id, "generated_image_1")
        self.assertEqual(active_records[0].status, "active")
        self.assertTrue(Path(active_records[0].output_reference).exists())
        self.assertEqual(tuple((content_root / "Pending_Edit").glob("*")), ())

    def test_approve_replaces_generation_library_asset_and_copies_edit_history(self):
        _edit_studio, generation_library = self.make_services()
        content_root = generation_library.archive_service.content_root
        source_path = content_root / "Generation" / "Active" / "source.png"
        candidate_path = content_root / "Generation" / "Active" / "candidate.png"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(b"original")
        candidate_path.write_bytes(b"approved")
        generation_library._write_records(
            [
                generated_record("generated_image_1", output_reference=str(source_path)),
                generated_record("generated_image_candidate", output_reference=str(candidate_path)),
            ]
        )
        pending = generation_library.send_to_pending_edit("generated_image_1")
        generation_library.mark_edit_candidate(
            "generated_image_candidate",
            pending_source_image_id=pending.image_id,
        )

        result = generation_library.approve_edit_candidate(
            source_image_id="generated_image_1",
            edited_image_id="generated_image_candidate",
        )

        self.assertTrue(result.success, result.errors)
        approved = generation_library.get("generated_image_1")
        self.assertEqual(approved.image_id, "generated_image_1")
        self.assertEqual(approved.review_state, "approved_edit")
        self.assertIn("Generation\\Active", approved.output_reference)
        self.assertTrue(Path(approved.output_reference).exists())
        self.assertEqual(Path(approved.output_reference).read_bytes(), b"approved")
        self.assertTrue((content_root / "Edited" / "Originals").exists())
        self.assertTrue((content_root / "Edited" / "Approved").exists())
        self.assertEqual(len(tuple((content_root / "Edited" / "Originals").glob("*"))), 1)
        self.assertEqual(len(tuple((content_root / "Edited" / "Approved").glob("*"))), 1)
        self.assertEqual(tuple((content_root / "Pending_Edit").glob("*")), ())
        with self.assertRaises(KeyError):
            generation_library.get("generated_image_candidate")
        self.assertEqual(tuple(record.image_id for record in generation_library.browse().records), ("generated_image_1",))

    def test_discard_leaves_original_untouched_and_creates_no_edit_history(self):
        _edit_studio, generation_library = self.make_services()
        content_root = generation_library.archive_service.content_root
        source_path = content_root / "Generation" / "Social" / "source.png"
        candidate_path = content_root / "Generation" / "Social" / "candidate.png"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(b"original")
        candidate_path.write_bytes(b"approved")
        generation_library._write_records(
            [
                generated_record("generated_image_1", output_reference=str(source_path)),
                generated_record("generated_image_candidate", output_reference=str(candidate_path)),
            ]
        )
        generation_library.mark_edit_candidate("generated_image_candidate")

        result = generation_library.discard_edit_candidate("generated_image_candidate")

        self.assertTrue(result.success, result.errors)
        original = generation_library.get("generated_image_1")
        self.assertEqual(original.output_reference, str(source_path))
        self.assertTrue(source_path.exists())
        self.assertFalse(candidate_path.exists())
        self.assertFalse((content_root / "Edited" / "Originals").exists())
        self.assertFalse((content_root / "Edited" / "Approved").exists())

    def test_discarded_edit_candidate_is_not_reindexed_by_future_sync(self):
        edit_studio, generation_library = self.make_services()
        job = successful_edit_job()
        engine = FakeGenerationEngine(jobs=(job,))
        candidates = edit_studio.sync_generation_library(
            generation_engine=engine,
            generation_library=generation_library,
        )
        candidate = generation_library.mark_edit_candidate(candidates[0].image_id)

        result = generation_library.discard_edit_candidate(candidate.image_id)
        created_again = edit_studio.sync_generation_library(
            generation_engine=engine,
            generation_library=generation_library,
        )

        self.assertTrue(result.success, result.errors)
        self.assertEqual(created_again, ())
        self.assertNotIn(candidate.image_id, tuple(record.image_id for record in generation_library.list_records()))

    def test_edit_again_can_use_pending_candidate_as_next_source(self):
        edit_studio, generation_library = self.make_services()
        engine = FakeGenerationEngine()
        content_root = generation_library.archive_service.content_root
        candidate_path = content_root / "Generation" / "Social" / "candidate.png"
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_bytes(b"candidate")
        generation_library._write_records(
            [
                generated_record("generated_image_1", output_reference="https://cdn.test/source.png"),
                generated_record("generated_image_candidate", output_reference=str(candidate_path)),
            ]
        )
        generation_library.mark_edit_candidate("generated_image_candidate")

        edit_item, job = create_edit_studio_generation_request(
            creator_profile={"id": 7},
            edit_studio=edit_studio,
            generation_library=generation_library,
            generation_engine=engine,
            source_image_ids=("generated_image_candidate",),
            edit_mode="single_image",
            edit_prompt="Refine the edited result.",
            provider_id="wan_2_7_image_edit",
            batch_size=1,
        )

        self.assertEqual(edit_item.source_image_ids, ("generated_image_candidate",))
        self.assertEqual(job.request.image_count, 1)

    def test_edit_studio_provider_options_only_show_active_edit_models(self):
        engine = FakeGenerationEngine(
            provider_ids=(
                "nano_banana",
                "seedream_4_5",
                "flux",
                "seedream_5_0_pro",
                "nano_banana_pro",
                "wan_2_7_image_edit",
            )
        )

        options = edit_studio_provider_options(engine)

        self.assertEqual(
            options,
            (
                ("seedream_5_0_pro", "Seedream 5.0 Pro"),
                ("nano_banana_pro", "Nano Banana Pro"),
                ("wan_2_7_image_edit", "WAN 2.7"),
            ),
        )

    def test_edit_studio_provider_defaults_to_seedream_5_pro_and_filters_stale_values(self):
        engine = FakeGenerationEngine(
            provider_ids=(
                "seedream_5_0_pro",
                "nano_banana_pro",
                "wan_2_7_image_edit",
                "flux",
            )
        )

        provider_ids = tuple(provider_id for provider_id, _label in edit_studio_provider_options(engine))

        self.assertEqual(provider_ids[0], EDIT_STUDIO_DEFAULT_PROVIDER_ID)
        self.assertEqual(default_provider_index(provider_ids, preferred_provider_id=EDIT_STUDIO_DEFAULT_PROVIDER_ID), 0)
        self.assertNotIn("flux", provider_ids)
        self.assertNotIn("seedream_4_5", provider_ids)
        self.assertNotIn("nano_banana", provider_ids)

    def test_edit_studio_ui_contract(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(encoding="utf-8")
        navigation = Path("app/dashboard/navigation.py").read_text(encoding="utf-8")

        self.assertIn("def _render_edit_studio", source)
        self.assertIn("Single Image Edit", source)
        self.assertIn("Multi Image Edit", source)
        self.assertIn("Face Replacement", source)
        self.assertIn("Style Transfer", source)
        self.assertIn("Variations", source)
        self.assertIn("Prompt", source)
        self.assertIn("Edit History", source)
        self.assertIn("Reference Image", source)
        self.assertIn("Batch Edit", source)
        self.assertIn("Original Image", source)
        self.assertIn("Edited Image", source)
        self.assertIn("max-height: {int(max_height)}px", source)
        self.assertIn("#171a1f", source)
        self.assertIn("edit_studio_card_selected", source)
        self.assertIn("🚀 Generate Edit", source)
        self.assertIn("✅ Approve", source)
        self.assertIn("✏️ Edit Again", source)
        self.assertIn("🗑 Discard", source)
        self.assertIn("↩️ Return to Library", source)
        self.assertIn("send_to_pending_edit", source)
        self.assertIn("pending_edit_record", source)
        self.assertIn('"Edit Studio"', navigation)
        self.assertIn(EDIT_MODE_LABELS["single_image"], source)
        self.assertIn(EDIT_MODE_LABELS["multi_image"], source)
        self.assertNotIn("st.multiselect", source[source.index("def _render_edit_studio"):source.index("def _render_generation_job_card")])
        self.assertNotIn("Batch Edit Count", source)
        self.assertNotIn("Open Generation Library", source)
        self.assertNotIn("Open Single Edit", source)
        self.assertNotIn("Open Multi Edit", source)
        self.assertNotIn("Edit Preview", source)
        self.assertNotIn("upload_to_imgbb", source)
        self.assertNotIn("submit_multi_edit_task", source)
        self.assertNotIn("poll_multi_edit_result", source)
        self.assertNotIn("Sent-to-Edit", source)


if __name__ == "__main__":
    unittest.main()
