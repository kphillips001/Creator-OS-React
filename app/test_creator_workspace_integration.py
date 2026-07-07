import unittest
import sys
import types
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.models.product import (
    ProductDeliveryType,
    ProductFulfillmentStatus,
    ProductStatus,
    ProductType,
)

if "psycopg" not in sys.modules:
    psycopg = types.ModuleType("psycopg")
    rows = types.ModuleType("psycopg.rows")
    psycopg_types = types.ModuleType("psycopg.types")
    json_types = types.ModuleType("psycopg.types.json")
    errors = types.ModuleType("psycopg.errors")
    psycopg.connect = lambda *args, **kwargs: None
    rows.dict_row = object()
    json_types.Json = lambda value: value
    errors.UniqueViolation = type("UniqueViolation", (Exception,), {})
    sys.modules["psycopg"] = psycopg
    sys.modules["psycopg.rows"] = rows
    sys.modules["psycopg.types"] = psycopg_types
    sys.modules["psycopg.types.json"] = json_types
    sys.modules["psycopg.errors"] = errors

from app.services.creator_workspace_service import CreatorWorkspaceService
from app.services.customer_business_service import CustomerBusinessService
from app.services.conversation_operations_service import ConversationOperationsService
from app.services.delivery_management_service import DeliveryManagementService
from app.services.relationship_management_service import RelationshipManagementService
from app.services.sales_management_service import SalesManagementService
from app.services.business_optimization_service import BusinessOptimizationService
from app.services.content_opportunity_service import ContentOpportunityService
from app.services.runtime_control_service import RuntimeControlService
from app.repositories.runtime_control_repository import RuntimeControlRepository
from app.test_conversation_operations_service import business_snapshot
from app.test_delivery_management_service import available_product
from app.test_telegram_business_service import (
    commerce_strategy_result,
    customer_snapshot,
    learning_context,
    product_business_snapshot,
)


class FakeAssetRepository:
    def list_all(self):
        return ()


class FakeProductRepository:
    pass


class FakeProductCatalogService:
    def __init__(self, displays):
        self.displays = tuple(displays)

    def count_workspace_products(self, creator_profile_id):
        return {
            ProductStatus.ACTIVE.value: 1,
            ProductStatus.DRAFT.value: 1,
        }

    def list_workspace_display_models(self, **kwargs):
        return self.displays[: kwargs.get("limit", len(self.displays))]


class FakeProductReviewService:
    def build_summary(self, **kwargs):
        return None

    def build_review_from_display(self, display):
        product = display.product
        approval_status = (
            "READY_TO_PUBLISH"
            if product.status == ProductStatus.ACTIVE
            else "NEEDS_REVIEW"
        )
        return SimpleNamespace(
            product_id=str(product.id),
            product_status=product.status.value,
            approval_status=approval_status,
            product=SimpleNamespace(status="available"),
            experience=SimpleNamespace(status="available"),
            commerce=SimpleNamespace(status="available", data={"confidence": 0.9}),
            publishing=SimpleNamespace(status=display.publishing.status),
            warnings=(),
        )


class FakePublishingService:
    def project_legacy_product_record(self, product):
        return SimpleNamespace(provider_error=None)

    def list_publishing_queue_items(self, limit=500):
        return ()


def product_display(
    *,
    product_id,
    name,
    status=ProductStatus.ACTIVE,
    fulfillment_status=ProductFulfillmentStatus.READY,
    media_link="https://example.test/media",
    publishing_status="PUBLISHING_COMPLETE",
):
    product = SimpleNamespace(
        id=product_id,
        display_name=name,
        internal_name=name.lower().replace(" ", "_"),
        status=status,
        product_type=ProductType.SINGLE_IMAGE,
        delivery_type=ProductDeliveryType.PAID,
        fulfillment_status=fulfillment_status,
        price_cents=1999,
        base_price_cents=1999,
        currency="USD",
        media_link=media_link,
        legacy_content_item_id=None,
        metadata={"commerce_intelligence": {"price": {"suggested_price_cents": 1999}}},
    )
    return SimpleNamespace(
        product=product,
        ordered_assets=(SimpleNamespace(id=101),),
        experience_presentation=SimpleNamespace(
            title="Experience",
            experience_id="experience-1",
            experience_type="STANDALONE",
            relationship_source="experience_read_model",
            compatibility=False,
        ),
        publishing=SimpleNamespace(status=publishing_status),
    )


