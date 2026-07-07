import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.models.creator_intent import CreatorContentType, CreatorIntent
from app.models.creator_workflow import CreatorWorkflowStage
from app.models.product import (
    ProductApprovalStatus,
    ProductDeliveryType,
    ProductStatus,
    ProductType,
    product_metadata_with_approval,
)
from app.services.ai_import_workflow_service import AIImportAssetResult
from app.services.creator_workflow_service import CreatorWorkflowService


class FakeCreatorReviewService:
    def __init__(self):
        self.calls = []

    def build_review(self, workflow_result):
        self.calls.append(workflow_result)
        return SimpleNamespace(review_type="creator_review")


class FakeProductReviewService:
    def __init__(self, review=None):
        self.review = review
        self.calls = []

    def build_review_from_display(self, display):
        self.calls.append(("build_review_from_display", display))
        return self.review or product_review()

    def build_review(self, product_id, *, creator_profile_id):
        self.calls.append(("build_review", product_id, creator_profile_id))
        return self.review or product_review(product_id=str(product_id))


class FakePublishingService:
    def __init__(self, projection):
        self.projection = projection
        self.calls = []

    def project_publishing_status(self, job):
        self.calls.append(job)
        return self.projection


def product(
    *,
    status=ProductStatus.DRAFT,
    approval_status=ProductApprovalStatus.NEEDS_REVIEW,
    media_link=None,
    delivery_type=ProductDeliveryType.PAID,
):
    metadata = product_metadata_with_approval(
        {
            "commerce_intelligence": {
                "source_type": "asset",
                "product_type": "SINGLE_IMAGE",
            }
        },
        approval_status,
    )
    return SimpleNamespace(
        id=uuid4(),
        creator_profile_id=7,
        legacy_content_item_id=101,
        internal_name="mirror-set-vip",
        display_name="Mirror Set VIP",
        description="A product-ready draft.",
        product_type=ProductType.SINGLE_IMAGE,
        delivery_type=delivery_type,
        status=status,
        price_cents=2499,
        currency="USD",
        media_link=media_link,
        metadata=metadata,
    )


def product_display(product_value=None):
    return SimpleNamespace(
        product=product_value or product(),
        ordered_assets=(SimpleNamespace(id=101),),
        experience_presentation=SimpleNamespace(
            experience_id="experience-101",
            experience_type="STANDALONE",
        ),
        publishing=SimpleNamespace(status="Ready", detail="Provider URL available"),
    )


def product_review(
    *,
    product_id="product-101",
    product_status="DRAFT",
    approval_status="NEEDS_REVIEW",
    publishing_status="Ready",
):
    return SimpleNamespace(
        product_id=product_id,
        product_status=product_status,
        approval_status=approval_status,
        product=SimpleNamespace(status="available"),
        experience=SimpleNamespace(status="available"),
        commerce=SimpleNamespace(status="available"),
        publishing=SimpleNamespace(status=publishing_status),
    )


