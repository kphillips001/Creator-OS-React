"""Product-first bridge for legacy content recommendation runtime.

Boundary note: this service adapts structured Product/CMS records into the
legacy payload shape consumed by DecisionEngine. It should not own Asset
storage, publishing, or conversation timing decisions.
"""

from app.contracts.cms import OfferCandidate
from app.models.product import (
    Product,
    ProductFulfillmentStatus,
    ProductStatus,
    provider_neutral_fulfillment_label,
)
from app.models.product_offer import ProductOffer
from app.models.ownership_intelligence import OwnershipIdentity
from app.repositories.product_repository import ProductRepository
from app.services.cms_contract_service import CMSContractService
from app.services.product_offer_service import ProductOfferService
from app.services.ownership_intelligence_service import OwnershipIntelligenceService


class ProductRecommendationService:
    def __init__(
        self,
        *,
        product_repository: ProductRepository | None = None,
        entitlement_repository=None,
        ownership_intelligence: OwnershipIntelligenceService | None = None,
        product_offer_service: ProductOfferService | None = None,
        cms_contract_service: CMSContractService | None = None,
        content_service=None,
        logger=None,
    ):
        self.products = product_repository or ProductRepository()
        # Kept as a constructor compatibility argument; ownership reads are
        # canonicalized through Ownership Intelligence.
        del entitlement_repository
        self.ownership_intelligence = (
            ownership_intelligence or OwnershipIntelligenceService()
        )
        self.product_offers = product_offer_service or ProductOfferService()
        self.cms_contracts = cms_contract_service or CMSContractService()
        self.content_service = content_service
        self.logger = logger
        self.last_offer_candidate_contract: OfferCandidate | None = None

    def get_content(
        self,
        offer_type: str,
        persona: str = "ava",
        user_memory: dict | None = None,
    ):
        offer, contract = self.recommend_contract(
            offer_type=offer_type,
            persona=persona,
            user_memory=user_memory,
        )
        if offer:
            payload = self.build_legacy_content_payload(
                contract,
                persona,
                source_offer=offer,
            )
            self._log(
                "info",
                "[PRODUCT RECOMMENDATION SELECTED] "
                f"product_id={payload.get('product_id')} "
                f"tag={payload.get('tag')} "
                f"fulfillment_strategy={payload.get('fulfillment_strategy')} "
                f"reason={payload.get('recommendation_reason')}",
            )
            return payload

        self._log(
            "info",
            "[PRODUCT RECOMMENDATION FALLBACK] "
            "No eligible active product; using ContentService.get_content()",
        )
        if not self.content_service:
            return None
        return self.content_service.get_content(
            offer_type,
            persona,
            user_memory,
        )

    def get_offer_candidate(
        self,
        *,
        offer_type: str,
        persona: str = "ava",
        user_memory: dict | None = None,
    ) -> OfferCandidate | None:
        _offer, contract = self.recommend_contract(
            offer_type=offer_type,
            persona=persona,
            user_memory=user_memory,
        )
        return contract

    def recommend_contract(
        self,
        *,
        offer_type: str,
        persona: str = "ava",
        user_memory: dict | None = None,
    ) -> tuple[ProductOffer | None, OfferCandidate | None]:
        offer = self.recommend(
            offer_type=offer_type,
            persona=persona,
            user_memory=user_memory,
        )
        contract = None
        if offer:
            delivery_permission = self.cms_contracts.build_delivery_permission(
                subject_id=offer.product.id,
                product=offer.product,
            )
            contract = self.cms_contracts.build_offer_candidate(
                offer,
                delivery_permission=delivery_permission,
            )
        self.last_offer_candidate_contract = contract
        return offer, contract

    def build_legacy_content_payload(
        self,
        offer_candidate: OfferCandidate,
        persona: str,
        *,
        source_offer: ProductOffer | None = None,
    ) -> dict:
        product = offer_candidate.product
        source_product = source_offer.product if source_offer else None
        product_metadata = dict(getattr(source_product, "metadata", {}) or {})
        offer_metadata = dict(
            getattr(source_offer, "metadata", {}) if source_offer else {}
        )
        product_id = product.product_id if product else None
        product_type = (
            getattr(getattr(source_product, "product_type", None), "value", None)
            or (product.product_type.upper() if product else None)
        )
        product_status = (
            getattr(getattr(source_product, "status", None), "value", None)
            or (
                ProductStatus.ACTIVE.value
                if product and product.availability.value == "available"
                else None
            )
        )
        fulfillment_strategy = getattr(
            getattr(source_product, "fulfillment_strategy", None),
            "value",
            None,
        )
        fulfillment_status = getattr(
            getattr(source_product, "fulfillment_status", None),
            "value",
            None,
        )
        delivery_type = (
            product.delivery_type.value
            if product and product.delivery_type
            else None
        )
        delivery_permission = offer_candidate.delivery_permission
        delivery_mode = (
            delivery_permission.delivery_mode.value
            if delivery_permission
            else None
        )
        checkout_url = source_offer.checkout_url if source_offer else None
        price = (offer_candidate.price_cents or 0) / 100
        price = int(price) if price.is_integer() else price
        tier = self._price_tier(offer_candidate.price_cents)

        return {
            "id": None,
            "content_item_id": None,
            "product_id": product_id,
            "tag": f"product_{product_id}",
            "type": offer_candidate.offer_kind.value,
            "tier": tier,
            "price": price,
            "caption": offer_candidate.description
            or (product.description if product else offer_candidate.title),
            "checkout_url": checkout_url,
            "fanvue_link": checkout_url,
            "persona": persona,
            "classification": offer_candidate.offer_kind.value.upper(),
            "file_path": None,
            "file_name": product.title if product else offer_candidate.title,
            "blurred_preview_path": None,
            "fanvue_media_preview_uuid": None,
            "fanvue_media_full_uuid": None,
            "fanvue_ptv_set_id": None,
            "source": "product",
            "recommendation_reason": offer_candidate.reason,
            "recommendation_score": offer_candidate.score,
            "fulfillment_strategy": fulfillment_strategy,
            "provider_neutral_fulfillment": provider_neutral_fulfillment_label(
                fulfillment_strategy
            ),
            "recommended_fulfillment_strategy": fulfillment_strategy,
            "fulfillment_status": fulfillment_status,
            "delivery_type": delivery_type,
            "delivery_permission_mode": delivery_mode,
            "delivery_allowed": (
                delivery_permission.allowed if delivery_permission else None
            ),
            "delivery_requires_payment": (
                delivery_permission.requires_payment
                if delivery_permission
                else None
            ),
            "delivery_permission_price_cents": (
                delivery_permission.price_cents if delivery_permission else None
            ),
            "delivery_permission_reason": (
                delivery_permission.reason if delivery_permission else None
            ),
            "product_type": product_type,
            "product_status": product_status,
            "product_display_name": product.title if product else None,
            "product_internal_name": getattr(
                source_product,
                "internal_name",
                product.title if product else None,
            ),
            "product_tags": list(product.tags if product else ()),
            "product_themes": list(product.themes if product else ()),
            "product_metadata": product_metadata,
            "product_offer_metadata": offer_metadata,
        }

    def offer_candidate_to_legacy_payload(
        self,
        offer_candidate: OfferCandidate,
        persona: str,
        *,
        source_offer: ProductOffer | None = None,
    ) -> dict:
        """Compatibility alias for callers still expecting legacy content dicts."""
        return self.build_legacy_content_payload(
            offer_candidate,
            persona,
            source_offer=source_offer,
        )

    def recommend(
        self,
        *,
        offer_type: str,
        persona: str = "ava",
        user_memory: dict | None = None,
    ) -> ProductOffer | None:
        user_memory = user_memory or {}
        creator_profile_id = self._creator_profile_id(user_memory)
        normalized_offer_type = self._normalize_offer_type(offer_type)

        if not creator_profile_id:
            self._log_rejected(
                None,
                "missing_creator_profile_id",
            )
            return None

        products = self.products.list_products(
            creator_profile_id=creator_profile_id,
            status=ProductStatus.ACTIVE,
            include_archived=False,
        )
        ownership = self._ownership_answer(
            user_memory, creator_profile_id=creator_profile_id
        )

        candidates: list[ProductOffer] = []
        for product in products:
            reason = self._rejection_reason(
                product, user_memory, ownership_answer=ownership
            )
            if reason:
                self._log_rejected(product, reason)
                continue

            score, reason = self._score_product(
                product,
                normalized_offer_type,
                user_memory,
            )
            candidates.append(
                self.product_offers.build_offer(
                    product=product,
                    offer_type=normalized_offer_type,
                    reason=reason,
                    score=score,
                    user_memory=user_memory,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                item.score,
                item.product.activated_at or item.product.updated_at,
            ),
            reverse=True,
        )
        return candidates[0]

    def eligibility_for_product(
        self,
        product: Product,
        *,
        user_memory: dict | None = None,
    ) -> dict[str, str | bool | None]:
        """Expose the existing recommendation gate as a read-only projection."""
        memory = user_memory or {}
        ownership = self._ownership_answer(
            memory, creator_profile_id=product.creator_profile_id or 0
        )
        reason = self._rejection_reason(
            product, memory, ownership_answer=ownership
        )
        return {
            "eligible": reason is None,
            "reason": reason,
        }

    def _rejection_reason(
        self,
        product: Product,
        user_memory: dict,
        ownership_answer=None,
    ) -> str | None:
        if product.status == ProductStatus.DISABLED:
            return "disabled"
        if product.status == ProductStatus.ARCHIVED:
            return "archived"
        if product.status != ProductStatus.ACTIVE:
            return f"not_active:{product.status.value}"
        if product.fulfillment_status != ProductFulfillmentStatus.READY:
            return f"fulfillment_not_ready:{product.fulfillment_status.value}"

        if ownership_answer is None or not ownership_answer.evidence_sufficient:
            return "ownership_evidence_insufficient"
        if self.ownership_intelligence.owns_product(
            ownership_answer, product.id
        ):
            return "already_entitled"

        if self._recently_offered(product, user_memory):
            return "recently_offered"

        return None

    def _ownership_answer(self, user_memory, *, creator_profile_id):
        return self.ownership_intelligence.answer(OwnershipIdentity(
            creator_profile_id=int(creator_profile_id or 0),
            fanvue_account_id=int(user_memory.get("fanvue_account_id") or 0),
            external_fanvue_user_uuid=user_memory.get(
                "external_fanvue_user_uuid"
            ),
            telegram_user_id=user_memory.get("telegram_user_id"),
            legacy_fanvue_user_id=(
                str(user_memory["fanvue_user_id"])
                if user_memory.get("fanvue_user_id") is not None else None
            ),
            core_user_id=user_memory.get("core_user_id"),
        ))

    def _recently_offered(
        self,
        product: Product,
        user_memory: dict,
    ) -> bool:
        product_id = str(product.id)
        product_tag = f"product_{product_id}"
        recent_product_ids = {
            str(value)
            for value in user_memory.get("recently_offered_product_ids", [])
            if value
        }

        recent_tags = [
            user_memory.get("last_offer_content_tag"),
            user_memory.get("last_content_sent_tag"),
            user_memory.get("last_selected_content_tag"),
            user_memory.get("last_content_tag"),
        ]
        seen_content_tags = user_memory.get("seen_content_tags") or []
        if isinstance(seen_content_tags, list):
            recent_tags.extend(seen_content_tags[-5:])

        normalized_recent_tags = {str(value) for value in recent_tags if value}
        return (
            product_id in recent_product_ids
            or product_tag in normalized_recent_tags
        )

    def _score_product(
        self,
        product: Product,
        offer_type: str,
        user_memory: dict,
    ) -> tuple[int, str]:
        score = 10
        reasons = ["active_product"]

        intent_score = int(user_memory.get("intent_score") or 0)
        preferred_theme = user_memory.get("preferred_content_theme")
        user_value_tier = (user_memory.get("user_value_tier") or "").lower()

        if product.activated_at:
            score += 5
            reasons.append("activated")

        if preferred_theme and preferred_theme in product.themes:
            score += 20
            reasons.append("theme_match")

        if offer_type == "tease" and (
            product.price_cents is None or product.price_cents <= 1500
        ):
            score += 15
            reasons.append("tease_price_fit")
        elif offer_type == "vip" and product.price_cents:
            if 1500 < product.price_cents <= 5000:
                score += 15
                reasons.append("vip_price_fit")
        elif offer_type == "premium" and product.price_cents:
            if product.price_cents >= 3500:
                score += 15
                reasons.append("premium_price_fit")

        if intent_score >= 80 and product.price_cents and product.price_cents >= 3500:
            score += 10
            reasons.append("high_intent_high_value")

        if user_value_tier in {"high", "premium", "whale", "buyer"}:
            score += 5
            reasons.append("buyer_value_fit")

        return score, ",".join(reasons)

    def _creator_profile_id(self, user_memory: dict) -> int | None:
        value = (
            user_memory.get("creator_profile_id")
            or user_memory.get("active_creator_profile_id")
        )
        if not value and isinstance(user_memory.get("creator_profile"), dict):
            value = user_memory["creator_profile"].get("id")

        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _normalize_offer_type(self, offer_type: str) -> str:
        normalized = (offer_type or "tease").lower()
        if normalized.endswith("_offer"):
            normalized = normalized.replace("_offer", "")
        if normalized == "teaser":
            normalized = "tease"
        if normalized not in {"tease", "vip", "premium"}:
            normalized = "tease"
        return normalized

    def _price_tier(self, price_cents: int | None) -> str:
        if price_cents is None or price_cents <= 1500:
            return "low"
        if price_cents <= 3500:
            return "high"
        return "premium"

    def _log_rejected(self, product: Product | None, reason: str) -> None:
        product_id = str(product.id) if product else None
        self._log(
            "info",
            "[PRODUCT RECOMMENDATION REJECTED] "
            f"product_id={product_id} reason={reason}",
        )

    def _log(self, level: str, message: str) -> None:
        if self.logger:
            getattr(self.logger, level)(message)
        else:
            print(message)
