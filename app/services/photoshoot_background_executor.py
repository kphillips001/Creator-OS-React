"""Background Operations adapter for operator-driven Photoshoot generation."""
from __future__ import annotations

from typing import Any


class PhotoshootBackgroundExecutor:
    executor_key = "photoshoot_generation"

    def execute(self, operation, operations, *, worker_id: str) -> None:
        from app.models.generation_engine import GenerationStatus
        from app.services.generation_engine_service import GenerationEngineService
        from app.services.photoshoot_manual_service import PhotoshootManualService

        metadata = dict(operation.metadata or {})
        session_id = str(metadata.get("photoshootSessionId") or operation.subject_id)
        request_id = str(metadata.get("requestId") or "")
        job_id = str(metadata.get("generationJobId") or operation.result_reference or "")
        manual = PhotoshootManualService()
        manual.session_for_creator(session_id, operation.creator_profile_id)
        request = manual.queue.get_request(request_id)
        if request.session_id != session_id or str(request.generation_job_id or "") != job_id:
            raise ValueError("Persisted Photoshoot request does not match this operation.")
        job = GenerationEngineService().get_job(job_id)
        if job is None:
            raise KeyError("Persisted Generation Engine job was not found.")

        # A reclaimed operation that crossed provider dispatch must never blindly
        # submit the same paid provider work for a second time.
        if operation.attempt_count > 1 and operation.result_reference:
            if job.status == GenerationStatus.SUCCEEDED.value and job.result:
                records = manual.library.sync_job(job)
                completed = manual.synchronize_completed(session_id=session_id, job=job, records=records)
                result = {"status": "succeeded", "job_id": job.job_id,
                          "request_id": completed.request_id if completed else request_id,
                          "image_ids": [record.image_id for record in records]}
                self._finish(operation, operations, result)
                return
            if job.status != GenerationStatus.QUEUED.value:
                operations.fail(
                    operation.operation_id,
                    "Provider job state is uncertain after worker restart; automatic resubmission was blocked.",
                    code="PROVIDER_STATE_UNCERTAIN",
                    metadata={"providerJobId": job_id},
                )
                return

        operations.progress(
            operation.operation_id, current=0, total=1, percent=5,
            stage="RESOLVING_CONTINUITY", message="Resolving identity and continuity",
            result_reference=job_id,
        )

        def observe(**state: Any) -> None:
            status = str(state.get("status") or "running").lower()
            stage = {"queued": "PROVIDER_QUEUED", "running": "GENERATING", "planning": "PLANNING"}.get(
                status, status.upper())
            operations.repository.renew_lease(operation.operation_id, worker_id, lease_seconds=120)
            operations.progress(
                operation.operation_id,
                current=int(state.get("current") or 0),
                total=max(1, int(state.get("total") or 1)),
                percent=float(state.get("percent") or state.get("progress") or 35), stage=stage,
                message=str(state.get("message") or "Generating Photoshoot image"),
                result_reference=str(state.get("jobId") or job_id),
                metadata={key: value for key, value in state.items() if key not in {"status", "message", "progress"}},
            )

        result = manual.execute(session_id=session_id, job=job, progress_callback=observe)
        self._finish(operation, operations, result)

    @staticmethod
    def _finish(operation, operations, result: dict) -> None:
        if result.get("status") == "succeeded":
            operations.progress(
                operation.operation_id, current=1, total=1, percent=100,
                stage="READY_FOR_REVIEW", message="Ready for review",
                result_reference=result.get("job_id"), metadata={"imageIds": result.get("image_ids", [])},
            )
            operations.succeed(
                operation.operation_id, result_reference=result.get("job_id"),
                metadata={"requestId": result.get("request_id"), "imageIds": result.get("image_ids", [])},
                message="Photoshoot image is ready for review",
            )
            return
        operations.fail(
            operation.operation_id, str(result.get("message") or "Photoshoot generation failed"),
            metadata={"providerJobId": result.get("job_id")},
        )
