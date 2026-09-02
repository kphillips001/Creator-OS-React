"""Durable trusted replay orchestration for Regeneration Studio backend."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid5

import requests

from app.models.generation_engine import (
    GenerationRequest, GenerationStatus, ProviderPromptState,
)
from app.models.regeneration import RegenerationEligibility
from app.providers.generation.base import ProviderSubmission
from app.repositories.generation_recipe_repository import GenerationRecipeRepository
from app.repositories.regeneration_repository import RegenerationRepository
from app.services.background_operation_service import BackgroundOperationService
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_library_service import GenerationLibraryService
from app.services.regeneration_eligibility_service import RegenerationEligibilityService


REGENERATION_NAMESPACE = UUID("126d9c31-9f83-4dda-a92c-157cb034d24c")


class RegenerationService:
    def __init__(self, *, eligibility=None, repository=None, recipes=None,
                 generation_engine=None, http_client=None, workspace_root=None):
        self.eligibility = eligibility or RegenerationEligibilityService()
        self.repository = repository or RegenerationRepository()
        self.recipes = recipes or GenerationRecipeRepository()
        self.engine = generation_engine or GenerationEngineService()
        self.http = http_client or requests
        self.workspace_root = Path(workspace_root or "data/regeneration_workspace")

    def start(self, *, source_generated_image_id: str, count: int,
              creator_profile_id: int, account_id: int | None,
              operations=None):
        if type(count) is not int or not 1 <= count <= 5:
            raise ValueError("Regeneration count must be an integer from 1 to 5.")
        eligibility = self.eligibility.inspect(
            source_generated_image_id, creator_profile_id=creator_profile_id,
        )
        if not eligibility.can_regenerate:
            raise RegenerationIneligible(eligibility)
        operations = operations or BackgroundOperationService()
        operation, created = operations.create(
            operation_type="regeneration",
            originating_workspace="regeneration_studio",
            creator_profile_id=int(creator_profile_id), account_id=account_id,
            subject_type="generated_image", subject_id=source_generated_image_id,
            idempotency_key=f"regeneration:{source_generated_image_id}:{count}",
            executor_key="regeneration", progress_total=count,
            current_stage="QUEUED", stage_message="Regeneration queued",
            result_location="/studio/regeneration", cancellation_supported=False,
            metadata={"sourceGeneratedImageId": source_generated_image_id,
                      "sourceRecipeId": str(eligibility.source_recipe_id),
                      "requestedCount": count, "completedCount": 0, "failedCount": 0},
        )
        self.repository.ensure_run(
            operation_id=operation.operation_id, creator_profile_id=creator_profile_id,
            source_generated_image_id=source_generated_image_id,
            source_recipe_id=eligibility.source_recipe_id, requested_count=count,
        )
        return operation, created

    def execute(self, operation, operations, *, worker_id: str):
        metadata = dict(operation.metadata or {})
        source_id = str(metadata.get("sourceGeneratedImageId") or operation.subject_id)
        count = int(metadata.get("requestedCount") or operation.progress_total)
        eligibility = self.eligibility.inspect(
            source_id, creator_profile_id=operation.creator_profile_id,
        )
        if not eligibility.can_regenerate:
            raise RegenerationIneligible(eligibility)
        source = self.eligibility.library.get(source_id)
        recipe = self.recipes.get(eligibility.source_recipe_id)
        resolved = self.eligibility.resolve_references(recipe, source.creator_profile_id)
        self.repository.ensure_run(
            operation_id=operation.operation_id, creator_profile_id=source.creator_profile_id,
            source_generated_image_id=source_id, source_recipe_id=recipe.recipe_id,
            requested_count=count,
        )
        self.repository.update_run_status(operation.operation_id, "RUNNING")
        for result in self.repository.results(operation.operation_id):
            if result.status in {"SUCCEEDED", "FAILED", "SUBMISSION_AMBIGUOUS"}:
                continue
            operations.repository.renew_lease(operation.operation_id, worker_id, lease_seconds=180)
            existing = self.repository.results(operation.operation_id)
            completed = sum(item.status == "SUCCEEDED" for item in existing)
            failed = sum(item.status in {"FAILED", "SUBMISSION_AMBIGUOUS"} for item in existing)
            operations.progress(
                operation.operation_id, current=completed + failed, total=count,
                percent=(completed + failed) / count * 100, stage="GENERATING",
                message=f"Generating variation {result.variation_index} of {count}",
                metadata={"completedCount": completed, "failedCount": failed,
                          "currentVariation": result.variation_index},
            )
            self.repository.start_result(operation.operation_id, result.variation_index)
            try:
                job = self._execute_variation(operation, result, source, recipe, resolved)
                self._persist_success(operation, result.variation_index, job)
            except Exception as error:
                current_recipe = self.recipes.get_by_request(
                    self._request_id(operation.operation_id, result.variation_index)
                )
                execution = self.recipes.get_execution(current_recipe.recipe_id) if current_recipe else None
                ambiguous = bool(execution and execution.status == "SUBMISSION_AMBIGUOUS")
                self.repository.fail_result(
                    operation.operation_id, result.variation_index, error,
                    code="SUBMISSION_AMBIGUOUS" if ambiguous else type(error).__name__,
                    recipe_id=current_recipe.recipe_id if current_recipe else None,
                    ambiguous=ambiguous,
                )
            self._progress(operation, operations)
        results = self.repository.results(operation.operation_id)
        succeeded = sum(item.status == "SUCCEEDED" for item in results)
        failed = len(results) - succeeded
        status = "SUCCEEDED" if succeeded == count else "PARTIAL" if succeeded else "FAILED"
        self.repository.update_run_status(operation.operation_id, status)
        summary = {"completedCount": succeeded, "failedCount": failed,
                   "requestedCount": count, "resultIds": [str(item.regeneration_result_id) for item in results]}
        if succeeded:
            operations.succeed(operation.operation_id, partial=failed > 0, metadata=summary,
                               message="Regeneration completed" if not failed else "Regeneration completed with partial success")
        else:
            operations.fail(operation.operation_id, "All regenerated variations failed.", metadata=summary)

    def _execute_variation(self, operation, result, source, recipe, resolved):
        request_id = self._request_id(operation.operation_id, result.variation_index)
        existing_recipe = self.recipes.get_by_request(request_id)
        if result.generation_job_id:
            job = self.engine.get_job(result.generation_job_id)
            if job.status == GenerationStatus.SUCCEEDED.value and job.result:
                return job
            if existing_recipe:
                return self._recover_submitted(job, existing_recipe)
        request = self._build_request(operation, result.variation_index, source, recipe, resolved)
        job = self.engine.enqueue(request, max_retries=0)
        self.repository.set_result_job(operation.operation_id, result.variation_index, job.job_id)
        executed = self.engine.dispatch_job(job.job_id)
        if executed.status != GenerationStatus.SUCCEEDED.value or not executed.result or not executed.result.output_references:
            raise RuntimeError(executed.failure.reason if executed.failure else "Regenerated variation failed.")
        return executed

    def _recover_submitted(self, job, recipe):
        execution = self.recipes.get_execution(recipe.recipe_id)
        if execution is None:
            raise RuntimeError("Regeneration recipe execution state is missing.")
        if execution.status not in {"SUBMITTED", "WAITING_PROVIDER", "SUCCEEDED"} or not execution.provider_request_id:
            raise RuntimeError("Provider state is uncertain; automatic resubmission was blocked.")
        provider = self.engine.provider_registry.require(recipe.provider_id)
        submission = ProviderSubmission(
            provider_request_id=execution.provider_request_id, raw_response={},
            generation_recipe_id=str(recipe.recipe_id),
        )
        poll = provider.poll_status(submission)
        if poll.status != GenerationStatus.SUCCEEDED.value:
            provider.recipe_capture.terminal(recipe.recipe_id, poll.status, error_message=poll.failure_reason)
            raise RuntimeError(poll.failure_reason or "Recovered provider generation failed.")
        provider.recipe_capture.terminal(recipe.recipe_id, "succeeded")
        generation_result = provider.retrieve_result(job.request, submission, poll)
        generation_result = replace(generation_result, generation_metadata={
            **dict(generation_result.generation_metadata or {}),
            "generation_recipe_ids": (str(recipe.recipe_id),),
            "output_generation_recipe_ids": (str(recipe.recipe_id),),
        })
        return self.engine.complete_job(job.job_id, generation_result)

    def _build_request(self, operation, index, source, recipe, resolved):
        first, *rest = resolved
        first_ref, first_path = first
        seed = next(((ref, path) for ref, path in rest if ref.role == "ORIGINAL_PHOTOSHOOT_SEED"), None)
        previous = next(((ref, path) for ref, path in rest if ref.role in {"PREVIOUS_APPROVED_CONTINUITY", "PHOTOSHOOT_CONTINUITY"}), None)
        metadata = {
            "source": "REGENERATION_STUDIO", "workflow_type": "REGENERATION_STUDIO",
            "workflow_origin": "regeneration", "creative_mode": recipe.creative_mode,
            "render_policy": recipe.render_policy,
            "render_policy_version": recipe.render_policy_version,
            "output_format": recipe.output_format or dict(recipe.normalized_settings).get("output_format") or "png",
            "source_generated_image_id": source.image_id,
            "source_recipe_id": str(recipe.recipe_id),
            "regeneration_operation_id": str(operation.operation_id),
            "regeneration_variation_index": index,
            "trusted_final_prompt_sha256": recipe.final_prompt_sha256,
            "original_seed_policy": recipe.seed_policy,
            "regeneration_seed_policy": "OMITTED_PROVIDER_RANDOM",
            "canonical_reference_image_url": first_path,
        }
        if seed:
            metadata.update({
                "original_photoshoot_seed_reference_image_url": seed[1],
                "original_photoshoot_seed_image_id": seed[0].generated_image_id,
            })
        continuity = previous or seed or (rest[0] if rest else None)
        if continuity:
            metadata.update({"photoshoot_continuity_reference_image_url": continuity[1],
                             "previous_approved_continuity_reference_image_url": continuity[1],
                             "active_reference_image_id": continuity[0].generated_image_id,
                             "previous_approved_continuity_reference_image_id": continuity[0].generated_image_id,
                             "require_frozen_photoshoot_identity": True})
        return GenerationRequest(
            request_id=self._request_id(operation.operation_id, index),
            creator_profile_id=source.creator_profile_id,
            prompt_plan_id=recipe.prompt_plan_id or str(recipe.recipe_id),
            prompt_text=recipe.final_prompt,
            prompt_state=ProviderPromptState.FINAL_PROVIDER_RENDERED.value,
            reference_asset_id=first_ref.asset_id,
            reference_asset_path=first_path,
            provider_id=recipe.provider_id,
            generation_type=recipe.generation_type,
            media_type=recipe.media_type,
            image_count=1,
            metadata=metadata,
        )

    def _persist_success(self, operation, index, job):
        result = job.result
        recipe_ids = tuple(result.generation_metadata.get("output_generation_recipe_ids") or ())
        if len(recipe_ids) != 1:
            raise RuntimeError("Regenerated output did not retain exactly one Generation Recipe.")
        recipe_id = recipe_ids[0]
        media_path = self._materialize(operation.operation_id, index, result.output_references[0])
        image_id = f"regenerated_image_{uuid5(REGENERATION_NAMESPACE, f'{operation.operation_id}:{index}').hex}"
        from app.services.generation_recipe_capture_service import GenerationRecipeCaptureService
        GenerationRecipeCaptureService(self.recipes).associate_output(
            recipe_id, result_id=result.result_id, image_id=image_id,
            output_index=0, output_reference=media_path,
        )
        self.repository.succeed_result(
            operation.operation_id, index, generation_job_id=job.job_id,
            generation_result_id=result.result_id, generated_image_id=image_id,
            generation_recipe_id=recipe_id, media_path=media_path,
        )

    def promote(self, operation_id, result_ids, *, creator_profile_id: int, account_id: int,
                operations=None, generation_library=None):
        operations = operations or BackgroundOperationService()
        operation = operations.get(operation_id, creator_profile_id=creator_profile_id, account_id=account_id)
        run = self.repository.get_run(operation_id, creator_profile_id=creator_profile_id)
        if operation is None or run is None:
            raise KeyError("Regeneration operation not found.")
        requested = tuple(dict.fromkeys(str(value) for value in result_ids))
        if not requested:
            raise ValueError("Select at least one regeneration result.")
        rows = {str(item.regeneration_result_id): item for item in self.repository.results(operation_id)}
        if any(value not in rows for value in requested):
            raise ValueError("A selected result does not belong to this regeneration operation.")
        library = generation_library or GenerationLibraryService()
        promoted = []
        for result_id in requested:
            item = rows[result_id]
            if item.status != "SUCCEEDED":
                raise ValueError("Only successful regeneration results can be promoted.")
            if item.disposition not in {"PENDING_REVIEW", "ARCHIVED", "PROMOTED"}:
                raise ValueError("Regeneration result is not pending review.")
            if not item.media_path or not Path(item.media_path).expanduser().is_file():
                raise ValueError("Regenerated media is unavailable.")
            if not item.generation_recipe_id:
                raise ValueError("Regeneration result has no Generation Recipe linkage.")
            recipe = self.recipes.get(item.generation_recipe_id)
            execution = self.recipes.get_execution(item.generation_recipe_id)
            if recipe is None or execution is None or execution.status != "SUCCEEDED":
                raise ValueError("Regeneration recipe execution is incomplete.")
            job = self.engine.get_job(item.generation_job_id)
            if job is None or job.result is None:
                raise ValueError("Regeneration Generation Engine result is unavailable.")
            record, _ = library.promote_regeneration_result(
                job=job, media_path=item.media_path,
                generated_image_id=item.generated_image_id,
                generation_recipe_id=str(item.generation_recipe_id),
            )
            self.repository.promote_result(operation_id, result_id)
            promoted.append(record)
        return tuple(promoted)

    def finalize_selection(self, operation_id, result_ids, *, creator_profile_id: int,
                           account_id: int, operations=None, generation_library=None):
        """Promote the selection, archive successful unselected results, and dismiss review."""
        operations = operations or BackgroundOperationService()
        _, _, rows, requested = self._owned_results(
            operation_id, result_ids, creator_profile_id, account_id, operations,
        )
        selected = set(requested)
        for result_id in requested:
            item = rows[result_id]
            if item.status != "SUCCEEDED":
                raise ValueError("Only successful regeneration results can be promoted.")
            if item.disposition not in {"PENDING_REVIEW", "ARCHIVED", "PROMOTED"}:
                raise ValueError("Regeneration result is not pending review.")

        to_promote = [result_id for result_id in requested
                      if rows[result_id].disposition != "PROMOTED"]
        promoted = self.promote(
            operation_id, to_promote, creator_profile_id=creator_profile_id,
            account_id=account_id, operations=operations,
            generation_library=generation_library,
        ) if to_promote else ()

        refreshed = self.repository.results(operation_id)
        to_archive = [str(item.regeneration_result_id) for item in refreshed
                      if str(item.regeneration_result_id) not in selected
                      and item.status == "SUCCEEDED"
                      and item.disposition == "PENDING_REVIEW"]
        archived = self.archive(
            operation_id, to_archive, creator_profile_id=creator_profile_id,
            account_id=account_id, operations=operations,
        ) if to_archive else ()
        run = self.repository.dismiss_workspace(
            operation_id, creator_profile_id=creator_profile_id,
        )
        return tuple(promoted), tuple(archived), run

    def archive(self, operation_id, result_ids, *, creator_profile_id: int, account_id: int,
                operations=None):
        operation, run, rows, requested = self._owned_results(
            operation_id, result_ids, creator_profile_id, account_id, operations,
        )
        archived = []
        for result_id in requested:
            item = rows[result_id]
            if item.status != "SUCCEEDED":
                raise ValueError("Only successful regeneration results can be archived.")
            if item.disposition == "PROMOTED":
                raise ValueError("Promoted regeneration results cannot be archived.")
            if item.disposition not in {"PENDING_REVIEW", "ARCHIVED"}:
                raise ValueError("Regeneration result cannot be archived from its current state.")
            if not item.media_path or not Path(item.media_path).expanduser().is_file():
                raise ValueError("Regenerated media is unavailable.")
            if not item.generation_recipe_id or self.recipes.get(item.generation_recipe_id) is None:
                raise ValueError("Regeneration result has no Generation Recipe linkage.")
            archived.append(self.repository.archive_result(operation_id, result_id))
        return tuple(archived)

    def restore(self, operation_id, result_id, *, creator_profile_id: int, account_id: int,
                operations=None):
        _, _, rows, _ = self._owned_results(
            operation_id, [result_id], creator_profile_id, account_id, operations,
        )
        item = rows[str(result_id)]
        if item.status != "SUCCEEDED" or item.disposition not in {"ARCHIVED", "PENDING_REVIEW"}:
            raise ValueError("Only archived successful results can be restored.")
        if not item.media_path or not Path(item.media_path).expanduser().is_file():
            raise ValueError("Regenerated media is unavailable.")
        return self.repository.restore_result(operation_id, result_id)

    def _owned_results(self, operation_id, result_ids, creator_profile_id, account_id, operations=None):
        operations = operations or BackgroundOperationService()
        operation = operations.get(operation_id, creator_profile_id=creator_profile_id, account_id=account_id)
        run = self.repository.get_run(operation_id, creator_profile_id=creator_profile_id)
        if operation is None or run is None:
            raise KeyError("Regeneration operation not found.")
        requested = tuple(dict.fromkeys(str(value) for value in result_ids))
        if not requested:
            raise ValueError("Select at least one regeneration result.")
        rows = {str(item.regeneration_result_id): item for item in self.repository.results(operation_id)}
        if any(value not in rows for value in requested):
            raise ValueError("A selected result does not belong to this regeneration operation.")
        return operation, run, rows, requested

    def _materialize(self, operation_id, index, reference):
        parsed = urlparse(str(reference))
        suffix = Path(parsed.path if parsed.scheme else str(reference)).suffix or ".png"
        destination = self.workspace_root / str(operation_id) / f"variation_{index}{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if parsed.scheme in {"http", "https"}:
            response = self.http.get(reference, timeout=120, headers={"User-Agent": "Creator-OS"})
            response.raise_for_status(); destination.write_bytes(response.content)
        else:
            source = Path(reference)
            if not source.is_file(): raise FileNotFoundError("Regenerated provider output was not found.")
            destination.write_bytes(source.read_bytes())
        return str(destination)

    def _progress(self, operation, operations):
        results = self.repository.results(operation.operation_id)
        completed = sum(item.status == "SUCCEEDED" for item in results)
        failed = sum(item.status in {"FAILED", "SUBMISSION_AMBIGUOUS"} for item in results)
        processed = completed + failed
        operations.progress(
            operation.operation_id, current=processed, total=len(results),
            percent=processed / max(1, len(results)) * 100, stage="GENERATING",
            message=f"Processed variation {processed} of {len(results)}",
            metadata={"completedCount": completed, "failedCount": failed,
                      "currentVariation": min(processed + 1, len(results))},
        )

    @staticmethod
    def _request_id(operation_id, index):
        return f"regeneration_request_{str(operation_id).replace('-', '')}_{int(index)}"


class RegenerationIneligible(ValueError):
    def __init__(self, eligibility: RegenerationEligibility):
        self.eligibility = eligibility
        super().__init__(eligibility.reason or "Generation is not eligible for regeneration.")
