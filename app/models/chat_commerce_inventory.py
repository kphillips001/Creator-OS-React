"""Read models for Chat Commerce Inventory projections."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping


CHAT_COMMERCE_INVENTORY_SCHEMA_VERSION = "phase_3_10_9_chat_commerce_inventory_v1"


@dataclass(frozen=True)
class ChatCommerceInventoryFilter:
    status: str | None = None
    destination: str | None = None
    product_id: str | None = None
    experience_id: str | None = None
    source_workflow: str | None = None
    chat_ready: bool | None = None
    fulfillment_ready: bool | None = None
    waiting_for_media_link: bool | None = None
    awaiting_destination: bool | None = None
    blocked: bool | None = None
    temporarily_unavailable: bool | None = None
    retired: bool | None = None
    recommendation_ready: bool | None = None


@dataclass(frozen=True)
class ChatCommerceInventoryMetrics:
    recommendation_count: int = 0
    offer_count: int = 0
    delivery_count: int = 0
    purchase_count: int = 0
    revenue_cents: int = 0
    conversion_rate: float = 0.0
    last_recommended: str | None = None
    last_offered: str | None = None
    last_delivered: str | None = None
    last_purchased: str | None = None
    performance_trend: str = "Unknown"


@dataclass(frozen=True)
class ChatCommerceInventoryItem:
    asset_id: int
    asset_name: str | None = None
    thumbnail_path: str | None = None
    source_workflow: str | None = None
    commerce_destination: str | None = None
    current_lifecycle: str | None = None
    chat_ready: bool = False
    fulfillment_ready: bool = False
    recommendation_ready: bool = False
    fanvue_upload_status: str | None = None
    fanvue_media_uuid: str | None = None
    media_link_status: str | None = None
    media_link: str | None = None
    product_ids: tuple[str, ...] = ()
    experience_ids: tuple[str, ...] = ()
    availability: str = "Unknown"
    waiting_for_media_link: bool = False
    awaiting_destination: bool = False
    blocked: bool = False
    temporarily_unavailable: bool = False
    retired: bool = False
    block_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metrics: ChatCommerceInventoryMetrics = field(
        default_factory=ChatCommerceInventoryMetrics
    )
    lifecycle_steps: tuple[tuple[str, str], ...] = ()
    quick_actions: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatCommerceInventorySummary:
    total_business_assets: int = 0
    chat_ready: int = 0
    fulfillment_ready: int = 0
    waiting_for_media_link: int = 0
    awaiting_destination: int = 0
    blocked: int = 0
    temporarily_unavailable: int = 0
    retired: int = 0
    recommendation_ready: int = 0
    recommendation_pending: int = 0
    total_revenue_cents: int = 0
    total_purchases: int = 0
    overall_conversion: float = 0.0
    top_performing_asset_ids: tuple[int, ...] = ()
    underperforming_asset_ids: tuple[int, ...] = ()
    disabled_asset_ids: tuple[int, ...] = ()
    retired_asset_ids: tuple[int, ...] = ()
    attention_asset_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ChatCommerceInventoryResult:
    items: tuple[ChatCommerceInventoryItem, ...]
    summary: ChatCommerceInventorySummary
    filters: ChatCommerceInventoryFilter = field(
        default_factory=ChatCommerceInventoryFilter
    )
    generated_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
