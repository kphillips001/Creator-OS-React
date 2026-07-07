"""Build typed ProductOffer payloads from catalog Products."""

from app.models.product import Product
from app.models.product_offer import ProductOffer


class ProductOfferService:
    def build_offer(
        self,
        *,
        product: Product,
        offer_type: str,
        reason: str,
        score: int,
        user_memory: dict | None = None,
    ) -> ProductOffer:
        user_memory = user_memory or {}
        # Compatibility boundary: checkout_url is still backed by Product.media_link
        # until publishing/delivery contracts fully own runtime fulfillment.
        return ProductOffer(
            product=product,
            offer_type=offer_type,
            reason=reason,
            score=score,
            checkout_url=product.media_link,
            metadata={
                "builder": "ProductOfferService",
                "creator_profile_id": product.creator_profile_id,
                "legacy_content_item_id": product.legacy_content_item_id,
                "requested_offer_type": offer_type,
                "recommendation_reason": reason,
                "recommendation_score": score,
                "intent_score": user_memory.get("intent_score"),
                "preferred_content_theme": user_memory.get(
                    "preferred_content_theme"
                ),
                "user_value_tier": user_memory.get("user_value_tier"),
            },
        )
