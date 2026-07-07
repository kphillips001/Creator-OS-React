"""Deprecated legacy Streamlit dashboard.

The active Creator OS dashboard entry point is app/dashboard/main.py. This
file is retained only for historical compatibility and should not receive new
navigation or Workspace behavior.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import streamlit as st

# ✅ Fix import path so Streamlit can find "app"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from app.services.ai_import_workflow_service import AIImportWorkflowService
from app.dashboard.pages.chat_console import render_chat_console
from app.services.runtime_media_resolver import RuntimeMediaResolver


CONFIG_PATH = Path("data/config/behavior_config.json")
CREATOR_PATH = Path("data/config/creator_profile.json")
_RUNTIME_MEDIA_RESOLVER = RuntimeMediaResolver()
_AI_IMPORT_WORKFLOW = AIImportWorkflowService()


st.set_page_config(
    page_title="Fanvue Chatbot Dashboard",
    page_icon="💬",
    layout="wide",
)

st.title("Fanvue Chatbot Control Dashboard 💬")
st.write("Dashboard loaded successfully.")

# =========================
# SIDEBAR NAVIGATION
# =========================

st.sidebar.title("Navigation")

page = st.sidebar.radio(
    "Go to",
    [
        "System Overview",
        "Chat Console",
        "Module Switches",
        "Creator Profile",
        "CMS Upload",
    ],
)

# =========================
# LOAD CONFIG
# =========================

with CONFIG_PATH.open("r", encoding="utf-8") as file:
    behavior_config = json.load(file)

with CREATOR_PATH.open("r", encoding="utf-8") as file:
    creator_profile = json.load(file)

# Ensure keys exist
behavior_config.setdefault("bot_enabled", False)
behavior_config.setdefault("dashboard_theme", "light")
behavior_config.setdefault("manual_pause_enabled", False)

modules = behavior_config.setdefault("modules", {})

creator_profile.setdefault("name", "")
creator_profile.setdefault("tone", "flirty")

# =========================
# PAGE: SYSTEM OVERVIEW
# =========================

if page == "System Overview":

    st.subheader("Behavior Config")

    bot_enabled = st.toggle(
        "Bot Enabled",
        value=behavior_config.get("bot_enabled", False),
    )

    manual_pause_enabled = st.toggle(
        "Manual Pause / Human Takeover",
        value=behavior_config.get("manual_pause_enabled", False),
    )

    dark_mode_enabled = st.toggle(
        "Dashboard Dark Mode Preference",
        value=behavior_config.get("dashboard_theme") == "dark",
    )

    new_theme = "dark" if dark_mode_enabled else "light"

    config_changed = False

    if bot_enabled != behavior_config.get("bot_enabled"):
        behavior_config["bot_enabled"] = bot_enabled
        config_changed = True

    if manual_pause_enabled != behavior_config.get("manual_pause_enabled"):
        behavior_config["manual_pause_enabled"] = manual_pause_enabled
        config_changed = True

    if new_theme != behavior_config.get("dashboard_theme"):
        behavior_config["dashboard_theme"] = new_theme
        config_changed = True

    if config_changed:
        with CONFIG_PATH.open("w", encoding="utf-8") as file:
            json.dump(behavior_config, file, indent=2)

        st.success("Behavior config updated!")

    st.json(behavior_config)

# =========================
# PAGE: CHAT CONSOLE
# =========================

elif page == "Chat Console":
    render_chat_console()

# =========================
# PAGE: MODULE SWITCHES
# =========================

elif page == "Module Switches":

    st.subheader("CMS / Local Module Switches")

    cms_upload_enabled = st.toggle(
        "CMS Upload Enabled",
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
    st.subheader("Live Bot Module Switches")

    main_chat_enabled = st.toggle(
        "Main Chat Enabled",
        value=modules.get("main_chat_enabled", False),
    )

    outreach_enabled = st.toggle(
        "Outreach Enabled",
        value=modules.get("outreach_enabled", False),
    )

    ppv_offers_enabled = st.toggle(
        "PPV Offers Enabled",
        value=modules.get("ppv_offers_enabled", False),
    )

    reactivation_enabled = st.toggle(
        "Reactivation Enabled",
        value=modules.get("reactivation_enabled", False),
    )

    config_changed = False

    module_updates = {
        "cms_upload_enabled": cms_upload_enabled,
        "classification_enabled": classification_enabled,
        "tag_editing_enabled": tag_editing_enabled,
        "fanvue_vault_upload_enabled": fanvue_vault_upload_enabled,
        "main_chat_enabled": main_chat_enabled,
        "outreach_enabled": outreach_enabled,
        "ppv_offers_enabled": ppv_offers_enabled,
        "reactivation_enabled": reactivation_enabled,
    }

    for key, value in module_updates.items():
        if modules.get(key) != value:
            modules[key] = value
            config_changed = True

    if config_changed:
        with CONFIG_PATH.open("w", encoding="utf-8") as file:
            json.dump(behavior_config, file, indent=2)

        st.success("Module settings updated!")

    st.json(behavior_config)

# =========================
# PAGE: CREATOR PROFILE
# =========================

elif page == "Creator Profile":

    st.subheader("Creator Profile")

    profile_changed = False

    name = st.text_input(
        "Creator Name",
        value=creator_profile.get("name", ""),
    )

    tone = st.text_input(
        "Creator Tone",
        value=creator_profile.get("tone", "flirty"),
    )

    if name != creator_profile.get("name"):
        creator_profile["name"] = name
        profile_changed = True

    if tone != creator_profile.get("tone"):
        creator_profile["tone"] = tone
        profile_changed = True

    if profile_changed:
        with CREATOR_PATH.open("w", encoding="utf-8") as file:
            json.dump(creator_profile, file, indent=2)

        st.success("Creator profile updated!")

    st.json(creator_profile)

# =========================
# PAGE: CMS UPLOAD
# =========================

elif page == "CMS Upload":

    st.subheader("CMS Upload")

    st.info("Upload images/videos to begin classification pipeline.")

    uploaded_files = st.file_uploader(
        "Upload Content",
        type=["jpg", "jpeg", "png", "webp", "mp4", "mov", "webm"],
        accept_multiple_files=True,
    )

    UPLOAD_DIR = Path("data/uploads")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if uploaded_files:
        image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
        video_extensions = {".mp4", ".mov", ".webm"}

        saved_files = []

        for uploaded_file in uploaded_files:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{timestamp}_{uploaded_file.name}"

            file_path = UPLOAD_DIR / filename

            file_extension = file_path.suffix.lower()

            if file_extension in image_extensions:
                media_type = "image"
            elif file_extension in video_extensions:
                media_type = "video"
            else:
                media_type = "unknown"

            # Save file
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            # 🔥 Classification (images only)
            classification_result = None

            if media_type == "image":
                try:
                    classification_result = _AI_IMPORT_WORKFLOW.import_asset(
                        media_path=file_path,
                        upload_intent="ppv_image",
                        creator_profile_id=None,
                        create_product_draft=True,
                        provider_upload_enabled=True,
                        is_test=True,
                    ).to_legacy_result()
                except Exception as e:
                    st.error(f"Classification failed for {filename}: {e}")

            saved_files.append((filename, media_type, classification_result))

        # Summary UI
        st.success(f"{len(saved_files)} file(s) processed successfully!")

        for fname, mtype, result in saved_files:
            if result:
                st.write(
                    f"• {fname} → `{mtype}` → `{result.get('final_classification')}`"
                )
            else:
                st.write(f"• {fname} → `{mtype}` → not classified yet")

# =========================
# PAGE: APPROVAL QUEUE
# =========================

elif False and page == "Approval Queue":

    st.subheader("Approval Queue")

    from app.database import get_db_connection
    import time

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    SELECT
                        id,
                        file_name,
                        file_path,
                        local_vault_path,
                        media_metadata,
                        classification,
                        confidence,
                        detected_themes,
                        suggested_tags,
                        nudity_labels,
                        nudity_level,
                        sexual_intensity,
                        is_explicit,
                        created_at
                    FROM content_items
                    WHERE status = 'pending'
                    ORDER BY created_at DESC
                    LIMIT 25
                """)

                rows = cur.fetchall()

        if not rows:
            st.info("No pending classified content found.")
        else:
            st.success(f"{len(rows)} pending content item(s) found.")

            for row in rows:
                st.divider()

                content_id = row["id"]
                file_name = row["file_name"]
                file_path = row["file_path"]
                runtime_media_path = (
                    _RUNTIME_MEDIA_RESOLVER.resolve_original_path_string(
                        row,
                        require_exists=True,
                    )
                    or file_path
                )
                classification = row["classification"]
                confidence = row["confidence"]
                detected_themes = row["detected_themes"]
                suggested_tags = row["suggested_tags"]
                nudity_labels = row["nudity_labels"]
                nudity_level = row["nudity_level"]
                sexual_intensity = row["sexual_intensity"]
                is_explicit = row["is_explicit"]
                created_at = row["created_at"]

                ext = Path(runtime_media_path).suffix.lower()
                if ext in {".jpg", ".jpeg", ".png", ".webp"}:
                    media_type = "image"
                elif ext in {".mp4", ".mov", ".webm"}:
                    media_type = "video"
                else:
                    media_type = "unknown"

                col1, col2 = st.columns([1, 2])

                with col1:
                    if Path(runtime_media_path).exists():
                        if media_type == "image":
                            st.image(
                                runtime_media_path,
                                caption=file_name,
                                use_container_width=True,
                            )
                        elif media_type == "video":
                            st.video(runtime_media_path)
                        else:
                            st.warning("No preview available")
                    else:
                        st.error("File not found")

                with col2:
                    st.write(f"**ID:** {content_id}")
                    st.write(f"**Media Type:** `{media_type}`")

                    classification_options = ["TEASE", "VIP", "PREMIUM"]

                    if classification in classification_options:
                        classification_index = classification_options.index(classification)
                    else:
                        classification_index = 0

                    edited_classification = st.selectbox(
                        "Classification Override",
                        classification_options,
                        index=classification_index,
                        key=f"classification_{content_id}",
                    )

                    if edited_classification != classification:
                        _ASSET_LIFECYCLE_SERVICE.update_classification(
                            asset_id=content_id,
                            classification=edited_classification,
                        )

                        st.toast(
                            f"Updated to {edited_classification} ✅",
                            icon="✅",
                        )

                        time.sleep(1)
                        st.rerun()

                    st.write(f"**Confidence:** `{confidence}`")

                    current_themes = detected_themes or []

                    if isinstance(current_themes, str):
                        current_themes_text = current_themes
                    else:
                        current_themes_text = ", ".join(current_themes)

                    edited_themes_text = st.text_input(
                        "Edit Detected Themes",
                        value=current_themes_text,
                        key=f"edit_themes_{content_id}",
                    )

                    st.write(f"**Original Detected Themes:** {detected_themes}")

                    current_tags = suggested_tags or []

                    if isinstance(current_tags, str):
                        current_tags_text = current_tags
                    else:
                        current_tags_text = ", ".join(current_tags)

                    edited_tags_text = st.text_input(
                        "Edit Suggested Tags",
                        value=current_tags_text,
                        key=f"edit_tags_{content_id}",
                    )

                    st.write(f"**Original Suggested Tags:** {suggested_tags}")
                    st.write(f"**Nudity Labels:** {nudity_labels}")
                    st.write(f"**Nudity Level:** `{nudity_level}`")
                    st.write(f"**Sexual Intensity:** `{sexual_intensity}`")
                    st.write(f"**Explicit:** `{is_explicit}`")
                    st.write(f"**Created At:** `{created_at}`")

                    action_col1, action_col2, action_col3 = st.columns(3)

                    with action_col1:
                        if st.button("✅ Approve", key=f"approve_{content_id}"):

                            updated_tags = [
                                tag.strip()
                                for tag in edited_tags_text.split(",")
                                if tag.strip()
                            ]

                            updated_themes = [
                                theme.strip()
                                for theme in edited_themes_text.split(",")
                                if theme.strip()
                            ]

                            _ASSET_LIFECYCLE_SERVICE.approve_review_only(
                                asset_id=content_id,
                                suggested_tags=updated_tags,
                                detected_themes=updated_themes,
                                classification=edited_classification,
                            )

                            st.toast(
                                f"Content ID {content_id} saved and approved ✅",
                                icon="✅",
                            )

                            time.sleep(1)
                            st.rerun()

                    with action_col2:
                        if st.button("❌ Reject", key=f"reject_{content_id}"):
                            _ASSET_LIFECYCLE_SERVICE.reject_asset(
                                asset_id=content_id,
                            )

                            st.toast(
                                f"Content ID {content_id} rejected ❌",
                                icon="❌",
                            )

                            time.sleep(1)
                            st.rerun()

                    with action_col3:
                        if st.button("💾 Save Edits", key=f"save_edits_{content_id}"):

                            updated_tags = [
                                tag.strip()
                                for tag in edited_tags_text.split(",")
                                if tag.strip()
                            ]

                            updated_themes = [
                                theme.strip()
                                for theme in edited_themes_text.split(",")
                                if theme.strip()
                            ]

                            _ASSET_LIFECYCLE_SERVICE.save_review_edits(
                                asset_id=content_id,
                                suggested_tags=updated_tags,
                                detected_themes=updated_themes,
                                classification=edited_classification,
                            )

                            st.toast(
                                f"Saved edits for content ID {content_id} ✅",
                                icon="✅",
                            )

                            time.sleep(1)
                            st.rerun()

    except Exception as e:
        st.error(f"Approval Queue failed to load: {e}")
