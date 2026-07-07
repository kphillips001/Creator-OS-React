"""Provider-neutral Experience domain contract.

A.4 contract only. Experience represents organization and presentation between
Assets and Products; it does not define persistence or commerce behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


class ExperienceType(str, Enum):
    STANDALONE = "STANDALONE"
    PHOTOSHOOT = "PHOTOSHOOT"
    STORY = "STORY"


@dataclass(frozen=True)
class Experience:
    experience_id: UUID | str | None
    experience_type: ExperienceType
    title: str
    description: str | None
    cover_asset_id: int | None
    asset_ids: tuple[int, ...]
    asset_order: tuple[int, ...]
    metadata: Mapping[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        asset_ids = self._coerce_asset_ids(self.asset_ids)
        asset_order = self._coerce_asset_ids(self.asset_order) or asset_ids
        cover_asset_id = self.cover_asset_id

        if cover_asset_id is None and asset_order:
            cover_asset_id = asset_order[0]

        object.__setattr__(self, "asset_ids", asset_ids)
        object.__setattr__(self, "asset_order", asset_order)
        object.__setattr__(self, "cover_asset_id", cover_asset_id)
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @property
    def ordered_asset_ids(self) -> tuple[int, ...]:
        return self.asset_order

    @property
    def is_standalone(self) -> bool:
        return self.experience_type == ExperienceType.STANDALONE

    @property
    def is_collection(self) -> bool:
        return self.experience_type in {
            ExperienceType.PHOTOSHOOT,
            ExperienceType.STORY,
        }

    @classmethod
    def standalone(
        cls,
        *,
        asset_id: int,
        title: str,
        experience_id: UUID | str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> "Experience":
        return cls(
            experience_id=experience_id,
            experience_type=ExperienceType.STANDALONE,
            title=title,
            description=description,
            cover_asset_id=asset_id,
            asset_ids=(asset_id,),
            asset_order=(asset_id,),
            metadata=metadata or {},
            created_at=created_at,
            updated_at=updated_at,
        )

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Experience":
        return cls(
            experience_id=row.get("experience_id") or row.get("id"),
            experience_type=ExperienceType(row["experience_type"]),
            title=row["title"],
            description=row.get("description"),
            cover_asset_id=row.get("cover_asset_id"),
            asset_ids=cls._coerce_asset_ids(row.get("asset_ids")),
            asset_order=cls._coerce_asset_ids(row.get("asset_order")),
            metadata=row.get("metadata") or {},
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    @staticmethod
    def _coerce_asset_ids(value: Any) -> tuple[int, ...]:
        if value is None:
            return ()
        if isinstance(value, (str, bytes)):
            values = [value]
        else:
            values = list(value)

        asset_ids = []
        for item in values:
            if item is None or str(item).strip() == "":
                continue
            asset_ids.append(int(item))
        return tuple(asset_ids)


@dataclass(frozen=True)
class ExperienceAssetRelationship:
    """Provider-neutral Asset membership inside an Experience.

    This is the first-class relationship contract. Existing ProductAsset rows
    may still be projected into this shape as compatibility data, but callers
    should consume relationships through ExperienceService.
    """

    experience_id: UUID | str
    asset_id: int
    position: int = 0
    role: str = "member"
    source: str = "experience"
    compatibility: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "experience_id", str(self.experience_id))
        object.__setattr__(self, "asset_id", int(self.asset_id))
        object.__setattr__(self, "position", int(self.position or 0))
        object.__setattr__(self, "role", str(self.role or "member"))
        object.__setattr__(self, "source", str(self.source or "experience"))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


@dataclass(frozen=True)
class ProductExperienceRelationship:
    """Provider-neutral Product membership in an Experience.

    ProductAsset-backed relationships may be projected into this shape for
    compatibility, but ProductAsset is not the public relationship contract.
    """

    product_id: UUID | str
    experience_id: UUID | str
    role: str = "primary"
    source: str = "experience"
    compatibility: bool = False
    compatibility_experience_id: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_id", str(self.product_id))
        object.__setattr__(self, "experience_id", str(self.experience_id))
        object.__setattr__(self, "role", str(self.role or "primary"))
        object.__setattr__(self, "source", str(self.source or "experience"))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


@dataclass(frozen=True)
class ExperienceProductRelationship:
    """Provider-neutral Experience to Product projection."""

    experience_id: UUID | str
    product_id: UUID | str
    role: str = "primary"
    source: str = "experience"
    compatibility: bool = False
    compatibility_experience_id: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "experience_id", str(self.experience_id))
        object.__setattr__(self, "product_id", str(self.product_id))
        object.__setattr__(self, "role", str(self.role or "primary"))
        object.__setattr__(self, "source", str(self.source or "experience"))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


@dataclass(frozen=True)
class ExperiencePersistenceSupport:
    """Describes whether a repository has dedicated Experience read models."""

    dedicated_read_model: bool
    relationship_read_model: bool
    source: str
    compatibility_fallback: str | None = None


@dataclass(frozen=True)
class ExperiencePublishingReadiness:
    """Read-only provider-neutral publishing readiness for an Experience."""

    experience_id: str
    status: str
    detail: str
    asset_count: int = 0
    ready_asset_count: int = 0
    source: str = "PublishingService"
    compatibility: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "experience_id", str(self.experience_id))
        object.__setattr__(self, "asset_count", int(self.asset_count or 0))
        object.__setattr__(
            self,
            "ready_asset_count",
            int(self.ready_asset_count or 0),
        )
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
