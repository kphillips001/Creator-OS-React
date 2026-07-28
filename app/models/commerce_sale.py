"""Consumer-safe offering projection returned by the commerce decision engine."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class CommerceSale:
    offering_id: UUID
    publication_id: UUID
    title: str
    description: str | None
    offering_type: str
    price_minor: int
    currency: str
    primary_sales_channel: str
    hero_asset_id: int
    delivery_url: str
    provider: str
    provider_resource_id: str
    published_at: datetime
