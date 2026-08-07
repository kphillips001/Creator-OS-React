"""Background Operations adapter for Autonomous Inspiration."""
from __future__ import annotations

from app.services.content_studio_background_executor import ContentStudioBackgroundExecutor


class ContentStudioAutonomousBackgroundExecutor:
    executor_key = "content_studio_autonomous_inspiration"

    def execute(self, operation, operations, *, worker_id: str) -> None:
        from app.api.content_studio import (
            AutonomousInspirationRequest,
            _execute_autonomous_inspiration,
        )

        if ContentStudioBackgroundExecutor.recover_submitted(operation, operations):
            return
        request = AutonomousInspirationRequest(**dict(operation.metadata.get("request") or {}))
        total = max(1, int(operation.progress_total or operation.metadata.get("imageCount") or 6))
        observe = ContentStudioBackgroundExecutor.operation_observer(
            operation, operations, worker_id=worker_id, total=total)
        result = _execute_autonomous_inspiration(
            str(operation.operation_id), request,
            state_callback=observe,
            account_id=operation.account_id,
            directions_override=tuple(operation.metadata.get("inspirationDirections") or ()),
        )
        ContentStudioBackgroundExecutor.finish(operation, operations, result)
