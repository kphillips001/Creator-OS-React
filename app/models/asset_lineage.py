"""Immutable domain representations for relationships between canonical Assets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID


class DerivationKind(str, Enum):
    IMAGE_TO_VIDEO = "IMAGE_TO_VIDEO"
    IMAGE_TO_GIF = "IMAGE_TO_GIF"
    IMAGE_TO_ANIMATION = "IMAGE_TO_ANIMATION"
    IMAGE_TO_CINEMAGRAPH = "IMAGE_TO_CINEMAGRAPH"
    IMAGE_UPSCALE = "IMAGE_UPSCALE"
    IMAGE_EDIT = "IMAGE_EDIT"
    SELECTIVE_BLUR = "SELECTIVE_BLUR"
    VIDEO_TO_GIF = "VIDEO_TO_GIF"
    VIDEO_TO_CLIP = "VIDEO_TO_CLIP"
    VIDEO_EDIT = "VIDEO_EDIT"
    MULTI_IMAGE_TO_VIDEO = "MULTI_IMAGE_TO_VIDEO"
    MULTI_ASSET_COMPOSITION = "MULTI_ASSET_COMPOSITION"
    FORMAT_TRANSFORMATION = "FORMAT_TRANSFORMATION"
    OTHER_DERIVED_MEDIA = "OTHER_DERIVED_MEDIA"


@dataclass(frozen=True)
class AssetLineageRelationship:
    relationship_id: UUID
    source_asset_ids: tuple[int, ...]
    derived_asset_id: int
    derivation_kind: DerivationKind
    provenance: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        sources = tuple(dict.fromkeys(int(value) for value in self.source_asset_ids))
        if not sources:
            raise ValueError("Asset Lineage requires at least one source Asset.")
        if int(self.derived_asset_id) in sources:
            raise ValueError("An Asset cannot derive from itself.")
        object.__setattr__(self, "source_asset_ids", sources)
        object.__setattr__(self, "derived_asset_id", int(self.derived_asset_id))
        object.__setattr__(self, "provenance", immutable_mapping(self.provenance))

    @property
    def multi_source(self) -> bool:
        return len(self.source_asset_ids) > 1


@dataclass(frozen=True)
class LineageAssetReference:
    asset_id: int
    depth: int


@dataclass(frozen=True)
class RootAsset(LineageAssetReference):
    pass


@dataclass(frozen=True)
class ParentAsset(LineageAssetReference):
    pass


@dataclass(frozen=True)
class ChildAsset(LineageAssetReference):
    pass


@dataclass(frozen=True)
class Ancestor(LineageAssetReference):
    pass


@dataclass(frozen=True)
class Descendant(LineageAssetReference):
    pass


@dataclass(frozen=True)
class PhotoshootLineageContext:
    photoshoot_session_id: str
    source_asset_ids: tuple[int, ...]
    minimum_depth: int
    direct_membership: bool = False


@dataclass(frozen=True)
class AssetLineageDiagnostics:
    asset_id: int
    classification: str
    roots: tuple[RootAsset, ...]
    parents: tuple[ParentAsset, ...]
    children: tuple[ChildAsset, ...]
    siblings: tuple[ChildAsset, ...]
    ancestors: tuple[Ancestor, ...]
    descendants: tuple[Descendant, ...]
    family_asset_ids: tuple[int, ...]
    relationships: tuple[AssetLineageRelationship, ...]
    photoshoot_contexts: tuple[PhotoshootLineageContext, ...]
    source_media_types: Mapping[int, str]
    derived_media_type: str
    lineage_depth: int
    ambiguous: bool
    complete: bool
    integrity_status: str
    provenance_complete: bool
    completeness_issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_media_types", immutable_mapping(self.source_media_types)
        )

    @property
    def root(self) -> RootAsset | None:
        return self.roots[0] if len(self.roots) == 1 else None


def immutable_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))
