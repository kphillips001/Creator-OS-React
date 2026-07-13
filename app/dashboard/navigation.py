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
    "System Health",
    "System Overview",
    "Chat Console",
    "Social Studio",
    "Premium Studio",
    "Reference Library",
    "Creative Director",
    "Generation Workspace",
    "Generation Library",
    "Archive",
    "Photoshoot Studio",
    "Photoshoot Gallery",
    "Social Publishing",
    "Caption Studio",
    "Edit Studio",
    "Prompt History",
    "Settings",
    "Mass PPV Dashboard",
    "Wall Scheduler",
    "Activity Feed",
    "Delayed Messages",
    "Creator Profile",
    "Module Switches",
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
        "🏠",
        "Creator Workspace",
    ),
    DashboardNavigationGroup(
        "Assets",
        (
            DashboardNavigationItem("Asset Library", "Asset Library"),
            DashboardNavigationItem("CMS Upload", "CMS Upload"),
        ),
        "🗂️",
    ),
    DashboardNavigationGroup(
        "Content Creation",
        (
            DashboardNavigationItem("Content Studio", "Premium Studio"),
            DashboardNavigationItem("Generation Library", "Generation Library"),
            DashboardNavigationItem("Edit Studio", "Edit Studio"),
            DashboardNavigationItem("📸 Photoshoot Studio", "Photoshoot Studio"),
            DashboardNavigationItem("📸 Photoshoot Gallery", "Photoshoot Gallery"),
            DashboardNavigationItem("Reference Library", "Reference Library"),
            DashboardNavigationItem("Archive", "Archive"),
            DashboardNavigationItem("Diagnostics", "Generation Workspace"),
        ),
        "📸",
    ),
    DashboardNavigationGroup(
        "Experiences",
        (
            DashboardNavigationItem("Experience Overview", None, True),
        ),
        "🎭",
    ),
    DashboardNavigationGroup(
        "Products",
        (
            DashboardNavigationItem("Product Review", "Product Review"),
            DashboardNavigationItem("Product Catalog", "Product Catalog"),
            DashboardNavigationItem("Pricing Playground", "Pricing Playground"),
        ),
        "🛍️",
    ),
    DashboardNavigationGroup(
        "Publishing",
        (
            DashboardNavigationItem("Publishing Queue", "Publishing Queue"),
            DashboardNavigationItem("Wall Publishing Queue", "Wall Scheduler"),
            DashboardNavigationItem("Campaign Publishing", "Mass PPV Dashboard"),
        ),
        "📢",
    ),
    DashboardNavigationGroup(
        "Customer Conversations",
        (
            DashboardNavigationItem("Customer Workspace", "Customer Workspace"),
            DashboardNavigationItem("Chat Console", "Chat Console"),
            DashboardNavigationItem("Relationship Sync", "Relationship Sync"),
        ),
        "💬",
    ),
    DashboardNavigationGroup(
        "Activity",
        (
            DashboardNavigationItem("Activity Feed", "Activity Feed"),
            DashboardNavigationItem("Delayed Messages", "Delayed Messages"),
        ),
        "📈",
    ),
    DashboardNavigationGroup(
        "Notifications",
        (
            DashboardNavigationItem("Notifications", None, True),
        ),
        "🔔",
    ),
    DashboardNavigationGroup(
        "Administration",
        (
            DashboardNavigationItem("System Health", "System Health"),
            DashboardNavigationItem("System Overview", "System Overview"),
            DashboardNavigationItem("Creator Profile", "Creator Profile"),
            DashboardNavigationItem("Module Switches", "Module Switches"),
            DashboardNavigationItem("Runtime Control", "Creator Workspace"),
            DashboardNavigationItem("Provider Connections", "Fanvue Auth"),
        ),
        "⚙️",
    ),
    DashboardNavigationGroup(
        "Agents",
        (
            DashboardNavigationItem("Creator Agent", "Creator Agent"),
            DashboardNavigationItem("Developer Agent", "Developer Agent"),
        ),
        "🤖",
    ),
)

DASHBOARD_PAGE_LABELS = {
    "Creator Workspace": "Creator HQ",
    "Creator Agent": "Agents: Creator Agent",
    "Developer Agent": "Agents: Developer Agent",
    "System Health": "Administration: System Health",
    "System Overview": "Administration: System Overview",
    "Creator Profile": "Administration: Creator Profile",
    "Module Switches": "Administration: Module Switches",
    "Asset Library": "Assets: Asset Library",
    "CMS Upload": "Assets: Ingestion",
    "Social Studio": "Content Creation: Social Studio",
    "Premium Studio": "Content Creation: Content Studio",
    "Reference Library": "Content Creation: Reference Library",
    "Creative Director": "Content Creation: Creative Director",
    "Generation Workspace": "Content Creation: Diagnostics",
    "Generation Library": "Content Creation: Generation Library",
    "Archive": "Content Creation: Archive",
    "Photoshoot Studio": "Content Creation: Photoshoot Studio",
    "Photoshoot Gallery": "Content Creation: Photoshoot Gallery",
    "Social Publishing": "Content Creation: Social Publishing",
    "Caption Studio": "Content Creation: Caption Studio",
    "Edit Studio": "Content Creation: Edit Studio",
    "Prompt History": "Content Creation: Prompt History",
    "Settings": "Content Creation: Settings",
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
    "Social Studio",
    "Premium Studio",
    "Reference Library",
    "Creative Director",
    "Generation Workspace",
    "Generation Library",
    "Archive",
    "Photoshoot Studio",
    "Photoshoot Gallery",
    "Social Publishing",
    "Caption Studio",
    "Edit Studio",
    "Prompt History",
    "Settings",
    "Publishing Queue",
    "Product Review",
    "Product Catalog",
    "Relationship Sync",
]


def normalize_dashboard_page(page: str | None) -> str:
    if page == "Creator HQ":
        return "Creator Workspace"
    if page == "Photoshoot Queue":
        return "Photoshoot Studio"
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
