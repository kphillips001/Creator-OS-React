import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_STATE_FILE = (
    PROJECT_ROOT
    / "data"
    / "config"
    / "dashboard_selected_account.json"
)
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from app.dashboard.config import load_dashboard_config
from app.dashboard.pages.creator_workspace import render_creator_workspace
from app.dashboard.pages.creator_agent import render_creator_agent
from app.dashboard.pages.developer_agent import render_developer_agent
from app.dashboard.pages.customer_workspace import render_customer_workspace
from app.dashboard.pages.system_overview import render_system_overview
from app.dashboard.pages.module_switches import render_module_switches
from app.dashboard.pages.creator_profile import render_creator_profile
from app.dashboard.pages.asset_library import render_asset_library
from app.dashboard.pages.cms_upload import render_cms_upload
from app.dashboard.pages.content_studio import render_content_studio_page
from app.dashboard.pages.relationship_sync import render as render_relationship_sync
from app.dashboard.pages.fanvue_auth import render_fanvue_auth
from app.dashboard.pages.chat_console import render_chat_console
from app.dashboard.pages.mass_ppv_dashboard import (
    render as render_mass_ppv_dashboard,
)
from app.dashboard.pages.wall_scheduler_dashboard import (
    render_wall_scheduler_dashboard,
)
from app.dashboard.pages.delayed_messages_dashboard import (
    render_delayed_messages_dashboard,
)
from app.dashboard.pages.activity_feed import render_activity_feed
from app.dashboard.pages.product_review import render_product_review
from app.dashboard.pages.product_catalog import render_product_catalog
from app.dashboard.pages.publishing_queue import render_publishing_queue
from app.dashboard.pages.pricing_playground import render_pricing_playground
from app.repositories.creator_profile_repository import (
    get_active_creator_profile,
)
from app.repositories.fanvue_account_repository import (
    get_all_accounts,
)
from app.services.local_vault_service import LocalVaultService
from app.dashboard.navigation import (
    DASHBOARD_NAVIGATION_GROUPS,
    DASHBOARD_PAGE_LABELS,
    PROFILE_LOCKED_PAGES,
    normalize_dashboard_page,
)

st.set_page_config(
    page_title="Ava Creator OS",
    page_icon="COS",
    layout="wide",
)
LocalVaultService().initialize()


# ==================================================
# HELPERS
# ==================================================

def _navigation_group_title(group):
    if group.icon:
        return f"{group.icon} {group.label}"
    return group.label


def _render_navigation_button(
    label,
    page,
    *,
    key,
    current_page,
):
    is_active = page == current_page
    button_label = f"* {label}" if is_active else label
    if st.button(
        button_label,
        key=key,
        use_container_width=True,
        disabled=is_active,
    ):
        st.session_state.dashboard_page = page
        st.rerun()


def _render_sidebar_navigation():
    current_page = st.session_state.dashboard_page

    for group_index, group in enumerate(DASHBOARD_NAVIGATION_GROUPS):
        group_title = _navigation_group_title(group)

        if group.page:
            _render_navigation_button(
                group_title,
                group.page,
                key=f"sidebar_nav_group_{group_index}",
                current_page=current_page,
            )
            continue

        expanded = any(
            item.page == current_page
            for item in group.items
            if item.page
        )

        with st.sidebar.expander(group_title, expanded=expanded):
            for item_index, item in enumerate(group.items):
                if item.placeholder or not item.page:
                    st.caption(f"{item.label} (Coming Soon)")
                    continue

                _render_navigation_button(
                    item.label,
                    item.page,
                    key=f"sidebar_nav_{group_index}_{item_index}",
                    current_page=current_page,
                )

