"""Read-only presentation composition for the React Product Workspace."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from app.services.product_availability_service import ProductAvailabilityService
from app.services.product_business_service import ProductBusinessService
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_lifecycle_service import ProductLifecycleService
from app.services.product_performance_service import ProductPerformanceService
from app.services.product_recommendation_service import ProductRecommendationService
from app.services.product_review_service import ProductReviewService


class ProductWorkspaceService:
    """Compose existing Product read models without owning domain decisions."""

    def __init__(
        self,
        *,
        product_catalog_service: ProductCatalogService | None = None,
        product_review_service: ProductReviewService | None = None,
        product_lifecycle_service: ProductLifecycleService | None = None,
        product_availability_service: ProductAvailabilityService | None = None,
        product_business_service: ProductBusinessService | None = None,
        product_performance_service: ProductPerformanceService | None = None,
        product_recommendation_service: ProductRecommendationService | None = None,
    ) -> None:
        self.catalog = product_catalog_service or ProductCatalogService()
        self.reviews = product_review_service or ProductReviewService(
            product_catalog_service=self.catalog,
        )
        self.lifecycle = product_lifecycle_service or ProductLifecycleService()
        self.business = product_business_service or ProductBusinessService(
            product_catalog_service=self.catalog,
            product_lifecycle_service=self.lifecycle,
        )
        self.availability = product_availability_service or ProductAvailabilityService(
            product_catalog_service=self.catalog,
            product_business_service=self.business,
            product_lifecycle_service=self.lifecycle,
        )
        self.performance = product_performance_service or ProductPerformanceService(
            product_catalog_service=self.catalog,
            product_business_service=self.business,
        )
        self.recommendations = (
            product_recommendation_service or ProductRecommendationService()
        )

    def list_products(
        self,
        *,
        creator_profile_id: int,
        include_archived: bool = True,
        limit: int = 500,
    ) -> tuple[dict[str, Any], ...]:
        displays = self.catalog.list_workspace_display_models(
            creator_profile_id=int(creator_profile_id),
            include_archived=include_archived,
            limit=limit,
        )
        return tuple(self._project(display) for display in displays)

    def get_product(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int,
    ) -> dict[str, Any] | None:
        product = self.catalog.products.get_by_id(
            product_id,
            creator_profile_id=int(creator_profile_id),
        )
        if product is None:
            return None
        return self._project(self.catalog.load_display_model(product))

    def summarize(self, products: Iterable[dict[str, Any]]) -> dict[str, int]:
        items = tuple(products)
        return {
            "total": len(items),
            "drafts": self._count(items, "productStatus", "DRAFT"),
            "needsReview": self._count(items, "approvalStatus", "NEEDS_REVIEW"),
            "readyToPublish": self._count(items, "approvalStatus", "READY_TO_PUBLISH"),
            "active": self._count(items, "productStatus", "ACTIVE"),
            "available": self._count(items, "availabilityStatus", "AVAILABLE"),
            "waitingForMediaLink": self._count(items, "availabilityStatus", "WAITING_FOR_MEDIA_LINK"),
            "needsAttention": self._count(items, "availabilityStatus", "NEEDS_ATTENTION"),
            "recommendationEligible": sum(
                1 for item in items if item["recommendationEligibility"]["eligible"]
            ),
        }

    @staticmethod
    def _count(items: tuple[dict[str, Any], ...], key: str, value: str) -> int:
        return sum(1 for item in items if item.get(key) == value)

    def _project(self, display: Any) -> dict[str, Any]:
        product = display.product
        review = self.reviews.build_review_from_display(display)
        lifecycle = self.lifecycle.build_lifecycle(
            product_display=display,
            product_review=review,
        )
        business = self.business.build_snapshot(
            product=product,
            product_display=display,
            lifecycle=lifecycle,
        )
        availability = self.availability.build_availability(
            product=product,
            product_business_snapshot=business,
            lifecycle=lifecycle,
        )
        performance = self.performance.build_performance(
            product=product,
            product_business_snapshot=business,
        )
        recommendation = self.recommendations.eligibility_for_product(
            product,
            user_memory={"creator_profile_id": product.creator_profile_id},
        )
        assets = tuple(display.ordered_assets or ())
        metadata = dict(product.metadata or {})
        commerce = metadata.get("commerce_intelligence") or {}
        ai_pricing = metadata.get("pricing") or (
            commerce.get("price") if isinstance(commerce, dict) else {}
        ) or {}
        return {
            "productId": str(product.id),
            "creatorProfileId": product.creator_profile_id,
            "internalName": product.internal_name,
            "displayName": product.display_name,
            "description": product.description,
            "productType": self._value(product.product_type),
            "deliveryType": self._value(product.delivery_type),
            "productStatus": self._value(product.status),
            "approvalStatus": review.approval_status,
            "reviewStatus": review.review_status,
            "productOrigin": review.product_origin,
            "priceCents": product.price_cents,
            "basePriceCents": product.base_price_cents,
            "minPriceCents": product.min_price_cents,
            "maxPriceCents": product.max_price_cents,
            "currency": product.currency,
            "tags": list(product.tags),
            "themes": list(product.themes),
            "fulfillmentStrategy": self._value(product.fulfillment_strategy),
            "fulfillmentStatus": self._value(product.fulfillment_status),
            "mediaLink": product.media_link,
            "activationSource": product.activation_source,
            "activationReason": product.activation_reason,
            "activatedAt": product.activated_at,
            "createdAt": product.created_at,
            "updatedAt": product.updated_at,
            "assetCount": len(assets),
            "coverAssetId": getattr(display.cover_asset, "id", None),
            "previewAssetId": getattr(display.preview_asset, "id", None),
            "imageUrl": self._asset_url(display.cover_asset or display.preview_asset),
            "publishingStatus": display.publishing.status,
            "publishingDetail": display.publishing.detail,
            "lifecycleStage": self._value(lifecycle.stage),
            "lifecycle": self._plain(lifecycle),
            "availabilityStatus": self._value(availability.status),
            "availability": self._plain(availability),
            "recommendationEligibility": recommendation,
            "businessHealth": self._value(business.product_health),
            "business": self._plain(business),
            "performance": self._plain(performance),
            "review": self._plain(review),
            "aiPricingRecommendation": self._plain(ai_pricing),
            "composition": [self._asset_payload(asset) for asset in assets],
            "experience": self._plain(display.experience_presentation),
            "warnings": list(review.warnings),
        }

    @staticmethod
    def _asset_url(asset: Any | None) -> str | None:
        asset_id = getattr(asset, "id", None)
        return f"/api/v1/assets/{int(asset_id)}/media" if asset_id else None

    def _asset_payload(self, asset: Any) -> dict[str, Any]:
        return {
            "assetId": int(asset.id),
            "fileName": asset.file_name,
            "mediaType": asset.media_type,
            "classification": asset.classification,
            "imageUrl": self._asset_url(asset),
        }

    @classmethod
    def _plain(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return cls._plain(asdict(value))
        if isinstance(value, dict):
            return {str(key): cls._plain(item) for key, item in value.items()}
        if isinstance(value, (tuple, list, set)):
            return [cls._plain(item) for item in value]
        return value

    @staticmethod
    def _value(value: Any) -> Any:
        return getattr(value, "value", value)
