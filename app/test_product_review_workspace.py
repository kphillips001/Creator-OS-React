import unittest
from pathlib import Path

from app.dashboard.navigation import (
    DASHBOARD_NAVIGATION_GROUPS,
    DASHBOARD_PAGE_LABELS,
    DASHBOARD_PAGE_OPTIONS,
    PROFILE_LOCKED_PAGES,
)


class ProductReviewWorkspaceTests(unittest.TestCase):
    def test_product_review_is_registered_in_products_navigation(self):
        self.assertIn("Product Review", DASHBOARD_PAGE_OPTIONS)
        self.assertIn("Product Review", PROFILE_LOCKED_PAGES)
        self.assertEqual(
            DASHBOARD_PAGE_LABELS["Product Review"],
            "Products: Product Review",
        )
        products_group = next(
            group
            for group in DASHBOARD_NAVIGATION_GROUPS
            if group.label == "Products"
        )
        self.assertEqual(products_group.items[0].page, "Product Review")

    def test_product_review_page_consumes_product_review_service(self):
        source = Path("app/dashboard/pages/product_review.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ProductReviewService", source)
        self.assertIn("service.build_summary", source)
        self.assertNotIn("ProductRepository", source)
        self.assertNotIn("AIProductDraftingService", source)
        self.assertNotIn("PublishingService", source)

    def test_product_review_edit_entry_opens_existing_catalog_editor(self):
        source = Path("app/dashboard/pages/product_review.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def open_product_catalog_editor", source)
        self.assertIn('"product_catalog_mode"] = "EDIT"', source)
        self.assertIn('"product_catalog_selected_product_id"] = product_id', source)
        self.assertIn('dashboard_page = "Product Catalog"', source)
        self.assertIn("Edit in Catalog", source)
        self.assertNotIn(".update_product(", source)
        self.assertNotIn(".transition_status(", source)
        self.assertNotIn(".save_media_link(", source)

    def test_commerce_reset_delegates_to_product_catalog_service(self):
        source = Path("app/dashboard/pages/product_review.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ProductCatalogService", source)
        self.assertIn("def reset_commerce_override", source)
        self.assertIn("service.reset_product_commerce_to_ai", source)
        self.assertIn("f\"Reset {label}\"", source)
        self.assertNotIn("ProductRepository", source)
        self.assertNotIn(".update_product(", source)

    def test_approval_actions_delegate_to_product_catalog_service(self):
        source = Path("app/dashboard/pages/product_review.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def approve_product_review", source)
        self.assertIn("def mark_product_review_needs_review", source)
        self.assertIn("def reject_product_review", source)
        self.assertIn("service.approve_product", source)
        self.assertIn("service.mark_product_needs_review", source)
        self.assertIn("service.reject_product", source)
        self.assertIn("Approve Product", source)
        self.assertIn("Mark Needs Review", source)
        self.assertIn("Reject Product", source)
        self.assertNotIn("PublishingService", source)

    def test_product_catalog_owns_editable_delivery_type_and_save_command(self):
        source = Path("app/dashboard/pages/product_catalog.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ProductCatalogService", source)
        self.assertIn("Create Manual Product", source)
        self.assertIn("ProductDeliveryType", source)
        self.assertIn('"Delivery Type"', source)
        self.assertIn("delivery_type = st.selectbox", source)
        self.assertIn("ProductCatalogCommand(", source)
        self.assertIn("delivery_type=delivery_type", source)
        self.assertIn("service.update_product(", source)
        self.assertNotIn("ProductRepository", source)

    def test_manual_product_creation_defaults_to_product_review(self):
        repository_source = Path("app/repositories/product_repository.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"creation_source": "manual"', repository_source)
        self.assertIn('"manual_product": True', repository_source)
        self.assertIn("ProductApprovalStatus.NEEDS_REVIEW", repository_source)
        self.assertIn("product_metadata_with_approval", repository_source)

        review_source = Path("app/services/product_review_service.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Manual Product", review_source)
        self.assertIn("AI Product Draft", review_source)

    def test_product_catalog_service_owns_reset_to_ai_persistence(self):
        source = Path("app/services/product_catalog_service.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def reset_product_commerce_to_ai", source)
        self.assertIn("_commerce_intelligence_metadata", source)
        self.assertIn("ProductCatalogCommand(", source)
        self.assertIn("return self.update_product(product_id, command)", source)
        self.assertIn('"price"', source)
        self.assertIn('"delivery_type"', source)
        self.assertIn('"product_type"', source)

    def test_product_catalog_service_owns_approval_persistence(self):
        source = Path("app/services/product_catalog_service.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def approve_product", source)
        self.assertIn("def mark_product_needs_review", source)
        self.assertIn("def reject_product", source)
        self.assertIn("update_approval_metadata", source)
        self.assertIn("ProductApprovalStatus.READY_TO_PUBLISH", source)
        self.assertIn("ProductApprovalStatus.NEEDS_REVIEW", source)
        self.assertIn("ProductApprovalStatus.REJECTED", source)

    def test_product_repository_persists_approval_metadata(self):
        source = Path("app/repositories/product_repository.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def update_approval_metadata", source)
        self.assertIn("product_metadata_with_approval", source)
        self.assertIn("metadata = %s::jsonb", source)

    def test_publishing_projection_consumes_approval_without_owning_it(self):
        source = Path("app/services/publishing_service.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("approval_status", source)
        self.assertIn("Needs Approval", source)
        self.assertIn("Not Approved", source)
        self.assertNotIn("update_approval_metadata", source)

    def test_main_router_exposes_product_review_page(self):
        source = Path("app/dashboard/main.py").read_text(encoding="utf-8")
        self.assertIn("render_product_review", source)
        self.assertIn('== "Product Review"', source)

    def test_creator_workspace_consumes_product_review_service(self):
        service_source = Path("app/services/creator_workspace_service.py").read_text(
            encoding="utf-8"
        )
        page_source = Path("app/dashboard/pages/creator_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("ProductReviewService", service_source)
        self.assertIn("self.product_review_service.build_summary", service_source)
        self.assertIn("build_review_from_display", service_source)
        self.assertIn("product_review=product_review", service_source)
        self.assertIn("dashboard.product_review", page_source)
        self.assertIn("Open Product Review", page_source)
        self.assertIn("Review Product", page_source)
        self.assertNotIn("ProductRepository", page_source)


if __name__ == "__main__":
    unittest.main()
