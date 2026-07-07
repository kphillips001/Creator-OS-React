"""Creator HQ landing page.

This page is presentation and navigation orchestration; existing pages and
services continue owning their workflows and business logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import streamlit as st

from app.models.workspace_dashboard import (
    WorkspaceBusinessOptimizationCard,
    WorkspaceContentOpportunityCard,
    WorkspaceCustomerBusinessCard,
    WorkspaceExperienceCard,
    WorkspaceInsight,
    WorkspaceNotification,
    WorkspaceProductBusinessCard,
    WorkspaceProductCard,
    WorkspacePublishingCard,
    WorkspacePublishingQueueItem,
    WorkspaceRecommendedAction,
    WorkspaceSummary,
    WorkspaceTelegramBusinessCard,
    WorkspaceTelegramOperationItem,
    WorkspaceWorkflowItem,
)
from app.models.product_review import ProductReviewSummary
from app.services.creator_workspace_service import CreatorWorkspaceService
from app.services.runtime_control_service import RuntimeControlService


@dataclass(frozen=True)
class WorkspaceSection:
    title: str
    marker: str
    description: str
    primary_target: str | None = None
    secondary_targets: tuple[tuple[str, str], ...] = ()


WORKSPACE_SECTIONS = (
    WorkspaceSection(
        title="AI",
        marker="AI",
        description="Ask Creator Agent about priorities, Products, customers, and business health.",
        primary_target="Creator Agent",
    ),
    WorkspaceSection(
        title="Assets",
        marker="A",
        description="Import, classify, process, and review media assets.",
        primary_target="Asset Library",
        secondary_targets=(("Ingestion", "CMS Upload"),),
    ),
    WorkspaceSection(
        title="Experiences",
        marker="E",
        description="Organize assets into photoshoots, stories, and sequences.",
        primary_target=None,
    ),
    WorkspaceSection(
        title="Products",
        marker="P",
        description="Manage commerce catalog, pricing, availability, and offers.",
        primary_target="Product Catalog",
        secondary_targets=(("Pricing Tool", "Pricing Playground"),),
    ),
    WorkspaceSection(
        title="Publishing",
        marker="U",
        description="Monitor scheduled publishing, campaigns, and provider status.",
        primary_target="Publishing Queue",
        secondary_targets=(
            ("Wall Scheduler", "Wall Scheduler"),
            ("Campaigns", "Mass PPV Dashboard"),
        ),
    ),
    WorkspaceSection(
        title="Customer Conversations",
        marker="C",
        description="Review conversations, simulator behavior, and relationship state.",
        primary_target="Customer Workspace",
        secondary_targets=(
            ("Chat Console", "Chat Console"),
            ("Relationships", "Relationship Sync"),
        ),
    ),
    WorkspaceSection(
        title="Activity",
        marker="L",
        description="Track queues, followups, recent changes, and operational history.",
        primary_target="Delayed Messages",
    ),
    WorkspaceSection(
        title="Notifications",
        marker="N",
        description="See warnings, errors, processing status, and follow-up actions.",
        primary_target=None,
    ),
    WorkspaceSection(
        title="Administration",
        marker="S",
        description="Configure creator profile, safety controls, modules, and providers.",
        primary_target="Creator Profile",
        secondary_targets=(
            ("System", "System Overview"),
            ("Modules", "Module Switches"),
            ("Provider Connections", "Fanvue Auth"),
        ),
    ),
)


def _navigate(target: str) -> None:
    st.session_state["dashboard_page"] = target
    st.rerun()


def _creator_display_name(creator_profile: dict | None) -> str:
    profile = creator_profile or {}
    return (
        profile.get("display_name")
        or profile.get("persona_name")
        or profile.get("name")
        or "Creator"
    )


def _metric_value(summary: WorkspaceSummary, label: str, default: str = "-") -> str:
    return next(
        (
            metric.value
            for metric in summary.metrics
            if metric.label == label
        ),
        default,
    )


def _executive_card_data(
    dashboard,
) -> tuple[dict[str, str], ...]:
    assets = dashboard.summary("Assets")
    products = dashboard.summary("Products")
    publishing = dashboard.summary("Publishing")
    customers = dashboard.summary("Customer Conversations")

    return (
        {
            "title": "Assets",
            "primary_label": "Total Assets",
            "primary_value": _metric_value(assets, "Total Assets"),
            "status": f"Alerts: {_metric_value(assets, 'Asset Alerts')}",
            "target": "Asset Library",
            "action": "Open Asset Library",
        },
        {
            "title": "Products",
            "primary_label": "Active Products",
            "primary_value": _metric_value(products, "Active Products"),
            "status": f"Ready: {_metric_value(products, 'Ready for Publishing')}",
            "target": "Product Catalog",
            "action": "Open Catalog",
        },
        {
            "title": "Publishing",
            "primary_label": "Pending Uploads",
            "primary_value": _metric_value(publishing, "Pending Uploads"),
            "status": f"Health: {_metric_value(publishing, 'Publishing Health')}",
            "target": "Publishing Queue",
            "action": "Open Queue",
        },
        {
            "title": "Customers",
            "primary_label": "Known Customers",
            "primary_value": _metric_value(customers, "Known Customers"),
            "status": f"Missing profiles: {_metric_value(customers, 'Missing Profiles')}",
            "target": "Customer Workspace",
            "action": "Open Customers",
        },
    )


def _render_executive_card(card: dict[str, str]) -> None:
    with st.container():
        st.subheader(card["title"])
        st.metric(card["primary_label"], card["primary_value"])
        st.caption(card["status"])
        if st.button(
            card["action"],
            key=f"workspace_exec_{card['target']}",
            use_container_width=True,
        ):
            _navigate(card["target"])


def _render_executive_cards(dashboard) -> None:
    columns = st.columns(4)
    for column, card in zip(columns, _executive_card_data(dashboard)):
        with column:
            _render_executive_card(card)


def _creator_agent_history(active_account: dict | None) -> list[dict]:
    account_id = (active_account or {}).get("id") or "default"
    key = f"creator_agent_history_{account_id}"
    return list(st.session_state.get(key, []))


def _render_creator_agent_entry(active_account: dict | None = None) -> None:
    with st.container():
        st.subheader("Creator Agent")
        st.caption(
            "Your natural-language business assistant for priorities, Products, "
            "customers, publishing, Telegram, and business health."
        )
        recent_history = _creator_agent_history(active_account)
        if recent_history:
            recent = recent_history[-1]
            st.caption(
                "Recent conversation: "
                + str(recent.get("content") or "Conversation available.")
            )
        prompt = st.text_input(
            "Ask Creator Agent...",
            placeholder="What should I work on today?",
            key="creator_hq_agent_prompt",
        )
        suggested = (
            "What should I work on today?",
            "Show Business Health.",
            "Which Products need Media Links?",
        )
        columns = st.columns(4)
        if columns[0].button(
            "Open Chat",
            key="creator_hq_open_creator_agent",
            use_container_width=True,
        ):
            _navigate("Creator Agent")
        for index, question in enumerate(suggested, start=1):
            if columns[index].button(
                question,
                key=f"creator_hq_agent_suggestion_{index}",
                use_container_width=True,
            ):
                st.session_state["creator_agent_prefill_question"] = question
                _navigate("Creator Agent")
        if prompt and st.button(
            "Ask Creator Agent",
            key="creator_hq_ask_creator_agent",
            use_container_width=True,
        ):
            st.session_state["creator_agent_prefill_question"] = prompt
            _navigate("Creator Agent")


def _render_business_health(dashboard) -> None:
    optimization = dashboard.summary("Business Optimization")
    rows = (
        ("Overall Business Health", _metric_value(optimization, "Overall Business Health")),
        ("Publishing Health", _metric_value(optimization, "Publishing Readiness")),
        ("Product Health", _metric_value(optimization, "Product Health")),
        ("Customer Health", _metric_value(optimization, "Customer Health")),
        ("Telegram Health", _metric_value(optimization, "Telegram Health")),
        (
            "AI Confidence",
            "Source-backed" if dashboard.business_optimization_card else "Unavailable",
        ),
        (
            "Operational Status",
            _metric_value(
                optimization,
                "Next Recommended Business Action",
                "Everything operating normally",
            ),
        ),
    )
    for row in range(0, len(rows), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, rows[row : row + 4]):
            column.metric(label, value)


def _business_greeting(now: datetime | None = None) -> str:
    current = now or datetime.now()
    if current.hour < 12:
        greeting = "Good morning."
    elif current.hour < 18:
        greeting = "Good afternoon."
    else:
        greeting = "Good evening."
    return f"{greeting} {current.strftime('%A, %B %d, %Y')}"


def _render_daily_business_briefing(dashboard) -> None:
    st.subheader(_business_greeting())
    st.caption(_daily_business_status(dashboard))

    snapshot_rows = _daily_business_snapshot(dashboard)
    columns = st.columns(4)
    for index, (label, value) in enumerate(snapshot_rows):
        columns[index % 4].metric(label, value)

    st.markdown("#### Today's Highest Priorities")
    actions = tuple(dashboard.recommended_actions[:3])
    if actions:
        for index, action in enumerate(actions, start=1):
            st.write(f"{index}. {action.title}")
            st.caption(
                " | ".join(
                    (
                        f"Priority: {action.priority}",
                        f"Source: {action.source}",
                        action.detail or "Review recommended.",
                    )
                )
            )
    else:
        st.success("No urgent priorities are visible.")

    st.markdown("#### What Changed Recently")
    if dashboard.insights:
        for insight in dashboard.insights[:3]:
            st.caption(
                " | ".join(
                    (
                        insight.category,
                        insight.trend,
                        insight.detail,
                    )
                )
            )
    else:
        st.caption("Recent change signals are not available yet.")

    st.markdown("#### Opportunities")
    for label, value in _daily_business_opportunities(dashboard):
        st.caption(f"{label}: {value}")

    st.markdown("#### Future Revenue")
    revenue_columns = st.columns(4)
    for column, label in zip(
        revenue_columns,
        ("Revenue Today", "Revenue This Week", "Top Product", "Top Customer"),
    ):
        column.metric(label, "Available when Fanvue attribution is enabled.")

    if st.button(
        "Ask Creator Agent about today's briefing",
        key="creator_hq_briefing_ask_creator_agent",
        use_container_width=True,
    ):
        st.session_state["creator_agent_prefill_question"] = (
            "Explain today's Daily Business Briefing."
        )
        _navigate("Creator Agent")


def _daily_business_status(dashboard) -> str:
    attention_count = len(_creator_attention_items(dashboard))
    optimization = dashboard.summary("Business Optimization")
    health = _metric_value(optimization, "Overall Business Health", "UNKNOWN")
    publishing = _metric_value(optimization, "Publishing Readiness", "unknown")
    if attention_count:
        return f"Business Health is {health}. {attention_count} item(s) need creator attention."
    if publishing not in {"ready", "unknown", "-", "Unavailable"}:
        return f"Business Health is {health}. Publishing requires attention."
    return f"Business Health is {health}. Business operating normally."


def _daily_business_snapshot(dashboard) -> tuple[tuple[str, str], ...]:
    products = dashboard.summary("Products")
    publishing = dashboard.summary("Publishing")
    customer_business = dashboard.summary("Customer Business")
    telegram = dashboard.summary("Telegram Operations")
    optimization = dashboard.summary("Business Optimization")
    return (
        ("Products Ready", _metric_value(publishing, "Ready To Publish")),
        ("Publishing Queue", _metric_value(publishing, "Publishing Queue Count")),
        (
            "Customers Requiring Attention",
            _metric_value(customer_business, "At-risk Customers"),
        ),
        ("Active Telegram Operations", _metric_value(telegram, "Active Conversations")),
        ("Business Health", _metric_value(optimization, "Overall Business Health")),
        ("Product Highlights", _metric_value(products, "Active Products")),
        ("Publishing Status", _metric_value(optimization, "Publishing Readiness")),
        ("Customer Highlights", _metric_value(customer_business, "VIP Customers")),
    )


def _daily_business_opportunities(dashboard) -> tuple[tuple[str, str], ...]:
    optimization_card = dashboard.business_optimization_card
    business_opportunity = "Review Business Optimization"
    if optimization_card is not None:
        recommendations = tuple(
            optimization_card.business_optimization.prioritized_recommendations
        )
        if recommendations:
            business_opportunity = recommendations[0].recommended_action
    product_opportunity = (
        dashboard.product_business_cards[0].next_recommended_action
        if dashboard.product_business_cards
        else "Review Products"
    )
    customer_opportunity = (
        dashboard.customer_business_cards[0].next_recommended_action
        if dashboard.customer_business_cards
        else "Review Customers"
    )
    publishing = dashboard.summary("Publishing")
    return (
        ("Product", product_opportunity),
        ("Customer", customer_opportunity),
        ("Publishing", _metric_value(publishing, "Waiting For Media Link")),
        ("Business", business_opportunity),
    )


def _render_todays_priorities(dashboard) -> None:
    actions = tuple(dashboard.recommended_actions[:3])
    if not actions:
        st.success("Business operating normally.")
        return
    for index, action in enumerate(actions, start=1):
        with st.container():
            st.write(f"{index}. {action.title}")
            st.caption(
                " | ".join(
                    (
                        f"Priority: {action.priority}",
                        f"Source: {action.source}",
                        f"Impact: {action.detail or 'Review recommended'}",
                    )
                )
            )
            if action.target and st.button(
                f"Open {action.target}",
                key=f"creator_hq_priority_{index}_{action.target}",
                use_container_width=True,
            ):
                _navigate(action.target)


def _render_creator_attention(dashboard) -> None:
    items = _creator_attention_items(dashboard)
    categories = (
        "Publishing",
        "Products",
        "Customers",
        "Telegram",
        "AI Review",
        "Business Risks",
    )
    grouped = {category: [] for category in categories}
    for item in items:
        grouped.setdefault(item["category"], []).append(item)

    if not items:
        st.success("Everything important is operating normally.")
    else:
        st.warning("Creator attention required.")

    columns = st.columns(3)
    for index, category in enumerate(categories):
        columns[index % 3].metric(category, str(len(grouped.get(category, ()))))

    if st.button(
        "Ask Creator Agent why these items need attention",
        key="creator_hq_attention_ask_creator_agent",
        use_container_width=True,
    ):
        st.session_state["creator_agent_prefill_question"] = (
            "Why do these Creator Attention items need attention?"
        )
        _navigate("Creator Agent")

    for category in categories:
        category_items = tuple(
            sorted(
                grouped.get(category, ()),
                key=_attention_priority_sort_key,
            )
        )
        with st.container():
            st.subheader(category)
            if not category_items:
                st.caption("No attention required.")
                continue
            for index, item in enumerate(category_items):
                st.caption(
                    " | ".join(
                        (
                            item["severity"].upper(),
                            item["source"],
                            f"Count: {item['count']}",
                        )
                    )
                )
                st.write(item["title"])
                st.caption(item["detail"])
                if item["target"] and st.button(
                    item["action"],
                    key=f"creator_hq_attention_{category}_{index}_{item['target']}",
                    use_container_width=True,
                ):
                    _navigate(item["target"])


def _creator_attention_items(dashboard) -> tuple[dict[str, str], ...]:
    publishing = dashboard.summary("Publishing")
    products = dashboard.summary("Products")
    customer_business = dashboard.summary("Customer Business")
    telegram = dashboard.summary("Telegram Operations")
    optimization = dashboard.summary("Business Optimization")
    items: list[dict[str, str]] = []

    def add(
        *,
        category: str,
        title: str,
        count: str,
        detail: str,
        severity: str,
        action: str,
        target: str | None,
        source: str,
    ) -> None:
        if str(count) in {"0", "-", "Unavailable", "UNKNOWN", "unknown", ""}:
            return
        items.append(
            {
                "category": category,
                "title": title,
                "count": str(count),
                "detail": detail,
                "severity": severity,
                "action": action,
                "target": target or "",
                "source": source,
            }
        )

    add(
        category="Publishing",
        title="Products awaiting Media Links",
        count=_metric_value(publishing, "Missing Media Link"),
        detail="Products or publishing jobs need Media Link completion.",
        severity="warning",
        action="Review Media Links",
        target="Publishing Queue",
        source="Publishing",
    )
    add(
        category="Publishing",
        title="Publishing failures",
        count=_metric_value(publishing, "Failed Count"),
        detail="Publishing jobs failed and need review.",
        severity="critical",
        action="Review Failed Uploads",
        target="Publishing Queue",
        source="Publishing",
    )
    add(
        category="Publishing",
        title="Retry-required Publishing Jobs",
        count=_metric_value(publishing, "Retry Required Count"),
        detail="Publishing jobs are ready for retry review.",
        severity="warning",
        action="Review Retry Required",
        target="Publishing Queue",
        source="Publishing",
    )
    add(
        category="Products",
        title="Products awaiting approval",
        count=_metric_value(products, "Products Needing Review"),
        detail="Products need creator review before they can progress.",
        severity="warning",
        action="Open Product Review",
        target="Product Review",
        source="Products",
    )
    if dashboard.product_business_health is not None:
        add(
            category="Products",
            title="Missing Products or missing FREE previews",
            count=str(len(dashboard.product_business_health.portfolio_gaps)),
            detail="Product Business reports portfolio gaps.",
            severity="warning",
            action="Review Product Business",
            target="Product Catalog",
            source="Product Business",
        )
    add(
        category="Customers",
        title="At-risk customers",
        count=_metric_value(customer_business, "At-risk Customers"),
        detail="Customer Business reports customers needing attention.",
        severity="warning",
        action="Open Customer Workspace",
        target="Customer Workspace",
        source="Customer Business",
    )
    add(
        category="Customers",
        title="Customer issues",
        count=_metric_value(customer_business, "Retention Opportunities"),
        detail="Customer Business reports retention opportunities.",
        severity="warning",
        action="Review Customer Retention",
        target="Customer Workspace",
        source="Customer Business",
    )
    add(
        category="Telegram",
        title="Telegram conversations needing follow-up",
        count=_metric_value(telegram, "Customers Needing Follow-Up"),
        detail="Telegram Operations reports conversations requiring follow-up.",
        severity="warning",
        action="Review Telegram Follow-up",
        target="Customer Workspace",
        source="Telegram Business",
    )
    add(
        category="Telegram",
        title="VIP opportunities",
        count=_metric_value(telegram, "VIP Opportunities"),
        detail="Telegram Business reports VIP relationship opportunities.",
        severity="info",
        action="Review VIP Opportunities",
        target="Customer Workspace",
        source="Telegram Business",
    )
    if dashboard.creator_review is not None:
        add(
            category="AI Review",
            title="Low AI confidence or high-priority review",
            count=str(dashboard.creator_review.high_priority_reviews),
            detail="Creator Review reports high-priority AI review items.",
            severity="warning",
            action="Open Product Review",
            target="Product Review",
            source="Creator Review",
        )
    add(
        category="Business Risks",
        title="Business risks",
        count=_metric_value(optimization, "Critical Recommendations"),
        detail="Business Optimization reports critical recommendations.",
        severity="critical",
        action="Review Business Optimization",
        target="Creator Workspace",
        source="Business Optimization",
    )
    for notification in dashboard.notifications:
        if not notification.action_required:
            continue
        items.append(
            {
                "category": "Business Risks",
                "title": notification.title,
                "count": "1",
                "detail": notification.detail,
                "severity": notification.severity,
                "action": "Review Notification",
                "target": "",
                "source": notification.source,
            }
        )
    return tuple(items)


def _attention_priority_sort_key(item: dict[str, str]) -> int:
    return {
        "critical": 0,
        "warning": 1,
        "high": 1,
        "info": 2,
    }.get(str(item.get("severity", "")).lower(), 3)


def _render_opportunities(dashboard) -> None:
    product_opportunity = (
        dashboard.product_business_cards[0].next_recommended_action
        if dashboard.product_business_cards
        else "Review Product Business"
    )
    customer_opportunity = (
        dashboard.customer_business_cards[0].next_recommended_action
        if dashboard.customer_business_cards
        else "Review Customer Business"
    )
    publishing = dashboard.summary("Publishing")
    optimization_card = dashboard.business_optimization_card
    optimization_opportunity = "Review Business Optimization"
    revenue_opportunity = "Unavailable"
    if optimization_card is not None:
        recommendations = tuple(
            optimization_card.business_optimization.prioritized_recommendations
        )
        if recommendations:
            optimization_opportunity = recommendations[0].recommended_action
        revenue_opportunity = optimization_card.revenue_readiness
    rows = (
        ("Best Product opportunity", product_opportunity),
        ("Customer growth opportunity", customer_opportunity),
        ("Publishing opportunity", _metric_value(publishing, "Waiting For Media Link")),
        ("Revenue opportunity", revenue_opportunity),
        ("Business Optimization recommendation", optimization_opportunity),
    )
    for row in range(0, len(rows), 3):
        columns = st.columns(3)
        for column, (label, value) in zip(columns, rows[row : row + 3]):
            column.metric(label, value)


def _render_quick_navigation() -> None:
    actions = (
        ("Creator Agent", "Creator Agent"),
        ("Products", "Product Catalog"),
        ("Publishing", "Publishing Queue"),
        ("Customers", "Customer Workspace"),
        ("Telegram", "Customer Workspace"),
        ("Business", "Creator Workspace"),
        ("Administration", "Creator Profile"),
    )
    columns = st.columns(4)
    for index, (label, target) in enumerate(actions):
        if columns[index % 4].button(
            label,
            key=f"creator_hq_quick_nav_{label}",
            use_container_width=True,
        ):
            _navigate(target)


def _render_dashboard_snapshot(dashboard) -> None:
    assets = dashboard.summary("Assets")
    experiences = dashboard.summary("Experiences")
    products = dashboard.summary("Products")
    publishing = dashboard.summary("Publishing")
    notifications = dashboard.summary("Notifications")
    rows = (
        ("Assets", _metric_value(assets, "Total Assets")),
        ("Experiences", _metric_value(experiences, "Total Experiences")),
        ("Products", _metric_value(products, "Total Products")),
        ("Ready To Publish", _metric_value(publishing, "Ready To Publish")),
        ("Needs Attention", _metric_value(notifications, "Attention Items")),
        ("Review Required", _metric_value(products, "Products Needing Review")),
        ("Missing Price", _metric_value(products, "Missing Price")),
        ("Missing Media Link", _metric_value(publishing, "Missing Media Link")),
        ("Missing Assets", _metric_value(products, "Missing Assets")),
        (
            "FREE / PAID",
            (
                f"{_metric_value(products, 'Free Products')} / "
                f"{_metric_value(products, 'Paid Products')}"
            ),
        ),
        ("Fanvue-ready", _metric_value(publishing, "Fanvue-ready Items")),
        ("Telegram-ready", _metric_value(publishing, "Telegram-ready Items")),
    )
    for row in range(0, len(rows), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, rows[row : row + 4]):
            column.metric(label, value)


def _render_creator_workflow(
    items: tuple[WorkspaceWorkflowItem, ...],
) -> None:
    if not items:
        st.caption("Creator Workflow projections are not available for this scope.")
        return

    attention_required = sum(
        1 for item in items if item.attention_summary.attention_required
    )
    columns = st.columns(4)
    columns[0].metric("Workflow Items", str(len(items)))
    columns[1].metric("Needs Attention", str(attention_required))
    columns[2].metric("Current Stage", items[0].current_workflow_stage)
    columns[3].metric("Lifecycle", items[0].current_lifecycle_stage)

    if not attention_required:
        st.success("Nothing requires attention.")

    for index, item in enumerate(items[:6]):
        attention = item.attention_summary
        publishing = item.publishing_status
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Workflow", item.current_workflow_stage)
            c2.metric("Lifecycle", item.current_lifecycle_stage)
            c3.metric("Publishing", publishing.state.value)
            c4.metric("Priority", attention.highest_priority.value)
            st.write(f"**{item.product_name}**")
            st.caption(
                " | ".join(
                    (
                        f"Next: {item.next_recommended_action}",
                        f"Publishing Status: {publishing.publishing_status or '-'}",
                        f"Media Link: {publishing.media_link_status or '-'}",
                    )
                )
            )
            for attention_item in attention.items:
                st.caption(
                    " | ".join(
                        (
                            attention_item.priority.value,
                            attention_item.category.value,
                            attention_item.recommended_action,
                        )
                    )
                )
                st.caption(attention_item.reason)
            if attention.attention_required:
                st.warning("Action required.")
            else:
                st.info("No action required.")
        if index < len(items[:6]) - 1:
            st.divider()


def _render_recommended_actions(
    actions: tuple[WorkspaceRecommendedAction, ...],
) -> None:
    if not actions:
        st.caption("No recommended next actions.")
        return

    for index, action in enumerate(actions[:6]):
        with st.container():
            st.caption(f"{action.priority.upper()} | {action.source}")
            st.write(action.title)
            st.caption(action.detail)
            if action.target and st.button(
                f"Open {action.target}",
                key=f"workspace_action_{index}_{action.target}",
                use_container_width=True,
            ):
                _navigate(action.target)
        if index < len(actions[:6]) - 1:
            st.divider()


def _render_publishing_operations(dashboard) -> None:
    publishing = dashboard.summary("Publishing")
    rows = (
        ("Queue", _metric_value(publishing, "Publishing Queue Count")),
        ("Uploading", _metric_value(publishing, "Uploading Count")),
        ("Uploaded", _metric_value(publishing, "Uploaded Count")),
        ("Waiting Links", _metric_value(publishing, "Waiting For Media Link")),
        ("Failed", _metric_value(publishing, "Failed Count")),
        ("Retry Required", _metric_value(publishing, "Retry Required Count")),
        ("Complete", _metric_value(publishing, "Publishing Complete")),
        ("Product ACTIVE", _metric_value(publishing, "Product ACTIVE Count")),
    )
    for row in range(0, len(rows), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, rows[row : row + 4]):
            column.metric(label, value)

    st.caption(f"Providers: {_metric_value(publishing, 'Provider Summary')}")

    actions = (
        ("Open Publishing Queue", "Publishing Queue"),
        ("Review Waiting For Media Links", "Publishing Queue"),
        ("Review Failed Uploads", "Publishing Queue"),
        ("Review Retry Required", "Publishing Queue"),
        ("Review Publishing Complete", "Publishing Queue"),
    )
    columns = st.columns(len(actions))
    for column, (label, target) in zip(columns, actions):
        if column.button(
            label,
            key=f"workspace_publishing_ops_{label}",
            use_container_width=True,
        ):
            _navigate(target)

    _render_publishing_operation_items(dashboard.publishing_queue)


def _render_publishing_operation_items(
    items: tuple[WorkspacePublishingQueueItem, ...],
) -> None:
    if not items:
        st.caption("No Publishing operations to show.")
        return

    for index, item in enumerate(items[:6]):
        with st.container():
            st.caption(f"{item.severity.upper()} | {item.status} | {item.source}")
            st.write(item.title)
            st.caption(item.detail)
            if item.action_required:
                st.warning("Action required.")
            elif item.future_ready:
                st.info("Placeholder: operation detail is not yet exposed.")
        if index < len(items[:6]) - 1:
            st.divider()


def _render_telegram_operations(dashboard) -> None:
    telegram = dashboard.summary("Telegram Operations")
    rows = (
        ("Active Conversations", _metric_value(telegram, "Active Conversations")),
        ("Relationship Health", _metric_value(telegram, "Operating State")),
        ("Active Experiences", _metric_value(telegram, "Active Experiences")),
        ("Customer Journeys", _metric_value(telegram, "Current Customer Journeys")),
        ("Pending Offers", _metric_value(telegram, "Pending Offers")),
        ("Pending Deliveries", _metric_value(telegram, "Pending Deliveries")),
        ("VIP Opportunities", _metric_value(telegram, "VIP Opportunities")),
        ("Follow-Up", _metric_value(telegram, "Customers Needing Follow-Up")),
        ("Next Actions", _metric_value(telegram, "Recommended Telegram Actions")),
        ("FREE Deliveries", _metric_value(telegram, "FREE Deliveries")),
        ("PAID Offers", _metric_value(telegram, "PAID Media Link Deliveries")),
        ("Business Customers", _metric_value(telegram, "Telegram Business Customers")),
    )
    for row in range(0, len(rows), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, rows[row : row + 4]):
            column.metric(label, value)

    actions = (
        ("Open Customer Workspace", "Customer Workspace"),
        ("Review Active Conversations", "Customer Workspace"),
        ("Review Customers Needing Follow-Up", "Customer Workspace"),
        ("Review Recent Paid Offers", "Customer Workspace"),
        ("Review Current Experiences", "Customer Workspace"),
    )
    columns = st.columns(len(actions))
    for column, (label, target) in zip(columns, actions):
        if column.button(
            label,
            key=f"workspace_telegram_ops_{label}",
            use_container_width=True,
        ):
            _navigate(target)

    _render_telegram_business_cards(dashboard.telegram_business_cards)
    _render_telegram_operation_items(dashboard.telegram_operations)


def _render_telegram_business_cards(
    cards: tuple[WorkspaceTelegramBusinessCard, ...],
) -> None:
    if not cards:
        st.caption("Telegram Business customer read models are not available yet.")
        return

    for index, card in enumerate(cards[:6]):
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Relationship", card.relationship_health)
            c2.metric("Conversation", card.conversation_status)
            c3.metric("Sales", card.sales_action)
            c4.metric("Delivery", card.delivery_action)
            st.write(f"**{card.customer_id or 'Telegram customer'}**")
            st.caption(
                " | ".join(
                    (
                        f"Provider: {card.provider}",
                        f"Business: {card.business_health}",
                        f"Next: {card.next_recommended_action}",
                    )
                )
            )
            if card.compatibility:
                st.caption("Presentation-only Telegram Business projection")
        if index < len(cards[:6]) - 1:
            st.divider()


def _render_customer_business(dashboard) -> None:
    customer_business = dashboard.summary("Customer Business")
    rows = (
        ("Active Customers", _metric_value(customer_business, "Active Customers")),
        ("New Customers", _metric_value(customer_business, "New Customers")),
        ("Returning", _metric_value(customer_business, "Returning Customers")),
        ("VIP", _metric_value(customer_business, "VIP Customers")),
        ("At-risk", _metric_value(customer_business, "At-risk Customers")),
        ("Dormant", _metric_value(customer_business, "Dormant Customers")),
        ("Growth", _metric_value(customer_business, "Growth Opportunities")),
        ("Retention", _metric_value(customer_business, "Retention Opportunities")),
        ("Next Actions", _metric_value(customer_business, "Recommended Customer Actions")),
        ("Customers", _metric_value(customer_business, "Customer Business Customers")),
        ("State", _metric_value(customer_business, "Operating State")),
    )
    for row in range(0, len(rows), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, rows[row : row + 4]):
            column.metric(label, value)

    actions = (
        ("Open Customer Workspace", "Customer Workspace"),
        ("Review Growth Opportunities", "Customer Workspace"),
        ("Review Retention Opportunities", "Customer Workspace"),
        ("Review VIP Customers", "Customer Workspace"),
    )
    columns = st.columns(len(actions))
    for column, (label, target) in zip(columns, actions):
        if column.button(
            label,
            key=f"workspace_customer_business_{label}",
            use_container_width=True,
        ):
            _navigate(target)

    _render_customer_business_cards(dashboard.customer_business_cards)


def _render_customer_business_cards(
    cards: tuple[WorkspaceCustomerBusinessCard, ...],
) -> None:
    if not cards:
        st.caption("Customer Business read models are not available yet.")
        return

    for index, card in enumerate(cards[:6]):
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Health", card.customer_health)
            c2.metric("Journey", card.journey_stage)
            c3.metric("Value", card.value_tier)
            c4.metric("Retention", card.retention_status)
            st.write(f"**{card.customer_id or 'Customer'}**")
            st.caption(
                " | ".join(
                    (
                        f"Growth: {card.growth_stage}",
                        f"Growth opportunities: {card.growth_opportunity_count}",
                        f"Retention opportunities: {card.retention_opportunity_count}",
                        f"Next: {card.next_recommended_action}",
                    )
                )
            )
            if card.compatibility:
                st.caption("Presentation-only Customer Business projection")
        if index < len(cards[:6]) - 1:
            st.divider()


def _render_business_optimization(dashboard) -> None:
    optimization = dashboard.summary("Business Optimization")
    rows = (
        ("Business Health", _metric_value(optimization, "Overall Business Health")),
        ("Performance", _metric_value(optimization, "Performance Health")),
        ("Strategy", _metric_value(optimization, "Strategy Health")),
        ("Revenue", _metric_value(optimization, "Revenue Readiness")),
        ("Publishing", _metric_value(optimization, "Publishing Readiness")),
        ("Products", _metric_value(optimization, "Product Health")),
        ("Customers", _metric_value(optimization, "Customer Health")),
        ("Telegram", _metric_value(optimization, "Telegram Health")),
        ("High-impact", _metric_value(optimization, "High-impact Opportunities")),
        ("Critical", _metric_value(optimization, "Critical Recommendations")),
        ("Today", _metric_value(optimization, "Today's Business Actions")),
        ("This Week", _metric_value(optimization, "This Week's Business Actions")),
    )
    for row in range(0, len(rows), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, rows[row : row + 4]):
            column.metric(label, value)

    st.caption(
        "Next: "
        + _metric_value(
            optimization,
            "Next Recommended Business Action",
            "Review Business",
        )
    )
    _render_business_optimization_card(dashboard.business_optimization_card)


def _render_business_optimization_card(
    card: WorkspaceBusinessOptimizationCard | None,
) -> None:
    if card is None:
        st.caption("Business Optimization read model is not available yet.")
        return

    actions = card.business_optimization.prioritized_recommendations
    if not actions:
        st.success("Everything operating normally.")
    for index, action in enumerate(actions[:6]):
        with st.container():
            st.caption(
                " | ".join(
                    (
                        action.priority.value,
                        action.category.value,
                        action.timeframe,
                    )
                )
            )
            st.write(action.recommended_action)
            st.caption(
                " | ".join(
                    (
                        f"Confidence: {action.confidence:.2f}",
                        f"Revenue: {card.revenue_readiness}",
                        f"Next: {card.next_recommended_business_action}",
                    )
                )
            )
            if action.priority.value == "CRITICAL":
                st.warning("Action required.")
        if index < len(actions[:6]) - 1:
            st.divider()
    if card.compatibility:
        st.caption("Presentation-only Business Optimization projection")


def _render_content_opportunity_center(dashboard) -> None:
    opportunity = dashboard.summary("Content Opportunity")
    rows = (
        ("Total Requests", _metric_value(opportunity, "Total Requests")),
        ("Matched", _metric_value(opportunity, "Matched Requests")),
        ("Unmatched", _metric_value(opportunity, "Unmatched Requests")),
        ("Matched %", _metric_value(opportunity, "Matched Percentage")),
        ("Unmatched %", _metric_value(opportunity, "Unmatched Percentage")),
        ("Health", _metric_value(opportunity, "Opportunity Health")),
        ("Trending", _metric_value(opportunity, "Trending Topics")),
        ("Growing", _metric_value(opportunity, "Growing Topics")),
        ("Repeat", _metric_value(opportunity, "Repeat Demand")),
        ("VIP", _metric_value(opportunity, "VIP Demand")),
        ("Resolution Ready", _metric_value(opportunity, "Resolution Ready")),
        ("Waiting Customers", _metric_value(opportunity, "Waiting Customers")),
        ("Ready Follow-ups", _metric_value(opportunity, "Ready Follow-ups")),
    )
    for row in range(0, len(rows), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, rows[row : row + 4]):
            column.metric(label, value)

    st.caption(
        "Next: "
        + _metric_value(
            opportunity,
            "Next Recommended Action",
            "Review Content Opportunities",
        )
    )
    _render_content_opportunity_card(dashboard.content_opportunity_card)


def _render_content_opportunity_card(
    card: WorkspaceContentOpportunityCard | None,
) -> None:
    if card is None:
        st.caption("Content Opportunity read model is not available yet.")
        return

    snapshot = card.content_opportunity
    if card.total_requests <= 0:
        st.success("No customer content demand has been recorded yet.")
    elif (
        card.highest_priority_opportunity_count == 0
        and card.resolution_ready_count == 0
        and card.ready_follow_up_count == 0
    ):
        st.success("Content Opportunity is operating normally.")

    columns = st.columns(3)
    with columns[0]:
        st.subheader("Demand Trends")
        topics = snapshot.trending_topics or snapshot.top_requested_topics
        if not topics:
            st.caption("No trending demand yet.")
        for topic in topics[:5]:
            st.write(" ".join(topic.terms) or topic.topic_key)
            st.caption(
                " | ".join(
                    (
                        f"Requests: {topic.request_count}",
                        f"Customers: {topic.unique_customers}",
                        f"VIP: {topic.vip_request_count}",
                    )
                )
            )

    with columns[1]:
        st.subheader("Business Opportunities")
        recommendations = snapshot.creator_recommendations
        if not recommendations:
            st.caption("No creator opportunity recommendations yet.")
        for recommendation in recommendations[:5]:
            st.write(recommendation.title)
            st.caption(
                " | ".join(
                    (
                        recommendation.priority.value,
                        f"Confidence: {recommendation.confidence:.2f}",
                    )
                )
            )

    with columns[2]:
        st.subheader("Resolution & Follow-up")
        st.caption(
            " | ".join(
                (
                    f"Ready: {card.resolution_ready_count}",
                    f"Pending: {card.pending_follow_up_count}",
                    f"Follow-ups: {card.ready_follow_up_count}",
                    f"Completed: {card.completed_follow_up_count}",
                )
            )
        )
        ready_follow_ups = snapshot.follow_up_opportunities[:5]
        if not ready_follow_ups:
            st.caption("No follow-up opportunities waiting.")
        for follow_up in ready_follow_ups:
            st.write(follow_up.original_request_text or "Customer content request")
            st.caption(
                " | ".join(
                    (
                        follow_up.priority.value,
                        follow_up.status.value,
                        f"Confidence: {follow_up.confidence:.2f}",
                    )
                )
            )

    waiting_customers = tuple(card.waiting_customers or ())[:6]
    if waiting_customers:
        st.subheader("Waiting Customers")
        for customer in waiting_customers:
            label = (
                customer.get("customer_id")
                or customer.get("provider_customer_id")
                or "Waiting customer"
            )
            st.write(str(label))
            st.caption(
                " | ".join(
                    str(value)
                    for value in (
                        customer.get("provider"),
                        customer.get("status"),
                        customer.get("request_text"),
                    )
                    if value
                )
            )

    if card.compatibility:
        st.caption("Presentation-only Content Opportunity Center")


def _render_telegram_operation_items(
    items: tuple[WorkspaceTelegramOperationItem, ...],
) -> None:
    if not items:
        st.caption("No Telegram Commerce operations to show.")
        return

    for index, item in enumerate(items[:8]):
        with st.container():
            st.caption(f"{item.severity.upper()} | {item.status} | {item.source}")
            st.write(item.title)
            st.caption(item.detail)
            if item.action_required:
                st.warning("Action required.")
            elif item.future_ready:
                st.info("Placeholder: operation detail is not yet exposed.")
            if item.target and st.button(
                f"Open {item.target}",
                key=f"workspace_telegram_item_{index}_{item.operation_type}",
                use_container_width=True,
            ):
                _navigate(item.target)
        if index < len(items[:8]) - 1:
            st.divider()


def _render_recent_activity(events) -> None:
    if not events:
        st.caption("No recent activity available.")
        return

    for index, event in enumerate(events[:3]):
        with st.container():
            st.caption(f"{event.source} | {event.event_type}")
            st.write(event.title)
            st.caption(event.detail)
        if index < len(events[:3]) - 1:
            st.divider()


def _render_creator_review(review) -> None:
    if not review:
        st.caption("Creator Review summary is unavailable.")
        return

    columns = st.columns(4)
    columns[0].metric("Pending", str(review.total_pending))
    columns[1].metric("Assets", str(review.assets_awaiting_review))
    columns[2].metric("Products", str(review.products_awaiting_review))
    completion = (
        f"{round(review.review_completion_percentage)}%"
        if review.review_completion_percentage is not None
        else "Unavailable"
    )
    columns[3].metric("Completion", completion)

    subcolumns = st.columns(4)
    subcolumns[0].metric("Experiences", str(review.experiences_awaiting_review))
    subcolumns[1].metric("Publishing", str(review.publishing_reviews_remaining))
    subcolumns[2].metric("High Priority", str(review.high_priority_reviews))
    subcolumns[3].metric(
        "Completed",
        str(review.completed_reviews)
        if review.completed_reviews is not None
        else "Unavailable",
    )

    if not review.items:
        st.caption("No pending Creator Review items.")
        return

    for index, item in enumerate(review.items[:5]):
        with st.container():
            st.caption(f"{item.priority.upper()} | {item.review_type}")
            st.write(item.title)
            st.caption(item.detail)
            metadata = [
                f"Status: {item.status}",
                f"Completeness: {item.completeness}",
                "Evidence available" if item.evidence_available else "Evidence unavailable",
            ]
            if item.confidence is not None:
                metadata.append(f"Confidence: {item.confidence:.2f}")
            st.caption(" | ".join(metadata))
            if item.override_proposals:
                st.caption(
                    "Override proposals: "
                    + ", ".join(item.override_proposals)
                )
            if item.target and st.button(
                f"Open {item.target}",
                key=f"workspace_review_{index}_{item.target}",
                use_container_width=True,
            ):
                _navigate(item.target)
        if index < len(review.items[:5]) - 1:
            st.divider()


def _open_product_review(
    *,
    search: str | None = None,
    approval_status: str | None = None,
) -> None:
    if search is not None:
        st.session_state["product_review_search"] = search
    if approval_status is not None:
        st.session_state["product_review_approval_filter"] = approval_status
    _navigate("Product Review")


def _render_product_review_summary(review: ProductReviewSummary | None) -> None:
    if not review:
        st.caption("Product Review summary is unavailable.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Awaiting Review", str(review.needs_review))
    c2.metric("Approved", str(review.approved))
    c3.metric("Rejected", str(review.rejected))
    c4.metric("Ready To Publish", str(review.ready_to_publish))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Manual Products", str(review.manual_products))
    c6.metric("AI Drafts", str(review.ai_product_drafts))
    c7.metric("Commerce Overrides", str(review.products_with_commerce_overrides))
    c8.metric("Total Reviews", str(review.total_reviews))

    a1, a2 = st.columns(2)
    if a1.button("Open Product Review", use_container_width=True):
        _open_product_review()
    if a2.button("Review Awaiting Approval", use_container_width=True):
        _open_product_review(approval_status="NEEDS_REVIEW")


def _render_experience_cards(
    experiences: tuple[WorkspaceExperienceCard, ...],
) -> None:
    if not experiences:
        st.caption("No Experiences available for this creator profile.")
        return

    for index, experience in enumerate(experiences[:6]):
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Type", experience.experience_type)
            c2.metric("Assets", str(experience.asset_count))
            c3.metric("Products", str(experience.product_count))
            c4.metric("Publishing", experience.publishing_readiness.status)
            st.write(f"**{experience.title}**")
            if experience.summary:
                st.caption(experience.summary)
            details = [
                f"Cover Asset: #{experience.cover_asset_id}"
                if experience.cover_asset_id
                else "Cover Asset: missing",
                f"Intelligence: {experience.intelligence_coverage}",
                f"Relationships: {experience.relationship_source}",
            ]
            if experience.compatibility:
                details.append("Compatibility projection")
            st.caption(" | ".join(details))
            if experience.delivery_types:
                st.caption(f"Delivery Types: {', '.join(experience.delivery_types)}")
            if experience.themes:
                st.caption(f"Themes: {', '.join(experience.themes)}")
            if experience.keywords:
                st.caption(f"Keywords: {', '.join(experience.keywords)}")
            if experience.mood:
                st.caption(f"Mood: {experience.mood}")
            if experience.story_progression:
                st.caption(f"Story: {experience.story_progression}")
            if experience.publishing_readiness.detail:
                st.caption(experience.publishing_readiness.detail)
        if index < len(experiences[:6]) - 1:
            st.divider()


def _render_product_cards(
    products: tuple[WorkspaceProductCard, ...],
) -> None:
    if not products:
        st.caption("No Products available for this creator profile.")
        return

    for index, product in enumerate(products[:6]):
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Status", product.status)
            c2.metric("Review", product.review_status)
            c3.metric("Delivery", product.delivery_type)
            c4.metric("Publishing", product.publishing_readiness)
            st.write(f"**{product.name}**")
            st.caption(
                " | ".join(
                    (
                        product.product_type,
                        product.product_origin,
                        f"Price: {product.price}",
                        f"Suggested: {product.suggested_price}",
                        f"Assets: {product.asset_count}",
                    )
                )
            )
            if product.experience_name or product.experience_type:
                st.caption(
                    "Experience: "
                    f"{product.experience_name or 'Unnamed'}"
                    + (
                        f" ({product.experience_type})"
                        if product.experience_type
                        else ""
                    )
                )
            st.caption(
                " | ".join(
                    (
                        f"Experience Relationship: {product.experience_relationship}",
                        f"Approval: {product.approval_status}",
                        f"Provider: {product.provider_status}",
                        f"Telegram: {product.telegram_delivery_status}",
                    )
                )
            )
            if product.has_commerce_overrides:
                st.caption(
                    f"Commerce overrides: {product.commerce_override_count}"
                )
            if product.ready_to_publish:
                st.caption("Ready To Publish")
            if st.button(
                "Review Product",
                key=f"workspace_product_review_{product.product_id}_{index}",
                use_container_width=True,
            ):
                _open_product_review(search=product.name)
            if product.compatibility:
                st.caption("Compatibility projection")
        if index < len(products[:6]) - 1:
            st.divider()


def _render_product_business(
    health,
    products: tuple[WorkspaceProductBusinessCard, ...],
) -> None:
    if health is None:
        st.caption("Product Business is unavailable for this creator profile.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Portfolio", health.status.value)
    c2.metric("Products", str(health.total_products))
    c3.metric("Missing", str(len(health.portfolio_gaps)))
    c4.metric("Recommendations", str(len(health.recommendations)))

    if health.status.value == "HEALTHY":
        st.success("Portfolio healthy.")
    elif health.portfolio_gaps:
        st.caption("Missing: " + ", ".join(health.portfolio_gaps))
    if health.recommendations:
        for recommendation in health.recommendations[:3]:
            st.caption(
                " | ".join(
                    (
                        recommendation.priority,
                        recommendation.label,
                        recommendation.reason or "No rationale provided.",
                    )
                )
            )

    if not products:
        st.caption("No Product Business cards available.")
        return

    for index, product in enumerate(products[:6]):
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Health", product.product_health)
            c2.metric("Availability", product.availability_status)
            c3.metric("Performance", product.performance_status)
            c4.metric(
                "Improvements",
                str(len(product.improvement.recommendations)),
            )
            st.write(f"**{product.product_name}**")
            st.caption(
                " | ".join(
                    (
                        f"Type: {product.product_business.product_type or '-'}",
                        f"Delivery: {product.product_business.delivery_type or '-'}",
                        f"Next: {product.next_recommended_action}",
                    )
                )
            )
            reach = product.product_business.customer_reach
            performance = product.performance.summary
            st.caption(
                " | ".join(
                    (
                        f"Reach: {reach.get('customer_count', 0)}",
                        f"Conversion: {performance.conversion_rate:.2f}",
                        f"Trend: {performance.trend}",
                    )
                )
            )
            if product.improvement.next_recommendation is not None:
                recommendation = product.improvement.next_recommendation
                st.caption(
                    "Improvement: "
                    f"{recommendation.priority.value} | "
                    f"{recommendation.label}"
                )
            if product.compatibility:
                st.caption("Compatibility projection")
        if index < len(products[:6]) - 1:
            st.divider()


def _render_publishing_cards(
    items: tuple[WorkspacePublishingCard, ...],
) -> None:
    if not items:
        st.caption("No publishing readiness items available for this creator profile.")
        return

    for index, item in enumerate(items[:6]):
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Publishing", item.publishing_status)
            c2.metric("Readiness", item.publishing_readiness)
            c3.metric("Provider", item.provider_status)
            c4.metric("Delivery", item.delivery_type)
            st.write(f"**{item.product_name}**")
            context = [
                item.product_type,
                f"Provider: {item.provider}",
                f"Media Link: {item.media_link_status}",
                f"Telegram: {item.telegram_delivery_intent}",
            ]
            st.caption(" | ".join(context))
            if item.experience_name:
                st.caption(f"Experience: {item.experience_name}")
            if item.missing_requirements:
                st.warning(
                    "Missing: " + ", ".join(item.missing_requirements)
                )
            elif item.ready_to_publish:
                st.success("Ready to publish.")
            if item.provider_error:
                st.error(item.provider_error)
            if item.published_active:
                st.caption("Published / Active")
            if item.compatibility:
                st.caption("Compatibility projection")
        if index < len(items[:6]) - 1:
            st.divider()


def _render_notifications(
    notifications: tuple[WorkspaceNotification, ...],
) -> None:
    if not notifications:
        st.caption("No workspace notifications.")
        return

    for index, notification in enumerate(notifications):
        with st.container():
            st.caption(
                " | ".join(
                    (
                        notification.severity.upper(),
                        notification.status,
                        notification.source,
                    )
                )
            )
            st.write(notification.title)
            st.caption(notification.detail)
            if notification.action_required:
                st.warning("Action required.")
            elif notification.future_ready:
                st.info("Placeholder: notification source not yet exposed.")
        if index < len(notifications) - 1:
            st.divider()


def _render_insights(insights: tuple[WorkspaceInsight, ...]) -> None:
    if not insights:
        st.caption("No workspace insights available.")
        return

    for index, insight in enumerate(insights):
        with st.container():
            st.caption(
                " | ".join(
                    (
                        insight.category,
                        insight.trend,
                        f"Delta: {insight.delta}",
                    )
                )
            )
            st.write(insight.title)
            st.metric("Current", insight.current_value)
            st.caption(insight.detail)
            if insight.future_ready:
                st.info("Placeholder: historical trend source not yet exposed.")
        if index < len(insights) - 1:
            st.divider()


def _render_runtime_control_panel(
    dashboard,
    *,
    creator_profile: dict | None,
    runtime_control_service: RuntimeControlService | None = None,
) -> None:
    card = dashboard.runtime_control_card
    summary = dashboard.summaries.get("Runtime Control")
    service = runtime_control_service or RuntimeControlService()
    creator_profile_id = (creator_profile or {}).get("id")

    st.markdown("### 🤖 Creator OS Runtime")
    if card is None:
        st.warning("Creator OS Runtime state is not available.")
        return

    mode = card.current_mode
    if mode == "LIVE":
        st.success(card.warning_banner)
    elif mode == "OBSERVE":
        st.warning(card.warning_banner)
    else:
        st.error(card.warning_banner)

    rows = (
        ("Runtime Status", card.runtime_status),
        ("Last Started", card.last_started),
        ("Last Stopped", card.last_stopped),
        ("Current Mode", card.current_mode),
        ("Active Conversations", str(card.active_conversations)),
        ("Pending Deliveries", str(card.pending_deliveries)),
        ("Pending Offers", str(card.pending_offers)),
        ("Current Runtime Provider", card.current_runtime_provider),
    )
    for row in range(0, len(rows), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, rows[row : row + 4]):
            column.metric(label, value)

    columns = st.columns(3)
    if columns[0].button("▶ Start Creator OS", use_container_width=True):
        service.start(creator_profile_id=creator_profile_id)
        st.rerun()
    if columns[1].button("⏸ Observe Mode", use_container_width=True):
        service.observe(creator_profile_id=creator_profile_id)
        st.rerun()
    if columns[2].button("■ Stop Creator OS", use_container_width=True):
        service.stop(creator_profile_id=creator_profile_id)
        st.rerun()

    observations = tuple(card.runtime.observed_recommendations or ())[:5]
    if observations:
        st.caption("Observe Mode recommendations")
        for observation in observations:
            st.write(observation.suggested_reply or "Suggested runtime action")
            st.caption(
                " | ".join(
                    value
                    for value in (
                        observation.customer_id or "unknown customer",
                        observation.provider,
                        observation.message_text,
                    )
                    if value
                )
            )
    if summary is not None and summary.note:
        st.caption(summary.note)


def render_creator_workspace(
    *,
    creator_profile: dict | None = None,
    active_account: dict | None = None,
    workspace_service: CreatorWorkspaceService | None = None,
) -> None:
    profile_name = _creator_display_name(creator_profile)
    account = active_account or {}
    account_label = (
        account.get("display_name")
        or account.get("account_name")
        or account.get("username")
        or "No provider account selected"
    )
    dashboard = (workspace_service or CreatorWorkspaceService()).build_dashboard(
        creator_profile=creator_profile,
        active_account=active_account,
    )

    st.title("Creator HQ")
    st.caption("The operational control center for Creator OS.")

    with st.container():
        st.subheader(profile_name)
        st.caption(f"Provider account: {account_label}")
        if creator_profile:
            st.success("Creator profile loaded.")
        else:
            st.warning("Creator profile is missing.")

    _render_runtime_control_panel(
        dashboard,
        creator_profile=creator_profile,
        runtime_control_service=getattr(workspace_service, "runtime_control_service", None)
        if workspace_service
        else None,
    )

    st.markdown("### Creator Agent")
    _render_creator_agent_entry(active_account)

    st.markdown("### Daily Business Briefing")
    _render_daily_business_briefing(dashboard)

    st.markdown("### Business Health")
    _render_business_health(dashboard)

    st.markdown("### Today's Priorities")
    _render_todays_priorities(dashboard)

    st.markdown("### Creator Attention")
    _render_creator_attention(dashboard)

    st.markdown("### Opportunities")
    _render_opportunities(dashboard)

    st.markdown("### Quick Navigation")
    _render_quick_navigation()

    st.markdown("### Operational Dashboards")

    st.markdown("### Business Overview")
    _render_executive_cards(dashboard)

    st.markdown("### Operational Snapshot")
    _render_dashboard_snapshot(dashboard)

    st.markdown("### Recommended Actions")
    _render_recommended_actions(dashboard.recommended_actions)

    st.markdown("### Publishing Operations")
    _render_publishing_operations(dashboard)

    st.markdown("### Telegram Operations")
    _render_telegram_operations(dashboard)

    st.markdown("### Customer Business")
    _render_customer_business(dashboard)

    st.markdown("### Business Optimization")
    _render_business_optimization(dashboard)

    st.markdown("### Content Opportunity Center")
    _render_content_opportunity_center(dashboard)

    st.markdown("### Business Learning")
    st.caption("Business Learning evidence is consumed through Business Optimization and Creator Agent read models.")

    st.markdown("### Creator Workflow")
    _render_creator_workflow(dashboard.workflow_items)

    st.markdown("### Creator Review")
    _render_creator_review(dashboard.creator_review)

    st.markdown("### Product Review")
    _render_product_review_summary(dashboard.product_review)

    st.markdown("### Experience Overview")
    _render_experience_cards(dashboard.experience_cards)

    st.markdown("### Product Overview")
    _render_product_cards(dashboard.product_cards)

    st.markdown("### Product Business")
    _render_product_business(
        dashboard.product_business_health,
        dashboard.product_business_cards,
    )

    st.markdown("### Publishing Overview")
    _render_publishing_cards(dashboard.publishing_cards)

    st.markdown("### Recent Activity")
    _render_recent_activity(dashboard.activity_feed)

    st.markdown("### Needs Attention")
    _render_notifications(dashboard.notifications)

    st.markdown("### HQ Insights")
    _render_insights(dashboard.insights)
