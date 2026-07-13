import unittest
import inspect
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import app.services.publishing_service as publishing_service_module
from app.models.publishing_job import PublishingJob, PublishingJobStatus, PublishingMediaLinkStatus
from app.providers.publishing import PublishingProviderCapabilities
from app.repositories.publishing_repository import PublishingRepository
from app.services.publishing_service import PublishingService


class FakePublishingRepository:
    def __init__(self):
        self.asset_record = None
        self.product_record = None
        self.asset_calls = []
        self.product_calls = []

    def get_by_asset_id(self, asset_id):
        self.asset_calls.append(asset_id)
        return self.asset_record

    def get_by_product_id(self, product_id):
        self.product_calls.append(product_id)
        return self.product_record

    def project_product(self, row):
        return PublishingRepository().project_product(row)


class FakeJobRepository(FakePublishingRepository):
    def __init__(self):
        super().__init__()
        self.jobs = {}
        self.asset_lookup_calls = []

    def get_open_job_for_asset(self, asset_id, *, provider=None, provider_metadata_filter=None):
        self.asset_lookup_calls.append((asset_id, provider, provider_metadata_filter))
        for job in self.jobs.values():
            if job.asset_id == asset_id and job.product_id is None and job.status not in {
                PublishingJobStatus.COMPLETED,
                PublishingJobStatus.CANCELLED,
            }:
                route = (job.provider_metadata or {}).get("route_owner")
                if provider_metadata_filter and route != provider_metadata_filter.get("route_owner"):
                    continue
                return job
        return None

    def create_job(self, **kwargs):
        now = datetime.now()
        job = PublishingJob(
            id=uuid4(),
            product_id=kwargs.get("product_id"),
            asset_id=kwargs.get("asset_id"),
            provider=kwargs.get("provider"),
            provider_account_id=kwargs.get("provider_account_id"),
            status=PublishingJobStatus.QUEUED,
            media_link_status=(
                PublishingMediaLinkStatus.REQUIRED
                if kwargs.get("media_link_required")
                else PublishingMediaLinkStatus.NOT_REQUIRED
            ),
            provider_status=None,
            provider_output_url=None,
            provider_media_id=None,
            provider_preview_media_id=None,
            provider_full_media_id=None,
            provider_metadata=kwargs.get("provider_metadata") or {},
            failure_reason=None,
            retry_count=0,
            max_retries=kwargs.get("max_retries") or 3,
            next_retry_at=None,
            upload_started_at=None,
            uploaded_at=None,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        self.jobs[job.id] = job
        return job

    def get_job_by_id(self, job_id):
        return self.jobs.get(job_id)

    def mark_job_media_link_created(self, job_id, *, media_link, provider_metadata=None, complete=True):
        job = self.jobs[job_id]
        updated = PublishingJob(
            **{
                **job.__dict__,
                "status": PublishingJobStatus.COMPLETED if complete else PublishingJobStatus.MEDIA_LINK_CREATED,
                "media_link_status": PublishingMediaLinkStatus.CREATED,
                "provider_output_url": media_link,
                "provider_metadata": {**dict(job.provider_metadata), **dict(provider_metadata or {})},
                "completed_at": datetime.now() if complete else job.completed_at,
                "updated_at": datetime.now(),
            }
        )
        self.jobs[job_id] = updated
        return updated


class FakeCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_obj


class FakeUploader:
    def __init__(self, *, fanvue_account_id=None):
        self.fanvue_account_id = fanvue_account_id
        self.calls = []

    def upload_media_item(self, item):
        self.calls.append(item)
        if "preview" in item["file_path"]:
            return {
                "success": True,
                "preview_uuid": "preview-id",
                "media_uuid": "preview-media",
            }
        return {
            "success": True,
            "full_uuid": "full-id",
            "media_uuid": "full-media",
        }


class FakePublishingProvider:
    provider_name = "fake"

    def __init__(self):
        self.publish_calls = []

    def publish(self, **kwargs):
        self.publish_calls.append(kwargs)
        return {
            "success": True,
            "preview_result": {"success": True},
            "full_result": {"success": True},
        }

    def publish_media_item(self, **kwargs):
        self.publish_calls.append(kwargs)
        return {
            "success": True,
            "media_uuid": "media",
            "preview_uuid": "preview",
            "full_uuid": "full",
        }

    def create_wall_post(self, **kwargs):
        self.publish_calls.append(kwargs)
        return {
            "success": True,
            "sent": True,
            "payload": kwargs,
        }

    def update(self, publishing_record, update_payload):
        return {"success": False}

    def delete(self, publishing_record):
        return {"success": False}

    def get_publishing_status(self, publishing_record):
        if not publishing_record:
            return None
        return publishing_record.get("provider_status")

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
        return {
            "provider_status": default_status,
            "provider_error": provider_error,
            "provider_metadata": dict(provider_response or {}),
            "provider_media_id": None,
            "provider_preview_media_id": None,
            "provider_full_media_id": None,
        }

    def retrieve_provider_output(self, publishing_record):
        if not publishing_record:
            return None
        return publishing_record.get("provider_output_url")

    def get_capabilities(self):
        return PublishingProviderCapabilities()


class PublishingServiceTests(unittest.TestCase):
    def test_service_does_not_import_fanvue_upload_service_directly(self):
        source = inspect.getsource(publishing_service_module)

        self.assertNotIn("fanvue_media_upload_service", source)
        self.assertNotIn("FanvueMediaUploadService", source)

    def test_delegates_asset_and_product_reads_to_repository(self):
        repository = FakePublishingRepository()
        service = PublishingService(repository)
        product_id = UUID("00000000-0000-4000-8000-000000000002")

        repository.asset_record = {"asset_id": 10, "provider_status": "completed"}
        repository.product_record = {
            "product_id": product_id,
            "provider_status": "READY",
        }

        self.assertEqual(service.get_by_asset_id(10), repository.asset_record)
        self.assertEqual(
            service.get_by_product_id(product_id),
            repository.product_record,
        )
        self.assertEqual(repository.asset_calls, [10])
        self.assertEqual(repository.product_calls, [product_id])

    def test_provider_status_helper_handles_missing_record(self):
        service = PublishingService(FakePublishingRepository())

        self.assertIsNone(service.get_provider_status(None))
        self.assertEqual(
            service.get_provider_status({"provider_status": "uploaded"}),
            "uploaded",
        )

    def test_has_provider_media_checks_all_provider_media_fields(self):
        service = PublishingService(FakePublishingRepository())

        self.assertFalse(service.has_provider_media(None))
        self.assertFalse(service.has_provider_media({}))
        self.assertTrue(
            service.has_provider_media({"provider_preview_media_id": "preview"})
        )
        self.assertTrue(
            service.has_provider_media({"provider_full_media_id": "full"})
        )
        self.assertTrue(
            service.has_provider_media({"provider_media_id": "media"})
        )

    def test_provider_output_helper_returns_output_url(self):
        service = PublishingService(FakePublishingRepository())

        self.assertIsNone(service.get_provider_output(None))
        self.assertEqual(
            service.get_provider_output(
                {"provider_output_url": "https://fanvue.example/link"}
            ),
            "https://fanvue.example/link",
        )

    def test_projects_legacy_product_record_with_delivery_type_context(self):
        service = PublishingService(FakePublishingRepository())
        product_id = UUID("00000000-0000-4000-8000-000000000021")
        product = SimpleNamespace(
            id=product_id,
            legacy_content_item_id=88,
            media_link=None,
            fulfillment_status=None,
            fulfillment_strategy=None,
            delivery_type="FREE",
            metadata={"delivery_type": "PAID"},
            created_at=None,
            updated_at=None,
        )

        record = service.project_legacy_product_record(product)

        self.assertEqual(record["product_id"], product_id)
        self.assertEqual(record["asset_id"], 88)
        self.assertEqual(record["delivery_type"], "FREE")
        self.assertIsNone(record["provider_output_url"])
        self.assertIsNone(record["provider_status"])

    def test_projects_experience_readiness_without_owning_experience(self):
        service = PublishingService(FakePublishingRepository())
        experience = SimpleNamespace(
            experience_id="experience-1",
            ordered_asset_ids=(10, 11),
        )

        readiness = service.project_experience_readiness(
            experience,
            asset_records=(
                {"provider_full_media_id": "full-10"},
                {"provider_status": "pending"},
            ),
        )

        self.assertEqual(readiness.experience_id, "experience-1")
        self.assertEqual(readiness.status, "partial")
        self.assertEqual(readiness.asset_count, 2)
        self.assertEqual(readiness.ready_asset_count, 1)
        self.assertFalse(readiness.compatibility)
        self.assertEqual(readiness.metadata["ordered_asset_ids"], (10, 11))
        self.assertEqual(readiness.metadata["readiness_ratio"], 0.5)
        self.assertFalse(readiness.metadata["owns_experience_state"])

    def test_convenience_methods_read_then_interpret_records(self):
        repository = FakePublishingRepository()
        product_id = UUID("00000000-0000-4000-8000-000000000003")
        repository.asset_record = {
            "provider_status": "completed",
            "provider_media_id": "media",
        }
        repository.product_record = {
            "provider_status": "READY",
            "provider_output_url": "https://fanvue.example/link",
        }
        service = PublishingService(repository)

        self.assertEqual(service.get_asset_provider_status(7), "completed")
        self.assertTrue(service.asset_has_provider_media(7))
        self.assertEqual(service.get_product_provider_status(product_id), "READY")
        self.assertFalse(service.product_has_provider_media(product_id))
        self.assertEqual(
            service.get_product_provider_output(product_id),
            "https://fanvue.example/link",
        )

    def test_build_upload_success_payload_normalizes_provider_fields(self):
        service = PublishingService(FakePublishingRepository())

        payload = service.build_upload_success_payload(
            {
                "success": True,
                "media_uuid": "media",
                "preview_uuid": None,
                "full_uuid": "full",
                "status": None,
            }
        )

        self.assertEqual(payload["provider_status"], "uploaded")
        self.assertIsNone(payload["provider_error"])
        self.assertEqual(payload["provider_media_id"], "media")
        self.assertEqual(payload["provider_preview_media_id"], "media")
        self.assertEqual(payload["provider_full_media_id"], "full")
        self.assertEqual(payload["provider_metadata"]["media_uuid"], "media")

    def test_build_upload_failure_payload_normalizes_error_and_metadata(self):
        service = PublishingService(FakePublishingRepository())

        payload = service.build_upload_failure_payload(
            {
                "success": False,
                "preview_uuid": "preview",
                "full_uuid": "full",
                "error": {"message": "timeout"},
            }
        )

        self.assertEqual(payload["provider_status"], "failed")
        self.assertEqual(payload["provider_error"], "{'message': 'timeout'}")
        self.assertIsNone(payload["provider_media_id"])
        self.assertEqual(payload["provider_preview_media_id"], "preview")
        self.assertEqual(payload["provider_full_media_id"], "full")

    def test_build_provider_status_update_accepts_non_mapping_metadata(self):
        service = PublishingService(FakePublishingRepository())

        payload = service.build_provider_status_update(
            provider_status="retrying",
            provider_error=None,
            provider_metadata="raw response",
        )

        self.assertEqual(payload["provider_status"], "retrying")
        self.assertIsNone(payload["provider_error"])
        self.assertEqual(payload["provider_metadata"], {"raw": "raw response"})

    def test_provider_status_display_preserves_fanvue_asset_strings(self):
        service = PublishingService(FakePublishingRepository())

        self.assertEqual(
            service.get_provider_status_display(None, provider_name="Fanvue"),
            ("Not uploaded to Fanvue", "No local asset is attached."),
        )
        self.assertEqual(
            service.get_provider_status_display(
                {
                    "provider_status": "failed",
                    "provider_error": None,
                },
                provider_name="Fanvue",
            ),
            ("Failed Fanvue upload", "failed"),
        )
        self.assertEqual(
            service.get_provider_status_display(
                {"provider_full_media_id": "full-id"},
                provider_name="Fanvue",
            ),
            ("Uploaded to Fanvue", "full-id"),
        )

    def test_product_provider_status_display_preserves_rollup_strings(self):
        service = PublishingService(FakePublishingRepository())
        uploaded = {"provider_full_media_id": "full-id"}
        pending = {}
        failed = {"provider_status": "failed"}

        self.assertEqual(
            service.get_product_provider_status_display(
                {"provider_output_url": "https://fanvue.example/link"},
                [],
                provider_name="Fanvue",
            ),
            ("Fanvue URL available", "https://fanvue.example/link"),
        )
        self.assertEqual(
            service.get_product_provider_status_display(
                None,
                [uploaded, uploaded],
                provider_name="Fanvue",
            ),
            ("Uploaded to Fanvue", "All attached assets have Fanvue media IDs."),
        )
        self.assertEqual(
            service.get_product_provider_status_display(
                None,
                [uploaded, pending],
                provider_name="Fanvue",
            ),
            ("Uploaded to Fanvue", "Some attached assets have Fanvue media IDs."),
        )
        self.assertEqual(
            service.get_product_provider_status_display(
                None,
                [failed, uploaded],
                provider_name="Fanvue",
            ),
            ("Failed Fanvue upload", "At least one asset failed upload."),
        )

    def test_upload_asset_media_pair_delegates_to_provider_uploader(self):
        created_uploaders = []

        def uploader_factory(*, fanvue_account_id=None):
            uploader = FakeUploader(fanvue_account_id=fanvue_account_id)
            created_uploaders.append(uploader)
            return uploader

        service = PublishingService(
            FakePublishingRepository(),
            media_upload_service_factory=uploader_factory,
        )

        result = service.upload_asset_media_pair(
            asset_id=22,
            fanvue_account_id=9,
            preview_path="data/previews/22_preview.jpg",
            full_path="data/uploads/22_full.jpg",
            classification="PREMIUM",
        )

        self.assertTrue(result["success"])
        self.assertEqual(created_uploaders[0].fanvue_account_id, 9)
        self.assertEqual(
            created_uploaders[0].calls,
            [
                {
                    "id": 22,
                    "file_path": "data/previews/22_preview.jpg",
                    "classification": "PREMIUM",
                },
                {
                    "id": 22,
                    "file_path": "data/uploads/22_full.jpg",
                    "classification": "PREMIUM",
                },
            ],
        )

    def test_upload_asset_media_pair_delegates_to_publishing_provider(self):
        provider = FakePublishingProvider()
        service = PublishingService(
            FakePublishingRepository(),
            publishing_provider=provider,
        )

        result = service.upload_asset_media_pair(
            asset_id=22,
            fanvue_account_id=9,
            preview_path="data/previews/22_preview.jpg",
            full_path="data/uploads/22_full.jpg",
            classification="PREMIUM",
        )

        self.assertTrue(result["success"])
        self.assertEqual(
            provider.publish_calls,
            [
                {
                    "asset_id": 22,
                    "provider_account_id": 9,
                    "preview_path": "data/previews/22_preview.jpg",
                    "full_path": "data/uploads/22_full.jpg",
                    "classification": "PREMIUM",
                }
            ],
        )

    def test_upload_asset_media_item_delegates_to_publishing_provider(self):
        provider = FakePublishingProvider()
        service = PublishingService(
            FakePublishingRepository(),
            publishing_provider=provider,
        )

        result = service.upload_asset_media_item(
            fanvue_account_id=9,
            item={
                "id": 22,
                "file_path": "data/uploads/22_full.jpg",
                "classification": "PREMIUM",
            },
        )

        self.assertTrue(result["success"])
        self.assertEqual(
            provider.publish_calls,
            [
                {
                    "provider_account_id": 9,
                    "item": {
                        "id": 22,
                        "file_path": "data/uploads/22_full.jpg",
                        "classification": "PREMIUM",
                    },
                }
            ],
        )

    def test_asset_only_publishing_job_reuses_route_job(self):
        repository = FakeJobRepository()
        provider = FakePublishingProvider()
        service = PublishingService(repository, publishing_provider=provider)

        first = service.ensure_asset_publishing_job(
            asset_id=44,
            media_link_required=True,
            provider_metadata={"route_owner": "CUSTOMER_CONVERSATIONS"},
            route_owner="CUSTOMER_CONVERSATIONS",
        )
        second = service.ensure_asset_publishing_job(
            asset_id=44,
            media_link_required=True,
            provider_metadata={"route_owner": "CUSTOMER_CONVERSATIONS"},
            route_owner="CUSTOMER_CONVERSATIONS",
        )

        self.assertEqual(first.id, second.id)
        self.assertIsNone(first.product_id)
        self.assertEqual(first.media_link_status, PublishingMediaLinkStatus.REQUIRED)

    def test_asset_only_media_link_workflow_completes_without_product(self):
        repository = FakeJobRepository()
        provider = FakePublishingProvider()
        service = PublishingService(repository, publishing_provider=provider)
        job = service.ensure_asset_publishing_job(
            asset_id=45,
            media_link_required=True,
            provider_metadata={"route_owner": "CUSTOMER_CONVERSATIONS"},
            route_owner="CUSTOMER_CONVERSATIONS",
        )
        repository.jobs[job.id] = PublishingJob(
            **{
                **job.__dict__,
                "status": PublishingJobStatus.UPLOADED,
                "media_link_status": PublishingMediaLinkStatus.REQUIRED,
            }
        )

        result = service.complete_publishing_media_link_workflow(
            job.id,
            creator_profile_id=7,
            media_link="https://fanvue.example/link",
        )

        self.assertTrue(result["success"])
        self.assertIsNone(result["product"])
        self.assertEqual(result["media_link"], "https://fanvue.example/link")
        self.assertEqual(repository.jobs[job.id].status, PublishingJobStatus.COMPLETED)

    def test_create_wall_post_delegates_to_publishing_provider(self):
        provider = FakePublishingProvider()
        service = PublishingService(
            FakePublishingRepository(),
            publishing_provider=provider,
        )

        result = service.create_wall_post(
            fanvue_account_id=9,
            text="hello",
            media_ids=["media-1"],
            audience="followers-and-subscribers",
        )

        self.assertTrue(result["success"])
        self.assertEqual(
            provider.publish_calls,
            [
                {
                    "provider_account_id": 9,
                    "text": "hello",
                    "media_ids": ["media-1"],
                    "audience": "followers-and-subscribers",
                }
            ],
        )

    def test_mark_asset_upload_not_requested_persists_provider_state(self):
        connection = FakeConnection()
        service = PublishingService(
            FakePublishingRepository(),
            connection_factory=lambda: connection,
        )

        service.mark_asset_upload_not_requested(
            asset_id=23,
            fanvue_account_id=8,
        )

        query, params = connection.cursor_obj.calls[0]
        self.assertIn("fanvue_upload_status = 'not_requested'", query)
        self.assertEqual(params, (23, 8))

    def test_record_asset_upload_success_persists_provider_media_ids(self):
        connection = FakeConnection()
        service = PublishingService(
            FakePublishingRepository(),
            connection_factory=lambda: connection,
        )

        service.record_asset_upload_success(
            asset_id=24,
            fanvue_account_id=7,
            preview_result={"preview_uuid": "preview"},
            full_result={"full_uuid": "full"},
        )

        query, params = connection.cursor_obj.calls[0]
        self.assertIn("fanvue_upload_status = 'completed'", query)
        self.assertIn("fanvue_media_preview_uuid = %s", query)
        self.assertEqual(params, ("preview", "full", 24, 7))

    def test_record_asset_upload_failure_persists_provider_error(self):
        connection = FakeConnection()
        service = PublishingService(
            FakePublishingRepository(),
            connection_factory=lambda: connection,
        )

        service.record_asset_upload_failure(
            asset_id=25,
            fanvue_account_id=6,
            error={"message": "timeout"},
        )

        query, params = connection.cursor_obj.calls[0]
        self.assertIn("fanvue_upload_status = 'failed'", query)
        self.assertEqual(params, ("{'message': 'timeout'}", 25, 6))


if __name__ == "__main__":
    unittest.main()
