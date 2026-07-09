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
    "Social Studio",
    "Premium Studio",
    "Reference Library",
    "Creative Director",
    "Generation Workspace",
    "Generation Library",
    "Archive",
    "Photoshoot Queue",
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
        "HQ",
        "Creator Workspace",
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
        "Content Studio",
        (
            DashboardNavigationItem("Social Studio", "Social Studio"),
            DashboardNavigationItem("Premium Studio", "Premium Studio"),
            DashboardNavigationItem("Reference Library", "Reference Library"),
            DashboardNavigationItem("Creative Director", "Creative Director"),
            DashboardNavigationItem("Generation Workspace", "Generation Workspace"),
            DashboardNavigationItem("Generation Library", "Generation Library"),
            DashboardNavigationItem("Archive", "Archive"),
            DashboardNavigationItem("Photoshoot Queue", "Photoshoot Queue"),
            DashboardNavigationItem("Social Publishing", "Social Publishing"),
            DashboardNavigationItem("Caption Studio", "Caption Studio"),
            DashboardNavigationItem("Edit Studio", "Edit Studio"),
            DashboardNavigationItem("Prompt History", "Prompt History"),
            DashboardNavigationItem("Settings", "Settings"),
        ),
        "CS",
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
            DashboardNavigationItem("Module Switches", "Module Switches"),
            DashboardNavigationItem("Runtime Control", "Creator Workspace"),
            DashboardNavigationItem("Provider Connections", "Fanvue Auth"),
        ),
        "AD",
    ),
    DashboardNavigationGroup(
        "Agents",
        (
            DashboardNavigationItem("Creator Agent", "Creator Agent"),
            DashboardNavigationItem("Developer Agent", "Developer Agent"),
        ),
        "AG",
    ),
)

DASHBOARD_PAGE_LABELS = {
    "Creator Workspace": "Creator HQ",
    "Creator Agent": "Agents: Creator Agent",
    "Developer Agent": "Agents: Developer Agent",
    "System Overview": "Administration: System Overview",
    "Creator Profile": "Administration: Creator Profile",
    "Module Switches": "Administration: Module Switches",
    "Asset Library": "Assets: Asset Library",
    "CMS Upload": "Assets: Ingestion",
    "Social Studio": "Content Studio: Social Studio",
    "Premium Studio": "Content Studio: Premium Studio",
    "Reference Library": "Content Studio: Reference Library",
    "Creative Director": "Content Studio: Creative Director",
    "Generation Workspace": "Content Studio: Generation Workspace",
    "Generation Library": "Content Studio: Generation Library",
    "Archive": "Content Studio: Archive",
    "Photoshoot Queue": "Content Studio: Photoshoot Queue",
    "Social Publishing": "Content Studio: Social Publishing",
    "Caption Studio": "Content Studio: Caption Studio",
    "Edit Studio": "Content Studio: Edit Studio",
    "Prompt History": "Content Studio: Prompt History",
    "Settings": "Content Studio: Settings",
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
    "Photoshoot Queue",
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
