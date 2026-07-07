import streamlit as st

from app.dashboard.config import (
    save_behavior_config,
)


def render_system_overview(
    behavior_config,
):

    active_account = (
        st.session_state.get(
            "active_fanvue_account",
            {}
        )
    )

    st.subheader("Behavior Config")

    st.info(
        f"Currently viewing dashboard as: "
        f"{active_account.get('display_name') or active_account.get('username')}"
    )

    bot_enabled = st.toggle(
        "Bot Enabled",
        value=behavior_config.get(
            "bot_enabled",
            False,
        ),
    )

    manual_pause_enabled = st.toggle(
        "Manual Pause / Human Takeover",
        value=behavior_config.get(
            "manual_pause_enabled",
            False,
        ),
    )

    dark_mode_enabled = st.toggle(
        "Dashboard Dark Mode Preference",
        value=(
            behavior_config.get(
                "dashboard_theme"
            )
            == "dark"
        ),
    )

    new_theme = (
        "dark"
        if dark_mode_enabled
        else "light"
    )

    config_changed = False

    if (
        bot_enabled
        != behavior_config.get(
            "bot_enabled"
        )
    ):
        behavior_config[
            "bot_enabled"
        ] = bot_enabled

        config_changed = True

    if (
        manual_pause_enabled
        != behavior_config.get(
            "manual_pause_enabled"
        )
    ):
        behavior_config[
            "manual_pause_enabled"
        ] = manual_pause_enabled

        config_changed = True

    if (
        new_theme
        != behavior_config.get(
            "dashboard_theme"
        )
    ):
        behavior_config[
            "dashboard_theme"
        ] = new_theme

        config_changed = True

    if config_changed:

        save_behavior_config(
            behavior_config
        )

        st.success(
            "Behavior config updated!"
        )

    st.divider()

    st.markdown(
        "### Current Configuration"
    )

    st.json(
        behavior_config
    )