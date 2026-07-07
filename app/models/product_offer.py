"""Typed product offer payload with legacy content compatibility."""

from dataclasses import dataclass
from typing import Any, Mapping

from app.models.product import Product, delivery_mode_value_for_delivery_type


@dataclass(frozen=True)
class ProductOffer:
    product: Product
    offer_type: str
    reason: str
    score: int
    # Phase 1 compatibility: this is currently the product media_link.
    # Future Delivery Type cleanup should separate delivery permission from
    # provider checkout or publishing URLs.
    checkout_url: str | None
    metadata: Mapping[str, Any]

    @property
    def fulfillment_strategy(self):
        return self.product.fulfillment_strategy

    @property
    def content_tag(self) -> str:
        return f"product_{self.product.id}"

    @property
    def price(self):
        price = (self.product.price_cents or 0) / 100
        return int(price) if price.is_integer() else price

    @property
    def tier(self) -> str:
        if self.product.price_cents is None or self.product.price_cents <= 1500:
            return "low"
        if self.product.price_cents <= 3500:
            return "high"
        return "premium"

    @property
    def caption(self) -> str:
        return self.product.description or self.product.display_name

    def to_legacy_payload(self, persona: str) -> dict:
        # Legacy external adapter. ProductRecommendationService now routes its
        # runtime path through CMSContractService before building this shape.
        product = self.product
        product_metadata = dict(product.metadata or {})
        offer_metadata = dict(self.metadata or {})
        delivery_mode = delivery_mode_value_for_delivery_type(
            product.delivery_type
        )
        requires_payment = delivery_mode == "paid"
        return {
            "id": None,
            "content_item_id": None,
            "product_id": str(product.id),
            "tag": self.content_tag,
            "type": self.offer_type,
            "tier": self.tier,
            "price": self.price,
            "caption": self.caption,
            "checkout_url": self.checkout_url,
            "fanvue_link": self.checkout_url,
            "persona": persona,
            "classification": self.offer_type.upper(),
            "file_path": None,
            "file_name": product.display_name,
            "blurred_preview_path": None,
            "fanvue_media_preview_uuid": None,
            "fanvue_media_full_uuid": None,
            "fanvue_ptv_set_id": None,
            "source": "product",
            "recommendation_reason": self.reason,
            "recommendation_score": self.score,
            "fulfillment_strategy": self.fulfillment_strategy.value,
            "recommended_fulfillment_strategy": self.fulfillment_strategy.value,
            "fulfillment_status": product.fulfillment_status.value,
            "delivery_type": product.delivery_type.value,
            "delivery_permission_mode": delivery_mode,
            "delivery_allowed": True,
            "delivery_requires_payment": requires_payment,
            "delivery_permission_price_cents": product.price_cents,
            "delivery_permission_reason": None,
            "product_type": product.product_type.value,
            "product_status": product.status.value,
            "product_display_name": product.display_name,
            "product_internal_name": product.internal_name,
            "product_tags": list(product.tags),
            "product_themes": list(product.themes),
            "product_metadata": product_metadata,
            "product_offer_metadata": offer_metadata,
        }
