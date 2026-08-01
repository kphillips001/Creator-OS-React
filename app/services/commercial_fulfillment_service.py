"""Provider-neutral Commercial Fulfillment read boundary."""
from __future__ import annotations
from uuid import UUID

from app.models.commercial_fulfillment import CommercialFulfillment
from app.repositories.commercial_fulfillment_repository import (
    CommercialFulfillmentRepository,
)


class CommercialFulfillmentService:
    def __init__(self, repository=None) -> None:
        self.repository = repository or CommercialFulfillmentRepository()

    def get_fulfillment(self, offering_id, *, creator_profile_id: int):
        row = self.repository.get(
            UUID(str(offering_id)), creator_profile_id=creator_profile_id
        )
        return self._hydrate(row) if row else None

    def list_fulfillable(
        self, *, creator_profile_id: int, primary_sales_channel: str,
        offering_type=None, provider=None, page=1, page_size=20,
    ):
        channel = self._choice(
            primary_sales_channel, {"AI_CHAT", "TELEGRAM_WALL"}, "sales channel"
        )
        normalized_type = str(offering_type).upper() if offering_type else None
        normalized_provider = str(provider).upper() if provider else None
        rows, total, current_page = self.repository.list_fulfillable(
            creator_profile_id=creator_profile_id,
            primary_sales_channel=channel,
            offering_type=normalized_type, provider=normalized_provider,
            page=max(1, int(page)), page_size=max(1, min(100, int(page_size))),
        )
        return tuple(self._hydrate(row) for row in rows), total, current_page

    @classmethod
    def _hydrate(cls, row):
        reason = cls._reason(row)
        fulfillable = reason is None
        channel = row["primary_sales_channel"]
        return CommercialFulfillment(
            offering_id=UUID(str(row["offering_id"])),
            title=row["title"], description=row.get("description"),
            offering_type=row["offering_type"],
            primary_sales_channel=channel,
            price_minor=row.get("price_minor"), currency=row["currency"],
            hero_asset_id=int(row["hero_asset_id"]),
            ordered_asset_ids=tuple(int(value) for value in row["asset_ids"]),
            publication_id=(
                UUID(str(row["publication_id"])) if row.get("publication_id") else None
            ),
            provider=row.get("provider"),
            provider_resource_id=(
                row.get("external_product_id") if fulfillable else None
            ),
            delivery_url=row.get("delivery_url") if fulfillable else None,
            publication_status=row.get("publication_status"),
            provider_resource_status=row.get("provider_resource_status") or "UNVERIFIED",
            last_reconciled_at=row.get("last_reconciled_at"),
            published_at=row.get("published_at"),
            fulfillable=fulfillable, ineligibility_reason=reason,
            eligible_for_ai_chat=fulfillable and channel == "AI_CHAT",
            eligible_for_telegram_wall=fulfillable and channel == "TELEGRAM_WALL",
        )

    @staticmethod
    def _reason(row):
        if row["offering_status"] == "ARCHIVED":
            return "OFFERING_ARCHIVED"
        if row.get("price_minor") is None or not 300 <= int(row["price_minor"]) <= 50000:
            return "PRICE_INVALID"
        if row.get("publication_status") != "LIVE":
            return "PUBLICATION_NOT_LIVE"
        if row.get("provider_resource_status") != "PRESENT":
            return "PROVIDER_RESOURCE_NOT_PRESENT"
        if not row.get("external_product_id") or not row.get("delivery_url"):
            return "DELIVERY_ARTIFACT_MISSING"
        expected = (
            "SINGLE_PPV" if row["offering_type"] in {"SINGLE_IMAGE", "VIDEO"}
            else "PHOTOSET" if row["offering_type"] == "PHOTOSET"
            else "BUNDLE" if row["offering_type"] == "BUNDLE" else None
        )
        if expected is None or any(value != expected for value in row["destinations"]):
            return "ASSET_COMMITMENT_INCONSISTENT"
        return None

    @staticmethod
    def _choice(value, allowed, label):
        normalized = str(value or "").strip().upper()
        if normalized not in allowed:
            raise ValueError(f"Unsupported {label}: {value}")
        return normalized
