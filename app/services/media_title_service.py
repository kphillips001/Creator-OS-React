"""Shared human-readable media-title validation and fallback rules."""

from __future__ import annotations

import re
from pathlib import Path


def meaningful_filename_title(file_name: str | None) -> str | None:
    stem = Path(str(file_name or "")).stem.strip()
    if not stem:
        return None
    lowered = stem.lower()
    if lowered.startswith(("generated_image_", "generated_video_")):
        return None
    if lowered in {"image", "video", "asset", "output"}:
        return None
    compact = re.sub(r"[^a-z0-9]", "", lowered)
    if len(compact) >= 20 and not re.search(r"[\s_-]", stem):
        return None
    if re.fullmatch(r"[0-9a-f-]{20,}", lowered):
        return None
    words = re.sub(r"[_-]+", " ", stem).strip()
    return words.title() if words else None


def safe_image_title(*, asset_id: int, canonical_title: str | None,
                     file_name: str | None) -> str:
    return (
        str(canonical_title or "").strip()
        or meaningful_filename_title(file_name)
        or f"Image {int(asset_id)}"
    )


def is_internal_fallback_title(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    return bool(
        lowered.startswith(("generated_image_", "generated_video_"))
        or re.fullmatch(r"(?:asset|image)\s*#?\d+", lowered)
    )
