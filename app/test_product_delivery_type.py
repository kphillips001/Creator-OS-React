import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.contracts.cms import DeliveryMode
from app.models.product import (
    FulfillmentStrategy,
    Product,
    ProductApprovalStatus,
    ProductDeliveryType,
    ProductStatus,
    ProductType,
    default_product_delivery_type,
    delivery_mode_value_for_delivery_type,
    product_approval_metadata,
    product_approval_status_from_metadata,
    product_metadata_with_approval,
    product_metadata_with_delivery_type,
    resolve_product_delivery_type,
)
from app.models.product_draft_source import ProductDraftSource


class ProductDeliveryTypeTests(unittest.TestCase):
    def test_delivery_type_is_free_or_paid_only(self):
        self.assertEqual(
            {item.value for item in ProductDeliveryType},
            {"FREE", "PAID"},
        )
        self.assertNotIn("INTERNAL", {item.value for item in ProductDeliveryType})

    def test_delivery_type_is_separate_from_product_type(self):
        self.assertNotIn(
            ProductDeliveryType.PAID.value,
            {item.value for item in ProductType},
        )
        self.assertNotIn(
            ProductDeliveryType.FREE.value,
            {item.value for item in ProductType},
        )

    def test_delivery_type_is_separate_from_fulfillment_strategy(self):
        self.assertNotIn(
            ProductDeliveryType.PAID.value,
            {item.value for item in FulfillmentStrategy},
        )
        self.assertNotIn(
            ProductDeliveryType.FREE.value,
            {item.value for item in FulfillmentStrategy},
        )

    def test_default_delivery_type_preserves_paid_behavior(self):
        self.assertEqual(default_product_delivery_type(), ProductDeliveryType.PAID)
        self.assertEqual(
            delivery_mode_value_for_delivery_type(default_product_delivery_type()),
            DeliveryMode.PAID.value,
        )

    def test_free_delivery_type_maps_to_existing_cms_delivery_mode(self):
        self.assertEqual(
            delivery_mode_value_for_delivery_type(ProductDeliveryType.FREE),
            DeliveryMode.INCLUDED.value,
        )

    def test_product_defaults_existing_rows_to_paid_delivery(self):
        product = self._product()

        self.assertEqual(product.delivery_type, ProductDeliveryType.PAID)

    def test_product_can_read_delivery_type_from_metadata(self):
        product = self._product(
            metadata={"delivery_type": ProductDeliveryType.FREE.value}
        )

        self.assertEqual(product.delivery_type, ProductDeliveryType.FREE)

    def test_product_from_row_reads_delivery_type_from_metadata(self):
        product = Product.from_row(
            {
                **self._row(),
                "metadata": {"delivery_type": "FREE"},
            }
        )

        self.assertEqual(product.delivery_type, ProductDeliveryType.FREE)

    def test_product_metadata_with_delivery_type_preserves_existing_metadata(self):
        metadata = product_metadata_with_delivery_type(
            {"theme": "GFE"},
            ProductDeliveryType.FREE,
        )

        self.assertEqual(metadata["theme"], "GFE")
        self.assertEqual(metadata["delivery_type"], ProductDeliveryType.FREE.value)

    def test_product_metadata_preserves_existing_delivery_type_when_not_overridden(self):
        metadata = product_metadata_with_delivery_type(
            {"theme": "GFE", "delivery_type": ProductDeliveryType.FREE.value},
        )

        self.assertEqual(metadata["theme"], "GFE")
        self.assertEqual(metadata["delivery_type"], ProductDeliveryType.FREE.value)

    def test_explicit_delivery_type_overrides_metadata_without_product_type(self):
        metadata = product_metadata_with_delivery_type(
            {"delivery_type": ProductDeliveryType.FREE.value},
            ProductDeliveryType.PAID,
        )

        self.assertEqual(metadata["delivery_type"], ProductDeliveryType.PAID.value)
        self.assertEqual(
            resolve_product_delivery_type(
                ProductDeliveryType.FREE,
                {"delivery_type": ProductDeliveryType.PAID.value},
            ),
            ProductDeliveryType.FREE,
        )

    def test_product_metadata_contains_canonical_delivery_type(self):
        product = self._product(
            metadata={"theme": "GFE", "delivery_type": "FREE"}
        )

        self.assertEqual(product.delivery_type, ProductDeliveryType.FREE)
        self.assertEqual(product.metadata["theme"], "GFE")
        self.assertEqual(product.metadata["delivery_type"], "FREE")

    def test_product_draft_source_defaults_delivery_type_to_paid(self):
        source = ProductDraftSource(
            source_id="asset-1",
            source_type="asset",
            product_type=ProductType.SINGLE_IMAGE,
            suggested_title="Test",
        )

        self.assertEqual(source.delivery_type, ProductDeliveryType.PAID)

    def test_product_approval_defaults_to_needs_review(self):
        self.assertEqual(
            product_approval_status_from_metadata({}),
            ProductApprovalStatus.NEEDS_REVIEW,
        )

    def test_product_metadata_with_approval_preserves_ai_recommendation(self):
        metadata = product_metadata_with_approval(
            {
                "delivery_type": "PAID",
                "commerce_intelligence": {"delivery_type": "PAID"},
            },
            ProductApprovalStatus.APPROVED,
            reviewed_by="creator",
            notes="Approved after review.",
        )

        approval = product_approval_metadata(metadata)
        self.assertEqual(approval["status"], ProductApprovalStatus.APPROVED.value)
        self.assertEqual(approval["approved_by"], "creator")
        self.assertEqual(approval["review_notes"], "Approved after review.")
        self.assertEqual(metadata["commerce_intelligence"]["delivery_type"], "PAID")
        self.assertEqual(metadata["delivery_type"], "PAID")

    def test_rejected_approval_clears_approved_metadata(self):
        approved = product_metadata_with_approval(
            {},
            ProductApprovalStatus.APPROVED,
            reviewed_by="creator",
        )
        rejected = product_metadata_with_approval(
            approved,
            ProductApprovalStatus.REJECTED,
            notes="Needs rework.",
        )

        approval = product_approval_metadata(rejected)
        self.assertEqual(approval["status"], ProductApprovalStatus.REJECTED.value)
        self.assertNotIn("approved_at", approval)
        self.assertNotIn("approved_by", approval)

    def _product(self, **overrides):
        values = self._row()
        values.update(overrides)
        return Product(**values)

    def _row(self):
        now = datetime.now(timezone.utc)
        return {
            "id": uuid4(),
            "creator_profile_id": 1,
            "legacy_content_item_id": None,
            "internal_name": "test-product",
            "display_name": "Test Product",
            "description": None,
            "product_type": ProductType.SINGLE_IMAGE,
            "status": ProductStatus.DRAFT,
            "price_cents": None,
            "base_price_cents": None,
            "min_price_cents": None,
            "max_price_cents": None,
            "currency": "USD",
            "media_link": None,
            "tags": (),
            "themes": (),
            "metadata": {},
            "activation_source": None,
            "activation_reason": None,
            "activated_at": None,
            "created_at": now,
            "updated_at": now,
        }


if __name__ == "__main__":
    unittest.main()
