"""Read-only normalized view of a legacy ``content_items`` row."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


_IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
_VIDEO_SUFFIXES = {".m4v", ".mov", ".mp4", ".webm"}

# A.2 ownership map for the legacy content_items compatibility surface.
# These tuples document intended lifecycle ownership only; they are not schema
# declarations and should not be used to remove fields until the compatibility
# table has been split.
ASSET_OWNED_FIELDS = (
    "id",
    "file_path",
    "file_name",
    "status",
    "is_active",
    "is_test",
    "blurred_preview_path",
    "created_at",
    "media_metadata",
    "local_vault_path",
    "creator_profile_id",
    "classification",
    "confidence",
    "suggested_tags",
    "detected_themes",
    "is_explicit",
    "short_safe_summary",
    "risk_flags",
    "analysis_reasoning",
    "analysis_provenance",
    "nudity_labels",
    "nudity_level",
    "sexual_intensity",
    "gpt_vision_result",
    "nudenet_result",
    "classification_result",
)

PRODUCT_OWNED_COMPATIBILITY_FIELDS = (
    "ready_for_rotation",
    "upload_intent",
    "content_type",
    "content_tier",
    "distribution_type",
    "mass_ppv_price",
)

PUBLISHING_OWNED_COMPATIBILITY_FIELDS = (
    "fanvue_account_id",
    "fanvue_upload_status",
    "fanvue_upload_error",
    "fanvue_upload_metadata",
    "fanvue_uploaded_at",
    "fanvue_preview_upload_status",
    "fanvue_full_upload_status",
    "fanvue_media_preview_uuid",
    "fanvue_media_full_uuid",
    "fanvue_ptv_set_id",
    "fanvue_set_status",
    "last_fanvue_message_uuid",
)

CONTENT_ITEM_OWNERSHIP_MAP = {
    "asset": ASSET_OWNED_FIELDS,
    "product_compatibility": PRODUCT_OWNED_COMPATIBILITY_FIELDS,
    "publishing_compatibility": PUBLISHING_OWNED_COMPATIBILITY_FIELDS,
}


def _coerce_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


def _coerce_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class Asset:
    """
    Phase 1 compatibility view for imported assets.

    Intended Asset ownership:
    import identity, Local Vault metadata, original/derived media paths,
    technical media metadata, AI analysis metadata, safety metadata, and
    review/archive state.

    Compatibility fields still exposed here:
    Product-owned readiness/grouping fields and Publishing-owned Fanvue fields
    remain on content_items until later lifecycle extraction phases move those
    responsibilities behind Product and Publishing records.
    """

    id: int
    file_path: str
    file_name: str | None
    classification: str | None
    confidence: float | None
    status: str | None
    is_active: bool
    is_test: bool
    ready_for_rotation: bool
    upload_intent: str | None
    content_tier: str | None
    distribution_type: str | None
    blurred_preview_path: str | None
    suggested_tags: tuple[str, ...]
    detected_themes: tuple[str, ...]
    is_explicit: bool
    fanvue_media_preview_uuid: str | None
    fanvue_media_full_uuid: str | None
    created_at: datetime | None
    fanvue_upload_status: str | None = None
    fanvue_upload_error: str | None = None
    summary: str | None = None
    risk_flags: tuple[str, ...] = ()
    reasoning: str | None = None
    analysis_provenance: Mapping[str, Any] | None = None
    media_metadata: Mapping[str, Any] | None = None
    local_vault_path: str | None = None
    creator_profile_id: int | None = None
    nudity_labels: tuple[str, ...] = ()
    nudity_level: str | None = None
    sexual_intensity: str | None = None
    gpt_vision_result: Mapping[str, Any] | None = None
    nudenet_result: Any = None
    classification_result: Mapping[str, Any] | None = None

    @property
    def media_type(self) -> str:
        suffix = Path(self.file_name or self.file_path).suffix.lower()
        if suffix in _IMAGE_SUFFIXES:
            return "image"
        if suffix in _VIDEO_SUFFIXES:
            return "video"
        return "unknown"

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Asset":
        return cls(
            id=row["id"],
            file_path=row["file_path"],
            file_name=row.get("file_name"),
            classification=row.get("classification"),
            confidence=row.get("confidence"),
            status=row.get("status"),
            is_active=bool(row.get("is_active", True)),
            is_test=bool(row.get("is_test", False)),
            ready_for_rotation=bool(row.get("ready_for_rotation", False)),
            upload_intent=row.get("upload_intent"),
            content_tier=row.get("content_tier"),
            distribution_type=row.get("distribution_type"),
            blurred_preview_path=row.get("blurred_preview_path"),
            suggested_tags=_coerce_tuple(row.get("suggested_tags")),
            detected_themes=_coerce_tuple(row.get("detected_themes")),
            is_explicit=bool(row.get("is_explicit", False)),
            fanvue_media_preview_uuid=row.get("fanvue_media_preview_uuid"),
            fanvue_media_full_uuid=row.get("fanvue_media_full_uuid"),
            fanvue_upload_status=row.get("fanvue_upload_status"),
            fanvue_upload_error=row.get("fanvue_upload_error"),
            created_at=row.get("created_at"),
            summary=row.get("short_safe_summary"),
            risk_flags=_coerce_tuple(row.get("risk_flags")),
            reasoning=row.get("analysis_reasoning"),
            analysis_provenance=_coerce_mapping(row.get("analysis_provenance")),
            media_metadata=_coerce_mapping(row.get("media_metadata")),
            local_vault_path=row.get("local_vault_path"),
            creator_profile_id=row.get("creator_profile_id"),
            nudity_labels=_coerce_tuple(row.get("nudity_labels")),
            nudity_level=row.get("nudity_level"),
            sexual_intensity=row.get("sexual_intensity"),
            gpt_vision_result=_coerce_mapping(row.get("gpt_vision_result")),
            nudenet_result=row.get("nudenet_result"),
            classification_result=_coerce_mapping(row.get("classification_result")),
        )
