"""Provider-neutral, consumer-safe Commercial Fulfillment projection."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class CommercialFulfillment:
    offering_id: UUID
    title: str
    description: str | None
    offering_type: str
    primary_sales_channel: str
    price_minor: int | None
    currency: str
    hero_asset_id: int
    ordered_asset_ids: tuple[int, ...]
    publication_id: UUID | None
    provider: str | None
    provider_resource_id: str | None
    delivery_url: str | None
    publication_status: str | None
    provider_resource_status: str
    last_reconciled_at: datetime | None
    published_at: datetime | None
    fulfillable: bool
    ineligibility_reason: str | None
    eligible_for_ai_chat: bool
    eligible_for_telegram_wall: bool
