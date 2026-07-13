"""Telegram Commerce orchestration boundary.

TelegramCommerceService coordinates Telegram commerce workflows between the
runtime-facing ConversationGateway and existing Creator OS domain services. It
does not own Telegram transport, DecisionEngine intelligence, Product state,
Publishing state, or customer persistence.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

from app.models.commerce_execution import CommerceExecutionRequest
from app.models.customer_intelligence import CustomerIntelligenceSnapshot
from app.models.runtime_decision import DecisionEngineResult, RuntimeDecision
from app.models.telegram_commerce import (
    TelegramCommerceResult,
    TelegramCommerceState,
    TelegramConversationState,
    TelegramCommerceMemory,
    TelegramCustomerProgress,
    TelegramDeliveryDecision,
    TelegramDeliveryPayload,
    TelegramExperienceProgression,
)
from app.services.customer_intelligence_service import CustomerIntelligenceService

if TYPE_CHECKING:
    from app.services.cms_contract_service import CMSContractService
    from app.services.customer_service import CustomerService
    from app.services.experience_service import ExperienceService
    from app.services.product_recommendation_service import (
        ProductRecommendationService,
    )
    from app.services.publishing_service import PublishingService
    from app.services.commerce_execution_service import CommerceExecutionService
    from app.services.telegram_delivery_executor import (
        TelegramDeliveryExecutor,
    )


class DecisionEngineCompatible(Protocol):
    """DecisionEngine behavior consumed by Telegram Commerce."""

    def process_message(
        self,
        user_id: str,
        message: str,
        chat_history: list[Any] | None = None,
    ) -> DecisionEngineResult | dict[str, Any] | None:
        ...


class TelegramCommerceService:
    """Coordinate Telegram commerce without replacing existing services."""

    def __init__(
        self,
        *,
        decision_engine: DecisionEngineCompatible,
        experience_service: ExperienceService | None = None,
        product_recommendation_service: ProductRecommendationService | None = None,
        cms_contract_service: CMSContractService | None = None,
        publishing_service: PublishingService | None = None,
        customer_service: CustomerService | None = None,
        memory_service: Any | None = None,
        asset_service: Any | None = None,
        content_delivery_guard_service: Any | None = None,
        delivery_executor: TelegramDeliveryExecutor | None = None,
        commerce_execution_service: CommerceExecutionService | None = None,
        customer_intelligence_service: CustomerIntelligenceService | None = None,
    ) -> None:
        if decision_engine is None:
            raise ValueError("decision_engine is required")

        self.decision_engine = decision_engine
        self.experience_service = experience_service or self._default_experience_service()
        self.product_recommendation_service = (
            product_recommendation_service
            or self._default_product_recommendation_service()
        )
        self.publishing_service = (
            publishing_service or self._default_publishing_service()
        )
        self.cms_contract_service = (
            cms_contract_service
            or self._default_cms_contract_service(
                experience_service=self.experience_service,
                publishing_service=self.publishing_service,
                recommendation_service=self.product_recommendation_service,
            )
        )
        self.customer_service = customer_service or self._default_customer_service()
        self.memory_service = memory_service
        self.asset_service = asset_service
        self.content_delivery_guard_service = content_delivery_guard_service
        self.delivery_executor = (
            delivery_executor or self._default_delivery_executor()
        )
        self.commerce_execution_service = (
            commerce_execution_service or self._default_commerce_execution_service()
        )
        self.customer_intelligence_service = (
            customer_intelligence_service
            or self._default_customer_intelligence_service()
        )

    def process_message(
        self,
        user_id: str,
        message: str,
        chat_history: list[Any] | None = None,
    ) -> dict[str, Any] | None:
        """Compatibility adapter for ConversationGateway."""

        result = self.execute(
            engine_user_id=user_id,
            message_text=message,
            chat_history=chat_history,
        )
        if result.decision_engine_result is None:
            return None
        gateway_result = result.decision_engine_result.to_dict()
        gateway_result["telegram_delivery_payload"] = (
            result.delivery_payload.to_dict()
        )
        return gateway_result

    def execute(
        self,
        *,
        engine_user_id: str,
        message_text: str,
        chat_history: list[Any] | None = None,
        correlation_id: str | None = None,
    ) -> TelegramCommerceResult:
        """Run one Telegram commerce turn through the existing intelligence."""

        previous_conversation_state = self.load_conversation_state(
            engine_user_id
        )
        previous_experience_progression = self.load_experience_progression(
            engine_user_id,
            conversation_state=previous_conversation_state,
        )
        previous_commerce_memory = self.load_commerce_memory(
            engine_user_id,
            conversation_state=previous_conversation_state,
            experience_progression=previous_experience_progression,
        )
        customer_intelligence_snapshot = self._customer_intelligence_snapshot(
            engine_user_id,
            commerce_memory=previous_commerce_memory,
            conversation_state=previous_conversation_state,
            experience_progression=previous_experience_progression,
        )
        decision_customer_context = (
            self.customer_intelligence_service.build_decision_customer_context(
                customer_intelligence_snapshot
            )
        )
        raw_engine_result = self.decision_engine.process_message(
            engine_user_id,
            message_text,
            chat_history=self._chat_history_with_customer_context(
                chat_history,
                decision_customer_context,
                previous_commerce_memory,
            ),
        )
        engine_result = DecisionEngineResult.from_value(raw_engine_result)

        delivery_decision = self.build_delivery_decision(engine_result)
        prepared_delivery = self._chat_delivery_context(engine_result)
        customer_progress = self.build_customer_progress(
            engine_user_id=engine_user_id,
            engine_result=engine_result,
            delivery_decision=delivery_decision,
        )
        conversation_state = self.update_conversation_state(
            previous_state=previous_conversation_state,
            engine_result=engine_result,
            delivery_decision=delivery_decision,
            customer_progress=customer_progress,
        )
        experience_progression = self.update_experience_progression(
            previous_progression=previous_experience_progression,
            engine_result=engine_result,
            conversation_state=conversation_state,
        )
        delivery_payload = self.build_telegram_delivery_payload(
            engine_result=engine_result,
            delivery_decision=delivery_decision,
            conversation_state=conversation_state,
            experience_progression=experience_progression,
        )
        commerce_execution_result = self.commerce_execution_service.execute(
            CommerceExecutionRequest(
                execution_decision=delivery_decision.to_dict(),
                execution_payload=delivery_payload,
                provider="telegram",
                delivery_type=delivery_decision.delivery_type,
                product_reference=delivery_decision.current_product_id,
                publishing_outputs={
                    "media_link": delivery_decision.paid_media_link,
                    "source": "PublishingService",
                }
                if delivery_decision.paid_media_link
                else {},
                runtime_context={
                    "correlation_id": correlation_id,
                    "engine_user_id": engine_user_id,
                    "delivery_id": prepared_delivery.get("delivery_id"),
                    "recommendation_id": prepared_delivery.get("recommendation_id"),
                    "asset_id": prepared_delivery.get("asset_id"),
                },
                metadata={
                    "chat_commerce_delivery": prepared_delivery,
                    "customer_intelligence": (
                        self.customer_intelligence_service
                        .build_execution_customer_context(
                            customer_intelligence_snapshot
                        )
                    ),
                    "customer_intelligence_boundary": type(
                        self.customer_intelligence_service
                    ).__name__,
                    "customer_knowledge_owner": "CustomerIntelligenceService",
                },
            ),
            runtime_executor=self.delivery_executor,
        )
        delivery_execution_result = commerce_execution_result.execution_result
        self._record_chat_delivery_execution(
            engine_result=engine_result,
            execution_result=delivery_execution_result,
        )
        commerce_memory = self.update_commerce_memory(
            previous_memory=previous_commerce_memory,
            delivery_decision=delivery_decision,
            delivery_payload=delivery_payload,
            conversation_state=conversation_state,
            experience_progression=experience_progression,
        )
        state = TelegramCommerceState(
            current_experience_id=customer_progress.current_experience_id,
            current_product_id=customer_progress.current_product_id,
            current_asset_id=customer_progress.current_asset_id,
            conversation_state=customer_progress.conversation_state,
            delivery_decision=delivery_decision,
            customer_progress=customer_progress,
            telegram_conversation_state=conversation_state,
            experience_progression=experience_progression,
            commerce_memory=commerce_memory,
        )

        response_text = self._runtime_response_text(engine_result)

        return TelegramCommerceResult(
            correlation_id=correlation_id,
            engine_user_id=engine_user_id,
            response_text=response_text,
            decision_engine_result=(
                engine_result if isinstance(engine_result, DecisionEngineResult) else None
            ),
            delivery_decision=delivery_decision,
            customer_progress=customer_progress,
            state=state,
            conversation_state=conversation_state,
            experience_progression=experience_progression,
            commerce_memory=commerce_memory,
            delivery_payload=delivery_payload,
            previous_commerce_memory=previous_commerce_memory,
            previous_conversation_state=previous_conversation_state,
            previous_experience_progression=previous_experience_progression,
            commerce_execution_result=commerce_execution_result,
            blocked=delivery_decision.blocked,
            error_code=self._safe_error_code(engine_result),
            diagnostic_metadata=self._diagnostics(
                delivery_decision,
                conversation_state=conversation_state,
                experience_progression=experience_progression,
                commerce_memory=commerce_memory,
                delivery_payload=delivery_payload,
                delivery_execution_result=delivery_execution_result,
                commerce_execution_result=commerce_execution_result,
                customer_intelligence_snapshot=customer_intelligence_snapshot,
            ),
        )

    def load_conversation_state(
        self,
        engine_user_id: str,
    ) -> TelegramConversationState:
        """Rebuild pre-decision conversation state from existing services."""

        customer_summary = self._customer_summary(engine_user_id)
        memory = self._memory_snapshot(engine_user_id)

        current_experience_id = self._first_value(
            customer_summary,
            memory,
            "current_experience_id",
        )
        current_product_id = self._first_value(
            customer_summary,
            memory,
            "current_product_id",
            "last_product_id",
        )
        current_asset_id = self._first_value(
            customer_summary,
            memory,
            "current_asset_id",
            "last_asset_id",
            "last_content_item_id",
        )
        current_delivery_type = self._first_value(
            customer_summary,
            memory,
            "current_delivery_type",
            "delivery_type",
        )
        conversation_mode = self._first_value(
            customer_summary,
            memory,
            "current_mode",
            "conversation_mode",
            "mode",
        )
        current_offer_id = self._first_value(
            customer_summary,
            memory,
            "last_offer_id",
            "current_offer_id",
        )
        current_offer_kind = self._first_value(
            customer_summary,
            memory,
            "last_offer_kind",
            "current_offer_kind",
        )

        progress = TelegramCustomerProgress(
            customer_id=engine_user_id,
            current_experience_id=self._safe_text(current_experience_id),
            current_product_id=self._safe_text(current_product_id),
            current_asset_id=self._safe_text(current_asset_id),
            conversation_state=self._safe_text(conversation_mode),
            commerce_state=self._safe_text(
                self._first_value(customer_summary, memory, "commerce_state")
            ),
            metadata={
                "source": "existing_customer_memory",
                "customer_summary_found": customer_summary is not None,
                "memory_found": memory is not None,
            },
        )

        return TelegramConversationState(
            current_experience_id=progress.current_experience_id,
            current_product_id=progress.current_product_id,
            current_asset_id=progress.current_asset_id,
            current_delivery_type=self._safe_text(current_delivery_type),
            conversation_mode=progress.conversation_state,
            current_offer_id=self._safe_text(current_offer_id),
            current_offer_kind=self._safe_text(current_offer_kind),
            commerce_state=progress.commerce_state,
            customer_progress=progress,
            last_delivery=self._last_delivery_from(memory),
            next_recommended_action=self._next_action_for_loaded_state(progress),
            metadata={
                "source": "telegram_commerce_service",
                "persistence_owner": "MemoryService",
                "customer_owner": "CustomerService",
            },
        )

    def load_experience_progression(
        self,
        engine_user_id: str,
        *,
        conversation_state: TelegramConversationState | None = None,
    ) -> TelegramExperienceProgression:
        """Rebuild Experience progression from existing memory/customer data."""

        customer_summary = self._customer_summary(engine_user_id)
        memory = self._memory_snapshot(engine_user_id)
        current_experience_id = self._first_value(
            customer_summary,
            memory,
            "current_experience_id",
        )
        story_position = self._first_value(
            customer_summary,
            memory,
            "current_position",
            "current_story_position",
            "story_position",
        )
        asset_position = self._first_value(
            customer_summary,
            memory,
            "current_asset_position",
            "asset_position",
            "session_step",
        )
        current_product_id = self._first_value(
            customer_summary,
            memory,
            "current_product_id",
            "last_product_id",
        )
        active_session = self._first_value(
            customer_summary,
            memory,
            "active_session",
        )
        session_step = self._first_value(
            customer_summary,
            memory,
            "session_step",
            "buyer_session_step",
        )
        progress_percentage = self._progress_percentage(
            self._first_value(
                customer_summary,
                memory,
                "progress_percentage",
                "experience_progress_percentage",
            ),
            session_step=session_step,
            active_session=active_session,
        )
        experience_state = self._loaded_experience_state(
            current_experience_id=current_experience_id,
            active_session=active_session,
            progress_percentage=progress_percentage,
        )

        return TelegramExperienceProgression(
            current_experience_id=self._safe_text(current_experience_id),
            experience_state=experience_state,
            current_story_position=self._safe_text(story_position),
            current_asset_position=self._safe_text(asset_position),
            current_product_id=(
                self._safe_text(current_product_id)
                or (
                    conversation_state.current_product_id
                    if conversation_state is not None
                    else None
                )
            ),
            progress_percentage=progress_percentage,
            last_progression_event=self._last_progression_event_from(memory),
            next_recommended_experience_action=(
                self._next_experience_action_for_loaded_state(
                    current_experience_id=current_experience_id,
                    experience_state=experience_state,
                )
            ),
            metadata={
                "source": "telegram_commerce_service",
                "experience_owner": "ExperienceService",
                "decision_owner": "DecisionEngine",
                "workflow_owner": "TelegramCommerceService",
            },
        )

    def load_commerce_memory(
        self,
        engine_user_id: str,
        *,
        conversation_state: TelegramConversationState,
        experience_progression: TelegramExperienceProgression,
    ) -> TelegramCommerceMemory:
        """Reconstruct Commerce Memory from existing customer and memory data."""

        customer_summary = self._customer_summary(engine_user_id)
        commerce_summary = self._customer_commerce_summary(engine_user_id)
        memory = self._memory_snapshot(engine_user_id)

        purchased_products = self._text_tuple(
            self._first_value(
                commerce_summary,
                customer_summary,
                memory,
                "products_purchased",
                "purchased_products",
                "owned_product_ids",
            )
        )
        previous_experiences = self._text_tuple(
            self._first_value(
                commerce_summary,
                customer_summary,
                memory,
                "purchased_experiences",
                "completed_experience_ids",
                "seen_experience_ids",
            )
        )
        free_assets = self._text_tuple(
            self._first_value(
                commerce_summary,
                memory,
                "free_assets_delivered",
                "delivered_free_asset_ids",
            )
        )
        paid_links = self._text_tuple(
            self._first_value(
                commerce_summary,
                memory,
                "paid_media_links_delivered",
                "delivered_paid_media_links",
            )
        )
        previous_offers = self._text_tuple(
            self._first_value(
                customer_summary,
                memory,
                "seen_offer_ids",
                "previous_offers",
            )
        )
        previous_purchases = self._text_tuple(
            self._first_value(
                commerce_summary,
                memory,
                "previous_purchases",
                "products_purchased",
            )
        )

        spending = self._spending_summary(commerce_summary, customer_summary)
        engagement = self._engagement_summary(customer_summary)
        journey = self._commerce_journey(
            purchased_products=purchased_products,
            previous_offers=previous_offers,
            current_experience_id=conversation_state.current_experience_id,
        )

        return TelegramCommerceMemory(
            purchased_products=purchased_products,
            current_experience_id=conversation_state.current_experience_id,
            previous_experiences=previous_experiences,
            current_commerce_journey=journey,
            free_assets_delivered=free_assets,
            paid_media_links_delivered=paid_links,
            previous_offers=previous_offers,
            previous_purchases=previous_purchases,
            last_purchase=self._last_purchase(commerce_summary),
            last_delivery=self._last_delivery_from(memory),
            customer_spending_summary=spending,
            customer_engagement_summary=engagement,
            recommended_commerce_action=self._recommended_commerce_action(
                journey=journey,
                spending=spending,
                engagement=engagement,
                experience_progression=experience_progression,
            ),
            metadata={
                "source": "telegram_commerce_service",
                "memory_owner": "MemoryService",
                "customer_history_owner": "CustomerService",
                "workflow_owner": "TelegramCommerceService",
            },
        )

    def update_commerce_memory(
        self,
        *,
        previous_memory: TelegramCommerceMemory,
        delivery_decision: TelegramDeliveryDecision,
        delivery_payload: TelegramDeliveryPayload,
        conversation_state: TelegramConversationState,
        experience_progression: TelegramExperienceProgression,
    ) -> TelegramCommerceMemory:
        """Update reconstructed Commerce Memory for the current turn."""

        free_assets = previous_memory.free_assets_delivered
        paid_links = previous_memory.paid_media_links_delivered
        if delivery_payload.delivery_method == "free_asset" and delivery_payload.asset_path:
            free_assets = self._append_unique(free_assets, delivery_payload.asset_path)
        if (
            delivery_payload.delivery_method == "paid_media_link"
            and delivery_payload.media_link
        ):
            paid_links = self._append_unique(paid_links, delivery_payload.media_link)

        last_delivery = dict(previous_memory.last_delivery)
        if delivery_payload.delivery_method:
            last_delivery = {
                "delivery_method": delivery_payload.delivery_method,
                "delivery_type": delivery_payload.delivery_type,
                "asset_path": delivery_payload.asset_path,
                "media_link": delivery_payload.media_link,
                "product_reference": delivery_payload.product_reference,
                "blocking_reason": delivery_payload.blocking_reason,
                "next_suggested_action": delivery_payload.next_suggested_action,
            }

        journey = self._commerce_journey(
            purchased_products=previous_memory.purchased_products,
            previous_offers=previous_memory.previous_offers,
            current_experience_id=conversation_state.current_experience_id,
        )

        return TelegramCommerceMemory(
            purchased_products=previous_memory.purchased_products,
            current_experience_id=conversation_state.current_experience_id,
            previous_experiences=previous_memory.previous_experiences,
            current_commerce_journey=journey,
            free_assets_delivered=free_assets,
            paid_media_links_delivered=paid_links,
            previous_offers=previous_memory.previous_offers,
            previous_purchases=previous_memory.previous_purchases,
            last_purchase=previous_memory.last_purchase,
            last_delivery=last_delivery,
            customer_spending_summary=previous_memory.customer_spending_summary,
            customer_engagement_summary=previous_memory.customer_engagement_summary,
            recommended_commerce_action=(
                delivery_decision.next_suggested_action
                or self._recommended_commerce_action(
                    journey=journey,
                    spending=previous_memory.customer_spending_summary,
                    engagement=previous_memory.customer_engagement_summary,
                    experience_progression=experience_progression,
                )
            ),
            metadata={
                "source": "telegram_commerce_service",
                "memory_owner": "MemoryService",
                "customer_history_owner": "CustomerService",
                "workflow_owner": "TelegramCommerceService",
            },
        )

    def update_experience_progression(
        self,
        *,
        previous_progression: TelegramExperienceProgression,
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
        conversation_state: TelegramConversationState,
    ) -> TelegramExperienceProgression:
        """Coordinate the DecisionEngine progression decision."""

        action = self._experience_action(engine_result)
        current_experience_id = self._safe_text(
            self._delivery_value(
                engine_result,
                "experience_id",
                "current_experience_id",
            )
        )
        current_product_id = self._safe_text(
            self._delivery_value(engine_result, "product_id")
        )
        story_position = self._safe_text(
            self._delivery_value(
                engine_result,
                "story_position",
                "current_story_position",
                "current_position",
            )
        )
        asset_position = self._safe_text(
            self._delivery_value(
                engine_result,
                "asset_position",
                "current_asset_position",
                "asset_id",
                "content_item_id",
            )
        )
        progress_percentage = self._progress_percentage(
            self._delivery_value(
                engine_result,
                "progress_percentage",
                "experience_progress_percentage",
            ),
            fallback=previous_progression.progress_percentage,
            action=action,
        )
        experience_state = self._experience_state_for_action(
            action,
            previous_state=previous_progression.experience_state,
        )

        return TelegramExperienceProgression(
            current_experience_id=(
                current_experience_id
                or previous_progression.current_experience_id
                or conversation_state.current_experience_id
            ),
            experience_state=experience_state,
            current_story_position=(
                story_position or previous_progression.current_story_position
            ),
            current_asset_position=(
                asset_position or previous_progression.current_asset_position
            ),
            current_product_id=(
                current_product_id
                or previous_progression.current_product_id
                or conversation_state.current_product_id
            ),
            progress_percentage=progress_percentage,
            last_progression_event={
                "action": action,
                "source": "decision_engine",
                "experience_id": (
                    current_experience_id
                    or previous_progression.current_experience_id
                ),
            },
            next_recommended_experience_action=(
                self._next_experience_action_for_action(action)
            ),
            metadata={
                "source": "telegram_commerce_service",
                "experience_owner": "ExperienceService",
                "decision_owner": "DecisionEngine",
                "workflow_owner": "TelegramCommerceService",
            },
        )

    def build_telegram_delivery_payload(
        self,
        *,
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
        delivery_decision: TelegramDeliveryDecision,
        conversation_state: TelegramConversationState,
        experience_progression: TelegramExperienceProgression,
    ) -> TelegramDeliveryPayload:
        """Build a runtime-owned Telegram delivery payload."""

        response_text = self._runtime_response_text(engine_result)
        prepared_delivery = self._chat_delivery_context(engine_result)

        if prepared_delivery and not prepared_delivery.get("delivery_ready"):
            return self._blocked_payload(
                delivery_decision=delivery_decision,
                conversation_state=conversation_state,
                message_text=response_text,
                reason=(
                    prepared_delivery.get("blocking_reason")
                    or prepared_delivery.get("failure_reason")
                    or "chat_delivery_not_ready"
                ),
            )

        blocking_reason = self._delivery_blocking_reason(delivery_decision)
        if blocking_reason:
            return TelegramDeliveryPayload(
                delivery_type=delivery_decision.delivery_type,
                message_text=response_text,
                product_reference=delivery_decision.current_product_id,
                experience_reference=conversation_state.current_experience_id,
                delivery_reason=delivery_decision.reason,
                blocking_reason=blocking_reason,
                next_suggested_action="skip_delivery",
                delivery_method="blocked",
                metadata={
                    "source": "TelegramCommerceService",
                    "transport_owner": "Telegram runtime",
                    "delivery_owner": "TelegramCommerceService",
                },
            )

        action = delivery_decision.next_suggested_action
        if action == "deliver_free_asset":
            if (
                prepared_delivery
                and prepared_delivery.get("delivery_method") == "free_asset"
            ):
                asset_path = self._safe_text(
                    prepared_delivery.get("asset_path")
                    or prepared_delivery.get("local_vault_path")
                    or self._delivery_value(engine_result, "asset_path", "file_path")
                )
                if not asset_path:
                    return self._blocked_payload(
                        delivery_decision=delivery_decision,
                        conversation_state=conversation_state,
                        message_text=response_text,
                        reason="free_asset_unavailable",
                    )
                return TelegramDeliveryPayload(
                    delivery_type=prepared_delivery.get("delivery_type") or "FREE",
                    message_text=response_text,
                    asset_path=asset_path,
                    product_reference=prepared_delivery.get("product_id"),
                    experience_reference=(
                        prepared_delivery.get("experience_id")
                        or conversation_state.current_experience_id
                    ),
                    delivery_reason=delivery_decision.reason,
                    next_suggested_action=action,
                    delivery_method="free_asset",
                    metadata={
                        "source": "ChatCommerceDeliveryService",
                        "chat_commerce_delivery": prepared_delivery,
                        "transport_owner": "Telegram runtime",
                    },
                )
            asset_path = self._free_asset_path(
                engine_result,
                delivery_decision.free_asset_id,
            )
            if not asset_path:
                return self._blocked_payload(
                    delivery_decision=delivery_decision,
                    conversation_state=conversation_state,
                    message_text=response_text,
                    reason="free_asset_unavailable",
                )
            return TelegramDeliveryPayload(
                delivery_type=delivery_decision.delivery_type or "FREE",
                message_text=response_text,
                asset_path=asset_path,
                product_reference=delivery_decision.current_product_id,
                experience_reference=conversation_state.current_experience_id,
                delivery_reason=delivery_decision.reason,
                next_suggested_action=action,
                delivery_method="free_asset",
                metadata={
                    "asset_owner": "Asset/Local Vault services",
                    "transport_owner": "Telegram runtime",
                    "experience_reference": (
                        experience_progression.current_experience_id
                    ),
                },
            )

        if action == "deliver_paid_media_link":
            if (
                prepared_delivery
                and prepared_delivery.get("delivery_method") == "paid_media_link"
            ):
                media_link = self._safe_text(
                    prepared_delivery.get("media_link")
                    or prepared_delivery.get("fanvue_media_link")
                )
                if not media_link:
                    return self._blocked_payload(
                        delivery_decision=delivery_decision,
                        conversation_state=conversation_state,
                        message_text=response_text,
                        reason="media_link_unavailable",
                    )
                return TelegramDeliveryPayload(
                    delivery_type=prepared_delivery.get("delivery_type") or "PAID",
                    message_text=response_text,
                    media_link=media_link,
                    product_reference=prepared_delivery.get("product_id"),
                    experience_reference=(
                        prepared_delivery.get("experience_id")
                        or conversation_state.current_experience_id
                    ),
                    delivery_reason=delivery_decision.reason,
                    next_suggested_action=action,
                    delivery_method="paid_media_link",
                    metadata={
                        "source": "ChatCommerceDeliveryService",
                        "chat_commerce_delivery": prepared_delivery,
                        "provider_media_uuid": (
                            prepared_delivery.get("provider_media_uuid")
                            or prepared_delivery.get("provider_media_id")
                        ),
                        "fulfillment_id": prepared_delivery.get("fulfillment_id"),
                        "recommendation_id": prepared_delivery.get(
                            "recommendation_id"
                        ),
                        "transport_owner": "Telegram runtime",
                    },
                )
            if not self._product_delivery_eligible(engine_result):
                return self._blocked_payload(
                    delivery_decision=delivery_decision,
                    conversation_state=conversation_state,
                    message_text=response_text,
                    reason="product_not_active",
                )
            if not delivery_decision.paid_media_link:
                return self._blocked_payload(
                    delivery_decision=delivery_decision,
                    conversation_state=conversation_state,
                    message_text=response_text,
                    reason="media_link_unavailable",
                )
            return TelegramDeliveryPayload(
                delivery_type=delivery_decision.delivery_type or "PAID",
                message_text=response_text,
                media_link=delivery_decision.paid_media_link,
                product_reference=delivery_decision.current_product_id,
                experience_reference=conversation_state.current_experience_id,
                delivery_reason=delivery_decision.reason,
                next_suggested_action=action,
                delivery_method="paid_media_link",
                metadata={
                    "media_link_owner": "PublishingService/Product",
                    "transport_owner": "Telegram runtime",
                    "experience_reference": (
                        experience_progression.current_experience_id
                    ),
                },
            )

        if action in {"delay_offer", "skip_delivery"}:
            return TelegramDeliveryPayload(
                delivery_type=delivery_decision.delivery_type,
                message_text=response_text,
                product_reference=delivery_decision.current_product_id,
                experience_reference=conversation_state.current_experience_id,
                delivery_reason=delivery_decision.reason,
                next_suggested_action=action,
                delivery_method="none",
                metadata={"source": "TelegramCommerceService"},
            )

        delivery_method = "offer" if delivery_decision.offer_authorized else "text"
        return TelegramDeliveryPayload(
            delivery_type=delivery_decision.delivery_type,
            message_text=response_text,
            media_link=delivery_decision.paid_media_link,
            product_reference=delivery_decision.current_product_id,
            experience_reference=conversation_state.current_experience_id,
            delivery_reason=delivery_decision.reason,
            next_suggested_action=action or "continue_experience",
            delivery_method=delivery_method,
            metadata={"source": "TelegramCommerceService"},
        )

    def update_conversation_state(
        self,
        *,
        previous_state: TelegramConversationState,
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
        delivery_decision: TelegramDeliveryDecision,
        customer_progress: TelegramCustomerProgress,
    ) -> TelegramConversationState:
        """Rebuild post-decision state for the current commerce turn."""

        current_offer_id = self._safe_text(
            self._delivery_value(engine_result, "offer_id", "id")
        )
        current_offer_kind = self._safe_text(
            self._delivery_value(engine_result, "offer_type", "offer_kind")
        )
        last_delivery = self._last_delivery_from_decision(delivery_decision)

        return TelegramConversationState(
            current_experience_id=(
                customer_progress.current_experience_id
                or previous_state.current_experience_id
            ),
            current_product_id=(
                customer_progress.current_product_id
                or previous_state.current_product_id
            ),
            current_asset_id=(
                customer_progress.current_asset_id
                or previous_state.current_asset_id
            ),
            current_delivery_type=(
                delivery_decision.delivery_type
                or previous_state.current_delivery_type
            ),
            conversation_mode=(
                customer_progress.conversation_state
                or previous_state.conversation_mode
            ),
            current_offer_id=current_offer_id or previous_state.current_offer_id,
            current_offer_kind=(
                current_offer_kind or previous_state.current_offer_kind
            ),
            commerce_state=customer_progress.commerce_state,
            customer_progress=customer_progress,
            last_delivery=last_delivery or previous_state.last_delivery,
            next_recommended_action=self._next_action_for_decision(
                delivery_decision
            ),
            metadata={
                "source": "telegram_commerce_service",
                "state_owner": "TelegramCommerceService",
                "memory_owner": "MemoryService",
                "customer_owner": "CustomerService",
            },
        )

    def build_delivery_decision(
        self,
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
    ) -> TelegramDeliveryDecision:
        """Normalize DecisionEngine delivery output for commerce orchestration."""

        engine_result = DecisionEngineResult.from_value(engine_result)
        if not isinstance(engine_result, Mapping):
            return TelegramDeliveryDecision(
                offer_authorized=False,
                blocked=True,
                reason="decision_engine_no_result",
            )

        prepared_delivery = self._chat_delivery_context(engine_result)
        runtime_decision = self._runtime_decision(engine_result)
        blocked = runtime_decision.blocked if runtime_decision else False
        offer_authorized = (
            not blocked
            and (
                runtime_decision.call_to_action.get("send_offer") is True
                if runtime_decision
                else engine_result.get("send_offer") is True
            )
        )
        commerce_recommendation = self._commerce_recommendation(engine_result)
        current_product_id = self._safe_text(
            prepared_delivery.get("product_id")
            if prepared_delivery
            else None
        ) or self._safe_text(
            (
                runtime_decision.product_reference
                if runtime_decision
                else None
            )
            or self._delivery_value(engine_result, "product_id", "current_product_id")
            or commerce_recommendation.get("product_id")
        )
        delivery_type = (
            prepared_delivery.get("delivery_type")
            if prepared_delivery
            else None
        ) or (
            runtime_decision.delivery_type
            if runtime_decision
            else self._delivery_value(engine_result, "delivery_type")
        )
        delivery_mode = (
            runtime_decision.execution_metadata.get("delivery_permission_mode")
            if runtime_decision
            else None
        ) or (
            "paid"
            if prepared_delivery
            and prepared_delivery.get("delivery_method") == "paid_media_link"
            else None
        ) or self._delivery_value(
            engine_result,
            "delivery_permission_mode",
            "delivery_mode",
        )
        requires_payment = self._requires_payment(
            engine_result,
            delivery_type=delivery_type,
            delivery_mode=delivery_mode,
        )
        delivery_permission = self._delivery_permission(
            engine_result,
            product_id=current_product_id,
            delivery_type=delivery_type,
            delivery_mode=delivery_mode,
            requires_payment=requires_payment,
        )
        if requires_payment is None and "requires_payment" in delivery_permission:
            requires_payment = delivery_permission.get("requires_payment")
        delivery_method = self._delivery_method(
            delivery_type=delivery_type,
            requires_payment=requires_payment,
        )
        free_asset_id = (
            self._safe_text(prepared_delivery.get("asset_id"))
            if prepared_delivery and delivery_method == "free_asset"
            else
            self._safe_text(
                self._delivery_value(engine_result, "asset_id", "content_item_id")
            )
            if delivery_method == "free_asset"
            else None
        )
        paid_media_link = (
            self._safe_text(
                prepared_delivery.get("media_link")
                or prepared_delivery.get("fanvue_media_link")
            )
            if prepared_delivery and delivery_method == "paid_media_link"
            else
            self._paid_media_link(engine_result, current_product_id)
            if delivery_method == "paid_media_link"
            else None
        )
        offer_link = (
            paid_media_link
            or self._delivery_value(engine_result, "fanvue_link", "checkout_url")
            if offer_authorized and requires_payment is not False
            else None
        )
        action = self._delivery_action(
            engine_result,
            delivery_method=delivery_method,
            offer_authorized=offer_authorized,
        )

        return TelegramDeliveryDecision(
            offer_authorized=offer_authorized,
            blocked=blocked,
            current_product_id=current_product_id,
            delivery_type=self._safe_text(delivery_type),
            delivery_permission=delivery_permission,
            delivery_method=delivery_method,
            free_asset_id=free_asset_id,
            paid_media_link=self._safe_text(paid_media_link),
            delivery_mode=self._safe_text(delivery_mode),
            requires_payment=requires_payment,
            offer_link=self._safe_text(offer_link),
            reason=self._delivery_reason(engine_result, blocked=blocked),
            commerce_recommendation=commerce_recommendation,
            next_suggested_action=action,
        )

    def _chat_delivery_context(
        self,
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        value = self._delivery_value(
            engine_result,
            "chat_delivery_payload",
            "delivery_payload",
        )
        if isinstance(value, Mapping):
            return self._safe_metadata(value)
        result = self._delivery_value(engine_result, "chat_delivery_result")
        if isinstance(result, Mapping):
            payload = result.get("payload")
            if isinstance(payload, Mapping):
                context = self._safe_metadata(payload)
                context.setdefault("failure_reason", result.get("failure_reason"))
                context.setdefault("delivery_ready", result.get("success") is True)
                return context
        return {}

    def _record_chat_delivery_execution(
        self,
        *,
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
        execution_result: Any,
    ) -> None:
        delivery_context = self._delivery_value(engine_result, "chat_delivery_result")
        if not isinstance(delivery_context, Mapping):
            return
        service = getattr(
            self.decision_engine,
            "chat_commerce_delivery_service",
            None,
        )
        recorder = getattr(service, "record_execution_result", None)
        if not callable(recorder):
            return
        try:
            recorder(delivery_context, execution_result)
        except Exception:
            return

    def build_customer_progress(
        self,
        *,
        engine_user_id: str,
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
        delivery_decision: TelegramDeliveryDecision,
    ) -> TelegramCustomerProgress:
        """Build a provider-neutral customer progress snapshot."""

        customer_summary = self._customer_summary(engine_user_id)
        current_experience_id = self._summary_or_delivery_value(
            customer_summary,
            engine_result,
            "current_experience_id",
            "experience_id",
        )
        current_product_id = self._summary_or_delivery_value(
            customer_summary,
            engine_result,
            "current_product_id",
            "product_id",
        )
        current_asset_id = self._summary_or_delivery_value(
            customer_summary,
            engine_result,
            "current_asset_id",
            "asset_id",
            "content_item_id",
        )
        conversation_state = self._conversation_state(engine_result)
        commerce_state = self._commerce_state(delivery_decision)

        metadata: dict[str, Any] = {
            "customer_summary_found": customer_summary is not None,
            "delivery_type": delivery_decision.delivery_type,
            "delivery_mode": delivery_decision.delivery_mode,
            "requires_payment": delivery_decision.requires_payment,
        }
        if isinstance(customer_summary, Mapping):
            for key in ("relationship_status", "buyer_tier", "active_session"):
                if key in customer_summary:
                    metadata[key] = customer_summary[key]

        return TelegramCustomerProgress(
            customer_id=engine_user_id,
            current_experience_id=self._safe_text(current_experience_id),
            current_product_id=self._safe_text(current_product_id),
            current_asset_id=self._safe_text(current_asset_id),
            conversation_state=conversation_state,
            commerce_state=commerce_state,
            metadata=metadata,
        )

    def _ensure_customer_memory(self, engine_user_id: str) -> None:
        memory_owner = self.memory_service
        if memory_owner is None:
            memory_owner = getattr(self.decision_engine, "memory", None)
        getter = getattr(memory_owner, "get_or_create_user_memory", None)
        if callable(getter):
            getter(engine_user_id)

    def _memory_snapshot(self, engine_user_id: str) -> Mapping[str, Any] | None:
        memory_owner = self.memory_service
        if memory_owner is None:
            memory_owner = getattr(self.decision_engine, "memory", None)
        getter = getattr(memory_owner, "get_or_create_user_memory", None)
        if not callable(getter):
            return None
        try:
            memory = getter(engine_user_id)
        except Exception:
            return None
        return memory if isinstance(memory, Mapping) else None

    @staticmethod
    def _default_experience_service() -> Any:
        from app.services.experience_service import ExperienceService

        return ExperienceService()

    @staticmethod
    def _default_product_recommendation_service() -> Any:
        from app.services.product_recommendation_service import (
            ProductRecommendationService,
        )

        return ProductRecommendationService()

    @staticmethod
    def _default_publishing_service() -> Any:
        from app.services.publishing_service import PublishingService

        return PublishingService()

    @staticmethod
    def _default_cms_contract_service(
        *,
        experience_service: Any,
        publishing_service: Any,
        recommendation_service: Any,
    ) -> Any:
        from app.services.cms_contract_service import CMSContractService

        return CMSContractService(
            experience_service=experience_service,
            publishing_service=publishing_service,
            recommendation_service=recommendation_service,
        )

    @staticmethod
    def _default_delivery_executor() -> Any:
        from app.services.telegram_delivery_executor import (
            TelegramDeliveryExecutor,
        )

        return TelegramDeliveryExecutor()

    @staticmethod
    def _default_commerce_execution_service() -> Any:
        from app.services.commerce_execution_service import (
            CommerceExecutionService,
        )

        return CommerceExecutionService()

    @staticmethod
    def _default_customer_service() -> Any:
        from app.services.customer_service import CustomerService

        return CustomerService()

    @staticmethod
    def _default_customer_intelligence_service() -> CustomerIntelligenceService:
        return CustomerIntelligenceService()

    def _customer_intelligence_snapshot(
        self,
        engine_user_id: str,
        *,
        commerce_memory: TelegramCommerceMemory,
        conversation_state: TelegramConversationState,
        experience_progression: TelegramExperienceProgression,
    ) -> CustomerIntelligenceSnapshot:
        return self.customer_intelligence_service.build_customer_snapshot(
            customer_id=engine_user_id,
            provider="telegram",
            telegram_context={"engine_user_id": engine_user_id},
            customer_summary=self._customer_summary(engine_user_id),
            commerce_summary=self._customer_commerce_summary(engine_user_id),
            commerce_memory=commerce_memory,
            conversation_state=conversation_state,
            experience_progression=experience_progression,
        )

    def _customer_summary(self, engine_user_id: str) -> Mapping[str, Any] | None:
        getter = getattr(self.customer_service, "get_customer_summary", None)
        if not callable(getter):
            return None
        try:
            summary = getter(engine_user_id)
        except Exception:
            return None
        return summary if isinstance(summary, Mapping) else None

    def _customer_commerce_summary(
        self,
        engine_user_id: str,
    ) -> Mapping[str, Any] | None:
        getter = getattr(self.customer_service, "get_customer_commerce_summary", None)
        if not callable(getter):
            return None
        try:
            summary = getter(engine_user_id)
        except Exception:
            return None
        return summary if isinstance(summary, Mapping) else None

    @staticmethod
    def _chat_history_with_customer_context(
        chat_history: list[Any] | None,
        customer_intelligence_context: Mapping[str, Any],
        commerce_memory: TelegramCommerceMemory,
    ) -> list[Any]:
        history = list(chat_history or [])
        history.append(
            {
                "role": "system",
                "content": "customer_intelligence_snapshot",
                "customer_intelligence": dict(customer_intelligence_context),
            }
        )
        history.append(
            {
                "role": "system",
                "content": "telegram_commerce_memory",
                "commerce_memory": commerce_memory.to_context(),
            }
        )
        return history

    @classmethod
    def _text_tuple(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, Mapping):
            value = value.values()
        if isinstance(value, (str, bytes)):
            values = (value,)
        else:
            try:
                values = tuple(value)
            except TypeError:
                values = (value,)
        return tuple(str(item) for item in values if item is not None)

    @staticmethod
    def _append_unique(values: tuple[str, ...], value: str) -> tuple[str, ...]:
        text = str(value)
        if text in values:
            return values
        return values + (text,)

    @classmethod
    def _spending_summary(
        cls,
        commerce_summary: Mapping[str, Any] | None,
        customer_summary: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        purchase = cls._first_value(
            commerce_summary,
            customer_summary,
            "purchase_summary",
        )
        if isinstance(purchase, Mapping):
            return {
                "purchase_count": purchase.get("purchase_count", 0),
                "total_spend_cents": purchase.get("total_spend_cents", 0),
                "last_purchase_at": purchase.get("last_purchase_at"),
            }
        return {
            "purchase_count": cls._first_value(
                customer_summary,
                "purchase_count",
            )
            or 0,
            "total_spend_cents": cls._first_value(
                customer_summary,
                "total_spend_cents",
            )
            or 0,
            "last_purchase_at": None,
        }

    @classmethod
    def _engagement_summary(
        cls,
        customer_summary: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "message_count": cls._first_value(customer_summary, "message_count") or 0,
            "offer_count": cls._first_value(customer_summary, "offer_count") or 0,
            "relationship_status": cls._first_value(
                customer_summary,
                "relationship_status",
            ),
            "buyer_tier": cls._first_value(customer_summary, "buyer_tier"),
            "active_session": cls._first_value(customer_summary, "active_session"),
        }

    @staticmethod
    def _commerce_journey(
        *,
        purchased_products: tuple[str, ...],
        previous_offers: tuple[str, ...],
        current_experience_id: str | None,
    ) -> str:
        if purchased_products:
            return "customer"
        if previous_offers:
            return "offer_consideration"
        if current_experience_id:
            return "experience_nurture"
        return "discovery"

    @staticmethod
    def _recommended_commerce_action(
        *,
        journey: str,
        spending: Mapping[str, Any],
        engagement: Mapping[str, Any],
        experience_progression: TelegramExperienceProgression,
    ) -> str:
        if experience_progression.experience_state == "paused":
            return "resume_experience"
        if int(spending.get("purchase_count") or 0) > 0:
            return "escalate_commerce_offer"
        if int(engagement.get("offer_count") or 0) > 0:
            return "delay_offer"
        if journey == "experience_nurture":
            return "continue_experience"
        return "continue_free_delivery"

    @staticmethod
    def _last_purchase(
        commerce_summary: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(commerce_summary, Mapping):
            return {}
        purchase = commerce_summary.get("purchase_summary")
        if not isinstance(purchase, Mapping):
            return {}
        return {
            "last_purchase_at": purchase.get("last_purchase_at"),
            "purchase_count": purchase.get("purchase_count", 0),
            "total_spend_cents": purchase.get("total_spend_cents", 0),
        }

    @classmethod
    def _first_value(
        cls,
        *sources_and_names: Any,
    ) -> Any:
        sources = []
        names = []
        for value in sources_and_names:
            if isinstance(value, Mapping) or value is None:
                sources.append(value)
            else:
                names.append(str(value))

        for source in sources:
            if not isinstance(source, Mapping):
                continue
            for name in names:
                value = cls._nested_value(source, name)
                if value is not None:
                    return value
        return None

    @classmethod
    def _nested_value(cls, source: Mapping[str, Any], name: str) -> Any:
        if name in source:
            return source[name]
        for parent in (
            "conversation",
            "conversation_summary",
            "progression",
            "customer_progression",
            "recommendation",
            "current_recommendation",
            "commerce",
            "telegram_conversation_state",
        ):
            nested = source.get(parent)
            if isinstance(nested, Mapping) and name in nested:
                return nested[name]
        return None

    @classmethod
    def _summary_or_delivery_value(
        cls,
        customer_summary: Mapping[str, Any] | None,
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
        summary_name: str,
        *delivery_names: str,
    ) -> Any:
        if isinstance(customer_summary, Mapping):
            value = customer_summary.get(summary_name)
            if value is not None:
                return value
        return cls._delivery_value(engine_result, *delivery_names)

    @staticmethod
    def _runtime_decision(
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
    ) -> RuntimeDecision | None:
        decision_result = DecisionEngineResult.from_value(engine_result)
        if decision_result is None:
            return None
        return decision_result.runtime_decision

    @classmethod
    def _runtime_response_text(
        cls,
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
    ) -> str:
        runtime_decision = cls._runtime_decision(engine_result)
        if runtime_decision and runtime_decision.response_text is not None:
            return runtime_decision.response_text
        if isinstance(engine_result, Mapping) and isinstance(
            engine_result.get("response"),
            str,
        ):
            return engine_result["response"]
        return ""

    @staticmethod
    def _delivery_value(
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
        *names: str,
    ) -> Any:
        engine_result = DecisionEngineResult.from_value(engine_result)
        if not isinstance(engine_result, Mapping):
            return None

        sources: list[Mapping[str, Any]] = [engine_result]
        progression = engine_result.get("experience_progression")
        if isinstance(progression, Mapping):
            sources.append(progression)
        offer = engine_result.get("offer")
        if isinstance(offer, Mapping):
            sources.append(offer)
            content = offer.get("content")
            if isinstance(content, Mapping):
                sources.append(content)

        for source in sources:
            for name in names:
                value = source.get(name)
                if value is not None:
                    return value
        return None

    @classmethod
    def _last_delivery_from(
        cls,
        memory: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(memory, Mapping):
            return {}
        direct = memory.get("last_delivery")
        if isinstance(direct, Mapping):
            return {
                str(key): value
                for key, value in direct.items()
                if cls._safe_metadata_key(str(key))
            }
        result = {}
        for key in (
            "last_delivery_type",
            "last_delivery_mode",
            "last_media_link",
            "last_asset_id",
            "last_product_id",
        ):
            value = memory.get(key)
            if value is not None:
                result[key] = value
        return result

    @staticmethod
    def _last_delivery_from_decision(
        delivery_decision: TelegramDeliveryDecision,
    ) -> dict[str, Any]:
        if not delivery_decision.offer_authorized and not delivery_decision.blocked:
            return {}
        return {
            "delivery_type": delivery_decision.delivery_type,
            "delivery_method": delivery_decision.delivery_method,
            "delivery_mode": delivery_decision.delivery_mode,
            "requires_payment": delivery_decision.requires_payment,
            "offer_authorized": delivery_decision.offer_authorized,
            "blocked": delivery_decision.blocked,
            "reason": delivery_decision.reason,
            "product_id": delivery_decision.current_product_id,
            "free_asset_id": delivery_decision.free_asset_id,
            "paid_media_link": delivery_decision.paid_media_link,
        }

    def _commerce_recommendation(
        self,
        engine_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        explicit = engine_result.get("commerce_recommendation")
        if isinstance(explicit, Mapping):
            return self._safe_metadata(explicit)

        offer = engine_result.get("offer")
        if isinstance(offer, Mapping):
            content = offer.get("content")
            product_id = self._delivery_value(engine_result, "product_id")
            if product_id is not None:
                return {
                    "source": "decision_engine",
                    "product_id": str(product_id),
                    "offer_type": self._safe_text(offer.get("offer_type")),
                    "title": (
                        self._safe_text(content.get("file_name"))
                        if isinstance(content, Mapping)
                        else None
                    ),
                }

        getter = getattr(self.product_recommendation_service, "get_offer_candidate", None)
        if callable(getter):
            try:
                candidate = getter(
                    offer_type=str(engine_result.get("offer_type") or "premium")
                )
            except Exception:
                candidate = None
            recommendation = self._recommendation_from_candidate(candidate)
            if recommendation:
                return recommendation
        return {}

    def _delivery_permission(
        self,
        engine_result: Mapping[str, Any],
        *,
        product_id: str | None,
        delivery_type: Any,
        delivery_mode: Any,
        requires_payment: bool | None,
    ) -> dict[str, Any]:
        explicit_allowed = self._delivery_value(
            engine_result,
            "delivery_allowed",
            "delivery_permission_allowed",
        )
        explicit_reason = self._delivery_value(
            engine_result,
            "delivery_permission_reason",
            "delivery_reason",
        )
        if explicit_allowed is not None or explicit_reason is not None:
            return {
                "allowed": bool(explicit_allowed)
                if explicit_allowed is not None
                else None,
                "delivery_mode": self._safe_text(delivery_mode),
                "requires_payment": requires_payment,
                "reason": self._safe_text(explicit_reason),
                "source": "decision_engine",
            }

        builder = getattr(self.cms_contract_service, "build_delivery_permission", None)
        if callable(builder) and product_id:
            try:
                permission = builder(
                    subject_id=product_id,
                    delivery_mode=self._delivery_mode_for_permission(
                        delivery_type=delivery_type,
                        delivery_mode=delivery_mode,
                        requires_payment=requires_payment,
                    ),
                    allowed=True,
                    reason=None,
                )
            except Exception:
                permission = None
            normalized = self._permission_to_dict(permission)
            if normalized:
                normalized["source"] = "CMSContractService"
                return normalized

        return {
            "allowed": None,
            "delivery_mode": self._safe_text(delivery_mode),
            "requires_payment": requires_payment,
            "reason": None,
            "source": "unavailable",
        }

    def _paid_media_link(
        self,
        engine_result: DecisionEngineResult | Mapping[str, Any],
        product_id: str | None,
    ) -> str | None:
        runtime_decision = self._runtime_decision(engine_result)
        if runtime_decision:
            explicit = runtime_decision.publishing_reference.get("media_link")
            if explicit:
                return self._safe_text(explicit)

        explicit = self._delivery_value(
            engine_result,
            "media_link",
            "paid_media_link",
            "provider_output_url",
            "fanvue_link",
            "checkout_url",
        )
        if explicit:
            return self._safe_text(explicit)

        getter = getattr(self.publishing_service, "get_by_product_id", None)
        if callable(getter) and product_id:
            try:
                publishing = getter(product_id)
            except Exception:
                publishing = None
            link = self._first_value(
                publishing if isinstance(publishing, Mapping) else None,
                "media_link",
                "provider_output_url",
                "output_url",
            )
            if link:
                return self._safe_text(link)
        return None

    def _free_asset_path(
        self,
        engine_result: Mapping[str, Any] | None,
        asset_id: str | None,
    ) -> str | None:
        explicit = self._delivery_value(
            engine_result,
            "asset_path",
            "local_vault_path",
            "file_path",
        )
        if explicit:
            return self._safe_text(explicit)

        for getter_name in (
            "get_asset_details",
            "get_asset",
            "get_by_id",
            "get_asset_item",
        ):
            getter = getattr(self.asset_service, getter_name, None)
            if not callable(getter) or not asset_id:
                continue
            try:
                asset = getter(asset_id)
            except Exception:
                asset = None
            asset_path = self._asset_path_from(asset)
            if asset_path:
                return asset_path
        return None

    @classmethod
    def _asset_path_from(cls, asset: Any) -> str | None:
        item = cls._read_value(asset, "item") or asset
        media = cls._read_value(item, "media") or item
        value = cls._read_value(
            media,
            "local_vault_path",
            "asset_path",
            "file_path",
            "legacy_file_path",
        )
        return cls._safe_text(value)

    def _delivery_blocking_reason(
        self,
        delivery_decision: TelegramDeliveryDecision,
    ) -> str | None:
        if delivery_decision.blocked:
            return delivery_decision.reason or "delivery_blocked"
        allowed = delivery_decision.delivery_permission.get("allowed")
        if allowed is False:
            return (
                delivery_decision.delivery_permission.get("reason")
                or "delivery_permission_denied"
            )
        guard = getattr(self.content_delivery_guard_service, "validate", None)
        if callable(guard):
            try:
                result = guard(delivery_decision.to_dict())
            except Exception:
                result = None
            if isinstance(result, Mapping) and result.get("allowed") is False:
                return self._safe_text(result.get("reason")) or "guard_blocked"
        return None

    @staticmethod
    def _product_delivery_eligible(
        engine_result: Mapping[str, Any] | None,
    ) -> bool:
        status = TelegramCommerceService._delivery_value(
            engine_result,
            "product_status",
            "status",
        )
        if status is None:
            return True
        return str(status).strip().upper() in {
            "ACTIVE",
            "APPROVED",
            "AVAILABLE",
            "PUBLISHED",
        }

    @staticmethod
    def _blocked_payload(
        *,
        delivery_decision: TelegramDeliveryDecision,
        conversation_state: TelegramConversationState,
        message_text: str,
        reason: str,
    ) -> TelegramDeliveryPayload:
        return TelegramDeliveryPayload(
            delivery_type=delivery_decision.delivery_type,
            message_text=message_text,
            product_reference=delivery_decision.current_product_id,
            experience_reference=conversation_state.current_experience_id,
            delivery_reason=delivery_decision.reason,
            blocking_reason=reason,
            next_suggested_action="skip_delivery",
            delivery_method="blocked",
            metadata={
                "source": "TelegramCommerceService",
                "transport_owner": "Telegram runtime",
            },
        )

    @staticmethod
    def _delivery_method(
        *,
        delivery_type: Any,
        requires_payment: bool | None,
    ) -> str | None:
        if requires_payment is True:
            return "paid_media_link"
        if requires_payment is False:
            return "free_asset"
        if delivery_type:
            normalized = str(delivery_type).upper()
            if normalized == "PAID":
                return "paid_media_link"
            if normalized == "FREE":
                return "free_asset"
        return None

    @staticmethod
    def _delivery_action(
        engine_result: DecisionEngineResult | Mapping[str, Any],
        *,
        delivery_method: str | None,
        offer_authorized: bool,
    ) -> str:
        runtime_decision = TelegramCommerceService._runtime_decision(engine_result)
        value = (
            (runtime_decision.delivery_action if runtime_decision else None)
            or engine_result.get("delivery_action")
            or engine_result.get("commerce_action")
            or engine_result.get("next_suggested_action")
        )
        normalized = str(value or "").strip().lower().replace(" ", "_")
        aliases = {
            "deliver_free": "deliver_free_asset",
            "free_asset": "deliver_free_asset",
            "deliver_paid": "deliver_paid_media_link",
            "paid_media_link": "deliver_paid_media_link",
            "continue": "continue_experience",
            "delay": "delay_offer",
            "skip": "skip_delivery",
            "different_product": "recommend_different_product",
            "escalate": "escalate_commerce_offer",
        }
        normalized = aliases.get(normalized, normalized)
        supported = {
            "deliver_free_asset",
            "deliver_paid_media_link",
            "continue_experience",
            "delay_offer",
            "skip_delivery",
            "recommend_different_product",
            "escalate_commerce_offer",
        }
        if normalized in supported:
            return normalized
        if delivery_method == "free_asset" and offer_authorized:
            return "deliver_free_asset"
        if delivery_method == "paid_media_link" and offer_authorized:
            return "deliver_paid_media_link"
        return "continue_experience"

    @staticmethod
    def _delivery_mode_for_permission(
        *,
        delivery_type: Any,
        delivery_mode: Any,
        requires_payment: bool | None,
    ) -> str:
        if delivery_mode:
            return str(delivery_mode)
        if requires_payment is True:
            return "paid"
        if requires_payment is False:
            return "included"
        if str(delivery_type or "").upper() == "FREE":
            return "included"
        return "paid"

    @classmethod
    def _permission_to_dict(cls, permission: Any) -> dict[str, Any]:
        if permission is None:
            return {}
        return {
            "allowed": cls._read_value(permission, "allowed"),
            "delivery_mode": cls._enum_text(
                cls._read_value(permission, "delivery_mode")
            ),
            "requires_payment": cls._read_value(permission, "requires_payment"),
            "reason": cls._safe_text(cls._read_value(permission, "reason")),
            "price_cents": cls._read_value(permission, "price_cents"),
            "currency": cls._safe_text(cls._read_value(permission, "currency")),
        }

    @classmethod
    def _recommendation_from_candidate(cls, candidate: Any) -> dict[str, Any]:
        if candidate is None:
            return {}
        product = cls._read_value(candidate, "product")
        product_id = cls._read_value(product, "product_id", "id")
        return {
            "source": "ProductRecommendationService",
            "offer_id": cls._safe_text(cls._read_value(candidate, "offer_id")),
            "offer_kind": cls._enum_text(cls._read_value(candidate, "offer_kind")),
            "product_id": cls._safe_text(product_id),
            "title": cls._safe_text(cls._read_value(candidate, "title")),
            "reason": cls._safe_text(cls._read_value(candidate, "reason")),
            "score": cls._read_value(candidate, "score"),
        }

    @classmethod
    def _safe_metadata(cls, value: Mapping[str, Any]) -> dict[str, Any]:
        return {
            str(key): item
            for key, item in value.items()
            if cls._safe_metadata_key(str(key))
        }

    @staticmethod
    def _read_value(value: Any, *names: str) -> Any:
        if value is None:
            return None
        for name in names:
            if isinstance(value, Mapping) and name in value:
                return value[name]
            if hasattr(value, name):
                return getattr(value, name)
        return None

    @staticmethod
    def _enum_text(value: Any) -> str | None:
        if value is None:
            return None
        enum_value = getattr(value, "value", value)
        return str(enum_value)

    @classmethod
    def _last_progression_event_from(
        cls,
        memory: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(memory, Mapping):
            return {}
        event = memory.get("last_progression_event")
        if isinstance(event, Mapping):
            return {
                str(key): value
                for key, value in event.items()
                if cls._safe_metadata_key(str(key))
            }
        action = memory.get("last_experience_action")
        if action is None:
            return {}
        return {"action": str(action), "source": "memory"}

    @classmethod
    def _experience_action(
        cls,
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
    ) -> str:
        runtime_decision = cls._runtime_decision(engine_result)
        value = cls._delivery_value(
            engine_result,
            "experience_action",
            "progression_action",
            "next_experience_action",
        )
        if value is None and runtime_decision:
            value = runtime_decision.delivery_action
        if value is None and isinstance(engine_result, Mapping):
            progression = engine_result.get("experience_progression")
            if isinstance(progression, Mapping):
                value = (
                    progression.get("action")
                    or progression.get("experience_action")
                    or progression.get("progression_action")
                )
        normalized = str(value or "continue").strip().lower().replace(" ", "_")
        aliases = {
            "continue": "continue_experience",
            "pause": "pause_experience",
            "resume": "resume_experience",
            "complete": "complete_experience",
            "switch": "switch_experience",
            "restart": "restart_experience",
        }
        normalized = aliases.get(normalized, normalized)
        supported = {
            "continue_experience",
            "pause_experience",
            "resume_experience",
            "complete_experience",
            "switch_experience",
            "restart_experience",
        }
        return normalized if normalized in supported else "continue_experience"

    @staticmethod
    def _progress_percentage(
        value: Any,
        *,
        session_step: Any = None,
        active_session: Any = None,
        fallback: int = 0,
        action: str | None = None,
    ) -> int:
        if action == "complete_experience":
            return 100
        if action == "restart_experience":
            return 0

        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            parsed = None

        if parsed is None and session_step is not None:
            try:
                parsed = int(float(session_step)) * 20
            except (TypeError, ValueError):
                parsed = None

        if parsed is None:
            parsed = fallback
        if parsed == 0 and active_session is True:
            parsed = 10
        return max(0, min(100, parsed))

    @staticmethod
    def _loaded_experience_state(
        *,
        current_experience_id: Any,
        active_session: Any,
        progress_percentage: int,
    ) -> str:
        if progress_percentage >= 100:
            return "complete"
        if current_experience_id and active_session is False:
            return "paused"
        if current_experience_id:
            return "active"
        return "not_started"

    @staticmethod
    def _experience_state_for_action(
        action: str,
        *,
        previous_state: str | None,
    ) -> str:
        states = {
            "continue_experience": "active",
            "pause_experience": "paused",
            "resume_experience": "active",
            "complete_experience": "complete",
            "switch_experience": "active",
            "restart_experience": "active",
        }
        return states.get(action, previous_state or "active")

    @staticmethod
    def _next_experience_action_for_loaded_state(
        *,
        current_experience_id: Any,
        experience_state: str,
    ) -> str:
        if experience_state == "paused":
            return "resume_experience"
        if experience_state == "complete":
            return "switch_experience"
        if current_experience_id:
            return "continue_experience"
        return "select_experience"

    @staticmethod
    def _next_experience_action_for_action(action: str) -> str:
        mapping = {
            "continue_experience": "continue_experience",
            "pause_experience": "resume_experience",
            "resume_experience": "continue_experience",
            "complete_experience": "switch_experience",
            "switch_experience": "continue_experience",
            "restart_experience": "continue_experience",
        }
        return mapping.get(action, "continue_experience")

    @staticmethod
    def _next_action_for_loaded_state(
        progress: TelegramCustomerProgress,
    ) -> str:
        if progress.commerce_state:
            return "continue_commerce"
        if progress.current_experience_id:
            return "continue_experience"
        return "evaluate_customer_message"

    @staticmethod
    def _next_action_for_decision(
        delivery_decision: TelegramDeliveryDecision,
    ) -> str:
        if delivery_decision.next_suggested_action:
            return delivery_decision.next_suggested_action
        if delivery_decision.blocked:
            return "review_blocked_response"
        if delivery_decision.requires_payment is True:
            return "send_paid_media_link"
        if delivery_decision.requires_payment is False:
            return "send_free_asset"
        if delivery_decision.offer_authorized:
            return "prepare_offer_delivery"
        return "continue_conversation"

    @staticmethod
    def _safe_metadata_key(key: str) -> bool:
        lowered = key.lower()
        return not any(
            marker in lowered
            for marker in (
                "authorization",
                "cookie",
                "password",
                "prompt",
                "secret",
                "token",
            )
        )

    def _requires_payment(
        self,
        engine_result: DecisionEngineResult | Mapping[str, Any],
        *,
        delivery_type: Any,
        delivery_mode: Any,
    ) -> bool | None:
        runtime_decision = self._runtime_decision(engine_result)
        if runtime_decision:
            value = runtime_decision.execution_metadata.get(
                "delivery_requires_payment"
            )
            if value is None:
                value = runtime_decision.execution_metadata.get("requires_payment")
        else:
            value = None
        if value is None:
            value = self._delivery_value(
                engine_result,
                "delivery_requires_payment",
                "requires_payment",
            )
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "paid"}:
                return True
            if normalized in {"false", "0", "no", "free", "included"}:
                return False
        if delivery_mode:
            return str(delivery_mode).lower() == "paid"
        if delivery_type:
            return str(delivery_type).upper() == "PAID"
        return None

    @staticmethod
    def _conversation_state(
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
    ) -> str | None:
        if not isinstance(engine_result, Mapping):
            return None
        for name in ("effective_route", "relationship_route", "route", "mode"):
            value = engine_result.get(name)
            if value is not None:
                return str(value)
        return None

    @staticmethod
    def _commerce_state(delivery_decision: TelegramDeliveryDecision) -> str:
        if delivery_decision.blocked:
            return "blocked"
        if not delivery_decision.offer_authorized:
            return "conversation"
        if delivery_decision.requires_payment is False:
            return "free_delivery"
        if delivery_decision.requires_payment is True:
            return "paid_media_link_delivery"
        return "offer"

    @staticmethod
    def _delivery_reason(
        engine_result: DecisionEngineResult | Mapping[str, Any],
        *,
        blocked: bool,
    ) -> str | None:
        runtime_decision = TelegramCommerceService._runtime_decision(engine_result)
        if blocked:
            if runtime_decision and runtime_decision.block_reason:
                return runtime_decision.block_reason
            error = engine_result.get("error")
            return str(error) if error else "blocked"
        reason = engine_result.get("delivery_reason") or engine_result.get(
            "recommendation_reason"
        )
        return str(reason) if reason is not None else None

    @staticmethod
    def _safe_error_code(
        engine_result: DecisionEngineResult | Mapping[str, Any] | None,
    ) -> str | None:
        if not isinstance(engine_result, Mapping):
            return "decision_engine_no_result"
        error = engine_result.get("error")
        if isinstance(error, str) and error:
            return error
        return None

    @staticmethod
    def _safe_text(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def _diagnostics(
        self,
        delivery_decision: TelegramDeliveryDecision,
        *,
        conversation_state: TelegramConversationState,
        experience_progression: TelegramExperienceProgression,
        commerce_memory: TelegramCommerceMemory,
        delivery_payload: TelegramDeliveryPayload,
        delivery_execution_result: Any | None = None,
        commerce_execution_result: Any | None = None,
        customer_intelligence_snapshot: Any | None = None,
    ) -> dict[str, Any]:
        execution_status = None
        execution_owner = type(self.delivery_executor).__name__
        if delivery_execution_result is not None:
            execution_status = delivery_execution_result.status
        commerce_execution_status = None
        commerce_execution_plan = None
        commerce_runtime_actions: tuple[str, ...] = ()
        if commerce_execution_result is not None:
            commerce_execution_status = getattr(
                commerce_execution_result,
                "status",
                None,
            )
            execution_plan = getattr(
                commerce_execution_result,
                "execution_plan",
                None,
            )
            commerce_execution_plan = getattr(
                execution_plan,
                "execution_type",
                None,
            )
            runtime_intent = getattr(
                commerce_execution_result,
                "runtime_intent",
                None,
            )
            commerce_runtime_actions = tuple(
                getattr(action, "value", str(action))
                for action in getattr(runtime_intent, "actions", ()) or ()
            )

        return {
            "orchestrator": "TelegramCommerceService",
            "commerce_execution_boundary": type(
                self.commerce_execution_service
            ).__name__,
            "commerce_execution_status": commerce_execution_status,
            "commerce_execution_plan": commerce_execution_plan,
            "commerce_runtime_actions": commerce_runtime_actions,
            "decision_engine_boundary": type(self.decision_engine).__name__,
            "experience_boundary": type(self.experience_service).__name__,
            "product_recommendation_boundary": type(
                self.product_recommendation_service
            ).__name__,
            "cms_contract_boundary": type(self.cms_contract_service).__name__,
            "publishing_boundary": type(self.publishing_service).__name__,
            "customer_boundary": type(self.customer_service).__name__,
            "customer_intelligence_boundary": type(
                self.customer_intelligence_service
            ).__name__,
            "customer_intelligence_stage": getattr(
                getattr(customer_intelligence_snapshot, "relationship_stage", None),
                "value",
                None,
            ),
            "memory_boundary": (
                type(self.memory_service).__name__
                if self.memory_service is not None
                else None
            ),
            "delivery_type": delivery_decision.delivery_type,
            "delivery_method": delivery_decision.delivery_method,
            "delivery_mode": delivery_decision.delivery_mode,
            "delivery_requires_payment": delivery_decision.requires_payment,
            "delivery_permission": delivery_decision.delivery_permission,
            "delivery_next_suggested_action": (
                delivery_decision.next_suggested_action
            ),
            "conversation_mode": conversation_state.conversation_mode,
            "commerce_state": conversation_state.commerce_state,
            "next_recommended_action": (
                conversation_state.next_recommended_action
            ),
            "experience_state": experience_progression.experience_state,
            "experience_progress_percentage": (
                experience_progression.progress_percentage
            ),
            "next_recommended_experience_action": (
                experience_progression.next_recommended_experience_action
            ),
            "telegram_delivery_payload_method": delivery_payload.delivery_method,
            "telegram_delivery_payload_blocking_reason": (
                delivery_payload.blocking_reason
            ),
            "telegram_delivery_execution_boundary": execution_owner,
            "telegram_delivery_execution_status": execution_status,
            "commerce_memory_journey": commerce_memory.current_commerce_journey,
            "recommended_commerce_action": (
                commerce_memory.recommended_commerce_action
            ),
        }
