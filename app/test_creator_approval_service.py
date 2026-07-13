import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.models.creator_approval import ApprovedSourceIdentity, CreatorApprovalRequest
from app.models.generation_engine import GenerationJob, GenerationRequest, GenerationResult, GenerationStatus
from app.models.generation_ingestion import GenerationAssetIngestionRecord, GenerationResultIngestionResult
from app.models.generation_library import GeneratedImageRecord
from app.models.photoshoot_queue import PHOTOSHOOT_ASSET_METADATA_KEY
from app.services.creator_approval_service import CreatorApprovalService


class FakeAssetRepository:
    def __init__(self):
        self.assets = {
            201: SimpleNamespace(id=201, media_metadata={}),
            777: SimpleNamespace(id=777, media_metadata={}),
        }
        self.updated = []

    def get_by_id(self, asset_id):
        return self.assets[int(asset_id)]

    def update_media_metadata(self, asset_id, media_metadata):
        self.updated.append((int(asset_id), media_metadata))
        self.assets[int(asset_id)] = SimpleNamespace(id=int(asset_id), media_metadata=media_metadata)


class FakeIngestionService:
    def __init__(self):
        self.assets = FakeAssetRepository()
        self.jobs = []
        self.records = []

    def ingest_job(self, job):
        self.jobs.append(job)
        record = GenerationAssetIngestionRecord(
            ingestion_id="generation_ingestion_1",
            generation_job_id=job.job_id,
            generation_request_id=job.request.request_id,
            generation_result_id=job.result.result_id,
            output_reference=job.result.output_references[0],
            status="imported",
            asset_id=201,
        )
        self.records.append(record)
        return GenerationResultIngestionResult(
            success=True,
            generation_job_id=job.job_id,
            imported_asset_ids=(201,),
            records=(record,),
        )

    def records_for_job(self, generation_job_id):
        return tuple(record for record in self.records if record.generation_job_id == generation_job_id)


class FakeContentIntelligenceRegistrar:
    def __init__(self):
        self.calls = []

    def register_asset(self, asset_id, **kwargs):
        self.calls.append((asset_id, kwargs))
        return SimpleNamespace(
            status=SimpleNamespace(value="COMPLETE"),
            ready=True,
            missing_components=(),
            error_message=None,
        )


class FakeCommerceRegistrar:
    def __init__(self):
        self.calls = []

    def register_asset(self, asset_id, **kwargs):
        self.calls.append((asset_id, kwargs))
        return SimpleNamespace(
            success=True,
            record=SimpleNamespace(
                registration_id="business-asset-201",
                status=SimpleNamespace(value="REGISTERED"),
                lifecycle_state=SimpleNamespace(value="AWAITING_DESTINATION"),
                destination_status=SimpleNamespace(value="AWAITING_DESTINATION"),
                product_ids=("product-1",),
                experience_ids=("experience-1",),
                product_draft_ids=(),
                missing_requirements=(),
                error_message=None,
            ),
            commerce_readiness=SimpleNamespace(ready_for_commerce_destination=True),
            errors=(),
        )


def generation_job():
    request = GenerationRequest(
        request_id="generation_request_1",
        creator_profile_id=7,
        prompt_plan_id="prompt_plan_1",
        prompt_text="Approved prompt",
        reference_asset_id=55,
        reference_asset_path="https://cdn.test/reference.png",
        provider_id="seedream_4_5",
        generation_type="image_to_image",
        media_type="image",
        image_count=1,
    )
    result = GenerationResult(
        result_id="generation_result_1",
        request_id=request.request_id,
        job_id="generation_job_1",
        provider_id=request.provider_id,
        status=GenerationStatus.SUCCEEDED.value,
        output_references=("https://cdn.test/approved.png",),
    )
    return GenerationJob(
        job_id="generation_job_1",
        request=request,
        status=GenerationStatus.SUCCEEDED.value,
        result=result,
    )


def generated_record(**overrides):
    values = {
        "image_id": "generated_image_1",
        "generation_job_id": "generation_job_1",
        "generation_request_id": "generation_request_1",
        "generation_result_id": "generation_result_1",
        "output_reference": "https://cdn.test/approved.png",
        "creator_profile_id": 7,
        "provider_id": "seedream_4_5",
        "prompt_plan_id": "prompt_plan_1",
        "prompt_text": "Approved prompt",
        "creative_mode": "social_safe",
        "reference_asset_id": 55,
    }
    values.update(overrides)
    return GeneratedImageRecord(**values)


