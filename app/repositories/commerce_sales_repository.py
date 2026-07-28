"""Narrow adapter over the authoritative Commercial Fulfillment boundary."""
from app.services.commercial_fulfillment_service import CommercialFulfillmentService


class CommerceSalesRepository:
    """Prevents sales consumers from accessing commerce persistence directly."""

    def __init__(self, fulfillment_service=None) -> None:
        self.fulfillments = fulfillment_service or CommercialFulfillmentService()

    def list_eligible(
        self, *, creator_profile_id: int, primary_sales_channel: str,
        offering_type: str | None, page: int, page_size: int,
    ):
        return self.fulfillments.list_fulfillable(
            creator_profile_id=creator_profile_id,
            primary_sales_channel=primary_sales_channel,
            offering_type=offering_type,
            page=page,
            page_size=page_size,
        )

    def get_eligible(
        self, offering_id, *, creator_profile_id: int,
    ):
        return self.fulfillments.get_fulfillment(
            offering_id, creator_profile_id=creator_profile_id
        )
