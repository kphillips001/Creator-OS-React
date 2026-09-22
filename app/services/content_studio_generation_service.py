"""HTTP-safe Content Studio generation orchestration using existing domain services."""

from dataclasses import replace
import re
from typing import Callable

from app.models.creative_director import PromptPlan
from app.models.canonical_creator_identity import (
    CanonicalCreatorIdentityContract,
    GenerationReferenceRole,
)
from app.models.generation_engine import GenerationMediaType, GenerationResult, GenerationStatus, GenerationType
from app.models.render_policy import content_render_policy
from app.services.canonical_creator_identity_policy import (
    CANONICAL_IDENTITY_POLICY_ID,
    CANONICAL_IDENTITY_POLICY_VERSION,
)


def plan_with_prompt_batch(plan: PromptPlan, prompts: tuple[str, ...]) -> PromptPlan:
    clean = tuple(str(prompt).strip() for prompt in prompts if str(prompt).strip())
    if not clean:
        return plan
    return replace(
        plan,
        prompt_text="\n\n".join(clean),
        prompt_metadata={
            **dict(plan.prompt_metadata or {}),
            "prompt_variations": clean,
            "prompt_count": len(clean),
            "edited_in_prompt_preview": True,
        },
    )


def recreate_source_expression_is_authoritative(
    *, origin: str | None, creative_tags: str,
) -> bool:
    """Capture Recreate expression provenance before provider-ready flattening."""
    if origin != "recreate_with_ava":
        return False
    match = re.search(
        r"(?:^|[\[\n,])\s*Expression\s*:\s*([^,\]\n]*)",
        str(creative_tags or ""),
        flags=re.IGNORECASE,
    )
    return bool(match and match.group(1).strip())


