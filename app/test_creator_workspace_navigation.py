import unittest
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

if "streamlit" not in sys.modules:
    streamlit = types.ModuleType("streamlit")
    sys.modules["streamlit"] = streamlit

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

from app.dashboard.navigation import (
    DASHBOARD_NAVIGATION_GROUPS,
    DASHBOARD_PAGE_LABELS,
    DASHBOARD_PAGE_OPTIONS,
    grouped_navigation_label_for_page,
    grouped_navigation_labels,
    page_for_grouped_navigation_label,
    normalize_dashboard_page,
)
from app.dashboard.pages.creator_workspace import (
    WORKSPACE_SECTIONS,
    _business_greeting,
    _creator_attention_items,
    _daily_business_snapshot,
    _daily_business_status,
)
from app.models.workspace_dashboard import (
    WorkspaceDashboard,
    WorkspaceMetric,
    WorkspaceSummary,
)
from app.models.product import (
    ProductDeliveryType,
    ProductFulfillmentStatus,
    ProductStatus,
    ProductType,
)
from app.services.creator_workspace_service import CreatorWorkspaceService


class CreatorWorkspaceNavigationTests(unittest.TestCase):
    def test_creator_hq_is_primary_dashboard_route_with_workspace_compatibility(self):
        self.assertEqual(DASHBOARD_PAGE_OPTIONS[0], "Creator Workspace")
        self.assertEqual(
            DASHBOARD_PAGE_LABELS["Creator Workspace"],
            "Creator HQ",
        )
        self.assertEqual(normalize_dashboard_page(None), "Creator Workspace")
        self.assertEqual(normalize_dashboard_page("Creator HQ"), "Creator Workspace")
        self.assertEqual(
            normalize_dashboard_page("missing"),
            "Creator Workspace",
        )

    def test_workspace_sections_target_existing_routes(self):
        targets = {
            section.primary_target
            for section in WORKSPACE_SECTIONS
            if section.primary_target
        }
        for section in WORKSPACE_SECTIONS:
            targets.update(target for _, target in section.secondary_targets)

        self.assertIn("CMS Upload", targets)
        self.assertIn("Product Catalog", targets)
        self.assertIn("Wall Scheduler", targets)
        self.assertIn("Mass PPV Dashboard", targets)
        self.assertIn("Chat Console", targets)
        self.assertIn("Creator Profile", targets)
        self.assertTrue(targets.issubset(set(DASHBOARD_PAGE_OPTIONS)))

    def test_sidebar_navigation_is_grouped_by_creator_os_domains(self):
        group_labels = [group.label for group in DASHBOARD_NAVIGATION_GROUPS]

        self.assertEqual(group_labels[0], "Creator HQ")
        self.assertEqual(
            group_labels,
            [
                "Creator HQ",
                "AI",
                "Assets",
                "Experiences",
                "Products",
                "Publishing",
                "Customer Conversations",
                "Activity",
                "Notifications",
                "Administration",
            ],
        )

        labels = grouped_navigation_labels()
        self.assertEqual(labels.count("Creator HQ"), 1)
        self.assertIn("AI", labels)
        self.assertIn("  Creator Agent", labels)
        self.assertIn("  Developer Agent", labels)
        self.assertIn("Assets", labels)
        self.assertIn("  CMS Upload", labels)
        self.assertIn("Experiences", labels)
        self.assertIn("  Experience Overview (Coming Soon)", labels)
        self.assertIn("  Activity Feed", labels)
        self.assertIn("  Delayed Messages", labels)
        self.assertIn("Notifications", labels)
        self.assertIn("  Notifications (Coming Soon)", labels)

        icons = {group.label: group.icon for group in DASHBOARD_NAVIGATION_GROUPS}
        self.assertEqual(icons["Creator HQ"], "HQ")
        self.assertEqual(icons["Assets"], "AS")
        self.assertEqual(icons["Publishing"], "PB")

    def test_existing_routes_remain_reachable_from_grouped_navigation(self):
        reachable_pages = {
            page_for_grouped_navigation_label(label)
            for label in grouped_navigation_labels()
        }
        reachable_pages.discard(None)

        self.assertEqual(reachable_pages, set(DASHBOARD_PAGE_OPTIONS))
        for page in DASHBOARD_PAGE_OPTIONS:
            label = grouped_navigation_label_for_page(page)
            self.assertEqual(page_for_grouped_navigation_label(label), page)

    def test_dashboard_router_imports_and_routes_workspace(self):
        source = Path("app/dashboard/main.py").read_text(encoding="utf-8")

        self.assertIn("render_creator_workspace", source)
        self.assertIn("render_creator_agent", source)
        self.assertIn("render_developer_agent", source)
        self.assertIn("render_activity_feed", source)
        self.assertIn('== "Creator Workspace"', source)
        self.assertIn('== "Creator Agent"', source)
        self.assertIn('== "Developer Agent"', source)
        self.assertIn('== "Activity Feed"', source)
        self.assertIn('"Creator Workspace"', source)
        self.assertIn("_render_sidebar_navigation", source)
        self.assertIn("DASHBOARD_NAVIGATION_GROUPS", source)
        self.assertIn("st.sidebar.expander", source)

    def test_streamlit_builtin_page_navigation_is_hidden(self):
        source = Path(".streamlit/config.toml").read_text(encoding="utf-8")

        self.assertIn("showSidebarNavigation=false", source)

    def test_workspace_summaries_use_existing_boundaries_read_only(self):
        now = datetime.now(timezone.utc)
        earlier = now - timedelta(hours=2)
        latest = now + timedelta(minutes=1)
        assets = [
            SimpleNamespace(
                id=1,
                file_name="ready.jpg",
                created_at=earlier,
                status="active",
                is_active=True,
                classification="selfie",
                ready_for_rotation=True,
                blurred_preview_path="/tmp/preview.jpg",
            ),
            SimpleNamespace(
                id=2,
                file_name="processing.jpg",
                created_at=now,
                status="processing",
                is_active=True,
                classification=None,
                ready_for_rotation=False,
                blurred_preview_path=None,
                fanvue_upload_error="failed",
            ),
        ]

        class FakeAssetRepository:
            def list_all(self):
                return assets

        class FakeProductRepository:
            def get_by_id(self, product_id, **kwargs):
                return SimpleNamespace(
                    id=product_id,
                    delivery_type=ProductDeliveryType.PAID,
                )

        class FakeProductCatalogService:
            def __init__(self):
                self.count_calls = []
                self.display_calls = []
                self.products = (
                    SimpleNamespace(
                        id="product-ready",
                        status=ProductStatus.ACTIVE,
                        product_type=ProductType.PHOTO_SET,
                        delivery_type=ProductDeliveryType.PAID,
                        price_cents=1999,
                        base_price_cents=2499,
                        currency="USD",
                        media_link="https://example.test/product-ready",
                        fulfillment_status=ProductFulfillmentStatus.READY,
                        display_name="Ready Product",
                        internal_name="ready_product",
                        legacy_content_item_id=None,
                        metadata={
                            "commerce_intelligence": {
                                "price": {"suggested_price_cents": 2499}
                            }
                        },
                        created_at=earlier,
                        updated_at=latest,
                    ),
                    SimpleNamespace(
                        id="product-review",
                        status=ProductStatus.ACTIVE,
                        product_type=ProductType.SINGLE_IMAGE,
                        delivery_type=ProductDeliveryType.FREE,
                        price_cents=None,
                        base_price_cents=0,
                        currency="USD",
                        media_link=None,
                        fulfillment_status=ProductFulfillmentStatus.NOT_READY,
                        display_name="Review Product",
                        internal_name="review_product",
                        legacy_content_item_id=2,
                        metadata={},
                        created_at=earlier,
                        updated_at=earlier,
                    ),
                    SimpleNamespace(
                        id="product-draft",
                        status=ProductStatus.DRAFT,
                        product_type=ProductType.STORY,
                        delivery_type=ProductDeliveryType.PAID,
                        price_cents=3999,
                        base_price_cents=3999,
                        currency="USD",
                        media_link=None,
                        fulfillment_status=ProductFulfillmentStatus.FAILED,
                        display_name="Draft Product",
                        internal_name="draft_product",
                        legacy_content_item_id=None,
                        metadata={},
                        created_at=earlier,
                        updated_at=earlier,
                    ),
                )

            def count_workspace_products(self, creator_profile_id):
                self.count_calls.append(creator_profile_id)
                return {
                    ProductStatus.ACTIVE.value: 2,
                    ProductStatus.DRAFT.value: 1,
                    ProductStatus.ARCHIVED.value: 1,
                    ProductStatus.DISABLED.value: 0,
                }

            def list_workspace_display_models(self, **kwargs):
                self.display_calls.append(kwargs)
                product_ready, product_review, product_draft = self.products
                return (
                    SimpleNamespace(
                        product=product_ready,
                        ordered_assets=(SimpleNamespace(id=1), SimpleNamespace(id=2)),
                        publishing=SimpleNamespace(
                            status="Uploaded to Fanvue",
                            detail="Provider media available.",
                        ),
                        experience_presentation=SimpleNamespace(
                            title="Set",
                            experience_type="PHOTOSHOOT",
                            relationship_source="experience_read_model",
                            compatibility=False,
                        ),
                    ),
                    SimpleNamespace(
                        product=product_review,
                        ordered_assets=(),
                        publishing=SimpleNamespace(
                            status="Not uploaded to Fanvue",
                            detail="No provider media.",
                        ),
                        experience_presentation=None,
                    ),
                    SimpleNamespace(
                        product=product_draft,
                        ordered_assets=(SimpleNamespace(id=3),),
                        publishing=SimpleNamespace(
                            status="Failed Fanvue upload",
                            detail="Provider upload failed.",
                        ),
                        experience_presentation=SimpleNamespace(
                            title="Story",
                            experience_type="STORY",
                            relationship_source="product_asset_compatibility",
                            compatibility=True,
                        ),
                    ),
                )

        class FakeExperienceService:
            def __init__(self):
                self.relationship_calls = []

            def list_experiences(self, **kwargs):
                self.kwargs = kwargs
                return [
                    SimpleNamespace(
                        experience_id="experience-solo",
                        experience_type="STANDALONE",
                        is_standalone=True,
                        is_collection=False,
                        ordered_asset_ids=(1,),
                        asset_ids=(1,),
                        cover_asset_id=1,
                        title="Solo",
                        description="Solo summary",
                        metadata={
                            "experience_intelligence": {"source": "test"},
                            "suggested_themes": ("solo",),
                            "suggested_keywords": ("intro",),
                            "mood": "warm",
                            "publishing_readiness": "ready",
                        },
                        created_at=earlier,
                    ),
                    SimpleNamespace(
                        experience_id="experience-set",
                        experience_type="PHOTOSHOOT",
                        is_standalone=False,
                        is_collection=True,
                        ordered_asset_ids=(1, 2),
                        asset_ids=(1, 2),
                        cover_asset_id=1,
                        title="Set",
                        description="Set summary",
                        metadata={
                            "experience_intelligence": {"source": "test"},
                            "story_progression": "teaser to reveal",
                        },
                        created_at=now,
                    ),
                    SimpleNamespace(
                        experience_id="experience-missing-cover",
                        experience_type="STORY",
                        is_standalone=False,
                        is_collection=True,
                        ordered_asset_ids=(3,),
                        asset_ids=(3,),
                        cover_asset_id=None,
                        title="Missing Cover",
                        description=None,
                        metadata={},
                        created_at=earlier,
                    ),
                ]

            def list_experience_product_relationships(self, experience_id):
                self.relationship_calls.append(experience_id)
                if experience_id == "experience-solo":
                    return (
                        SimpleNamespace(
                            product_id="product-solo",
                            source="experience_read_model",
                            compatibility=False,
                            compatibility_experience_id=False,
                            metadata={
                                "suggested_themes": ("relationship-theme",),
                                "suggested_keywords": ("relationship-keyword",),
                            },
                        ),
                    )
                return ()

        class FakeAssetLibraryService:
            def search_assets(self, filters):
                return SimpleNamespace(items=tuple(assets[: filters.limit]))

            def get_asset_items(self, asset_ids):
                return tuple(
                    SimpleNamespace(
                        asset_id=asset_id,
                        publishing=SimpleNamespace(
                            provider_media_id=(
                                "provider-media" if asset_id == 1 else None
                            ),
                            status="Uploaded to Provider",
                        ),
                    )
                    for asset_id in asset_ids
                )

        class FakePublishingService:
            def __init__(self):
                self.projected_products = []

            def project_experience_readiness(self, experience, *, asset_records=()):
                ready = sum(
                    1
                    for record in asset_records
                    if record.get("provider_media_id")
                )
                return SimpleNamespace(
                    status="ready" if ready else "unknown",
                    detail=f"{ready} asset(s) provider-ready.",
                    asset_count=len(getattr(experience, "asset_ids", ())),
                    ready_asset_count=ready,
                    source="PublishingService",
                    compatibility=False,
                )

            def project_legacy_product_record(self, product):
                self.projected_products.append(product.id)
                return {"provider_error": None}

            def list_publishing_queue_items(self, *, limit=500):
                return (
                    SimpleNamespace(
                        status="QUEUED",
                        upload_status="QUEUED",
                        waiting_for_media_link=False,
                        failed_upload=False,
                        retry_state="NOT_RETRIED",
                        provider="fanvue",
                    ),
                    SimpleNamespace(
                        status="UPLOADING",
                        upload_status="UPLOADING",
                        waiting_for_media_link=False,
                        failed_upload=False,
                        retry_state="NOT_RETRIED",
                        provider="fanvue",
                    ),
                    SimpleNamespace(
                        status="WAITING_FOR_MEDIA_LINK",
                        upload_status="UPLOADED",
                        waiting_for_media_link=True,
                        failed_upload=False,
                        retry_state="NOT_RETRIED",
                        provider="fanvue",
                    ),
                    SimpleNamespace(
                        status="RETRY_REQUIRED",
                        upload_status="RETRY_REQUIRED",
                        waiting_for_media_link=False,
                        failed_upload=True,
                        retry_state="RETRY_REQUIRED",
                        provider="fanvue",
                    ),
                    SimpleNamespace(
                        status="PUBLISHING_COMPLETE",
                        upload_status="UPLOADED",
                        waiting_for_media_link=False,
                        failed_upload=False,
                        retry_state="NOT_RETRIED",
                        provider="fanvue",
                    ),
                )

        class FakeCreatorReviewService:
            def __init__(self):
                self.calls = []

            def build_workspace_review_summary(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(
                    total_pending=6,
                    assets_awaiting_review=3,
                    experiences_awaiting_review=1,
                    products_awaiting_review=1,
                    high_priority_reviews=3,
                    publishing_reviews_remaining=1,
                    completed_reviews=None,
                    review_completion_percentage=None,
                    items=(
                        SimpleNamespace(
                            review_type="assets",
                            title="Assets awaiting review",
                            detail="3 Asset(s) need creator review.",
                            status="pending",
                            priority="warning",
                            target="Asset Library",
                            confidence=None,
                            evidence_available=True,
                            override_proposals=("classification",),
                            completeness="partial",
                        ),
                    ),
                )

        experience_service = FakeExperienceService()
        product_catalog = FakeProductCatalogService()
        publishing_service = FakePublishingService()
        creator_review = FakeCreatorReviewService()
        dashboard = CreatorWorkspaceService(
            asset_repository=FakeAssetRepository(),
            asset_library_service=FakeAssetLibraryService(),
            product_repository=FakeProductRepository(),
            product_catalog_service=product_catalog,
            experience_service=experience_service,
            publishing_service=publishing_service,
            creator_review_service=creator_review,
            wall_counts_fetcher=lambda **kwargs: {
                "pending": 4,
                "processing": 1,
                "completed": 8,
                "failed": 1,
            },
            pending_mass_ppv_fetcher=lambda: 2,
            failed_mass_ppv_fetcher=lambda: 3,
            relationship_stats_fetcher=lambda account_id: {
                "total_users": 12,
                "followers": 7,
                "subscribers": 5,
                "missing": 1,
            },
            delayed_counts_fetcher=lambda **kwargs: {
                "pending": 6,
                "processing": 1,
                "completed": 10,
                "failed": 2,
                "cancelled": 3,
                "expired": 4,
            },
        ).build_dashboard(
            creator_profile={"id": 7, "display_name": "Ava"},
            active_account={
                "id": 9,
                "display_name": "Ava Provider",
                "oauth_access_token": "token",
            },
        )
        summaries = dashboard.summaries

        self.assertIsInstance(dashboard, WorkspaceDashboard)
        metric_values = {
            title: {
                metric.label: metric.value
                for metric in summary.metrics
            }
            for title, summary in summaries.items()
        }

        self.assertEqual(metric_values["Assets"]["Total Assets"], "2")
        self.assertEqual(metric_values["Assets"]["Assets Processing"], "1")
        self.assertEqual(metric_values["Assets"]["Classified Assets"], "1")
        self.assertEqual(metric_values["Assets"]["Ready for Rotation"], "1")
        self.assertEqual(metric_values["Experiences"]["Total Experiences"], "3")
        self.assertEqual(metric_values["Experiences"]["Collections"], "2")
        self.assertEqual(metric_values["Experiences"]["Assets Organized"], "3")
        self.assertEqual(metric_values["Experiences"]["With Intelligence"], "2")
        self.assertEqual(metric_values["Experiences"]["Story Ready"], "1")
        self.assertEqual(metric_values["Experiences"]["Needs Review"], "1")
        self.assertEqual(
            metric_values["Experiences"]["Ready for Product Review"],
            "2",
        )
        self.assertEqual(metric_values["Experiences"]["Ready for Publishing"], "1")
        self.assertEqual(metric_values["Products"]["Total Products"], "3")
        self.assertEqual(metric_values["Products"]["Active Products"], "2")
        self.assertEqual(metric_values["Products"]["Draft Products"], "1")
        self.assertEqual(metric_values["Products"]["Disabled Products"], "0")
        self.assertEqual(metric_values["Products"]["Ready To Publish"], "1")
        self.assertEqual(metric_values["Products"]["Published Products"], "1")
        self.assertEqual(metric_values["Products"]["Products Needing Review"], "2")
        self.assertEqual(metric_values["Products"]["Not Ready"], "1")
        self.assertEqual(metric_values["Products"]["Missing Price"], "1")
        self.assertEqual(metric_values["Products"]["Missing Experience"], "1")
        self.assertEqual(metric_values["Products"]["Missing Assets"], "1")
        self.assertEqual(metric_values["Products"]["Free Products"], "1")
        self.assertEqual(metric_values["Products"]["Paid Products"], "2")
        self.assertEqual(metric_values["Publishing"]["Pending Uploads"], "6")
        self.assertEqual(metric_values["Publishing"]["Failed Uploads"], "4")
        self.assertEqual(
            metric_values["Publishing"]["Total Publishable Products"],
            "3",
        )
        self.assertEqual(metric_values["Publishing"]["Ready To Publish"], "1")
        self.assertEqual(metric_values["Publishing"]["Needs Attention"], "10")
        self.assertEqual(metric_values["Publishing"]["Published / Active"], "1")
        self.assertEqual(metric_values["Publishing"]["Missing Media Link"], "2")
        self.assertEqual(metric_values["Publishing"]["Missing Price"], "0")
        self.assertEqual(metric_values["Publishing"]["Missing Assets"], "1")
        self.assertEqual(metric_values["Publishing"]["FREE Delivery Items"], "1")
        self.assertEqual(metric_values["Publishing"]["PAID Delivery Items"], "2")
        self.assertEqual(metric_values["Publishing"]["Fanvue-ready Items"], "1")
        self.assertEqual(metric_values["Publishing"]["Telegram-ready Items"], "3")
        self.assertEqual(metric_values["Publishing"]["Wall Pending"], "4")
        self.assertEqual(metric_values["Publishing"]["Mass PPV Failed"], "3")
        self.assertEqual(metric_values["Publishing"]["Publishing Queue Count"], "5")
        self.assertEqual(metric_values["Publishing"]["Uploading Count"], "1")
        self.assertEqual(metric_values["Publishing"]["Uploaded Count"], "2")
        self.assertEqual(metric_values["Publishing"]["Waiting For Media Link"], "1")
        self.assertEqual(metric_values["Publishing"]["Failed Count"], "1")
        self.assertEqual(metric_values["Publishing"]["Retry Required Count"], "1")
        self.assertEqual(metric_values["Publishing"]["Publishing Complete"], "1")
        self.assertEqual(metric_values["Publishing"]["Product ACTIVE Count"], "2")
        self.assertEqual(metric_values["Publishing"]["Provider Summary"], "fanvue")
        self.assertEqual(
            metric_values["Customer Conversations"]["Known Customers"],
            "12",
        )
        self.assertEqual(metric_values["Customer Conversations"]["Followers"], "7")
        self.assertEqual(metric_values["Customer Conversations"]["Missing Profiles"], "1")
        self.assertEqual(metric_values["Telegram Operations"]["Active Conversations"], "12")
        self.assertEqual(metric_values["Telegram Operations"]["Active Experiences"], "1")
        self.assertEqual(metric_values["Telegram Operations"]["Current Customer Journeys"], "11")
        self.assertEqual(metric_values["Telegram Operations"]["Recent Delivery Decisions"], "3")
        self.assertEqual(metric_values["Telegram Operations"]["FREE Deliveries"], "1")
        self.assertEqual(metric_values["Telegram Operations"]["PAID Media Link Deliveries"], "2")
        self.assertEqual(metric_values["Telegram Operations"]["Commerce Memory Summaries"], "12")
        self.assertEqual(metric_values["Telegram Operations"]["Customers Needing Follow-Up"], "1")
        self.assertEqual(metric_values["Activity"]["Delayed Processing"], "1")
        self.assertEqual(metric_values["Activity"]["Delayed Failed"], "2")
        self.assertEqual(metric_values["Activity"]["Delayed Expired"], "4")
        self.assertEqual(metric_values["Notifications"]["Attention Items"], "2")
        self.assertEqual(metric_values["Notifications"]["Queue Failures"], "4")
        self.assertEqual(metric_values["Notifications"]["Provider OAuth"], "Connected")

        self.assertTrue(dashboard.activity_feed)
        self.assertEqual(
            dashboard.activity_feed[0].title,
            "Product ready for publishing: Ready Product",
        )
        self.assertEqual(dashboard.activity_feed[0].timestamp, latest)
        event_types = {event.event_type for event in dashboard.activity_feed}
        self.assertIn("asset_import", event_types)
        self.assertIn("asset_processing", event_types)
        self.assertIn("experience_created", event_types)
        self.assertIn("product_created", event_types)
        self.assertIn("product_publishing", event_types)
        self.assertIn("publishing", event_types)
        self.assertIn("customer", event_types)
        self.assertIn("delayed_message", event_types)
        self.assertIn("decision_engine", event_types)
        self.assertIn("system", event_types)
        self.assertTrue(
            any(event.future_ready for event in dashboard.activity_feed),
        )

        self.assertTrue(dashboard.notifications)
        notification_types = {
            notification.notification_type for notification in dashboard.notifications
        }
        self.assertIn("asset_classification", notification_types)
        self.assertIn("asset_processing_failure", notification_types)
        self.assertIn("product_pricing", notification_types)
        self.assertIn("product_review", notification_types)
        self.assertIn("publishing_failure", notification_types)
        self.assertIn("publishing_missing_media_link", notification_types)
        self.assertIn("queue_attention", notification_types)
        self.assertIn("customer_sync", notification_types)
        self.assertIn("delayed_message_failure", notification_types)
        self.assertIn("synchronization", notification_types)
        self.assertIn("ai_recommendation", notification_types)
        self.assertEqual(dashboard.notifications[0].severity, "critical")
        self.assertTrue(
            any(notification.action_required for notification in dashboard.notifications),
        )
        self.assertTrue(
            any(notification.future_ready for notification in dashboard.notifications),
        )

        self.assertTrue(dashboard.publishing_queue)
        queue_types = {item.queue_type for item in dashboard.publishing_queue}
        self.assertIn("publishing_failures", queue_types)
        self.assertIn("queue_attention", queue_types)
        self.assertIn("wall_publishing", queue_types)
        self.assertIn("mass_ppv_publishing", queue_types)
        self.assertIn("completed_publishing", queue_types)
        self.assertIn("vault_publishing", queue_types)
        self.assertIn("waiting_media_links", queue_types)
        self.assertIn("publishing_retry_required", queue_types)
        self.assertIn("publishing_complete", queue_types)
        self.assertEqual(dashboard.publishing_queue[0].status, "Failed")
        self.assertTrue(any(item.action_required for item in dashboard.publishing_queue))
        self.assertTrue(any(item.future_ready for item in dashboard.publishing_queue))
        self.assertTrue(dashboard.telegram_operations)
        telegram_operation_types = {
            item.operation_type for item in dashboard.telegram_operations
        }
        self.assertIn("active_conversations", telegram_operation_types)
        self.assertIn("current_experiences", telegram_operation_types)
        self.assertIn("delivery_decisions", telegram_operation_types)
        self.assertIn("commerce_memory", telegram_operation_types)
        self.assertIn("recent_free_deliveries", telegram_operation_types)
        self.assertIn("recent_paid_offers", telegram_operation_types)
        self.assertIn("customers_needing_followup", telegram_operation_types)
        self.assertTrue(
            any(item.target == "Customer Workspace" for item in dashboard.telegram_operations)
        )
        self.assertTrue(any(item.action_required for item in dashboard.telegram_operations))

        self.assertTrue(dashboard.insights)
        insight_types = {insight.insight_type for insight in dashboard.insights}
        self.assertIn("asset_growth", insight_types)
        self.assertIn("import_trend", insight_types)
        self.assertIn("experience_growth", insight_types)
        self.assertIn("product_growth", insight_types)
        self.assertIn("dashboard_readiness", insight_types)
        self.assertIn("customer_growth", insight_types)
        self.assertIn("publishing_health", insight_types)
        self.assertIn("publishing_trend", insight_types)
        self.assertIn("workspace_health", insight_types)
        self.assertIn("customer_engagement", insight_types)
        self.assertIn("recommendation_trend", insight_types)
        publishing_health = next(
            insight
            for insight in dashboard.insights
            if insight.insight_type == "publishing_health"
        )
        self.assertEqual(publishing_health.current_value, "Attention")
        self.assertEqual(publishing_health.trend, "Needs Attention")
        self.assertTrue(any(insight.future_ready for insight in dashboard.insights))

        self.assertTrue(dashboard.experience_cards)
        self.assertEqual(dashboard.experience_cards[0].title, "Solo")
        self.assertEqual(dashboard.experience_cards[0].experience_type, "STANDALONE")
        self.assertEqual(dashboard.experience_cards[0].product_count, 1)
        self.assertEqual(dashboard.experience_cards[0].delivery_types, ("PAID",))
        self.assertEqual(
            dashboard.experience_cards[0].themes,
            ("relationship-theme",),
        )
        self.assertEqual(
            dashboard.experience_cards[0].keywords,
            ("relationship-keyword",),
        )
        self.assertEqual(dashboard.experience_cards[0].mood, "warm")
        self.assertEqual(
            dashboard.experience_cards[0].publishing_readiness.status,
            "ready",
        )
        self.assertEqual(
            dashboard.experience_cards[0].relationship_source,
            "experience_read_model",
        )
        self.assertEqual(
            experience_service.relationship_calls[:3],
            [
                "experience-solo",
                "experience-set",
                "experience-missing-cover",
            ],
        )
        self.assertEqual(product_catalog.count_calls, [7])
        self.assertTrue(product_catalog.display_calls)
        self.assertTrue(dashboard.product_cards)
        self.assertEqual(dashboard.product_cards[0].name, "Ready Product")
        self.assertEqual(dashboard.product_cards[0].product_type, "PHOTO_SET")
        self.assertEqual(dashboard.product_cards[0].delivery_type, "PAID")
        self.assertEqual(dashboard.product_cards[0].experience_name, "Set")
        self.assertEqual(dashboard.product_cards[0].experience_type, "PHOTOSHOOT")
        self.assertEqual(dashboard.product_cards[0].status, "ACTIVE")
        self.assertEqual(dashboard.product_cards[0].review_status, "Ready")
        self.assertEqual(dashboard.product_cards[0].publishing_readiness, "READY")
        self.assertEqual(dashboard.product_cards[0].provider_status, "Uploaded to Fanvue")
        self.assertEqual(
            dashboard.product_cards[0].telegram_delivery_status,
            "PAID delivery intent",
        )
        self.assertEqual(dashboard.product_cards[0].price, "USD 19.99")
        self.assertEqual(dashboard.product_cards[0].suggested_price, "USD 24.99")
        self.assertEqual(dashboard.product_cards[0].asset_count, 2)
        self.assertEqual(
            dashboard.product_cards[0].experience_relationship,
            "experience_read_model",
        )
        self.assertFalse(dashboard.product_cards[0].compatibility)
        self.assertEqual(dashboard.product_cards[1].review_status, "Needs Assets")
        self.assertTrue(dashboard.product_cards[2].compatibility)
        self.assertTrue(dashboard.publishing_cards)
        self.assertEqual(dashboard.publishing_cards[0].product_name, "Ready Product")
        self.assertEqual(dashboard.publishing_cards[0].experience_name, "Set")
        self.assertEqual(dashboard.publishing_cards[0].product_type, "PHOTO_SET")
        self.assertEqual(dashboard.publishing_cards[0].delivery_type, "PAID")
        self.assertEqual(
            dashboard.publishing_cards[0].publishing_status,
            "Uploaded to Fanvue",
        )
        self.assertEqual(dashboard.publishing_cards[0].publishing_readiness, "READY")
        self.assertEqual(dashboard.publishing_cards[0].media_link_status, "Available")
        self.assertEqual(
            dashboard.publishing_cards[0].telegram_delivery_intent,
            "PAID delivery intent",
        )
        self.assertTrue(dashboard.publishing_cards[0].ready_to_publish)
        self.assertTrue(dashboard.publishing_cards[0].published_active)
        self.assertEqual(dashboard.publishing_cards[0].missing_requirements, ())
        self.assertIn("Media Link", dashboard.publishing_cards[1].missing_requirements)
        self.assertIn("Assets", dashboard.publishing_cards[1].missing_requirements)
        self.assertIn(
            "Provider Status",
            dashboard.publishing_cards[2].missing_requirements,
        )
        self.assertEqual(
            publishing_service.projected_products,
            ["product-ready", "product-review", "product-draft"],
        )
        self.assertTrue(dashboard.workflow_items)
        self.assertEqual(dashboard.workflow_items[0].product_name, "Ready Product")
        self.assertEqual(
            dashboard.workflow_items[0].workflow_snapshot.product_id,
            "product-ready",
        )
        self.assertEqual(
            dashboard.workflow_items[0].current_workflow_stage,
            "TELEGRAM_READY",
        )
        self.assertEqual(
            dashboard.workflow_items[0].current_lifecycle_stage,
            "ACTIVE",
        )
        self.assertEqual(
            dashboard.workflow_items[0].publishing_status.state.value,
            "PUBLISHING_COMPLETE",
        )
        self.assertTrue(dashboard.workflow_items[0].attention_summary.recommended_action)
        self.assertTrue(
            any(
                item.attention_summary.attention_required
                for item in dashboard.workflow_items
            )
        )
        self.assertIsNotNone(dashboard.creator_review)
        self.assertEqual(dashboard.creator_review.total_pending, 6)
        self.assertEqual(dashboard.creator_review.assets_awaiting_review, 3)
        self.assertEqual(dashboard.creator_review.products_awaiting_review, 1)
        self.assertEqual(dashboard.creator_review.high_priority_reviews, 3)
        self.assertEqual(dashboard.creator_review.items[0].target, "Asset Library")
        self.assertEqual(len(creator_review.calls), 1)
        self.assertIs(creator_review.calls[0]["asset_summary"], summaries["Assets"])
        self.assertEqual(
            creator_review.calls[0]["experience_cards"],
            dashboard.experience_cards,
        )
        self.assertEqual(
            creator_review.calls[0]["product_cards"],
            dashboard.product_cards,
        )
        self.assertEqual(
            creator_review.calls[0]["publishing_cards"],
            dashboard.publishing_cards,
        )
        self.assertTrue(dashboard.recommended_actions)
        action_titles = {action.title for action in dashboard.recommended_actions}
        self.assertIn("Add missing media links", action_titles)
        self.assertIn("Attach missing Product Assets", action_titles)
        self.assertIn("Review ready-to-publish Products", action_titles)
        self.assertIn("Review Waiting For Media Links", action_titles)
        self.assertIn("Review Failed Uploads", action_titles)
        self.assertIn("Review Retry Required", action_titles)
        self.assertIn("Review Publishing Complete", action_titles)
        self.assertIn("Review unclassified Assets", action_titles)
        self.assertTrue(
            any(action.target == "Product Catalog" for action in dashboard.recommended_actions)
        )
        self.assertTrue(
            any(action.target == "Publishing Queue" for action in dashboard.recommended_actions)
        )

    def test_workspace_summaries_gracefully_placeholder_without_scope(self):
        dashboard = CreatorWorkspaceService(
            asset_repository=type(
                "FakeAssets",
                (),
                {"list_all": lambda self: []},
            )(),
        ).build_dashboard(
            creator_profile={},
            active_account={},
        )
        summaries = dashboard.summaries

        self.assertEqual(
            summaries["Experiences"].metrics[0].value,
            "Unavailable",
        )
        self.assertEqual(
            summaries["Products"].metrics[0].value,
            "Unavailable",
        )
        self.assertEqual(
            summaries["Publishing"].metrics[0].value,
            "Unavailable",
        )
        self.assertEqual(
            summaries["Notifications"].metrics[0].value,
            "Missing",
        )

    def test_workspace_consumes_asset_library_presentation_boundary(self):
        class ForbiddenAssetRepository:
            def list_all(self):
                raise AssertionError("Workspace must use AssetLibraryService")

        class FakeAssetLibraryService:
            def __init__(self):
                self.filters = []

            def search_assets(self, filters):
                self.filters.append(filters)
                return SimpleNamespace(
                    items=(
                        SimpleNamespace(
                            asset_id=1,
                            file_name="asset.jpg",
                            created_at=None,
                            status="approved",
                            is_active=True,
                            classification="VIP",
                            ready_for_rotation=True,
                            preview_path="preview.jpg",
                        ),
                    )
                )

        assets = FakeAssetLibraryService()
        dashboard = CreatorWorkspaceService(
            asset_repository=ForbiddenAssetRepository(),
            asset_library_service=assets,
        ).build_dashboard(creator_profile={}, active_account={})

        self.assertEqual(
            dashboard.summaries["Assets"].metrics[0].value,
            "1",
        )
        self.assertTrue(assets.filters)
        self.assertFalse(assets.filters[0].eligible_only)

    def test_workspace_page_uses_dashboard_service_not_repositories(self):
        source = Path("app/dashboard/pages/creator_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("CreatorWorkspaceService", source)
        self.assertIn("dashboard.notifications", source)
        self.assertIn("dashboard.insights", source)
        self.assertIn("dashboard.recommended_actions", source)
        self.assertIn("dashboard.creator_review", source)
        self.assertIn("dashboard.workflow_items", source)
        self.assertIn("dashboard.experience_cards", source)
        self.assertIn("dashboard.product_cards", source)
        self.assertIn("dashboard.publishing_cards", source)
        self.assertIn("dashboard.publishing_queue", source)
        self.assertIn("dashboard.telegram_operations", source)
        self.assertIn("_render_dashboard_snapshot", source)
        self.assertIn("_render_creator_workflow", source)
        self.assertIn("_render_recommended_actions", source)
        self.assertIn("_render_publishing_operations", source)
        self.assertIn("_render_telegram_operations", source)
        self.assertIn("_render_creator_review", source)
        self.assertIn("_render_recent_activity", source)
        self.assertIn("_render_experience_cards", source)
        self.assertIn("_render_product_cards", source)
        self.assertIn("_render_product_business", source)
        self.assertIn("_render_publishing_cards", source)
        self.assertIn("_render_executive_cards", source)
        self.assertIn("_render_business_health", source)
        self.assertIn("_render_daily_business_briefing", source)
        self.assertIn("_daily_business_snapshot", source)
        self.assertIn("_daily_business_status", source)
        self.assertIn("_render_todays_priorities", source)
        self.assertIn("_render_creator_attention", source)
        self.assertIn("_creator_attention_items", source)
        self.assertIn("_attention_priority_sort_key", source)
        self.assertIn("_render_opportunities", source)
        self.assertIn("_render_quick_navigation", source)
        self.assertIn("Creator HQ", source)
        self.assertIn("### Creator Agent", source)
        self.assertIn("### Daily Business Briefing", source)
        self.assertIn("Good morning.", source)
        self.assertIn("Good afternoon.", source)
        self.assertIn("Good evening.", source)
        self.assertIn("Today's Highest Priorities", source)
        self.assertIn("What Changed Recently", source)
        self.assertIn("Future Revenue", source)
        self.assertIn("Available when Fanvue attribution is enabled.", source)
        self.assertIn("Ask Creator Agent about today's briefing", source)
        self.assertIn("### Business Health", source)
        self.assertIn("### Today's Priorities", source)
        self.assertIn("### Creator Attention", source)
        self.assertIn("Publishing", source)
        self.assertIn("Products", source)
        self.assertIn("Customers", source)
        self.assertIn("Telegram", source)
        self.assertIn("AI Review", source)
        self.assertIn("Business Risks", source)
        self.assertIn("Everything important is operating normally.", source)
        self.assertIn("Ask Creator Agent why these items need attention", source)
        self.assertIn("### Opportunities", source)
        self.assertIn("### Quick Navigation", source)
        self.assertIn("### Operational Dashboards", source)
        self.assertIn("### Business Overview", source)
        self.assertIn("_render_creator_agent_entry", source)
        self.assertIn("### Operational Snapshot", source)
        self.assertIn("### Creator Workflow", source)
        self.assertIn("### Recommended Actions", source)
        self.assertIn("### Publishing Operations", source)
        self.assertIn("### Telegram Operations", source)
        self.assertIn("### Business Learning", source)
        render_source = source[source.index("def render_creator_workspace") :]
        self.assertLess(
            render_source.index("### Creator Agent"),
            render_source.index("### Daily Business Briefing"),
        )
        self.assertLess(
            render_source.index("### Daily Business Briefing"),
            render_source.index("### Business Health"),
        )
        self.assertLess(
            render_source.index("### Business Health"),
            render_source.index("### Today's Priorities"),
        )
        self.assertLess(
            render_source.index("### Today's Priorities"),
            render_source.index("### Creator Attention"),
        )
        self.assertLess(
            render_source.index("### Creator Attention"),
            render_source.index("### Opportunities"),
        )
        self.assertLess(
            render_source.index("### Opportunities"),
            render_source.index("### Operational Dashboards"),
        )
        self.assertIn("Open Customer Workspace", source)
        self.assertIn("Review Active Conversations", source)
        self.assertIn("Review Customers Needing Follow-Up", source)
        self.assertIn("Review Recent Paid Offers", source)
        self.assertIn("Review Current Experiences", source)
        self.assertIn("Open Publishing Queue", source)
        self.assertIn("Review Waiting For Media Links", source)
        self.assertIn("Review Failed Uploads", source)
        self.assertIn("Review Retry Required", source)
        self.assertIn("Review Publishing Complete", source)
        self.assertIn("### Creator Review", source)
        self.assertIn("### Experience Overview", source)
        self.assertIn("### Product Overview", source)
        self.assertIn("### Product Business", source)
        self.assertIn("### Publishing Overview", source)
        self.assertIn("### Recent Activity", source)
        self.assertIn("### Needs Attention", source)
        self.assertIn("### HQ Insights", source)
        self.assertNotIn("### Activity Feed", source)
        self.assertNotIn("WorkspaceActivityEvent", source)
        self.assertNotIn("def _render_activity_feed", source)
        self.assertNotIn("_render_publishing_queue", source)
        self.assertNotIn("_render_summary_panel", source)
        self.assertNotIn("AssetRepository", source)
        self.assertNotIn("ProductRepository", source)
        self.assertNotIn("fetch_wall_queue_counts", source)

    def test_daily_business_briefing_reuses_workspace_dashboard_data(self):
        dashboard = WorkspaceDashboard(
            summaries={
                "Products": WorkspaceSummary(
                    title="Products",
                    metrics=(
                        WorkspaceMetric("Active Products", "4"),
                        WorkspaceMetric("Products Needing Review", "0"),
                    ),
                ),
                "Publishing": WorkspaceSummary(
                    title="Publishing",
                    metrics=(
                        WorkspaceMetric("Ready To Publish", "2"),
                        WorkspaceMetric("Publishing Queue Count", "3"),
                        WorkspaceMetric("Waiting For Media Link", "1"),
                        WorkspaceMetric("Missing Media Link", "0"),
                        WorkspaceMetric("Failed Count", "0"),
                        WorkspaceMetric("Retry Required Count", "0"),
                    ),
                ),
                "Customer Business": WorkspaceSummary(
                    title="Customer Business",
                    metrics=(
                        WorkspaceMetric("At-risk Customers", "0"),
                        WorkspaceMetric("VIP Customers", "1"),
                        WorkspaceMetric("Retention Opportunities", "0"),
                    ),
                ),
                "Telegram Operations": WorkspaceSummary(
                    title="Telegram Operations",
                    metrics=(
                        WorkspaceMetric("Active Conversations", "5"),
                        WorkspaceMetric("Customers Needing Follow-Up", "0"),
                        WorkspaceMetric("VIP Opportunities", "0"),
                    ),
                ),
                "Business Optimization": WorkspaceSummary(
                    title="Business Optimization",
                    metrics=(
                        WorkspaceMetric("Overall Business Health", "HEALTHY"),
                        WorkspaceMetric("Publishing Readiness", "ready"),
                        WorkspaceMetric("Critical Recommendations", "0"),
                    ),
                ),
            }
        )

        self.assertIn("Business operating normally", _daily_business_status(dashboard))
        snapshot = dict(_daily_business_snapshot(dashboard))
        self.assertEqual(snapshot["Products Ready"], "2")
        self.assertEqual(snapshot["Publishing Queue"], "3")
        self.assertEqual(snapshot["Active Telegram Operations"], "5")
        self.assertEqual(snapshot["Business Health"], "HEALTHY")

    def test_daily_business_greeting_is_contextual(self):
        morning = _business_greeting(datetime(2026, 7, 6, 9, 0))
        afternoon = _business_greeting(datetime(2026, 7, 6, 14, 0))
        evening = _business_greeting(datetime(2026, 7, 6, 20, 0))

        self.assertIn("Good morning.", morning)
        self.assertIn("Monday, July 06, 2026", morning)
        self.assertIn("Good afternoon.", afternoon)
        self.assertIn("Good evening.", evening)

    def test_creator_attention_items_group_existing_dashboard_data(self):
        dashboard = WorkspaceDashboard(
            summaries={
                "Publishing": WorkspaceSummary(
                    title="Publishing",
                    metrics=(
                        WorkspaceMetric("Missing Media Link", "2"),
                        WorkspaceMetric("Failed Count", "1"),
                        WorkspaceMetric("Retry Required Count", "1"),
                    ),
                ),
                "Products": WorkspaceSummary(
                    title="Products",
                    metrics=(WorkspaceMetric("Products Needing Review", "3"),),
                ),
                "Customer Business": WorkspaceSummary(
                    title="Customer Business",
                    metrics=(
                        WorkspaceMetric("At-risk Customers", "1"),
                        WorkspaceMetric("Retention Opportunities", "2"),
                    ),
                ),
                "Telegram Operations": WorkspaceSummary(
                    title="Telegram Operations",
                    metrics=(
                        WorkspaceMetric("Customers Needing Follow-Up", "1"),
                        WorkspaceMetric("VIP Opportunities", "1"),
                    ),
                ),
                "Business Optimization": WorkspaceSummary(
                    title="Business Optimization",
                    metrics=(WorkspaceMetric("Critical Recommendations", "1"),),
                ),
            }
        )

        items = _creator_attention_items(dashboard)
        categories = {item["category"] for item in items}

        self.assertIn("Publishing", categories)
        self.assertIn("Products", categories)
        self.assertIn("Customers", categories)
        self.assertIn("Telegram", categories)
        self.assertIn("Business Risks", categories)
        self.assertTrue(any(item["target"] == "Creator Agent" or item["target"] == "Publishing Queue" for item in items))

    def test_creator_attention_items_empty_state_has_no_items(self):
        empty_summary = lambda title: WorkspaceSummary(
            title=title,
            metrics=(
                WorkspaceMetric("Missing Media Link", "0"),
                WorkspaceMetric("Failed Count", "0"),
                WorkspaceMetric("Retry Required Count", "0"),
                WorkspaceMetric("Products Needing Review", "0"),
                WorkspaceMetric("At-risk Customers", "0"),
                WorkspaceMetric("Retention Opportunities", "0"),
                WorkspaceMetric("Customers Needing Follow-Up", "0"),
                WorkspaceMetric("VIP Opportunities", "0"),
                WorkspaceMetric("Critical Recommendations", "0"),
            ),
        )
        dashboard = WorkspaceDashboard(
            summaries={
                "Publishing": empty_summary("Publishing"),
                "Products": empty_summary("Products"),
                "Customer Business": empty_summary("Customer Business"),
                "Telegram Operations": empty_summary("Telegram Operations"),
                "Business Optimization": empty_summary("Business Optimization"),
            }
        )

        self.assertEqual(_creator_attention_items(dashboard), ())

    def test_activity_feed_page_uses_workspace_service(self):
        source = Path("app/dashboard/pages/activity_feed.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("CreatorWorkspaceService", source)
        self.assertIn("dashboard.activity_feed", source)
        self.assertIn("_render_activity_feed", source)
        self.assertNotIn("AssetRepository", source)
        self.assertNotIn("ProductRepository", source)
        self.assertNotIn("fetch_wall_queue_counts", source)


if __name__ == "__main__":
    unittest.main()
