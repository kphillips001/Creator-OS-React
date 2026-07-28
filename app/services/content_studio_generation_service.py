"""HTTP-safe Content Studio generation orchestration using existing domain services."""

from dataclasses import replace
from typing import Callable

from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationMediaType, GenerationResult, GenerationStatus, GenerationType


def plan_with_prompt_batch(plan: PromptPlan, prompts: tuple[str, ...]) -> PromptPlan:
    clean = tuple(str(prompt).strip() for prompt in prompts if str(prompt).strip())
    if not clean:
        return plan
    return replace(
        plan,
        prompt_text="\n\n".join(f"Prompt {index}: {prompt}" for index, prompt in enumerate(clean, 1)),
        prompt_metadata={
            **dict(plan.prompt_metadata or {}),
            "prompt_variations": clean,
            "prompt_count": len(clean),
            "edited_in_prompt_preview": True,
        },
    )


class ContentStudioGenerationService:
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
    ):
        lineage = dict(planner_lineage or {})
        plan = self.creative_director.create_prompt_plan(
            creator_profile=creator_profile,
            creative_tags=creative_tags,
            creative_mode=creative_mode,
            prompt_count=prompt_count,
            metadata={
                **({"workflow_origin": origin} if origin else {}),
                **({"planner_lineage": lineage} if lineage else {}),
            },
        )
        plan = plan_with_prompt_batch(plan, prompt_batch)
        variations = tuple(plan.prompt_metadata.get("prompt_variations") or ())
        job = self.generation_engine.queue_prompt_plan(
            creator_profile=creator_profile,
            prompt_plan=plan,
            provider_id=provider_id,
            generation_type=GenerationType.IMAGE_TO_IMAGE.value,
            media_type=GenerationMediaType.IMAGE.value,
            image_count=prompt_count,
            metadata={
                "source": "premium_studio",
                "workflow_type": "premium",
                "creative_mode": creative_mode,
                "premium_workflow": True,
                "prompt_variations": variations,
                "prompt_batch_count": len(variations) or prompt_count,
                **({"workflow_origin": origin} if origin else {}),
                **({"planner_lineage": lineage} if lineage else {}),
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
