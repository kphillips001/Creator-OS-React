"""Dashboard route definitions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardNavigationItem:
    label: str
    page: str | None = None
    placeholder: bool = False


@dataclass(frozen=True)
class DashboardNavigationGroup:
    label: str
    items: tuple[DashboardNavigationItem, ...]
    icon: str = ""
    page: str | None = None


DASHBOARD_PAGE_OPTIONS = [
    "Creator Workspace",
    "Creator Agent",
    "Developer Agent",
    "System Overview",
    "Chat Console",
    "Mass PPV Dashboard",
    "Wall Scheduler",
    "Activity Feed",
    "Delayed Messages",
    "Creator Profile",
    "Customer Workspace",
    "Asset Library",
    "CMS Upload",
    "Publishing Queue",
    "Product Review",
    "Product Catalog",
    "Pricing Playground",
    "Relationship Sync",
    "Fanvue Auth",
]

DASHBOARD_NAVIGATION_GROUPS = (
    DashboardNavigationGroup(
        "Creator HQ",
        (),
        "HQ",
        "Creator Workspace",
    ),
    DashboardNavigationGroup(
        "AI",
        (
            DashboardNavigationItem("Creator Agent", "Creator Agent"),
            DashboardNavigationItem("Developer Agent", "Developer Agent"),
        ),
        "AI",
    ),
    DashboardNavigationGroup(
        "Assets",
        (
            DashboardNavigationItem("Asset Library", "Asset Library"),
            DashboardNavigationItem("CMS Upload", "CMS Upload"),
        ),
        "AS",
    ),
    DashboardNavigationGroup(
        "Experiences",
        (
            DashboardNavigationItem("Experience Overview", None, True),
        ),
        "EX",
    ),
    DashboardNavigationGroup(
        "Products",
        (
            DashboardNavigationItem("Product Review", "Product Review"),
            DashboardNavigationItem("Product Catalog", "Product Catalog"),
            DashboardNavigationItem("Pricing Playground", "Pricing Playground"),
        ),
        "PR",
    ),
    DashboardNavigationGroup(
        "Publishing",
        (
            DashboardNavigationItem("Publishing Queue", "Publishing Queue"),
            DashboardNavigationItem("Wall Publishing Queue", "Wall Scheduler"),
            DashboardNavigationItem("Campaign Publishing", "Mass PPV Dashboard"),
        ),
        "PB",
    ),
    DashboardNavigationGroup(
        "Customer Conversations",
        (
            DashboardNavigationItem("Customer Workspace", "Customer Workspace"),
            DashboardNavigationItem("Chat Console", "Chat Console"),
            DashboardNavigationItem("Relationship Sync", "Relationship Sync"),
        ),
        "CC",
    ),
    DashboardNavigationGroup(
        "Activity",
        (
            DashboardNavigationItem("Activity Feed", "Activity Feed"),
            DashboardNavigationItem("Delayed Messages", "Delayed Messages"),
        ),
        "AC",
    ),
    DashboardNavigationGroup(
        "Notifications",
        (
            DashboardNavigationItem("Notifications", None, True),
        ),
        "NO",
    ),
    DashboardNavigationGroup(
        "Administration",
        (
            DashboardNavigationItem("System Overview", "System Overview"),
            DashboardNavigationItem("Creator Profile", "Creator Profile"),
            DashboardNavigationItem("Runtime Control", "Creator Workspace"),
            DashboardNavigationItem("Provider Connections", "Fanvue Auth"),
        ),
        "AD",
    ),
)

DASHBOARD_PAGE_LABELS = {
    "Creator Workspace": "Creator HQ",
    "Creator Agent": "AI: Creator Agent",
    "Developer Agent": "AI: Developer Agent",
    "System Overview": "Administration: System Overview",
    "Creator Profile": "Administration: Creator Profile",
    "Asset Library": "Assets: Asset Library",
    "CMS Upload": "Assets: Ingestion",
    "Publishing Queue": "Publishing: Queue",
    "Product Review": "Products: Product Review",
    "Product Catalog": "Products: Catalog",
    "Pricing Playground": "Products: Pricing Playground",
    "Customer Workspace": "Customer Conversations: Customer Workspace",
    "Wall Scheduler": "Publishing: Wall Publishing Queue",
    "Mass PPV Dashboard": "Publishing: Campaign Publishing",
    "Chat Console": "Customer Conversations: Chat Console",
    "Relationship Sync": "Customer Conversations: Relationship Sync",
    "Activity Feed": "Activity: Activity Feed",
    "Delayed Messages": "Activity: Delayed Messages",
    "Fanvue Auth": "Administration: Provider Connections",
}

PROFILE_LOCKED_PAGES = [
    "Creator Agent",
    "Developer Agent",
    "Chat Console",
    "Mass PPV Dashboard",
    "Wall Scheduler",
    "Delayed Messages",
    "Customer Workspace",
    "Asset Library",
    "CMS Upload",
    "Publishing Queue",
    "Product Review",
    "Product Catalog",
    "Relationship Sync",
]


def normalize_dashboard_page(page: str | None) -> str:
    if page == "Creator HQ":
        return "Creator Workspace"
    if page in DASHBOARD_PAGE_OPTIONS:
        return page
    return "Creator Workspace"


def grouped_navigation_options() -> list[tuple[str, str | None]]:
    options: list[tuple[str, str | None]] = []
    for group in DASHBOARD_NAVIGATION_GROUPS:
        options.append((group.label, group.page))
        for item in group.items:
            suffix = " (Coming Soon)" if item.placeholder else ""
            options.append((f"  {item.label}{suffix}", item.page))
    return options


def grouped_navigation_labels() -> list[str]:
    return [label for label, _ in grouped_navigation_options()]


def page_for_grouped_navigation_label(label: str) -> str | None:
    return dict(grouped_navigation_options()).get(label)


def grouped_navigation_label_for_page(page: str) -> str:
    for label, target in grouped_navigation_options():
        if target == page:
            return label
    return "Creator HQ"
