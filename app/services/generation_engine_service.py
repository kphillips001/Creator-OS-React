"""Provider-neutral Generation Engine service.

The engine owns requests, queue state, lifecycle, and provider dispatch.
Provider adapters remain swappable and are not called by Content Studio.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping

from app.models.creative_director import PromptPlan
from app.models.generation_engine import (
    GenerationFailure,
    GenerationJob,
    GenerationMediaType,
    GenerationProgress,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    GenerationType,
    new_generation_id,
    utc_now,
)
from app.providers.generation.provider_registry import ProviderRegistry, create_default_registry
from app.services.reference_library_service import ReferenceLibraryService
from app.services.hosted_asset_reference_service import HostedAssetReferenceService
from app.models.render_policy import (
    RenderPolicy,
    content_render_policy,
    photoshoot_render_policy,
)


class GenerationEngineService:
    """Owns provider-neutral generation execution state and queue behavior."""

    DEFAULT_STORAGE_DIR = Path("data") / "generation_engine"
    _dispatch_locks_guard = threading.Lock()
    _dispatch_locks: dict[str, threading.Lock] = {}

    def __init__(
        self,
        *,
        storage_dir: str | Path | None = None,
        reference_library_service: ReferenceLibraryService | None = None,
        provider_registry: ProviderRegistry | None = None,
        providers: Mapping[str, Any] | None = None,
        hosted_reference_service: HostedAssetReferenceService | None = None,
    ):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)
        self.reference_library = reference_library_service or ReferenceLibraryService()
        self.hosted_references = hosted_reference_service
        if provider_registry is not None:
            self.provider_registry = provider_registry
        elif providers is not None:
            self.provider_registry = ProviderRegistry(providers)
        else:
            self.provider_registry = create_default_registry()

    @property
    def jobs_path(self) -> Path:
        return self.storage_dir / "generation_jobs.json"

    def create_request(
        self,
        *,
        creator_profile: Mapping[str, Any],
        prompt_plan: PromptPlan,
        provider_id: str = "seedream_5_0_pro",
        generation_type: str = GenerationType.IMAGE_TO_IMAGE.value,
        media_type: str = GenerationMediaType.IMAGE.value,
        image_count: int = 1,
        metadata: Mapping[str, Any] | None = None,
    ) -> GenerationRequest:
        creator_profile_id = int((creator_profile or {}).get("id") or prompt_plan.creator_profile_id)
        active_reference = self.reference_library.get_active_canonical_reference(
            creator_profile_id=creator_profile_id,
        )
        reference_asset_id = (
            active_reference.asset_id
            if active_reference
            else prompt_plan.reference_asset_id
        )
        reference_asset_path = (
            active_reference.asset.original_path
            if active_reference
            else prompt_plan.reference_asset_path
        )
        reference_metadata = dict(active_reference.metadata or {}) if active_reference else {}
        provider_reference_url = self._provider_reference_url_from_metadata(reference_metadata)
        if (
            not provider_reference_url and active_reference and reference_asset_id
            and reference_asset_path and str(provider_id) == "seedream_5_0_pro"
        ):
            resolver = self.hosted_references or HostedAssetReferenceService()
            provider_reference_url = resolver.cached_url(
                asset_id=int(reference_asset_id), source_path=str(reference_asset_path), host_name="imgbb",
            )
        request_metadata = dict(metadata or {})
        if not request_metadata.get("render_policy"):
            workflow = str(
                request_metadata.get("workflow_type") or "content_studio"
            ).strip().lower()
            creative_mode = str(
                request_metadata.get("creative_mode")
                or prompt_plan.creative_mode
                or "standard"
            )
            if workflow in {"edit", "edit_studio"}:
                request_metadata["render_policy"] = RenderPolicy.EDIT.value
            elif workflow == "photoshoot":
                request_metadata["render_policy"] = (
                    photoshoot_render_policy(creative_mode).value
                )
            else:
                request_metadata["render_policy"] = (
                    content_render_policy(creative_mode).value
                )
        return GenerationRequest(
            request_id=new_generation_id("generation_request"),
            creator_profile_id=creator_profile_id,
            prompt_plan_id=prompt_plan.plan_id,
            prompt_text=prompt_plan.prompt_text,
            reference_asset_id=reference_asset_id,
            reference_asset_path=reference_asset_path,
            provider_id=str(provider_id or "seedream_5_0_pro"),
            generation_type=self._normalize_generation_type(generation_type),
            media_type=self._normalize_media_type(media_type),
            image_count=max(1, int(image_count or 1)),
            metadata={
                "owner": "Generation Engine",
                "provider_neutral": True,
                "prompt_plan_owner": "Creative Director",
                "creative_mode": prompt_plan.creative_mode,
                "creative_tags": tuple(prompt_plan.creative_tags),
                "prompt_metadata": dict(prompt_plan.prompt_metadata or {}),
                "reference_metadata": reference_metadata,
                "reference_file_name": active_reference.asset.file_name if active_reference else None,
                "reference_preview_path": active_reference.asset.preview_path if active_reference else None,
                **(
                    {"canonical_reference_image_url": provider_reference_url or reference_asset_path}
                    if active_reference and (provider_reference_url or reference_asset_path)
                    else {}
                ),
                **({"reference_image_url": provider_reference_url} if provider_reference_url else {}),
                **request_metadata,
            },
        )

    def enqueue(
        self,
        request: GenerationRequest,
        *,
        max_retries: int = 0,
    ) -> GenerationJob:
        job = GenerationJob(
            job_id=new_generation_id("generation_job"),
            request=request,
            max_retries=max(0, int(max_retries or 0)),
        )
        jobs = list(self.list_jobs())
        jobs.append(job)
        self._write_jobs(jobs)
        return job

    def queue_prompt_plan(
        self,
        *,
        creator_profile: Mapping[str, Any],
        prompt_plan: PromptPlan,
        provider_id: str = "seedream_5_0_pro",
        generation_type: str = GenerationType.IMAGE_TO_IMAGE.value,
        media_type: str = GenerationMediaType.IMAGE.value,
        image_count: int = 1,
        metadata: Mapping[str, Any] | None = None,
        max_retries: int = 0,
    ) -> GenerationJob:
        request = self.create_request(
            creator_profile=creator_profile,
            prompt_plan=prompt_plan,
            provider_id=provider_id,
            generation_type=generation_type,
            media_type=media_type,
            image_count=image_count,
            metadata=metadata,
        )
        return self.enqueue(request, max_retries=max_retries)

    def start_job(self, job_id: str) -> GenerationJob:
        job = self.get_job(job_id)
        if job.status in {
            GenerationStatus.SUCCEEDED.value,
            GenerationStatus.CANCELLED.value,
        }:
            return job
        updated = replace(
            job,
            status=GenerationStatus.RUNNING.value,
            started_at=job.started_at or utc_now(),
            updated_at=utc_now(),
            progress=GenerationProgress(current=0, total=job.request.image_count, percent=0, message="Running"),
        )
        self._replace_job(updated)
        return updated

    def complete_job(
        self,
        job_id: str,
        result: GenerationResult | None = None,
    ) -> GenerationJob:
        job = self.get_job(job_id)
        completed_at = utc_now()
        result = result or GenerationResult(
            result_id=new_generation_id("generation_result"),
            request_id=job.request.request_id,
            job_id=job.job_id,
            provider_id=job.request.provider_id,
            status=GenerationStatus.SUCCEEDED.value,
            generation_metadata={"provider_neutral_result": True},
        )
        updated = replace(
            job,
            status=GenerationStatus.SUCCEEDED.value,
            completed_at=completed_at,
            updated_at=completed_at,
            result=result,
            failure=None,
            progress=GenerationProgress(
                current=job.request.image_count,
                total=job.request.image_count,
                percent=100.0,
                message="Succeeded",
            ),
        )
        self._replace_job(updated)
        return updated

    def fail_job(self, job_id: str, failure: GenerationFailure) -> GenerationJob:
        job = self.get_job(job_id)
        can_retry = failure.retryable and job.retry_count < job.max_retries
        status = GenerationStatus.RETRY.value if can_retry else GenerationStatus.FAILED.value
        updated = replace(
            job,
            status=status,
            retry_count=job.retry_count + 1 if can_retry else job.retry_count,
            completed_at=None if can_retry else utc_now(),
            updated_at=utc_now(),
            failure=failure,
            progress=replace(job.progress, message="Retry queued" if can_retry else "Failed"),
        )
        self._replace_job(updated)
        return updated

    def cancel_job(self, job_id: str) -> GenerationJob:
        with self._dispatch_lock(job_id):
            job = self.get_job(job_id)
            if job.status == GenerationStatus.SUCCEEDED.value:
                return job
            updated = replace(
                job,
                status=GenerationStatus.CANCELLED.value,
                completed_at=utc_now(),
                updated_at=utc_now(),
                progress=replace(job.progress, message="Cancelled"),
            )
            self._replace_job(updated)
            return updated

    def retry_job(self, job_id: str) -> GenerationJob:
        with self._dispatch_lock(job_id):
            job = self.get_job(job_id)
            if job.status in {
                GenerationStatus.SUCCEEDED.value,
                GenerationStatus.CANCELLED.value,
            }:
                return job
            updated = replace(
                job,
                status=GenerationStatus.RETRY.value,
                completed_at=None,
                updated_at=utc_now(),
                failure=None,
                progress=GenerationProgress(
                    current=0,
                    total=job.request.image_count,
                    percent=0,
                    message="Retry queued",
                ),
            )
            self._replace_job(updated)
            return updated

    def dispatch_job(
        self,
        job_id: str,
        progress_callback: Callable[..., None] | None = None,
    ) -> GenerationJob:
        lock = self._dispatch_lock(job_id)
        with lock:
            current = self.get_job(job_id)
            if current.status in {
                GenerationStatus.SUCCEEDED.value,
                GenerationStatus.CANCELLED.value,
            }:
                return current
            return self._dispatch_locked(
                job_id, progress_callback=progress_callback
            )

    def _dispatch_locked(
        self, job_id: str,
        progress_callback: Callable[..., None] | None = None,
    ) -> GenerationJob:
        job = self.start_job(job_id)
        provider = self.provider_registry.get(job.request.provider_id)
        if provider is None:
            return self.fail_job(
                job_id,
                GenerationFailure(
                    reason=f"No Generation Provider registered for {job.request.provider_id}.",
                    retryable=False,
                ),
            )

        started = perf_counter()
        try:
            if hasattr(provider, "execute_with_progress"):
                result = provider.execute_with_progress(
                    job.request,
                    progress_callback=progress_callback,
                )
            else:
                if progress_callback:
                    progress_callback(
                        current=0,
                        total=job.request.image_count,
                        message="Provider is running",
                        output_references=(),
                    )
                result = self.provider_registry.dispatch(job.request)
        except Exception as exc:  # pragma: no cover - defensive adapter boundary
            return self.fail_job(
                job_id,
                GenerationFailure(
                    reason=str(exc), retryable=bool(getattr(exc, "retryable", True)),
                    provider_error=exc.__class__.__name__, stage=getattr(exc, "stage", None),
                    may_have_been_accepted=bool(getattr(exc, "may_have_been_accepted", False)),
                ),
            )

        duration = perf_counter() - started
        result = replace(
            result,
            job_id=job.job_id,
            request_id=job.request.request_id,
            provider_id=job.request.provider_id,
            duration_seconds=result.duration_seconds if result.duration_seconds is not None else duration,
        )
        if result.status == GenerationStatus.SUCCEEDED.value:
            return self.complete_job(job_id, result)
        retryable_failure = any(
            bool(item.get("provider_error"))
            for item in dict(result.execution_metadata or {}).get("failures", ())
            if isinstance(item, Mapping)
        )
        provider_failures = tuple(
            item for item in dict(result.execution_metadata or {}).get("failures", ())
            if isinstance(item, Mapping)
        )
        primary_failure = provider_failures[0] if provider_failures else {}
        return self.fail_job(
            job_id,
            GenerationFailure(
                reason=result.failure_reason or "Generation failed. No requested images completed.",
                retryable=retryable_failure,
                provider_error=primary_failure.get("provider_error"),
                stage=primary_failure.get("stage"),
                may_have_been_accepted=bool(primary_failure.get("may_have_been_accepted", False)),
            ),
        )

    @classmethod
    def _dispatch_lock(cls, job_id: str) -> threading.Lock:
        with cls._dispatch_locks_guard:
            return cls._dispatch_locks.setdefault(str(job_id), threading.Lock())

    def next_queued_job(self) -> GenerationJob | None:
        queued_statuses = {GenerationStatus.QUEUED.value, GenerationStatus.RETRY.value}
        for job in self.list_jobs():
            if job.status in queued_statuses:
                return job
        return None

    def latest_job_for_prompt_plan(
        self,
        *,
        prompt_plan_id: str,
        creator_profile_id: int | None = None,
    ) -> GenerationJob | None:
        for job in reversed(self.list_jobs()):
            if job.request.prompt_plan_id != prompt_plan_id:
                continue
            if creator_profile_id is not None and job.request.creator_profile_id != int(creator_profile_id):
                continue
            return job
        return None

    def get_job(self, job_id: str) -> GenerationJob:
        for job in self.list_jobs():
            if job.job_id == job_id:
                return job
        raise KeyError(f"Generation Job not found: {job_id}")

    def list_jobs(
        self,
        *,
        creator_profile_id: int | None = None,
        status: str | None = None,
    ) -> tuple[GenerationJob, ...]:
        jobs = tuple(self._job_from_dict(item) for item in self._read_json(self.jobs_path, []))
        filtered = []
        for job in jobs:
            if creator_profile_id is not None and job.request.creator_profile_id != int(creator_profile_id):
                continue
            if status is not None and job.status != str(status):
                continue
            filtered.append(job)
        return tuple(filtered)

    def _replace_job(self, updated: GenerationJob) -> None:
        jobs = []
        replaced = False
        for job in self.list_jobs():
            if job.job_id == updated.job_id:
                jobs.append(updated)
                replaced = True
            else:
                jobs.append(job)
        if not replaced:
            jobs.append(updated)
        self._write_jobs(jobs)

    def _write_jobs(self, jobs: list[GenerationJob]) -> None:
        self._write_json(self.jobs_path, [asdict(job) for job in jobs])

    @staticmethod
    def _normalize_generation_type(value: Any) -> str:
        candidate = str(value or GenerationType.IMAGE_TO_IMAGE.value).strip().lower()
        allowed = {item.value for item in GenerationType}
        return candidate if candidate in allowed else GenerationType.IMAGE_TO_IMAGE.value

    @staticmethod
    def _normalize_media_type(value: Any) -> str:
        candidate = str(value or GenerationMediaType.IMAGE.value).strip().lower()
        allowed = {item.value for item in GenerationMediaType}
        return candidate if candidate in allowed else GenerationMediaType.IMAGE.value

    @staticmethod
    def _provider_reference_url_from_metadata(metadata: Mapping[str, Any]) -> str | None:
        for key in (
            "reference_image_url",
            "reference_url",
            "provider_reference_url",
            "public_url",
            "image_url",
            "hosted_url",
        ):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @classmethod
    def _job_from_dict(cls, data: Mapping[str, Any]) -> GenerationJob:
        request_data = data.get("request") or {}
        result_data = data.get("result")
        failure_data = data.get("failure")
        progress_data = data.get("progress") or {}
        return GenerationJob(
            job_id=str(data.get("job_id")),
            request=GenerationRequest(
                request_id=str(request_data.get("request_id")),
                creator_profile_id=int(request_data.get("creator_profile_id")),
                prompt_plan_id=str(request_data.get("prompt_plan_id")),
                prompt_text=str(request_data.get("prompt_text") or ""),
                reference_asset_id=request_data.get("reference_asset_id"),
                reference_asset_path=request_data.get("reference_asset_path"),
                provider_id=str(request_data.get("provider_id") or "future_provider"),
                generation_type=cls._normalize_generation_type(request_data.get("generation_type")),
                media_type=cls._normalize_media_type(request_data.get("media_type")),
                image_count=max(1, int(request_data.get("image_count") or 1)),
                metadata=request_data.get("metadata") or {},
                created_at=request_data.get("created_at") or "",
            ),
            status=str(data.get("status") or GenerationStatus.QUEUED.value),
            progress=GenerationProgress(
                current=int(progress_data.get("current") or 0),
                total=max(1, int(progress_data.get("total") or 1)),
                percent=float(progress_data.get("percent") or 0),
                message=str(progress_data.get("message") or ""),
            ),
            retry_count=int(data.get("retry_count") or 0),
            max_retries=int(data.get("max_retries") or 0),
            queued_at=data.get("queued_at") or "",
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            updated_at=data.get("updated_at") or "",
            result=cls._result_from_dict(result_data),
            failure=cls._failure_from_dict(failure_data),
        )

    @staticmethod
    def _result_from_dict(data: Any) -> GenerationResult | None:
        if not isinstance(data, Mapping):
            return None
        return GenerationResult(
            result_id=str(data.get("result_id")),
            request_id=str(data.get("request_id")),
            job_id=str(data.get("job_id")),
            provider_id=str(data.get("provider_id")),
            status=str(data.get("status") or GenerationStatus.SUCCEEDED.value),
            generation_metadata=data.get("generation_metadata") or {},
            execution_metadata=data.get("execution_metadata") or {},
            image_metadata=data.get("image_metadata") or {},
            output_references=tuple(data.get("output_references") or ()),
            duration_seconds=data.get("duration_seconds"),
            failure_reason=data.get("failure_reason"),
            created_at=data.get("created_at") or "",
        )

    @staticmethod
    def _failure_from_dict(data: Any) -> GenerationFailure | None:
        if not isinstance(data, Mapping):
            return None
        return GenerationFailure(
            reason=str(data.get("reason") or ""),
            retryable=bool(data.get("retryable", True)),
            provider_error=data.get("provider_error"),
            stage=data.get("stage"),
            may_have_been_accepted=bool(data.get("may_have_been_accepted", False)),
            failed_at=data.get("failed_at") or "",
        )

    @staticmethod
    def _read_json(path: Path, default):
        try:
            if not path.exists():
                return default
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            return default

    @staticmethod
    def _write_json(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, default=str)
