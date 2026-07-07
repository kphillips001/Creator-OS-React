"""Provider-neutral Creator Intent contract for Creator OS."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class CreatorContentType(str, Enum):
    SINGLE_ASSET = "SINGLE_ASSET"
    PHOTOSHOOT = "PHOTOSHOOT"
    STORY = "STORY"
    BUNDLE = "BUNDLE"


_LEGACY_CONTENT_TYPE_MAP = {
    "single": CreatorContentType.SINGLE_ASSET,
    "single_asset": CreatorContentType.SINGLE_ASSET,
    "asset": CreatorContentType.SINGLE_ASSET,
    "image": CreatorContentType.SINGLE_ASSET,
    "video": CreatorContentType.SINGLE_ASSET,
    "teaser": CreatorContentType.SINGLE_ASSET,
    "teaser_image": CreatorContentType.SINGLE_ASSET,
    "teaser_video": CreatorContentType.SINGLE_ASSET,
    "wall": CreatorContentType.SINGLE_ASSET,
    "wall_image": CreatorContentType.SINGLE_ASSET,
    "wall_video": CreatorContentType.SINGLE_ASSET,
    "ppv": CreatorContentType.SINGLE_ASSET,
    "ppv_image": CreatorContentType.SINGLE_ASSET,
    "ppv_video": CreatorContentType.SINGLE_ASSET,
    "premium_image": CreatorContentType.SINGLE_ASSET,
    "premium_video": CreatorContentType.SINGLE_ASSET,
    "vip_image": CreatorContentType.SINGLE_ASSET,
    "vip_video": CreatorContentType.SINGLE_ASSET,
    "photo_set": CreatorContentType.PHOTOSHOOT,
    "photoset": CreatorContentType.PHOTOSHOOT,
    "photoshoot": CreatorContentType.PHOTOSHOOT,
    "shoot": CreatorContentType.PHOTOSHOOT,
    "story": CreatorContentType.STORY,
    "bundle": CreatorContentType.BUNDLE,
    "collection": CreatorContentType.BUNDLE,
}


def normalize_creator_content_type(value: Any) -> CreatorContentType:
    """Normalize current and legacy content-type labels."""

    if isinstance(value, CreatorContentType):
        return value
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not key:
        return CreatorContentType.SINGLE_ASSET
    if key in _LEGACY_CONTENT_TYPE_MAP:
        return _LEGACY_CONTENT_TYPE_MAP[key]
    try:
        return CreatorContentType(key.upper())
    except ValueError:
        return CreatorContentType.SINGLE_ASSET


@dataclass(frozen=True)
class CreatorIntent:
    """Creator-owned, provider-neutral creative intent.

    AI services may consume this as evidence, but the creator remains the owner
    of the explicit creative decision.
    """

    content_type: CreatorContentType
    selected_at: str
    confirmed: bool = True
    override_active: bool = False
    notes: str | None = None
    legacy_upload_intent: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        content_type: CreatorContentType | str | None,
        *,
        selected_at: str | None = None,
        confirmed: bool = True,
        override_active: bool = False,
        notes: str | None = None,
        legacy_upload_intent: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "CreatorIntent":
        return cls(
            content_type=normalize_creator_content_type(
                content_type or legacy_upload_intent
            ),
            selected_at=selected_at or datetime.now(timezone.utc).isoformat(),
            confirmed=bool(confirmed),
            override_active=bool(override_active),
            notes=str(notes).strip() if notes else None,
            legacy_upload_intent=(
                str(legacy_upload_intent).strip().lower()
                if legacy_upload_intent
                else None
            ),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_legacy(
        cls,
        value: Any,
        *,
        selected_at: str | None = None,
        confirmed: bool = True,
        override_active: bool = False,
        notes: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "CreatorIntent":
        legacy_value = str(value or "").strip().lower() or None
        return cls.create(
            legacy_value,
            selected_at=selected_at,
            confirmed=confirmed,
            override_active=override_active,
            notes=notes,
            legacy_upload_intent=legacy_value,
            metadata={
                **dict(metadata or {}),
                "source": "legacy_upload_intent",
            },
        )

    @classmethod
    def from_value(
        cls,
        value: "CreatorIntent | Mapping[str, Any] | str | None",
        *,
        fallback_upload_intent: str | None = None,
    ) -> "CreatorIntent":
        if isinstance(value, CreatorIntent):
            return value
        if isinstance(value, Mapping):
            return cls.create(
                value.get("content_type")
                or value.get("content_type_selection")
                or fallback_upload_intent,
                selected_at=value.get("selected_at"),
                confirmed=value.get("confirmed", True),
                override_active=value.get("override_active", False),
                notes=value.get("notes"),
                legacy_upload_intent=(
                    value.get("legacy_upload_intent")
                    or value.get("upload_intent")
                    or fallback_upload_intent
                ),
                metadata=value.get("metadata") or {},
            )
        return cls.from_legacy(value or fallback_upload_intent)

    def to_context(self) -> dict[str, Any]:
        return {
            "content_type": self.content_type.value,
            "selected_at": self.selected_at,
            "confirmed": self.confirmed,
            "override_active": self.override_active,
            "notes": self.notes,
            "legacy_upload_intent": self.legacy_upload_intent,
            "metadata": dict(self.metadata or {}),
            "owner": "creator",
            "provider_neutral": True,
            "ai_advisory_only": True,
        }

    def to_legacy_upload_intent(self, default: str | None = None) -> str:
        if self.legacy_upload_intent:
            return self.legacy_upload_intent
        if default:
            return str(default).strip().lower()
        if self.content_type == CreatorContentType.PHOTOSHOOT:
            return "teaser_image"
        if self.content_type == CreatorContentType.STORY:
            return "teaser_image"
        if self.content_type == CreatorContentType.BUNDLE:
            return "ppv_image"
        return "teaser_image"

    @property
    def package_type(self) -> str:
        if self.content_type == CreatorContentType.PHOTOSHOOT:
            return "photo_set"
        if self.content_type == CreatorContentType.STORY:
            return "story"
        if self.content_type == CreatorContentType.BUNDLE:
            return "bundle"
        return "standalone"
