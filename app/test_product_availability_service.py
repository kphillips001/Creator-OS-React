import unittest
from types import SimpleNamespace

from app.models.creator_workflow import CreatorWorkflowSnapshot, CreatorWorkflowStage
from app.models.product_availability import (
    ProductAvailability,
    ProductAvailabilityStatus,
)
from app.models.product_business import (
    ProductBusinessAvailability,
    ProductBusinessSnapshot,
)
from app.models.publishing_automation import PublishingAutomationState
from app.services.product_availability_service import ProductAvailabilityService


def workflow_snapshot(**kwargs):
    defaults = {
        "workflow_id": "product:product-1",
        "product_id": "product-1",
        "current_stage": CreatorWorkflowStage.IMPORTED,
        "stages": (),
    }
    defaults.update(kwargs)
    return CreatorWorkflowSnapshot(**defaults)


class ProductAvailabilityServiceTests(unittest.TestCase):
    def test_availability_generation(self):
        availability = ProductAvailability(product_id="product-1")

        self.assertEqual(availability.product_id, "product-1")
        self.assertEqual(availability.status, ProductAvailabilityStatus.UNAVAILABLE)
        self.assertFalse(availability.available_for_customers)

    def test_availability_recommendations(self):
        service = ProductAvailabilityService()

        available = service.build_availability(
            product=SimpleNamespace(id="product-1", status="ACTIVE")
        )
        waiting = service.build_availability(
            workflow_snapshot=workflow_snapshot(
                publishing_status="WAITING_FOR_MEDIA_LINK",
                media_link_status="PENDING",
            )
        )
        failed = service.build_availability(
            workflow_snapshot=workflow_snapshot(approval_status="READY_TO_PUBLISH"),
            publishing_status={
                "publishing_status": "FAILED",
                "media_link_status": "FAILED",
                "provider_error": "upload_failed",
            },
        )

        self.assertEqual(available.status, ProductAvailabilityStatus.AVAILABLE)
        self.assertEqual(available.next_recommended_action, "Ready to Sell")
        self.assertEqual(
            waiting.status,
            ProductAvailabilityStatus.WAITING_FOR_MEDIA_LINK,
        )
        self.assertEqual(waiting.next_recommended_action, "Paste Media Link")
        self.assertEqual(failed.status, ProductAvailabilityStatus.NEEDS_ATTENTION)
        self.assertEqual(failed.next_recommended_action, "Resolve Publishing")

    def test_lifecycle_integration(self):
        availability = ProductAvailabilityService().build_availability(
            workflow_snapshot=workflow_snapshot(approval_status="READY_TO_PUBLISH")
        )

        self.assertEqual(availability.status, ProductAvailabilityStatus.PUBLISHING)
        self.assertIsNotNone(availability.lifecycle)
        self.assertEqual(availability.next_recommended_action, "Ready to Publish")
        self.assertTrue(availability.compatibility["product_lifecycle_consumed"])

    def test_publishing_integration(self):
        availability = ProductAvailabilityService().build_availability(
            workflow_snapshot=workflow_snapshot(
                publishing_status="UPLOADING",
                media_link_status="NOT_REQUIRED",
            )
        )

        self.assertEqual(availability.status, ProductAvailabilityStatus.PUBLISHING)
        self.assertEqual(
            availability.publishing_status.state,
            PublishingAutomationState.UPLOAD_IN_PROGRESS,
        )
        self.assertEqual(availability.publishing_state, "UPLOAD_IN_PROGRESS")
        self.assertTrue(availability.compatibility["publishing_consumed"])

    def test_product_business_integration(self):
        snapshot = ProductBusinessSnapshot(
            product_id="product-1",
            product_status="ACTIVE",
            availability=ProductBusinessAvailability.TELEGRAM_READY,
        )

        availability = ProductAvailabilityService().build_availability(
            product_business_snapshot=snapshot
        )

        self.assertEqual(availability.product_id, "product-1")
        self.assertEqual(availability.status, ProductAvailabilityStatus.AVAILABLE)
        self.assertTrue(availability.available_for_customers)
        self.assertTrue(availability.telegram_ready)
        self.assertTrue(availability.compatibility["product_business_consumed"])

    def test_archived_and_draft_states(self):
        service = ProductAvailabilityService()

        archived = service.build_availability(
            product=SimpleNamespace(id="archived", status="ARCHIVED")
        )
        draft = service.build_availability(
            product=SimpleNamespace(id="draft", status="DRAFT")
        )

        self.assertEqual(archived.status, ProductAvailabilityStatus.ARCHIVED)
        self.assertEqual(archived.next_recommended_action, "Archive Product")
        self.assertEqual(draft.status, ProductAvailabilityStatus.DRAFT)
        self.assertEqual(draft.next_recommended_action, "Complete Product")

    def test_backward_compatibility_mapping_inputs(self):
        availability = ProductAvailabilityService().build_availability(
            product_business_snapshot={
                "product_id": "legacy-product",
                "product_status": "DRAFT",
                "availability": "WAITING_FOR_MEDIA_LINK",
                "publishing_readiness": {
                    "media_link_status": "PENDING",
                },
            },
            publishing_status={
                "publishing_status": "WAITING_FOR_MEDIA_LINK",
                "media_link_status": "PENDING",
            },
        )

        self.assertEqual(availability.product_id, "legacy-product")
        self.assertEqual(
            availability.status,
            ProductAvailabilityStatus.WAITING_FOR_MEDIA_LINK,
        )
        self.assertTrue(availability.compatibility["provider_neutral"])
        self.assertTrue(availability.compatibility["does_not_replace_product_status"])


if __name__ == "__main__":
    unittest.main()
