import unittest
from pathlib import Path

from app.dashboard.navigation import (
    DASHBOARD_NAVIGATION_GROUPS,
    DASHBOARD_PAGE_OPTIONS,
    grouped_navigation_label_for_page,
    page_for_grouped_navigation_label,
)
from app.dashboard.pages.customer_workspace import (
    CUSTOMER_WORKSPACE_REGIONS,
    build_customer_lookup,
)


class CustomerWorkspaceTests(unittest.TestCase):
    def test_customer_workspace_route_exists(self):
        self.assertIn("Customer Workspace", DASHBOARD_PAGE_OPTIONS)
        self.assertEqual(
            page_for_grouped_navigation_label(
                grouped_navigation_label_for_page("Customer Workspace")
            ),
            "Customer Workspace",
        )

    def test_navigation_includes_customer_workspace(self):
        customer_group = next(
            group for group in DASHBOARD_NAVIGATION_GROUPS
            if group.label == "Customer Conversations"
        )
        labels = [item.label for item in customer_group.items]
        pages = [item.page for item in customer_group.items]

        self.assertEqual(labels[0], "Customer Workspace")
        self.assertIn("Chat Console", labels)
        self.assertIn("Relationship Sync", labels)
        self.assertIn("Customer Workspace", pages)

    def test_dashboard_router_imports_and_routes_customer_workspace(self):
        source = Path("app/dashboard/main.py").read_text(encoding="utf-8")

        self.assertIn("render_customer_workspace", source)
        self.assertIn('== "Customer Workspace"', source)

    def test_workspace_customer_card_targets_customer_workspace(self):
        source = Path("app/dashboard/pages/creator_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('primary_target="Customer Workspace"', source)
        self.assertIn('("Chat Console", "Chat Console")', source)
        self.assertIn('("Relationships", "Relationship Sync")', source)

    def test_page_uses_customer_service_not_repositories(self):
        source = Path("app/dashboard/pages/customer_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("CustomerService", source)
        self.assertIn("get_customer_summary", source)
        self.assertIn("get_customer_timeline", source)
        self.assertIn("get_customer_decision_inspector", source)
        self.assertIn("get_customer_commerce_summary", source)
        self.assertIn("get_customer_experience_progression_summary", source)
        self.assertNotIn("CustomerRepository", source)
        self.assertNotIn("MemoryRepository", source)
        self.assertNotIn("TelegramIdentityRepository", source)
        self.assertNotIn("DecisionEngine(", source)
        self.assertNotIn("get_user_memory_row", source)
        self.assertNotIn("get_thread_messages_for_user", source)
        self.assertNotIn("get_owned_content_tags", source)

    def test_search_controls_convert_to_customer_service_lookup(self):
        lookup = build_customer_lookup(
            search_text="  7:42  ",
            provider="internal",
            provider_customer_id=None,
            provider_account_id=None,
        )

        self.assertEqual(lookup, {"customer_id": "7:42"})

        lookup = build_customer_lookup(
            search_text="provider-user-42",
            provider="fanvue",
            provider_customer_id="",
            provider_account_id="7",
        )

        self.assertEqual(
            lookup,
            {
                "provider": "fanvue",
                "provider_customer_id": "provider-user-42",
                "provider_account_id": "7",
            },
        )

    def test_placeholder_regions_are_defined_for_future_widgets(self):
        self.assertEqual(
            CUSTOMER_WORKSPACE_REGIONS,
            (
                "Timeline",
                "DecisionEngine Inspector",
                "Commerce",
                "Experience Progression",
            ),
        )

    def test_timeline_region_is_populated_before_future_placeholders(self):
        source = Path("app/dashboard/pages/customer_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("def _render_timeline", source)
        self.assertIn("_render_timeline(timeline_events)", source)
        self.assertIn('"Timeline", "DecisionEngine Inspector"', source)
        self.assertIn("DecisionEngine Inspector", source)

    def test_decision_engine_inspector_region_is_populated(self):
        source = Path("app/dashboard/pages/customer_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("def _render_decision_inspector", source)
        self.assertIn("_render_decision_inspector(decision_inspector)", source)
        self.assertIn("Recommendation Context", source)
        self.assertIn("Future Decision Data", source)
        self.assertIn('"DecisionEngine Inspector"', source)

    def test_commerce_region_is_populated(self):
        source = Path("app/dashboard/pages/customer_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("def _render_customer_commerce", source)
        self.assertIn("_render_customer_commerce(commerce_summary)", source)
        self.assertIn("Owned Commerce", source)
        self.assertIn("Telegram Conversation State", source)
        self.assertIn("telegram_conversation_state", source)
        self.assertIn("Delivery Decision", source)
        self.assertIn("delivery_decision", source)
        self.assertIn("Current delivery decision", source)
        self.assertIn("FREE vs PAID", source)
        self.assertIn("Last delivery", source)
        self.assertIn("Last FREE asset", source)
        self.assertIn("Last PAID media link", source)
        self.assertIn("Blocking reason", source)
        self.assertIn("Next suggested action", source)
        self.assertIn("Commerce Memory", source)
        self.assertIn("Purchased products", source)
        self.assertIn("FREE assets delivered", source)
        self.assertIn("PAID media links delivered", source)
        self.assertIn("Current commerce journey", source)
        self.assertIn("Recommended next commerce action", source)
        self.assertIn("Current experience", source)
        self.assertIn("Commerce progress", source)
        self.assertIn("Future Commerce Data", source)
        self.assertIn('"Commerce"', source)

    def test_experience_progression_region_is_populated(self):
        source = Path("app/dashboard/pages/customer_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("def _render_experience_progression", source)
        self.assertIn("_render_experience_progression(experience_progression)", source)
        self.assertIn("Current Experience", source)
        self.assertIn("Last Progression Event", source)
        self.assertIn("progress_percentage", source)
        self.assertIn("next_recommended_experience_action", source)
        self.assertIn('"Experience Progression"', source)


if __name__ == "__main__":
    unittest.main()
