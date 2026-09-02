"""Durable failed-slot retry executor for partial Explicit generation batches."""
from __future__ import annotations

from dataclasses import replace


class ExplicitFailedRetryBackgroundExecutor:
    executor_key = "content_studio_explicit_failed_retry"

    def execute(self, operation, operations, *, worker_id: str) -> None:
        from app.services.content_studio_background_executor import ContentStudioBackgroundExecutor

        cycle = dict(operation.metadata.get("retryCycle") or {})
        cycle_id = str(cycle.get("cycleId") or "")
        failed_ids = tuple(str(value) for value in cycle.get("failedItemIds") or ())
        if not cycle_id or not failed_ids:
            operations.fail(operation.operation_id, "Explicit retry cycle metadata is incomplete.")
            return

        child_executor = ContentStudioBackgroundExecutor()
        for item_id in failed_ids:
            current = operations.repository._one_unscoped(operation.operation_id)
            if current.status in {"CANCEL_REQUESTED", "CANCELLED"}:
                if current.status == "CANCEL_REQUESTED":
                    operations.cancel(
                        current.operation_id,
                        "Failed-item retry stopped by operator. Completed images were preserved.",
                    )
                return
            item = self._item(current, item_id)
            if item is None or item.get("status") == "completed":
                continue
            original_operation_id = self._original_operation_id(item)
            original = operations.repository._one_unscoped(original_operation_id)
            request = dict((original.metadata if original else {}).get("request") or {})
            if not request:
                self._settle_item(
                    current, operations, item_id=item_id, child=None, status="failed",
                    error="The original provider-ready request is unavailable for this failed item.",
                )
                continue

            idempotency_key = f"explicit-failed-retry:{operation.operation_id}:{cycle_id}:{item_id}"
            child = operations.repository.latest_by_idempotency(
                creator_profile_id=operation.creator_profile_id, idempotency_key=idempotency_key,
            )
            if child is None:
                child, _ = operations.create(
                    operation_type="content_studio_generation",
                    originating_workspace="content_studio",
                    creator_profile_id=operation.creator_profile_id,
                    account_id=operation.account_id,
                    subject_type="explicit_batch_item",
                    subject_id=f"{operation.operation_id}:{item_id}",
                    idempotency_key=idempotency_key,
                    executor_key="content_studio_generation",
                    progress_total=1,
                    current_stage="QUEUED",
                    stage_message="Failed Explicit item queued for retry",
                    result_location="/studio/content",
                    cancellation_supported=False,
                    metadata={
                        "request": request, "provider": request.get("provider"),
                        "completedCount": 0, "failedCount": 0, "outputReferences": [],
                        "parentExplicitBatchOperationId": str(operation.operation_id),
                        "parentExplicitItemId": item_id, "retryCycleId": cycle_id,
                    },
                )
            self._mark_child(current, operations, item_id=item_id, child=child, status="generating")

            if child.status not in {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"}:
                if child.status == "QUEUED":
                    child = operations.repository.transition(
                        child.operation_id, "RUNNING", stage="PREPARING",
                        message="Retry generation preparing",
                    )
                elif child.result_reference:
                    recovered = child_executor.recover_submitted(
                        replace(child, attempt_count=max(2, child.attempt_count)), operations,
                    )
                    if recovered:
                        child = operations.repository._one_unscoped(child.operation_id)
                if child.status == "RUNNING":
                    child_executor.execute(child, operations, worker_id=worker_id)
                    child = operations.repository._one_unscoped(child.operation_id)

            succeeded = child.status == "SUCCEEDED" and bool(
                tuple((child.metadata or {}).get("outputReferences") or ())
            )
            self._settle_item(
                operations.repository._one_unscoped(operation.operation_id), operations,
                item_id=item_id, child=child,
                status="completed" if succeeded else "failed",
                error="" if succeeded else str(child.error_message or "Generation failed"),
            )

        current = operations.repository._one_unscoped(operation.operation_id)
        if current.status in {"CANCEL_REQUESTED", "CANCELLED"}:
            if current.status == "CANCEL_REQUESTED":
                operations.cancel(
                    current.operation_id,
                    "Failed-item retry stopped by operator. Completed images were preserved.",
                )
            return
        items = [dict(item) for item in current.metadata.get("items") or ()]
        completed = sum(item.get("status") == "completed" for item in items)
        failed = sum(item.get("status") == "failed" for item in items)
        metadata = {
            "items": items, "completedIdeas": completed, "failedIdeas": failed,
            "currentIdeaIndex": len(items), "phase": "complete",
            "retryCycle": {**cycle, "status": "COMPLETED"},
        }
        message = f"{completed} completed · {failed} failed"
        if failed:
            operations.succeed(
                current.operation_id, partial=True, message=message, metadata=metadata,
            )
        else:
            operations.complete_explicit_batch(
                current.operation_id, message=message, metadata=metadata,
            )

    @staticmethod
    def _item(operation, item_id: str):
        return next(
            (dict(item) for item in operation.metadata.get("items") or ()
             if str(item.get("id")) == item_id),
            None,
        )

    @staticmethod
    def _original_operation_id(item: dict) -> str:
        attempts = list(item.get("attempts") or ())
        if attempts:
            return str(attempts[0].get("operationId") or "")
        return str(item.get("jobId") or "")

    def _mark_child(self, operation, operations, *, item_id: str, child, status: str) -> None:
        self._update_parent_item(
            operation, operations, item_id=item_id,
            changes={"jobId": str(child.operation_id), "status": status, "error": ""},
            message=f"Retrying failed item {int(self._item(operation, item_id).get('ordinal') or 0) + 1}...",
        )

    def _settle_item(self, operation, operations, *, item_id: str, child, status: str, error: str) -> None:
        item = self._item(operation, item_id) or {}
        attempts = list(item.get("attempts") or ())
        outputs = tuple((child.metadata or {}).get("outputReferences") or ()) if child else ()
        attempts.append({
            "attemptNumber": len(attempts) + 1,
            "operationId": str(child.operation_id) if child else None,
            "generationJobId": child.result_reference if child else None,
            "status": status, "error": error or None,
            "failureStage": None if status == "completed" else "generation",
        })
        changes = {
            "attempts": attempts, "status": status, "error": error,
            "failureStage": None if status == "completed" else "generation",
        }
        if child:
            changes["jobId"] = str(child.operation_id)
        if outputs:
            changes["imageUrl"] = f"/api/v1/content-studio/generations/{child.operation_id}/images/0"
        self._update_parent_item(
            operation, operations, item_id=item_id, changes=changes,
            message="Retry item completed" if status == "completed" else "Retry item failed",
        )

    @staticmethod
    def _update_parent_item(operation, operations, *, item_id: str, changes: dict, message: str) -> None:
        items = [
            {**dict(item), **changes} if str(item.get("id")) == item_id else dict(item)
            for item in operation.metadata.get("items") or ()
        ]
        completed = sum(item.get("status") == "completed" for item in items)
        failed = sum(item.get("status") == "failed" for item in items)
        retrying = sum(item.get("status") in {"pending", "generating", "submitting"} for item in items)
        operations.repository.renew_lease(operation.operation_id, operation.worker_id or "", lease_seconds=120)
        operations.progress(
            operation.operation_id, current=completed, total=len(items),
            percent=completed / max(1, len(items)) * 100,
            stage="RETRYING_FAILED", message=message,
            metadata={
                "items": items, "completedIdeas": completed, "failedIdeas": failed,
                "retryingIdeas": retrying, "phase": "generating",
            },
        )
