"""Typed, provider-neutral context passed from conversation decisions to commerce."""
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CommerceConversationContext:
    creator_profile_id: int
    purchase_intent: bool
    requested_media_type: str | None
    requested_themes: tuple[str, ...]
    relationship_level: str
    customer_identifier: str
    conversation_identifier: str
    recommendation_reason: str
    primary_sales_channel: str = "AI_CHAT"


@dataclass(frozen=True)
class ChatCommerceDecision:
    lookup_attempted: bool
    requested_media_type: str | None
    requested_themes: tuple[str, ...]
    offering: Any | None
    recommendation_reason: str | None
    no_offering_reason: str | None
    selection_source: str = "NONE"
    legacy_recommendation_used: bool = False
    product_context: Mapping[str, Any] | None = None

    def diagnostics(self) -> Mapping[str, Any]:
        offering = self.offering
        return {
            "commerce_lookup_attempted": self.lookup_attempted,
            "requested_media_type": self.requested_media_type,
            "requested_themes": list(self.requested_themes),
            "offering_selected": offering is not None,
            "offering_id": str(offering.offering_id) if offering else None,
            "publication_id": (
                str(getattr(offering, "publication_id"))
                if offering and getattr(offering, "publication_id", None)
                else None
            ),
            "offering_type": offering.offering_type if offering else None,
            "offering_title": offering.title if offering else None,
            "price_minor": offering.price_minor if offering else None,
            "currency": offering.currency if offering else None,
            "primary_sales_channel": (
                offering.primary_sales_channel if offering else "AI_CHAT"
            ),
            "provider": offering.provider if offering else None,
            "provider_resource_id": (
                offering.provider_resource_id if offering else None
            ),
            "fulfillable": offering is not None,
            "recommendation_reason": self.recommendation_reason,
            "no_offering_reason": self.no_offering_reason,
            "delivery_url": offering.delivery_url if offering else None,
            "selection_source": self.selection_source,
            "legacy_recommendation_used": self.legacy_recommendation_used,
        }
