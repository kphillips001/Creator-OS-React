import unittest
from types import SimpleNamespace

from app.models.creator_workflow import CreatorWorkflowSnapshot, CreatorWorkflowStage
from app.models.product_lifecycle import ProductLifecycleStage
from app.models.publishing_automation import (
    PublishingAutomationAction,
    PublishingAutomationState,
)
from app.services.product_lifecycle_service import ProductLifecycleService
from app.services.publishing_automation_service import PublishingAutomationService


def lifecycle_snapshot(
    *,
    approval_status=None,
    product_status=None,
    publishing_status=None,
    media_link_status=None,
    telegram_ready=False,
):
    return CreatorWorkflowSnapshot(
        workflow_id="product:1",
        product_id="1",
        current_stage=CreatorWorkflowStage.IMPORTED,
        stages=(),
        approval_status=approval_status,
        product_status=product_status,
        publishing_status=publishing_status,
        media_link_status=media_link_status,
        telegram_ready=telegram_ready,
    )


class FakePublishingService:
    def __init__(self, projection):
        self.projection = projection
        self.calls = []

    def project_publishing_status(self, job):
        self.calls.append(job)
        return self.projection


class PublishingAutomationServiceTests(unittest.TestCase):
    def test_publishing_automation_status_ready_to_publish(self):
        lifecycle = ProductLifecycleService().build_lifecycle(
            lifecycle_snapshot(approval_status="READY_TO_PUBLISH")
        )
        status = PublishingAutomationService().build_from_lifecycle(lifecycle)

        self.assertEqual(status.state, PublishingAutomationState.READY_TO_PUBLISH)
        self.assertEqual(
            status.recommendation.action,
            PublishingAutomationAction.READY_TO_PUBLISH,
        )
        self.assertFalse(status.manual_media_link_required)
        self.assertTrue(status.compatibility["manual_media_link_creation_preserved"])

    def test_publishing_recommendation_generation(self):
        service = PublishingAutomationService()

        queued = service.build_status(
            lifecycle=ProductLifecycleService().build_lifecycle(
                lifecycle_snapshot(
                    approval_status="READY_TO_PUBLISH",
                    publishing_status="QUEUED",
                )
            )
        )
        waiting = service.build_status(
            lifecycle=ProductLifecycleService().build_lifecycle(
                lifecycle_snapshot(
                    publishing_status="WAITING_FOR_MEDIA_LINK",
                    media_link_status="PENDING",
                )
            )
        )

        self.assertEqual(queued.state, PublishingAutomationState.QUEUED)
        self.assertEqual(
            queued.next_recommended_action,
            PublishingAutomationAction.MONITOR_UPLOAD.value,
        )
        self.assertEqual(waiting.state, PublishingAutomationState.WAITING_FOR_MEDIA_LINK)
        self.assertEqual(
            waiting.next_recommended_action,
            PublishingAutomationAction.WAITING_FOR_MEDIA_LINK.value,
        )
        self.assertTrue(waiting.manual_media_link_required)

    def test_product_lifecycle_integration(self):
        lifecycle = ProductLifecycleService().build_lifecycle(
            lifecycle_snapshot(product_status="ACTIVE", telegram_ready=True)
        )
        status = PublishingAutomationService().build_status(lifecycle=lifecycle)

        self.assertEqual(lifecycle.stage, ProductLifecycleStage.TELEGRAM_READY)
        self.assertEqual(status.state, PublishingAutomationState.READY_FOR_TELEGRAM)
        self.assertEqual(
            status.recommendation.action,
            PublishingAutomationAction.READY_FOR_TELEGRAM,
        )

    def test_creator_workflow_integration(self):
        status = PublishingAutomationService().build_from_workflow_snapshot(
            lifecycle_snapshot(
                publishing_status="WAITING_FOR_MEDIA_LINK",
                media_link_status="PENDING",
            )
        )

        self.assertEqual(status.state, PublishingAutomationState.WAITING_FOR_MEDIA_LINK)
        self.assertEqual(status.media_link_status, "PENDING")

    def test_publishing_projection_and_failure_attention(self):
        projection = SimpleNamespace(
            publishing_status="FAILED",
            media_link_status="FAILED",
            provider_status="failed",
            provider_error="upload_failed",
        )
        service = PublishingAutomationService(
            publishing_service=FakePublishingService(projection)
        )

        status = service.build_status(
            lifecycle=ProductLifecycleService().build_lifecycle(
                lifecycle_snapshot(approval_status="READY_TO_PUBLISH")
            ),
            publishing_job=SimpleNamespace(id="job-1"),
        )

        self.assertEqual(status.state, PublishingAutomationState.NEEDS_ATTENTION)
        self.assertTrue(status.attention_required)
        self.assertEqual(status.provider_error, "upload_failed")
        self.assertEqual(
            status.recommendation.action,
            PublishingAutomationAction.REVIEW_PUBLISHING_FAILURE,
        )

    def test_backward_compatibility_mapping_lifecycle(self):
        status = PublishingAutomationService().build_status(
            lifecycle={
                "workflow_id": "product:legacy",
                "product_id": "legacy",
                "current_stage": "IMPORTED",
                "publishing_status": "UPLOADING",
                "media_link_status": "NOT_REQUIRED",
                "stages": (),
            }
        )

        self.assertEqual(status.product_id, "legacy")
        self.assertEqual(status.state, PublishingAutomationState.UPLOAD_IN_PROGRESS)
        self.assertEqual(
            status.next_recommended_action,
            PublishingAutomationAction.MONITOR_UPLOAD.value,
        )


if __name__ == "__main__":
    unittest.main()
