import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.dashboard.navigation import (
    DASHBOARD_NAVIGATION_GROUPS,
    DASHBOARD_PAGE_LABELS,
    DASHBOARD_PAGE_OPTIONS,
    PROFILE_LOCKED_PAGES,
)
from app.models.publishing_queue import (
    PublishingQueueItem,
    build_publishing_queue_summary,
)
from app.models.product import ProductApprovalStatus
from app.services.product_catalog_service import ProductCatalogService


class _FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}

    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return False

        return _noop


sys.modules.setdefault("streamlit", _FakeStreamlit())

from app.dashboard.pages.publishing_queue import filter_queue_items


def queue_item(**overrides):
    now = datetime.now(timezone.utc)
    values = {
        "id": uuid4(),
        "product_id": UUID("00000000-0000-4000-8000-000000000301"),
        "asset_id": 101,
        "provider": "fanvue",
        "provider_account_id": 7,
        "status": "QUEUED",
        "media_link_status": "REQUIRED",
        "provider_status": None,
        "provider_output_url": None,
        "provider_media_id": None,
        "provider_preview_media_id": None,
        "provider_full_media_id": None,
        "provider_metadata": {"source": "test"},
        "failure_reason": None,
        "retry_count": 0,
        "max_retries": 3,
        "next_retry_at": None,
        "upload_started_at": None,
        "uploaded_at": None,
        "completed_at": None,
        "created_at": now - timedelta(hours=2),
        "updated_at": now,
        "product_name": "Queued Product",
        "asset_file_path": "data/uploads/queued.jpg",
        "asset_classification": "VIP_IMAGE",
    }
    values.update(overrides)
    return PublishingQueueItem.from_row(values)


