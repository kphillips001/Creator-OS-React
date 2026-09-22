"""Provider-neutral Generation Engine service.

The engine owns requests, queue state, lifecycle, and provider dispatch.
Provider adapters remain swappable and are not called by Content Studio.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping

from app.models.creative_director import PromptPlan
from app.models.canonical_creator_identity import CanonicalCreatorIdentityContract
from app.models.generation_engine import (
    GenerationFailure,
    GenerationJob,
    GenerationMediaType,
    GenerationProgress,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    GenerationType,
    ProviderPromptState,
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


class GenerationJobStoreError(RuntimeError):
    """The durable Generation Engine job store could not be read or published."""


class GenerationJobStoreLockTimeout(GenerationJobStoreError):
    """Another process held the Generation Engine mutation lock too long."""


class GenerationEngineService:
    """Owns provider-neutral generation execution state and queue behavior."""

    DEFAULT_STORAGE_DIR = Path("data") / "generation_engine"
    _dispatch_locks_guard = threading.Lock()
    _dispatch_locks: dict[str, threading.Lock] = {}
    STORE_READ_ATTEMPTS = 3
    STORE_READ_RETRY_SECONDS = 0.025
    STORE_LOCK_TIMEOUT_SECONDS = 30.0
    STORE_LOCK_RETRY_SECONDS = 0.025

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
        canonical_identity: CanonicalCreatorIdentityContract | None = None,
    ) -> GenerationRequest:
        creator_profile_id = int((creator_profile or {}).get("id") or prompt_plan.creator_profile_id)
        request_metadata = dict(metadata or {})
        frozen_identity_path = str(request_metadata.get("canonical_identity_reference_path") or "").strip()
        frozen_identity_asset_id = int(request_metadata.get("canonical_identity_reference_asset_id") or 0)
        frozen_identity_required = bool(request_metadata.get("require_frozen_photoshoot_identity"))
        if frozen_identity_required and (not frozen_identity_path or not frozen_identity_asset_id):
            raise ValueError("The frozen canonical identity reference is unavailable for this Photoshoot.")
        if canonical_identity is not None and canonical_identity.creator_profile_id != creator_profile_id:
            raise ValueError("The frozen canonical identity belongs to a different creator.")
        active_reference = None if (frozen_identity_required or canonical_identity is not None) else self.reference_library.get_active_canonical_reference(
            creator_profile_id=creator_profile_id,
        )
        reference_asset_id = (
            frozen_identity_asset_id if frozen_identity_required else canonical_identity.canonical_asset_id
            if canonical_identity is not None else active_reference.asset_id
            if active_reference
            else prompt_plan.reference_asset_id
        )
        reference_asset_path = (
            frozen_identity_path if frozen_identity_required else canonical_identity.canonical_local_path
            if canonical_identity is not None else active_reference.asset.original_path
            if active_reference
            else prompt_plan.reference_asset_path
        )
        reference_metadata = dict(active_reference.metadata or {}) if active_reference else {}
        provider_reference_url = canonical_identity.canonical_provider_reference if canonical_identity is not None else None
        if (
            active_reference and reference_asset_id
            and reference_asset_path and str(provider_id) == "seedream_5_0_pro"
        ):
            resolver = self.hosted_references or HostedAssetReferenceService()
            provider_reference_url = resolver.cached_url(
                asset_id=int(reference_asset_id), source_path=str(reference_asset_path), host_name="wavespeed_media",
            )
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
        generation_request = GenerationRequest(
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
            canonical_identity=canonical_identity,
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
                    if (active_reference or canonical_identity) and (provider_reference_url or reference_asset_path)
                    else {}
                ),
                **({"reference_image_url": provider_reference_url} if provider_reference_url else {}),
                **request_metadata,
            },
        )
        from app.services.generation_request_diagnostic_service import GenerationRequestDiagnosticService
        diagnostic = GenerationRequestDiagnosticService()
        diagnostic.record(
            trace_id=request_metadata.get("diagnostic_trace_id"),
            workflow_origin=request_metadata.get("workflow_origin"),
            stage="9_generation_request_fields_and_metadata",
            value=generation_request,
        )
        diagnostic.record(
            trace_id=request_metadata.get("diagnostic_trace_id"),
            workflow_origin=request_metadata.get("workflow_origin"),
            stage="10_render_policy",
            value=generation_request.metadata.get("render_policy"),
        )
        return generation_request

    def enqueue(
        self,
        request: GenerationRequest,
        *,
        max_retries: int = 0,
    ) -> GenerationJob:
        job_id = new_generation_id("generation_job")
        request = replace(
            request,
            metadata={**dict(request.metadata or {}), "generation_job_id": job_id},
        )
        job = GenerationJob(
            job_id=job_id,
            request=request,
            max_retries=max(0, int(max_retries or 0)),
        )
        self._mutate_jobs(lambda jobs: [*jobs, job])
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
        canonical_identity: CanonicalCreatorIdentityContract | None = None,
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
            canonical_identity=canonical_identity,
        )
        return self.enqueue(request, max_retries=max_retries)

    def start_job(self, job_id: str) -> GenerationJob:
        return self._mutate_job(job_id, lambda job: job if job.status in {
            GenerationStatus.SUCCEEDED.value,
            GenerationStatus.CANCELLED.value,
        } else replace(
            job,
            status=GenerationStatus.RUNNING.value,
            started_at=job.started_at or utc_now(),
            updated_at=utc_now(),
            progress=GenerationProgress(current=0, total=job.request.image_count, percent=0, message="Running"),
        ))

    def complete_job(
        self,
        job_id: str,
        result: GenerationResult | None = None,
    ) -> GenerationJob:
        completed_at = utc_now()
        def complete(job):
            if job.status == GenerationStatus.CANCELLED.value:
                return job
            completed_result = result or GenerationResult(
                result_id=new_generation_id("generation_result"),
                request_id=job.request.request_id,
                job_id=job.job_id,
                provider_id=job.request.provider_id,
                status=GenerationStatus.SUCCEEDED.value,
                generation_metadata={"provider_neutral_result": True},
            )
            return replace(
                job, status=GenerationStatus.SUCCEEDED.value,
                completed_at=completed_at, updated_at=completed_at,
                result=completed_result, failure=None,
                progress=GenerationProgress(
                    current=job.request.image_count, total=job.request.image_count,
                    percent=100.0, message="Succeeded"),
            )
        return self._mutate_job(job_id, complete)

    def fail_job(self, job_id: str, failure: GenerationFailure) -> GenerationJob:
        def fail(job):
            if job.status == GenerationStatus.CANCELLED.value:
                return job
            can_retry = failure.retryable and job.retry_count < job.max_retries
            return replace(
                job,
                status=(GenerationStatus.RETRY.value if can_retry else GenerationStatus.FAILED.value),
                retry_count=job.retry_count + 1 if can_retry else job.retry_count,
                completed_at=None if can_retry else utc_now(), updated_at=utc_now(),
                failure=failure,
                progress=replace(job.progress, message="Retry queued" if can_retry else "Failed"),
            )
        return self._mutate_job(job_id, fail)

    def cancel_job(self, job_id: str) -> GenerationJob:
        with self._dispatch_lock(job_id):
            return self._mutate_job(job_id, lambda job: job if job.status == GenerationStatus.SUCCEEDED.value else replace(
                job, status=GenerationStatus.CANCELLED.value,
                completed_at=utc_now(), updated_at=utc_now(),
                progress=replace(job.progress, message="Cancelled"),
            ))

    def retry_job(self, job_id: str) -> GenerationJob:
        with self._dispatch_lock(job_id):
            return self._mutate_job(job_id, lambda job: job if job.status in {
                GenerationStatus.SUCCEEDED.value,
                GenerationStatus.CANCELLED.value,
            } else replace(
                job, status=GenerationStatus.RETRY.value, completed_at=None,
                updated_at=utc_now(), failure=None,
                progress=GenerationProgress(
                    current=0, total=job.request.image_count,
                    percent=0, message="Retry queued"),
            ))

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
        if result.status == GenerationStatus.RUNNING.value:
            waiting = replace(
                job, status=GenerationStatus.RUNNING.value, result=result, failure=None,
                completed_at=None, updated_at=utc_now(),
                progress=replace(job.progress, message="Waiting on provider"),
            )
            self._replace_job(waiting)
            return waiting
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
        jobs = self._list_jobs_unlocked()
        filtered = []
        for job in jobs:
            if creator_profile_id is not None and job.request.creator_profile_id != int(creator_profile_id):
                continue
            if status is not None and job.status != str(status):
                continue
            filtered.append(job)
        return tuple(filtered)

    def _replace_job(self, updated: GenerationJob) -> None:
        self._mutate_jobs(lambda jobs: [
            updated if job.job_id == updated.job_id else job for job in jobs
        ] if any(job.job_id == updated.job_id for job in jobs) else [*jobs, updated])

    def _write_jobs(self, jobs: list[GenerationJob]) -> None:
        with self._job_store_lock():
            self._write_jobs_unlocked(jobs)

    def _write_jobs_unlocked(self, jobs) -> None:
        self._write_json_atomic(self.jobs_path, [asdict(job) for job in jobs])

    def _mutate_jobs(self, mutation):
        with self._job_store_lock():
            jobs = list(self._list_jobs_unlocked())
            updated = list(mutation(jobs))
            self._write_jobs_unlocked(updated)
            return updated

    def _mutate_job(self, job_id: str, mutation) -> GenerationJob:
        selected = None
        def update(jobs):
            nonlocal selected
            if not any(job.job_id == job_id for job in jobs):
                raise KeyError(f"Generation Job not found: {job_id}")
            result = []
            for job in jobs:
                if job.job_id == job_id:
                    selected = mutation(job)
                    result.append(selected)
                else:
                    result.append(job)
            return result
        self._mutate_jobs(update)
        return selected

    def _list_jobs_unlocked(self) -> tuple[GenerationJob, ...]:
        return tuple(self._job_from_dict(item) for item in self._read_json(self.jobs_path, []))

    @contextmanager
    def _job_store_lock(self):
        """Bounded OS-level lock covering the complete read/modify/publish transaction."""
        path = self.jobs_path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_name(f".{path.name}.lock")
        deadline = time.monotonic() + self.STORE_LOCK_TIMEOUT_SECONDS
        with open(lock_path, "a+b") as lock_file:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"0"); lock_file.flush()
            acquired = False
            while not acquired:
                lock_file.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except (OSError, BlockingIOError):
                    if time.monotonic() >= deadline:
                        raise GenerationJobStoreLockTimeout(
                            f"Timed out acquiring Generation Job store lock: {lock_path}")
                    time.sleep(self.STORE_LOCK_RETRY_SECONDS)
            try:
                yield
            finally:
                lock_file.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

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
    def _normalize_prompt_state(value: Any) -> str:
        candidate = str(value or ProviderPromptState.PLANNED.value).strip().upper()
        allowed = {item.value for item in ProviderPromptState}
        return candidate if candidate in allowed else ProviderPromptState.PLANNED.value

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
                prompt_state=cls._normalize_prompt_state(request_data.get("prompt_state")),
                canonical_identity=CanonicalCreatorIdentityContract.from_dict(
                    request_data.get("canonical_identity")
                    or (request_data.get("metadata") or {}).get("canonical_identity_contract")
                ),
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

    @classmethod
    def _read_json(cls, path: Path, default):
        if not path.exists():
            return default
        last_error = None
        for attempt in range(cls.STORE_READ_ATTEMPTS):
            try:
                with open(path, "r", encoding="utf-8") as file:
                    return json.load(file)
            except (OSError, json.JSONDecodeError) as error:
                last_error = error
                if attempt + 1 < cls.STORE_READ_ATTEMPTS:
                    time.sleep(cls.STORE_READ_RETRY_SECONDS)
        raise GenerationJobStoreError(
            f"Generation Job store is unreadable: {path}: "
            f"{type(last_error).__name__}: {last_error}"
        ) from last_error

    @staticmethod
    def _write_json_atomic(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.{os.getpid()}.", suffix=".tmp",
                delete=False,
            ) as output:
                temporary_path = Path(output.name)
                json.dump(data, output, indent=2, default=str)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