class CreatorWorkspaceIntegrationTests(unittest.TestCase):
    def build_service(self, **kwargs):
        defaults = {
            "asset_repository": FakeAssetRepository(),
            "product_repository": FakeProductRepository(),
            "product_catalog_service": FakeProductCatalogService(
                (
                    product_display(
                        product_id="ready",
                        name="Ready Product",
                    ),
                )
            ),
            "publishing_service": FakePublishingService(),
            "product_review_service": FakeProductReviewService(),
            "wall_counts_fetcher": lambda **kwargs: {},
            "pending_mass_ppv_fetcher": lambda: 0,
            "failed_mass_ppv_fetcher": lambda: 0,
            "relationship_stats_fetcher": lambda account_id: {},
            "delayed_counts_fetcher": lambda **kwargs: {},
        }
        defaults.update(kwargs)
        return CreatorWorkspaceService(**defaults)

    def test_workspace_aggregates_phase_31_workflow_contracts(self):
        service = self.build_service(
            product_catalog_service=FakeProductCatalogService(
                (
                    product_display(
                        product_id="ready",
                        name="Ready Product",
                    ),
                    product_display(
                        product_id="link",
                        name="Link Product",
                        status=ProductStatus.DRAFT,
                        fulfillment_status=ProductFulfillmentStatus.NOT_READY,
                        media_link=None,
                        publishing_status="WAITING_FOR_MEDIA_LINK",
                    ),
                )
            ),
        )

        dashboard = service.build_dashboard(
            creator_profile={"id": 7},
            active_account={"id": 3, "oauth_access_token": "token"},
        )

        self.assertEqual(len(dashboard.workflow_items), 2)
        self.assertIsNotNone(dashboard.product_business_health)
        self.assertEqual(len(dashboard.product_business_cards), 2)
        self.assertGreaterEqual(
            len(dashboard.product_business_health.recommendations),
            1,
        )
        product_business = dashboard.product_business_cards[0]
        self.assertEqual(product_business.product_id, "ready")
        self.assertTrue(product_business.product_health)
        self.assertTrue(product_business.availability_status)
        self.assertTrue(product_business.performance_status)
        self.assertTrue(product_business.next_recommended_action)
        self.assertFalse(
            product_business.improvement.compatibility["modifies_products"]
        )
        self.assertFalse(
            product_business.improvement.compatibility["publishes_products"]
        )
        ready = dashboard.workflow_items[0]
        self.assertEqual(ready.workflow_snapshot.product_id, "ready")
        self.assertEqual(ready.current_workflow_stage, "TELEGRAM_READY")
        self.assertEqual(ready.current_lifecycle_stage, "TELEGRAM_READY")
        self.assertEqual(ready.publishing_status.state.value, "READY_FOR_TELEGRAM")
        self.assertFalse(ready.attention_summary.attention_required)

        needs_link = dashboard.workflow_items[1]
        self.assertEqual(needs_link.current_lifecycle_stage, "WAITING_FOR_MEDIA_LINK")
        self.assertEqual(
            needs_link.attention_summary.recommended_action,
            "Paste Media Link",
        )
        self.assertTrue(needs_link.attention_summary.attention_required)
        self.assertTrue(
            any(
                action.source == "CreatorAttentionService"
                and action.title == "Paste Media Link"
                for action in dashboard.recommended_actions
            )
        )

    def test_workspace_aggregates_telegram_business_dashboard(self):
        snapshot = business_snapshot()
        operation = ConversationOperationsService().build_operation(
            telegram_business_snapshot=snapshot
        )
        sales = SalesManagementService().build_management(
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            customer_snapshot=customer_snapshot(),
            commerce_strategy_result=commerce_strategy_result(),
            product_business_snapshot=product_business_snapshot(),
            learning_context=learning_context(),
        )
        delivery = DeliveryManagementService().build_management(
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            sales_management=sales,
            product_availability=available_product(),
            customer_snapshot=customer_snapshot(),
        )
        relationship = RelationshipManagementService().build_management(
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            sales_management=sales,
            delivery_management=delivery,
            customer_snapshot=customer_snapshot(),
            learning_context=learning_context(),
        )
        service = self.build_service(
            telegram_business_contexts_fetcher=lambda **kwargs: (
                {
                    "telegram_business_snapshot": snapshot,
                    "conversation_operation": operation,
                    "sales_management": sales,
                    "delivery_management": delivery,
                    "relationship_management": relationship,
                },
            )
        )

        dashboard = service.build_dashboard(
            creator_profile={"id": 7},
            active_account={"id": 3, "oauth_access_token": "token"},
        )

        telegram = dashboard.summary("Telegram Operations")
        self.assertEqual(
            next(
                metric.value
                for metric in telegram.metrics
                if metric.label == "Telegram Business Customers"
            ),
            "1",
        )
        self.assertEqual(len(dashboard.telegram_business_cards), 1)
        card = dashboard.telegram_business_cards[0]
        self.assertEqual(card.customer_id, "telegram-customer-1")
        self.assertEqual(card.relationship_health, "SELLING_READY")
        self.assertEqual(card.conversation_status, "DELIVERY_PENDING")
        self.assertEqual(card.sales_action, "Offer Premium Product")
        self.assertEqual(card.delivery_action, "Send Media Link")
        self.assertTrue(
            any(
                item.source == "Telegram Business"
                and item.operation_type == "telegram_business_customer"
                for item in dashboard.telegram_operations
            )
        )
        self.assertTrue(
            any(
                action.source == "Telegram Business"
                and action.title == "Increase Selling"
                for action in dashboard.recommended_actions
            )
        )
        self.assertTrue(card.compatibility)
        self.assertFalse(card.sales_management.compatibility["generates_commerce_strategy"])
        self.assertFalse(card.delivery_management.compatibility["executes_telegram"])
        self.assertFalse(
            card.relationship_management.compatibility[
                "modifies_customer_intelligence"
            ]
        )

    def test_workspace_customer_business_empty_state(self):
        service = self.build_service()

        dashboard = service.build_dashboard(
            creator_profile={"id": 7},
            active_account={"id": 3},
        )

        customer_business = dashboard.summary("Customer Business")
        self.assertEqual(len(dashboard.customer_business_cards), 0)
        self.assertEqual(
            next(
                metric.value
                for metric in customer_business.metrics
                if metric.label == "Customer Business Customers"
            ),
            "0",
        )
        self.assertEqual(
            next(
                metric.value
                for metric in customer_business.metrics
                if metric.label == "Operating State"
            ),
            "No Customer Business customers",
        )

    def test_workspace_consumes_customer_business_service(self):
        class FakeCustomerBusinessService:
            def __init__(self):
                self.calls = []

            def build_snapshot(self, **context):
                self.calls.append(context)
                return CustomerBusinessService().build_snapshot(**context)

        fake_service = FakeCustomerBusinessService()
        service = self.build_service(
            customer_business_service=fake_service,
            customer_business_contexts_fetcher=lambda **kwargs: (
                {
                    "customer_id": "customer-business-1",
                    "customer_snapshot": customer_snapshot(),
                    "sales_management": SimpleNamespace(
                        recommendation=SimpleNamespace(
                            recommendation_type="OFFER_BUNDLE",
                            priority="HIGH",
                            confidence=0.82,
                            recommended_next_action="Recommend bundle",
                        ),
                    ),
                },
            ),
        )

        dashboard = service.build_dashboard(
            creator_profile={"id": 7},
            active_account={"id": 3},
        )

        self.assertEqual(len(fake_service.calls), 1)
        self.assertEqual(len(dashboard.customer_business_cards), 1)
        card = dashboard.customer_business_cards[0]
        self.assertEqual(card.customer_id, "customer-business-1")
        self.assertEqual(card.provider, "provider_neutral")
        self.assertTrue(card.customer_health)
        self.assertTrue(card.journey_stage)
        self.assertTrue(card.value_tier)
        self.assertTrue(card.retention_status)
        self.assertTrue(card.growth_stage)
        self.assertTrue(card.next_recommended_action)
        self.assertTrue(card.compatibility)

        customer_business = dashboard.summary("Customer Business")
        self.assertEqual(
            next(
                metric.value
                for metric in customer_business.metrics
                if metric.label == "Customer Business Customers"
            ),
            "1",
        )
        self.assertGreaterEqual(
            int(
                next(
                    metric.value
                    for metric in customer_business.metrics
                    if metric.label == "Recommended Customer Actions"
                )
            ),
            1,
        )
        self.assertTrue(
            any(
                action.source == "Customer Business"
                and action.target == "Customer Workspace"
                for action in dashboard.recommended_actions
            )
        )
        self.assertTrue(
            card.customer_business.compatibility["read_only"]
        )
        self.assertFalse(
            card.customer_business.compatibility["executes_telegram"]
        )
        self.assertFalse(
            card.customer_business.compatibility[
                "changes_decision_engine_behavior"
            ]
        )

    def test_existing_business_dashboards_remain_available_with_customer_business(self):
        service = self.build_service(
            customer_business_contexts_fetcher=lambda **kwargs: (
                {
                    "customer_business_snapshot": CustomerBusinessService().build_snapshot(
                        customer_id="customer-business-2",
                        customer_snapshot=customer_snapshot(),
                    )
                },
            )
        )

        dashboard = service.build_dashboard(
            creator_profile={"id": 7},
            active_account={"id": 3},
        )

        self.assertIsNotNone(dashboard.product_business_health)
        self.assertGreaterEqual(len(dashboard.product_business_cards), 1)
        self.assertIn("Telegram Operations", dashboard.summaries)
        self.assertIn("Customer Business", dashboard.summaries)
        self.assertEqual(len(dashboard.customer_business_cards), 1)

    def test_workspace_consumes_business_optimization_service(self):
        class FakeBusinessOptimizationService:
            def __init__(self):
                self.calls = []

            def build_snapshot(self, **context):
                self.calls.append(context)
                return BusinessOptimizationService().build_snapshot(**context)

        fake_service = FakeBusinessOptimizationService()
        service = self.build_service(
            business_optimization_service=fake_service,
            customer_business_contexts_fetcher=lambda **kwargs: (
                {
                    "customer_business_snapshot": CustomerBusinessService().build_snapshot(
                        customer_id="customer-business-3",
                        customer_snapshot=customer_snapshot(),
                    )
                },
            ),
        )

        dashboard = service.build_dashboard(
            creator_profile={"id": 7},
            active_account={"id": 3},
        )

        self.assertEqual(len(fake_service.calls), 1)
        self.assertIn("Business Optimization", dashboard.summaries)
        self.assertIsNotNone(dashboard.business_optimization_card)
        card = dashboard.business_optimization_card
        self.assertTrue(card.overall_business_health)
        self.assertTrue(card.performance_health)
        self.assertTrue(card.strategy_health)
        self.assertTrue(card.revenue_readiness)
        self.assertTrue(card.next_recommended_business_action)
        self.assertTrue(card.compatibility)
        business_optimization = dashboard.summary("Business Optimization")
        self.assertEqual(
            next(
                metric.value
                for metric in business_optimization.metrics
                if metric.label == "Overall Business Health"
            ),
            card.overall_business_health,
        )
        self.assertTrue(
            any(
                action.source == "Business Optimization"
                for action in dashboard.recommended_actions
            )
        )
        self.assertTrue(
            card.business_optimization.compatibility["read_only"]
        )
        self.assertFalse(
            card.business_optimization.compatibility["executes_telegram"]
        )
        self.assertFalse(
            card.business_optimization.compatibility[
                "changes_decision_engine_behavior"
            ]
        )

    def test_workspace_business_optimization_empty_state(self):
        class FailingBusinessOptimizationService:
            def build_snapshot(self, **context):
                raise RuntimeError("unavailable")

        service = self.build_service(
            business_optimization_service=FailingBusinessOptimizationService(),
        )

        dashboard = service.build_dashboard(
            creator_profile={"id": 7},
            active_account={"id": 3},
        )

        self.assertIsNone(dashboard.business_optimization_card)
        business_optimization = dashboard.summary("Business Optimization")
        self.assertEqual(
            next(
                metric.value
                for metric in business_optimization.metrics
                if metric.label == "Overall Business Health"
            ),
            "UNKNOWN",
        )
        self.assertEqual(
            next(
                metric.value
                for metric in business_optimization.metrics
                if metric.label == "Today's Business Actions"
            ),
            "0",
        )

    def test_existing_business_dashboards_remain_available_with_business_optimization(self):
        service = self.build_service()

        dashboard = service.build_dashboard(
            creator_profile={"id": 7},
            active_account={"id": 3},
        )

        self.assertIsNotNone(dashboard.product_business_health)
        self.assertGreaterEqual(len(dashboard.product_business_cards), 1)
        self.assertIn("Telegram Operations", dashboard.summaries)
        self.assertIn("Customer Business", dashboard.summaries)
        self.assertIn("Business Optimization", dashboard.summaries)

    def test_workspace_consumes_content_opportunity_service(self):
        class FakeContentOpportunityService:
            def __init__(self):
                self.calls = 0
                self.service = ContentOpportunityService()
                self._seeded = False

            def build_snapshot(self):
                self.calls += 1
                if not self._seeded:
                    self.service.resolve_content_request(
                        customer_id="vip-customer",
                        provider="telegram",
                        provider_customer_id="telegram-vip",
                        request_text="Do you have shower videos?",
                        normalized_terms=("shower", "video"),
                        requested_content_type="video",
                        requested_format="video",
                        is_vip=True,
                    )
                    self.service.resolve_content_request(
                        customer_id="returning-customer",
                        provider="telegram",
                        request_text="Any shower video content?",
                        normalized_terms=("shower", "video"),
                        requested_content_type="video",
                        requested_format="video",
                    )
                    self.service.resolve_content_request(
                        customer_id="matched-customer",
                        provider="telegram",
                        request_text="Do you have beach photos?",
                        normalized_terms=("beach", "photos"),
                        requested_content_type="photo",
                        requested_format="photo",
                        product_candidates=(
                            {
                                "id": "product-beach",
                                "name": "Beach Photos",
                                "description": "Beach photo set",
                                "tags": ("beach", "photos"),
                                "published_active": True,
                            },
                        ),
                    )
                    resolutions = self.service.resolve_opportunities_for_product(
                        {
                            "id": "product-shower",
                            "name": "Shower Videos",
                            "description": "New shower video set",
                            "tags": ("shower", "video"),
                        }
                    )
                    for resolution in resolutions:
                        self.service.create_follow_up_opportunities(resolution)
                    self._seeded = True
                return self.service.build_snapshot()

        fake_service = FakeContentOpportunityService()
        service = self.build_service(content_opportunity_service=fake_service)

        dashboard = service.build_dashboard(
            creator_profile={"id": 7},
            active_account={"id": 3},
        )

        self.assertEqual(fake_service.calls, 1)
        self.assertIn("Content Opportunity", dashboard.summaries)
        self.assertIsNotNone(dashboard.content_opportunity_card)
        card = dashboard.content_opportunity_card
        self.assertGreaterEqual(card.total_requests, 3)
        self.assertGreaterEqual(card.matched_requests, 1)
        self.assertGreaterEqual(card.unmatched_requests, 1)
        self.assertGreaterEqual(card.trending_topic_count, 1)
        self.assertGreaterEqual(card.repeat_demand_count, 1)
        self.assertGreaterEqual(card.vip_demand_count, 1)
        self.assertGreaterEqual(card.resolution_ready_count, 1)
        self.assertGreaterEqual(card.waiting_customer_count, 1)
        self.assertTrue(card.waiting_customers)
        self.assertGreaterEqual(card.ready_follow_up_count, 1)
        self.assertTrue(card.compatibility)

        content_opportunity = dashboard.summary("Content Opportunity")
        self.assertEqual(
            next(
                metric.value
                for metric in content_opportunity.metrics
                if metric.label == "Total Requests"
            ),
            str(card.total_requests),
        )
        self.assertEqual(
            next(
                metric.value
                for metric in content_opportunity.metrics
                if metric.label == "Opportunity Health"
            ),
            card.opportunity_health,
        )
        self.assertEqual(
            next(
                metric.value
                for metric in content_opportunity.metrics
                if metric.label == "Waiting Customers"
            ),
            str(card.waiting_customer_count),
        )
        self.assertTrue(
            any(
                notification.source == "Content Opportunity"
                and "demand" in notification.title.lower()
                for notification in dashboard.notifications
            )
        )
        self.assertTrue(
            any(
                action.source == "Content Opportunity"
                and action.target == "Content Opportunity Center"
                for action in dashboard.recommended_actions
            )
        )
        self.assertTrue(
            card.content_opportunity.compatibility["read_only"]
        )
        self.assertFalse(
            card.content_opportunity.compatibility["executes_telegram"]
        )
        self.assertFalse(
            card.content_opportunity.compatibility["modifies_products"]
        )

    def test_workspace_displays_runtime_control_state(self):
        with TemporaryDirectory() as directory:
            runtime = RuntimeControlService(
                repository=RuntimeControlRepository(f"{directory}/runtime.json")
            )
            runtime.observe(creator_profile_id=7)
            service = self.build_service(runtime_control_service=runtime)

            dashboard = service.build_dashboard(
                creator_profile={"id": 7},
                active_account={"id": 3},
            )

            self.assertIn("Runtime Control", dashboard.summaries)
            self.assertIsNotNone(dashboard.runtime_control_card)
            card = dashboard.runtime_control_card
            self.assertEqual(card.current_mode, "OBSERVE")
            self.assertEqual(card.runtime_status, "OBSERVE")
            self.assertIn("observing conversations", card.warning_banner)
            runtime_summary = dashboard.summary("Runtime Control")
            self.assertEqual(
                next(
                    metric.value
                    for metric in runtime_summary.metrics
                    if metric.label == "Current Mode"
                ),
                "OBSERVE",
            )

    def test_workspace_content_opportunity_empty_state(self):
        class FailingContentOpportunityService:
            def build_snapshot(self):
                raise RuntimeError("unavailable")

        service = self.build_service(
            content_opportunity_service=FailingContentOpportunityService(),
        )

        dashboard = service.build_dashboard(
            creator_profile={"id": 7},
            active_account={"id": 3},
        )

        self.assertIsNone(dashboard.content_opportunity_card)
        content_opportunity = dashboard.summary("Content Opportunity")
        self.assertEqual(
            next(
                metric.value
                for metric in content_opportunity.metrics
                if metric.label == "Total Requests"
            ),
            "0",
        )
        self.assertEqual(
            next(
                metric.value
                for metric in content_opportunity.metrics
                if metric.label == "Opportunity Health"
            ),
            "UNKNOWN",
        )

    def test_existing_business_dashboards_remain_available_with_content_opportunity(self):
        service = self.build_service()

        dashboard = service.build_dashboard(
            creator_profile={"id": 7},
            active_account={"id": 3},
        )

        self.assertIsNotNone(dashboard.product_business_health)
        self.assertGreaterEqual(len(dashboard.product_business_cards), 1)
        self.assertIn("Telegram Operations", dashboard.summaries)
        self.assertIn("Customer Business", dashboard.summaries)
        self.assertIn("Business Optimization", dashboard.summaries)
        self.assertIn("Content Opportunity", dashboard.summaries)

    def test_creator_workspace_customer_business_ui_is_presentation_only(self):
        from pathlib import Path

        source = Path("app/dashboard/pages/creator_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("### Customer Business", source)
        self.assertIn("_render_customer_business", source)
        self.assertIn("dashboard.customer_business_cards", source)
        self.assertNotIn("CustomerBusinessService(", source)
        self.assertNotIn("DecisionEngine(", source)
        self.assertNotIn("send_text(", source)

    def test_creator_workspace_business_optimization_ui_is_presentation_only(self):
        from pathlib import Path

        source = Path("app/dashboard/pages/creator_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("### Business Optimization", source)
        self.assertIn("_render_business_optimization", source)
        self.assertIn("dashboard.business_optimization_card", source)
        self.assertNotIn("BusinessOptimizationService(", source)
        self.assertNotIn("DecisionEngine(", source)
        self.assertNotIn("send_text(", source)

    def test_creator_workspace_content_opportunity_ui_is_presentation_only(self):
        from pathlib import Path

        source = Path("app/dashboard/pages/creator_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("### Content Opportunity Center", source)
        self.assertIn("_render_content_opportunity_center", source)
        self.assertIn("dashboard.content_opportunity_card", source)
        self.assertNotIn("ContentOpportunityService(", source)
        self.assertNotIn("DecisionEngine(", source)
        self.assertNotIn("send_text(", source)
        self.assertNotIn("publish_product(", source)


if __name__ == "__main__":
    unittest.main()
