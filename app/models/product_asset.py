"""Relationship between a sellable product and a content-backed asset.

Phase 1 compatibility: ordered ProductAsset rows currently carry some
Experience-like composition such as covers, chapters, and multi-asset sets.
Future Experience architecture should own reusable asset grouping before
Products apply commerce and publishing rules.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


class ProductAssetRole(str, Enum):
    PRIMARY = "primary"
    PREVIEW = "preview"
    COVER = "cover"
    CHAPTER = "chapter"
    BONUS = "bonus"
    ATTACHMENT = "attachment"
    FULFILLMENT = "fulfillment"


class AssetDeliveryMode(str, Enum):
    # Asset-level delivery mode within a Product. This is not yet the
    # business-level Delivery Type such as FREE or PAID.
    PREVIEW = "preview"
    PROTECTED = "protected"
    DOWNLOAD = "download"
    STREAM = "stream"
    MANUAL = "manual"


@dataclass(frozen=True)
class ProductAsset:
    product_id: UUID
    asset_id: int
    position: int
    role: ProductAssetRole
    is_required: bool
    delivery_mode: AssetDeliveryMode
    metadata: Mapping[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ProductAsset":
        return cls(
            product_id=row["product_id"],
            asset_id=row["asset_id"],
            position=row["position"],
            role=ProductAssetRole(row["role"]),
            is_required=bool(row["is_required"]),
            delivery_mode=AssetDeliveryMode(row["delivery_mode"]),
            metadata=row.get("metadata") or {},
            created_at=row["created_at"],
        )
