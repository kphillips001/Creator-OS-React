import json

import streamlit as st
from datetime import datetime

from app.repositories.creator_profile_repository import upsert_creator_profile


PROFILE_TEXT_SECTIONS = {
    "Identity": [
        "id",
        "fanvue_account_id",
        "persona_name",
        "display_name",
        "gender",
        "is_active",
        "created_at",
        "updated_at",
        "last_updated",
    ],
    "Core Personality": [
        "archetype",
        "personality_description",
        "backstory",
    ],
    "Lifestyle / Age / Location / Occupation Context": [
        "age",
        "location",
        "lifestyle_context",
        "lifestyle_vibe",
        "daily_routine",
        "hobbies",
        "occupation",
        "occupation_context",
    ],
    "Attraction Psychology": [
        "likes",
        "dislikes",
        "ideal_user_type",
        "turn_ons",
        "turn_offs",
    ],
    "Sexual Personality": [
        "sexual_style",
        "sexual_likes",
        "sexual_dislikes",
        "kinks",
        "fantasy_style",
    ],
    "Flirting & Behavior": [
        "tone_style",
        "flirt_style",
        "tease_intensity",
        "push_pull_style",
        "mystery_level",
    ],
    "Chat Behavior": [
        "response_style",
        "pacing_style",
        "question_frequency",
        "emotional_depth",
        "affection_style",
        "jealousy_style",
        "availability_style",
    ],
    "Advanced Behavior": [
        "conversation_hooks",
        "retention_hooks",
        "escalation_style",
        "escalation_triggers",
        "self_value_style",
        "persona_intensity",
    ],
    "Boundaries": [
        "boundaries",
        "sexual_boundaries",
        "hard_limits",
        "response_rules",
    ],
}


def _format_profile_text_value(value):
    if value is None:
        return "NULL"
    if value == "":
        return '""'
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, ensure_ascii=False, default=str)
    return str(value)


def _build_profile_text(profile):
    sections = {
        title: [field for field in fields if field in profile]
        for title, fields in PROFILE_TEXT_SECTIONS.items()
    }
    grouped_fields = {
        field
        for fields in sections.values()
        for field in fields
    }

    # Preserve unexpected fields without introducing an ungrouped section.
    sections["Identity"].extend(
        field for field in profile if field not in grouped_fields
    )

    lines = []
    for section_title, fields in sections.items():
        lines.append(section_title)
        lines.append("=" * len(section_title))

        if not fields:
            lines.append("(No fields loaded)")
        else:
            for field in fields:
                label = field.replace("_", " ").title()
                lines.append(f"{label}: {_format_profile_text_value(profile[field])}")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _get_profile(creator_profile):
    if isinstance(creator_profile, dict):
        return creator_profile
    return {}


def _selectbox_with_saved(label, options, saved_value, default_index=0, disabled=False):
    index = options.index(saved_value) if saved_value in options else default_index
    return st.selectbox(label, options, index=index, disabled=disabled)


def _get_fanvue_account_id(profile):
    """
    Fanvue account should come from OAuth/session/profile.
    It should NOT be manually entered in Creator Profile UI.
    """

    return (
        profile.get("fanvue_account_id")
        or st.session_state.get("fanvue_account_id")
        or st.session_state.get("connected_fanvue_account_id")
    )


