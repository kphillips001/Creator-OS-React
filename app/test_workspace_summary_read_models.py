import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.product import (
    ProductApprovalStatus,
    ProductDeliveryType,
    ProductFulfillmentStatus,
    ProductStatus,
    product_metadata_with_approval,
)
from app.services import workspace_summary_read_models as read_models


def metric_values(summary):
    return {metric.label: metric.value for metric in summary.metrics}


class WorkspaceSummaryReadModelTests(unittest.TestCase):
    def test_asset_summary_preserves_workspace_metric_labels(self):
        now = datetime.now(timezone.utc)
        assets = [
            SimpleNamespace(
                created_at=now - timedelta(days=1),
                status="active",
                is_active=True,
                classification="selfie",
                ready_for_rotation=True,
                blurred_preview_path="preview.jpg",
                fanvue_media_preview_uuid=None,
                fanvue_media_full_uuid=None,
                fanvue_upload_error=None,
            ),
            SimpleNamespace(
                created_at=now,
                status="processing",
                is_active=True,
                classification=None,
                ready_for_rotation=False,
                blurred_preview_path=None,
                fanvue_media_preview_uuid=None,
                fanvue_media_full_uuid=None,
                fanvue_upload_error="failed",
            ),
        ]

        values = metric_values(read_models.build_asset_summary(assets, now=now))

        self.assertEqual(values["Total Assets"], "2")
        self.assertEqual(values["Recently Imported"], "2")
        self.assertEqual(values["Assets Processing"], "1")
        self.assertEqual(values["Asset Library"], "2")
        self.assertEqual(values["Classified Assets"], "1")
        self.assertEqual(values["Needs Classification"], "1")
        self.assertEqual(values["Ready for Rotation"], "1")
        self.assertEqual(values["Preview Ready"], "1")
        self.assertEqual(values["Asset Alerts"], "1")

    def test_product_summary_preserves_catalog_readiness_counts(self):
        products = [
            SimpleNamespace(
                status=ProductStatus.ACTIVE,
                price_cents=1999,
                fulfillment_status=ProductFulfillmentStatus.READY,
                delivery_type=ProductDeliveryType.PAID,
                metadata=product_metadata_with_approval(
                    {"delivery_type": ProductDeliveryType.PAID.value},
                    ProductApprovalStatus.READY_TO_PUBLISH,
                ),
            ),
            SimpleNamespace(
                status=ProductStatus.ACTIVE,
                price_cents=None,
                fulfillment_status=ProductFulfillmentStatus.NOT_READY,
                delivery_type=ProductDeliveryType.FREE,
            ),
            SimpleNamespace(
                status=ProductStatus.DRAFT.value,
                price_cents=None,
                fulfillment_status=ProductFulfillmentStatus.FAILED.value,
                delivery_type=ProductDeliveryType.PAID.value,
            ),
        ]
        counts = {
            ProductStatus.ACTIVE.value: 2,
            ProductStatus.DRAFT.value: 1,
            ProductStatus.ARCHIVED.value: 0,
            ProductStatus.DISABLED.value: 0,
        }

        values = metric_values(read_models.build_product_summary(counts, products))

        self.assertEqual(values["Active Products"], "2")
        self.assertEqual(values["Total Products"], "3")
        self.assertEqual(values["Draft Products"], "1")
        self.assertEqual(values["Ready for Publishing"], "1")
        self.assertEqual(values["Ready To Publish"], "1")
        self.assertEqual(values["Published Products"], "1")
        self.assertEqual(values["Products Needing Review"], "2")
        self.assertEqual(values["Not Ready"], "1")
        self.assertEqual(values["Fulfillment Failed"], "1")
        self.assertEqual(values["Missing Price"], "1")
        self.assertEqual(values["Priced Products"], "1")
        self.assertEqual(values["Free Products"], "1")
        self.assertEqual(values["Paid Products"], "2")

    def test_product_summary_consumes_catalog_display_context(self):
        ready = SimpleNamespace(
            status=ProductStatus.ACTIVE,
            price_cents=1999,
            fulfillment_status=ProductFulfillmentStatus.READY,
            delivery_type=ProductDeliveryType.PAID,
            metadata=product_metadata_with_approval(
                {"delivery_type": ProductDeliveryType.PAID.value},
                ProductApprovalStatus.READY_TO_PUBLISH,
            ),
        )
        missing = SimpleNamespace(
            status=ProductStatus.ACTIVE,
            price_cents=None,
            fulfillment_status=ProductFulfillmentStatus.NOT_READY,
            delivery_type=ProductDeliveryType.FREE,
        )
        displays = (
            SimpleNamespace(
                product=ready,
                ordered_assets=(SimpleNamespace(id=1),),
                experience_presentation=SimpleNamespace(title="Experience"),
            ),
            SimpleNamespace(
                product=missing,
                ordered_assets=(),
                experience_presentation=None,
            ),
        )

        values = metric_values(
            read_models.build_product_summary(
                {
                    ProductStatus.ACTIVE.value: 2,
                    ProductStatus.DRAFT.value: 0,
                    ProductStatus.ARCHIVED.value: 0,
                    ProductStatus.DISABLED.value: 0,
                },
                displays,
            )
        )

        self.assertEqual(values["Total Products"], "2")
        self.assertEqual(values["Missing Experience"], "1")
        self.assertEqual(values["Missing Assets"], "1")
        self.assertEqual(values["Products Needing Review"], "1")

    def test_publishing_summary_preserves_queue_rollups(self):
        ready_product = SimpleNamespace(
            status=ProductStatus.ACTIVE,
            delivery_type=ProductDeliveryType.PAID,
            fulfillment_status=ProductFulfillmentStatus.READY,
            price_cents=1999,
            media_link="https://example.test/product",
            metadata=product_metadata_with_approval(
                {"delivery_type": ProductDeliveryType.PAID.value},
                ProductApprovalStatus.READY_TO_PUBLISH,
            ),
        )
        review_product = SimpleNamespace(
            status=ProductStatus.ACTIVE,
            delivery_type=ProductDeliveryType.FREE,
            fulfillment_status=ProductFulfillmentStatus.NOT_READY,
            price_cents=None,
            media_link=None,
        )
        values = metric_values(
            read_models.build_publishing_summary(
                wall_counts={
                    "pending": 4,
                    "processing": 1,
                    "completed": 8,
                    "failed": 1,
                },
                pending_mass=2,
                failed_mass=3,
                products=(
                    SimpleNamespace(
                        product=ready_product,
                        ordered_assets=(SimpleNamespace(id=1),),
                        publishing=SimpleNamespace(status="Uploaded to Fanvue"),
                    ),
                    SimpleNamespace(
                        product=review_product,
                        ordered_assets=(),
                        publishing=SimpleNamespace(status="Not uploaded to Fanvue"),
                    ),
                ),
                publishing_queue_items=(
                    SimpleNamespace(
                        status="QUEUED",
                        upload_status="QUEUED",
                        waiting_for_media_link=False,
                        failed_upload=False,
                        retry_state="NOT_RETRIED",
                        provider="fanvue",
                    ),
                    SimpleNamespace(
                        status="UPLOADING",
                        upload_status="UPLOADING",
                        waiting_for_media_link=False,
                        failed_upload=False,
                        retry_state="NOT_RETRIED",
                        provider="fanvue",
                    ),
                    SimpleNamespace(
                        status="WAITING_FOR_MEDIA_LINK",
                        upload_status="UPLOADED",
                        waiting_for_media_link=True,
                        failed_upload=False,
                        retry_state="NOT_RETRIED",
                        provider="fanvue",
                    ),
                    SimpleNamespace(
                        status="RETRY_REQUIRED",
                        upload_status="RETRY_REQUIRED",
                        waiting_for_media_link=False,
                        failed_upload=True,
                        retry_state="RETRY_REQUIRED",
                        provider="fanvue",
                    ),
                    SimpleNamespace(
                        status="PUBLISHING_COMPLETE",
                        upload_status="UPLOADED",
                        waiting_for_media_link=False,
                        failed_upload=False,
                        retry_state="NOT_RETRIED",
                        provider="fanvue",
                    ),
                ),
            )
        )

        self.assertEqual(values["Total Publishable Products"], "2")
        self.assertEqual(values["Ready To Publish"], "1")
        self.assertEqual(values["Needs Attention"], "9")
        self.assertEqual(values["Published / Active"], "1")
        self.assertEqual(values["Missing Media Link"], "1")
        self.assertEqual(values["Missing Price"], "0")
        self.assertEqual(values["Missing Assets"], "1")
        self.assertEqual(values["FREE Delivery Items"], "1")
        self.assertEqual(values["PAID Delivery Items"], "1")
        self.assertEqual(values["Fanvue-ready Items"], "1")
        self.assertEqual(values["Telegram-ready Items"], "2")
        self.assertEqual(values["Pending Uploads"], "6")
        self.assertEqual(values["Failed Uploads"], "4")
        self.assertEqual(values["Recently Published"], "8")
        self.assertEqual(values["Wall Pending"], "4")
        self.assertEqual(values["Wall Processing"], "1")
        self.assertEqual(values["Mass PPV Pending"], "2")
        self.assertEqual(values["Mass PPV Failed"], "3")
        self.assertEqual(values["Publishing Health"], "Attention")
        self.assertEqual(values["Queue Attention"], "8")
        self.assertEqual(values["Publishing Queue Count"], "5")
        self.assertEqual(values["Uploading Count"], "1")
        self.assertEqual(values["Uploaded Count"], "2")
        self.assertEqual(values["Waiting For Media Link"], "1")
        self.assertEqual(values["Failed Count"], "1")
        self.assertEqual(values["Retry Required Count"], "1")
        self.assertEqual(values["Publishing Complete"], "1")
        self.assertEqual(values["Product ACTIVE Count"], "2")
        self.assertEqual(values["Provider Summary"], "fanvue")

    def test_experience_summary_consumes_experience_semantics(self):
        experiences = [
            SimpleNamespace(
                is_standalone=True,
                is_collection=False,
                ordered_asset_ids=(1,),
                asset_ids=(1,),
                cover_asset_id=1,
                metadata={
                    "experience_intelligence": {"source": "test"},
                    "story_progression": "teaser to payoff",
                    "publishing_readiness": "ready",
                },
            ),
            SimpleNamespace(
                is_standalone=False,
                is_collection=True,
                ordered_asset_ids=(2, 3),
                asset_ids=(2, 3),
                cover_asset_id=None,
                metadata={},
            ),
        ]

        summary = read_models.build_experience_summary(experiences)
        values = metric_values(summary)

        self.assertEqual(values["Total Experiences"], "2")
        self.assertEqual(values["Standalone"], "1")
        self.assertEqual(values["Collections"], "1")
        self.assertEqual(values["Assets Organized"], "3")
        self.assertEqual(values["With Intelligence"], "1")
        self.assertEqual(values["Story Ready"], "1")
        self.assertEqual(values["Missing Covers"], "1")
        self.assertEqual(values["Needs Review"], "1")
        self.assertEqual(values["Ready for Product Review"], "1")
        self.assertEqual(values["Ready for Publishing"], "1")
        self.assertIn("Product/ProductAsset compatibility", summary.note)


if __name__ == "__main__":
    unittest.main()