def normalize_creator_profiles(
    creator_profile,
):
    """
    Supports both old single-profile format
    and new multi-profile format.
    """

    if isinstance(
        creator_profile,
        list,
    ):
        return [
            profile
            for profile in creator_profile
            if isinstance(profile, dict)
        ]

    if isinstance(
        creator_profile,
        dict,
    ):
        return [
            {
                "fanvue_account_id": (
                    creator_profile.get(
                        "fanvue_account_id",
                        "",
                    )
                ),
                "persona_name": (
                    creator_profile.get(
                        "persona_name"
                    )
                    or creator_profile.get(
                        "name",
                        "",
                    )
                ),
                "display_name": (
                    creator_profile.get(
                        "display_name"
                    )
                    or creator_profile.get(
                        "name",
                        "",
                    )
                ),
                "tone_style": (
                    creator_profile.get(
                        "tone_style"
                    )
                    or creator_profile.get(
                        "tone",
                        "flirty",
                    )
                ),
                "flirt_style": (
                    creator_profile.get(
                        "flirt_style",
                        "",
                    )
                ),
                "emoji_style": (
                    creator_profile.get(
                        "emoji_style",
                        "",
                    )
                ),
                "response_style": (
                    creator_profile.get(
                        "response_style",
                        "",
                    )
                ),
                "pacing_style": (
                    creator_profile.get(
                        "pacing_style",
                        "",
                    )
                ),
                "personality_description": (
                    creator_profile.get(
                        "personality_description",
                        "",
                    )
                ),
                "is_active": (
                    creator_profile.get(
                        "is_active",
                        True,
                    )
                ),
                "last_updated": (
                    creator_profile.get(
                        "last_updated",
                        "",
                    )
                ),
            }
        ]

    return []


def get_account_label(account):
    return (
        account.get("display_name")
        or account.get("account_name")
        or account.get("username")
        or f"Creator Account {account.get('id')}"
    )

# ==================================================
# DASHBOARD ACCOUNT PERSISTENCE
# ==================================================

