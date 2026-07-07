import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.models.publishing_job import (
    PublishingJob,
    PublishingLifecycleStatus,
    PublishingJobStatus,
    PublishingMediaLinkStatus,
    build_publishing_status_projection,
)
from app.models.publishing_queue import PublishingQueueItem
from app.providers.publishing import PublishingProviderCapabilities
from app.repositories.publishing_repository import PublishingRepository
from app.services.publishing_service import PublishingService


def job(**overrides):
    now = datetime.now(timezone.utc)
    values = {
        "id": uuid4(),
        "product_id": UUID("00000000-0000-4000-8000-000000000101"),
        "asset_id": 55,
        "provider": "fanvue",
        "provider_account_id": 7,
        "status": "QUEUED",
        "media_link_status": "REQUIRED",
        "provider_status": None,
        "provider_output_url": None,
        "provider_media_id": None,
        "provider_preview_media_id": None,
        "provider_full_media_id": None,
        "provider_metadata": {},
        "failure_reason": None,
        "retry_count": 0,
        "max_retries": 3,
        "next_retry_at": None,
        "upload_started_at": None,
        "uploaded_at": None,
        "completed_at": None,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return PublishingJob.from_row(values)


class FakePublishingRepository:
    def __init__(self):
        self.calls = []
        self.created_job = job()
        self.updated_job = job(status="UPLOADED", media_link_status="REQUIRED")

    def create_job(self, **kwargs):
        self.calls.append(("create_job", kwargs))
        return self.created_job

    def get_job_by_id(self, job_id):
        self.calls.append(("get_job_by_id", job_id))
        return self.created_job

    def list_jobs_for_product(self, product_id, *, limit=50):
        self.calls.append(("list_jobs_for_product", product_id, limit))
        return (self.created_job,)

    def get_queue_item(self, job_id):
        self.calls.append(("get_queue_item", job_id))
        return PublishingQueueItem.from_row(
            {
                **self.created_job.__dict__,
                "status": self.created_job.status.value,
                "media_link_status": self.created_job.media_link_status.value,
                "product_name": "Queued Product",
                "asset_file_path": "asset.jpg",
                "asset_classification": "VIP",
            }
        )

    def project_job(self, value):
        return PublishingRepository().project_job(value)

    def mark_job_uploading(self, job_id, *, provider_status="uploading"):
        self.calls.append(("mark_job_uploading", job_id, provider_status))
        return self.updated_job

    def record_job_upload_result(
        self,
        job_id,
        *,
        upload_payload,
        media_link_required=False,
    ):
        self.calls.append(
            (
                "record_job_upload_result",
                job_id,
                upload_payload,
                media_link_required,
            )
        )
        return self.updated_job

    def mark_job_media_link_created(
        self,
        job_id,
        *,
        media_link,
        provider_metadata=None,
        complete=True,
    ):
        self.calls.append(
            (
                "mark_job_media_link_created",
                job_id,
                media_link,
                provider_metadata,
                complete,
            )
        )
        return self.updated_job

    def mark_job_failed(
        self,
        job_id,
        *,
        failure_reason,
        provider_status="failed",
        provider_metadata=None,
    ):
        self.calls.append(
            (
                "mark_job_failed",
                job_id,
                failure_reason,
                provider_status,
                provider_metadata,
            )
        )
        return self.updated_job

    def schedule_job_retry(self, job_id, *, next_retry_at, failure_reason=None):
        self.calls.append(
            ("schedule_job_retry", job_id, next_retry_at, failure_reason)
        )
        return self.updated_job


class FakeProvider:
    provider_name = "fanvue"

    def __init__(self, upload_result=None):
        self.upload_result = upload_result or {
            "success": True,
            "media_uuid": "media-1",
            "preview_uuid": "preview-1",
            "full_uuid": "full-1",
            "status": "uploaded",
        }

    def publish(self, **kwargs):
        return self.upload_result

    def publish_media_item(self, **kwargs):
        return self.upload_result

    def create_wall_post(self, **kwargs):
        return {"success": True}

    def update(self, publishing_record, update_payload):
        return {"success": False}

    def delete(self, publishing_record):
        return {"success": False}

    def get_publishing_status(self, publishing_record):
        return None if not publishing_record else publishing_record.get("provider_status")

    def get_upload_status(self, publishing_record):
        return self.get_publishing_status(publishing_record)

    def normalize_provider_response(
        self,
        provider_response,
        *,
        default_status,
        provider_error=None,
        fallback_media_ids=True,
    ):
        media_id = provider_response.get("media_uuid")
        return {
            "provider_status": provider_response.get("status") or default_status,
            "provider_error": None if provider_error is None else str(provider_error),
            "provider_metadata": dict(provider_response),
            "provider_media_id": media_id if fallback_media_ids else None,
            "provider_preview_media_id": provider_response.get("preview_uuid")
            or (media_id if fallback_media_ids else None),
            "provider_full_media_id": provider_response.get("full_uuid")
            or (media_id if fallback_media_ids else None),
        }

    def retrieve_provider_output(self, publishing_record):
        return None if not publishing_record else publishing_record.get("provider_output_url")

    def get_capabilities(self):
        return PublishingProviderCapabilities(manual_media_link=True)


class FakeProductCatalog:
    def __init__(self, *, duplicate=False):
        self.duplicate = duplicate
        self.calls = []
        self.product = SimpleNamespace(
            id=UUID("00000000-0000-4000-8000-000000000101"),
            status="ACTIVE",
            media_link="https://fanvue.example/media",
        )

    def validate_media_link_ownership(
        self,
        *,
        product_id,
        creator_profile_id,
        media_link,
    ):
        self.calls.append(
            (
                "validate_media_link_ownership",
                product_id,
                creator_profile_id,
                media_link,
            )
        )
        if self.duplicate:
            raise ValueError("Media link already belongs to another Product.")
        return self.product

    def find_product_by_media_link(self, media_link, *, creator_profile_id=None):
        self.calls.append(
            ("find_product_by_media_link", media_link, creator_profile_id)
        )
        return None

    def complete_publishing_media_link(
        self,
        *,
        product_id,
        creator_profile_id,
        media_link,
    ):
        self.calls.append(
            (
                "complete_publishing_media_link",
                product_id,
                creator_profile_id,
                media_link,
            )
        )
        return self.product


class PublishingJobDomainTests(unittest.TestCase):
    def test_job_model_represents_execution_state_only(self):
        record = job()

        self.assertEqual(record.status, PublishingJobStatus.QUEUED)
        self.assertEqual(
            record.media_link_status,
            PublishingMediaLinkStatus.REQUIRED,
        )
        self.assertTrue(record.can_retry)
        self.assertFalse(hasattr(record, "price_cents"))
        self.assertFalse(hasattr(record, "delivery_type"))
        self.assertFalse(hasattr(record, "approval_status"))
        self.assertFalse(hasattr(record, "product_status"))
        self.assertFalse(hasattr(record, "media_link"))
        self.assertFalse(hasattr(record, "commerce_metadata"))
        self.assertFalse(hasattr(record, "product_editing"))

    def test_publishing_job_fields_are_provider_neutral_execution_state(self):
        field_names = set(PublishingJob.__dataclass_fields__)

        self.assertIn("provider", field_names)
        self.assertIn("provider_account_id", field_names)
        self.assertIn("provider_metadata", field_names)
        self.assertIn("provider_media_id", field_names)
        self.assertIn("provider_output_url", field_names)
        self.assertIn("retry_count", field_names)
        self.assertNotIn("price_cents", field_names)
        self.assertNotIn("approval_status", field_names)
        self.assertNotIn("delivery_type", field_names)
        self.assertNotIn("commerce_metadata", field_names)

    def test_repository_projects_job_to_publishing_record_shape(self):
        record = PublishingRepository().project_job(
            job(
                status="MEDIA_LINK_CREATED",
                media_link_status="CREATED",
                provider_output_url="https://fanvue.example/media",
                provider_media_id="media-1",
                retry_count=1,
            )
        )

        self.assertEqual(record["provider"], "fanvue")
        self.assertEqual(record["publishing_status"], "MEDIA_LINK_VERIFIED")
        self.assertEqual(record["provider_status"], "MEDIA_LINK_CREATED")
        self.assertEqual(record["media_link_status"], "MEDIA_LINK_VERIFIED")
        self.assertEqual(record["provider_output_url"], "https://fanvue.example/media")
        self.assertEqual(record["provider_media_id"], "media-1")
        self.assertEqual(
            record["provider_metadata"]["publishing_job"]["publishing_status"],
            "MEDIA_LINK_VERIFIED",
        )
        self.assertEqual(record["provider_metadata"]["publishing_job"]["retry_count"], 1)

    def test_status_projection_maps_existing_states_to_publishing_lifecycle(self):
        now = datetime.now(timezone.utc)
        cases = (
            (job(status="QUEUED"), PublishingLifecycleStatus.QUEUED.value),
            (job(status="UPLOADING"), PublishingLifecycleStatus.UPLOADING.value),
            (
                job(
                    status="UPLOADED",
                    media_link_status="NOT_REQUIRED",
                    provider_media_id="media-1",
                    uploaded_at=now,
                ),
                PublishingLifecycleStatus.UPLOADED.value,
            ),
            (
                job(status="UPLOADED", media_link_status="REQUIRED"),
                PublishingLifecycleStatus.WAITING_FOR_MEDIA_LINK.value,
            ),
            (
                job(status="MEDIA_LINK_REQUIRED", media_link_status="REQUIRED"),
                PublishingLifecycleStatus.WAITING_FOR_MEDIA_LINK.value,
            ),
            (
                job(status="MEDIA_LINK_CREATED", media_link_status="CREATED"),
                PublishingLifecycleStatus.MEDIA_LINK_VERIFIED.value,
            ),
            (
                job(status="COMPLETED", media_link_status="CREATED"),
                PublishingLifecycleStatus.PUBLISHING_COMPLETE.value,
            ),
            (
                job(status="FAILED", retry_count=0, max_retries=3),
                PublishingLifecycleStatus.RETRY_REQUIRED.value,
            ),
            (
                job(status="FAILED", retry_count=3, max_retries=3),
                PublishingLifecycleStatus.FAILED.value,
            ),
            (
                job(status="CANCELLED"),
                PublishingLifecycleStatus.ARCHIVED.value,
            ),
        )

        for record, expected in cases:
            self.assertEqual(
                build_publishing_status_projection(record).publishing_status,
                expected,
            )

    def test_status_projection_exposes_provider_execution_metadata(self):
        now = datetime.now(timezone.utc)
        record = job(
            status="FAILED",
            provider_status="failed",
            provider_media_id="media-1",
            provider_output_url="https://fanvue.example/media",
            failure_reason="timeout",
            retry_count=1,
            max_retries=3,
            next_retry_at=now,
            upload_started_at=now,
        )

        projection = build_publishing_status_projection(record)

        self.assertEqual(projection.publishing_status, "RETRY_REQUIRED")
        self.assertEqual(projection.provider, "fanvue")
        self.assertEqual(projection.provider_status, "failed")
        self.assertEqual(projection.upload_status, "RETRY_REQUIRED")
        self.assertEqual(projection.retry_state, "RETRY_REQUIRED")
        self.assertEqual(projection.provider_media_id, "media-1")
        self.assertEqual(projection.provider_output_url, "https://fanvue.example/media")
        self.assertEqual(projection.provider_error, "timeout")
        self.assertEqual(projection.upload_started_at, now)
        self.assertEqual(projection.last_attempted_at, now)
        self.assertEqual(projection.retry_scheduled_at, now)

    def test_service_exposes_provider_execution_metadata_contract(self):
        now = datetime.now(timezone.utc)
        service = PublishingService(
            FakePublishingRepository(),
            publishing_provider=FakeProvider(),
        )
        record = job(
            provider_account_id=7,
            status="UPLOADED",
            media_link_status="REQUIRED",
            provider_status="uploaded",
            provider_media_id="media-1",
            provider_output_url="https://fanvue.example/media",
            provider_metadata={"media_uuid": "media-1"},
            upload_started_at=now,
            uploaded_at=now,
            retry_count=1,
        )

        metadata = service.build_provider_execution_metadata(record)

        self.assertEqual(metadata["provider"], "fanvue")
        self.assertEqual(metadata["provider_account_id"], 7)
        self.assertEqual(metadata["provider_status"], "uploaded")
        self.assertEqual(metadata["upload_status"], "UPLOADED")
        self.assertEqual(metadata["provider_media_id"], "media-1")
        self.assertEqual(metadata["provider_output_url"], "https://fanvue.example/media")
        self.assertEqual(metadata["retry_state"], "RETRIED")
        self.assertEqual(metadata["retry_count"], 1)
        self.assertEqual(metadata["provider_metadata"], {"media_uuid": "media-1"})
        self.assertTrue(metadata["capabilities"]["uploads"])
        self.assertTrue(metadata["capabilities"]["manual_media_link"])

    def test_publishing_service_owns_job_orchestration(self):
        repository = FakePublishingRepository()
        service = PublishingService(
            repository,
            publishing_provider=FakeProvider(),
        )
        product_id = UUID("00000000-0000-4000-8000-000000000202")

        created = service.create_publishing_job(
            product_id=product_id,
            asset_id=44,
            provider_account_id=7,
            media_link_required=True,
        )
        service.mark_publishing_job_uploading(created.id)
        service.record_publishing_job_upload_result(
            created.id,
            upload_payload={"provider_status": "uploaded"},
            media_link_required=True,
        )
        service.record_publishing_job_media_link(
            created.id,
            media_link="https://fanvue.example/media",
        )
        retry_at = datetime.now(timezone.utc)
        service.schedule_publishing_job_retry(
            created.id,
            next_retry_at=retry_at,
            failure_reason={"message": "timeout"},
        )

        self.assertEqual(repository.calls[0][0], "create_job")
        self.assertEqual(repository.calls[0][1]["product_id"], product_id)
        self.assertTrue(repository.calls[0][1]["media_link_required"])
        self.assertIn("mark_job_uploading", [call[0] for call in repository.calls])
        self.assertIn("record_job_upload_result", [call[0] for call in repository.calls])
        self.assertIn("mark_job_media_link_created", [call[0] for call in repository.calls])
        self.assertIn("schedule_job_retry", [call[0] for call in repository.calls])

    def test_product_consumable_result_does_not_mutate_product(self):
        service = PublishingService(
            FakePublishingRepository(),
            publishing_provider=FakeProvider(),
        )
        source_job = job(
            status="UPLOADED",
            media_link_status="REQUIRED",
            provider_output_url="https://fanvue.example/media",
            provider_media_id="media-1",
        )

        result = service.build_product_publishing_result(source_job)

        self.assertEqual(result["product_id"], source_job.product_id)
        self.assertEqual(result["publishing_status"], "WAITING_FOR_MEDIA_LINK")
        self.assertEqual(result["upload_status"], "UPLOADED")
        self.assertEqual(result["media_link_status"], "WAITING_FOR_MEDIA_LINK")
        self.assertEqual(result["provider_output_url"], "https://fanvue.example/media")
        self.assertEqual(result["provider_media_id"], "media-1")
        self.assertNotIn("price_cents", result)
        self.assertNotIn("delivery_type", result)
        self.assertNotIn("approval_status", result)
        self.assertNotIn("product_status", result)

    def test_job_upload_helper_records_job_and_legacy_asset_state(self):
        repository = FakePublishingRepository()
        service = PublishingService(
            repository,
            publishing_provider=FakeProvider(),
        )
        legacy_calls = []
        service.record_asset_upload_payload = lambda **kwargs: legacy_calls.append(
            kwargs
        )

        result = service.upload_asset_media_item_for_job(
            job_id=repository.created_job.id,
            fanvue_account_id=7,
            item={"id": 44, "file_path": "asset.jpg", "classification": "VIP"},
            media_link_required=True,
        )

        self.assertEqual(result["job_id"], repository.created_job.id)
        self.assertEqual(repository.calls[0][0], "mark_job_uploading")
        self.assertEqual(repository.calls[1][0], "record_job_upload_result")
        self.assertTrue(repository.calls[1][3])
        self.assertEqual(legacy_calls[0]["asset_id"], 44)
        self.assertEqual(
            legacy_calls[0]["upload_payload"]["provider_media_id"],
            "media-1",
        )
        self.assertEqual(result["job"], repository.updated_job)

    def test_upload_success_keeps_execution_status_uploaded(self):
        source = Path("app/repositories/publishing_repository.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("PublishingJobStatus.UPLOADED.value", source)
        self.assertNotIn(
            "status = (\n            PublishingJobStatus.MEDIA_LINK_REQUIRED",
            source,
        )

    def test_job_upload_helper_records_failure_metadata(self):
        repository = FakePublishingRepository()
        service = PublishingService(
            repository,
            publishing_provider=FakeProvider(
                upload_result={
                    "success": False,
                    "error": "fanvue timeout",
                    "status": "failed",
                }
            ),
        )
        legacy_calls = []
        service.record_asset_upload_payload = lambda **kwargs: legacy_calls.append(
            kwargs
        )

        result = service.upload_asset_media_item_for_job(
            job_id=repository.created_job.id,
            fanvue_account_id=7,
            item={"id": 44, "file_path": "asset.jpg", "classification": "VIP"},
            media_link_required=True,
        )

        self.assertFalse(result["upload_result"]["success"])
        self.assertEqual(repository.calls[0][0], "mark_job_uploading")
        self.assertEqual(repository.calls[1][0], "mark_job_failed")
        self.assertIn("fanvue timeout", repository.calls[1][2])
        self.assertEqual(legacy_calls[0]["upload_payload"]["provider_status"], "failed")

    def test_retry_requeues_existing_job_without_creating_duplicate(self):
        repository = FakePublishingRepository()
        repository.created_job = job(
            status="FAILED",
            failure_reason="timeout",
            retry_count=1,
            max_retries=3,
        )
        service = PublishingService(
            repository,
            publishing_provider=FakeProvider(),
        )
        service.record_asset_upload_payload = lambda **kwargs: None

        result = service.retry_publishing_queue_item(
            repository.created_job.id,
            provider_account_id=7,
        )

        call_names = [call[0] for call in repository.calls]
        self.assertTrue(result["success"])
        self.assertIn("schedule_job_retry", call_names)
        self.assertIn("mark_job_uploading", call_names)
        self.assertIn("record_job_upload_result", call_names)
        self.assertNotIn("create_job", call_names)

    def test_retry_transition_returns_to_queued_state(self):
        source = Path("app/repositories/publishing_repository.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("PublishingJobStatus.QUEUED.value", source)
        self.assertIn('"retry_queued"', source)

    def test_media_link_validation_detects_missing_invalid_and_duplicate_links(self):
        service = PublishingService(
            FakePublishingRepository(),
            publishing_provider=FakeProvider(),
        )
        product_id = UUID("00000000-0000-4000-8000-000000000101")

        missing = service.validate_publishing_media_link(
            "",
            product_id=product_id,
            creator_profile_id=2,
            product_catalog_service=FakeProductCatalog(),
        )
        invalid = service.validate_publishing_media_link(
            "not-a-url",
            product_id=product_id,
            creator_profile_id=2,
            product_catalog_service=FakeProductCatalog(),
        )
        duplicate = service.validate_publishing_media_link(
            "https://fanvue.example/media",
            product_id=product_id,
            creator_profile_id=2,
            product_catalog_service=FakeProductCatalog(duplicate=True),
        )

        self.assertFalse(missing["valid"])
        self.assertIn("missing_media_link", missing["errors"])
        self.assertFalse(invalid["valid"])
        self.assertIn("invalid_media_link_url", invalid["errors"])
        self.assertFalse(duplicate["valid"])
        self.assertIn(
            "Media link already belongs to another Product.",
            duplicate["errors"],
        )

    def test_media_link_workflow_completes_job_then_product_catalog_activation(self):
        repository = FakePublishingRepository()
        repository.created_job = job(
            status="UPLOADED",
            media_link_status="REQUIRED",
        )
        service = PublishingService(
            repository,
            publishing_provider=FakeProvider(),
        )
        catalog = FakeProductCatalog()

        result = service.complete_publishing_media_link_workflow(
            repository.created_job.id,
            creator_profile_id=2,
            media_link=" https://fanvue.example/media ",
            product_catalog_service=catalog,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["media_link"], "https://fanvue.example/media")
        media_calls = [
            call for call in repository.calls if call[0] == "mark_job_media_link_created"
        ]
        self.assertEqual(len(media_calls), 2)
        self.assertFalse(media_calls[0][4])
        self.assertTrue(media_calls[1][4])
        self.assertIn(
            "complete_publishing_media_link",
            [call[0] for call in catalog.calls],
        )

    def test_media_link_workflow_requires_waiting_job(self):
        repository = FakePublishingRepository()
        repository.created_job = job(status="QUEUED")
        service = PublishingService(
            repository,
            publishing_provider=FakeProvider(),
        )

        result = service.complete_publishing_media_link_workflow(
            repository.created_job.id,
            creator_profile_id=2,
            media_link="https://fanvue.example/media",
            product_catalog_service=FakeProductCatalog(),
        )

        self.assertFalse(result["success"])
        self.assertIn(
            "publishing_job_not_waiting_for_media_link",
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