class CreatorWorkflowServiceTests(unittest.TestCase):
    def test_workflow_snapshot_creation_from_import_result(self):
        creator_intent = CreatorIntent.create("SINGLE_ASSET")
        workflow_result = AIImportAssetResult(
            success=True,
            media_path="data/uploads/example.jpg",
            upload_intent="teaser_image",
            legacy_result={"success": True},
            content_id=101,
            content_intelligence=SimpleNamespace(asset_id=101),
            asset_understanding=SimpleNamespace(asset_id=101),
            experience_recommendation=SimpleNamespace(asset_ids=(101,)),
            product_strategy_result=SimpleNamespace(source_type="content"),
            commerce_strategy_result=SimpleNamespace(source_type="content"),
            creator_intent=creator_intent,
        )
        creator_review = FakeCreatorReviewService()
        service = CreatorWorkflowService(creator_review_service=creator_review)

        snapshot = service.build_from_import_result(workflow_result)

        self.assertEqual(snapshot.workflow_id, "asset:101")
        self.assertEqual(snapshot.creator_intent.content_type, CreatorContentType.SINGLE_ASSET)
        self.assertEqual(snapshot.asset_ids, (101,))
        self.assertEqual(snapshot.current_stage, CreatorWorkflowStage.APPROVED)
        self.assertEqual(snapshot.stage_status(CreatorWorkflowStage.IMPORTED), "complete")
        self.assertEqual(
            snapshot.stage_status(CreatorWorkflowStage.COMMERCE_STRATEGY_READY),
            "complete",
        )
        self.assertEqual(len(creator_review.calls), 1)

    def test_workflow_stage_progression_to_telegram_ready(self):
        active_product = product(
            status=ProductStatus.ACTIVE,
            approval_status=ProductApprovalStatus.READY_TO_PUBLISH,
            media_link="https://provider.example/media/1",
        )
        display = product_display(active_product)
        service = CreatorWorkflowService(
            product_review_service=FakeProductReviewService(
                product_review(
                    product_id=str(active_product.id),
                    product_status="ACTIVE",
                    approval_status="READY_TO_PUBLISH",
                    publishing_status="PUBLISHING_COMPLETE",
                )
            )
        )

        snapshot = service.build_from_product_display(display)

        self.assertEqual(snapshot.current_stage, CreatorWorkflowStage.TELEGRAM_READY)
        self.assertTrue(snapshot.telegram_ready)
        self.assertEqual(snapshot.stage_status(CreatorWorkflowStage.ACTIVE), "complete")
        self.assertEqual(
            snapshot.stage_status(CreatorWorkflowStage.TELEGRAM_READY),
            "complete",
        )

    def test_workflow_assembly_from_existing_services(self):
        display = product_display()
        product_review_service = FakeProductReviewService()
        service = CreatorWorkflowService(product_review_service=product_review_service)

        snapshot = service.build_from_product_display(display)

        self.assertEqual(
            product_review_service.calls[0][0],
            "build_review_from_display",
        )
        self.assertEqual(snapshot.product_id, str(display.product.id))
        self.assertEqual(snapshot.stage_status(CreatorWorkflowStage.IN_CREATOR_REVIEW), "complete")
        self.assertEqual(snapshot.stage_status(CreatorWorkflowStage.APPROVED), "current")

    def test_publishing_integration_waiting_for_media_link(self):
        projection = SimpleNamespace(
            publishing_status="WAITING_FOR_MEDIA_LINK",
            media_link_status="PENDING",
        )
        service = CreatorWorkflowService(
            publishing_service=FakePublishingService(projection)
        )

        snapshot = service.build_snapshot(
            product_review=product_review(
                approval_status="READY_TO_PUBLISH",
                publishing_status=None,
            ),
            publishing_job=SimpleNamespace(id="job-1"),
        )

        self.assertEqual(snapshot.publishing_status, "WAITING_FOR_MEDIA_LINK")
        self.assertEqual(snapshot.media_link_status, "PENDING")
        self.assertEqual(
            snapshot.stage_status(CreatorWorkflowStage.WAITING_FOR_MEDIA_LINK),
            "complete",
        )
        self.assertEqual(snapshot.current_stage, CreatorWorkflowStage.ACTIVE)

    def test_creator_intent_backward_compatibility(self):
        workflow_result = AIImportAssetResult(
            success=True,
            media_path="data/uploads/example.jpg",
            upload_intent="photo_set",
            legacy_result={"success": True},
            content_id=202,
        )

        snapshot = CreatorWorkflowService().build_from_import_result(
            workflow_result
        )

        self.assertEqual(snapshot.creator_intent.content_type, CreatorContentType.PHOTOSHOOT)
        self.assertEqual(snapshot.creator_intent.legacy_upload_intent, "photo_set")


if __name__ == "__main__":
    unittest.main()