def render_creator_profile(creator_profile):
    st.subheader("Creator Profile")

    st.caption(
        "Define who this creator is: identity, personality, lifestyle, attraction style, and boundaries."
    )

    profile = _get_profile(creator_profile)
    has_saved_profile = bool(profile.get("persona_name"))

    if st.button("📤 Export Current Profile JSON"):
        profile_json = json.dumps(
            profile,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        profile_text = _build_profile_text(profile)

        st.markdown("### ava_blackthorne_profile_backup.json")
        st.code(profile_json, language="json")
        st.download_button(
            label="Download ava_blackthorne_profile_backup.json",
            data=profile_json,
            file_name="ava_blackthorne_profile_backup.json",
            mime="application/json",
        )

        st.markdown("### ava_blackthorne_profile_backup.txt")
        st.code(profile_text, language="text")
        st.download_button(
            label="Download ava_blackthorne_profile_backup.txt",
            data=profile_text,
            file_name="ava_blackthorne_profile_backup.txt",
            mime="text/plain",
        )

    if "creator_profile_edit_mode" not in st.session_state:
        st.session_state.creator_profile_edit_mode = not has_saved_profile

    fanvue_account_id = _get_fanvue_account_id(profile)

    st.divider()

    # ==================================================
    # VIEW / EDIT CONTROL
    # ==================================================
    if has_saved_profile and not st.session_state.creator_profile_edit_mode:
        st.success("Creator profile loaded from saved data ✅")

        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("✏️ Edit Profile"):
                st.session_state.creator_profile_edit_mode = True
                st.rerun()

        # --------------------------------------------------
        # BASIC INFO
        # --------------------------------------------------
        st.markdown("### Current Profile")
        st.write(f"**Persona Name:** {profile.get('persona_name', '')}")
        st.write(f"**Age:** {profile.get('age', '')}")
        st.write(f"**Gender:** {profile.get('gender', '')}")
        st.write(f"**Location:** {profile.get('location', '')}")
        st.write(f"**Active:** {profile.get('is_active', True)}")

        st.divider()

        # --------------------------------------------------
        # SECTION DEFINITIONS
        # --------------------------------------------------
        view_sections = {
            "Core Personality": [
                ("Archetype", "archetype"),
                ("Personality Description", "personality_description"),
                ("Backstory", "backstory"),
                ("Lifestyle Context", "lifestyle_context"),
                ("Lifestyle Vibe", "lifestyle_vibe"),
                ("Daily Routine", "daily_routine"),
                ("Hobbies", "hobbies"),
            ],
            "Attraction Psychology": [
                ("Likes", "likes"),
                ("Dislikes", "dislikes"),
                ("Ideal User Type", "ideal_user_type"),
                ("Turn-Ons", "turn_ons"),
                ("Turn-Offs", "turn_offs"),
            ],
            "Sexual Personality": [
                ("Sexual Style", "sexual_style"),
                ("Sexual Likes", "sexual_likes"),
                ("Sexual Dislikes", "sexual_dislikes"),
                ("Kinks / Interests", "kinks"),
                ("Fantasy Style", "fantasy_style"),
            ],
            "Flirting & Behavior": [
                ("Tone Style", "tone_style"),
                ("Flirt Style", "flirt_style"),
                ("Tease Intensity", "tease_intensity"),
                ("Push / Pull Style", "push_pull_style"),
                ("Mystery Level", "mystery_level"),
            ],
            "Chat Behavior": [
                ("Response Style", "response_style"),
                ("Pacing Style", "pacing_style"),
                ("Question Frequency", "question_frequency"),
                ("Emotional Depth", "emotional_depth"),
                ("Affection Style", "affection_style"),
                ("Jealousy Style", "jealousy_style"),
                ("Availability Style", "availability_style"),
            ],
            "Advanced Behavior": [
                ("Conversation Hooks", "conversation_hooks"),
                ("Retention Hooks", "retention_hooks"),
                ("Escalation Style", "escalation_style"),
                ("Escalation Triggers", "escalation_triggers"),
                ("Self-Value Style", "self_value_style"),
                ("Persona Intensity", "persona_intensity"),
            ],
            "Boundaries": [
                ("Boundaries", "boundaries"),
                ("Sexual Boundaries", "sexual_boundaries"),
                ("Hard Limits", "hard_limits"),
                ("Response Rules", "response_rules"),
            ],
        }

        # --------------------------------------------------
        # RENDER ALL SECTIONS
        # --------------------------------------------------
        for section_title, fields in view_sections.items():
            has_content = any(profile.get(key) not in [None, ""] for _, key in fields)

            if has_content:
                st.markdown(f"### {section_title}")

                for label, key in fields:
                    value = profile.get(key)

                    if value not in [None, ""]:
                        st.markdown(f"**{label}:**")
                        st.write(value)

                st.divider()

        return

    if has_saved_profile:
        st.info("Editing saved creator profile ✏️")
    else:
        st.info("Create the creator profile below. Only Persona Name is required.")

    # ==================================================
    # IDENTITY
    # ==================================================
    st.markdown("### Identity")

    active_account = (
        st.session_state.get(
            "active_fanvue_account",
            {}
        )
    )

    active_display_name = (
        active_account.get("display_name")
        or active_account.get("username")
        or "Unknown"
    )

    if fanvue_account_id:
        st.caption(
            f"Connected Publishing Account: "
            f"`{fanvue_account_id}`"
        )
    else:
        st.warning(
            "No connected publishing account detected yet. "
            "Connect provider OAuth before saving this profile."
        )

    st.info(
        f"Currently configuring creator profile for: "
        f"{active_display_name}"
    )

    default_persona_name = (
        active_account.get("display_name")
        or active_account.get("username")
        or ""
    )

    persona_name = st.text_input(
        "Persona Name",
        value=profile.get(
            "persona_name",
            default_persona_name,
        ),
        help=(
            "Required. This is the creator/persona "
            "name GPT will know."
        ),
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        age = st.number_input(
            "Age",
            min_value=18,
            max_value=60,
            value=int(
                profile.get("age", 18) or 18
            ),
        )

    with col2:
        gender = _selectbox_with_saved(
            "Gender",
            [
                "female",
                "male",
                "non-binary",
            ],
            profile.get(
                "gender",
                "female",
            ),
        )

    with col3:
        is_active = st.checkbox(
            "Active Profile",
            value=profile.get(
                "is_active",
                True,
            ),
        )

    location = st.text_input(
        "Location",
        value=profile.get(
            "location",
            "",
        ),
        help="Optional.",
    )

    st.divider()

    # ==================================================
    # CORE PERSONALITY
    # ==================================================
    st.markdown("### Core Personality")

    archetype = st.text_input("Archetype", value=profile.get("archetype", ""))

    personality_description = st.text_area(
        "Personality Description",
        value=profile.get("personality_description", ""),
        height=120,
    )

    backstory = st.text_area(
        "Backstory",
        value=profile.get("backstory", ""),
        height=100,
    )

    lifestyle_context = st.text_area(
        "Lifestyle / Age / Location / Occupation Context",
        value=profile.get("lifestyle_context", ""),
        height=100,
    )

    lifestyle_vibe = st.text_area(
        "Lifestyle Vibe",
        value=profile.get("lifestyle_vibe", ""),
        height=80,
    )

    daily_routine = st.text_area(
        "Daily Routine",
        value=profile.get("daily_routine", ""),
        height=80,
    )

    hobbies = st.text_area(
        "Hobbies",
        value=profile.get("hobbies", ""),
        height=80,
    )

    st.divider()

    # ==================================================
    # ATTRACTION PSYCHOLOGY
    # ==================================================
    st.markdown("### Attraction Psychology")

    likes = st.text_area("Likes", value=profile.get("likes", ""), height=80)
    dislikes = st.text_area("Dislikes", value=profile.get("dislikes", ""), height=80)

    ideal_user_type = st.text_area(
        "Ideal User Type",
        value=profile.get("ideal_user_type", ""),
        height=80,
    )

    turn_ons = st.text_area("Turn-Ons", value=profile.get("turn_ons", ""), height=80)
    turn_offs = st.text_area("Turn-Offs", value=profile.get("turn_offs", ""), height=80)

    st.divider()

    # ==================================================
    # SEXUAL PERSONALITY
    # ==================================================
    st.markdown("### Sexual Personality")

    sexual_style = st.text_input(
        "Sexual Style",
        value=profile.get("sexual_style", ""),
    )

    sexual_likes = st.text_area(
        "Sexual Likes",
        value=profile.get("sexual_likes", ""),
        height=80,
    )

    sexual_dislikes = st.text_area(
        "Sexual Dislikes",
        value=profile.get("sexual_dislikes", ""),
        height=80,
    )

    kinks = st.text_area(
        "Kinks / Interests",
        value=profile.get("kinks", ""),
        height=80,
    )

    fantasy_style = st.text_area(
        "Fantasy Style",
        value=profile.get("fantasy_style", ""),
        height=80,
    )

    st.divider()

    # ==================================================
    # FLIRTING / BEHAVIOR
    # ==================================================
    st.markdown("### Flirting & Behavior")

    tone_style = st.text_input(
        "Tone Style",
        value=profile.get("tone_style", ""),
    )

    flirt_style = st.text_input(
        "Flirt Style",
        value=profile.get("flirt_style", ""),
    )

    tease_intensity = st.slider(
        "Tease Intensity",
        1,
        10,
        int(profile.get("tease_intensity", 5) or 5),
    )

    col1, col2 = st.columns(2)

    with col1:
        push_pull_style = _selectbox_with_saved(
            "Push/Pull Style",
            ["low", "medium", "high"],
            profile.get("push_pull_style", "medium"),
            default_index=1,
        )

    with col2:
        mystery_level = _selectbox_with_saved(
            "Mystery Level",
            ["low", "medium", "high"],
            profile.get("mystery_level", "medium"),
            default_index=1,
        )

    st.divider()

    # ==================================================
    # CHAT BEHAVIOR
    # ==================================================
    st.markdown("### Chat Behavior")

    response_style = st.text_input(
        "Response Style",
        value=profile.get("response_style", ""),
    )

    pacing_style = st.text_input(
        "Pacing Style",
        value=profile.get("pacing_style", ""),
    )

    col1, col2 = st.columns(2)

    with col1:
        question_frequency = _selectbox_with_saved(
            "Question Frequency",
            ["low", "medium", "high"],
            profile.get("question_frequency", "medium"),
            default_index=1,
        )

    with col2:
        emotional_depth = _selectbox_with_saved(
            "Emotional Depth",
            ["low", "medium", "high"],
            profile.get("emotional_depth", "medium"),
            default_index=1,
        )

    affection_style = st.text_input(
        "Affection Style",
        value=profile.get("affection_style", ""),
    )

    jealousy_style = st.text_input(
        "Jealousy Style",
        value=profile.get("jealousy_style", ""),
    )

    availability_style = st.text_input(
        "Availability Style",
        value=profile.get("availability_style", ""),
    )

    st.divider()

    # ==================================================
    # ADVANCED BEHAVIOR
    # ==================================================
    st.markdown("### Advanced Behavior")

    conversation_hooks = st.text_area(
        "Conversation Hooks",
        value=profile.get("conversation_hooks", ""),
        height=80,
    )

    retention_hooks = st.text_area(
        "Retention Hooks",
        value=profile.get("retention_hooks", ""),
        height=80,
    )

    escalation_style = st.text_area(
        "Escalation Style",
        value=profile.get("escalation_style", ""),
        height=80,
    )

    escalation_triggers = st.text_area(
        "Escalation Triggers",
        value=profile.get("escalation_triggers", ""),
        height=80,
    )

    self_value_style = st.text_input(
        "Self-Value Style",
        value=profile.get("self_value_style", ""),
    )

    persona_intensity = st.slider(
        "Persona Intensity",
        1,
        10,
        int(profile.get("persona_intensity", 5) or 5),
    )

    st.divider()

    # ==================================================
    # BOUNDARIES
    # ==================================================
    st.markdown("### Boundaries")

    boundaries = st.text_area(
        "Boundaries",
        value=profile.get("boundaries", ""),
        height=80,
    )

    sexual_boundaries = st.text_area(
        "Sexual Boundaries",
        value=profile.get("sexual_boundaries", ""),
        height=80,
    )

    hard_limits = st.text_area(
        "Hard Limits",
        value=profile.get("hard_limits", ""),
        height=80,
    )

    response_rules = st.text_area(
        "Response Rules",
        value=profile.get("response_rules", ""),
        height=120,
    )

    st.divider()

    # ==================================================
    # SAVE / CANCEL
    # ==================================================
    col1, col2 = st.columns([1, 4])

    with col1:
        save_clicked = st.button("💾 Save Profile")

    with col2:
        if has_saved_profile:
            cancel_clicked = st.button("Cancel Edit")
        else:
            cancel_clicked = False

    if cancel_clicked:
        st.session_state.creator_profile_edit_mode = False
        st.rerun()

    if save_clicked:
        errors = []

        if not fanvue_account_id:
            errors.append("Provider OAuth account is required before saving.")

        if not persona_name.strip():
            errors.append("Persona Name is required.")

        if errors:
            for error in errors:
                st.error(error)
            st.stop()

        updated_profile = {
            "fanvue_account_id": fanvue_account_id,
            "persona_name": persona_name.strip(),
            "display_name": persona_name.strip(),
            "age": age,
            "gender": gender,
            "location": location.strip(),
            "is_active": is_active,

            "archetype": archetype.strip(),
            "personality_description": personality_description.strip(),
            "backstory": backstory.strip(),
            "lifestyle_context": lifestyle_context.strip(),
            "lifestyle_vibe": lifestyle_vibe.strip(),
            "daily_routine": daily_routine.strip(),
            "hobbies": hobbies.strip(),

            "likes": likes.strip(),
            "dislikes": dislikes.strip(),
            "ideal_user_type": ideal_user_type.strip(),
            "turn_ons": turn_ons.strip(),
            "turn_offs": turn_offs.strip(),

            "sexual_style": sexual_style.strip(),
            "sexual_likes": sexual_likes.strip(),
            "sexual_dislikes": sexual_dislikes.strip(),
            "kinks": kinks.strip(),
            "fantasy_style": fantasy_style.strip(),

            "tone_style": tone_style.strip(),
            "flirt_style": flirt_style.strip(),
            "tease_intensity": tease_intensity,
            "push_pull_style": push_pull_style,
            "mystery_level": mystery_level,

            "response_style": response_style.strip(),
            "pacing_style": pacing_style.strip(),
            "question_frequency": question_frequency,
            "emotional_depth": emotional_depth,
            "affection_style": affection_style.strip(),
            "jealousy_style": jealousy_style.strip(),
            "availability_style": availability_style.strip(),

            "conversation_hooks": conversation_hooks.strip(),
            "retention_hooks": retention_hooks.strip(),
            "escalation_style": escalation_style.strip(),
            "escalation_triggers": escalation_triggers.strip(),
            "self_value_style": self_value_style.strip(),
            "persona_intensity": persona_intensity,

            "boundaries": boundaries.strip(),
            "sexual_boundaries": sexual_boundaries.strip(),
            "hard_limits": hard_limits.strip(),
            "response_rules": response_rules.strip(),

            "last_updated": str(datetime.utcnow()),
        }

        saved_profile = upsert_creator_profile(updated_profile)

        st.session_state.creator_profile_edit_mode = False
        st.session_state.creator_profile_saved = True

        st.success("Creator profile saved successfully ✅")
        st.caption("Your changes were saved and will load again when you return to this page.")

        st.json(saved_profile)
