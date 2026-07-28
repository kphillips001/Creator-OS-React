"""Provider-neutral commerce eligibility and deterministic recommendation engine."""
from __future__ import annotations

from app.models.commerce_sale import CommerceSale
from app.repositories.commerce_sales_repository import CommerceSalesRepository


class CommerceSalesDecisionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CommerceSalesService:
    """Validate selected offerings and support explicit legacy compatibility."""

    SUPPORTED_CHANNEL = "AI_CHAT"
    SUPPORTED_TYPES = frozenset({"SINGLE_IMAGE", "PHOTOSET", "VIDEO"})

    def __init__(self, repository=None) -> None:
        self.repository = repository or CommerceSalesRepository()

    def list_eligible_offerings(
        self, *, creator_profile_id: int, primary_sales_channel: str,
        conversation_context=None, requested_media_type=None,
        requested_themes=None, customer_history=None, page=1, page_size=20,
    ):
        del conversation_context, requested_themes, customer_history
        channel = str(primary_sales_channel or "").strip().upper()
        if channel != self.SUPPORTED_CHANNEL:
            raise CommerceSalesDecisionError(
                "UNSUPPORTED_SALES_CHANNEL",
                "Commerce Sales currently supports AI_CHAT only.",
            )
        offering_type = self._offering_type(requested_media_type)
        fulfillments, total, current_page = self.repository.list_eligible(
            creator_profile_id=int(creator_profile_id),
            primary_sales_channel=channel,
            offering_type=offering_type,
            page=max(1, int(page)),
            page_size=max(1, min(100, int(page_size))),
        )
        sales = tuple(self._sale(item) for item in fulfillments)
        return sales, total, current_page

    def recommend_best(
        self, *, creator_profile_id: int, primary_sales_channel: str,
        conversation_context=None, requested_media_type=None,
        requested_themes=None, customer_history=None,
    ) -> CommerceSale | None:
        """Compatibility selector; configured conversation runtimes do not use it."""
        items, _, _ = self.list_eligible_offerings(
            creator_profile_id=creator_profile_id,
            primary_sales_channel=primary_sales_channel,
            conversation_context=conversation_context,
            requested_media_type=requested_media_type,
            requested_themes=requested_themes,
            customer_history=customer_history,
            page=1, page_size=1,
        )
        return items[0] if items else None

    def resolve_recommended_offering(
        self, *, offering_id, creator_profile_id: int,
    ) -> CommerceSale | None:
        """Resolve an already-selected offering without making a new decision."""
        item = self.repository.get_eligible(
            offering_id, creator_profile_id=int(creator_profile_id)
        )
        return self._sale(item) if item is not None else None

    @classmethod
    def _offering_type(cls, value):
        if value is None or not str(value).strip():
            return None
        normalized = str(value).strip().upper()
        if normalized not in cls.SUPPORTED_TYPES:
            raise CommerceSalesDecisionError(
                "UNSUPPORTED_OFFERING_TYPE",
                f"Commerce Sales does not support offering type {normalized}.",
            )
        return normalized

    @staticmethod
    def _sale(item) -> CommerceSale:
        if not (
            item.fulfillable
            and item.eligible_for_ai_chat
            and item.publication_status == "LIVE"
            and item.provider_resource_status == "PRESENT"
            and item.delivery_url
            and item.provider
            and item.provider_resource_id
            and item.published_at
            and item.price_minor is not None
        ):
            raise CommerceSalesDecisionError(
                "INELIGIBLE_FULFILLMENT_PROJECTION",
                "Commercial Fulfillment returned an ineligible sales offering.",
            )
        return CommerceSale(
            offering_id=item.offering_id,
            publication_id=item.publication_id,
            title=item.title,
            description=item.description,
            offering_type=item.offering_type,
            price_minor=int(item.price_minor),
            currency=item.currency,
            primary_sales_channel=item.primary_sales_channel,
            hero_asset_id=item.hero_asset_id,
            delivery_url=item.delivery_url,
            provider=item.provider,
            provider_resource_id=item.provider_resource_id,
            published_at=item.published_at,
        )
