"""Commercial Offering domain, distinct from canonical Assets and Products."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class CommercialOfferingType(str, Enum):
    SINGLE_IMAGE = "SINGLE_IMAGE"
    PHOTOSET = "PHOTOSET"
    VIDEO = "VIDEO"
    STORY = "STORY"
    STORY_SET = "STORY_SET"
    BUNDLE = "BUNDLE"


class PrimarySalesChannel(str, Enum):
    AI_CHAT = "AI_CHAT"
    TELEGRAM_WALL = "TELEGRAM_WALL"


class CommercialOfferingStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class CommercialOfferingAsset:
    asset_id: int
    position: int
    is_hero: bool


@dataclass(frozen=True)
class CommercialOffering:
    offering_id: UUID
    creator_profile_id: int
    offering_type: CommercialOfferingType
    title: str
    description: str | None
    hero_asset_id: int
    primary_sales_channel: PrimarySalesChannel
    status: CommercialOfferingStatus
    assets: tuple[CommercialOfferingAsset, ...]
    created_at: datetime
    updated_at: datetime
    price_minor: int | None = None
    currency: str = "USD"