class CreatorApprovalServiceTests(unittest.TestCase):
    def make_service(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return CreatorApprovalService(
            storage_dir=Path(temp_dir.name),
            content_intelligence_registrar=FakeContentIntelligenceRegistrar(),
            commerce_registrar=FakeCommerceRegistrar(),
        )

    def test_generation_approval_is_idempotent(self):
        service = self.make_service()
        ingestion = FakeIngestionService()
        job = generation_job()
        record = generated_record()

        first = service.approve_generated_record(record, generation_job=job, ingestion_service=ingestion)
        second = service.approve_generated_record(record, generation_job=job, ingestion_service=ingestion)

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(first.asset_id, 201)
        self.assertEqual(second.asset_id, 201)
        self.assertEqual(len(ingestion.jobs), 1)
        self.assertTrue(second.reused_existing_mapping)
        self.assertEqual(first.intelligence_status, "COMPLETE")
        self.assertTrue(second.intelligence_ready)

    def test_generation_approval_registers_content_intelligence_for_new_and_reused_asset(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        registrar = FakeContentIntelligenceRegistrar()
        service = CreatorApprovalService(
            storage_dir=Path(temp_dir.name),
            content_intelligence_registrar=registrar,
            commerce_registrar=FakeCommerceRegistrar(),
        )
        ingestion = FakeIngestionService()
        job = generation_job()
        record = generated_record()

        service.approve_generated_record(record, generation_job=job, ingestion_service=ingestion)
        service.approve_generated_record(record, generation_job=job, ingestion_service=ingestion)

        self.assertEqual(len(registrar.calls), 2)
        self.assertEqual(registrar.calls[0][0], 201)
        self.assertEqual(
            registrar.calls[0][1]["source_workflow"],
            "generation_library",
        )
        self.assertEqual(
            registrar.calls[0][1]["approval_identity"]["source_item_id"],
            "generated_image_1",
        )

    def test_photoshoot_approval_writes_photoshoot_asset_metadata(self):
        service = self.make_service()
        ingestion = FakeIngestionService()
        job = generation_job()
        record = generated_record(
            photoshoot_session_id="photoshoot_session_1",
            photoshoot_request_id="photoshoot_request_1",
        )

        result = service.approve_generated_record(
            record,
            generation_job=job,
            ingestion_service=ingestion,
            source_workflow="photoshoot",
            source_session_id="photoshoot_session_1",
            source_metadata={
                "photoshoot_session_id": "photoshoot_session_1",
                "photoshoot_request_id": "photoshoot_request_1",
                "photoshoot_sequence_index": 2,
                "prompt_plan_id": "prompt_plan_1",
                "photoshoot_shot_number": 3,
            },
        )

        self.assertTrue(result.success)
        metadata = ingestion.assets.assets[201].media_metadata
        self.assertEqual(metadata["creator_approval"]["source_workflow"], "photoshoot")
        self.assertEqual(metadata[PHOTOSHOOT_ASSET_METADATA_KEY]["session_id"], "photoshoot_session_1")
        self.assertEqual(metadata[PHOTOSHOOT_ASSET_METADATA_KEY]["request_id"], "photoshoot_request_1")
        self.assertEqual(metadata[PHOTOSHOOT_ASSET_METADATA_KEY]["shot_number"], 3)

    def test_future_workflow_request_uses_same_contract(self):
        service = self.make_service()
        calls = []
        request = CreatorApprovalRequest(
            source=ApprovedSourceIdentity(
                source_workflow="story",
                source_item_id="story_draft_1",
                source_session_id="story_session_1",
            ),
            media_reference="story://draft/1",
            creator_profile_id=7,
            source_metadata={"format": "text_story"},
        )

        first = service.approve_request(request, register_asset=lambda: calls.append("register") or 777)
        second = service.approve_request(request, register_asset=lambda: calls.append("duplicate") or 888)

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(first.asset_id, 777)
        self.assertEqual(second.asset_id, 777)
        self.assertEqual(calls, ["register"])

    def test_generation_approval_registers_commerce_after_intelligence(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        commerce = FakeCommerceRegistrar()
        service = CreatorApprovalService(
            storage_dir=Path(temp_dir.name),
            content_intelligence_registrar=FakeContentIntelligenceRegistrar(),
            commerce_registrar=commerce,
        )
        ingestion = FakeIngestionService()
        job = generation_job()
        record = generated_record()

        result = service.approve_generated_record(
            record,
            generation_job=job,
            ingestion_service=ingestion,
        )

        self.assertTrue(result.success)
        self.assertEqual(len(commerce.calls), 1)
        self.assertEqual(commerce.calls[0][0], 201)
        self.assertEqual(result.commerce_registration_status, "REGISTERED")
        self.assertEqual(result.business_lifecycle_state, "AWAITING_DESTINATION")
        self.assertTrue(result.commerce_ready)
        self.assertEqual(result.commerce_product_ids, ("product-1",))


if __name__ == "__main__":
    unittest.main()
