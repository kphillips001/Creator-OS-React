"""Customer presentation service.

C.3.4 introduces the service boundary future Customer Workspace pages should
consume. CustomerRepository remains responsible for retrieval; this service
only presents the Customer read model in convenient slices.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.customer import (
    Customer,
    CustomerConversationSummary,
    CustomerOwnershipSummary,
    CustomerProgressionSummary,
    CustomerRecommendationSummary,
    CustomerRelationshipSummary,
)
from app.repositories.customer_repository import CustomerRepository


class CustomerService:
    """Presentation and business summary layer for Customer read models."""

    def __init__(self, customer_repository: CustomerRepository | None = None):
        self.customer_repository = customer_repository or CustomerRepository()

    def get_customer(
        self,
        customer_id: str | int | None = None,
        *,
        provider: str | None = None,
        provider_customer_id: str | int | None = None,
        provider_account_id: str | int | None = None,
    ) -> Customer | None:
        """Retrieve a Customer through CustomerRepository."""

        if provider and provider_customer_id is not None:
            return self.customer_repository.get_by_provider_identity(
                provider=provider,
                provider_customer_id=provider_customer_id,
                provider_account_id=provider_account_id,
            )

        parsed_customer_id = self._parse_customer_id(customer_id)
        if parsed_customer_id is None:
            return None

        account_id, user_id = parsed_customer_id
        return self.customer_repository.get_by_legacy_fanvue_user(
            fanvue_account_id=account_id,
            fanvue_user_id=user_id,
        )

    def get_customer_summary(
        self,
        customer_id: str | int | None = None,
        **lookup: Any,
    ) -> dict[str, Any] | None:
        """Return a compact provider-neutral summary for presentation surfaces."""

        customer = self.get_customer(customer_id, **lookup)
        if customer is None:
            return None

        relationship = customer.relationship
        conversation = customer.conversation
        progression = customer.progression
        ownership = customer.ownership
        recommendation = customer.recommendation

        return {
            "customer_id": customer.customer_id,
            "display_name": customer.display_name,
            "relationship_status": relationship.status.value,
            "is_follower": relationship.is_follower,
            "is_subscriber": relationship.is_subscriber,
            "value_tier": relationship.value_tier,
            "buyer_tier": relationship.buyer_tier,
            "total_spend_cents": relationship.total_spend_cents,
            "purchase_count": max(
                relationship.purchase_count,
                ownership.purchase_count,
            ),
            "thread_count": conversation.thread_count,
            "message_count": conversation.message_count,
            "current_experience_id": progression.current_experience_id,
            "active_session": progression.active_session,
            "owned_product_count": len(ownership.owned_product_ids),
            "owned_experience_count": len(ownership.owned_experience_ids),
            "entitlement_count": ownership.entitlement_count,
            "last_offer_id": recommendation.last_offer_id,
            "offer_count": recommendation.offer_count,
            "provider_count": len(customer.provider_identities),
            "last_active_at": (
                relationship.last_active_at
                or conversation.last_message_at
                or ownership.last_purchase_at
                or recommendation.last_offer_at
            ),
            "updated_at": customer.updated_at,
        }

    def get_customer_relationship(
        self,
        customer_id: str | int | None = None,
        **lookup: Any,
    ) -> CustomerRelationshipSummary | None:
        customer = self.get_customer(customer_id, **lookup)
        return customer.relationship if customer else None

    def get_customer_progression(
        self,
        customer_id: str | int | None = None,
        **lookup: Any,
    ) -> CustomerProgressionSummary | None:
        customer = self.get_customer(customer_id, **lookup)
        return customer.progression if customer else None

    def get_customer_conversation(
        self,
        customer_id: str | int | None = None,
        **lookup: Any,
    ) -> CustomerConversationSummary | None:
        customer = self.get_customer(customer_id, **lookup)
        return customer.conversation if customer else None

    def get_customer_ownership(
        self,
        customer_id: str | int | None = None,
        **lookup: Any,
    ) -> CustomerOwnershipSummary | None:
        customer = self.get_customer(customer_id, **lookup)
        return customer.ownership if customer else None

    def get_customer_recommendations(
        self,
        customer_id: str | int | None = None,
        **lookup: Any,
    ) -> CustomerRecommendationSummary | None:
        customer = self.get_customer(customer_id, **lookup)
        return customer.recommendation if customer else None

    def get_customer_timeline(
        self,
        customer_id: str | int | None = None,
        **lookup: Any,
    ) -> list[dict[str, Any]]:
        """Build a read-only customer timeline from the Customer read model."""

        customer = self.get_customer(customer_id, **lookup)
        if customer is None:
            return []

        events: list[dict[str, Any]] = []
        relationship = customer.relationship
        conversation = customer.conversation
        progression = customer.progression
        ownership = customer.ownership
        recommendation = customer.recommendation

        if conversation.message_count:
            events.append(
                self._timeline_event(
                    event_type="conversation",
                    title="Conversation activity",
                    detail=(
                        f"{conversation.message_count} messages"
                        f" across {conversation.thread_count} thread(s)"
                    ),
                    timestamp=conversation.last_message_at,
                    source="conversation_summary",
                )
            )

        if recommendation.last_offer_id or recommendation.offer_count:
            events.append(
                self._timeline_event(
                    event_type="recommendation",
                    title="Product recommendation activity",
                    detail=(
                        recommendation.last_offer_id
                        or f"{recommendation.offer_count} offer(s) shown"
                    ),
                    timestamp=recommendation.last_offer_at,
                    source="recommendation_summary",
                )
            )

        for product_id in ownership.owned_product_ids:
            events.append(
                self._timeline_event(
                    event_type="product_purchased",
                    title="Product owned",
                    detail=str(product_id),
                    timestamp=ownership.last_purchase_at,
                    source="ownership_summary",
                )
            )

        if ownership.purchase_count and not ownership.owned_product_ids:
            events.append(
                self._timeline_event(
                    event_type="product_purchased",
                    title="Purchase activity",
                    detail=f"{ownership.purchase_count} purchase(s)",
                    timestamp=ownership.last_purchase_at,
                    source="ownership_summary",
                )
            )

        if progression.current_experience_id or progression.active_session:
            events.append(
                self._timeline_event(
                    event_type="experience_progression",
                    title="Experience progression",
                    detail=(
                        progression.current_experience_id
                        or f"Active session step {progression.session_step}"
                    ),
                    timestamp=None,
                    source="progression_summary",
                )
            )

        if relationship.status.value != "unknown":
            events.append(
                self._timeline_event(
                    event_type="customer_memory",
                    title="Relationship milestone",
                    detail=relationship.status.value,
                    timestamp=relationship.last_active_at,
                    source="relationship_summary",
                )
            )

        if customer.updated_at:
            events.append(
                self._timeline_event(
                    event_type="system",
                    title="Customer read model updated",
                    detail="Customer summary data refreshed.",
                    timestamp=customer.updated_at,
                    source="customer_model",
                )
            )

        if customer.created_at:
            events.append(
                self._timeline_event(
                    event_type="system",
                    title="Customer first seen",
                    detail="Customer identity appeared in Creator OS.",
                    timestamp=customer.created_at,
                    source="customer_model",
                )
            )

        events.extend(
            [
                self._future_timeline_event(
                    "media_link",
                    "Media Link activity",
                    "Media Link creation/use is not yet exposed through CustomerService.",
                ),
                self._future_timeline_event(
                    "products_offered",
                    "Products offered",
                    "Detailed offer history is not yet exposed through CustomerService.",
                ),
            ]
        )

        return sorted(events, key=self._timeline_sort_key, reverse=True)

    def get_customer_decision_inspector(
        self,
        customer_id: str | int | None = None,
        **lookup: Any,
    ) -> dict[str, Any] | None:
        """Expose DecisionEngine-facing customer business context."""

        customer = self.get_customer(customer_id, **lookup)
        if customer is None:
            return None

        conversation = customer.conversation
        progression = customer.progression
        ownership = customer.ownership
        recommendation = customer.recommendation
        relationship = customer.relationship

        return {
            "customer_id": customer.customer_id,
            "current_recommendation": {
                "last_offer_id": recommendation.last_offer_id,
                "last_offer_kind": recommendation.last_offer_kind,
                "last_offer_at": recommendation.last_offer_at,
                "recent_product_ids": recommendation.recent_product_ids,
            },
            "recent_recommendations": {
                "offer_count": recommendation.offer_count,
                "accepted_offer_count": recommendation.accepted_offer_count,
                "rejected_offer_count": recommendation.rejected_offer_count,
                "seen_offer_ids": recommendation.seen_offer_ids,
                "preferred_tags": recommendation.preferred_tags,
                "preferred_themes": recommendation.preferred_themes,
            },
            "offer_candidates": self._future_inspector_section(
                "Offer candidates are not yet exposed through CustomerService."
            ),
            "delivery_permissions": self._future_inspector_section(
                "Delivery permission summaries are not yet exposed through CustomerService."
            ),
            "customer_progression": {
                "current_experience_id": progression.current_experience_id,
                "current_position": progression.current_position,
                "active_session": progression.active_session,
                "session_step": progression.session_step,
                "seen_content_tags": progression.seen_content_tags,
                "completed_experience_ids": progression.completed_experience_ids,
            },
            "conversation_summary": {
                "thread_count": conversation.thread_count,
                "message_count": conversation.message_count,
                "inbound_message_count": conversation.inbound_message_count,
                "outbound_message_count": conversation.outbound_message_count,
                "current_mode": conversation.current_mode,
                "last_message_at": conversation.last_message_at,
            },
            "memory_summary": {
                "relationship_status": relationship.status.value,
                "value_tier": relationship.value_tier,
                "buyer_tier": relationship.buyer_tier,
                "total_spend_cents": relationship.total_spend_cents,
                "purchase_count": max(
                    relationship.purchase_count,
                    ownership.purchase_count,
                ),
                "owned_product_count": len(ownership.owned_product_ids),
                "entitlement_count": ownership.entitlement_count,
            },
            "last_decision_activity": (
                recommendation.last_offer_at
                or conversation.last_message_at
                or customer.updated_at
            ),
        }

    def get_customer_commerce_summary(
        self,
        customer_id: str | int | None = None,
        **lookup: Any,
    ) -> dict[str, Any] | None:
        """Expose read-only customer commerce relationship data."""

        customer = self.get_customer(customer_id, **lookup)
        if customer is None:
            return None

        relationship = customer.relationship
        ownership = customer.ownership
        recommendation = customer.recommendation
        telegram_conversation_state = self._telegram_conversation_state(customer)
        delivery_decision = self._delivery_decision_summary(customer)
        commerce_memory = self._commerce_memory_summary(customer)

        return {
            "customer_id": customer.customer_id,
            "products_owned": ownership.owned_product_ids,
            "products_purchased": ownership.owned_product_ids,
            "products_offered": self._future_commerce_section(
                "Detailed product offer history is not yet exposed through CustomerService."
            ),
            "entitlements": {
                "count": ownership.entitlement_count,
                "owned_product_count": len(ownership.owned_product_ids),
                "owned_experience_count": len(ownership.owned_experience_ids),
            },
            "purchased_experiences": ownership.owned_experience_ids,
            "offer_acceptance": {
                "accepted_offer_count": recommendation.accepted_offer_count,
                "offer_count": recommendation.offer_count,
            },
            "offer_rejection": {
                "rejected_offer_count": recommendation.rejected_offer_count,
                "offer_count": recommendation.offer_count,
            },
            "media_links": self._future_commerce_section(
                "Media Link history is not yet exposed through CustomerService."
            ),
            "telegram_conversation_state": telegram_conversation_state,
            "delivery_decision": delivery_decision,
            "commerce_memory": commerce_memory,
            "purchase_summary": {
                "purchase_count": max(
                    relationship.purchase_count,
                    ownership.purchase_count,
                ),
                "last_purchase_at": ownership.last_purchase_at,
                "total_spend_cents": relationship.total_spend_cents,
            },
            "customer_value": {
                "relationship_status": relationship.status.value,
                "value_tier": relationship.value_tier,
                "buyer_tier": relationship.buyer_tier,
                "is_subscriber": relationship.is_subscriber,
                "is_follower": relationship.is_follower,
            },
        }

    @staticmethod
    def _commerce_memory_summary(customer: Customer) -> dict[str, Any]:
        """Expose read-only Commerce Memory visibility from customer history."""

        progression = customer.progression
        conversation = customer.conversation
        relationship = customer.relationship
        ownership = customer.ownership
        recommendation = customer.recommendation

        purchased_products = ownership.owned_product_ids
        journey = "customer" if purchased_products else "discovery"
        if recommendation.offer_count and not purchased_products:
            journey = "offer_consideration"
        elif progression.current_experience_id and not purchased_products:
            journey = "experience_nurture"

        recommended_action = "continue_free_delivery"
        if relationship.purchase_count or ownership.purchase_count:
            recommended_action = "escalate_commerce_offer"
        elif recommendation.offer_count:
            recommended_action = "delay_offer"
        elif progression.current_experience_id:
            recommended_action = "continue_experience"

        return {
            "purchased_products": purchased_products,
            "free_assets_delivered": (),
            "paid_media_links_delivered": (),
            "current_commerce_journey": journey,
            "customer_spending_summary": {
                "purchase_count": max(
                    relationship.purchase_count,
                    ownership.purchase_count,
                ),
                "total_spend_cents": relationship.total_spend_cents,
                "last_purchase_at": ownership.last_purchase_at,
            },
            "customer_engagement_summary": {
                "message_count": conversation.message_count,
                "offer_count": recommendation.offer_count,
                "relationship_status": relationship.status.value,
                "buyer_tier": relationship.buyer_tier,
            },
            "recommended_next_commerce_action": recommended_action,
            "source": "customer_service_read_model",
        }

    @staticmethod
    def _delivery_decision_summary(customer: Customer) -> dict[str, Any]:
        """Expose read-only Delivery Decision visibility from Customer data."""

        progression = customer.progression
        recommendation = customer.recommendation
        ownership = customer.ownership
        current_product = (
            recommendation.recent_product_ids[0]
            if recommendation.recent_product_ids
            else None
        )
        delivery_type = None
        free_vs_paid = "unknown"
        if current_product and current_product in ownership.owned_product_ids:
            delivery_type = "FREE"
            free_vs_paid = "FREE"
        elif recommendation.last_offer_id:
            delivery_type = "PAID"
            free_vs_paid = "PAID"

        return {
            "current_delivery_decision": (
                "offer_active"
                if recommendation.last_offer_id
                else "continue_experience"
            ),
            "delivery_type": delivery_type,
            "recommended_product": current_product,
            "delivery_permission": {
                "allowed": current_product in ownership.owned_product_ids
                if current_product
                else None,
                "source": "customer_service_read_model",
            },
            "free_vs_paid": free_vs_paid,
            "delivery_reason": (
                "Last offer is active."
                if recommendation.last_offer_id
                else "No active delivery decision."
            ),
            "last_delivery": {
                "delivery_method": (
                    "paid_media_link"
                    if free_vs_paid == "PAID"
                    else ("free_asset" if free_vs_paid == "FREE" else None)
                ),
                "last_free_asset": (
                    current_product if free_vs_paid == "FREE" else None
                ),
                "last_paid_media_link": None,
                "blocking_reason": None,
            },
            "next_suggested_action": (
                "deliver_free_asset"
                if free_vs_paid == "FREE"
                else (
                    "deliver_paid_media_link"
                    if free_vs_paid == "PAID"
                    else (
                        "continue_experience"
                        if progression.current_experience_id
                        else "skip_delivery"
                    )
                )
            ),
            "source": "customer_service_read_model",
        }

    def get_customer_experience_progression_summary(
        self,
        customer_id: str | int | None = None,
        **lookup: Any,
    ) -> dict[str, Any] | None:
        """Expose read-only Experience progression for Customer Workspace."""

        customer = self.get_customer(customer_id, **lookup)
        if customer is None:
            return None

        progression = customer.progression
        recommendation = customer.recommendation
        progress_percentage = self._experience_progress_percentage(progression)
        state = self._experience_progression_state(
            current_experience_id=progression.current_experience_id,
            active_session=progression.active_session,
            progress_percentage=progress_percentage,
        )

        return {
            "current_experience": progression.current_experience_id,
            "current_experience_state": state,
            "current_story_position": progression.current_position,
            "current_asset_position": (
                str(progression.session_step)
                if progression.session_step
                else None
            ),
            "current_product": (
                recommendation.recent_product_ids[0]
                if recommendation.recent_product_ids
                else None
            ),
            "progress_percentage": progress_percentage,
            "last_progression_event": {
                "source": "customer_progression_summary",
                "experience_id": progression.current_experience_id,
                "session_step": progression.session_step,
            },
            "next_recommended_experience_action": (
                self._next_experience_progression_action(
                    state,
                    progression.current_experience_id,
                )
            ),
            "source": "customer_service_read_model",
        }

    @staticmethod
    def _telegram_conversation_state(customer: Customer) -> dict[str, Any]:
        """Expose read-only Telegram Commerce state from existing customer data."""

        progression = customer.progression
        conversation = customer.conversation
        recommendation = customer.recommendation
        ownership = customer.ownership

        current_product_id = (
            recommendation.recent_product_ids[0]
            if recommendation.recent_product_ids
            else None
        )
        commerce_progress = "customer" if ownership.purchase_count else "prospect"
        if recommendation.last_offer_id:
            commerce_progress = "offer_active"

        return {
            "available": True,
            "source": "customer_service_read_model",
            "current_experience": progression.current_experience_id,
            "current_product": current_product_id,
            "current_offer": recommendation.last_offer_id,
            "current_offer_kind": recommendation.last_offer_kind,
            "delivery_type": None,
            "conversation_status": conversation.current_mode,
            "commerce_progress": commerce_progress,
            "last_delivery": {
                "available": False,
                "future_ready": True,
                "message": "Last delivery state is owned by Telegram Commerce orchestration.",
            },
            "next_recommended_action": (
                "continue_experience"
                if progression.current_experience_id
                else "evaluate_customer_message"
            ),
        }

    @staticmethod
    def _experience_progress_percentage(progression) -> int:
        if progression.current_experience_id in progression.completed_experience_ids:
            return 100
        if progression.session_step:
            return max(0, min(95, int(progression.session_step) * 20))
        if progression.active_session:
            return 10
        return 0

    @staticmethod
    def _experience_progression_state(
        *,
        current_experience_id: str | None,
        active_session: bool,
        progress_percentage: int,
    ) -> str:
        if progress_percentage >= 100:
            return "complete"
        if current_experience_id and active_session:
            return "active"
        if current_experience_id:
            return "paused"
        return "not_started"

    @staticmethod
    def _next_experience_progression_action(
        state: str,
        current_experience_id: str | None,
    ) -> str:
        if state == "complete":
            return "switch_experience"
        if state == "paused":
            return "resume_experience"
        if current_experience_id:
            return "continue_experience"
        return "select_experience"

    @staticmethod
    def _future_inspector_section(message: str) -> dict[str, Any]:
        return {
            "available": False,
            "future_ready": True,
            "message": message,
        }

    @staticmethod
    def _future_commerce_section(message: str) -> dict[str, Any]:
        return {
            "available": False,
            "future_ready": True,
            "message": message,
        }

    @staticmethod
    def _timeline_event(
        *,
        event_type: str,
        title: str,
        detail: str,
        timestamp: Any,
        source: str,
        future_ready: bool = False,
    ) -> dict[str, Any]:
        return {
            "type": event_type,
            "title": title,
            "detail": detail,
            "timestamp": timestamp,
            "source": source,
            "future_ready": future_ready,
        }

    @classmethod
    def _future_timeline_event(
        cls,
        event_type: str,
        title: str,
        detail: str,
    ) -> dict[str, Any]:
        return cls._timeline_event(
            event_type=event_type,
            title=title,
            detail=detail,
            timestamp=None,
            source="future_customer_workspace",
            future_ready=True,
        )

    @staticmethod
    def _timeline_sort_key(event: dict[str, Any]) -> tuple[int, str]:
        timestamp = event.get("timestamp")
        if timestamp is None:
            return (0, "")
        if isinstance(timestamp, datetime):
            return (1, timestamp.isoformat())
        return (1, str(timestamp))

    @staticmethod
    def _parse_customer_id(customer_id: str | int | None) -> tuple[int, int] | None:
        if customer_id is None:
            return None

        text = str(customer_id).strip()
        if not text or ":" not in text:
            return None

        account_id, user_id = text.split(":", 1)
        try:
            return int(account_id), int(user_id)
        except (TypeError, ValueError):
            return None
