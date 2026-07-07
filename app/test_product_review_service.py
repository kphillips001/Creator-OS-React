import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.models.product import ProductDeliveryType, ProductStatus, ProductType
from app.models.product import ProductApprovalStatus, product_metadata_with_approval
from app.services.product_review_service import ProductReviewService


def product(
    *,
    status=ProductStatus.DRAFT,
    delivery_type=ProductDeliveryType.PAID,
    price_cents=2499,
    metadata=None,
):
    return SimpleNamespace(
        id=uuid4(),
        creator_profile_id=7,
        internal_name="mirror-set-vip",
        display_name="Mirror Set VIP",
        description="A creator-ready Product Draft.",
        product_type=ProductType.SINGLE_IMAGE,
        delivery_type=delivery_type,
        status=status,
        price_cents=price_cents,
        currency="USD",
        metadata=metadata
        if metadata is not None
        else {
            "ai_product_draft": True,
            "draft_source": "ai_cms_asset",
            "commerce_intelligence": {
                "source_type": "asset",
                "source_id": "101",
                "product_type": "SINGLE_IMAGE",
                "delivery_type": "PAID",
                "suggested_keywords": ["mirror", "vip"],
                "confidence": 0.88,
                "price": {
                    "suggested_price_cents": 2499,
                    "min_price_cents": 1800,
                    "max_price_cents": 3400,
                    "pricing_rule": "VIP_SINGLE_IMAGE",
                },
                "publishing": {
                    "status": "ready_for_draft",
                    "action": "review_product_draft",
                    "reason": "Ready for draft review.",
                },
                "delivery_type_rationale": "Premium classification supports paid delivery.",
            },
        },
        activation_source=None,
        activation_reason=None,
    )


def manual_product():
    return product(
        status=ProductStatus.DRAFT,
        metadata={
            "creation_source": "manual",
            "manual_product": True,
            "delivery_type": "PAID",
            "approval": {"status": "NEEDS_REVIEW"},
        },
    )


def experience_presentation():
    return SimpleNamespace(
        experience_id="experience-101",
        experience_type="STANDALONE",
        title="Mirror Set",
        summary="A standalone mirror set.",
        cover_asset_id=101,
        asset_ids=(101,),
        themes=("mirror",),
        keywords=("vip",),
        mood="flirty",
        story_progression=None,
        technical_continuity="single asset",
        relationship_source="experience_service",
        compatibility=False,
    )


def display_model(product_value=None, *, publishing=True, assets=(101,)):
    return SimpleNamespace(
        product=product_value or product(),
        ordered_assets=tuple(SimpleNamespace(id=asset_id) for asset_id in assets),
        experience_presentation=experience_presentation(),
        publishing=SimpleNamespace(status="Ready", detail="Provider URL available")
        if publishing
        else None,
    )


class FakeProductCatalogService:
    def __init__(self, display):
        self.display = display
        self.calls = []

    def load_editor(self, product_id, creator_profile_id):
        self.calls.append(("load_editor", str(product_id), creator_profile_id))
        return SimpleNamespace(product=self.display.product)

    def build_editor_display_model(self, editor):
        self.calls.append(("build_editor_display_model", editor.product.id))
        return self.display

    def list_workspace_display_models(
        self,
        *,
        creator_profile_id,
        include_archived,
        limit,
    ):
        self.calls.append(
            (
                "list_workspace_display_models",
                creator_profile_id,
                include_archived,
                limit,
            )
        )
        return (self.display,)

    def create_product(self, *args, **kwargs):
        raise AssertionError("Product Review must not create Products.")

    def update_product(self, *args, **kwargs):
        raise AssertionError("Product Review must not edit Products.")

    def transition_status(self, *args, **kwargs):
        raise AssertionError("Product Review must not approve Products.")

    def save_media_link(self, *args, **kwargs):
        raise AssertionError("Product Review must not persist media links.")


class FakePublishingService:
    def __init__(self):
        self.calls = []

    def project_legacy_product_record(self, product_value):
        self.calls.append(("project_legacy_product_record", product_value.id))
        return {"delivery_type": product_value.delivery_type.value}

    def get_product_provider_status_display(self, product_record, assets):
        self.calls.append(("get_product_provider_status_display", len(tuple(assets))))
        return "Ready", "Projected by PublishingService"


class FakeCreatorReviewService:
    def __init__(self):
        self.calls = []

    def build_review(self, workflow_result, *, manual_overrides=None):
        self.calls.append(("build_review", workflow_result, manual_overrides))
        return SimpleNamespace(review_type="creator_review")