def load_last_selected_account_id():
    """
    Loads the last selected dashboard account
    from local dashboard state.
    """

    try:

        if not DASHBOARD_STATE_FILE.exists():
            return None

        with open(
            DASHBOARD_STATE_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        return data.get(
            "last_selected_account_id"
        )

    except Exception:
        return None


def save_last_selected_account_id(
    account_id,
):
    """
    Persists last selected dashboard account.
    """

    try:

        DASHBOARD_STATE_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(
            DASHBOARD_STATE_FILE,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                {
                    "last_selected_account_id": (
                        account_id
                    )
                },
                file,
                indent=4,
            )

    except Exception as error:

        print(
            "[DASHBOARD STATE SAVE ERROR]",
            error,
        )

# ==================================================
# LOAD CONFIG
# ==================================================

behavior_config, creator_profile = (
    load_dashboard_config()
)

creator_profiles = normalize_creator_profiles(
    creator_profile,
)

modules = behavior_config.setdefault(
    "modules",
    {},
)

all_fanvue_accounts = (
    get_all_accounts()
)


# ==================================================
# SESSION DEFAULTS
# ==================================================

if "dashboard_page" not in st.session_state:
    st.session_state.dashboard_page = (
        "Creator Workspace"
    )
else:
    st.session_state.dashboard_page = normalize_dashboard_page(
        st.session_state.dashboard_page
    )

if (
    "fanvue_account_id"
    not in st.session_state
):

    if all_fanvue_accounts:

        saved_account_id = (
            load_last_selected_account_id()
        )

        selected_account = None

        # ==========================================
        # 1. LAST SELECTED ACCOUNT
        # ==========================================

        if saved_account_id:

            selected_account = next(
                (
                    account
                    for account
                    in all_fanvue_accounts
                    if account["id"]
                    == saved_account_id
                ),
                None,
            )

        # ==========================================
        # 2. DEFAULT_PERSONA FALLBACK
        # ==========================================

        if not selected_account:

            default_persona = (
                behavior_config.get(
                    "default_persona"
                )
                or "ava"
            ).lower()

            selected_account = next(
                (
                    account
                    for account
                    in all_fanvue_accounts
                    if default_persona
                    in (
                        (
                            account.get(
                                "display_name",
                                ""
                            )
                            or ""
                        ).lower()
                    )
                ),
                None,
            )

        # ==========================================
        # 3. FINAL FALLBACK
        # ==========================================

        if not selected_account:
            selected_account = (
                all_fanvue_accounts[0]
            )

        st.session_state[
            "fanvue_account_id"
        ] = selected_account["id"]

        st.session_state[
            "active_fanvue_account"
        ] = selected_account

        st.session_state[
            "active_persona_name"
        ] = get_account_label(
            selected_account,
        )

# ==================================================
# SIDEBAR
# ==================================================

st.sidebar.title("Navigation")

st.sidebar.subheader(
    "Active Creator Account"
)

if all_fanvue_accounts:

    account_options = {
        get_account_label(account): account
        for account in all_fanvue_accounts
    }

    option_labels = list(
        account_options.keys()
    )

    current_label = next(
        (
            label
            for label, account
            in account_options.items()
            if account["id"]
            == st.session_state.get(
                "fanvue_account_id"
            )
        ),
        option_labels[0],
    )

    selected_label = (
        st.sidebar.selectbox(
            "Account",
            option_labels,
            index=option_labels.index(
                current_label
            ),
            key="active_fanvue_account_select",
        )
    )

    selected_account = (
        account_options[selected_label]
    )

    previous_account_id = (
        st.session_state.get(
            "fanvue_account_id"
        )
    )

    if (
        previous_account_id
        != selected_account["id"]
    ):

        st.session_state[
            "fanvue_account_id"
        ] = selected_account["id"]

        save_last_selected_account_id(
            selected_account["id"]
        )

        st.rerun()

    active_account = next(
        (
            account
            for account
            in all_fanvue_accounts
            if account["id"]
            == st.session_state.get(
                "fanvue_account_id"
            )
        ),
        selected_account,
    )

    st.session_state[
        "active_fanvue_account"
    ] = active_account

    st.session_state[
        "active_persona_name"
    ] = get_account_label(
        active_account,
    )

    st.sidebar.caption(
        f"Selected: "
        f"{st.session_state.get('active_persona_name')}"
    )

    st.sidebar.caption(
        f"Provider Account ID: "
        f"{st.session_state.get('fanvue_account_id')}"
    )

    oauth_connected = bool(
        active_account.get("oauth_access_token")
        or active_account.get("oauth_refresh_token")
        or active_account.get("fanvue_user_uuid")
    )

    if oauth_connected:
        st.sidebar.success(
            "OAuth Connected ✅"
        )
    else:
        st.sidebar.warning(
            "OAuth Not Connected ⚠️"
        )

else:
    st.sidebar.warning(
        "No creator accounts found."
    )

st.sidebar.divider()


# ==================================================
# PAGE NAVIGATION
# ==================================================

page_labels = DASHBOARD_PAGE_LABELS
st.sidebar.markdown("#### Pages")
_render_sidebar_navigation()


# ==================================================
# GLOBAL HEADER
# ==================================================

active_name = (
    st.session_state.get(
        "active_persona_name",
        "Unknown",
    )
)

st.title(
    "Ava Creator OS"
)

st.info(
    f"ACTIVE PROFILE: {active_name}"
)

st.caption(
    f"Current page: "
    f"{page_labels.get(st.session_state.dashboard_page, st.session_state.dashboard_page)}"
)

st.divider()

# ==================================================
# ACTIVE CREATOR PROFILE VALIDATION
# ==================================================

active_creator_profile = (
    get_active_creator_profile(
        st.session_state.get(
            "fanvue_account_id"
        )
    )
)

st.session_state[
    "active_creator_profile"
] = active_creator_profile

if active_creator_profile:

    profile_name = (
        active_creator_profile.get(
            "display_name"
        )
        or active_creator_profile.get(
            "persona_name"
        )
        or "Unknown"
    )

    st.success(
        f"Creator Profile Loaded ✅ "
        f"({profile_name})"
    )

else:

    st.error(
        "Creator Profile Missing ⚠️"
    )

    st.warning(
        "This creator account cannot be used "
        "until a Creator Profile is created."
    )

# ==================================================
# PAGE LOCKS
# ==================================================

blocked_pages = PROFILE_LOCKED_PAGES

if (
    st.session_state.dashboard_page
    in blocked_pages
    and not active_creator_profile
):

    st.error(
        "This page is locked because the "
        "selected account does not have "
        "a Creator Profile configured."
    )

    st.stop()

# ==================================================
# AUTO OAUTH CALLBACK
# ==================================================

if "code" in st.query_params:
    render_fanvue_auth()
    st.stop()


# ==================================================
# PAGE ROUTER
# ==================================================

if (
    st.session_state.dashboard_page
    == "Creator Workspace"
):
    render_creator_workspace(
        creator_profile=active_creator_profile or {},
        active_account=st.session_state.get("active_fanvue_account", {}),
    )

elif (
    st.session_state.dashboard_page
    == "Creator Agent"
):
    render_creator_agent(
        creator_profile=active_creator_profile or {},
        active_account=st.session_state.get("active_fanvue_account", {}),
    )

elif (
    st.session_state.dashboard_page
    == "Developer Agent"
):
    render_developer_agent(
        active_account=st.session_state.get("active_fanvue_account", {}),
    )

elif (
    st.session_state.dashboard_page
    == "Customer Workspace"
):
    render_customer_workspace()

elif (
    st.session_state.dashboard_page
    == "System Overview"
):
    render_system_overview(
        behavior_config,
    )

elif (
    st.session_state.dashboard_page
    == "Chat Console"
):
    render_chat_console()

elif (
    st.session_state.dashboard_page
    == "Mass PPV Dashboard"
):
    render_mass_ppv_dashboard()

elif (
    st.session_state.dashboard_page
    == "Wall Scheduler"
):
    render_wall_scheduler_dashboard()

elif (
    st.session_state.dashboard_page
    == "Publishing Queue"
):
    render_publishing_queue(
        active_account=st.session_state.get("active_fanvue_account", {}),
        creator_profile=active_creator_profile or {},
    )

elif (
    st.session_state.dashboard_page
    == "Activity Feed"
):
    render_activity_feed(
        creator_profile=active_creator_profile or {},
        active_account=st.session_state.get("active_fanvue_account", {}),
    )

elif (
    st.session_state.dashboard_page
    == "Delayed Messages"
):
    render_delayed_messages_dashboard()

elif (
    st.session_state.dashboard_page
    == "Module Switches"
):
    render_module_switches(
        behavior_config,
        modules,
    )

elif (
    st.session_state.dashboard_page
    == "Creator Profile"
):

    fanvue_account_id = (
        st.session_state.get(
            "fanvue_account_id"
        )
    )

    creator_profile = {}

    if fanvue_account_id:

        creator_profile = (
            get_active_creator_profile(
                fanvue_account_id,
            )
            or {}
        )

        creator_profile[
            "fanvue_account_id"
        ] = fanvue_account_id

    render_creator_profile(
        creator_profile,
    )

elif (
    st.session_state.dashboard_page
    == "Asset Library"
):
    render_asset_library()

elif (
    st.session_state.dashboard_page
    == "CMS Upload"
):
    render_cms_upload()

elif (
    st.session_state.dashboard_page
    in {
        "Social Studio",
        "Premium Studio",
        "Reference Library",
        "Creative Director",
        "Generation Workspace",
        "Generation Library",
        "Photoshoot Queue",
        "Social Publishing",
        "Caption Studio",
        "Edit Studio",
        "Prompt History",
        "Settings",
    }
):
    render_content_studio_page(
        st.session_state.dashboard_page,
        creator_profile=active_creator_profile or {},
        active_account=st.session_state.get("active_fanvue_account", {}),
    )

elif (
    st.session_state.dashboard_page
    == "Product Review"
):
    render_product_review(
        creator_profile=active_creator_profile or {},
    )

elif (
    st.session_state.dashboard_page
    == "Product Catalog"
):
    render_product_catalog(
        fanvue_account_id=st.session_state.get("fanvue_account_id"),
        creator_profile=active_creator_profile or {},
    )

elif (
    st.session_state.dashboard_page
    == "Pricing Playground"
):
    render_pricing_playground()

elif (
    st.session_state.dashboard_page
    == "Relationship Sync"
):
    render_relationship_sync()

elif (
    st.session_state.dashboard_page
    == "Fanvue Auth"
):
    render_fanvue_auth()

else:
    st.error(
        "Unknown dashboard page selected."
    )
