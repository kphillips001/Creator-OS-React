import unittest

from app.models.creator_workflow import (
    CreatorWorkflowSnapshot,
    CreatorWorkflowStage,
    CreatorWorkflowStageStatus,
)
from app.models.product_lifecycle import ProductLifecycleAction, ProductLifecycleStage
from app.services.product_lifecycle_service import ProductLifecycleService


def snapshot(
    *,
    product_status=None,
    approval_status=None,
    publishing_status=None,
    media_link_status=None,
    telegram_ready=False,
    complete=(),
):
    stages = tuple(
        CreatorWorkflowStageStatus(stage=stage, status="complete")
        for stage in complete
    )
    return CreatorWorkflowSnapshot(
        workflow_id="product:1",
        product_id="1",
        current_stage=CreatorWorkflowStage.IMPORTED,
        stages=stages,
        product_status=product_status,
        approval_status=approval_status,
        publishing_status=publishing_status,
        media_link_status=media_link_status,
        telegram_ready=telegram_ready,
    )


class FakeCreatorWorkflowService:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def build_snapshot(self, **kwargs):
        self.calls.append(kwargs)
        return self.value


class ProductLifecycleServiceTests(unittest.TestCase):
    def test_lifecycle_creation_from_workflow_snapshot(self):
        service = ProductLifecycleService()
        lifecycle = service.build_from_workflow_snapshot(
            snapshot(
                complete=(
                    CreatorWorkflowStage.PRODUCT_STRATEGY_READY,
                    CreatorWorkflowStage.COMMERCE_STRATEGY_READY,
                )
            )
        )

        self.assertEqual(lifecycle.stage, ProductLifecycleStage.STRATEGY_READY)
        self.assertEqual(
            lifecycle.next_recommended_action,
            ProductLifecycleAction.READY_FOR_REVIEW.value,
        )
        self.assertEqual(lifecycle.product_id, "1")
        self.assertTrue(lifecycle.compatibility["read_only"])

    def test_lifecycle_stage_progression(self):
        service = ProductLifecycleService()
        cases = (
            (
                snapshot(),
                ProductLifecycleStage.DRAFT,
            ),
            (
                snapshot(complete=(CreatorWorkflowStage.IN_CREATOR_REVIEW,)),
                ProductLifecycleStage.REVIEW_READY,
            ),
            (
                snapshot(approval_status="APPROVED"),
                ProductLifecycleStage.APPROVED,
            ),
            (
                snapshot(approval_status="READY_TO_PUBLISH"),
                ProductLifecycleStage.PUBLISHING_READY,
            ),
            (
                snapshot(publishing_status="UPLOADING"),
                ProductLifecycleStage.PUBLISHING,
            ),
            (
                snapshot(
                    publishing_status="WAITING_FOR_MEDIA_LINK",
                    media_link_status="PENDING",
                ),
                ProductLifecycleStage.WAITING_FOR_MEDIA_LINK,
            ),
            (
                snapshot(product_status="ACTIVE"),
                ProductLifecycleStage.ACTIVE,
            ),
            (
                snapshot(product_status="ACTIVE", telegram_ready=True),
                ProductLifecycleStage.TELEGRAM_READY,
            ),
        )

        for item, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(service.determine_stage(item), expected)

    def test_lifecycle_recommendations(self):
        service = ProductLifecycleService()

        self.assertEqual(
            service.build_lifecycle(snapshot(approval_status="APPROVED"))
            .recommendation
            .action,
            ProductLifecycleAction.PUBLISH_PRODUCT,
        )
        self.assertEqual(
            service.build_lifecycle(
                snapshot(
                    publishing_status="WAITING_FOR_MEDIA_LINK",
                    media_link_status="PENDING",
                )
            )
            .recommendation
            .action,
            ProductLifecycleAction.PASTE_MEDIA_LINK,
        )
        self.assertEqual(
            service.build_lifecycle(snapshot(product_status="ACTIVE"))
            .recommendation
            .action,
            ProductLifecycleAction.READY_FOR_TELEGRAM,
        )

    def test_publishing_and_approval_integration(self):
        service = ProductLifecycleService()
        lifecycle = service.build_lifecycle(
            snapshot(
                approval_status="READY_TO_PUBLISH",
                publishing_status="QUEUED",
            )
        )

        self.assertEqual(lifecycle.stage, ProductLifecycleStage.PUBLISHING)
        self.assertEqual(lifecycle.approval_status, "READY_TO_PUBLISH")
        self.assertEqual(lifecycle.publishing_status, "QUEUED")

    def test_creator_workflow_snapshot_integration(self):
        workflow_snapshot = snapshot(approval_status="APPROVED")
        workflow = FakeCreatorWorkflowService(workflow_snapshot)
        service = ProductLifecycleService(creator_workflow_service=workflow)

        lifecycle = service.build_lifecycle(product_review={"product_id": "1"})

        self.assertEqual(lifecycle.stage, ProductLifecycleStage.APPROVED)
        self.assertEqual(workflow.calls, [{"product_review": {"product_id": "1"}}])

    def test_backward_compatibility_mapping_snapshot(self):
        service = ProductLifecycleService()
        lifecycle = service.build_lifecycle(
            {
                "workflow_id": "product:legacy",
                "product_id": "legacy",
                "current_stage": "IMPORTED",
                "approval_status": "READY_TO_PUBLISH",
                "stages": (
                    {
                        "stage": "IN_CREATOR_REVIEW",
                        "status": "complete",
                    },
                ),
            }
        )

        self.assertEqual(lifecycle.product_id, "legacy")
        self.assertEqual(lifecycle.stage, ProductLifecycleStage.PUBLISHING_READY)
        self.assertEqual(
            lifecycle.next_recommended_action,
            ProductLifecycleAction.PUBLISH_PRODUCT.value,
        )


if __name__ == "__main__":
    unittest.main()
