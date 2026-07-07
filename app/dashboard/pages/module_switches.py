import streamlit as st

from app.dashboard.config import save_behavior_config


def render_module_switches(behavior_config, modules):
    st.subheader("CMS / Local Module Switches")

    cms_upload_enabled = st.toggle(
        "Asset Ingestion Enabled",
        value=modules.get("cms_upload_enabled", True),
    )

    classification_enabled = st.toggle(
        "Classification Enabled",
        value=modules.get("classification_enabled", True),
    )

    tag_editing_enabled = st.toggle(
        "Tag Editing Enabled",
        value=modules.get("tag_editing_enabled", True),
    )

    fanvue_vault_upload_enabled = st.toggle(
        "Provider Vault Upload Enabled",
        value=modules.get("fanvue_vault_upload_enabled", False),
    )

    st.divider()

    st.subheader("🔒 Global Safety Controls")

    global_automation_enabled = st.toggle(
        "Global Automation Enabled",
        value=behavior_config.get(
            "global_automation_enabled",
            False,
        ),
        help=(
            "MASTER switch. If OFF, all outbound automation is blocked, "
            "even if individual module switches are enabled."
        ),
    )

    global_sends_enabled = st.toggle(
        "Global Live Sends Enabled",
        value=behavior_config.get(
            "global_sends_enabled",
            False,
        ),
        help=(
            "If OFF, no live provider sends are allowed. "
            "Server, webhooks, DB updates, and testing can still run."
        ),
    )

    manual_pause_enabled = st.toggle(
        "Manual Pause Enabled",
        value=behavior_config.get(
            "manual_pause_enabled",
            False,
        ),
        help=(
            "Emergency pause. If ON, all outbound automation is blocked."
        ),
    )

    if not global_automation_enabled:
        st.warning(
            "Global Automation is OFF. All outbound automation is blocked."
        )

    if not global_sends_enabled:
        st.warning(
            "Global Live Sends are OFF. No live provider messages, PPVs, "
            "reactions, outreach, or broadcasts can be sent."
        )

    if manual_pause_enabled:
        st.error(
            "Manual Pause is ON. All outbound automation is blocked."
        )

    st.divider()

    st.subheader("Live Bot Module Switches")

    main_chat_enabled = st.toggle(
        "Main Chat Enabled",
        value=modules.get("main_chat_enabled", False),
        disabled=not global_automation_enabled,
        help="Controls realtime chat automation.",
    )

    outreach_enabled = st.toggle(
        "Outreach Enabled",
        value=modules.get("outreach_enabled", False),
        disabled=not global_automation_enabled,
        help="Controls outbound outreach automation.",
    )

    ppv_offers_enabled = st.toggle(
        "PPV Offers Enabled",
        value=modules.get("ppv_offers_enabled", False),
        disabled=not global_automation_enabled,
        help="Controls one-on-one PPV offer automation.",
    )

    mass_ppv_enabled = st.toggle(
        "Mass PPV Enabled",
        value=modules.get("mass_ppv_enabled", False),
        disabled=not global_automation_enabled,
        help=(
            "Controls automated Mass PPV campaigns. "
            "Global Safety Controls still override this."
        ),
    )

    col1, col2 = st.columns([5, 2])

    with col1:
        reactivation_enabled = st.toggle(
            "Reactivation Enabled",
            value=modules.get("reactivation_enabled", False),
            disabled=not global_automation_enabled,
            help="Controls reactivation automation.",
        )

    post_purchase_reactions_enabled = st.toggle(
        "Post-Purchase Reactions Enabled",
        value=modules.get(
            "post_purchase_reactions_enabled",
            False,
        ),
        disabled=not global_automation_enabled,
        help=(
            "Controls automated thank-you, tip reward, subscriber welcome, "
            "premium followup, and whale retention reactions."
        ),
    )

    col1, col2 = st.columns([5, 2])

    with col1:
        delayed_followups_enabled = st.toggle(
            "Delayed Followups Enabled",
            value=modules.get(
                "delayed_followups_enabled",
                False,
            ),
            disabled=not global_automation_enabled,
            help="Controls delayed monetization followup automation.",
        )

    config_changed = False

    root_updates = {
        "global_automation_enabled": global_automation_enabled,
        "global_sends_enabled": global_sends_enabled,
        "manual_pause_enabled": manual_pause_enabled,
    }

    module_updates = {
        "cms_upload_enabled": cms_upload_enabled,
        "classification_enabled": classification_enabled,
        "tag_editing_enabled": tag_editing_enabled,
        "fanvue_vault_upload_enabled": fanvue_vault_upload_enabled,
        "main_chat_enabled": main_chat_enabled,
        "outreach_enabled": outreach_enabled,
        "ppv_offers_enabled": ppv_offers_enabled,
        "mass_ppv_enabled": mass_ppv_enabled,
        "reactivation_enabled": reactivation_enabled,
        "post_purchase_reactions_enabled": (
            post_purchase_reactions_enabled
        ),
        "delayed_followups_enabled": delayed_followups_enabled,
    }

    for key, value in root_updates.items():
        if behavior_config.get(key) != value:
            behavior_config[key] = value
            config_changed = True

    for key, value in module_updates.items():
        if modules.get(key) != value:
            modules[key] = value
            config_changed = True

    if config_changed:
        save_behavior_config(behavior_config)
        st.success("Module settings updated!")

    st.json(behavior_config)
