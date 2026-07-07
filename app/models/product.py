"""Commerce product domain model.

Phase 1 compatibility: Products still carry fulfillment and media-link fields
that are used as publishing readiness. Future publishing lifecycle cleanup
should move provider-specific delivery state out of the Product core.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from urllib.parse import urlparse
from uuid import UUID


class ProductType(str, Enum):
    SINGLE_IMAGE = "SINGLE_IMAGE"
    SINGLE_VIDEO = "SINGLE_VIDEO"
    PHOTO_SET = "PHOTO_SET"
    VIDEO_SET = "VIDEO_SET"
    SESSION = "SESSION"
    STORY = "STORY"
    BUNDLE = "BUNDLE"
    CUSTOM = "CUSTOM"


class ProductDeliveryType(str, Enum):
    """Commerce-facing delivery intent, separate from Product shape."""

    FREE = "FREE"
    PAID = "PAID"


class ProductStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    ARCHIVED = "ARCHIVED"


class FulfillmentStrategy(str, Enum):
    # Stored legacy values. Keep these stable for database/runtime compatibility.
    FANVUE_PAID_CHAT = "FANVUE_PAID_CHAT"
    FANVUE_PAID_POST = "FANVUE_PAID_POST"
    # Provider-neutral aliases for new Creator OS code paths.
    PROVIDER_PAID_CHAT = "FANVUE_PAID_CHAT"
    PROVIDER_PAID_POST = "FANVUE_PAID_POST"
    MEDIA_LINK_FUTURE = "MEDIA_LINK_FUTURE"
    MANUAL_FUTURE = "MANUAL_FUTURE"


class ProductFulfillmentStatus(str, Enum):
    NOT_READY = "NOT_READY"
    READY = "READY"
    FAILED = "FAILED"


class ProductApprovalStatus(str, Enum):
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"


DEFAULT_FULFILLMENT_STRATEGY_BY_TYPE = {
    ProductType.SINGLE_IMAGE: FulfillmentStrategy.FANVUE_PAID_CHAT,
    ProductType.SINGLE_VIDEO: FulfillmentStrategy.FANVUE_PAID_CHAT,
    ProductType.PHOTO_SET: FulfillmentStrategy.FANVUE_PAID_CHAT,
    ProductType.VIDEO_SET: FulfillmentStrategy.FANVUE_PAID_CHAT,
    ProductType.STORY: FulfillmentStrategy.FANVUE_PAID_POST,
    ProductType.SESSION: FulfillmentStrategy.FANVUE_PAID_CHAT,
    ProductType.BUNDLE: FulfillmentStrategy.MANUAL_FUTURE,
    ProductType.CUSTOM: FulfillmentStrategy.MANUAL_FUTURE,
}


DEFAULT_PRODUCT_DELIVERY_TYPE = ProductDeliveryType.PAID
DELIVERY_TYPE_METADATA_KEY = "delivery_type"
APPROVAL_METADATA_KEY = "approval"


def default_fulfillment_strategy(
    product_type: ProductType,
) -> FulfillmentStrategy:
    return DEFAULT_FULFILLMENT_STRATEGY_BY_TYPE.get(
        product_type,
        FulfillmentStrategy.MANUAL_FUTURE,
    )


def provider_neutral_fulfillment_label(
    strategy: FulfillmentStrategy | str | None,
) -> str:
    if not strategy:
        return "manual"
    normalized = FulfillmentStrategy(strategy)
    if normalized == FulfillmentStrategy.FANVUE_PAID_CHAT:
        return "provider_paid_chat"
    if normalized == FulfillmentStrategy.FANVUE_PAID_POST:
        return "provider_paid_post"
    if normalized == FulfillmentStrategy.MEDIA_LINK_FUTURE:
        return "media_link"
    return "manual"


def default_product_delivery_type() -> ProductDeliveryType:
    return DEFAULT_PRODUCT_DELIVERY_TYPE


def normalize_product_delivery_type(
    delivery_type: ProductDeliveryType | str | None,
) -> ProductDeliveryType:
    if delivery_type is None:
        return default_product_delivery_type()
    if isinstance(delivery_type, ProductDeliveryType):
        return delivery_type
    return ProductDeliveryType(str(delivery_type).strip().upper())


def product_delivery_type_from_metadata(
    metadata: Mapping[str, Any] | None,
) -> ProductDeliveryType:
    metadata = metadata or {}
    return normalize_product_delivery_type(
        metadata.get(DELIVERY_TYPE_METADATA_KEY)
        or metadata.get("product_delivery_type")
    )


def resolve_product_delivery_type(
    delivery_type: ProductDeliveryType | str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ProductDeliveryType:
    """Resolve Product-owned delivery intent without reading Product Type."""

    if delivery_type is not None:
        return normalize_product_delivery_type(delivery_type)
    return product_delivery_type_from_metadata(metadata)


def product_metadata_with_delivery_type(
    metadata: Mapping[str, Any] | None,
    delivery_type: ProductDeliveryType | str | None = None,
) -> dict[str, Any]:
    merged = dict(metadata or {})
    merged[DELIVERY_TYPE_METADATA_KEY] = resolve_product_delivery_type(
        delivery_type,
        merged,
    ).value
    return merged


def normalize_product_approval_status(
    status: ProductApprovalStatus | str | None,
) -> ProductApprovalStatus:
    if status is None:
        return ProductApprovalStatus.NEEDS_REVIEW
    if isinstance(status, ProductApprovalStatus):
        return status
    return ProductApprovalStatus(str(status).strip().upper())


def product_approval_metadata(
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    metadata = metadata or {}
    approval = metadata.get(APPROVAL_METADATA_KEY) or {}
    return dict(approval) if isinstance(approval, Mapping) else {}


def product_approval_status_from_metadata(
    metadata: Mapping[str, Any] | None,
) -> ProductApprovalStatus:
    approval = product_approval_metadata(metadata)
    return normalize_product_approval_status(approval.get("status"))


def product_metadata_with_approval(
    metadata: Mapping[str, Any] | None,
    status: ProductApprovalStatus | str,
    *,
    reviewed_by: str | None = None,
    notes: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    merged = dict(metadata or {})
    timestamp = timestamp or datetime.now(timezone.utc)
    timestamp_value = timestamp.isoformat()
    normalized_status = normalize_product_approval_status(status)
    existing = product_approval_metadata(merged)
    approval = {
        **existing,
        "status": normalized_status.value,
        "last_reviewed_at": timestamp_value,
    }
    if reviewed_by:
        approval["reviewed_by"] = reviewed_by
    if notes is not None:
        approval["review_notes"] = notes
    if normalized_status in {
        ProductApprovalStatus.APPROVED,
        ProductApprovalStatus.READY_TO_PUBLISH,
    }:
        approval["approved_at"] = existing.get("approved_at") or timestamp_value
        if reviewed_by:
            approval["approved_by"] = reviewed_by
    else:
        approval.pop("approved_at", None)
        approval.pop("approved_by", None)
    merged[APPROVAL_METADATA_KEY] = approval
    return product_metadata_with_delivery_type(merged)


def delivery_mode_value_for_delivery_type(
    delivery_type: ProductDeliveryType | str,
) -> str:
    """Return the compatible CMS DeliveryMode value without importing contracts."""

    normalized = ProductDeliveryType(delivery_type)
    if normalized == ProductDeliveryType.FREE:
        return "included"
    return "paid"


def fulfillment_status_for_media_link(
    media_link: str | None,
) -> ProductFulfillmentStatus:
    clean = str(media_link or "").strip()
    if not clean:
        return ProductFulfillmentStatus.NOT_READY
    if urlparse(clean).scheme not in {"http", "https", "local"}:
        return ProductFulfillmentStatus.FAILED
    return ProductFulfillmentStatus.READY


@dataclass(frozen=True)
class Product:
    id: UUID
    creator_profile_id: int | None
    legacy_content_item_id: int | None
    internal_name: str
    display_name: str
    description: str | None
    product_type: ProductType
    status: ProductStatus
    price_cents: int | None
    base_price_cents: int | None
    min_price_cents: int | None
    max_price_cents: int | None
    currency: str
    media_link: str | None
    tags: tuple[str, ...]
    themes: tuple[str, ...]
    metadata: Mapping[str, Any]
    activation_source: str | None
    activation_reason: str | None
    activated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    fulfillment_strategy: FulfillmentStrategy | None = None
    fulfillment_status: ProductFulfillmentStatus | None = None
    delivery_type: ProductDeliveryType | None = None

    def __post_init__(self) -> None:
        if self.fulfillment_strategy is None:
            object.__setattr__(
                self,
                "fulfillment_strategy",
                default_fulfillment_strategy(self.product_type),
            )
        if self.fulfillment_status is None:
            object.__setattr__(
                self,
                "fulfillment_status",
                fulfillment_status_for_media_link(self.media_link),
            )
        delivery_type = resolve_product_delivery_type(
            self.delivery_type,
            self.metadata,
        )
        object.__setattr__(
            self,
            "metadata",
            product_metadata_with_delivery_type(self.metadata, delivery_type),
        )
        object.__setattr__(
            self,
            "delivery_type",
            delivery_type,
        )

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Product":
        product_type = ProductType(row["product_type"])
        strategy = row.get("fulfillment_strategy")
        fulfillment_status = row.get("fulfillment_status")
        metadata = row.get("metadata") or {}
        return cls(
            id=row["id"],
            creator_profile_id=row.get("creator_profile_id"),
            legacy_content_item_id=row.get("legacy_content_item_id"),
            internal_name=row["internal_name"],
            display_name=row["display_name"],
            description=row.get("description"),
            product_type=product_type,
            status=ProductStatus(row["status"]),
            price_cents=row.get("price_cents"),
            base_price_cents=row.get("base_price_cents"),
            min_price_cents=row.get("min_price_cents"),
            max_price_cents=row.get("max_price_cents"),
            currency=row["currency"].strip(),
            media_link=row.get("media_link"),
            tags=tuple(row.get("tags") or ()),
            themes=tuple(row.get("themes") or ()),
            metadata=metadata,
            activation_source=row.get("activation_source"),
            activation_reason=row.get("activation_reason"),
            activated_at=row.get("activated_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            fulfillment_strategy=(
                FulfillmentStrategy(strategy)
                if strategy
                else default_fulfillment_strategy(product_type)
            ),
            fulfillment_status=(
                ProductFulfillmentStatus(fulfillment_status)
                if fulfillment_status
                else fulfillment_status_for_media_link(row.get("media_link"))
            ),
            delivery_type=(
                row.get(DELIVERY_TYPE_METADATA_KEY)
                or product_delivery_type_from_metadata(metadata)
            ),
        )
