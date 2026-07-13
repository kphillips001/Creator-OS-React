"""Read-only inspection utility for the active Creator Persona.

This tool intentionally reads through CreatorProfileRepository instead of
creating a second persona ownership path.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Iterable

@dataclass(frozen=True)
class ExpectedPersonaField:
    section: str
    label: str
    keys: tuple[str, ...]
    recommendation: str


EXPECTED_FIELDS: tuple[ExpectedPersonaField, ...] = (
    ExpectedPersonaField("Identity", "Creator ID", ("id", "creator_id", "creator_profile_id"), "canonical"),
    ExpectedPersonaField("Identity", "Display Name", ("display_name",), "canonical"),
    ExpectedPersonaField("Identity", "Username(s)", ("username", "usernames", "fanvue_username"), "optional"),
    ExpectedPersonaField("Identity", "Character Name", ("persona_name", "character_name"), "canonical"),
    ExpectedPersonaField("Identity", "Age", ("age",), "optional"),
    ExpectedPersonaField("Identity", "Location", ("location",), "optional"),
    ExpectedPersonaField("Identity", "Occupation", ("occupation", "occupation_context"), "optional"),
    ExpectedPersonaField("Biography", "Bio", ("bio", "biography"), "should become canonical"),
    ExpectedPersonaField("Biography", "Backstory", ("backstory",), "canonical"),
    ExpectedPersonaField("Biography", "Personality Summary", ("personality_summary", "personality_description"), "canonical"),
    ExpectedPersonaField("Personality", "Traits", ("traits", "personality_traits", "archetype"), "should become canonical"),
    ExpectedPersonaField("Personality", "Communication Style", ("communication_style", "response_style"), "canonical"),
    ExpectedPersonaField("Personality", "Humor", ("humor", "humor_style"), "should become canonical"),
    ExpectedPersonaField("Personality", "Confidence", ("confidence", "confidence_style", "self_value_style"), "canonical"),
    ExpectedPersonaField("Personality", "Flirting Style", ("flirting_style", "flirt_style"), "canonical"),
    ExpectedPersonaField("Personality", "Energy", ("energy", "persona_intensity"), "canonical"),
    ExpectedPersonaField("Personality", "Emotional Tone", ("emotional_tone", "tone_style", "emotional_depth"), "canonical"),
    ExpectedPersonaField("Appearance", "Hair", ("hair", "hair_style", "hair_color"), "should become canonical"),
    ExpectedPersonaField("Appearance", "Eyes", ("eyes", "eye_color"), "should become canonical"),
    ExpectedPersonaField("Appearance", "Body", ("body", "body_type", "body_description"), "should become canonical"),
    ExpectedPersonaField("Appearance", "Height", ("height",), "optional"),
    ExpectedPersonaField("Appearance", "Skin Tone", ("skin_tone",), "should become canonical"),
    ExpectedPersonaField("Appearance", "Style", ("style", "fashion_style", "visual_style", "lifestyle_vibe"), "canonical"),
    ExpectedPersonaField("Appearance", "Distinguishing Features", ("distinguishing_features", "features"), "optional"),
    ExpectedPersonaField("Voice", "Writing Style", ("writing_style", "response_style", "tone_style"), "canonical"),
    ExpectedPersonaField("Voice", "Vocabulary", ("vocabulary", "word_choice"), "should become canonical"),
    ExpectedPersonaField("Voice", "Emoji Usage", ("emoji_usage", "emoji_style"), "should become canonical"),
    ExpectedPersonaField("Voice", "Greeting Style", ("greeting_style",), "optional"),
    ExpectedPersonaField("Voice", "Closing Style", ("closing_style",), "optional"),
    ExpectedPersonaField("Voice", "Things to Avoid", ("things_to_avoid", "avoid_phrases", "response_rules"), "canonical"),
    ExpectedPersonaField("Interests", "Hobbies", ("hobbies",), "canonical"),
    ExpectedPersonaField("Interests", "Favorite Activities", ("favorite_activities", "activities", "daily_routine"), "optional"),
    ExpectedPersonaField("Interests", "Lifestyle", ("lifestyle", "lifestyle_context", "lifestyle_vibe"), "canonical"),
    ExpectedPersonaField("Interests", "Likes", ("likes",), "canonical"),
    ExpectedPersonaField("Interests", "Dislikes", ("dislikes",), "canonical"),
    ExpectedPersonaField("Boundaries", "Hard Rules", ("hard_rules", "hard_limits", "boundaries"), "canonical"),
    ExpectedPersonaField("Boundaries", "Never Say", ("never_say", "forbidden_phrases"), "should become canonical"),
    ExpectedPersonaField("Boundaries", "Never Do", ("never_do", "forbidden_actions"), "should become canonical"),
    ExpectedPersonaField("Boundaries", "Brand Restrictions", ("brand_restrictions", "boundaries"), "should become canonical"),
    ExpectedPersonaField("Relationship Style", "Subscriber Interaction Style", ("subscriber_interaction_style", "response_style"), "canonical"),
    ExpectedPersonaField("Relationship Style", "Sales Approach", ("sales_approach", "escalation_style"), "canonical"),
    ExpectedPersonaField("Relationship Style", "Girlfriend Experience Level", ("girlfriend_experience_level", "gfe_level", "affection_style"), "should become canonical"),
    ExpectedPersonaField("Relationship Style", "Conversation Goals", ("conversation_goals", "conversation_hooks", "retention_hooks"), "canonical"),
    ExpectedPersonaField("Business", "Brand Pillars", ("brand_pillars", "archetype", "self_value_style"), "should become canonical"),
    ExpectedPersonaField("Business", "Audience", ("audience", "ideal_user_type"), "canonical"),
    ExpectedPersonaField("Business", "Content Categories", ("content_categories", "content_types"), "should become canonical"),
    ExpectedPersonaField("Business", "Pricing Preferences", ("pricing_preferences", "pricing_style"), "optional"),
    ExpectedPersonaField("Prompting", "System Prompt", ("system_prompt",), "should become canonical"),
    ExpectedPersonaField("Prompting", "Persona Prompt", ("persona_prompt",), "should become canonical"),
    ExpectedPersonaField("Prompting", "Default Instructions", ("default_instructions", "response_rules"), "canonical"),
    ExpectedPersonaField("Prompting", "AI Guidance", ("ai_guidance", "prompt_guidance", "generation_guidance"), "should become canonical"),
    ExpectedPersonaField("Metadata", "Created Date", ("created_at",), "canonical"),
    ExpectedPersonaField("Metadata", "Last Updated", ("updated_at", "last_updated"), "canonical"),
    ExpectedPersonaField("Metadata", "Version", ("version",), "should become canonical"),
    ExpectedPersonaField("Metadata", "Active Flag", ("is_active", "active"), "canonical"),
)


def _as_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if row is None:
        return {}
    try:
        return dict(row)
    except (TypeError, ValueError):
        return {}


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _format_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, indent=2, ensure_ascii=False, default=str)
    return str(value)


def _first_present_value(
    profile: dict[str, Any],
    keys: Iterable[str],
) -> tuple[str | None, Any]:
    for key in keys:
        if key in profile and not _is_missing(profile.get(key)):
            return key, profile.get(key)
    return None, None


def _section_order() -> tuple[str, ...]:
    ordered: list[str] = []
    for field in EXPECTED_FIELDS:
        if field.section not in ordered:
            ordered.append(field.section)
    return tuple(ordered)


def build_creator_persona_report(
    profile: dict[str, Any],
    *,
    fanvue_account_id: str | int | None = None,
) -> str:
    """Build a complete read-only report from a loaded creator profile row."""

    lines: list[str] = [
        "Creator Persona Inspection",
        "==========================",
        "Source: app.repositories.creator_profile_repository.get_active_creator_profile",
    ]
    if fanvue_account_id is not None:
        lines.append(f"Fanvue Account ID: {fanvue_account_id}")
    lines.append("")

    missing_fields: list[ExpectedPersonaField] = []
    for section in _section_order():
        lines.append(section)
        lines.append("-" * len(section))
        for field in (item for item in EXPECTED_FIELDS if item.section == section):
            key, value = _first_present_value(profile, field.keys)
            if key is None:
                lines.append(f"{field.label}: Missing")
                missing_fields.append(field)
            else:
                lines.append(f"{field.label}: {_format_value(value)}")
                lines.append(f"  stored_as: {key}")
        lines.append("")

    lines.append("Raw Stored Fields")
    lines.append("-----------------")
    if profile:
        for key in sorted(profile):
            lines.append(f"{key}: {_format_value(profile[key])}")
    else:
        lines.append("No active creator profile loaded.")
    lines.append("")

    lines.append("Missing Field Review")
    lines.append("--------------------")
    if missing_fields:
        for field in missing_fields:
            lines.append(
                f"- {field.section} / {field.label}: {field.recommendation}"
            )
    else:
        lines.append("No expected fields are missing.")

    return "\n".join(lines).rstrip() + "\n"


def _load_first_available_profile() -> tuple[str | int | None, dict[str, Any]]:
    from app.repositories.creator_profile_repository import get_active_creator_profile
    from app.repositories.fanvue_account_repository import get_all_accounts

    for account in get_all_accounts():
        account_data = _as_dict(account)
        account_id = account_data.get("id") or account_data.get("fanvue_account_id")
        if account_id is None:
            continue
        profile = get_active_creator_profile(account_id)
        if profile:
            return account_id, _as_dict(profile)
    return None, {}


def load_active_creator_persona(
    fanvue_account_id: str | int | None = None,
) -> tuple[str | int | None, dict[str, Any]]:
    """Load the active persona without mutating existing profile data."""

    from app.repositories.creator_profile_repository import get_active_creator_profile

    if fanvue_account_id is not None:
        return fanvue_account_id, _as_dict(
            get_active_creator_profile(fanvue_account_id)
        )
    return _load_first_available_profile()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect the active Creator Persona without modifying data.",
    )
    parser.add_argument(
        "--fanvue-account-id",
        help="Optional provider account id. If omitted, the first account with an active profile is inspected.",
    )
    args = parser.parse_args()

    account_id, profile = load_active_creator_persona(args.fanvue_account_id)
    print(
        build_creator_persona_report(
            profile,
            fanvue_account_id=account_id,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
