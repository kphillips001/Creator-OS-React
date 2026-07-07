"""Product Availability read-model aggregation service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from app.models.product_availability import (
    ProductAvailability,
    ProductAvailabilityRecommendation,
    ProductAvailabilityStatus,
)
from app.models.product_business import (
    ProductBusinessAvailability,
    ProductBusinessSnapshot,
)
from app.models.product_lifecycle import ProductLifecycle, ProductLifecycleStage
from app.models.publishing_automation import (
    PublishingAutomationState,
    PublishingAutomationStatus,
)

if TYPE_CHECKING:
    from app.services.product_business_service import ProductBusinessService
    from app.services.product_catalog_service import ProductCatalogService
    from app.services.product_lifecycle_service import ProductLifecycleService
    from app.services.publishing_automation_service import PublishingAutomationService


class ProductAvailabilityService:
    """Build canonical Product Availability without mutating domain state."""

    def __init__(
        self,
        *,
        product_business_service: "ProductBusinessService | None" = None,
        product_lifecycle_service: "ProductLifecycleService | None" = None,
        publishing_automation_service: "PublishingAutomationService | None" = None,
        product_catalog_service: "ProductCatalogService | None" = None,
    ) -> None:
        self._product_business = product_business_service
        self._product_lifecycle = product_lifecycle_service
        self._publishing_automation = publishing_automation_service
        self._product_catalog = product_catalog_service

    @property
    def product_business(self) -> "ProductBusinessService":
        if self._product_business is None:
            from app.services.product_business_service import ProductBusinessService

            self._product_business = ProductBusinessService()
        return self._product_business

    @property
    def product_lifecycle(self) -> "ProductLifecycleService":
        if self._product_lifecycle is None:
            from app.services.product_lifecycle_service import ProductLifecycleService

            self._product_lifecycle = ProductLifecycleService()
        return self._product_lifecycle

    @property
    def publishing_automation(self) -> "PublishingAutomationService":
        if self._publishing_automation is None:
            from app.services.publishing_automation_service import (
                PublishingAutomationService,
            )

            self._publishing_automation = PublishingAutomationService(
                product_lifecycle_service=self.product_lifecycle,
            )
        return self._publishing_automation

    @property
    def product_catalog(self) -> "ProductCatalogService":
        if self._product_catalog is None:
            from app.services.product_catalog_service import ProductCatalogService

            self._product_catalog = ProductCatalogService()
        return self._product_catalog

    def build_availability(
        self,
        *,
        product: Any | None = None,
        product_business_snapshot: ProductBusinessSnapshot | Mapping[str, Any] | None = None,
        lifecycle: ProductLifecycle | Mapping[str, Any] | None = None,
        workflow_snapshot: Any | None = None,
        publishing_status: PublishingAutomationStatus | Mapping[str, Any] | None = None,
        publishing_projection: Any | None = None,
        publishing_job: Any | None = None,
        publishing_queue_item: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ProductAvailability:
        product_business = self._resolve_product_business(
            product_business_snapshot,
            product=product,
            lifecycle=lifecycle,
            workflow_snapshot=workflow_snapshot,
            publishing_status=publishing_status,
            publishing_projection=publishing_projection,
            publishing_job=publishing_job,
            publishing_queue_item=publishing_queue_item,
        )
        resolved_lifecycle = self._resolve_lifecycle(
            lifecycle,
            workflow_snapshot=workflow_snapshot,
            product_business_snapshot=product_business,
        )
        resolved_publishing = self._resolve_publishing(
            publishing_status,
            lifecycle=resolved_lifecycle,
            workflow_snapshot=workflow_snapshot,
            publishing_projection=publishing_projection,
            publishing_job=publishing_job,
            publishing_queue_item=publishing_queue_item,
            product_business_snapshot=product_business,
        )
        product_status = (
            self._enum_value(self._read(product, "status"))
            or self._safe_text(self._read(product_business, "product_status"))
            or self._safe_text(self._read(resolved_lifecycle, "product_status"))
        )
        status = self.determine_status(
            product_status=product_status,
            lifecycle=resolved_lifecycle,
            publishing_status=resolved_publishing,
            product_business_snapshot=product_business,
        )
        recommendation = self.recommend_next_action(
            status,
            lifecycle=resolved_lifecycle,
            publishing_status=resolved_publishing,
        )
        telegram_ready = bool(
            self._read(product_business, "availability")
            == ProductBusinessAvailability.TELEGRAM_READY
            or self._read(resolved_lifecycle, "telegram_ready")
            or self._read(resolved_publishing, "telegram_ready")
        )
        return ProductAvailability(
            product_id=(
                self._safe_text(self._read(product, "id"))
                or self._safe_text(self._read(product_business, "product_id"))
                or self._safe_text(self._read(resolved_lifecycle, "product_id"))
                or self._safe_text(self._read(resolved_publishing, "product_id"))
            ),
            status=status,
            recommendation=recommendation,
            product_status=product_status,
            lifecycle=resolved_lifecycle,
            publishing_status=resolved_publishing,
            product_business_snapshot=product_business,
            publishing_state=self._enum_value(self._read(resolved_publishing, "state")),
            media_link_status=self._safe_text(
                self._read(resolved_publishing, "media_link_status")
                or self._read(resolved_lifecycle, "media_link_status")
            ),
            provider_status=self._safe_text(
                self._read(resolved_publishing, "provider_status")
            ),
            telegram_ready=telegram_ready,
            available_for_customers=status == ProductAvailabilityStatus.AVAILABLE,
            evidence={
                "product_status": product_status,
                "lifecycle_stage": self._enum_value(
                    self._read(resolved_lifecycle, "stage")
                ),
                "publishing_state": self._enum_value(
                    self._read(resolved_publishing, "state")
                ),
                "business_availability": self._enum_value(
                    self._read(product_business, "availability")
                ),
                **dict(metadata or {}),
            },
            compatibility={
                "source": "product_availability",
                "owner": "ProductAvailabilityService",
                "read_only": True,
                "provider_neutral": True,
                "aggregation_only": True,
                "publishes_products": False,
                "modifies_products": False,
                "activates_products": False,
                "executes_telegram": False,
                "creates_products": False,
                "does_not_replace_product_status": True,
                "does_not_replace_publishing_status": True,
                "does_not_replace_product_lifecycle": True,
                "product_business_consumed": product_business is not None,
                "product_lifecycle_consumed": resolved_lifecycle is not None,
                "publishing_consumed": resolved_publishing is not None,
            },
        )

    def build_for_product_id(self, product_id: Any, **context: Any) -> ProductAvailability:
        product = self.product_catalog.products.get_by_id(product_id)
        return self.build_availability(product=product, **context)

    def determine_status(
        self,
        *,
        product_status: str | None,
        lifecycle: ProductLifecycle | None = None,
        publishing_status: PublishingAutomationStatus | None = None,
        product_business_snapshot: ProductBusinessSnapshot | None = None,
    ) -> ProductAvailabilityStatus:
        normalized_product_status = self._text(product_status)
        lifecycle_stage = self._read(lifecycle, "stage")
        publishing_state = self._read(publishing_status, "state")
        business_availability = self._read(product_business_snapshot, "availability")
        if normalized_product_status == "ARCHIVED":
            return ProductAvailabilityStatus.ARCHIVED
        if self._bool(self._read(publishing_status, "attention_required")):
            return ProductAvailabilityStatus.NEEDS_ATTENTION
        if publishing_state == PublishingAutomationState.NEEDS_ATTENTION:
            return ProductAvailabilityStatus.NEEDS_ATTENTION
        if business_availability == ProductBusinessAvailability.UNAVAILABLE:
            return ProductAvailabilityStatus.UNAVAILABLE
        if normalized_product_status == "DISABLED":
            return ProductAvailabilityStatus.UNAVAILABLE
        if publishing_state in {
            PublishingAutomationState.WAITING_FOR_MEDIA_LINK,
            PublishingAutomationState.VERIFY_MEDIA_LINK,
        }:
            return ProductAvailabilityStatus.WAITING_FOR_MEDIA_LINK
        if lifecycle_stage == ProductLifecycleStage.WAITING_FOR_MEDIA_LINK:
            return ProductAvailabilityStatus.WAITING_FOR_MEDIA_LINK
        if business_availability == ProductBusinessAvailability.WAITING_FOR_MEDIA_LINK:
            return ProductAvailabilityStatus.WAITING_FOR_MEDIA_LINK
        if publishing_state in {
            PublishingAutomationState.READY_TO_PUBLISH,
            PublishingAutomationState.QUEUED,
            PublishingAutomationState.UPLOAD_IN_PROGRESS,
        }:
            return ProductAvailabilityStatus.PUBLISHING
        if lifecycle_stage in {
            ProductLifecycleStage.APPROVED,
            ProductLifecycleStage.PUBLISHING_READY,
            ProductLifecycleStage.PUBLISHING,
        }:
            return ProductAvailabilityStatus.PUBLISHING
        if business_availability == ProductBusinessAvailability.PUBLISHING:
            return ProductAvailabilityStatus.PUBLISHING
        if normalized_product_status == "DRAFT":
            return ProductAvailabilityStatus.DRAFT
        if lifecycle_stage == ProductLifecycleStage.DRAFT:
            return ProductAvailabilityStatus.DRAFT
        if business_availability == ProductBusinessAvailability.DRAFT:
            return ProductAvailabilityStatus.DRAFT
        if normalized_product_status == "ACTIVE":
            return ProductAvailabilityStatus.AVAILABLE
        if lifecycle_stage in {
            ProductLifecycleStage.ACTIVE,
            ProductLifecycleStage.TELEGRAM_READY,
        }:
            return ProductAvailabilityStatus.AVAILABLE
        if business_availability in {
            ProductBusinessAvailability.AVAILABLE,
            ProductBusinessAvailability.TELEGRAM_READY,
        }:
            return ProductAvailabilityStatus.AVAILABLE
        return ProductAvailabilityStatus.UNAVAILABLE

    @staticmethod
    def recommend_next_action(
        status: ProductAvailabilityStatus,
        *,
        lifecycle: ProductLifecycle | None = None,
        publishing_status: PublishingAutomationStatus | None = None,
    ) -> ProductAvailabilityRecommendation:
        if status == ProductAvailabilityStatus.AVAILABLE:
            return ProductAvailabilityRecommendation(
                label="Ready to Sell",
                reason="Product is available for customers.",
            )
        if status == ProductAvailabilityStatus.WAITING_FOR_MEDIA_LINK:
            return ProductAvailabilityRecommendation(
                label="Paste Media Link",
                reason="Publishing is waiting for manual media link completion.",
            )
        if status == ProductAvailabilityStatus.PUBLISHING:
            action = ProductAvailabilityService._read(
                publishing_status,
                "next_recommended_action",
            ) or ProductAvailabilityService._read(lifecycle, "next_recommended_action")
            return ProductAvailabilityRecommendation(
                label=str(action or "Publish Product"),
                reason="Product is moving through Publishing.",
            )
        if status == ProductAvailabilityStatus.NEEDS_ATTENTION:
            return ProductAvailabilityRecommendation(
                label="Resolve Publishing",
                reason="Publishing or availability state needs attention.",
            )
        if status == ProductAvailabilityStatus.ARCHIVED:
            return ProductAvailabilityRecommendation(
                label="Archive Product",
                reason="Product is archived and unavailable to customers.",
            )
        if status == ProductAvailabilityStatus.DRAFT:
            return ProductAvailabilityRecommendation(
                label="Complete Product",
                reason="Product is still in draft state.",
            )
        return ProductAvailabilityRecommendation(
            label="Unavailable",
            reason="Product is not available for customers.",
        )

    def _resolve_product_business(
        self,
        value: ProductBusinessSnapshot | Mapping[str, Any] | None,
        **context: Any,
    ) -> ProductBusinessSnapshot | None:
        if isinstance(value, ProductBusinessSnapshot):
            return value
        if isinstance(value, Mapping):
            return self._business_from_mapping(value)
        if any(item is not None for item in context.values()):
            return self.product_business.build_snapshot(**context)
        return None

    def _resolve_lifecycle(
        self,
        lifecycle: ProductLifecycle | Mapping[str, Any] | None,
        *,
        workflow_snapshot: Any | None,
        product_business_snapshot: ProductBusinessSnapshot | None,
    ) -> ProductLifecycle | None:
        if isinstance(lifecycle, ProductLifecycle):
            return lifecycle
        if lifecycle is not None:
            return self.product_lifecycle.build_lifecycle(lifecycle)
        resolved = self._read(product_business_snapshot, "lifecycle")
        if isinstance(resolved, ProductLifecycle):
            return resolved
        if workflow_snapshot is not None:
            return self.product_lifecycle.build_lifecycle(workflow_snapshot)
        return None

    def _resolve_publishing(
        self,
        publishing_status: PublishingAutomationStatus | Mapping[str, Any] | None,
        *,
        lifecycle: ProductLifecycle | None,
        workflow_snapshot: Any | None,
        publishing_projection: Any | None,
        publishing_job: Any | None,
        publishing_queue_item: Any | None,
        product_business_snapshot: ProductBusinessSnapshot | None,
    ) -> PublishingAutomationStatus | None:
        if isinstance(publishing_status, PublishingAutomationStatus):
            return publishing_status
        resolved = self._read(product_business_snapshot, "publishing_status")
        if isinstance(resolved, PublishingAutomationStatus):
            return resolved
        if any(
            item is not None
            for item in (
                publishing_status,
                lifecycle,
                workflow_snapshot,
                publishing_projection,
                publishing_job,
                publishing_queue_item,
            )
        ):
            return self.publishing_automation.build_status(
                lifecycle=lifecycle,
                workflow_snapshot=workflow_snapshot,
                publishing_projection=publishing_status or publishing_projection,
                publishing_job=publishing_job,
                publishing_queue_item=publishing_queue_item,
            )
        return None

    @staticmethod
    def _business_from_mapping(value: Mapping[str, Any]) -> ProductBusinessSnapshot:
        availability = value.get("availability")
        if not isinstance(availability, ProductBusinessAvailability):
            try:
                availability = ProductBusinessAvailability(str(availability))
            except (TypeError, ValueError):
                availability = ProductBusinessAvailability.UNKNOWN
        return ProductBusinessSnapshot(
            product_id=ProductAvailabilityService._safe_text(
                value.get("product_id") or value.get("id")
            ),
            product_name=ProductAvailabilityService._safe_text(
                value.get("product_name")
            ),
            product_status=ProductAvailabilityService._safe_text(
                value.get("product_status") or value.get("status")
            ),
            lifecycle=value.get("lifecycle"),
            publishing_status=value.get("publishing_status"),
            publishing_readiness=value.get("publishing_readiness") or {},
            availability=availability,
            metadata=value.get("metadata") or {},
        )

    @staticmethod
    def _read(value: Any, key: str) -> Any:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return value.get(key)
        return getattr(value, key, None)

    @staticmethod
    def _enum_value(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value))

    @staticmethod
    def _safe_text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value))

    @staticmethod
    def _text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value)).strip().upper()

    @staticmethod
    def _bool(value: Any) -> bool:
        return bool(value)