class ProductReviewServiceTests(unittest.TestCase):
    def test_builds_product_review_from_catalog_display_model(self):
        display = display_model()
        service = ProductReviewService(
            product_catalog_service=FakeProductCatalogService(display),
        )

        review = service.build_review_from_display(display)

        self.assertEqual(review.product_name, "Mirror Set VIP")
        self.assertEqual(review.product_origin, "AI Product Draft")
        self.assertEqual(review.product_type, "SINGLE_IMAGE")
        self.assertEqual(review.delivery_type, "PAID")
        self.assertEqual(review.review_status, "Draft Review")
        self.assertEqual(review.product.data["asset_count"], 1)
        self.assertEqual(review.experience.data["experience_id"], "experience-101")
        self.assertEqual(
            review.commerce.data["suggested_price_cents"],
            2499,
        )
        self.assertEqual(review.publishing.status, "Ready")
        self.assertEqual(review.ai_rationale.status, "available")
        self.assertEqual(review.commerce_overrides.status, "aligned")

    def test_manual_product_review_identifies_manual_origin(self):
        display = display_model(manual_product())
        service = ProductReviewService()

        review = service.build_review_from_display(display)

        self.assertEqual(review.product_origin, "Manual Product")
        self.assertEqual(review.approval_status, "NEEDS_REVIEW")
        self.assertEqual(review.product.data["product_origin"], "Manual Product")
        self.assertEqual(review.commerce.status, "missing")
        self.assertIn("missing_commerce_recommendation", review.warnings)

    def test_displays_commerce_overrides_without_persisting(self):
        product_value = product(
            delivery_type=ProductDeliveryType.FREE,
            price_cents=999,
        )
        display = display_model(product_value)
        service = ProductReviewService()

        review = service.build_review_from_display(display)

        self.assertEqual(review.review_status, "Commerce Override Review")
        self.assertEqual(review.commerce_overrides.status, "overridden")
        fields = review.commerce_overrides.data["fields"]
        self.assertTrue(fields["price"]["overridden"])
        self.assertEqual(fields["price"]["ai"], 2499)
        self.assertEqual(fields["price"]["current"], 999)
        self.assertTrue(fields["delivery_type"]["overridden"])
        self.assertEqual(fields["delivery_type"]["ai"], "PAID")
        self.assertEqual(fields["delivery_type"]["current"], "FREE")
        self.assertIn("commerce_override_price", review.warnings)
        self.assertIn("commerce_override_delivery_type", review.warnings)

    def test_build_review_uses_catalog_read_model_without_editing(self):
        display = display_model()
        catalog = FakeProductCatalogService(display)
        service = ProductReviewService(product_catalog_service=catalog)

        review = service.build_review(
            display.product.id,
            creator_profile_id=7,
            manual_overrides={"display_name": "Creator Override"},
        )

        self.assertEqual(review.manual_overrides["display_name"], "Creator Override")
        self.assertEqual(
            [call[0] for call in catalog.calls],
            ["load_editor", "build_editor_display_model"],
        )

    def test_summary_counts_product_review_states(self):
        display = display_model()
        catalog = FakeProductCatalogService(display)
        service = ProductReviewService(product_catalog_service=catalog)

        summary = service.build_summary(creator_profile_id=7)

        self.assertEqual(summary.total_reviews, 1)
        self.assertEqual(summary.needs_review, 1)
        self.assertEqual(summary.manual_products, 0)
        self.assertEqual(summary.ai_product_drafts, 1)
        self.assertEqual(summary.products_with_commerce_overrides, 0)
        self.assertEqual(summary.draft_reviews, 1)
        self.assertEqual(summary.high_priority_reviews, 0)
        self.assertEqual(len(summary.reviews), 1)

    def test_displays_persistent_approval_metadata(self):
        metadata = product_metadata_with_approval(
            product().metadata,
            ProductApprovalStatus.READY_TO_PUBLISH,
            reviewed_by="creator",
            notes="Looks good.",
        )
        display = display_model(product(metadata=metadata))
        service = ProductReviewService()

        review = service.build_review_from_display(display)

        self.assertEqual(review.approval_status, "READY_TO_PUBLISH")
        self.assertEqual(review.review_status, "Ready To Publish")
        self.assertEqual(review.review_notes, "Looks good.")
        self.assertIsNotNone(review.approved_at)
        self.assertIsNotNone(review.last_reviewed_at)

    def test_missing_price_and_assets_require_attention(self):
        display = display_model(
            product(
                status=ProductStatus.ACTIVE,
                delivery_type=ProductDeliveryType.PAID,
                price_cents=None,
            ),
            assets=(),
        )
        service = ProductReviewService()

        review = service.build_review_from_display(display)

        self.assertEqual(review.review_status, "Needs Attention")
        self.assertEqual(review.priority, "high")
        self.assertIn("missing_price", review.warnings)
        self.assertIn("missing_assets", review.warnings)

    def test_uses_publishing_service_as_projection_fallback(self):
        display = display_model(publishing=False)
        publishing = FakePublishingService()
        service = ProductReviewService(publishing_service=publishing)

        review = service.build_review_from_display(display)

        self.assertEqual(review.publishing.summary, "Projected by PublishingService")
        self.assertIn(
            "project_legacy_product_record",
            [call[0] for call in publishing.calls],
        )

    def test_workflow_result_review_delegates_to_creator_review_service(self):
        creator_review = FakeCreatorReviewService()
        service = ProductReviewService(creator_review_service=creator_review)
        workflow_result = SimpleNamespace(success=True)

        review = service.build_from_workflow_result(
            workflow_result,
            manual_overrides={"price": 1999},
        )

        self.assertEqual(review.review_type, "creator_review")
        self.assertEqual(
            creator_review.calls,
            [("build_review", workflow_result, {"price": 1999})],
        )


if __name__ == "__main__":
    unittest.main()
