import json
from pathlib import Path


CONFIG_PATH = Path("data/config/behavior_config.json")
CREATOR_PATH = Path("data/config/creator_profile.json")


def load_dashboard_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        behavior_config = json.load(file)

    with CREATOR_PATH.open("r", encoding="utf-8") as file:
        creator_profile = json.load(file)

    # =========================
    # DEFAULT BEHAVIOR CONFIG
    # =========================
    behavior_config.setdefault("bot_enabled", False)
    behavior_config.setdefault("dashboard_theme", "light")
    behavior_config.setdefault("manual_pause_enabled", False)
    behavior_config.setdefault("modules", {})

    # =========================
    # MEDIA PREVIEW (NEW)
    # =========================
    media_preview = behavior_config.setdefault("media_preview", {})

    media_preview.setdefault("blur_pending_cms_media", True)
    media_preview.setdefault("blur_explicit_content_preview", True)
    media_preview.setdefault("blur_strength", 12)
    media_preview.setdefault("click_to_reveal_enabled", True)

    # =========================
    # CREATOR PROFILE DEFAULTS
    # =========================
    creator_profile.setdefault("name", "")
    creator_profile.setdefault("tone", "flirty")

    return behavior_config, creator_profile


def save_behavior_config(behavior_config):
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(behavior_config, file, indent=2)


def save_creator_profile(creator_profile):
    with CREATOR_PATH.open("w", encoding="utf-8") as file:
        json.dump(creator_profile, file, indent=2)