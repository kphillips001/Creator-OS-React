"""Presentation models for the Content Studio Reference Library."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from app.models.asset_library import AssetLibraryItem


@dataclass(frozen=True)
class CanonicalReferenceAsset:
    asset_id: int
    file_name: str | None
    media_type: str
    classification: str | None
    status: str | None
    is_active: bool
    preview_path: str | None
    original_path: str | None


@dataclass(frozen=True)
class CanonicalReferenceProjection:
    asset: CanonicalReferenceAsset
    creator_profile_id: int
    is_active: bool
    is_favorite: bool
    added_at: str | None
    last_used_at: str | None
    metadata: Mapping[str, Any]

    @property
    def asset_id(self) -> int:
        return self.asset.asset_id


@dataclass(frozen=True)
class LightweightReferenceProjection:
    asset: CanonicalReferenceAsset
    creator_profile_id: int
    is_active: bool
    is_favorite: bool
    added_at: str | None
    last_used_at: str | None
    metadata: Mapping[str, Any]

    @property
    def asset_id(self) -> int:
        return self.asset.asset_id


@dataclass(frozen=True)
class ReferenceLibraryFilter:
    search: str | None = None
    creator_profile_id: int | None = None
    favorites_only: bool = False
    active_only: bool = False
    has_local_vault_original: bool | None = True
    limit: int = 100


@dataclass(frozen=True)
class ReferenceAsset:
    asset: AssetLibraryItem
    creator_profile_id: int | None
    is_active: bool = False
    is_favorite: bool = False
    added_at: str | None = None
    last_used_at: str | None = None
    removed_at: str | None = None
    metadata: Mapping[str, Any] | None = None

    @property
    def asset_id(self) -> int:
        return self.asset.asset_id


@dataclass(frozen=True)
class ReferenceLibraryResult:
    references: tuple[ReferenceAsset, ...]
    filters: ReferenceLibraryFilter
    active_reference: ReferenceAsset | None = None

    @property
    def total(self) -> int:
        return len(self.references)


@dataclass(frozen=True)
class ReferenceLibraryActionResult:
    success: bool
    message: str
    asset_id: int | None = None
    reference: ReferenceAsset | None = None
    data: Mapping[str, Any] | None = None


def utc_timestamp(value: datetime | None = None) -> str:
    return (value or datetime.utcnow()).isoformat()
