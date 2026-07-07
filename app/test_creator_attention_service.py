import unittest

from app.models.creator_attention import (
    CreatorAttentionCategory,
    CreatorAttentionPriority,
)
from app.models.creator_review_optimization import (
    CreatorReviewAction,
    CreatorReviewRecommendation,
    CreatorReviewState,
    CreatorReviewStatus,
)
from app.models.creator_workflow import CreatorWorkflowSnapshot, CreatorWorkflowStage
from app.models.publishing_automation import (
    PublishingAutomationAction,
    PublishingAutomationRecommendation,
    PublishingAutomationState,
    PublishingAutomationStatus,
)
from app.services.creator_attention_service import CreatorAttentionService
from app.services.product_lifecycle_service import ProductLifecycleService


def workflow_snapshot(
    *,
    product_id="1",
    content_type="SINGLE_ASSET",
    approval_status=None,
    product_status=None,
    publishing_status=None,
    media_link_status=None,
    telegram_ready=False,
):
    return CreatorWorkflowSnapshot(
        workflow_id="product:1",
        product_id=product_id,
        current_stage=CreatorWorkflowStage.IMPORTED,
        stages=(),
        content_type=content_type,
        approval_status=approval_status,
        product_status=product_status,
        publishing_status=publishing_status,
        media_link_status=media_link_status,
        telegram_ready=telegram_ready,
    )


class CreatorAttentionServiceTests(unittest.TestCase):
    def test_attention_generation_for_review_required(self):
        lifecycle = ProductLifecycleService().build_lifecycle(workflow_snapshot())
        review_status = CreatorReviewStatus(
            state=CreatorReviewState.REVIEW_REQUIRED,
            recommendation=CreatorReviewRecommendation(
                action=CreatorReviewAction.REVIEW_PRODUCT,
                label=CreatorReviewAction.REVIEW_PRODUCT.value,
                reason="low confidence",
            ),
            lifecycle=lifecycle,
            review_required=True,
            warnings=("low_confidence",),
        )

        summary = CreatorAttentionService().build_attention_summary(
            lifecycle=lifecycle,
            review_status=review_status,
        )

        self.assertTrue(summary.attention_required)
        self.assertEqual(summary.recommended_action, "Review Product")
        self.assertEqual(summary.items[0].category, CreatorAttentionCategory.REVIEW)

    def test_priority_calculation_orders_failure_first(self):
        lifecycle = ProductLifecycleService().build_lifecycle(
            workflow_snapshot(
                approval_status="READY_TO_PUBLISH",
                publishing_status="WAITING_FOR_MEDIA_LINK",
                media_link_status="PENDING",
            )
        )
        publishing_status = PublishingAutomationStatus(
            state=PublishingAutomationState.NEEDS_ATTENTION,
            recommendation=PublishingAutomationRecommendation(
                action=PublishingAutomationAction.REVIEW_PUBLISHING_FAILURE,
                label=PublishingAutomationAction.REVIEW_PUBLISHING_FAILURE.value,
            ),
            lifecycle=lifecycle,
            provider_error="upload_failed",
            attention_required=True,
        )

        summary = CreatorAttentionService().build_attention_summary(
            lifecycle=lifecycle,
            publishing_status=publishing_status,
        )

        self.assertEqual(summary.highest_priority, CreatorAttentionPriority.CRITICAL)
        self.assertEqual(summary.recommended_action, "Resolve Publishing Failure")
        self.assertEqual(summary.items[0].category, CreatorAttentionCategory.FAILURE)

    def test_workflow_aggregation_detects_missing_content_type(self):
        summary = CreatorAttentionService().build_attention_summary(
            workflow_snapshot=workflow_snapshot(product_id=None, content_type=None)
        )

        self.assertTrue(summary.attention_required)
        self.assertEqual(summary.recommended_action, "Select Content Type")
        self.assertEqual(summary.items[0].priority, CreatorAttentionPriority.HIGH)

    def test_lifecycle_integration_generates_approval_attention(self):
        lifecycle = ProductLifecycleService().build_lifecycle(
            workflow_snapshot(approval_status="APPROVED")
        )
        review_status = CreatorReviewStatus(
            state=CreatorReviewState.READY_FOR_APPROVAL,
            recommendation=CreatorReviewRecommendation(
                action=CreatorReviewAction.APPROVE_PRODUCT,
                label=CreatorReviewAction.APPROVE_PRODUCT.value,
            ),
            lifecycle=lifecycle,
        )

        summary = CreatorAttentionService().build_attention_summary(
            lifecycle=lifecycle,
            review_status=review_status,
        )

        self.assertEqual(summary.recommended_action, "Approve Product")
        self.assertEqual(summary.items[0].category, CreatorAttentionCategory.APPROVAL)

    def test_publishing_integration_generates_media_link_attention(self):
        lifecycle = ProductLifecycleService().build_lifecycle(
            workflow_snapshot(
                publishing_status="WAITING_FOR_MEDIA_LINK",
                media_link_status="PENDING",
            )
        )

        summary = CreatorAttentionService().build_attention_summary(lifecycle=lifecycle)

        self.assertTrue(summary.attention_required)
        self.assertEqual(summary.recommended_action, "Paste Media Link")
        self.assertEqual(summary.items[0].category, CreatorAttentionCategory.MEDIA_LINK)

    def test_publishing_verification_attention(self):
        lifecycle = ProductLifecycleService().build_lifecycle(
            workflow_snapshot(publishing_status="MEDIA_LINK_VERIFIED")
        )

        summary = CreatorAttentionService().build_attention_summary(lifecycle=lifecycle)

        self.assertEqual(summary.recommended_action, "Verify Media Link")
        self.assertEqual(summary.items[0].priority, CreatorAttentionPriority.NORMAL)

    def test_backward_compatibility_mapping_inputs(self):
        summary = CreatorAttentionService().build_attention_summary(
            lifecycle={
                "workflow_id": "product:legacy",
                "product_id": "legacy",
                "current_stage": "IMPORTED",
                "content_type": "SINGLE_ASSET",
                "publishing_status": "WAITING_FOR_MEDIA_LINK",
                "media_link_status": "PENDING",
                "stages": (),
            },
            review_status={
                "state": "AUTO_PROGRESS_ELIGIBLE",
                "action": "Continue Automatically",
            },
        )

        self.assertTrue(summary.attention_required)
        self.assertEqual(summary.items[0].product_id, "legacy")
        self.assertEqual(summary.recommended_action, "Paste Media Link")

    def test_no_action_required_when_workflow_is_ready(self):
        lifecycle = ProductLifecycleService().build_lifecycle(
            workflow_snapshot(product_status="ACTIVE", telegram_ready=True)
        )
        review_status = CreatorReviewStatus(
            state=CreatorReviewState.AUTO_PROGRESS_ELIGIBLE,
            recommendation=CreatorReviewRecommendation(
                action=CreatorReviewAction.CONTINUE_AUTOMATICALLY,
                label=CreatorReviewAction.CONTINUE_AUTOMATICALLY.value,
            ),
            lifecycle=lifecycle,
            auto_progress_eligible=True,
        )

        summary = CreatorAttentionService().build_attention_summary(
            lifecycle=lifecycle,
            review_status=review_status,
        )

        self.assertFalse(summary.attention_required)
        self.assertEqual(summary.recommended_action, "No Action Required")
        self.assertEqual(summary.items[0].category, CreatorAttentionCategory.INFORMATION)


if __name__ == "__main__":
    unittest.main()
