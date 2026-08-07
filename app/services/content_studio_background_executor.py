"""Thin Background Operations adapter for normal Content Studio generation."""
from __future__ import annotations

from typing import Any


class ContentStudioBackgroundExecutor:
    executor_key = "content_studio_generation"

    def execute(self, operation, operations, *, worker_id: str) -> None:
        # Imported lazily to keep the generic worker free of Content Studio API models.
        from app.api.content_studio import GenerationSubmissionRequest, _execute_content_studio_generation

        request_data = dict(operation.metadata.get("request") or {})
        request = GenerationSubmissionRequest(**request_data)
        total = max(1, int(request.promptCount))

        if self.recover_submitted(operation, operations):
            return

        observe = self.operation_observer(
            operation, operations, worker_id=worker_id, total=total)

        result = _execute_content_studio_generation(
            str(operation.operation_id), request,
            state_callback=observe, account_id=operation.account_id,
        )
        self.finish(operation, operations, result)

    @staticmethod
    def recover_submitted(operation, operations) -> bool:
        """Settle known provider work without ever submitting it twice."""
        # A provider job reference means a prior worker crossed the dispatch
        # boundary. Never submit a second provider job after lease recovery.
        if operation.attempt_count > 1 and operation.result_reference:
            from app.services.generation_engine_service import GenerationEngineService
            from app.models.generation_engine import GenerationStatus

            job = GenerationEngineService().get_job(operation.result_reference)
            if job and job.status == GenerationStatus.SUCCEEDED.value and job.result:
                from app.services.generation_library_service import GenerationLibraryService
                records = GenerationLibraryService().sync_job(job)
                outputs = tuple(record.output_reference for record in records)
                if not outputs:
                    outputs = tuple(job.result.output_references)
                operations.succeed(
                    operation.operation_id,
                    result_reference=job.job_id,
                    metadata={"outputReferences": outputs, "completedCount": len(outputs),
                              "failedCount": max(0, operation.progress_total - len(outputs))},
                    partial=len(outputs) < operation.progress_total,
                    message="Recovered completed provider generation",
                )
                return True
            operations.fail(
                operation.operation_id,
                "Provider job state is uncertain after worker restart; automatic resubmission was blocked.",
                code="PROVIDER_STATE_UNCERTAIN",
                metadata={"providerJobId": operation.result_reference},
            )
            return True
        return False

    @staticmethod
    def operation_observer(operation, operations, *, worker_id: str, total: int):
        def observe(state: dict[str, Any]) -> None:
            status = str(state.get("status") or "running").lower()
            current = int(state.get("processedCount") or state.get("completedCount") or 0)
            metadata = {
                key: value for key, value in state.items()
                if key not in {"status", "message", "progress"}
            }
            stage = {
                "planning": "PLANNING",
                "queued": "PROVIDER_QUEUED",
                "running": "GENERATING",
            }.get(status, status.upper())
            operations.repository.renew_lease(operation.operation_id, worker_id, lease_seconds=120)
            operations.progress(
                operation.operation_id,
                current=current,
                total=total,
                percent=float(state.get("progress") or current / total * 100),
                stage=stage,
                message=str(state.get("message") or "Generation running"),
                result_reference=state.get("jobId"),
                metadata=metadata,
            )
        return observe

    @staticmethod
    def finish(operation, operations, result) -> None:
        metadata = {key: value for key, value in result.items() if key != "status"}
        status = str(result.get("status") or "failed").lower()
        if status == "succeeded":
            operations.succeed(operation.operation_id, metadata=metadata,
                               message=str(result.get("message") or "Generation completed"))
        elif status == "partial":
            operations.succeed(operation.operation_id, metadata=metadata, partial=True,
                               message=str(result.get("message") or "Generation partially completed"))
        else:
            operations.fail(operation.operation_id,
                            str(result.get("message") or "Generation failed"), metadata=metadata)
