"""Provider-neutral Telegram Commerce orchestration models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.runtime_decision import DecisionEngineResult


@dataclass(frozen=True)
class TelegramDeliveryDecision:
    """Normalized delivery decision produced during Telegram commerce."""

    offer_authorized: bool
    blocked: bool
    current_product_id: str | None = None
    delivery_type: str | None = None
    delivery_permission: dict[str, Any] = field(default_factory=dict)
    delivery_method: str | None = None
    free_asset_id: str | None = None
    paid_media_link: str | None = None
    delivery_mode: str | None = None
    requires_payment: bool | None = None
    offer_link: str | None = None
    reason: str | None = None
    commerce_recommendation: dict[str, Any] = field(default_factory=dict)
    next_suggested_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "offer_authorized": self.offer_authorized,
            "blocked": self.blocked,
            "current_product_id": self.current_product_id,
            "delivery_type": self.delivery_type,
            "delivery_permission": dict(self.delivery_permission),
            "delivery_method": self.delivery_method,
            "free_asset_id": self.free_asset_id,
            "paid_media_link": self.paid_media_link,
            "delivery_mode": self.delivery_mode,
            "requires_payment": self.requires_payment,
            "offer_link": self.offer_link,
            "reason": self.reason,
            "commerce_recommendation": dict(self.commerce_recommendation),
            "next_suggested_action": self.next_suggested_action,
        }


@dataclass(frozen=True)
class TelegramCustomerProgress:
    """Provider-neutral snapshot of customer commerce progression."""

    customer_id: str
    current_experience_id: str | None = None
    current_product_id: str | None = None
    current_asset_id: str | None = None
    conversation_state: str | None = None
    commerce_state: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TelegramConversationState:
    """Provider-neutral orchestration state for one Telegram commerce turn."""

    current_experience_id: str | None = None
    current_product_id: str | None = None
    current_asset_id: str | None = None
    current_delivery_type: str | None = None
    conversation_mode: str | None = None
    current_offer_id: str | None = None
    current_offer_kind: str | None = None
    commerce_state: str | None = None
    customer_progress: TelegramCustomerProgress | None = None
    last_delivery: dict[str, Any] = field(default_factory=dict)
    next_recommended_action: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TelegramExperienceProgression:
    """Provider-neutral Experience progression orchestration state."""

    current_experience_id: str | None = None
    experience_state: str | None = None
    current_story_position: str | None = None
    current_asset_position: str | None = None
    current_product_id: str | None = None
    progress_percentage: int = 0
    last_progression_event: dict[str, Any] = field(default_factory=dict)
    next_recommended_experience_action: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TelegramDeliveryPayload:
    """Provider-neutral payload for Telegram runtime delivery."""

    delivery_type: str | None = None
    message_text: str = ""
    asset_path: str | None = None
    media_link: str | None = None
    product_reference: str | None = None
    experience_reference: str | None = None
    delivery_reason: str | None = None
    blocking_reason: str | None = None
    next_suggested_action: str | None = None
    delivery_method: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "delivery_type": self.delivery_type,
            "message_text": self.message_text,
            "asset_path": self.asset_path,
            "media_link": self.media_link,
            "product_reference": self.product_reference,
            "experience_reference": self.experience_reference,
            "delivery_reason": self.delivery_reason,
            "blocking_reason": self.blocking_reason,
            "next_suggested_action": self.next_suggested_action,
            "delivery_method": self.delivery_method,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TelegramCommerceMemory:
    """Provider-neutral Commerce Memory reconstructed for one turn."""

    purchased_products: tuple[str, ...] = ()
    current_experience_id: str | None = None
    previous_experiences: tuple[str, ...] = ()
    current_commerce_journey: str | None = None
    free_assets_delivered: tuple[str, ...] = ()
    paid_media_links_delivered: tuple[str, ...] = ()
    previous_offers: tuple[str, ...] = ()
    previous_purchases: tuple[str, ...] = ()
    last_purchase: dict[str, Any] = field(default_factory=dict)
    last_delivery: dict[str, Any] = field(default_factory=dict)
    customer_spending_summary: dict[str, Any] = field(default_factory=dict)
    customer_engagement_summary: dict[str, Any] = field(default_factory=dict)
    recommended_commerce_action: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "type": "telegram_commerce_memory",
            "purchased_products": self.purchased_products,
            "current_experience_id": self.current_experience_id,
            "previous_experiences": self.previous_experiences,
            "current_commerce_journey": self.current_commerce_journey,
            "free_assets_delivered": self.free_assets_delivered,
            "paid_media_links_delivered": self.paid_media_links_delivered,
            "previous_offers": self.previous_offers,
            "previous_purchases": self.previous_purchases,
            "last_purchase": dict(self.last_purchase),
            "last_delivery": dict(self.last_delivery),
            "customer_spending_summary": dict(self.customer_spending_summary),
            "customer_engagement_summary": dict(self.customer_engagement_summary),
            "recommended_commerce_action": self.recommended_commerce_action,
        }


@dataclass(frozen=True)
class TelegramCommerceState:
    """Current orchestration state for a Telegram customer interaction."""

    current_experience_id: str | None = None
    current_product_id: str | None = None
    current_asset_id: str | None = None
    conversation_state: str | None = None
    delivery_decision: TelegramDeliveryDecision | None = None
    customer_progress: TelegramCustomerProgress | None = None
    telegram_conversation_state: TelegramConversationState | None = None
    experience_progression: TelegramExperienceProgression | None = None
    commerce_memory: TelegramCommerceMemory | None = None


@dataclass(frozen=True)
class TelegramCommerceResult:
    """Result returned by the Telegram Commerce orchestration boundary."""

    correlation_id: str | None
    engine_user_id: str
    response_text: str
    decision_engine_result: DecisionEngineResult | None
    delivery_decision: TelegramDeliveryDecision
    customer_progress: TelegramCustomerProgress
    state: TelegramCommerceState
    conversation_state: TelegramConversationState
    experience_progression: TelegramExperienceProgression
    commerce_memory: TelegramCommerceMemory
    delivery_payload: TelegramDeliveryPayload
    previous_commerce_memory: TelegramCommerceMemory | None = None
    previous_conversation_state: TelegramConversationState | None = None
    previous_experience_progression: TelegramExperienceProgression | None = None
    commerce_execution_result: Any | None = None
    blocked: bool = False
    error_code: str | None = None
    diagnostic_metadata: dict[str, Any] = field(default_factory=dict)
