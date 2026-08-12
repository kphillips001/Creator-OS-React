"""Durable Background Operation executor for Session Sales Strategy generation."""
from __future__ import annotations

from app.services.photoshoot_session_sales_strategy_service import (
    SESSION_SALES_STRATEGY_VERSION,
    PhotoshootSessionSalesStrategyService,
)


class PhotoshootSessionStrategyBackgroundExecutor:
    executor_key = "photoshoot_session_sales_strategy"

    def __init__(self, strategy=None) -> None:
        self.strategy = strategy or PhotoshootSessionSalesStrategyService()

    def execute(self, operation, operations, *, worker_id: str) -> None:
        metadata = dict(operation.metadata or {})
        deliverable_id = str(metadata.get("deliverableId") or operation.subject_id)
        strategy_version = str(
            metadata.get("strategyVersion") or SESSION_SALES_STRATEGY_VERSION
        )
        operations.progress(
            operation.operation_id, current=0, total=1, percent=5,
            stage="VALIDATING_SESSION", message="Validating Session selling configuration",
        )
        # The provider call is synchronous. Keep this operation exclusively leased while
        # Grok analyzes the persisted Photoshoot intelligence.
        operations.repository.renew_lease(
            operation.operation_id, worker_id, lease_seconds=900,
        )
        strategy = self.strategy.generate(
            deliverable_id,
            creator_profile_id=int(operation.creator_profile_id),
            strategy_version=strategy_version,
        )
        operations.progress(
            operation.operation_id, current=1, total=1, percent=100,
            stage="STRATEGY_READY", message="Session Sales Strategy ready",
            result_reference=str(strategy.deliverable_id),
            metadata={"strategyVersion": strategy.strategy_version},
        )
        operations.succeed(
            operation.operation_id,
            result_reference=str(strategy.deliverable_id),
            message="Session Sales Strategy ready",
            metadata={"strategyVersion": strategy.strategy_version},
        )
