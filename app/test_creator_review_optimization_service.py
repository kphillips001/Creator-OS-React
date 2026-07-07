import unittest
from types import SimpleNamespace

from app.models.creator_review import CreatorReviewSection
from app.models.creator_review_optimization import (
    CreatorReviewAction,
    CreatorReviewState,
)
from app.models.creator_workflow import (
    CreatorWorkflowSnapshot,
    CreatorWorkflowStage,
    CreatorWorkflowStageStatus,
)
from app.models.product_lifecycle import ProductLifecycleStage
from app.services.creator_review_optimization_service import (
    CreatorReviewOptimizationService,
)


def workflow_snapshot(*, complete=(), product_status=None, approval_status=None):
    return CreatorWorkflowSnapshot(
        workflow_id="product:1",
        product_id="1",
        current_stage=CreatorWorkflowStage.IMPORTED,
        stages=tuple(
            CreatorWorkflowStageStatus(stage=stage, status="complete")
            for stage in complete
        ),
        product_status=product_status,
        approval_status=approval_status,
    )


def creator_review(*, warnings=(), confidence=0.86):
    section = CreatorReviewSection(
        title="Section",
        confidence=confidence,
        warnings=(),
    )
    return SimpleNamespace(
        asset_understanding=section,
        content_intelligence=section,
        experience_recommendation=section,
        product_strategy=section,
        commerce_strategy=section,
        commerce_recommendation=section,
        warnings=tuple(warnings),
        manual_overrides={},
    )


def product_review(
    *,
    review_status="Ready for Approval",
    priority="normal",
    warnings=(),
    commerce_override_status="aligned",
    confidence=0.88,
):
    return SimpleNamespace(
        review_status=review_status,
        priority=priority,
        warnings=tuple(warnings),
        commerce_overrides=SimpleNamespace(status=commerce_override_status),
        commerce=SimpleNamespace(data={"confidence": confidence}),
    )


class FakeCreatorReviewService:
    def __init__(self, review):
        self.review = review
        self.calls = []

    def build_review(self, workflow_result):
        self.calls.append(workflow_result)
        return self.review


class FakeProductReviewService:
    def __init__(self, review):
        self.review = review
        self.calls = []

    def build_review_from_display(self, display):
        self.calls.append(display)
        return self.review


class CreatorReviewOptimizationServiceTests(unittest.TestCase):
    def test_review_status_generation_auto_progress_eligible(self):
        service = CreatorReviewOptimizationService()
        status = service.build_review_status(
            workflow_snapshot=workflow_snapshot(
                complete=(
                    CreatorWorkflowStage.PRODUCT_STRATEGY_READY,
                    CreatorWorkflowStage.COMMERCE_STRATEGY_READY,
                )
            ),
            creator_review=creator_review(),
            product_review=product_review(),
        )

        self.assertEqual(status.state, CreatorReviewState.AUTO_PROGRESS_ELIGIBLE)
        self.assertTrue(status.auto_progress_eligible)
        self.assertFalse(status.review_required)
        self.assertEqual(
            status.recommendation.action,
            CreatorReviewAction.CONTINUE_AUTOMATICALLY,
        )

    def test_review_required_for_warnings(self):
        service = CreatorReviewOptimizationService()
        status = service.build_review_status(
            workflow_snapshot=workflow_snapshot(),
            creator_review=creator_review(warnings=("partial",)),
            product_review=product_review(warnings=("missing_price",)),
        )

        self.assertEqual(status.state, CreatorReviewState.REVIEW_REQUIRED)
        self.assertTrue(status.review_required)
        self.assertIn("missing_price", status.warnings)
        self.assertEqual(status.next_creator_action, "Review Product")

    def test_ready_for_approval_when_low_confidence(self):
        service = CreatorReviewOptimizationService(minimum_auto_confidence=0.9)
        status = service.build_review_status(
            workflow_snapshot=workflow_snapshot(
                complete=(
                    CreatorWorkflowStage.PRODUCT_STRATEGY_READY,
                    CreatorWorkflowStage.COMMERCE_STRATEGY_READY,
                )
            ),
            creator_review=creator_review(confidence=0.7),
            product_review=product_review(confidence=0.72),
        )

        self.assertEqual(status.state, CreatorReviewState.READY_FOR_APPROVAL)
        self.assertEqual(status.recommendation.action, CreatorReviewAction.APPROVE_PRODUCT)

    def test_lifecycle_integration(self):
        service = CreatorReviewOptimizationService()
        status = service.build_review_status(
            lifecycle={
                "workflow_id": "product:1",
                "product_id": "1",
                "current_stage": "IMPORTED",
                "approval_status": "APPROVED",
                "stages": (),
            },
            product_review=product_review(review_status="Approved"),
        )

        self.assertEqual(status.lifecycle.stage, ProductLifecycleStage.APPROVED)
        self.assertEqual(status.state, CreatorReviewState.AUTO_PROGRESS_ELIGIBLE)

    def test_workflow_integration(self):
        service = CreatorReviewOptimizationService()
        status = service.build_from_workflow_snapshot(
            workflow_snapshot(
                complete=(
                    CreatorWorkflowStage.PRODUCT_STRATEGY_READY,
                    CreatorWorkflowStage.COMMERCE_STRATEGY_READY,
                )
            ),
            product_review=product_review(review_status="Draft Review"),
        )

        self.assertEqual(status.state, CreatorReviewState.AUTO_PROGRESS_ELIGIBLE)
        self.assertGreaterEqual(status.confidence, 0.75)

    def test_backward_compatibility_from_existing_services(self):
        creator = creator_review()
        product = product_review()
        creator_service = FakeCreatorReviewService(creator)
        product_service = FakeProductReviewService(product)
        service = CreatorReviewOptimizationService(
            creator_review_service=creator_service,
            product_review_service=product_service,
        )

        status = service.build_review_status(
            workflow_result=SimpleNamespace(id="import"),
            product_display=SimpleNamespace(id="display"),
        )

        self.assertEqual(status.state, CreatorReviewState.AUTO_PROGRESS_ELIGIBLE)
        self.assertEqual(creator_service.calls[0].id, "import")
        self.assertEqual(product_service.calls[0].id, "display")


if __name__ == "__main__":
    unittest.main()