class PublishingQueueTests(unittest.TestCase):
    def test_publishing_queue_is_registered_in_navigation(self):
        self.assertIn("Publishing Queue", DASHBOARD_PAGE_OPTIONS)
        self.assertIn("Publishing Queue", PROFILE_LOCKED_PAGES)
        self.assertEqual(
            DASHBOARD_PAGE_LABELS["Publishing Queue"],
            "Publishing: Queue",
        )
        publishing_group = next(
            group
            for group in DASHBOARD_NAVIGATION_GROUPS
            if group.label == "Publishing"
        )
        self.assertEqual(publishing_group.items[0].page, "Publishing Queue")

    def test_publishing_queue_page_is_presentation_only(self):
        source = Path("app/dashboard/pages/publishing_queue.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("PublishingService", source)
        self.assertIn("list_publishing_queue_items", source)
        self.assertIn("upload_publishing_queue_item", source)
        self.assertIn("retry_publishing_queue_item", source)
        self.assertIn("complete_publishing_media_link_workflow", source)
        self.assertNotIn("ProductRepository", source)
        self.assertNotIn("ProductCatalogService", source)
        self.assertNotIn("ProductReviewService", source)
        self.assertNotIn("FanvuePublishingProvider", source)

    def test_main_router_exposes_publishing_queue(self):
        source = Path("app/dashboard/main.py").read_text(encoding="utf-8")

        self.assertIn("render_publishing_queue", source)
        self.assertIn('== "Publishing Queue"', source)
        self.assertIn("creator_profile=active_creator_profile", source)

    def test_publishing_queue_exposes_manual_media_link_controls(self):
        source = Path("app/dashboard/pages/publishing_queue.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("Open Fanvue", source)
        self.assertIn("Paste Media Link", source)
        self.assertIn("Verify Link", source)
        self.assertIn("_run_media_link_action", source)

    def test_queue_item_summary_flags_retry_and_upload_visibility(self):
        failed = queue_item(
            status="FAILED",
            failure_reason="timeout",
            retry_count=1,
            max_retries=3,
            product_name="Failed Product",
        )
        queued = queue_item(product_name="Queued Product")
        waiting = queue_item(
            status="UPLOADED",
            media_link_status="REQUIRED",
            asset_file_path=None,
            product_name="Waiting Product",
        )

        self.assertTrue(failed.retry_visible)
        self.assertTrue(failed.failed_upload)
        self.assertEqual(failed.status, "RETRY_REQUIRED")
        self.assertEqual(failed.upload_status, "RETRY_REQUIRED")
        self.assertEqual(failed.retry_state, "RETRY_REQUIRED")
        self.assertIsNotNone(failed.build_upload_item(allow_retry=True))
        self.assertTrue(queued.ready_to_upload)
        self.assertTrue(waiting.waiting_for_media_link)
        self.assertEqual(waiting.status, "WAITING_FOR_MEDIA_LINK")

        summary = build_publishing_queue_summary((failed, queued, waiting))
        self.assertEqual(summary.total_jobs, 3)
        self.assertEqual(summary.ready_to_upload, 1)
        self.assertEqual(summary.waiting_for_media_link, 1)
        self.assertEqual(summary.failed_uploads, 1)
        self.assertEqual(summary.retryable, 1)
        self.assertEqual(summary.providers, ("fanvue",))

    def test_queue_search_and_filters(self):
        now = datetime.now(timezone.utc)
        queued = queue_item(
            product_name="Queued Product",
            uploaded_at=now - timedelta(hours=3),
        )
        failed = queue_item(
            product_name="Failed Product",
            status="FAILED",
            failure_reason="timeout",
            retry_count=1,
            max_retries=3,
            uploaded_at=now - timedelta(days=2),
        )
        complete = queue_item(
            product_name="Complete Product",
            provider="telegram",
            status="COMPLETED",
            media_link_status="CREATED",
            uploaded_at=now - timedelta(days=10),
        )
        items = (queued, failed, complete)

        self.assertEqual(
            filter_queue_items(items, search="failed", now=now),
            (failed,),
        )
        self.assertEqual(
            filter_queue_items(items, status="PUBLISHING_COMPLETE", now=now),
            (complete,),
        )
        self.assertEqual(
            filter_queue_items(items, provider="telegram", now=now),
            (complete,),
        )
        self.assertEqual(
            filter_queue_items(items, retry_filter="Retryable", now=now),
            (failed,),
        )
        self.assertEqual(
            filter_queue_items(items, retry_filter="Retry Required", now=now),
            (failed,),
        )
        self.assertEqual(
            filter_queue_items(items, retry_required=True, now=now),
            (failed,),
        )
        self.assertEqual(
            filter_queue_items(items, upload_date_filter="Last 24 Hours", now=now),
            (queued,),
        )
        self.assertEqual(
            filter_queue_items(items, ready_to_upload=True, now=now),
            (queued,),
        )
        self.assertEqual(
            filter_queue_items(items, failed_upload=True, now=now),
            (failed,),
        )

    def test_queue_item_exposes_provider_metadata_status_fields(self):
        now = datetime.now(timezone.utc)
        item = queue_item(
            status="UPLOADED",
            media_link_status="REQUIRED",
            provider_status="uploaded",
            provider_media_id="media-1",
            provider_output_url="https://fanvue.example/media",
            uploaded_at=now,
            upload_started_at=now - timedelta(minutes=2),
            next_retry_at=now + timedelta(hours=1),
        )

        self.assertEqual(item.status, "WAITING_FOR_MEDIA_LINK")
        self.assertEqual(item.provider_status, "uploaded")
        self.assertEqual(item.upload_status, "UPLOADED")
        self.assertEqual(item.media_link_status, "WAITING_FOR_MEDIA_LINK")
        self.assertEqual(item.provider_media_id, "media-1")
        self.assertEqual(item.provider_output_url, "https://fanvue.example/media")
        self.assertEqual(item.upload_completed_at, now)
        self.assertEqual(item.last_attempted_at, now)
        self.assertEqual(item.retry_scheduled_at, now + timedelta(hours=1))

    def test_approved_product_enqueue_delegates_to_publishing_service(self):
        class FakePublishing:
            def __init__(self):
                self.calls = []

            def ensure_product_publishing_job(self, **kwargs):
                self.calls.append(kwargs)

        publishing = FakePublishing()
        service = ProductCatalogService.__new__(ProductCatalogService)
        service.publishing = publishing
        product_id = UUID("00000000-0000-4000-8000-000000000401")
        product = SimpleNamespace(
            id=product_id,
            legacy_content_item_id=None,
        )
        asset = SimpleNamespace(id=77, fanvue_account_id=9)

        service._ensure_publishing_job_for_approved_product(
            product,
            (asset,),
            approval_status=ProductApprovalStatus.READY_TO_PUBLISH,
        )

        self.assertEqual(len(publishing.calls), 1)
        call = publishing.calls[0]
        self.assertEqual(call["product_id"], product_id)
        self.assertEqual(call["asset_id"], 77)
        self.assertEqual(call["provider_account_id"], 9)
        self.assertTrue(call["media_link_required"])
        self.assertEqual(
            call["provider_metadata"]["source"],
            "ProductCatalogService.approve_product",
        )

    def test_creator_workspace_targets_publishing_queue(self):
        source = Path("app/dashboard/pages/creator_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('primary_target="Publishing Queue"', source)
        self.assertIn('"target": "Publishing Queue"', source)


if __name__ == "__main__":
    unittest.main()