class ContentStudioGenerationService:
    IDENTITY_PROMPT_POLICY_ID = CANONICAL_IDENTITY_POLICY_ID
    IDENTITY_PROMPT_POLICY_VERSION = CANONICAL_IDENTITY_POLICY_VERSION
    def __init__(self, *, creative_director, generation_engine, generation_library, reference_service):
        self.creative_director = creative_director
        self.generation_engine = generation_engine
        self.generation_library = generation_library
        self.reference_service = reference_service

    def queue(
        self, *, creator_profile: dict, creative_tags: str,
        creative_mode: str, prompt_count: int, provider_id: str,
        prompt_batch: tuple[str, ...], origin: str | None = None,
        planner_lineage: dict | None = None,
        explicit_input: dict | None = None,
        diagnostic_trace_id: str | None = None,
        canonical_identity_contract: dict | CanonicalCreatorIdentityContract | None = None,
    ):
        supplied_identity = (
            canonical_identity_contract
            if isinstance(canonical_identity_contract, CanonicalCreatorIdentityContract)
            else CanonicalCreatorIdentityContract.from_dict(canonical_identity_contract)
        )
        canonical_identity = supplied_identity or (
            self.reference_service.resolve_canonical_identity_contract(
                creator_profile=creator_profile,
                provider_id=provider_id,
                identity_prompt_policy_id=self.IDENTITY_PROMPT_POLICY_ID,
                identity_prompt_policy_version=self.IDENTITY_PROMPT_POLICY_VERSION,
            )
        )
        lineage = dict(planner_lineage or {})
        input_contract = dict(explicit_input or {})
        recreate_expression_authoritative = recreate_source_expression_is_authoritative(
            origin=origin,
            creative_tags=creative_tags,
        )
        metadata = {
            **(
                {"canonical_identity_contract": canonical_identity.to_dict()}
                if canonical_identity else {}
            ),
            **({"workflow_origin": origin} if origin else {}),
            **(
                {"recreate_source_expression_authoritative": recreate_expression_authoritative}
                if origin == "recreate_with_ava" else {}
            ),
            **({"planner_lineage": lineage} if lineage else {}),
            **({"explicit_input": input_contract} if input_contract else {}),
            **(
                {
                    "creative_inspiration_provenance": {
                        "reference_role": GenerationReferenceRole.CREATIVE_INSPIRATION.value,
                        "transport": "ANALYSIS_ONLY",
                        "identity_transfer_prohibited": True,
                    }
                }
                if origin == "recreate_with_ava" else {}
            ),
        }
        from app.services.generation_request_diagnostic_service import GenerationRequestDiagnosticService
        diagnostic = GenerationRequestDiagnosticService()
        if origin == "autonomous_inspiration":
            diagnostic.record(
                trace_id=diagnostic_trace_id, workflow_origin=origin,
                stage="5_prompt_plan_input",
                value={"creativeTags": creative_tags, "creativeMode": creative_mode,
                       "promptCount": prompt_count, "providerId": provider_id,
                       "promptBatch": prompt_batch},
            )
        provider_ready_modes = {
            "explicit", "premium_teaser", "spicy", "story_sequence"
        }
        if creative_mode in provider_ready_modes and prompt_batch:
            plan = self.creative_director.create_provider_prompt_plan(
                creator_profile=creator_profile,
                creative_tags=creative_tags,
                creative_mode=creative_mode,
                prompts=prompt_batch,
                metadata=metadata,
                canonical_identity=canonical_identity,
            )
        else:
            plan = self.creative_director.create_prompt_plan(
                creator_profile=creator_profile,
                creative_tags=creative_tags,
                creative_mode=creative_mode,
                prompt_count=prompt_count,
                metadata=metadata,
                canonical_identity=canonical_identity,
            )
            plan = plan_with_prompt_batch(plan, prompt_batch)
            if origin == "autonomous_inspiration":
                diagnostic.record(
                    trace_id=diagnostic_trace_id, workflow_origin=origin,
                    stage="6_prompt_plan_output_and_variations",
                    value={"planId": plan.plan_id, "promptText": plan.prompt_text,
                           "promptMetadata": dict(plan.prompt_metadata or {}),
                           "variations": list(plan.prompt_metadata.get("prompt_variations") or ())},
                )
                diagnostic.record(
                    trace_id=diagnostic_trace_id, workflow_origin=origin,
                    stage="7_prompt_before_render_locks",
                    value=list(plan.prompt_metadata.get("prompt_variations") or ()),
                )
            if creative_mode in {"premium_teaser", "spicy", "story_sequence"}:
                from app.services.seedream_premium_render_locks import (
                    enforce_premium_render_body_lock,
                )

                locked = tuple(
                    enforce_premium_render_body_lock(prompt)
                    for prompt in plan.prompt_metadata.get("prompt_variations") or ()
                )
                plan = plan_with_prompt_batch(plan, locked)
        if origin == "autonomous_inspiration":
            diagnostic.record(
                trace_id=diagnostic_trace_id, workflow_origin=origin,
                stage="8_prompt_after_render_locks",
                value=list(plan.prompt_metadata.get("prompt_variations") or ()),
            )
        variations = tuple(plan.prompt_metadata.get("prompt_variations") or ())
        job = self.generation_engine.queue_prompt_plan(
            creator_profile=creator_profile,
            prompt_plan=plan,
            provider_id=provider_id,
            generation_type=GenerationType.IMAGE_TO_IMAGE.value,
            media_type=GenerationMediaType.IMAGE.value,
            image_count=prompt_count,
            canonical_identity=canonical_identity,
            metadata={
                **(
                    {
                        "canonical_identity_contract": canonical_identity.to_dict(),
                        "canonical_content_sha256": canonical_identity.canonical_content_sha256,
                        "identity_version": canonical_identity.identity_version,
                        "identity_prompt_policy_id": canonical_identity.identity_prompt_policy_id,
                        "identity_prompt_policy_version": canonical_identity.identity_prompt_policy_version,
                        "reference_roles": (canonical_identity.reference_role,),
                    }
                    if canonical_identity else {}
                ),
                "source": "premium_studio",
                "workflow_type": "premium",
                "creative_mode": creative_mode,
                "premium_workflow": True,
                "render_policy": content_render_policy(creative_mode).value,
                "prompt_variations": variations,
                "prompt_batch_count": len(variations) or prompt_count,
                **({"workflow_origin": origin} if origin else {}),
                **(
                    {"recreate_source_expression_authoritative": recreate_expression_authoritative}
                    if origin == "recreate_with_ava" else {}
                ),
                **({"planner_lineage": lineage} if lineage else {}),
                **({"explicit_input": input_contract} if input_contract else {}),
                **(
                    {
                        "creative_inspiration_provenance": {
                            "reference_role": GenerationReferenceRole.CREATIVE_INSPIRATION.value,
                            "transport": "ANALYSIS_ONLY",
                            "identity_transfer_prohibited": True,
                        }
                    }
                    if origin == "recreate_with_ava" else {}
                ),
                **({"diagnostic_trace_id": diagnostic_trace_id} if diagnostic_trace_id else {}),
            },
        )
        return plan, job

    def execute(self, job, *, progress_callback: Callable[..., None] | None = None):
        synced = {}

        def sync_progress(**event):
            outputs = tuple(event.get("output_references") or ())
            if outputs:
                result = job.result or GenerationResult(
                    result_id=f"{job.job_id}_live_result",
                    request_id=job.request.request_id,
                    job_id=job.job_id,
                    provider_id=job.request.provider_id,
                    status=GenerationStatus.SUCCEEDED.value,
                    generation_metadata={
                        "output_generation_recipe_ids": tuple(
                            event.get("output_generation_recipe_ids") or ()
                        ),
                    },
                    output_references=outputs,
                )
                partial = replace(job, status=GenerationStatus.SUCCEEDED.value, result=replace(result, output_references=outputs))
                for record in self.generation_library.sync_job(partial):
                    synced[record.image_id] = record
            if progress_callback:
                progress_callback(**event)

        try:
            executed = self.generation_engine.dispatch_job(job.job_id, progress_callback=sync_progress)
        except TypeError as error:
            if "progress_callback" not in str(error):
                raise
            executed = self.generation_engine.dispatch_job(job.job_id)
        for record in self.generation_library.sync_job(executed):
            synced[record.image_id] = record
        return executed, tuple(synced.values())


def generation_completion_message(*, total_requested: int, success_count: int, failed_count: int) -> tuple[str, str]:
    if success_count >= max(1, int(total_requested or 1)) and failed_count == 0:
        return "success", "Generation completed successfully."
    if success_count > 0:
        return "warning", f"Generation completed with partial success. Success: {success_count}. Failed: {failed_count}."
    return "error", "Generation failed."
