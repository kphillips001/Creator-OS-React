"""Canonical deterministic runtime for Photoshoot Session Selling."""

from app.models.customer_photoshoot_lifecycle import CustomerPhotoshootStatus
from app.models.ownership_intelligence import OwnershipAnswerState, OwnershipIdentity
from app.models.photoshoot_session_runtime import (
    PhotoshootSessionRuntimeState,
    PhotoshootSessionRuntimeStatus,
)
from app.repositories.customer_commerce_repository import CustomerCommerceRepository
from app.repositories.customer_photoshoot_lifecycle_repository import CustomerPhotoshootLifecycleRepository
from app.repositories.photoshoot_session_sales_strategy_repository import (
    PhotoshootSessionSalesStrategyRepository,
)
from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
from app.services.ownership_intelligence_service import OwnershipIntelligenceService


class PhotoshootSessionRuntimeUnavailable(ValueError):
    pass


class PhotoshootSessionRuntimeService:
    """Loads canonical state and executes, but never invents, a sales strategy."""

    def __init__(self, *, customers=None, lifecycles=None, ownership=None, strategies=None):
        self.customers = customers or CustomerCommerceRepository()
        self.lifecycles = lifecycles or CustomerPhotoshootLifecycleService(
            CustomerPhotoshootLifecycleRepository()
        )
        self.ownership = ownership or OwnershipIntelligenceService()
        self.strategies = strategies or PhotoshootSessionSalesStrategyRepository()

    def evaluate(self, *, creator_profile_id: int, customer_commerce_profile_id,
                 photoshoot_session_id: str) -> PhotoshootSessionRuntimeState:
        customer = self.customers.get_by_id(
            customer_commerce_profile_id, creator_profile_id=creator_profile_id
        )
        if customer is None:
            raise KeyError("Customer commerce profile not found.")
        strategy = self.strategies.latest(str(photoshoot_session_id))
        if strategy is None:
            raise PhotoshootSessionRuntimeUnavailable(
                "Completed Photoshoot has no READY Session Sales Strategy."
            )
        lifecycle = self.lifecycles.repository.get(
            creator_profile_id=creator_profile_id,
            customer_commerce_profile_id=customer.customer_commerce_profile_id,
            photoshoot_id=str(photoshoot_session_id),
        )
        answer = self.ownership.answer(OwnershipIdentity(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=int(customer.fanvue_account_id),
            external_fanvue_user_uuid=customer.external_fanvue_user_uuid,
            telegram_user_id=customer.telegram_user_id,
        ))
        if answer.state in {OwnershipAnswerState.INSUFFICIENT, OwnershipAnswerState.CONFLICTING}:
            raise PhotoshootSessionRuntimeUnavailable(
                "Canonical customer ownership is insufficient or conflicting."
            )
        purchased = set()
        presented = set()
        if lifecycle is not None:
            coverage = self.lifecycles.repository.coverage(lifecycle.lifecycle_id)
            purchased.update(coverage["purchased_asset_ids"])
            presented.update(coverage["presented_asset_ids"])
        owned = set(int(value) for value in answer.owned_asset_ids) | purchased
        ordered = tuple(sorted(strategy.shots, key=lambda item: (item.sales_position, item.asset_id)))
        strategy_ids = {item.asset_id for item in ordered}
        advanced = {
            item.asset_id for item in ordered
            if item.asset_id in owned
            or (
                str(item.access_recommendation).upper() == "FREE"
                and item.asset_id in presented
            )
        }
        owned_strategy_ids = tuple(item.asset_id for item in ordered if item.asset_id in owned)

        if lifecycle is None:
            status = PhotoshootSessionRuntimeStatus.NOT_STARTED
        elif lifecycle.status is CustomerPhotoshootStatus.COMPLETED:
            status = PhotoshootSessionRuntimeStatus.COMPLETED
        elif lifecycle.status in {CustomerPhotoshootStatus.CLOSED, CustomerPhotoshootStatus.DECLINED}:
            status = PhotoshootSessionRuntimeStatus.ABANDONED
        else:
            status = PhotoshootSessionRuntimeStatus.ACTIVE

        all_owned = bool(ordered) and strategy_ids.issubset(advanced)
        if all_owned and lifecycle is not None and lifecycle.status in {
            CustomerPhotoshootStatus.ACTIVE, CustomerPhotoshootStatus.OBJECTION,
        }:
            lifecycle = self.lifecycles.transition(
                lifecycle, CustomerPhotoshootStatus.COMPLETED,
                event_type="SESSION_RUNTIME_COMPLETED",
                metadata={"strategy_version": strategy.strategy_version},
            )
            status = PhotoshootSessionRuntimeStatus.COMPLETED

        current_index = next(
            (index for index, item in enumerate(ordered) if item.asset_id not in advanced),
            len(ordered) - 1 if ordered else 0,
        )
        current = ordered[current_index] if ordered else None
        next_item = (
            ordered[current_index + 1]
            if current is not None and current_index + 1 < len(ordered) else None
        )
        if status is PhotoshootSessionRuntimeStatus.COMPLETED:
            next_item = None
        return PhotoshootSessionRuntimeState(
            customer_commerce_profile_id=customer.customer_commerce_profile_id,
            photoshoot_session_id=str(photoshoot_session_id),
            lifecycle_id=lifecycle.lifecycle_id if lifecycle else None,
            status=status, strategy_version=strategy.strategy_version,
            current_position=(current_index + 1 if current else 0),
            total_positions=len(ordered),
            current_asset_id=current.asset_id if current else None,
            current_sales_role=current.sales_role if current else None,
            next_asset_id=next_item.asset_id if next_item else None,
            next_sales_role=next_item.sales_role if next_item else None,
            owned_asset_ids=owned_strategy_ids,
            conversation_goal=current.conversation_goal if current else None,
            psychological_objective=current.psychological_objective if current else None,
            customer_engagement_strategy=strategy.customer_engagement_strategy,
            escalation_pacing=strategy.escalation_pacing,
            session_completion_strategy=strategy.session_completion_strategy,
            metadata={
                "ownershipState": answer.state.value,
                "advancementAuthority": "CANONICAL_OWNERSHIP",
                "strategySource": "PERSISTED_SESSION_SALES_STRATEGY",
                "lifecycleStatus": lifecycle.status.value if lifecycle else None,
            },
        )
