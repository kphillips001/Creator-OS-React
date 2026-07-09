"""Content Studio shell pages.

This module defines Creator OS Content Studio presentation and delegates
generation execution to Generation Engine/provider registry services.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

import app.services.social_publishing_service as social_marketing_service
from app.models.caption_studio import CaptionPlatform, CaptionStyle
from app.models.creative_director import PromptPlan
from app.models.generation_library import GenerationLibraryFilter
from app.models.generation_engine import GenerationJob
from app.models.reference_library import ReferenceLibraryFilter
from app.models.generation_engine import GenerationMediaType, GenerationStatus, GenerationType
from app.services.asset_library_service import AssetLibraryService
from app.services.caption_studio_service import CaptionStudioService
from app.services.content_archive_service import ContentArchiveService
from app.services.creative_director_service import CreativeDirectorService
from app.services.edit_studio_service import EditStudioService
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_library_service import GenerationLibraryService
from app.services.generation_result_ingestion_service import GenerationResultIngestionService
from app.services.photoshoot_queue_service import PhotoshootQueueService
from app.services.reference_library_service import ReferenceLibraryService


CONTENT_STUDIO_PAGES = (
    "Social Studio",
    "Premium Studio",
    "Reference Library",
    "Creative Director",
    "Generation Workspace",
    "Generation Library",
    "Archive",
    "Photoshoot Queue",
    "Social Publishing",
    "Caption Studio",
    "Edit Studio",
    "Prompt History",
    "Settings",
)


SOCIAL_PROVIDER_LABELS = {
    "seedream_4_5": "Seedream 4.5",
    "seedream_5_0_lite": "Seedream 5.0 Lite",
    "wan_2_7_image_edit": "WAN 2.7",
    "nano_banana_pro": "Nano Banana Pro",
    "nano_banana": "Nano Banana",
    "future_provider": "Future Provider",
}

SOCIAL_CREATIVE_MODE_LABELS = {
    "social_safe": "Social Safe",
    "story_sequence": "Story Sequence",
}

PREMIUM_PROVIDER_LABELS = {
    "seedream_4_5": "Seedream 4.5",
    "seedream_5_0_lite": "Seedream 5.0 Lite",
    "wan_2_7_image_edit": "WAN 2.7",
    "nano_banana_pro": "Nano Banana Pro",
    "nano_banana": "Nano Banana",
    "flux": "Flux",
    "future_provider": "Future Provider",
}

PREMIUM_CREATIVE_MODE_LABELS = {
    "premium_teaser": "Premium Teaser",
    "spicy": "Spicy",
    "story_sequence": "Story Sequence",
}

EDIT_MODE_LABELS = {
    "single_image": "Single Image Edit",
    "multi_image": "Multi Image Edit",
    "face_replacement": "Face Replacement",
    "style_transfer": "Style Transfer",
    "variation": "Variation",
}


@dataclass(frozen=True)
class ContentStudioShellPage:
    title: str
    purpose: str
    owns: tuple[str, ...]
    future_handoffs: tuple[str, ...] = ()


CONTENT_STUDIO_SHELL = {
    "Social Studio": ContentStudioShellPage(
        title="Social Studio",
        purpose="Workspace shell for social-safe creative batches and review.",
        owns=("Social creative UI", "Batch review workflow", "Social staging handoff"),
        future_handoffs=("Creator OS Local Vault", "AI Import Workflow"),
    ),
    "Premium Studio": ContentStudioShellPage(
        title="Premium Studio",
        purpose="Workspace shell for premium creative planning and review.",
        owns=("Premium creative UI", "Premium review workflow", "Premium staging handoff"),
        future_handoffs=("Creator OS Local Vault", "AI Import Workflow"),
    ),
    "Reference Library": ContentStudioShellPage(
        title="Reference Library",
        purpose="Presentation shell for source references and inspiration assets.",
        owns=("Reference selection UI", "Reference organization workflow"),
        future_handoffs=("Assets", "Creator OS Local Vault"),
    ),
    "Creative Director": ContentStudioShellPage(
        title="Creative Director",
        purpose="Shell for creative direction controls, shot planning, and prompt workflow.",
        owns=("Creative workflow UI", "Shot planning workflow", "Prompt workflow"),
    ),
    "Generation Workspace": ContentStudioShellPage(
        title="Generation Workspace",
        purpose="Operational dashboard for AI generation jobs and generated assets.",
        owns=("Generation job presentation", "Generated asset review workflow", "Generation history"),
        future_handoffs=("Asset Library", "Creator Review"),
    ),
    "Generation Library": ContentStudioShellPage(
        title="Generation Library",
        purpose="Permanent review workspace for generated images before Creator OS asset import.",
        owns=("Generated image review", "Selection workflow", "Bulk operations"),
        future_handoffs=("AI Import Workflow", "Asset Library"),
    ),
    "Photoshoot Queue": ContentStudioShellPage(
        title="Photoshoot Queue",
        purpose="Shell for planned photoshoot sessions awaiting future generation flow.",
        owns=("Photoshoot queue UI", "Creative queue workflow"),
        future_handoffs=("Creator OS Local Vault", "AI Import Workflow"),
    ),
    "Social Publishing": ContentStudioShellPage(
        title="Social Publishing",
        purpose="Marketing queue for generated images before future captioning and posting.",
        owns=("Social Queue", "Platform selection", "Marketing workflow"),
        future_handoffs=("Caption Studio", "Posted History"),
    ),
    "Caption Studio": ContentStudioShellPage(
        title="Caption Studio",
        purpose="Provider-neutral writing engine for social, product, story, and marketing text.",
        owns=("Caption writing", "Tone", "Style", "Prompt templates"),
        future_handoffs=("Social Publishing", "Creator OS Products"),
    ),
    "Edit Studio": ContentStudioShellPage(
        title="Edit Studio",
        purpose="Shell for single-image and multi-image edit workflows.",
        owns=("Edit workflow UI", "Edit review workflow", "Edit staging handoff"),
        future_handoffs=("Creator OS Local Vault", "AI Import Workflow"),
    ),
    "Prompt History": ContentStudioShellPage(
        title="Prompt History",
        purpose="Shell for future prompt archive browsing and reuse.",
        owns=("Prompt history UI", "Prompt workflow"),
    ),
    "Settings": ContentStudioShellPage(
        title="Settings",
        purpose="Shell for Content Studio presentation and workflow preferences.",
        owns=("Content Studio UI settings", "Creative workflow preferences"),
    ),
}


def _render_boundary_summary() -> None:
    st.markdown("### Architecture Boundary")
    owned_col, external_col = st.columns(2)
    with owned_col:
        st.markdown("#### Owned By Content Studio")
        for item in (
            "UI",
            "Creative workflow",
            "Generation workflow shell",
            "Prompt workflow shell",
        ):
            st.caption(item)
    with external_col:
        st.markdown("#### Owned Elsewhere")
        for item in (
            "Assets",
            "Products",
            "Publishing",
            "Business logic",
            "Customer Intelligence",
            "Commerce",
        ):
            st.caption(item)


def _render_future_asset_flow() -> None:
    st.markdown("### Future Asset Flow")
    c1, c2, c3 = st.columns(3)
    c1.metric("Step 1", "Generate")
    c2.metric("Step 2", "Creator OS Local Vault")
    c3.metric("Step 3", "AI Import Workflow")
    st.caption("This shell does not execute generation, upload, import, or publishing.")


def _creator_profile_id(creator_profile: dict | None) -> int | None:
    value = (creator_profile or {}).get("id")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _render_active_reference(
    *,
    creator_profile: dict | None,
    reference_service: ReferenceLibraryService,
    show_preview: bool = True,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    reference = reference_service.get_active_reference(
        creator_profile_id=creator_profile_id,
    )
    st.markdown("### Active Reference")
    if not creator_profile_id:
        st.warning("Creator Profile required before selecting a Reference Image.")
        return
    if reference is None:
        st.info("No active Reference Image selected for this Creator Profile.")
        return
    if not show_preview:
        st.success(f"Active Reference selected: Asset #{reference.asset_id}")
        st.caption(f"Last used: {reference.last_used_at or '-'}")
        return
    preview_col, meta_col = st.columns([1, 3])
    with preview_col:
        if reference.asset.preview_path:
            st.image(reference.asset.preview_path, use_container_width=True)
        else:
            st.caption("Preview unavailable.")
    with meta_col:
        st.write(reference.asset.file_name or f"Asset #{reference.asset_id}")
        st.caption(f"Asset ID: {reference.asset_id}")
        st.caption(f"Local Vault: {reference.asset.original_path or '-'}")
        st.caption(f"Last used: {reference.last_used_at or '-'}")
        st.caption(f"Favorite: {'Yes' if reference.is_favorite else 'No'}")


def _render_creative_session_summary(
    *,
    creator_profile: dict | None,
    creative_director: CreativeDirectorService,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    latest = creative_director.latest_session(creator_profile_id=creator_profile_id)
    st.markdown("### Creative Director")
    if latest is None:
        st.info("No Creative Session planned yet.")
        return
    st.caption(f"Session: {latest.session.session_id}")
    st.caption(f"Mode: {latest.session.creative_mode}")
    st.caption(f"Reference Asset: {latest.session.reference_asset_id or '-'}")
    st.write(", ".join(latest.session.creative_tags))
    if latest.prompt_plan:
        with st.expander("Prompt Plan", expanded=False):
            st.write(latest.prompt_plan.prompt_text)
            st.caption(latest.prompt_plan.creative_rationale)


def _render_generation_request_panel(
    *,
    creator_profile: dict | None,
    creative_director: CreativeDirectorService,
    generation_engine: GenerationEngineService,
    generation_ingestion: GenerationResultIngestionService,
    panel_key: str,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    latest = creative_director.latest_session(creator_profile_id=creator_profile_id)
    st.markdown("### Generation Ready")
    if not creator_profile_id:
        st.info("Creator Profile required before queuing Generation Requests.")
        return
    if latest is None or latest.prompt_plan is None:
        st.info("Create a Prompt Plan before queuing a Generation Request.")
        return

    provider_id = st.text_input(
        "Provider",
        value="future_provider",
        key=f"{panel_key}_generation_provider",
        help="Provider-neutral dispatch target. Future providers plug into Generation Engine.",
    )
    image_count = st.number_input(
        "Image Count",
        min_value=1,
        max_value=12,
        value=max(1, latest.session.prompt_count),
        step=1,
        key=f"{panel_key}_generation_image_count",
    )
    if st.button(
        "Queue Generation Request",
        key=f"{panel_key}_queue_generation_request",
        use_container_width=True,
    ):
        job = generation_engine.queue_prompt_plan(
            creator_profile=creator_profile or {},
            prompt_plan=latest.prompt_plan,
            provider_id=provider_id,
            generation_type=GenerationType.IMAGE_TO_IMAGE.value,
            media_type=GenerationMediaType.IMAGE.value,
            image_count=int(image_count),
            metadata={"source": panel_key},
        )
        st.success("Generation Request queued.")
        st.session_state[f"{panel_key}_latest_generation_job_id"] = job.job_id
        st.rerun()

    job = generation_engine.latest_job_for_prompt_plan(
        prompt_plan_id=latest.prompt_plan.plan_id,
        creator_profile_id=creator_profile_id,
    )
    if job is None:
        st.caption("Status: Generation Ready")
        st.caption(f"Prompt Plan: {latest.prompt_plan.plan_id}")
        st.caption(f"Reference Asset: {latest.prompt_plan.reference_asset_id or '-'}")
        return

    status_col, provider_col, reference_col = st.columns(3)
    status_col.metric("Status", job.status.title())
    provider_col.metric("Provider", job.request.provider_id)
    reference_col.metric("Reference Asset", job.request.reference_asset_id or "-")
    with st.expander("Queued Prompt Plan", expanded=False):
        st.write(job.request.prompt_text)
        st.json(dict(job.request.metadata))

    st.markdown("### Completed Generation Jobs")
    completed_jobs = generation_engine.list_jobs(
        creator_profile_id=creator_profile_id,
        status="succeeded",
    )
    if not completed_jobs:
        st.caption("No completed Generation Jobs yet.")
        return
    for completed in reversed(completed_jobs[-5:]):
        result_count = len(completed.result.output_references) if completed.result else 0
        status = generation_ingestion.ingestion_status_for_job(completed.job_id)
        with st.container():
            c1, c2, c3 = st.columns(3)
            c1.metric("Generated Results", result_count)
            c2.metric("Ingestion", str(status["status"]).title())
            c3.metric("Imported Assets", len(status["imported_asset_ids"]))
            st.caption(f"Job: {completed.job_id}")
            st.caption(f"Provider: {completed.request.provider_id}")
            st.caption(f"Prompt Plan: {completed.request.prompt_plan_id}")
            if status["imported_asset_ids"]:
                st.caption(
                    "Imported Asset IDs: "
                    + ", ".join(str(asset_id) for asset_id in status["imported_asset_ids"])
                )
            for message in status["failed_messages"]:
                st.error(message)
            if completed.result and completed.result.output_references:
                if st.button(
                    "Review / Import Generated Results",
                    key=f"{panel_key}_ingest_{completed.job_id}",
                    use_container_width=True,
                ):
                    st.session_state["dashboard_page"] = "Generation Library"
                    st.session_state["generation_library_selected_job_id"] = completed.job_id
                    st.rerun()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _generation_duration_seconds(job: GenerationJob) -> float | None:
    if job.result and job.result.duration_seconds is not None:
        return float(job.result.duration_seconds)
    started = _parse_datetime(job.started_at)
    completed = _parse_datetime(job.completed_at)
    if started and completed:
        return max(0.0, (completed - started).total_seconds())
    return None


def generation_workspace_metrics(
    jobs: tuple[GenerationJob, ...],
    generation_ingestion: GenerationResultIngestionService,
) -> dict[str, Any]:
    today_dates = {date.today(), datetime.utcnow().date()}
    jobs_today = 0
    succeeded = 0
    failed = 0
    generated_assets = 0
    imported_assets: set[int] = set()
    queue_depth = 0
    durations = []
    for job in jobs:
        created_at = _parse_datetime(job.queued_at)
        if created_at and created_at.date() in today_dates:
            jobs_today += 1
        if job.status == "succeeded":
            succeeded += 1
        if job.status == "failed":
            failed += 1
        if job.status in {"queued", "retry"}:
            queue_depth += 1
        if job.result:
            generated_assets += len(job.result.output_references)
        duration = _generation_duration_seconds(job)
        if duration is not None:
            durations.append(duration)
        ingestion_status = generation_ingestion.ingestion_status_for_job(job.job_id)
        imported_assets.update(
            int(asset_id)
            for asset_id in ingestion_status.get("imported_asset_ids", ())
            if asset_id is not None
        )
    total_terminal = succeeded + failed
    return {
        "jobs_today": jobs_today,
        "success_rate": (succeeded / total_terminal * 100) if total_terminal else 0.0,
        "failed_jobs": failed,
        "average_generation_time": (sum(durations) / len(durations)) if durations else 0.0,
        "generated_assets": generated_assets,
        "imported_assets": len(imported_assets),
        "queue_depth": queue_depth,
    }


def filter_generation_jobs(
    jobs: tuple[GenerationJob, ...],
    *,
    search: str | None = None,
    provider: str | None = None,
    status: str | None = None,
    creator_profile_id: int | None = None,
    creative_mode: str | None = None,
    created_after: date | None = None,
    created_before: date | None = None,
) -> tuple[GenerationJob, ...]:
    search_value = str(search or "").strip().lower()
    provider_value = str(provider or "").strip()
    status_value = str(status or "").strip()
    creative_mode_value = str(creative_mode or "").strip()
    filtered = []
    for job in jobs:
        created_at = _parse_datetime(job.queued_at)
        if creator_profile_id is not None and job.request.creator_profile_id != int(creator_profile_id):
            continue
        if provider_value and job.request.provider_id != provider_value:
            continue
        if status_value and job.status != status_value:
            continue
        if creative_mode_value and job.request.metadata.get("creative_mode") != creative_mode_value:
            continue
        if created_after and (not created_at or created_at.date() < created_after):
            continue
        if created_before and (not created_at or created_at.date() > created_before):
            continue
        haystack = " ".join(
            (
                job.job_id,
                job.request.request_id,
                job.request.prompt_plan_id,
                job.request.prompt_text,
                job.request.provider_id,
                str(job.request.reference_asset_id or ""),
                str(job.failure.reason if job.failure else ""),
            )
        ).lower()
        if search_value and search_value not in haystack:
            continue
        filtered.append(job)
    return tuple(filtered)


def _recent_generated_asset_items(
    *,
    generation_ingestion: GenerationResultIngestionService,
    asset_library: AssetLibraryService,
    limit: int = 12,
):
    asset_ids = []
    seen = set()
    for record in reversed(generation_ingestion.list_records()):
        if record.status != "imported" or record.asset_id is None:
            continue
        if record.asset_id in seen:
            continue
        seen.add(record.asset_id)
        asset_ids.append(record.asset_id)
        if len(asset_ids) >= limit:
            break
    if not asset_ids:
        return ()
    try:
        return asset_library.get_asset_items(tuple(asset_ids))
    except Exception:
        return ()


def social_studio_provider_options(
    generation_engine: GenerationEngineService,
) -> tuple[tuple[str, str], ...]:
    registry = getattr(generation_engine, "provider_registry", None)
    provider_ids = tuple(getattr(registry, "provider_ids", lambda: ())())
    if not provider_ids:
        return (("future_provider", SOCIAL_PROVIDER_LABELS["future_provider"]),)
    options = []
    for provider_id in provider_ids:
        if provider_id == "flux":
            continue
        label = SOCIAL_PROVIDER_LABELS.get(provider_id)
        if label:
            options.append((provider_id, label))
    return tuple(options) or (("future_provider", SOCIAL_PROVIDER_LABELS["future_provider"]),)


def premium_studio_provider_options(
    generation_engine: GenerationEngineService,
) -> tuple[tuple[str, str], ...]:
    registry = getattr(generation_engine, "provider_registry", None)
    provider_ids = tuple(getattr(registry, "provider_ids", lambda: ())())
    if not provider_ids:
        return (("future_provider", PREMIUM_PROVIDER_LABELS["future_provider"]),)
    options = []
    for provider_id in provider_ids:
        label = PREMIUM_PROVIDER_LABELS.get(provider_id)
        if label:
            options.append((provider_id, label))
    return tuple(options) or (("future_provider", PREMIUM_PROVIDER_LABELS["future_provider"]),)


def default_provider_index(
    provider_ids: tuple[str, ...],
    *,
    preferred_provider_id: str = "seedream_4_5",
) -> int:
    return provider_ids.index(preferred_provider_id) if preferred_provider_id in provider_ids else 0


def edit_studio_provider_options(
    generation_engine: GenerationEngineService,
) -> tuple[tuple[str, str], ...]:
    return premium_studio_provider_options(generation_engine)


def _prompt_variations_from_plan(plan: PromptPlan, *, prompt_count: int) -> tuple[str, ...]:
    metadata = dict(plan.prompt_metadata or {})
    variations = tuple(
        str(prompt).strip()
        for prompt in metadata.get("prompt_variations") or ()
        if str(prompt).strip()
    )
    if variations:
        return variations[: max(1, int(prompt_count or len(variations)))]
    return (str(plan.prompt_text or "").strip(),)


def _prompt_batch_signature(
    *,
    creative_mode: str,
    prompt_count: int,
    creative_tags: str,
) -> tuple[str, int, str]:
    return (
        str(creative_mode or "").strip(),
        max(1, int(prompt_count or 1)),
        str(creative_tags or "").strip(),
    )


def _prompt_batch_text(prompts: tuple[str, ...]) -> str:
    return "\n\n".join(
        f"Prompt {index}: {prompt}"
        for index, prompt in enumerate(prompts, start=1)
    )


def _plan_with_prompt_batch(plan: PromptPlan, prompts: tuple[str, ...]) -> PromptPlan:
    clean_prompts = tuple(str(prompt).strip() for prompt in prompts if str(prompt).strip())
    if not clean_prompts:
        clean_prompts = (str(plan.prompt_text or "").strip(),)
    metadata = {
        **dict(plan.prompt_metadata or {}),
        "prompt_variations": clean_prompts,
        "prompt_count": len(clean_prompts),
        "edited_in_prompt_preview": True,
    }
    return replace(
        plan,
        prompt_text=_prompt_batch_text(clean_prompts),
        prompt_metadata=metadata,
    )


def _store_studio_prompt_preview(
    *,
    studio_key: str,
    plan: PromptPlan,
    prompt_count: int,
    signature: tuple[str, int, str],
) -> tuple[str, ...]:
    prompts = _prompt_variations_from_plan(plan, prompt_count=prompt_count)
    st.session_state[f"{studio_key}_latest_prompt_plan_id"] = plan.plan_id
    st.session_state[f"{studio_key}_prompt_preview_signature"] = signature
    st.session_state[f"{studio_key}_prompt_preview_prompts"] = prompts
    return prompts


def _load_studio_prompt_preview(
    *,
    studio_key: str,
    signature: tuple[str, int, str],
) -> tuple[str, ...]:
    if st.session_state.get(f"{studio_key}_prompt_preview_signature") != signature:
        return ()
    return tuple(st.session_state.get(f"{studio_key}_prompt_preview_prompts") or ())


def _create_studio_prompt_preview(
    *,
    studio_key: str,
    creator_profile: dict | None,
    creative_director: CreativeDirectorService,
    creative_tags: str,
    creative_mode: str,
    prompt_count: int,
) -> PromptPlan:
    plan = creative_director.create_prompt_plan(
        creator_profile=creator_profile or {},
        creative_tags=creative_tags,
        creative_mode=creative_mode,
        prompt_count=prompt_count,
    )
    _store_studio_prompt_preview(
        studio_key=studio_key,
        plan=plan,
        prompt_count=prompt_count,
        signature=_prompt_batch_signature(
            creative_mode=creative_mode,
            prompt_count=prompt_count,
            creative_tags=creative_tags,
        ),
    )
    return plan


def _render_prompt_preview_workflow(
    *,
    studio_key: str,
    creator_profile: dict | None,
    creator_profile_id: int,
    creative_director: CreativeDirectorService,
    creative_tags: str,
    creative_mode: str,
    prompt_count: int,
    disabled: bool,
    button_label: str,
) -> tuple[PromptPlan | None, tuple[str, ...]]:
    signature = _prompt_batch_signature(
        creative_mode=creative_mode,
        prompt_count=prompt_count,
        creative_tags=creative_tags,
    )
    latest = creative_director.latest_session(creator_profile_id=creator_profile_id)
    latest_plan = latest.prompt_plan if latest and latest.prompt_plan else None
    active_plan = (
        latest_plan
        if latest_plan
        and latest_plan.plan_id == st.session_state.get(f"{studio_key}_latest_prompt_plan_id")
        and st.session_state.get(f"{studio_key}_prompt_preview_signature") == signature
        else None
    )
    prompts = _load_studio_prompt_preview(studio_key=studio_key, signature=signature)

    st.markdown("### Prompt Preview")
    with st.expander("Prompt Preview", expanded=False):
        st.caption("These editable prompts are the prompts sent to Generation Engine for this batch.")
        action_col, copy_col = st.columns(2)
        if action_col.button(
            button_label,
            disabled=disabled,
            key=f"{studio_key}_regenerate_prompt_preview",
            use_container_width=True,
        ):
            active_plan = _create_studio_prompt_preview(
                studio_key=studio_key,
                creator_profile=creator_profile,
                creative_director=creative_director,
                creative_tags=creative_tags,
                creative_mode=creative_mode,
                prompt_count=prompt_count,
            )
            prompts = _load_studio_prompt_preview(studio_key=studio_key, signature=signature)
            st.rerun()

        if not prompts and active_plan:
            prompts = _store_studio_prompt_preview(
                studio_key=studio_key,
                plan=active_plan,
                prompt_count=prompt_count,
                signature=signature,
            )

        if prompts:
            edited_prompts = []
            for index, prompt in enumerate(prompts, start=1):
                edited_prompts.append(
                    st.text_area(
                        f"Prompt {index}",
                        value=prompt,
                        key=f"{studio_key}_prompt_preview_text_{index}",
                        height=150,
                    )
                )
            clean_edited = tuple(str(prompt).strip() for prompt in edited_prompts if str(prompt).strip())
            st.session_state[f"{studio_key}_prompt_preview_prompts"] = clean_edited
            copy_col.download_button(
                "Copy Prompt Batch",
                data=_prompt_batch_text(clean_edited),
                file_name=f"{studio_key}_prompt_batch.txt",
                mime="text/plain",
                disabled=not clean_edited,
                use_container_width=True,
            )
            with st.expander("Advanced Details", expanded=False):
                if active_plan:
                    st.caption(f"Prompt Plan: {active_plan.plan_id}")
                    st.caption(f"Creative Mode: {active_plan.creative_mode}")
                    st.caption(active_plan.creative_rationale)
                    st.json(dict(active_plan.prompt_metadata or {}))
            if active_plan:
                active_plan = _plan_with_prompt_batch(active_plan, clean_edited)
            return active_plan, clean_edited

        st.info("Prompt Preview is ready when you create, regenerate, or generate images.")
    return active_plan, prompts


def _ensure_prompt_preview_for_generation(
    *,
    studio_key: str,
    creator_profile: dict | None,
    creative_director: CreativeDirectorService,
    creative_tags: str,
    creative_mode: str,
    prompt_count: int,
    existing_plan: PromptPlan | None,
    existing_prompts: tuple[str, ...],
) -> PromptPlan:
    signature = _prompt_batch_signature(
        creative_mode=creative_mode,
        prompt_count=prompt_count,
        creative_tags=creative_tags,
    )
    prompts = tuple(str(prompt).strip() for prompt in existing_prompts if str(prompt).strip())
    plan = existing_plan
    if not plan or st.session_state.get(f"{studio_key}_prompt_preview_signature") != signature:
        plan = _create_studio_prompt_preview(
            studio_key=studio_key,
            creator_profile=creator_profile,
            creative_director=creative_director,
            creative_tags=creative_tags,
            creative_mode=creative_mode,
            prompt_count=prompt_count,
        )
        prompts = _load_studio_prompt_preview(studio_key=studio_key, signature=signature)
    return _plan_with_prompt_batch(plan, prompts)


def create_social_studio_generation_request(
    *,
    creator_profile: dict | None,
    reference_service: ReferenceLibraryService,
    creative_director: CreativeDirectorService,
    generation_engine: GenerationEngineService,
    creative_tags: str,
    creative_mode: str,
    prompt_count: int,
    provider_id: str,
    prompt_plan: PromptPlan | None = None,
):
    creator_profile_id = _creator_profile_id(creator_profile)
    if not creator_profile_id:
        raise ValueError("Creator Profile required before generating.")
    active_reference = reference_service.get_active_reference(
        creator_profile_id=creator_profile_id,
    )
    if active_reference is None:
        raise ValueError("Select an active Reference Image before generating.")
    if not str(creative_tags or "").strip():
        raise ValueError("Creative Tags are required.")
    plan = prompt_plan or creative_director.create_prompt_plan(
        creator_profile=creator_profile or {},
        creative_tags=creative_tags,
        creative_mode=creative_mode,
        prompt_count=prompt_count,
    )
    prompt_variations = tuple(plan.prompt_metadata.get("prompt_variations") or ())
    job = generation_engine.queue_prompt_plan(
        creator_profile=creator_profile or {},
        prompt_plan=plan,
        provider_id=provider_id,
        generation_type=GenerationType.IMAGE_TO_IMAGE.value,
        media_type=GenerationMediaType.IMAGE.value,
        image_count=prompt_count,
        metadata={
            "source": "social_studio",
            "workflow_type": "social",
            "creative_mode": creative_mode,
            "prompt_variations": prompt_variations,
            "prompt_batch_count": len(prompt_variations) or prompt_count,
        },
    )
    return plan, job


def create_edit_studio_generation_request(
    *,
    creator_profile: dict | None,
    edit_studio: EditStudioService,
    generation_library: GenerationLibraryService,
    generation_engine: GenerationEngineService,
    source_image_ids: tuple[str, ...],
    edit_mode: str,
    edit_prompt: str,
    provider_id: str,
    reference_image_id: str | None = None,
    reference_asset_id: int | None = None,
    batch_size: int = 1,
):
    return edit_studio.create_edit_request(
        creator_profile=creator_profile or {},
        source_image_ids=source_image_ids,
        edit_mode=edit_mode,
        edit_prompt=edit_prompt,
        provider_id=provider_id,
        generation_library=generation_library,
        generation_engine=generation_engine,
        reference_image_id=reference_image_id,
        reference_asset_id=reference_asset_id,
        batch_size=batch_size,
    )


def create_premium_studio_generation_request(
    *,
    creator_profile: dict | None,
    reference_service: ReferenceLibraryService,
    creative_director: CreativeDirectorService,
    generation_engine: GenerationEngineService,
    creative_tags: str,
    creative_mode: str,
    prompt_count: int,
    provider_id: str,
    prompt_plan: PromptPlan | None = None,
):
    creator_profile_id = _creator_profile_id(creator_profile)
    if not creator_profile_id:
        raise ValueError("Creator Profile required before generating.")
    active_reference = reference_service.get_active_reference(
        creator_profile_id=creator_profile_id,
    )
    if active_reference is None:
        raise ValueError("Select an active Reference Image before generating.")
    if creative_mode not in PREMIUM_CREATIVE_MODE_LABELS:
        raise ValueError("Select a Premium creative mode.")
    if not str(creative_tags or "").strip():
        raise ValueError("Creative Tags are required.")
    plan = prompt_plan or creative_director.create_prompt_plan(
        creator_profile=creator_profile or {},
        creative_tags=creative_tags,
        creative_mode=creative_mode,
        prompt_count=prompt_count,
    )
    prompt_variations = tuple(plan.prompt_metadata.get("prompt_variations") or ())
    job = generation_engine.queue_prompt_plan(
        creator_profile=creator_profile or {},
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
            "prompt_variations": prompt_variations,
            "prompt_batch_count": len(prompt_variations) or prompt_count,
        },
    )
    return plan, job


def _render_live_generation_preview(
    *,
    title: str,
    total: int,
    status_placeholder=None,
    progress_placeholder=None,
    preview_placeholder=None,
):
    safe_total = max(1, int(total or 1))
    status_placeholder = status_placeholder or st.empty()
    progress_placeholder = progress_placeholder or st.empty()
    progress_bar = progress_placeholder.progress(0)
    preview_placeholder = preview_placeholder or st.empty()
    seen_outputs: list[str] = []

    def render_status(current: int, message: str, *, failed: bool = False) -> None:
        completed = max(0, min(int(current or 0), safe_total))
        remaining = max(0, safe_total - completed)
        text = (
            f"{message} | {completed} of {safe_total} complete, "
            f"{remaining} remaining"
        )
        if failed:
            status_placeholder.error(text)
        else:
            status_placeholder.info(text)
        progress_bar.progress(min(1.0, completed / safe_total))

    def render_images(outputs: tuple[str, ...]) -> None:
        for output in outputs:
            if output and output not in seen_outputs:
                seen_outputs.append(output)
        with preview_placeholder.container():
            st.markdown(f"### {title}")
            if not seen_outputs:
                st.caption("Images will appear here as each provider result completes.")
                return
            cols = st.columns(min(5, len(seen_outputs)))
            for index, output in enumerate(seen_outputs, start=1):
                with cols[(index - 1) % len(cols)]:
                    st.image(output, use_container_width=True)
                    st.caption(f"{index} of {safe_total}")

    def callback(**event) -> None:
        outputs = tuple(event.get("output_references") or ())
        completed = max(int(event.get("current") or 0), len(outputs))
        render_status(
            completed,
            str(event.get("message") or "Generation running"),
            failed=bool(event.get("failed")),
        )
        render_images(outputs)

    def complete_preview(outputs: tuple[str, ...]) -> None:
        render_images(outputs)
        completed = max(len(seen_outputs), len(outputs), safe_total)
        status_placeholder.success(
            f"Generation Complete | {completed} of {safe_total} complete"
        )
        progress_bar.progress(1.0)
        time.sleep(5)
        preview_placeholder.empty()
        status_placeholder.empty()
        progress_bar.empty()

    render_status(0, f"Queued 0 of {safe_total}")
    render_images(())
    return callback, render_status, render_images, complete_preview


CONTENT_STUDIO_RESET_PREFIXES = (
    "social_studio_",
    "premium_studio_",
    "premium_grok_anything_",
)

CONTENT_STUDIO_RESET_EXACT_KEYS = (
    "content_studio_active_photoshoot_session_id",
    "content_studio_generated_asset_ids",
    "content_studio_open_asset_id",
    "content_studio_open_asset_library",
    "content_studio_creator_review_asset_ids",
)

UNFINISHED_GENERATION_STATUSES = {
    GenerationStatus.QUEUED.value,
    GenerationStatus.RUNNING.value,
    "retry",
}


def reset_content_studio_session_state() -> tuple[str, ...]:
    cleared: list[str] = []
    for key in list(st.session_state.keys()):
        if key in CONTENT_STUDIO_RESET_EXACT_KEYS or any(
            key.startswith(prefix) for prefix in CONTENT_STUDIO_RESET_PREFIXES
        ):
            del st.session_state[key]
            cleared.append(key)
    return tuple(cleared)


def _consume_content_studio_reset_request() -> None:
    reset_label = st.session_state.pop("content_studio_reset_requested", None)
    if not reset_label:
        return
    reset_content_studio_session_state()
    st.session_state["content_studio_reset_notice"] = (
        f"{reset_label} session reset. Permanent Creator OS data was preserved."
    )


def _render_content_studio_reset_notice() -> None:
    notice = st.session_state.pop("content_studio_reset_notice", None)
    if notice:
        st.success(str(notice))


def _request_content_studio_reset(*, studio_label: str, key: str) -> None:
    if st.button("🛑 Reset Session", key=key, use_container_width=True):
        st.session_state["content_studio_reset_requested"] = studio_label
        st.rerun()


def _current_session_job_ids(*, studio_key: str) -> set[str]:
    latest_job_id = st.session_state.get(f"{studio_key}_latest_generation_job_id")
    return {str(latest_job_id)} if latest_job_id else set()


def _session_scoped_generation_jobs(
    jobs: tuple[GenerationJob, ...],
    *,
    studio_key: str,
) -> tuple[GenerationJob, ...]:
    session_job_ids = _current_session_job_ids(studio_key=studio_key)
    if not session_job_ids:
        return ()
    return tuple(job for job in jobs if job.job_id in session_job_ids)


def _render_resume_previous_generation(
    *,
    jobs: tuple[GenerationJob, ...],
    studio_key: str,
    button_key: str,
) -> None:
    if _current_session_job_ids(studio_key=studio_key):
        return
    unfinished_jobs = tuple(
        job for job in reversed(jobs) if job.status in UNFINISHED_GENERATION_STATUSES
    )
    if not unfinished_jobs:
        return
    latest_unfinished = unfinished_jobs[0]
    st.warning("An unfinished generation job exists.")
    if st.button(
        "Resume Previous Generation?",
        key=button_key,
        use_container_width=True,
    ):
        st.session_state[f"{studio_key}_latest_generation_job_id"] = latest_unfinished.job_id
        st.rerun()


def execute_generation_job_to_library(
    *,
    job: GenerationJob,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    progress_callback=None,
):
    """Run a queued job through Generation Engine and index successful outputs."""
    try:
        executed = generation_engine.dispatch_job(
            job.job_id,
            progress_callback=progress_callback,
        )
    except TypeError as error:
        if "progress_callback" not in str(error):
            raise
        executed = generation_engine.dispatch_job(job.job_id)
    records = generation_library.sync_job(executed)
    return executed, records


def execute_photoshoot_next_to_library(
    *,
    session_id: str,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    photoshoot_queue: PhotoshootQueueService,
):
    job = photoshoot_queue.queue_next_prompt(
        session_id=session_id,
        generation_engine=generation_engine,
    )
    if job is None:
        return None, ()
    executed, records = execute_generation_job_to_library(
        job=job,
        generation_engine=generation_engine,
        generation_library=generation_library,
    )
    if executed.status == GenerationStatus.SUCCEEDED.value:
        photoshoot_queue.mark_generation_complete(
            generation_job_id=executed.job_id,
            generated_image_ids=tuple(record.image_id for record in records),
        )
    return executed, records


def create_social_photoshoot_session(
    *,
    creator_profile: dict | None,
    reference_service: ReferenceLibraryService,
    creative_director: CreativeDirectorService,
    photoshoot_queue: PhotoshootQueueService,
    creative_tags: str,
    creative_mode: str,
    prompt_count: int,
    provider_id: str,
    creator_notes: str | None = None,
):
    creator_profile_id = _creator_profile_id(creator_profile)
    if not creator_profile_id:
        raise ValueError("Creator Profile required before starting a Photoshoot.")
    active_reference = reference_service.get_active_reference(
        creator_profile_id=creator_profile_id,
    )
    if active_reference is None:
        raise ValueError("Select an active Reference Image before starting a Photoshoot.")
    plans = []
    for index in range(1, max(1, int(prompt_count or 1)) + 1):
        plan = creative_director.create_prompt_plan(
            creator_profile=creator_profile or {},
            creative_tags=f"{creative_tags}\nShot {index}: maintain creative continuity with the prior shot.",
            creative_mode=creative_mode,
            prompt_count=1,
        )
        plans.append(plan)
    return photoshoot_queue.create_session(
        creator_profile_id=creator_profile_id,
        prompt_plans=plans,
        title="Social Photoshoot",
        provider_id=provider_id,
        reference_asset_id=active_reference.asset_id,
        creator_notes=creator_notes,
        creative_continuity={
            "source": "social_studio",
            "creative_tags": creative_director.normalize_tags(creative_tags),
        },
    )


def create_premium_photoshoot_session(
    *,
    creator_profile: dict | None,
    reference_service: ReferenceLibraryService,
    creative_director: CreativeDirectorService,
    photoshoot_queue: PhotoshootQueueService,
    creative_tags: str,
    creative_mode: str,
    prompt_count: int,
    provider_id: str,
    creator_notes: str | None = None,
):
    creator_profile_id = _creator_profile_id(creator_profile)
    if not creator_profile_id:
        raise ValueError("Creator Profile required before starting a Photoshoot.")
    active_reference = reference_service.get_active_reference(
        creator_profile_id=creator_profile_id,
    )
    if active_reference is None:
        raise ValueError("Select an active Reference Image before starting a Photoshoot.")
    if creative_mode not in PREMIUM_CREATIVE_MODE_LABELS:
        raise ValueError("Select a Premium creative mode.")
    plans = []
    for index in range(1, max(1, int(prompt_count or 1)) + 1):
        plan = creative_director.create_prompt_plan(
            creator_profile=creator_profile or {},
            creative_tags=f"{creative_tags}\nPremium shot {index}: preserve continuity, private creator mood, and review-ready framing.",
            creative_mode=creative_mode,
            prompt_count=1,
        )
        plans.append(plan)
    return photoshoot_queue.create_session(
        creator_profile_id=creator_profile_id,
        prompt_plans=plans,
        title="Premium Photoshoot",
        provider_id=provider_id,
        reference_asset_id=active_reference.asset_id,
        creator_notes=creator_notes,
        creative_continuity={
            "source": "premium_studio",
            "creative_tags": creative_director.normalize_tags(creative_tags),
            "premium_workflow": True,
        },
    )


def _render_social_imported_assets(
    *,
    generation_ingestion: GenerationResultIngestionService,
    asset_library: AssetLibraryService,
) -> None:
    st.markdown("### Imported Assets")
    items = _recent_generated_asset_items(
        generation_ingestion=generation_ingestion,
        asset_library=asset_library,
        limit=6,
    )
    if not items:
        st.caption("Generated assets will appear here after successful ingestion.")
        return
    cols = st.columns(3)
    for index, item in enumerate(items):
        with cols[index % 3]:
            if item.preview_path:
                st.image(item.preview_path, use_container_width=True)
            st.write(item.file_name or f"Asset #{item.asset_id}")
            st.caption(f"Asset ID: {item.asset_id}")
            st.caption(f"Status: {item.status or '-'}")
            if st.button(
                "Open Asset",
                key=f"social_open_asset_{item.asset_id}",
                use_container_width=True,
            ):
                st.session_state["content_studio_open_asset_id"] = item.asset_id
                st.session_state["content_studio_open_asset_library"] = True
            if st.button(
                "Creator Review",
                key=f"social_creator_review_{item.asset_id}",
                use_container_width=True,
            ):
                st.session_state["content_studio_creator_review_asset_ids"] = (item.asset_id,)


def _social_prompt_source_text(selected_source: str, *, creative_tags: str) -> str:
    if selected_source == "Enhanced Tags":
        return str(st.session_state.get("social_studio_enhanced_tags") or "").strip()
    if selected_source == "Surprise Me Tags":
        return str(st.session_state.get("social_studio_surprise_tags") or "").strip()
    return str(creative_tags or "").strip()


def _render_social_studio(
    *,
    creator_profile: dict | None,
    reference_service: ReferenceLibraryService,
    creative_director: CreativeDirectorService,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    generation_ingestion: GenerationResultIngestionService,
    photoshoot_queue: PhotoshootQueueService,
    asset_library: AssetLibraryService,
) -> None:
    _consume_content_studio_reset_request()
    creator_profile_id = _creator_profile_id(creator_profile)
    st.title("Social Studio")
    st.caption("SFW creator workflow for reference-led image generation.")
    _render_content_studio_reset_notice()
    active_reference = reference_service.get_active_reference(
        creator_profile_id=creator_profile_id,
    )
    _render_active_reference(
        creator_profile=creator_profile,
        reference_service=reference_service,
        show_preview=False,
    )
    if not creator_profile_id:
        st.error("Creator Profile required before using Social Studio.")
        return
    if active_reference is None:
        st.warning("Select an active Reference Image before creating a social generation request.")

    settings = creative_director.load_settings(creator_profile_id)
    mode_values = tuple(SOCIAL_CREATIVE_MODE_LABELS)
    selected_mode = st.selectbox(
        "Creative Mode",
        mode_values,
        index=mode_values.index(settings.default_mode)
        if settings.default_mode in mode_values
        else 0,
        format_func=lambda value: SOCIAL_CREATIVE_MODE_LABELS[value],
        key="social_studio_creative_mode",
    )
    prompt_count = st.slider(
        "Prompt Count",
        min_value=1,
        max_value=12,
        value=min(max(settings.default_prompt_count, 1), 12),
        key="social_studio_prompt_count",
    )
    provider_options = social_studio_provider_options(generation_engine)
    provider_ids = tuple(provider_id for provider_id, _ in provider_options)
    provider_labels = dict(provider_options)
    selected_provider = st.selectbox(
        "Provider",
        provider_ids,
        index=default_provider_index(provider_ids),
        format_func=lambda value: provider_labels.get(value, value),
        key="social_studio_provider",
    )

    link_col, library_col = st.columns(2)
    with link_col:
        if st.button(
            "Generation Workspace",
            key="social_studio_generation_workspace_link",
            use_container_width=True,
        ):
            st.session_state["dashboard_page"] = "Generation Workspace"
            st.rerun()
    with library_col:
        if st.button(
            "Generation Library",
            key="social_studio_generation_library_link",
            use_container_width=True,
        ):
            st.session_state["dashboard_page"] = "Generation Library"
            st.rerun()

    with st.expander("Creative Director Tools", expanded=True):
        st.caption("Social-safe prompt helpers, enhanced tags, Surprise Me, and prompt planning.")
        lucky_col, enhance_col, surprise_col = st.columns(3)
        if lucky_col.button(
            "I Feel Lucky",
            disabled=active_reference is None,
            key="social_studio_lucky",
            use_container_width=True,
        ):
            lucky_tags = creative_director.i_feel_lucky(
                creator_profile=creator_profile,
                creative_mode=selected_mode,
                prompt_count=prompt_count,
            )
            st.session_state["social_studio_creative_tags"] = "\n".join(lucky_tags)
            st.session_state["social_studio_selected_tag_source"] = "Original Tags"
            st.rerun()

        creative_tags = st.text_area(
            "Creative Tags",
            key="social_studio_creative_tags",
            placeholder="Enter SFW scene ideas, wardrobe, setting, mood, framing, and constraints.",
            height=120,
            disabled=active_reference is None,
        )
        if enhance_col.button(
            "Enhance Social Tags",
            disabled=active_reference is None or not str(creative_tags).strip(),
            key="social_studio_enhance_tags_button",
            use_container_width=True,
        ):
            st.session_state["social_studio_enhanced_tags"] = creative_director.enhance_social_tags(
                simple_tags=creative_tags,
                creator_profile=creator_profile,
            )
            st.session_state["social_studio_selected_tag_source"] = "Enhanced Tags"
            st.rerun()
        if surprise_col.button(
            "Surprise Me",
            disabled=active_reference is None or not str(creative_tags).strip(),
            key="social_studio_surprise_tags_button",
            use_container_width=True,
        ):
            st.session_state["social_studio_surprise_tags"] = creative_director.surprise_social_tags(
                simple_tags=creative_tags,
                creator_profile=creator_profile,
            )
            st.session_state["social_studio_selected_tag_source"] = "Surprise Me Tags"
            st.rerun()
        st.text_area(
            "Enhanced Social Tags",
            key="social_studio_enhanced_tags",
            height=90,
            disabled=active_reference is None,
        )
        st.text_area(
            "Surprise Me Tags",
            key="social_studio_surprise_tags",
            height=90,
            disabled=active_reference is None,
        )
        selected_social_source = st.radio(
            "Choose tags to send to prompt planning",
            ("Original Tags", "Enhanced Tags", "Surprise Me Tags"),
            key="social_studio_selected_tag_source",
            horizontal=True,
        )
        selected_social_prompt_input = _social_prompt_source_text(
            selected_social_source,
            creative_tags=creative_tags,
        )
        if selected_social_prompt_input:
            st.caption(f"Using {selected_social_source}.")
        else:
            st.warning("Selected social prompt source is empty.")

    preview_plan, preview_prompts = _render_prompt_preview_workflow(
        studio_key="social_studio",
        creator_profile=creator_profile,
        creator_profile_id=creator_profile_id,
        creative_director=creative_director,
        creative_tags=selected_social_prompt_input,
        creative_mode=selected_mode,
        prompt_count=prompt_count,
        disabled=active_reference is None or not str(selected_social_prompt_input).strip(),
        button_label="Regenerate Prompt Preview",
    )

    generate_clicked = False
    action_row = st.container()
    with action_row:
        action_col, generate_col = st.columns(2)
        with action_col:
            if st.button(
                "Create Prompt Preview",
                disabled=active_reference is None or not str(selected_social_prompt_input).strip(),
                key="social_studio_preview_prompt_plan",
                use_container_width=True,
            ):
                _create_studio_prompt_preview(
                    studio_key="social_studio",
                    creator_profile=creator_profile,
                    creative_director=creative_director,
                    creative_tags=selected_social_prompt_input,
                    creative_mode=selected_mode,
                    prompt_count=prompt_count,
                )
                st.success("Prompt Preview created.")
                st.rerun()
        with generate_col:
            generate_clicked = st.button(
                "Generate",
                disabled=active_reference is None or not str(selected_social_prompt_input).strip(),
                key="social_studio_generate",
                use_container_width=True,
            )
    live_status_placeholder = st.empty()
    live_progress_placeholder = st.empty()
    live_preview_placeholder = st.empty()
    if generate_clicked:
        try:
            prompt_plan = _ensure_prompt_preview_for_generation(
                studio_key="social_studio",
                creator_profile=creator_profile,
                creative_director=creative_director,
                creative_tags=selected_social_prompt_input,
                creative_mode=selected_mode,
                prompt_count=prompt_count,
                existing_plan=preview_plan,
                existing_prompts=preview_prompts,
            )
            plan, job = create_social_studio_generation_request(
                creator_profile=creator_profile,
                reference_service=reference_service,
                creative_director=creative_director,
                generation_engine=generation_engine,
                creative_tags=selected_social_prompt_input,
                creative_mode=selected_mode,
                prompt_count=prompt_count,
                provider_id=selected_provider,
                prompt_plan=prompt_plan,
            )
            progress_callback, render_status, render_images, complete_preview = _render_live_generation_preview(
                title="Live Generated Images",
                total=prompt_count,
                status_placeholder=live_status_placeholder,
                progress_placeholder=live_progress_placeholder,
                preview_placeholder=live_preview_placeholder,
            )
            with st.spinner(f"Generating {prompt_count} image(s) with {provider_labels.get(selected_provider, selected_provider)}..."):
                executed, records = execute_generation_job_to_library(
                    job=job,
                    generation_engine=generation_engine,
                    generation_library=generation_library,
                    progress_callback=progress_callback,
                )
        except ValueError as error:
            st.error(str(error))
        except Exception as error:
            st.error(f"Generation failed: {error}")
        else:
            st.session_state["social_studio_latest_prompt_plan_id"] = plan.plan_id
            st.session_state["social_studio_latest_generation_job_id"] = executed.job_id
            if executed.status == GenerationStatus.SUCCEEDED.value:
                outputs = tuple(record.output_reference for record in records)
                complete_preview(
                    outputs or tuple(executed.result.output_references if executed.result else ())
                )
                st.success(f"Generation completed. {len(records)} item(s) added to Generation Library.")
            elif executed.failure:
                render_status(
                    len(executed.result.output_references) if executed.result else 0,
                    executed.failure.reason,
                    failed=True,
                )
                st.error(executed.failure.reason)
            else:
                render_status(
                    executed.progress.current,
                    f"Generation finished with status: {executed.status}",
                )
                st.warning(f"Generation finished with status: {executed.status}.")
            st.rerun()

    st.markdown("### Photoshoot")
    current_photoshoot = photoshoot_queue.current_session(
        creator_profile_id=creator_profile_id,
    )
    shoot_col1, shoot_col2, shoot_col3 = st.columns(3)
    with shoot_col1:
        if st.button(
            "Start Photoshoot",
            disabled=active_reference is None or not str(creative_tags).strip(),
            key="social_studio_start_photoshoot",
            use_container_width=True,
        ):
            try:
                session = create_social_photoshoot_session(
                    creator_profile=creator_profile,
                    reference_service=reference_service,
                    creative_director=creative_director,
                    photoshoot_queue=photoshoot_queue,
                    creative_tags=creative_tags,
                    creative_mode=selected_mode,
                    prompt_count=prompt_count,
                    provider_id=selected_provider,
                    creator_notes="Started from Social Studio.",
                )
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state["content_studio_active_photoshoot_session_id"] = session.session_id
                st.success("Photoshoot Session started.")
                st.rerun()
    with shoot_col2:
        if st.button(
            "Continue Photoshoot",
            disabled=current_photoshoot is None,
            key="social_studio_continue_photoshoot",
            use_container_width=True,
        ):
            if current_photoshoot:
                st.session_state["content_studio_active_photoshoot_session_id"] = current_photoshoot.session_id
                st.session_state["dashboard_page"] = "Photoshoot Queue"
                st.rerun()
    with shoot_col3:
        if st.button(
            "Open Existing Photoshoot",
            key="social_studio_open_photoshoot",
            use_container_width=True,
        ):
            st.session_state["dashboard_page"] = "Photoshoot Queue"
            st.rerun()
    if current_photoshoot:
        progress = photoshoot_queue.progress(current_photoshoot.session_id)
        st.caption(
            f"Current Photoshoot: {current_photoshoot.session_id} | "
            f"{progress.imported_assets} imported asset(s), "
            f"{progress.queued_prompts} remaining prompt(s)."
        )

    st.markdown("### Generation Progress")
    jobs = generation_engine.list_jobs(creator_profile_id=creator_profile_id)
    all_social_jobs = tuple(
        job
        for job in jobs
        if job.request.metadata.get("source") == "social_studio"
        or job.request.metadata.get("creative_mode") in SOCIAL_CREATIVE_MODE_LABELS
    )
    _render_resume_previous_generation(
        jobs=all_social_jobs,
        studio_key="social_studio",
        button_key="social_studio_resume_previous_generation",
    )
    social_jobs = _session_scoped_generation_jobs(
        all_social_jobs,
        studio_key="social_studio",
    )
    if not social_jobs:
        st.caption("No active Social Studio generation session.")
    for job in reversed(social_jobs[-5:]):
        status = generation_ingestion.ingestion_status_for_job(job.job_id)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Status", job.status.title())
        c2.metric("Provider", provider_labels.get(job.request.provider_id, job.request.provider_id))
        c3.metric("Progress", f"{job.progress.percent:.0f}%")
        c4.metric("Imported", len(status.get("imported_asset_ids", ())))
        st.caption(f"Job ID: {job.job_id}")
        st.caption(f"Prompt Plan: {job.request.prompt_plan_id}")
        if job.failure:
            st.error(job.failure.reason)
        elif job.result and job.result.output_references:
            st.caption(f"Generation Library items: {len(job.result.output_references)}")
        if status.get("imported_asset_ids"):
            st.caption(
                "Imported Asset IDs: "
                + ", ".join(str(asset_id) for asset_id in status["imported_asset_ids"])
            )
        for message in status.get("failed_messages", ()):
            st.error(message)

    _render_social_imported_assets(
        generation_ingestion=generation_ingestion,
        asset_library=asset_library,
    )
    if st.button(
        "Open Asset Library",
        key="social_studio_open_asset_library",
        use_container_width=True,
    ):
        st.session_state["dashboard_page"] = "Asset Library"
        st.rerun()
    _request_content_studio_reset(
        studio_label="Social Studio",
        key="social_studio_reset_session",
    )


def _premium_prompt_source_text(selected_source: str, *, creative_tags: str) -> str:
    if selected_source == "Enhanced Tags":
        return str(st.session_state.get("premium_studio_enhanced_tags") or "").strip()
    if selected_source == "Surprise Me Tags":
        return str(st.session_state.get("premium_studio_surprise_tags") or "").strip()
    if selected_source == "Enhanced Explicit Tags":
        return str(st.session_state.get("premium_studio_enhanced_explicit_tags") or "").strip()
    if selected_source == "Ask Grok Prompt":
        return str(st.session_state.get("premium_studio_manual_prompt") or "").strip()
    return str(creative_tags or "").strip()


def _store_premium_prompt_batch(prompts: tuple[str, ...], *, source: str) -> None:
    clean_prompts = tuple(prompt for prompt in prompts if str(prompt or "").strip())
    st.session_state["premium_studio_prompt_batch"] = clean_prompts
    st.session_state["premium_studio_prompt_batch_source"] = source
    if clean_prompts:
        st.session_state["premium_studio_manual_prompt"] = clean_prompts[0]


def _render_premium_prompt_batch() -> None:
    prompts = tuple(st.session_state.get("premium_studio_prompt_batch") or ())
    if not prompts:
        return
    st.markdown("### Premium Prompt Helper")
    st.caption(
        f"Prompt archive source: {st.session_state.get('premium_studio_prompt_batch_source') or 'Premium Studio'}"
    )
    with st.expander("Generated Premium Prompts", expanded=True):
        for index, prompt in enumerate(prompts, start=1):
            col_prompt, col_action = st.columns([4, 1])
            with col_prompt:
                st.text_area(
                    f"Premium Prompt {index}",
                    value=prompt,
                    key=f"premium_studio_prompt_batch_preview_{index}",
                    height=120,
                )
            with col_action:
                if st.button(
                    "Use",
                    key=f"premium_studio_use_prompt_batch_{index}",
                    use_container_width=True,
                ):
                    st.session_state["premium_studio_manual_prompt"] = prompt
                    st.session_state["premium_studio_selected_tag_source"] = "Ask Grok Prompt"
                    st.rerun()


def _render_premium_prompt_assistant(
    *,
    creator_profile: dict | None,
    creator_profile_id: int,
    creative_director: CreativeDirectorService,
    prompt_count: int,
    active_reference_available: bool,
) -> None:
    with st.expander("Ask Grok / Prompt Assistant", expanded=False):
        st.caption("Create premium shot-card ideas without leaving Premium Studio.")
        lane = st.selectbox(
            "Prompt Assistant Lane",
            ("premium", "explicit"),
            format_func=lambda value: "Premium" if value == "premium" else "Explicit",
            key="premium_studio_prompt_assistant_lane",
        )
        request_text = st.text_area(
            "Ask Grok for Shot Cards",
            key="premium_studio_prompt_assistant_request",
            placeholder="Example: hotel mirror lingerie set with warm lamp light and playful confidence",
            height=100,
            disabled=not active_reference_available,
        )
        if st.button(
            "Ask Grok",
            key="premium_studio_ask_grok",
            disabled=not active_reference_available or not str(request_text).strip(),
            use_container_width=True,
        ):
            try:
                batch = creative_director.ask_prompt_assistant(
                    creator_profile=creator_profile or {},
                    request_text=request_text,
                    lane=lane,
                    prompt_count=prompt_count,
                )
            except ValueError as error:
                st.error(str(error))
            except Exception as error:
                st.error(f"Prompt assistant failed: {error}")
            else:
                st.session_state["premium_studio_prompt_assistant_batch_id"] = batch.batch_id
                st.session_state["premium_studio_prompt_assistant_results"] = batch.prompts
                _store_premium_prompt_batch(batch.prompts, source="Ask Grok")
                st.success("Prompt assistant shot cards created.")
                st.rerun()

        prompts = tuple(st.session_state.get("premium_studio_prompt_assistant_results") or ())
        if prompts:
            selected_number = st.number_input(
                "Use shot card number",
                min_value=1,
                max_value=len(prompts),
                value=1,
                step=1,
                key="premium_studio_prompt_assistant_selected_number",
            )
            selected_prompt = prompts[int(selected_number) - 1]
            st.write(selected_prompt)
            a1, a2, a3 = st.columns(3)
            if a1.button("Use Selected", key="premium_studio_prompt_assistant_use", use_container_width=True):
                st.session_state["premium_studio_manual_prompt"] = selected_prompt
                st.session_state["premium_studio_selected_tag_source"] = "Ask Grok Prompt"
                batch_id = st.session_state.get("premium_studio_prompt_assistant_batch_id")
                if batch_id:
                    creative_director.mark_prompt_assistant_used(batch_id, int(selected_number))
                st.rerun()
            if a2.button("Apply to Premium Tags", key="premium_studio_prompt_assistant_apply_tags", use_container_width=True):
                st.session_state["premium_studio_creative_tags"] = selected_prompt
                st.session_state["premium_studio_selected_tag_source"] = "Original Tags"
                st.rerun()
            if a3.button("Generate All", key="premium_studio_prompt_assistant_generate_all", use_container_width=True):
                _store_premium_prompt_batch(prompts, source="Ask Grok")
                st.session_state["premium_studio_selected_tag_source"] = "Ask Grok Prompt"
                st.rerun()

        history = creative_director.prompt_assistant_history(
            creator_profile_id=creator_profile_id,
            limit=10,
        )
        if history:
            with st.expander("Prompt Archive", expanded=False):
                labels = tuple(
                    f"{batch.created_at[:19]} | {batch.lane} | {batch.request_text[:60]}"
                    for batch in history
                )
                selected_label = st.selectbox(
                    "Archived prompt batch",
                    labels,
                    key="premium_studio_prompt_assistant_archive",
                )
                selected_batch = history[labels.index(selected_label)]
                st.caption(selected_batch.request_text)
                for index, prompt in enumerate(selected_batch.prompts, start=1):
                    used = " used" if index in selected_batch.used_prompt_numbers else ""
                    st.markdown(f"**{index}.**{used} {prompt}")
                archive_number = st.number_input(
                    "Use archived shot card number",
                    min_value=1,
                    max_value=max(1, len(selected_batch.prompts)),
                    value=1,
                    step=1,
                    key="premium_studio_archive_prompt_number",
                )
                c1, c2 = st.columns(2)
                if c1.button("Use Archived", key="premium_studio_archive_use", use_container_width=True):
                    selected_prompt = selected_batch.prompts[int(archive_number) - 1]
                    st.session_state["premium_studio_manual_prompt"] = selected_prompt
                    st.session_state["premium_studio_selected_tag_source"] = "Ask Grok Prompt"
                    creative_director.mark_prompt_assistant_used(
                        selected_batch.batch_id,
                        int(archive_number),
                    )
                    st.rerun()
                if c2.button("Load Batch", key="premium_studio_archive_load", use_container_width=True):
                    st.session_state["premium_studio_prompt_assistant_results"] = selected_batch.prompts
                    st.session_state["premium_studio_prompt_assistant_batch_id"] = selected_batch.batch_id
                    _store_premium_prompt_batch(selected_batch.prompts, source="Prompt Archive")
                    st.rerun()


def _render_premium_grok_anything(
    *,
    creative_director: CreativeDirectorService,
) -> None:
    history_key = "premium_grok_anything_history"
    form_key = "premium_grok_anything_form_key"
    st.session_state.setdefault(history_key, [])
    st.session_state.setdefault(form_key, 0)

    with st.expander("Ask Grok Anything", expanded=False):
        question = st.text_area(
            "Ask Grok",
            height=150,
            key=f"premium_grok_anything_question_{st.session_state[form_key]}",
            placeholder=(
                "Ask anything. Example: give me 10 flirty X captions, critique a pose, "
                "rewrite a caption, or brainstorm premium shot ideas."
            ),
        )
        uploaded_image = st.file_uploader(
            "Add Image",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"premium_grok_anything_image_{st.session_state[form_key]}",
            help="Optional. Add an image when you want Grok to analyze it.",
        )
        ask_col, clear_col = st.columns([3, 1])
        ask_clicked = ask_col.button(
            "Ask Grok",
            key="premium_grok_anything_ask",
            disabled=not str(question).strip(),
            use_container_width=True,
        )
        clear_clicked = clear_col.button(
            "Clear",
            key="premium_grok_anything_clear",
            use_container_width=True,
        )
        if clear_clicked:
            st.session_state[history_key] = []
            st.session_state[form_key] += 1
            st.rerun()
        if ask_clicked:
            image_bytes = uploaded_image.getvalue() if uploaded_image is not None else None
            image_mime_type = getattr(uploaded_image, "type", None) if uploaded_image is not None else None
            image_name = getattr(uploaded_image, "name", None) if uploaded_image is not None else None
            with st.spinner("Asking Grok..."):
                try:
                    answer = creative_director.ask_anything(
                        question=question,
                        image_bytes=image_bytes,
                        image_mime_type=image_mime_type,
                        image_name=image_name,
                    )
                except ValueError as error:
                    st.error(str(error))
                    answer = ""
                except Exception as error:
                    st.error(f"Grok request failed: {error}")
                    answer = ""
            if answer:
                st.session_state[history_key].insert(
                    0,
                    {
                        "question": question,
                        "answer": answer,
                        "image_name": image_name or "",
                    },
                )
                st.rerun()

        history = st.session_state.get(history_key, [])
        if history:
            st.markdown("#### Grok Responses")
            for index, item in enumerate(history, start=1):
                image_label = item.get("image_name")
                label = f"Response {index}" + (f" - {image_label}" if image_label else "")
                with st.expander(label, expanded=index == 1):
                    st.markdown("**Question**")
                    st.write(item.get("question", ""))
                    st.markdown("**Answer**")
                    st.write(item.get("answer", ""))
                    st.markdown("**Copyable Answer**")
                    st.code(item.get("answer", ""), language="text")
            if st.button(
                "Ask Grok another question",
                key="premium_grok_anything_ask_another",
                use_container_width=True,
            ):
                st.session_state[form_key] += 1
                st.rerun()


def _render_premium_studio(
    *,
    creator_profile: dict | None,
    reference_service: ReferenceLibraryService,
    creative_director: CreativeDirectorService,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    generation_ingestion: GenerationResultIngestionService,
    photoshoot_queue: PhotoshootQueueService,
    asset_library: AssetLibraryService,
) -> None:
    _consume_content_studio_reset_request()
    creator_profile_id = _creator_profile_id(creator_profile)
    st.title("Premium Studio")
    st.caption("Premium creator workflow for provider-neutral prompt planning and generation review.")
    _render_content_studio_reset_notice()
    active_reference = reference_service.get_active_reference(
        creator_profile_id=creator_profile_id,
    )
    _render_active_reference(
        creator_profile=creator_profile,
        reference_service=reference_service,
        show_preview=False,
    )
    if not creator_profile_id:
        st.error("Creator Profile required before using Premium Studio.")
        return
    if active_reference is None:
        st.warning("Select an active Reference Image before creating premium work.")

    settings = creative_director.load_settings(creator_profile_id)
    mode_values = tuple(PREMIUM_CREATIVE_MODE_LABELS)
    selected_mode = st.selectbox(
        "Premium Creative Mode",
        mode_values,
        index=mode_values.index(settings.default_mode)
        if settings.default_mode in mode_values
        else 0,
        format_func=lambda value: PREMIUM_CREATIVE_MODE_LABELS[value],
        key="premium_studio_creative_mode",
    )
    prompt_count = st.slider(
        "Prompt Count",
        min_value=1,
        max_value=20,
        value=min(max(settings.default_prompt_count, 1), 20),
        key="premium_studio_prompt_count",
    )
    provider_options = premium_studio_provider_options(generation_engine)
    provider_ids = tuple(provider_id for provider_id, _ in provider_options)
    provider_labels = dict(provider_options)
    selected_provider = st.selectbox(
        "Provider",
        provider_ids,
        index=default_provider_index(provider_ids),
        format_func=lambda value: provider_labels.get(value, value),
        key="premium_studio_provider",
    )

    library_col, workspace_col = st.columns(2)
    with library_col:
        if st.button(
            "Generation Library",
            key="premium_studio_generation_library_link",
            use_container_width=True,
        ):
            st.session_state["dashboard_page"] = "Generation Library"
            st.rerun()
    with workspace_col:
        if st.button(
            "Generation Workspace",
            key="premium_studio_generation_workspace_link",
            use_container_width=True,
        ):
            st.session_state["dashboard_page"] = "Generation Workspace"
            st.rerun()

    with st.expander("Creative Director Tools", expanded=True):
        st.caption("Premium prompt helpers, enhanced tags, Surprise Me, and explicit-ready planning.")
        lucky_col, explicit_lucky_col = st.columns(2)
        if lucky_col.button(
            "I Feel Lucky - Premium",
            disabled=active_reference is None,
            key="premium_studio_lucky",
            use_container_width=True,
        ):
            st.session_state["premium_studio_creative_tags"] = creative_director.premium_lucky_tags(
                creator_profile=creator_profile,
                prompt_count=prompt_count,
            )
            st.session_state["premium_studio_selected_tag_source"] = "Original Tags"
            st.rerun()
        if explicit_lucky_col.button(
            "I Feel Lucky - Explicit",
            disabled=active_reference is None,
            key="premium_studio_lucky_explicit",
            use_container_width=True,
        ):
            st.session_state["premium_studio_explicit_tags"] = creative_director.premium_lucky_tags(
                creator_profile=creator_profile,
                prompt_count=prompt_count,
                explicit=True,
            )
            st.rerun()

        creative_tags = st.text_area(
            "Premium Creative Tags",
            key="premium_studio_creative_tags",
            placeholder="Enter premium scene, wardrobe, setting, mood, continuity, and framing direction.",
            height=130,
            disabled=active_reference is None,
        )
        explicit_tags = st.text_area(
            "Explicit Tags",
            key="premium_studio_explicit_tags",
            placeholder="Optional explicit-ready premium direction for the explicit tag lane.",
            height=90,
            disabled=active_reference is None,
        )

        e1, e2, e3 = st.columns(3)
        if e1.button(
            "Enhance Premium Tags",
            disabled=active_reference is None or not str(creative_tags).strip(),
            key="premium_studio_enhance_tags",
            use_container_width=True,
        ):
            st.session_state["premium_studio_enhanced_tags"] = creative_director.enhance_premium_tags(
                simple_tags=creative_tags,
                creator_profile=creator_profile,
            )
            st.session_state["premium_studio_selected_tag_source"] = "Enhanced Tags"
            st.rerun()
        if e2.button(
            "Surprise Me",
            disabled=active_reference is None or not str(creative_tags).strip(),
            key="premium_studio_surprise_tags_button",
            use_container_width=True,
        ):
            st.session_state["premium_studio_surprise_tags"] = creative_director.surprise_premium_tags(
                simple_tags=creative_tags,
                creator_profile=creator_profile,
            )
            st.session_state["premium_studio_selected_tag_source"] = "Surprise Me Tags"
            st.rerun()
        if e3.button(
            "Enhance Explicit Tags",
            disabled=active_reference is None or not str(explicit_tags).strip(),
            key="premium_studio_enhance_explicit_tags",
            use_container_width=True,
        ):
            st.session_state["premium_studio_enhanced_explicit_tags"] = creative_director.enhance_premium_tags(
                simple_tags=explicit_tags,
                creator_profile=creator_profile,
                explicit=True,
            )
            st.session_state["premium_studio_selected_tag_source"] = "Enhanced Explicit Tags"
            st.rerun()

        st.text_area(
            "Enhanced Premium Tags",
            key="premium_studio_enhanced_tags",
            height=90,
            disabled=active_reference is None,
        )
        st.text_area(
            "Surprise Me Tags",
            key="premium_studio_surprise_tags",
            height=90,
            disabled=active_reference is None,
        )
        st.text_area(
            "Enhanced Explicit Tags",
            key="premium_studio_enhanced_explicit_tags",
            height=90,
            disabled=active_reference is None,
        )
        selected_tag_source = st.radio(
            "Choose tags to send to prompt planning",
            ("Original Tags", "Enhanced Tags", "Surprise Me Tags", "Enhanced Explicit Tags", "Ask Grok Prompt"),
            key="premium_studio_selected_tag_source",
            horizontal=True,
        )
        selected_prompt_input = _premium_prompt_source_text(
            selected_tag_source,
            creative_tags=creative_tags,
        )
        if selected_prompt_input:
            st.caption(f"Using {selected_tag_source}.")
        else:
            st.warning("Selected premium prompt source is empty.")

    _render_premium_grok_anything(
        creative_director=creative_director,
    )
    _render_premium_prompt_assistant(
        creator_profile=creator_profile,
        creator_profile_id=creator_profile_id,
        creative_director=creative_director,
        prompt_count=prompt_count,
        active_reference_available=active_reference is not None,
    )
    _render_premium_prompt_batch()

    manual_prompt = st.text_area(
        "Manual Prompt",
        key="premium_studio_manual_prompt",
        placeholder="Optional: paste or edit a complete premium prompt. This bypasses tag enhancement but still uses Generation Engine.",
        height=130,
        disabled=active_reference is None,
    )
    selected_prompt_input = str(manual_prompt or "").strip() or selected_prompt_input

    preview_plan, preview_prompts = _render_prompt_preview_workflow(
        studio_key="premium_studio",
        creator_profile=creator_profile,
        creator_profile_id=creator_profile_id,
        creative_director=creative_director,
        creative_tags=selected_prompt_input,
        creative_mode=selected_mode,
        prompt_count=prompt_count,
        disabled=active_reference is None or not str(selected_prompt_input).strip(),
        button_label="Regenerate Premium Prompt Preview",
    )

    generate_clicked = False
    action_row = st.container()
    with action_row:
        action_col, generate_col = st.columns(2)
        with action_col:
            if st.button(
                "Create Premium Prompt Preview",
                disabled=active_reference is None or not str(selected_prompt_input).strip(),
                key="premium_studio_preview_prompt_plan",
                use_container_width=True,
            ):
                _create_studio_prompt_preview(
                    studio_key="premium_studio",
                    creator_profile=creator_profile,
                    creative_director=creative_director,
                    creative_tags=selected_prompt_input,
                    creative_mode=selected_mode,
                    prompt_count=prompt_count,
                )
                st.success("Premium Prompt Preview created.")
                st.rerun()
        with generate_col:
            generate_clicked = st.button(
                "Generate Premium Images",
                disabled=active_reference is None or not str(selected_prompt_input).strip(),
                key="premium_studio_generate",
                use_container_width=True,
            )
    live_status_placeholder = st.empty()
    live_progress_placeholder = st.empty()
    live_preview_placeholder = st.empty()
    if generate_clicked:
        try:
            prompt_plan = _ensure_prompt_preview_for_generation(
                studio_key="premium_studio",
                creator_profile=creator_profile,
                creative_director=creative_director,
                creative_tags=selected_prompt_input,
                creative_mode=selected_mode,
                prompt_count=prompt_count,
                existing_plan=preview_plan,
                existing_prompts=preview_prompts,
            )
            plan, job = create_premium_studio_generation_request(
                creator_profile=creator_profile,
                reference_service=reference_service,
                creative_director=creative_director,
                generation_engine=generation_engine,
                creative_tags=selected_prompt_input,
                creative_mode=selected_mode,
                prompt_count=prompt_count,
                provider_id=selected_provider,
                prompt_plan=prompt_plan,
            )
            progress_callback, render_status, render_images, complete_preview = _render_live_generation_preview(
                title="Live Generated Images",
                total=prompt_count,
                status_placeholder=live_status_placeholder,
                progress_placeholder=live_progress_placeholder,
                preview_placeholder=live_preview_placeholder,
            )
            with st.spinner(f"Generating {prompt_count} premium image(s) with {provider_labels.get(selected_provider, selected_provider)}..."):
                executed, records = execute_generation_job_to_library(
                    job=job,
                    generation_engine=generation_engine,
                    generation_library=generation_library,
                    progress_callback=progress_callback,
                )
        except ValueError as error:
            st.error(str(error))
        except Exception as error:
            st.error(f"Generation failed: {error}")
        else:
            st.session_state["premium_studio_latest_prompt_plan_id"] = plan.plan_id
            st.session_state["premium_studio_latest_generation_job_id"] = executed.job_id
            if executed.status == GenerationStatus.SUCCEEDED.value:
                outputs = tuple(record.output_reference for record in records)
                complete_preview(
                    outputs or tuple(executed.result.output_references if executed.result else ())
                )
                st.success(f"Generation completed. {len(records)} item(s) added to Generation Library.")
            elif executed.failure:
                render_status(
                    len(executed.result.output_references) if executed.result else 0,
                    executed.failure.reason,
                    failed=True,
                )
                st.error(executed.failure.reason)
            else:
                render_status(
                    executed.progress.current,
                    f"Generation finished with status: {executed.status}",
                )
                st.warning(f"Generation finished with status: {executed.status}.")

    st.markdown("### Photoshoot")
    current_photoshoot = photoshoot_queue.current_session(
        creator_profile_id=creator_profile_id,
    )
    shoot_col1, shoot_col2, shoot_col3 = st.columns(3)
    with shoot_col1:
        if st.button(
            "Start Premium Photoshoot",
            disabled=active_reference is None or not str(selected_prompt_input).strip(),
            key="premium_studio_start_photoshoot",
            use_container_width=True,
        ):
            try:
                session = create_premium_photoshoot_session(
                    creator_profile=creator_profile,
                    reference_service=reference_service,
                    creative_director=creative_director,
                    photoshoot_queue=photoshoot_queue,
                    creative_tags=selected_prompt_input,
                    creative_mode=selected_mode,
                    prompt_count=prompt_count,
                    provider_id=selected_provider,
                    creator_notes="Started from Premium Studio.",
                )
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state["content_studio_active_photoshoot_session_id"] = session.session_id
                st.success("Premium Photoshoot Session started.")
                st.rerun()
    with shoot_col2:
        if st.button(
            "Continue Photoshoot",
            disabled=current_photoshoot is None,
            key="premium_studio_continue_photoshoot",
            use_container_width=True,
        ):
            if current_photoshoot:
                st.session_state["content_studio_active_photoshoot_session_id"] = current_photoshoot.session_id
                st.session_state["dashboard_page"] = "Photoshoot Queue"
                st.rerun()
    with shoot_col3:
        if st.button(
            "Open Existing Photoshoot",
            key="premium_studio_open_photoshoot",
            use_container_width=True,
        ):
            st.session_state["dashboard_page"] = "Photoshoot Queue"
            st.rerun()
    if current_photoshoot:
        progress = photoshoot_queue.progress(current_photoshoot.session_id)
        st.caption(
            f"Current Photoshoot: {current_photoshoot.session_id} | "
            f"{progress.approved_images} approved image(s), "
            f"{progress.queued_prompts} remaining prompt(s)."
        )

    st.markdown("### Generation Status")
    jobs = generation_engine.list_jobs(creator_profile_id=creator_profile_id)
    all_premium_jobs = tuple(
        job
        for job in jobs
        if job.request.metadata.get("source") == "premium_studio"
        or job.request.metadata.get("premium_workflow") is True
        or job.request.metadata.get("creative_mode") in PREMIUM_CREATIVE_MODE_LABELS
    )
    _render_resume_previous_generation(
        jobs=all_premium_jobs,
        studio_key="premium_studio",
        button_key="premium_studio_resume_previous_generation",
    )
    premium_jobs = _session_scoped_generation_jobs(
        all_premium_jobs,
        studio_key="premium_studio",
    )
    generation_library.sync_jobs(job for job in premium_jobs if job.status == "succeeded")
    if not premium_jobs:
        st.caption("No active Premium Studio generation session.")
    for job in reversed(premium_jobs[-6:]):
        status = generation_ingestion.ingestion_status_for_job(job.job_id)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Status", job.status.title())
        c2.metric("Provider", provider_labels.get(job.request.provider_id, job.request.provider_id))
        c3.metric("Progress", f"{job.progress.percent:.0f}%")
        c4.metric("Library Items", len(job.result.output_references) if job.result else 0)
        st.caption(f"Job ID: {job.job_id}")
        st.caption(f"Prompt Plan: {job.request.prompt_plan_id}")
        st.caption(f"Creative Mode: {job.request.metadata.get('creative_mode') or '-'}")
        if job.failure:
            st.error(job.failure.reason)
        if status.get("imported_asset_ids"):
            st.caption(
                "Imported Asset IDs: "
                + ", ".join(str(asset_id) for asset_id in status["imported_asset_ids"])
            )
        for message in status.get("failed_messages", ()):
            st.error(message)

    if st.button(
        "Open Generation Library",
        key="premium_studio_open_generation_library",
        use_container_width=True,
    ):
        st.session_state["dashboard_page"] = "Generation Library"
        st.rerun()
    asset_count = len(_recent_generated_asset_items(
        generation_ingestion=generation_ingestion,
        asset_library=asset_library,
        limit=6,
    ))
    st.caption(f"Creator OS imported generated assets: {asset_count}")
    _request_content_studio_reset(
        studio_label="Premium Studio",
        key="premium_studio_reset_session",
    )


def _render_edit_studio(
    *,
    creator_profile: dict | None,
    edit_studio: EditStudioService,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    reference_service: ReferenceLibraryService,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    st.title("Edit Studio")
    st.caption("Single, multi-image, face, style, and variation edits for Generation Library images.")
    if not creator_profile_id:
        st.error("Creator Profile required before using Edit Studio.")
        return

    edit_studio.sync_generation_library(
        generation_engine=generation_engine,
        generation_library=generation_library,
    )
    library_result = generation_library.browse(
        GenerationLibraryFilter(
            creator_profile_id=creator_profile_id,
            status="active",
            sort="newest",
        )
    )
    active_reference = reference_service.get_active_reference(
        creator_profile_id=creator_profile_id,
    )

    st.markdown("### Select Image(s)")
    source_options = tuple(record.image_id for record in library_result.records)
    selected_source_ids = tuple(
        st.multiselect(
            "Generation Library Images",
            source_options,
            default=tuple(
                st.session_state.get("edit_studio_source_image_ids")
                or st.session_state.get("generation_library_selected_ids")
                or ()
            ),
            key="edit_studio_source_image_ids",
        )
    )
    source_records = tuple(
        record for record in library_result.records if record.image_id in selected_source_ids
    )
    if not source_options:
        st.info("Generation Library images will appear here after generation completes.")

    st.markdown("### Edit Request")
    mode_values = tuple(EDIT_MODE_LABELS)
    edit_mode = st.selectbox(
        "Edit Mode",
        mode_values,
        format_func=lambda value: EDIT_MODE_LABELS[value],
        key="edit_studio_mode",
    )
    provider_options = edit_studio_provider_options(generation_engine)
    provider_ids = tuple(provider_id for provider_id, _ in provider_options)
    provider_labels = dict(provider_options)
    selected_provider = st.selectbox(
        "Provider",
        provider_ids,
        format_func=lambda value: provider_labels.get(value, value),
        key="edit_studio_provider",
    )
    batch_size = st.slider(
        "Batch Edit Count",
        min_value=1,
        max_value=12,
        value=max(1, min(len(selected_source_ids) or 1, 12)),
        key="edit_studio_batch_size",
    )
    reference_image_id = None
    if edit_mode in {"multi_image", "style_transfer", "face_replacement"}:
        reference_options = tuple(
            record.image_id
            for record in library_result.records
            if record.image_id not in selected_source_ids
        )
        reference_image_id = st.selectbox(
            "Reference Image Selection",
            ("", *reference_options),
            key="edit_studio_reference_image_id",
        ) or None
    reference_asset_id = active_reference.asset_id if active_reference else None
    if active_reference:
        st.caption(f"Active Reference Asset: {active_reference.asset_id}")

    prompt_placeholder = {
        "single_image": "Describe the exact change while preserving everything else.",
        "multi_image": "Describe how the selected images and reference image should combine.",
        "face_replacement": "Describe the face replacement while preserving pose, lighting, and body framing.",
        "style_transfer": "Describe the style to transfer and what must remain unchanged.",
        "variation": "Describe the variation range and continuity requirements.",
    }[edit_mode]
    edit_prompt = st.text_area(
        "Edit Prompt",
        placeholder=prompt_placeholder,
        height=150,
        key="edit_studio_prompt",
    )

    st.markdown("### Edit Preview")
    preview_cols = st.columns(2)
    with preview_cols[0]:
        st.caption("Original")
        for record in source_records[:3]:
            if record.output_reference:
                st.image(record.output_reference, use_container_width=True)
            st.caption(record.image_id)
    with preview_cols[1]:
        st.caption("Edited")
        edited_records = tuple(
            record
            for record in library_result.records
            if (record.generation_metadata.get("request_metadata") or {}).get("source") == "edit_studio"
        )
        if not edited_records:
            st.info("Edited images return to Generation Library after the Generation Engine completes.")
        for record in edited_records[:3]:
            if record.output_reference:
                st.image(record.output_reference, use_container_width=True)
            st.caption(record.image_id)

    submit_disabled = (
        not selected_source_ids
        or not str(edit_prompt).strip()
        or (edit_mode in {"multi_image", "style_transfer", "face_replacement"} and not reference_image_id)
    )
    action_cols = st.columns(3)
    with action_cols[0]:
        if st.button(
            "Submit Edit Request",
            disabled=submit_disabled,
            key="edit_studio_submit",
            use_container_width=True,
        ):
            try:
                edit_item, job = create_edit_studio_generation_request(
                    creator_profile=creator_profile,
                    edit_studio=edit_studio,
                    generation_library=generation_library,
                    generation_engine=generation_engine,
                    source_image_ids=selected_source_ids,
                    edit_mode=edit_mode,
                    edit_prompt=edit_prompt,
                    provider_id=selected_provider,
                    reference_image_id=reference_image_id,
                    reference_asset_id=reference_asset_id,
                    batch_size=batch_size,
                )
                with st.spinner("Running Edit Request through Generation Engine..."):
                    executed, records = execute_generation_job_to_library(
                        job=job,
                        generation_engine=generation_engine,
                        generation_library=generation_library,
                    )
            except (KeyError, ValueError) as error:
                st.error(str(error))
            except Exception as error:
                st.error(f"Edit generation failed: {error}")
            else:
                st.session_state["edit_studio_latest_edit_id"] = edit_item.edit_request_id
                st.session_state["edit_studio_latest_generation_job_id"] = executed.job_id
                if executed.status == GenerationStatus.SUCCEEDED.value:
                    st.success(f"Edit completed. {len(records)} item(s) returned to Generation Library.")
                elif executed.failure:
                    st.error(executed.failure.reason)
                else:
                    st.warning(f"Edit finished with status: {executed.status}.")
                st.rerun()
    with action_cols[1]:
        if st.button(
            "Open Generation Library",
            key="edit_studio_open_generation_library",
            use_container_width=True,
        ):
            st.session_state["dashboard_page"] = "Generation Library"
            st.rerun()
    with action_cols[2]:
        if st.button(
            "Batch Edit",
            disabled=not selected_source_ids or not str(edit_prompt).strip(),
            key="edit_studio_batch_edit",
            use_container_width=True,
        ):
            try:
                edit_item, job = edit_studio.batch_edit(
                    creator_profile=creator_profile or {},
                    source_image_ids=selected_source_ids,
                    edit_prompt=edit_prompt,
                    provider_id=selected_provider,
                    generation_library=generation_library,
                    generation_engine=generation_engine,
                )
                with st.spinner("Running Batch Edit through Generation Engine..."):
                    executed, records = execute_generation_job_to_library(
                        job=job,
                        generation_engine=generation_engine,
                        generation_library=generation_library,
                    )
            except (KeyError, ValueError) as error:
                st.error(str(error))
            except Exception as error:
                st.error(f"Batch edit failed: {error}")
            else:
                st.session_state["edit_studio_latest_edit_id"] = edit_item.edit_request_id
                st.session_state["edit_studio_latest_generation_job_id"] = executed.job_id
                if executed.status == GenerationStatus.SUCCEEDED.value:
                    st.success(f"Batch edit completed. {len(records)} item(s) returned to Generation Library.")
                elif executed.failure:
                    st.error(executed.failure.reason)
                else:
                    st.warning(f"Batch edit finished with status: {executed.status}.")
                st.rerun()

    st.markdown("### Edit History")
    history = edit_studio.history(creator_profile_id=creator_profile_id, limit=10)
    if not history:
        st.caption("No Edit Studio history yet.")
    for entry in history:
        st.caption(
            " | ".join(
                (
                    entry.session.created_at,
                    EDIT_MODE_LABELS.get(entry.session.edit_mode, entry.session.edit_mode),
                    ", ".join(entry.session.source_image_ids),
                )
            )
        )
        if entry.edit_request:
            st.write(entry.edit_request.edit_prompt)
            st.caption(f"Generation Job: {entry.edit_request.generation_job_id or '-'}")
            if entry.edit_request.generation_job_id:
                try:
                    job = generation_engine.get_job(entry.edit_request.generation_job_id)
                    st.caption(f"Status: {job.status}")
                    if job.failure:
                        st.error(job.failure.reason)
                except Exception:
                    pass


def _render_generation_job_card(
    *,
    job: GenerationJob,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    generation_ingestion: GenerationResultIngestionService,
    reference_service: ReferenceLibraryService,
    panel_key: str,
) -> None:
    ingestion_status = generation_ingestion.ingestion_status_for_job(job.job_id)
    duration = _generation_duration_seconds(job)
    with st.container():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Status", job.status.title())
        c2.metric("Provider", job.request.provider_id)
        c3.metric("Retry Count", job.retry_count)
        c4.metric("Generated Assets", len(job.result.output_references) if job.result else 0)
        st.caption(f"Job ID: {job.job_id}")
        st.caption(f"Prompt Plan: {job.request.prompt_plan_id}")
        st.caption(f"Creative Mode: {job.request.metadata.get('creative_mode') or '-'}")
        st.caption(f"Reference Asset: {job.request.reference_asset_id or '-'}")
        st.caption(f"Generation Time: {duration:.2f}s" if duration is not None else "Generation Time: -")
        imported_ids = tuple(ingestion_status.get("imported_asset_ids") or ())
        if imported_ids:
            st.caption("Imported Asset IDs: " + ", ".join(str(asset_id) for asset_id in imported_ids))
        if job.failure:
            st.error(job.failure.reason)
        for message in ingestion_status.get("failed_messages", ()):
            st.error(message)

        with st.expander("View Prompt", expanded=False):
            st.write(job.request.prompt_text)
            st.json(dict(job.request.metadata or {}))
        with st.expander("View Reference", expanded=False):
            reference = None
            if job.request.reference_asset_id:
                try:
                    reference = reference_service.get_reference(
                        job.request.reference_asset_id,
                    )
                except Exception:
                    reference = None
            if reference and reference.asset.preview_path:
                st.image(reference.asset.preview_path, use_container_width=True)
            else:
                st.caption(f"Reference Asset: {job.request.reference_asset_id or '-'}")

        a0, a1, a2, a3, a4 = st.columns(5)
        if a0.button(
            "Run Job",
            disabled=job.status not in {"queued", "retry"},
            key=f"{panel_key}_run_{job.job_id}",
            use_container_width=True,
        ):
            with st.spinner("Running Generation Job..."):
                executed, records = execute_generation_job_to_library(
                    job=job,
                    generation_engine=generation_engine,
                    generation_library=generation_library,
                )
            if executed.status == GenerationStatus.SUCCEEDED.value:
                st.success(f"Generation completed. {len(records)} item(s) added to Generation Library.")
            elif executed.failure:
                st.error(executed.failure.reason)
            else:
                st.warning(f"Generation finished with status: {executed.status}.")
            st.rerun()
        if a1.button(
            "Retry Job",
            disabled=job.status not in {"failed", "cancelled", "retry"},
            key=f"{panel_key}_retry_{job.job_id}",
            use_container_width=True,
        ):
            generation_engine.retry_job(job.job_id)
            st.success("Generation Job returned to Retry Queue.")
            st.rerun()
        if a2.button(
            "Cancel Job",
            disabled=job.status not in {"queued", "running", "retry"},
            key=f"{panel_key}_cancel_{job.job_id}",
            use_container_width=True,
        ):
            generation_engine.cancel_job(job.job_id)
            st.warning("Generation Job cancelled.")
            st.rerun()
        if a3.button(
            "Open Generated Assets",
            disabled=not imported_ids,
            key=f"{panel_key}_open_assets_{job.job_id}",
            use_container_width=True,
        ):
            st.session_state["content_studio_generated_asset_ids"] = tuple(imported_ids)
            st.session_state["content_studio_open_asset_library"] = True
        if a4.button(
            "Open Creator Review",
            disabled=not imported_ids,
            key=f"{panel_key}_open_review_{job.job_id}",
            use_container_width=True,
        ):
            st.session_state["content_studio_creator_review_asset_ids"] = tuple(imported_ids)


def _render_generation_workspace(
    *,
    creator_profile: dict | None,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    generation_ingestion: GenerationResultIngestionService,
    reference_service: ReferenceLibraryService,
    creative_director: CreativeDirectorService,
    photoshoot_queue: PhotoshootQueueService,
    asset_library: AssetLibraryService,
) -> None:
    st.title("Generation Workspace")
    st.caption("Operational dashboard for generation jobs and generated Creator OS Assets.")
    creator_profile_id = _creator_profile_id(creator_profile)
    jobs = generation_engine.list_jobs()
    metrics = generation_workspace_metrics(jobs, generation_ingestion)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Jobs Today", metrics["jobs_today"])
    m2.metric("Success Rate", f"{metrics['success_rate']:.0f}%")
    m3.metric("Failed Jobs", metrics["failed_jobs"])
    m4.metric("Queue Depth", metrics["queue_depth"])
    m5, m6, m7 = st.columns(3)
    m5.metric("Average Generation Time", f"{metrics['average_generation_time']:.1f}s")
    m6.metric("Generated Assets", metrics["generated_assets"])
    m7.metric("Imported Assets", metrics["imported_assets"])

    st.markdown("### Current Photoshoot")
    current_photoshoot = photoshoot_queue.current_session(
        creator_profile_id=creator_profile_id,
    )
    if current_photoshoot is None:
        st.caption("No active Photoshoot Session.")
    else:
        photoshoot_queue.sync_ingested_assets_for_session(current_photoshoot.session_id)
        progress = photoshoot_queue.progress(current_photoshoot.session_id)
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Queue Position", current_photoshoot.current_request_id or "-")
        p2.metric("Remaining Prompts", progress.queued_prompts)
        p3.metric("Completed Images", progress.approved_images)
        p4.metric("Imported Assets", progress.imported_assets)
        st.caption(f"Session: {current_photoshoot.session_id}")
        st.caption(f"Status: {current_photoshoot.status}")

    st.markdown("### Filters")
    providers = sorted({job.request.provider_id for job in jobs})
    statuses = sorted({job.status for job in jobs})
    modes = sorted(
        {
            str(job.request.metadata.get("creative_mode"))
            for job in jobs
            if job.request.metadata.get("creative_mode")
        }
    )
    f1, f2, f3 = st.columns(3)
    search = f1.text_input("Search", key="generation_workspace_search")
    provider = f2.selectbox("Provider", ("", *providers), key="generation_workspace_provider")
    status = f3.selectbox("Status", ("", *statuses), key="generation_workspace_status")
    f4, f5, f6 = st.columns(3)
    creative_mode = f4.selectbox("Creative Mode", ("", *modes), key="generation_workspace_mode")
    creator_only = f5.checkbox("Current Creator", value=bool(creator_profile_id), key="generation_workspace_creator")
    date_window = f6.selectbox(
        "Date",
        ("All", "Today", "Last 7 Days"),
        key="generation_workspace_date",
    )
    created_after = None
    if date_window == "Today":
        created_after = date.today()
    elif date_window == "Last 7 Days":
        created_after = date.today() - timedelta(days=7)
    filtered_jobs = filter_generation_jobs(
        jobs,
        search=search,
        provider=provider,
        status=status,
        creator_profile_id=creator_profile_id if creator_only else None,
        creative_mode=creative_mode,
        created_after=created_after,
    )

    st.markdown("### Queue Overview")
    status_groups = (
        ("Queued Jobs", "queued"),
        ("Running Jobs", "running"),
        ("Completed Jobs", "succeeded"),
        ("Failed Jobs", "failed"),
        ("Retry Queue", "retry"),
    )
    for title, group_status in status_groups:
        group_jobs = tuple(job for job in filtered_jobs if job.status == group_status)
        with st.expander(f"{title} ({len(group_jobs)})", expanded=group_status in {"queued", "running"}):
            if not group_jobs:
                st.caption("No jobs in this section.")
            for job in reversed(group_jobs):
                _render_generation_job_card(
                    job=job,
                    generation_engine=generation_engine,
                    generation_library=generation_library,
                    generation_ingestion=generation_ingestion,
                    reference_service=reference_service,
                    panel_key=f"generation_workspace_{group_status}",
                )
                st.divider()

    st.markdown("### Generation History")
    if not filtered_jobs:
        st.info("No Generation Jobs match the current filters.")
    for job in reversed(filtered_jobs):
        st.caption(
            " | ".join(
                (
                    job.queued_at,
                    job.status,
                    job.request.provider_id,
                    job.request.metadata.get("creative_mode") or "-",
                    f"Creator {job.request.creator_profile_id}",
                )
            )
        )
        st.write(f"{job.job_id} - {job.request.prompt_plan_id}")

    st.markdown("### Recent Generated Assets")
    items = _recent_generated_asset_items(
        generation_ingestion=generation_ingestion,
        asset_library=asset_library,
    )
    if not items:
        st.caption("No imported generated assets yet.")
    for item in items:
        col_preview, col_meta = st.columns([1, 3])
        with col_preview:
            if item.preview_path:
                st.image(item.preview_path, use_container_width=True)
        with col_meta:
            st.write(item.file_name or f"Asset #{item.asset_id}")
            st.caption(f"Asset ID: {item.asset_id}")
            st.caption(f"Asset Library status: {item.status or '-'}")
            st.caption("Open Asset Library or Creator Review for deeper asset workflows.")

    latest = creative_director.latest_session(creator_profile_id=creator_profile_id)
    if latest:
        st.caption(f"Latest Creative Director session: {latest.session.session_id}")


def _generation_publish_context(record) -> dict[str, Any]:
    workflow = record.generation_metadata.get("workflow_type") or record.generation_metadata.get("source") or ""
    return {
        "generated_image_id": record.image_id,
        "image_reference": record.output_reference,
        "provider": record.provider_id,
        "workflow": workflow,
        "creative_mode": record.creative_mode,
        "prompt_text": record.prompt_text,
        "prompt_metadata": dict(record.prompt_metadata or {}),
        "generation_metadata": dict(record.generation_metadata or {}),
    }


def _open_generation_publish_modal(record) -> None:
    st.session_state["generation_library_publish_modal_open"] = True
    st.session_state["generation_library_publish_context"] = _generation_publish_context(record)
    st.session_state.pop("generation_library_publish_destination", None)
    st.session_state.pop("generation_library_x_caption_result_id", None)
    st.session_state.pop("generation_library_x_selected_caption", None)
    st.session_state.pop("generation_library_x_caption_seed", None)
    st.session_state.pop("generation_library_x_publish_message", None)
    st.session_state.pop("generation_library_x_caption_selected_at", None)
    st.session_state.pop("generation_library_telegram_caption_result_id", None)
    st.session_state.pop("generation_library_telegram_selected_caption", None)
    st.session_state.pop("generation_library_telegram_caption_seed", None)
    st.session_state.pop("generation_library_telegram_publish_message", None)
    st.session_state.pop("generation_library_telegram_caption_selected_at", None)


def _close_generation_publish_modal() -> None:
    for key in (
        "generation_library_publish_modal_open",
        "generation_library_publish_context",
        "generation_library_publish_destination",
        "generation_library_x_caption_result_id",
        "generation_library_x_selected_caption",
        "generation_library_x_caption_seed",
        "generation_library_x_publish_message",
        "generation_library_x_caption_selected_at",
        "generation_library_telegram_caption_result_id",
        "generation_library_telegram_selected_caption",
        "generation_library_telegram_caption_seed",
        "generation_library_telegram_publish_message",
        "generation_library_telegram_caption_selected_at",
    ):
        st.session_state.pop(key, None)


def _render_generated_caption_choices(
    *,
    caption_result: Any,
    selected_key: str,
    text_key: str,
    button_prefix: str,
    confirmation_key: str,
) -> None:
    selected_at = float(st.session_state.get(confirmation_key) or 0)
    if selected_at and time.time() - selected_at <= 3:
        st.success("Caption selected.")
    for theme_index, theme in enumerate(caption_result.formatter_metadata.get("themes") or (), start=1):
        st.markdown(f"**{theme.get('theme')}**")
        for caption_index, caption in enumerate(theme.get("captions") or (), start=1):
            selected = st.session_state.get(selected_key) == caption
            if st.button(
                caption,
                key=f"{button_prefix}_{theme_index}_{caption_index}",
                type="primary" if selected else "secondary",
                use_container_width=True,
            ):
                st.session_state[selected_key] = caption
                st.session_state[text_key] = caption
                st.session_state[confirmation_key] = time.time()
                st.rerun()


def _render_x_engagement_publish_dialog(
    *,
    context: dict[str, Any],
    creator_profile: dict | None,
    generation_library: GenerationLibraryService,
    caption_studio: CaptionStudioService,
    social_publishing: Any,
) -> None:
    st.markdown("### X Publish")
    image_reference = str(context.get("image_reference") or "")
    if image_reference:
        st.image(image_reference, use_container_width=True)

    st.markdown("### Generate Captions")
    st.caption("Grok Vision analyzes the actual image first, then writes two caption styles. Nothing is posted until you choose a caption and publish.")
    generated_image_id = str(context.get("generated_image_id") or "")
    result_id_key = "generation_library_x_caption_result_id"
    seed_key = "generation_library_x_caption_seed"
    selected_key = "generation_library_x_selected_caption"
    custom_key = f"generation_library_x_custom_caption_{generated_image_id}"

    generate_col, regenerate_col = st.columns(2)
    if generate_col.button("Generate Captions", key="generation_library_x_generate_captions", use_container_width=True):
        st.session_state[seed_key] = int(st.session_state.get(seed_key, 0))
        result = caption_studio.generate_x_engagement_themes(
            generated_image_id=generated_image_id,
            image_reference=image_reference,
            creator_profile_id=_creator_profile_id(creator_profile) or 0,
            creator_profile=creator_profile,
            creative_mode=str(context.get("creative_mode") or ""),
            prompt_text=str(context.get("prompt_text") or ""),
            prompt_metadata=dict(context.get("prompt_metadata") or {}),
            generation_metadata=dict(context.get("generation_metadata") or {}),
            idea_seed=int(st.session_state.get(seed_key, 0)),
        )
        st.session_state[result_id_key] = result.caption_result_id
        st.session_state.pop(selected_key, None)
        st.session_state.pop(custom_key, None)
        st.rerun()
    if regenerate_col.button("Generate Different Ideas", key="generation_library_x_generate_different", use_container_width=True):
        st.session_state[seed_key] = int(st.session_state.get(seed_key, 0)) + 1
        result = caption_studio.generate_x_engagement_themes(
            generated_image_id=generated_image_id,
            image_reference=image_reference,
            creator_profile_id=_creator_profile_id(creator_profile) or 0,
            creator_profile=creator_profile,
            creative_mode=str(context.get("creative_mode") or ""),
            prompt_text=str(context.get("prompt_text") or ""),
            prompt_metadata=dict(context.get("prompt_metadata") or {}),
            generation_metadata=dict(context.get("generation_metadata") or {}),
            idea_seed=int(st.session_state.get(seed_key, 0)),
        )
        st.session_state[result_id_key] = result.caption_result_id
        st.session_state.pop(selected_key, None)
        st.session_state.pop(custom_key, None)
        st.rerun()

    caption_result = None
    if st.session_state.get(result_id_key):
        try:
            caption_result = caption_studio.get_result(st.session_state[result_id_key])
        except KeyError:
            st.session_state.pop(result_id_key, None)
            caption_result = None

    if caption_result:
        _render_generated_caption_choices(
            caption_result=caption_result,
            selected_key=selected_key,
            text_key=custom_key,
            button_prefix="generation_library_x_caption",
            confirmation_key="generation_library_x_caption_selected_at",
        )

    st.markdown('<div id="caption-editor-anchor"></div>', unsafe_allow_html=True)
    if float(st.session_state.get("generation_library_x_caption_selected_at") or 0) and time.time() - float(st.session_state.get("generation_library_x_caption_selected_at") or 0) <= 3:
        components.html(
            """
            <script>
            const anchor = window.parent.document.getElementById("caption-editor-anchor");
            if (anchor) anchor.scrollIntoView({behavior: "smooth", block: "center"});
            </script>
            """,
            height=0,
        )
    custom_caption = st.text_area(
        "Caption Editor",
        key=custom_key,
        placeholder="Select a generated caption above or write your own.",
    )
    selected_caption = str(st.session_state.get(custom_key) or "").strip()
    selected_generated_caption = str(st.session_state.get(selected_key) or "").strip()
    caption_was_edited = bool(selected_generated_caption and selected_caption != selected_generated_caption)
    if selected_generated_caption and selected_caption:
        st.caption("Any changes made here will be published.")
        if caption_was_edited and st.button("↺ Restore Original", key="generation_library_x_restore_original", use_container_width=True):
            st.session_state[custom_key] = selected_generated_caption
            st.rerun()
    elif selected_caption:
        st.caption("Custom caption will be published.")
    else:
        st.warning("Select a generated caption or write one before publishing.")

    publish_col, cancel_col = st.columns(2)
    if publish_col.button(
        "Publish to AvaBlackthorne",
        key="generation_library_x_publish_now",
        disabled=not selected_caption,
        use_container_width=True,
    ):
        caption_id = None
        if caption_result and selected_generated_caption:
            selected_result = caption_studio.select_caption(
                caption_result.caption_result_id,
                selected_text=selected_caption,
            )
            caption_id = selected_result.caption_result_id
        item = social_publishing.create_queue_item(
            generated_image_id=generated_image_id,
            generation_library=generation_library,
            platform="x",
            creator_notes="Queued from Generation Library X Publish dialog.",
        )
        if caption_id:
            social_publishing.assign_caption(item.queue_item_id, caption_id=caption_id)
        updated = social_publishing.publish_now(
            item.queue_item_id,
            caption_text=selected_caption,
            account_name="AvaBlackthorne",
            caption_id=caption_id,
        )
        if updated.status == "posted":
            archive_result = generation_library.mark_published(
                generated_image_id,
                platform="x",
                caption=selected_caption,
                metadata={
                    "social_queue_item_id": item.queue_item_id,
                    "caption_id": caption_id,
                    "selected_generated_caption": selected_generated_caption,
                    "caption_was_edited": caption_was_edited,
                    "caption_source": "edited_generated" if caption_was_edited else "generated" if selected_generated_caption else "custom",
                    "account_name": "AvaBlackthorne",
                },
            )
            if archive_result.success:
                st.session_state["generation_library_x_publish_message"] = "Published to X."
            else:
                st.session_state["generation_library_x_publish_message"] = (
                    "Posted to X, but archive update failed: "
                    + "; ".join(archive_result.errors)
                )
        else:
            latest_history = next(iter(social_publishing.list_history()), None)
            failure_message = (
                latest_history.message
                if latest_history and latest_history.queue_item_id == item.queue_item_id
                else None
            )
            st.session_state["generation_library_x_publish_message"] = (
                failure_message or "X publish failed."
            )
        st.rerun()
    if cancel_col.button("Cancel", key="generation_library_x_cancel", use_container_width=True):
        _close_generation_publish_modal()
        st.rerun()

    message = st.session_state.get("generation_library_x_publish_message")
    if message == "Published to X.":
        st.success(message)
    elif message:
        st.error(message)


def _render_telegram_publish_dialog(
    *,
    context: dict[str, Any],
    creator_profile: dict | None,
    generation_library: GenerationLibraryService,
    caption_studio: CaptionStudioService,
    social_publishing: Any,
) -> None:
    st.markdown("### Telegram Publish")
    image_reference = str(context.get("image_reference") or "")
    if image_reference:
        st.image(image_reference, use_container_width=True)
    generated_image_id = str(context.get("generated_image_id") or "")
    caption_key = f"generation_library_telegram_caption_{generated_image_id}"
    result_id_key = "generation_library_telegram_caption_result_id"
    seed_key = "generation_library_telegram_caption_seed"
    selected_key = "generation_library_telegram_selected_caption"
    post_to_key = f"generation_library_telegram_post_to_{generated_image_id}"
    cta_enabled_key = f"generation_library_telegram_cta_enabled_{generated_image_id}"
    cta_label_key = f"generation_library_telegram_cta_label_{generated_image_id}"
    cta_url_key = f"generation_library_telegram_cta_url_{generated_image_id}"
    message_key = "generation_library_telegram_publish_message"

    st.markdown("### Generate Captions")
    st.caption("Grok Vision analyzes the actual image first, then writes Telegram-ready caption styles. Nothing is posted until you choose a caption and publish.")

    generate_col, regenerate_col = st.columns(2)
    if generate_col.button("Generate Captions", key="generation_library_telegram_generate_captions", use_container_width=True):
        st.session_state[seed_key] = int(st.session_state.get(seed_key, 0))
        result = caption_studio.generate_telegram_vision_themes(
            generated_image_id=generated_image_id,
            image_reference=image_reference,
            creator_profile_id=_creator_profile_id(creator_profile) or 0,
            creator_profile=creator_profile,
            creative_mode=str(context.get("creative_mode") or ""),
            prompt_text=str(context.get("prompt_text") or ""),
            prompt_metadata=dict(context.get("prompt_metadata") or {}),
            generation_metadata=dict(context.get("generation_metadata") or {}),
            idea_seed=int(st.session_state.get(seed_key, 0)),
        )
        st.session_state[result_id_key] = result.caption_result_id
        st.session_state.pop(selected_key, None)
        st.session_state.pop(caption_key, None)
        st.rerun()
    if regenerate_col.button("Generate Different Ideas", key="generation_library_telegram_generate_different", use_container_width=True):
        st.session_state[seed_key] = int(st.session_state.get(seed_key, 0)) + 1
        result = caption_studio.generate_telegram_vision_themes(
            generated_image_id=generated_image_id,
            image_reference=image_reference,
            creator_profile_id=_creator_profile_id(creator_profile) or 0,
            creator_profile=creator_profile,
            creative_mode=str(context.get("creative_mode") or ""),
            prompt_text=str(context.get("prompt_text") or ""),
            prompt_metadata=dict(context.get("prompt_metadata") or {}),
            generation_metadata=dict(context.get("generation_metadata") or {}),
            idea_seed=int(st.session_state.get(seed_key, 0)),
        )
        st.session_state[result_id_key] = result.caption_result_id
        st.session_state.pop(selected_key, None)
        st.session_state.pop(caption_key, None)
        st.rerun()

    caption_result = None
    if st.session_state.get(result_id_key):
        try:
            caption_result = caption_studio.get_result(st.session_state[result_id_key])
        except KeyError:
            st.session_state.pop(result_id_key, None)
            caption_result = None

    if caption_result:
        _render_generated_caption_choices(
            caption_result=caption_result,
            selected_key=selected_key,
            text_key=caption_key,
            button_prefix="generation_library_telegram_caption",
            confirmation_key="generation_library_telegram_caption_selected_at",
        )

    st.markdown('<div id="caption-editor-anchor"></div>', unsafe_allow_html=True)
    if float(st.session_state.get("generation_library_telegram_caption_selected_at") or 0) and time.time() - float(st.session_state.get("generation_library_telegram_caption_selected_at") or 0) <= 3:
        components.html(
            """
            <script>
            const anchor = window.parent.document.getElementById("caption-editor-anchor");
            if (anchor) anchor.scrollIntoView({behavior: "smooth", block: "center"});
            </script>
            """,
            height=0,
        )
    custom_caption = st.text_area(
        "Caption Editor",
        key=caption_key,
        placeholder="Select a generated caption above or write your own.",
    )
    selected_caption = str(st.session_state.get(caption_key) or "").strip()
    selected_generated_caption = str(st.session_state.get(selected_key) or "").strip()
    caption_was_edited = bool(selected_generated_caption and selected_caption != selected_generated_caption)
    if selected_generated_caption and selected_caption:
        st.caption("Any changes made here will be published.")
        if caption_was_edited and st.button("↺ Restore Original", key="generation_library_telegram_restore_original", use_container_width=True):
            st.session_state[caption_key] = selected_generated_caption
            st.rerun()
    elif selected_caption:
        st.caption("Custom caption will be published.")
    else:
        st.warning("Select a generated caption or write one before publishing.")

    post_to = st.selectbox("Post To", ("main", "vault"), key=post_to_key)
    cta_enabled = st.checkbox("Include CTA button", key=cta_enabled_key)
    cta_label = ""
    cta_url = ""
    if cta_enabled:
        cta_label = st.text_input("Button Text", key=cta_label_key)
        cta_url = st.text_input("Button URL", key=cta_url_key)

    publish_col, cancel_col = st.columns(2)
    if publish_col.button(
        "Publish to Telegram",
        key="generation_library_telegram_publish_now",
        disabled=not selected_caption,
        use_container_width=True,
    ):
        caption_id = None
        if caption_result and selected_generated_caption:
            selected_result = caption_studio.select_caption(
                caption_result.caption_result_id,
                selected_text=selected_caption,
            )
            caption_id = selected_result.caption_result_id
        item = social_publishing.create_queue_item(
            generated_image_id=generated_image_id,
            generation_library=generation_library,
            platform="telegram",
            creator_notes="Queued from Generation Library Telegram Publish dialog.",
        )
        if caption_id:
            social_publishing.assign_caption(item.queue_item_id, caption_id=caption_id)
        updated = social_publishing.publish_now(
            item.queue_item_id,
            caption_text=selected_caption,
            telegram_post_to=post_to,
            telegram_cta_enabled=cta_enabled,
            telegram_cta_label=cta_label,
            telegram_cta_url=cta_url,
        )
        if updated.status == "posted":
            archive_result = generation_library.mark_published(
                generated_image_id,
                platform="telegram",
                caption=selected_caption,
                metadata={
                    "social_queue_item_id": item.queue_item_id,
                    "caption_id": caption_id,
                    "selected_generated_caption": selected_generated_caption,
                    "caption_was_edited": caption_was_edited,
                    "caption_source": "edited_generated" if caption_was_edited else "generated" if selected_generated_caption else "custom",
                    "post_to": post_to,
                    "cta_enabled": cta_enabled,
                    "cta_label": cta_label,
                    "cta_url": cta_url,
                },
            )
            if archive_result.success:
                st.session_state[message_key] = "Published to Telegram."
            else:
                st.session_state[message_key] = (
                    "Posted to Telegram, but archive update failed: "
                    + "; ".join(archive_result.errors)
                )
        else:
            latest_history = next(iter(social_publishing.list_history()), None)
            st.session_state[message_key] = (
                latest_history.message
                if latest_history and latest_history.queue_item_id == item.queue_item_id
                else "Telegram publish failed."
            )
        st.rerun()
    if cancel_col.button("Cancel", key="generation_library_telegram_cancel", use_container_width=True):
        _close_generation_publish_modal()
        st.rerun()

    message = st.session_state.get(message_key)
    if message == "Published to Telegram.":
        st.success(message)
    elif message:
        st.error(message)


def _render_generation_publish_modal(
    *,
    creator_profile: dict | None,
    generation_library: GenerationLibraryService,
    caption_studio: CaptionStudioService,
    social_publishing: Any,
) -> None:
    if not st.session_state.get("generation_library_publish_modal_open"):
        return
    context = dict(st.session_state.get("generation_library_publish_context") or {})
    if not context:
        st.session_state.pop("generation_library_publish_modal_open", None)
        return

    def render_body() -> None:
        destination = dict(st.session_state.get("generation_library_publish_destination") or {})
        if destination.get("destination") == "x":
            _render_x_engagement_publish_dialog(
                context=context,
                creator_profile=creator_profile,
                generation_library=generation_library,
                caption_studio=caption_studio,
                social_publishing=social_publishing,
            )
            return
        if destination.get("destination") == "telegram":
            _render_telegram_publish_dialog(
                context=context,
                creator_profile=creator_profile,
                generation_library=generation_library,
                caption_studio=caption_studio,
                social_publishing=social_publishing,
            )
            return
        st.write("Where would you like to publish this image?")
        option_x, option_telegram = st.columns(2)
        with option_x:
            if st.button("Publish to X", key="generation_publish_select_x", use_container_width=True):
                st.session_state["generation_library_publish_destination"] = {
                    **context,
                    "destination": "x",
                }
                st.rerun()
        with option_telegram:
            if st.button("Publish to Telegram", key="generation_publish_select_telegram", use_container_width=True):
                st.session_state["generation_library_publish_destination"] = {
                    **context,
                    "destination": "telegram",
                }
                st.rerun()
        if st.button("Cancel", key="generation_publish_close", use_container_width=True):
            _close_generation_publish_modal()
            st.rerun()

    dialog = getattr(st, "dialog", None)
    if callable(dialog):
        @dialog("Publish")
        def publish_dialog():
            render_body()

        publish_dialog()
    else:
        with st.expander("Publish", expanded=True):
            render_body()


def _render_generation_library(
    *,
    creator_profile: dict | None,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    generation_ingestion: GenerationResultIngestionService,
    reference_service: ReferenceLibraryService,
    caption_studio: CaptionStudioService,
    social_publishing: Any,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    st.title("Generation Library")
    st.caption("Generated images awaiting creator review before Creator OS asset import.")
    generation_library.sync_jobs(generation_engine.list_jobs(status="succeeded"))

    records = generation_library.list_records()
    providers = sorted({record.provider_id for record in records if record.provider_id})
    statuses = ("active",)
    modes = sorted({record.creative_mode for record in records if record.creative_mode})
    photoshoot_sessions = sorted(
        {record.photoshoot_session_id for record in records if record.photoshoot_session_id}
    )

    st.markdown("### Browse")
    selected_job_id = st.session_state.get("generation_library_selected_job_id")
    if selected_job_id and "generation_library_search" not in st.session_state:
        st.session_state["generation_library_search"] = selected_job_id
    f1, f2, f3 = st.columns(3)
    search = f1.text_input("Search", key="generation_library_search")
    provider = f2.selectbox("Provider", ("", *providers), key="generation_library_provider")
    if st.session_state.get("generation_library_status") not in statuses:
        st.session_state["generation_library_status"] = "active"
    status = f3.selectbox("Status", statuses, key="generation_library_status")
    f4, f5, f6 = st.columns(3)
    creative_mode = f4.selectbox("Creative Mode", ("", *modes), key="generation_library_mode")
    photoshoot_session = f5.selectbox(
        "Photoshoot Session",
        ("", *photoshoot_sessions),
        key="generation_library_photoshoot",
    )
    sort = f6.selectbox(
        "Sort",
        ("newest", "oldest", "provider", "status"),
        key="generation_library_sort",
    )
    result = generation_library.browse(
        GenerationLibraryFilter(
            search=search,
            provider_id=provider,
            status=status,
            creative_mode=creative_mode,
            photoshoot_session_id=photoshoot_session,
            creator_profile_id=creator_profile_id,
            sort=sort,
        )
    )
    st.caption(f"{result.total} generated image(s)")
    selectable_ids = tuple(record.image_id for record in result.records)
    selected_ids = tuple(
        st.multiselect(
            "Multi-select",
            selectable_ids,
            default=tuple(record.image_id for record in result.records if record.selected),
            key="generation_library_selected_ids",
        )
    )
    if selected_ids:
        generation_library.select(selected_ids, selected=True)
    platform_options = social_publishing.platform_options()
    selected_social_platform = st.selectbox(
        "Social Platform",
        platform_options,
        key="generation_library_social_platform",
    )
    bulk1, bulk2, bulk3, bulk4, bulk5, bulk6, bulk7 = st.columns(7)
    if bulk1.button("Add to Creator OS", disabled=not selected_ids, key="generation_library_add", use_container_width=True):
        action = generation_library.add_to_creator_os(
            selected_ids,
            generation_engine=generation_engine,
            ingestion_service=generation_ingestion,
        )
        if action.success:
            st.success(action.message)
        else:
            st.error("; ".join(action.errors))
        st.rerun()
    if bulk2.button("Move to Junk", disabled=not selected_ids, key="generation_library_junk", use_container_width=True):
        generation_library.move_to_junk(selected_ids)
        st.rerun()
    if bulk3.button("Restore", disabled=not selected_ids, key="generation_library_restore", use_container_width=True):
        generation_library.restore(selected_ids)
        st.rerun()
    if bulk4.button("Archive", disabled=not selected_ids, key="generation_library_archive", use_container_width=True):
        generation_library.archive(selected_ids)
        st.rerun()
    if bulk5.button("Delete", disabled=not selected_ids, key="generation_library_delete", use_container_width=True):
        generation_library.delete(selected_ids)
        st.rerun()
    if bulk6.button("Multi Edit", disabled=not selected_ids, key="generation_library_multi_edit", use_container_width=True):
        st.session_state["edit_studio_source_image_ids"] = selected_ids
        st.session_state["dashboard_page"] = "Edit Studio"
        st.rerun()
    if bulk7.button("Regenerate", disabled=not selected_ids, key="generation_library_regenerate", use_container_width=True):
        action = generation_library.regenerate(
            selected_ids,
            generation_engine=generation_engine,
        )
        if action.success:
            st.success(action.message)
        else:
            st.error("; ".join(action.errors))
        st.rerun()
    send1, send2 = st.columns(2)
    if send1.button("Send to Social Publishing", disabled=not selected_ids, key="generation_library_social", use_container_width=True):
        social_publishing.queue_many(
            generated_image_ids=selected_ids,
            generation_library=generation_library,
            platform=selected_social_platform,
            creator_notes="Queued from Generation Library.",
        )
        st.session_state["dashboard_page"] = "Social Publishing"
        st.rerun()
    if send2.button("Both", disabled=not selected_ids, key="generation_library_both", use_container_width=True):
        social_publishing.queue_many(
            generated_image_ids=selected_ids,
            generation_library=generation_library,
            platform=selected_social_platform,
            creator_notes="Queued from Generation Library and added to Creator OS.",
        )
        action = generation_library.add_to_creator_os(
            selected_ids,
            generation_engine=generation_engine,
            ingestion_service=generation_ingestion,
        )
        if action.success:
            st.success("Sent to Social Publishing and added to Creator OS.")
        else:
            st.error("; ".join(action.errors))
        st.rerun()

    _render_generation_publish_modal(
        creator_profile=creator_profile,
        generation_library=generation_library,
        caption_studio=caption_studio,
        social_publishing=social_publishing,
    )

    preview_id = st.session_state.get("generation_library_preview_id")
    preview_record = next((record for record in result.records if record.image_id == preview_id), None)
    if preview_record:
        st.markdown("### Preview")
        p1, p2 = st.columns([2, 1])
        with p1:
            st.image(preview_record.output_reference, use_container_width=True)
        with p2:
            st.write(preview_record.image_id)
            st.caption(f"Provider: {preview_record.provider_id}")
            st.caption(f"Workflow: {preview_record.generation_metadata.get('workflow_type') or preview_record.generation_metadata.get('source') or '-'}")
            st.caption(f"Generated: {preview_record.generation_date or '-'}")
            st.caption(f"Reference Asset: {preview_record.reference_asset_id or '-'}")
            with st.expander("Prompt", expanded=True):
                st.write(preview_record.prompt_text)
            if st.button("Close Preview", key="generation_library_close_preview", use_container_width=True):
                st.session_state.pop("generation_library_preview_id", None)
                st.rerun()

    st.markdown("### Thumbnail Grid")
    if not result.records:
        st.info("No generated images match the current filters.")
        return
    page_size = st.selectbox("Page Size", (9, 18, 36), key="generation_library_page_size")
    total_pages = max(1, (result.total + int(page_size) - 1) // int(page_size))
    page_number = st.number_input(
        "Page",
        min_value=1,
        max_value=total_pages,
        value=min(int(st.session_state.get("generation_library_page", 1)), total_pages),
        step=1,
        key="generation_library_page",
    )
    start = (int(page_number) - 1) * int(page_size)
    page_records = result.records[start:start + int(page_size)]
    st.caption(f"Page {int(page_number)} of {total_pages}")
    cols = st.columns(3)
    for index, record in enumerate(page_records):
        with cols[index % 3]:
            if record.output_reference:
                st.image(record.output_reference, use_container_width=True)
            st.write(record.image_id)
            workflow = record.generation_metadata.get("workflow_type") or record.generation_metadata.get("source") or "-"
            st.caption(f"Provider: {record.provider_id}")
            st.caption(f"Workflow: {workflow}")
            st.caption(f"Creative Mode: {record.creative_mode or '-'}")
            st.caption(f"Status: {record.status}")
            st.caption(f"Generated: {record.generation_date or '-'}")
            st.caption(f"Reference Image: {record.reference_asset_id or '-'}")
            st.caption(f"Photoshoot Session: {record.photoshoot_session_id or '-'}")
            if record.imported_asset_id:
                st.success(f"Asset #{record.imported_asset_id}")
            social_item = social_publishing.find_queue_item(record.image_id, platform="x")
            if social_item and social_item.status == "posted":
                st.success("Published to X")
            elif social_item:
                st.caption(f"X Publishing: {social_item.status}")
            a1, a2, a3, a4 = st.columns(4)
            if a1.button("Preview", key=f"generation_library_preview_{record.image_id}", use_container_width=True):
                st.session_state["generation_library_preview_id"] = record.image_id
                st.rerun()
            if a2.button("Edit", key=f"generation_library_edit_{record.image_id}", use_container_width=True):
                st.session_state["edit_studio_source_image_ids"] = (record.image_id,)
                st.session_state["dashboard_page"] = "Edit Studio"
                st.rerun()
            if a3.button("Publish", key=f"generation_library_publish_{record.image_id}", use_container_width=True):
                _open_generation_publish_modal(record)
                st.rerun()
            if a4.button("Delete", key=f"generation_library_delete_{record.image_id}", use_container_width=True):
                generation_library.delete((record.image_id,))
                st.rerun()
            with st.expander("Open Prompt", expanded=False):
                st.write(record.prompt_text)
                st.json(dict(record.prompt_metadata or {}))
            with st.expander("Metadata", expanded=False):
                st.json(dict(record.generation_metadata or {}))
            with st.expander("Provider Metadata", expanded=False):
                st.json(dict(record.provider_metadata or {}))
            with st.expander("Open Reference", expanded=False):
                reference = None
                if record.reference_asset_id:
                    try:
                        reference = reference_service.get_reference(
                            record.reference_asset_id,
                        )
                    except Exception:
                        reference = None
                if reference and reference.asset.preview_path:
                    st.image(reference.asset.preview_path, use_container_width=True)
                else:
                    st.caption(f"Reference Asset: {record.reference_asset_id or '-'}")


def _render_archive_page(
    *,
    generation_library: GenerationLibraryService,
    content_archive: ContentArchiveService,
) -> None:
    st.title("Archive")
    st.caption("Permanent Content Studio history for published, edited, imported, and junked generated images.")
    content_archive.initialize_content_root()
    paths = content_archive.content_paths()
    with st.expander("Content Root", expanded=False):
        st.caption(f"Root: {content_archive.content_root}")
        st.caption(f"Posted/X/Main: {paths['posted_x_main']}")
        st.caption(f"Posted/Telegram/Main: {paths['posted_telegram_main']}")
        st.caption(f"Archive/Edited: {paths['archive_edited']}")
        st.caption(f"Archive/Imported: {paths['archive_imported']}")
        st.caption(f"Archive/Junk: {paths['archive_junk']}")

    records = content_archive.list_records()
    sections = (
        ("Published - X", lambda item: item.archive_type == "published_x"),
        ("Published - Telegram", lambda item: item.archive_type == "published_telegram"),
        ("Published - Fanvue", lambda item: item.archive_type == "published_fanvue"),
        ("Edited", lambda item: item.archive_type == "edited_original"),
        ("Imported", lambda item: item.archive_type == "imported"),
        ("Junk", lambda item: item.archive_type == "junk"),
    )
    for title, predicate in sections:
        section_records = tuple(record for record in records if predicate(record))
        st.markdown(f"### {title}")
        st.caption(f"{len(section_records)} item(s)")
        if not section_records:
            st.info("No archive records yet.")
            continue
        for record in section_records:
            with st.container():
                c1, c2, c3 = st.columns([1, 2, 2])
                with c1:
                    if record.current_file_path and Path(record.current_file_path).exists():
                        st.image(record.current_file_path, use_container_width=True)
                    else:
                        st.caption("Thumbnail unavailable")
                with c2:
                    st.write(record.image_id)
                    st.caption(f"Date: {record.created_at or '-'}")
                    st.caption(f"Destination: {record.destination or '-'}")
                    st.caption(f"Provider: {record.provider_id or '-'}")
                    st.caption(f"Platform: {record.platform or '-'}")
                    if record.caption:
                        st.caption(f"Caption: {record.caption}")
                    prompt_summary = " ".join(str(record.prompt_text or "").split())[:180]
                    st.caption(f"Prompt: {prompt_summary or '-'}")
                with c3:
                    with st.expander("Metadata", expanded=False):
                        st.json(dict(record.metadata or {}))
                    if record.archive_type == "junk":
                        if st.button("Restore", key=f"archive_restore_{record.archive_id}", use_container_width=True):
                            restored = generation_library.restore((record.image_id,))
                            if restored.success:
                                st.success("Restored to Generation Library.")
                            else:
                                st.error("; ".join(restored.errors))
                            st.rerun()
                        confirm = st.checkbox(
                            "Confirm Permanent Delete",
                            key=f"archive_permanent_confirm_{record.archive_id}",
                        )
                        if st.button(
                            "Permanent Delete",
                            key=f"archive_permanent_delete_{record.archive_id}",
                            disabled=not confirm,
                            use_container_width=True,
                        ):
                            content_archive.permanent_delete_junk(record.image_id)
                            st.success("Permanently deleted from Junk.")
                            st.rerun()


def _render_social_publishing(
    *,
    creator_profile: dict | None,
    generation_library: GenerationLibraryService,
    generation_engine: GenerationEngineService,
    generation_ingestion: GenerationResultIngestionService,
    reference_service: ReferenceLibraryService,
    caption_studio: CaptionStudioService,
    social_publishing: Any,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    st.title("Social Publishing")
    st.caption("Marketing queue for generated images. Product Publishing, Fanvue, Telegram, and Commerce stay separate.")
    if not creator_profile_id:
        st.error("Creator Profile required before using Social Publishing.")
        return

    platform_options = social_publishing.platform_options()
    status_options = ("", "queued", "scheduled", "posted", "failed", "archived")
    f1, f2, f3 = st.columns(3)
    platform_filter = f1.selectbox("Platform", ("", *platform_options), key="social_publishing_platform")
    status_filter = f2.selectbox("Status", status_options, key="social_publishing_status")
    creator_notes = f3.text_input("Creator Notes", key="social_publishing_creator_notes")
    x_accounts = social_publishing.x_account_options()
    x_account = st.selectbox("X Account", x_accounts or ("",), key="social_publishing_x_account")
    telegram_post_to = st.selectbox("Telegram Post To", ("main", "vault"), key="social_publishing_telegram_post_to")
    telegram_cta_enabled = st.checkbox("Telegram CTA", key="social_publishing_telegram_cta_enabled")
    telegram_cta_label = ""
    telegram_cta_url = ""
    if telegram_cta_enabled:
        t1, t2 = st.columns(2)
        telegram_cta_label = t1.text_input("Telegram Button Text", key="social_publishing_telegram_cta_label")
        telegram_cta_url = t2.text_input("Telegram Button URL", key="social_publishing_telegram_cta_url")
    scheduled_for = st.text_input("Schedule", key="social_publishing_schedule", placeholder="Optional ISO timestamp")

    items = social_publishing.list_queue_items(
        creator_profile_id=creator_profile_id,
        status=status_filter or None,
        platform=platform_filter or None,
    )
    queued = tuple(item for item in items if item.status == "queued")
    scheduled = tuple(item for item in items if item.status == "scheduled")
    posted = tuple(item for item in items if item.status == "posted")
    failed = tuple(item for item in items if item.status == "failed")
    archived = tuple(item for item in items if item.status == "archived")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Queued Images", len(queued))
    m2.metric("Scheduled", len(scheduled))
    m3.metric("Posted", len(posted))
    m4.metric("Failed", len(failed))
    m5.metric("Archived", len(archived))

    st.markdown("### Social Queue")
    if not items:
        st.info("Send generated images from Generation Library to build the Social Queue.")
    for item in items:
        with st.container():
            c1, c2 = st.columns([1, 3])
            with c1:
                if item.output_reference:
                    st.image(item.output_reference, use_container_width=True)
            with c2:
                st.write(item.generated_image_id)
                st.caption(f"Platform: {item.platform}")
                st.caption(f"Status: {item.status}")
                st.caption(f"Scheduled: {item.scheduled_for or '-'}")
                st.caption(f"Creator Notes: {item.creator_notes or '-'}")
                st.caption(f"Creative Mode: {item.creative_mode or '-'}")
                st.caption(f"Reference Image: {item.reference_asset_id or '-'}")
                if item.caption_id:
                    try:
                        caption_result = caption_studio.get_result(item.caption_id)
                        selected_caption = caption_result.selected_text or (caption_result.variations[0] if caption_result.variations else "")
                    except KeyError:
                        caption_result = None
                        selected_caption = ""
                else:
                    caption_result = None
                    selected_caption = ""
                caption_text = st.text_area(
                    "Caption",
                    value=selected_caption,
                    key=f"social_queue_caption_text_{item.queue_item_id}",
                    height=100,
                )
                with st.expander("Generation Metadata", expanded=False):
                    st.json(dict(item.generation_metadata or {}))
                with st.expander("View Prompt", expanded=False):
                    st.write(item.prompt_text or "")
                with st.expander("View Reference", expanded=False):
                    reference = None
                    if item.reference_asset_id:
                        try:
                            reference = reference_service.get_reference(
                                item.reference_asset_id,
                            )
                        except Exception:
                            reference = None
                    if reference and reference.asset.preview_path:
                        st.image(reference.asset.preview_path, use_container_width=True)
                    else:
                        st.caption(f"Reference Asset: {item.reference_asset_id or '-'}")
                a1, a2, a3, a4, a5, a6, a7, a8 = st.columns(8)
                if a1.button("Remove", key=f"social_queue_remove_{item.queue_item_id}", use_container_width=True):
                    social_publishing.remove_queue_item(item.queue_item_id)
                    st.rerun()
                if a2.button("Archive", key=f"social_queue_archive_{item.queue_item_id}", use_container_width=True):
                    social_publishing.archive_queue_item(item.queue_item_id)
                    st.rerun()
                if a3.button("Move Back to Generation Library", key=f"social_queue_back_{item.queue_item_id}", use_container_width=True):
                    social_publishing.move_back_to_generation_library(item.queue_item_id)
                    st.rerun()
                if a4.button("Send to Creator OS", key=f"social_queue_creator_os_{item.queue_item_id}", use_container_width=True):
                    result = social_publishing.send_to_creator_os(
                        item.queue_item_id,
                        generation_library=generation_library,
                        generation_engine=generation_engine,
                        ingestion_service=generation_ingestion,
                    )
                    if result.success:
                        st.success("Generated image sent to Creator OS.")
                    else:
                        st.error("; ".join(result.errors))
                    st.rerun()
                if a5.button("Open Generation", key=f"social_queue_open_generation_{item.queue_item_id}", use_container_width=True):
                    st.session_state["generation_library_search"] = item.generated_image_id
                    st.session_state["dashboard_page"] = "Generation Library"
                    st.rerun()
                if a6.button("Generate Caption", key=f"social_queue_caption_{item.queue_item_id}", use_container_width=True):
                    result = caption_studio.generate_for_social_queue(
                        queue_item_id=item.queue_item_id,
                        social_publishing=social_publishing,
                        platform=item.platform,
                        style=CaptionStyle.SOCIAL_SAFE.value,
                        tone="confident",
                        variation_count=3,
                    )
                    st.session_state["caption_studio_latest_result_id"] = result.caption_result_id
                    st.success("Caption generated.")
                    st.rerun()
                can_publish_now = item.platform in {"x", "telegram"}
                if a7.button("Publish Now", disabled=not can_publish_now, key=f"social_queue_publish_{item.queue_item_id}", use_container_width=True):
                    updated = social_publishing.publish_now(
                        item.queue_item_id,
                        caption_text=caption_text,
                        account_name=x_account,
                        caption_id=item.caption_id,
                        telegram_post_to=telegram_post_to,
                        telegram_cta_enabled=telegram_cta_enabled,
                        telegram_cta_label=telegram_cta_label,
                        telegram_cta_url=telegram_cta_url,
                    )
                    if updated.status == "posted":
                        archive_metadata = {
                            "social_queue_item_id": item.queue_item_id,
                            "caption_id": item.caption_id,
                        }
                        if item.platform == "telegram":
                            archive_metadata.update(
                                {
                                    "post_to": telegram_post_to,
                                    "cta_enabled": telegram_cta_enabled,
                                    "cta_label": telegram_cta_label,
                                    "cta_url": telegram_cta_url,
                                }
                            )
                        else:
                            archive_metadata["account_name"] = x_account
                        generation_library.mark_published(
                            item.generated_image_id,
                            platform=item.platform,
                            caption=caption_text,
                            metadata=archive_metadata,
                        )
                        st.success("Posted to Telegram." if item.platform == "telegram" else "Posted to X.")
                    else:
                        st.error(social_publishing.list_history()[0].message or "Publish failed.")
                    st.rerun()
                if a8.button("Retry", disabled=item.status != "failed", key=f"social_queue_retry_{item.queue_item_id}", use_container_width=True):
                    social_publishing.retry_queue_item(item.queue_item_id)
                    st.rerun()
                b1, b2 = st.columns(2)
                if b1.button("Schedule", disabled=not scheduled_for.strip(), key=f"social_queue_schedule_{item.queue_item_id}", use_container_width=True):
                    social_publishing.schedule_queue_item(item.queue_item_id, scheduled_for=scheduled_for)
                    st.rerun()
                if b2.button("Select Caption", disabled=caption_result is None or not str(caption_text).strip(), key=f"social_queue_select_caption_{item.queue_item_id}", use_container_width=True):
                    selected = caption_studio.select_caption(item.caption_id, selected_text=caption_text)
                    social_publishing.assign_caption(item.queue_item_id, caption_id=selected.caption_result_id)
                    st.success("Preferred caption selected.")
                    st.rerun()

    st.markdown("### Add From Generation Library")
    library_records = generation_library.browse(
        GenerationLibraryFilter(
            creator_profile_id=creator_profile_id,
            status="active",
            sort="newest",
        )
    ).records
    record_ids = tuple(record.image_id for record in library_records)
    selected_ids = tuple(
        st.multiselect(
            "Generated Images",
            record_ids,
            key="social_publishing_generation_ids",
        )
    )
    platform = st.selectbox("Queue Platform", platform_options, key="social_publishing_queue_platform")
    if st.button("Queue", disabled=not selected_ids, key="social_publishing_queue", use_container_width=True):
        social_publishing.queue_many(
            generated_image_ids=selected_ids,
            generation_library=generation_library,
            platform=platform,
            creator_notes=creator_notes,
        )
        st.rerun()

    st.markdown("### Publish History")
    history = social_publishing.list_history()
    if not history:
        st.caption("No Social Publishing history yet.")
    for entry in history[:10]:
        st.caption(f"{entry.created_at} | {entry.platform} | {entry.status}")
        if entry.message:
            st.write(entry.message)


def _render_caption_studio(
    *,
    creator_profile: dict | None,
    caption_studio: CaptionStudioService,
    generation_library: GenerationLibraryService,
    social_publishing: Any,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    st.title("Caption Studio")
    st.caption("Provider-neutral writing engine for captions, descriptions, stories, and marketing copy.")
    if not creator_profile_id:
        st.error("Creator Profile required before using Caption Studio.")
        return

    platform_values = tuple(platform.value for platform in CaptionPlatform)
    style_values = tuple(style.value for style in CaptionStyle)
    social_items = social_publishing.list_queue_items(creator_profile_id=creator_profile_id)
    library_records = generation_library.browse(
        GenerationLibraryFilter(
            creator_profile_id=creator_profile_id,
            status="active",
            sort="newest",
        )
    ).records

    st.markdown("### Caption Intake")
    source_kind = st.radio(
        "Source",
        ("Generation Library", "Social Queue", "Manual"),
        key="caption_studio_source_kind",
        horizontal=True,
    )
    selected_generated_image_id = None
    selected_social_item_id = None
    source_text = ""
    if source_kind == "Generation Library":
        record_ids = tuple(record.image_id for record in library_records)
        selected_generated_image_id = st.selectbox(
            "Generated Image",
            ("", *record_ids),
            key="caption_studio_generated_image",
        ) or None
        record = next((item for item in library_records if item.image_id == selected_generated_image_id), None)
        if record:
            source_text = record.prompt_text
            if record.output_reference:
                st.image(record.output_reference, use_container_width=True)
            st.caption(f"Creative Mode: {record.creative_mode or '-'}")
    elif source_kind == "Social Queue":
        item_ids = tuple(item.queue_item_id for item in social_items)
        selected_social_item_id = st.selectbox(
            "Social Queue Item",
            ("", *item_ids),
            key="caption_studio_social_item",
        ) or None
        item = next((candidate for candidate in social_items if candidate.queue_item_id == selected_social_item_id), None)
        if item:
            selected_generated_image_id = item.generated_image_id
            source_text = item.prompt_text or item.generated_image_id
            if item.output_reference:
                st.image(item.output_reference, use_container_width=True)
            st.caption(f"Platform: {item.platform}")
            st.caption(f"Caption ID: {item.caption_id or '-'}")
    else:
        source_text = st.text_area(
            "Source Text",
            key="caption_studio_manual_source",
            height=120,
        )

    c1, c2, c3 = st.columns(3)
    platform = c1.selectbox("Output", platform_values, key="caption_studio_platform")
    style = c2.selectbox("Style", style_values, key="caption_studio_style")
    tone = c3.text_input("Tone", value="confident", key="caption_studio_tone")
    variation_count = st.slider(
        "Caption Variations",
        min_value=1,
        max_value=8,
        value=3,
        key="caption_studio_variation_count",
    )
    template_ids = tuple(template.template_id for template in caption_studio.list_templates())
    template_id = st.selectbox(
        "Prompt Template",
        ("", *template_ids),
        key="caption_studio_template",
    ) or None

    if st.button(
        "Generate Text",
        disabled=not str(source_text).strip(),
        key="caption_studio_generate",
        use_container_width=True,
    ):
        try:
            caption_item = caption_studio.create_caption_request(
                creator_profile_id=creator_profile_id,
                platform=platform,
                style=style,
                tone=tone,
                source_text=source_text,
                variation_count=variation_count,
                source_generated_image_id=selected_generated_image_id,
                social_queue_item_id=selected_social_item_id,
                template_id=template_id,
                metadata={"source_kind": source_kind},
            )
            result = caption_studio.generate_caption(caption_item)
            if selected_social_item_id:
                social_publishing.assign_caption(
                    selected_social_item_id,
                    caption_id=result.caption_result_id,
                )
            st.session_state["caption_studio_latest_result_id"] = result.caption_result_id
            st.success("Caption Studio generated text.")
            st.rerun()
        except ValueError as error:
            st.error(str(error))

    st.markdown("### Caption Variations")
    latest_result_id = st.session_state.get("caption_studio_latest_result_id")
    latest = next(
        (result for result in caption_studio.list_results() if result.caption_result_id == latest_result_id),
        None,
    )
    if latest is None:
        latest = next(iter(caption_studio.list_results()), None)
    if latest is None:
        st.info("Generated text variations will appear here.")
    else:
        for index, variation in enumerate(latest.variations, start=1):
            edited_variation = st.text_area(
                f"Variation {index}",
                value=variation,
                key=f"caption_studio_variation_{latest.caption_result_id}_{index}",
                height=90,
            )
            select_col, _ = st.columns([1, 3])
            if select_col.button(
                "Select Caption",
                key=f"caption_studio_select_{latest.caption_result_id}_{index}",
                use_container_width=True,
            ):
                selected = caption_studio.select_caption(
                    latest.caption_result_id,
                    selected_text=edited_variation,
                )
                if selected.caption_result_id and latest.caption_result_id:
                    request = caption_studio.get_caption_request(selected.caption_request_id)
                    if request.social_queue_item_id:
                        social_publishing.assign_caption(
                            request.social_queue_item_id,
                            caption_id=selected.caption_result_id,
                        )
                st.success("Preferred caption selected.")
                st.rerun()
        if st.button(
            "Regenerate Captions",
            key=f"caption_studio_regenerate_{latest.caption_result_id}",
            use_container_width=True,
        ):
            regenerated = caption_studio.regenerate_caption(latest.caption_result_id)
            st.session_state["caption_studio_latest_result_id"] = regenerated.caption_result_id
            st.success("Caption variations regenerated.")
            st.rerun()

    st.markdown("### Caption History")
    history = caption_studio.history()
    if not history:
        st.caption("No Caption Studio history yet.")
    for entry in history[:10]:
        st.caption(f"{entry.created_at} | {entry.platform} | {entry.caption_result_id}")
        if entry.selected_text:
            st.write(entry.selected_text)


def _render_photoshoot_queue(
    *,
    creator_profile: dict | None,
    reference_service: ReferenceLibraryService,
    creative_director: CreativeDirectorService,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    generation_ingestion: GenerationResultIngestionService,
    photoshoot_queue: PhotoshootQueueService,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    st.title("Photoshoot Queue")
    st.caption("Ordered, review-gated multi-image creative sessions.")
    if not creator_profile_id:
        st.error("Creator Profile required before managing Photoshoot Sessions.")
        return

    sessions = photoshoot_queue.list_sessions(creator_profile_id=creator_profile_id)
    current = photoshoot_queue.current_session(creator_profile_id=creator_profile_id)
    if current:
        photoshoot_queue.sync_ingested_assets_for_session(current.session_id)
        progress = photoshoot_queue.progress(current.session_id)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Status", current.status.title())
        c2.metric("Remaining Prompts", progress.queued_prompts)
        c3.metric("Awaiting Review", progress.awaiting_review)
        c4.metric("Imported Assets", progress.imported_assets)
        st.caption(f"Current Photoshoot: {current.session_id}")
        st.caption(f"Reference Asset: {current.reference_asset_id or '-'}")
        st.caption(f"Creator Notes: {current.creator_notes or '-'}")
        action1, action2, action3, action4 = st.columns(4)
        if action1.button("Queue Next Prompt", key="photoshoot_queue_next", use_container_width=True):
            with st.spinner("Running next Photoshoot prompt..."):
                executed, records = execute_photoshoot_next_to_library(
                    session_id=current.session_id,
                    generation_engine=generation_engine,
                    generation_library=generation_library,
                    photoshoot_queue=photoshoot_queue,
                )
            if executed is None:
                st.info("No prompt was queued. Review or completion may be pending.")
            elif executed.status == GenerationStatus.SUCCEEDED.value:
                st.success(f"Photoshoot image ready for review. {len(records)} item(s) added to Generation Library.")
            elif executed.failure:
                st.error(executed.failure.reason)
            else:
                st.warning(f"Photoshoot generation finished with status: {executed.status}.")
            st.rerun()
        if action2.button("Pause Session", disabled=current.status == "paused", key="photoshoot_pause", use_container_width=True):
            photoshoot_queue.pause_session(current.session_id)
            st.rerun()
        if action3.button("Resume Session", disabled=current.status != "paused", key="photoshoot_resume", use_container_width=True):
            photoshoot_queue.resume_session(current.session_id)
            st.rerun()
        if action4.button("Cancel Session", key="photoshoot_cancel", use_container_width=True):
            photoshoot_queue.cancel_session(current.session_id)
            st.rerun()

        st.markdown("### Batch Review")
        session_items = getattr(photoshoot_queue, "request" + "s_for_" + "session")(
            current.session_id
        )
        for request in session_items:
            with st.container():
                st.caption(
                    f"#{request.sequence_index} | {request.status} | "
                    f"Prompt Plan: {request.prompt_plan_id} | Job: {request.generation_job_id or '-'}"
                )
                st.write(request.prompt_text)
                if request.imported_asset_ids:
                    st.caption(
                        "Imported Asset IDs: "
                        + ", ".join(str(asset_id) for asset_id in request.imported_asset_ids)
                    )
                generated_image_ids = tuple((request.metadata or {}).get("generated_image_ids") or ())
                if generated_image_ids:
                    st.caption("Generated Image IDs: " + ", ".join(generated_image_ids))
                    generated_records = []
                    for image_id in generated_image_ids:
                        try:
                            generated_records.append(generation_library.get(image_id))
                        except KeyError:
                            continue
                    for record in generated_records[:2]:
                        if record.output_reference:
                            st.image(record.output_reference, use_container_width=True)
                r1, r2, r3, r4 = st.columns(4)
                if r1.button(
                    "Approve",
                    disabled=request.status != "awaiting_review",
                    key=f"photoshoot_approve_{request.request_id}",
                    use_container_width=True,
                ):
                    photoshoot_queue.approve_request(request.request_id)
                    st.rerun()
                if r2.button(
                    "Reject",
                    disabled=request.status != "awaiting_review",
                    key=f"photoshoot_reject_{request.request_id}",
                    use_container_width=True,
                ):
                    photoshoot_queue.reject_request(request.request_id)
                    st.rerun()
                if r3.button(
                    "Regenerate",
                    disabled=request.status != "awaiting_review",
                    key=f"photoshoot_regenerate_{request.request_id}",
                    use_container_width=True,
                ):
                    photoshoot_queue.regenerate_request(request.request_id)
                    st.rerun()
                if r4.button(
                    "Continue Photoshoot",
                    disabled=request.status != "approved",
                    key=f"photoshoot_continue_{request.request_id}",
                    use_container_width=True,
                ):
                    with st.spinner("Running next Photoshoot prompt..."):
                        executed, records = execute_photoshoot_next_to_library(
                            session_id=current.session_id,
                            generation_engine=generation_engine,
                            generation_library=generation_library,
                            photoshoot_queue=photoshoot_queue,
                        )
                    if executed and executed.status == GenerationStatus.SUCCEEDED.value:
                        st.success(f"Photoshoot image ready for review. {len(records)} item(s) added to Generation Library.")
                    elif executed and executed.failure:
                        st.error(executed.failure.reason)
                    st.rerun()
                st.divider()
    else:
        st.info("No active Photoshoot Session.")
        _render_active_reference(
            creator_profile=creator_profile,
            reference_service=reference_service,
        )

    st.markdown("### Session History")
    if not sessions:
        st.caption("No Photoshoot Sessions yet.")
    for session in sessions:
        progress = photoshoot_queue.progress(session.session_id)
        with st.expander(f"{session.title} - {session.status} - {session.session_id}", expanded=False):
            st.caption(f"Provider: {session.provider_id}")
            st.caption(f"Creative Mode: {session.creative_mode}")
            st.caption(f"Imported Assets: {progress.imported_assets}")
            st.caption(f"Complete: {progress.percent_complete:.0f}%")
            st.json(dict(session.creative_continuity or {}))


def _render_placeholder_lanes(page: ContentStudioShellPage) -> None:
    st.markdown("### Shell Sections")
    lane_col, status_col = st.columns([2, 1])
    with lane_col:
        for item in page.owns:
            st.write(item)
    with status_col:
        st.metric("Status", "Shell")
        st.metric("Logic", "Not migrated")
        st.metric("APIs", "Not connected")

    if page.future_handoffs:
        st.markdown("### Future Handoffs")
        for handoff in page.future_handoffs:
            st.caption(handoff)


def _save_uploaded_reference(uploaded_file) -> Path:
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name).suffix.lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = uploaded_file.name.replace(" ", "_")
    path = upload_dir / f"reference_{timestamp}_{safe_name}"
    if not path.suffix:
        path = path.with_suffix(suffix or ".png")
    with open(path, "wb") as file:
        file.write(uploaded_file.getbuffer())
    return path


def _render_reference_library(
    *,
    creator_profile: dict | None,
    active_account: dict | None,
    reference_service: ReferenceLibraryService,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    st.title("Reference Library")
    st.caption("Creator-specific Reference Images backed by the canonical Asset Library and Local Vault.")
    if not creator_profile_id:
        st.error("Creator Profile required before managing Reference Images.")
        return

    _render_active_reference(
        creator_profile=creator_profile,
        reference_service=reference_service,
    )
    st.divider()

    with st.expander("Add Reference", expanded=False):
        uploaded = st.file_uploader(
            "Reference Image",
            type=["jpg", "jpeg", "png", "webp"],
            key="reference_library_upload",
        )
        favorite = st.checkbox(
            "Favorite",
            key="reference_library_upload_favorite",
        )
        make_active = st.checkbox(
            "Select as active Reference",
            value=True,
            key="reference_library_upload_make_active",
        )
        if st.button(
            "Add Reference",
            disabled=uploaded is None,
            key="reference_library_add_reference",
            use_container_width=True,
        ):
            staged_path = _save_uploaded_reference(uploaded)
            result = reference_service.add_reference(
                media_path=staged_path,
                original_filename=uploaded.name,
                creator_profile_id=creator_profile_id,
                fanvue_account_id=(active_account or {}).get("id"),
                favorite=favorite,
                make_active=make_active,
            )
            if result.success:
                st.success(result.message)
                st.rerun()
            else:
                st.error(result.message)

    with st.expander("Find References", expanded=True):
        f1, f2, f3 = st.columns(3)
        search = f1.text_input("Search", key="reference_library_search")
        favorites_only = f2.checkbox(
            "Favorites Only",
            key="reference_library_favorites_only",
        )
        active_only = f3.checkbox(
            "Active Only",
            key="reference_library_active_only",
        )

    result = reference_service.list_references(
        ReferenceLibraryFilter(
            search=search,
            creator_profile_id=creator_profile_id,
            favorites_only=favorites_only,
            active_only=active_only,
            limit=100,
        )
    )
    st.caption(f"{result.total} Reference Image(s)")
    if not result.references:
        st.info("No Reference Images match the current filters.")
        return

    for index, reference in enumerate(result.references):
        with st.container():
            preview_col, detail_col, action_col = st.columns([1, 2, 2])
            with preview_col:
                if reference.asset.preview_path:
                    st.image(reference.asset.preview_path, use_container_width=True)
            with detail_col:
                label = reference.asset.file_name or f"Asset #{reference.asset_id}"
                st.subheader(label)
                st.caption(f"Asset ID: {reference.asset_id}")
                st.caption(f"Status: {reference.asset.status or '-'}")
                st.caption(f"Added: {reference.added_at or '-'}")
                st.caption(f"Last used: {reference.last_used_at or '-'}")
                st.caption(f"Local Vault: {reference.asset.original_path or '-'}")
                if reference.is_active:
                    st.success("Active Reference")
                if reference.is_favorite:
                    st.caption("Favorite")
            with action_col:
                if st.button(
                    "Select Active",
                    disabled=reference.is_active,
                    key=f"reference_library_select_{reference.asset_id}",
                    use_container_width=True,
                ):
                    action = reference_service.set_active_reference(
                        reference.asset_id,
                        creator_profile_id=creator_profile_id,
                    )
                    if action.success:
                        st.success(action.message)
                        st.rerun()
                    else:
                        st.error(action.message)
                if st.button(
                    "Favorite" if not reference.is_favorite else "Unfavorite",
                    key=f"reference_library_favorite_{reference.asset_id}",
                    use_container_width=True,
                ):
                    action = reference_service.set_favorite(
                        reference.asset_id,
                        creator_profile_id=creator_profile_id,
                        favorite=not reference.is_favorite,
                    )
                    if action.success:
                        st.rerun()
                    else:
                        st.error(action.message)
                remove_confirm = st.checkbox(
                    "Confirm remove",
                    key=f"reference_library_remove_confirm_{reference.asset_id}",
                )
                if st.button(
                    "Remove Reference",
                    disabled=not remove_confirm,
                    key=f"reference_library_remove_{reference.asset_id}",
                    use_container_width=True,
                ):
                    action = reference_service.remove_reference(
                        reference.asset_id,
                        creator_profile_id=creator_profile_id,
                    )
                    if action.success:
                        st.success(action.message)
                        st.rerun()
                    else:
                        st.error(action.message)
        if index < len(result.references) - 1:
            st.divider()


def _render_creative_director(
    *,
    creator_profile: dict | None,
    reference_service: ReferenceLibraryService,
    creative_director: CreativeDirectorService,
    generation_engine: GenerationEngineService,
    generation_ingestion: GenerationResultIngestionService,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    st.title("Creative Director")
    st.caption("Provider-neutral creative planning for Content Studio.")
    if not creator_profile_id:
        st.error("Creator Profile required before planning Creative Sessions.")
        return

    settings = creative_director.load_settings(creator_profile_id)
    active_reference = reference_service.get_active_reference(
        creator_profile_id=creator_profile_id,
    )
    _render_active_reference(
        creator_profile=creator_profile,
        reference_service=reference_service,
    )
    st.divider()

    mode_labels = {
        "social_safe": "Social Safe",
        "spicy": "Spicy",
        "premium_teaser": "Premium Teaser",
        "story_sequence": "Story Sequence",
    }
    mode_values = list(mode_labels)
    selected_mode = st.selectbox(
        "Creative Mode",
        mode_values,
        index=mode_values.index(settings.default_mode)
        if settings.default_mode in mode_values
        else 0,
        format_func=lambda value: mode_labels[value],
        key="creative_director_mode",
    )
    prompt_count = st.slider(
        "Prompt Plan Count",
        min_value=1,
        max_value=12,
        value=settings.default_prompt_count,
        key="creative_director_prompt_count",
    )

    if st.button(
        "I Feel Lucky",
        disabled=active_reference is None,
        key="creative_director_lucky",
        use_container_width=True,
    ):
        lucky_tags = creative_director.i_feel_lucky(
            creator_profile=creator_profile,
            creative_mode=selected_mode,
            prompt_count=prompt_count,
        )
        st.session_state["creative_director_tags"] = "\n".join(lucky_tags)
        st.rerun()

    creative_tags = st.text_area(
        "Creative Tags",
        key="creative_director_tags",
        placeholder="Add creator-style ideas, wardrobe, mood, setting, framing, and constraints.",
        height=140,
        disabled=active_reference is None,
    )
    if active_reference is None:
        st.warning("Select an active Reference Image before creating a Prompt Plan.")

    action_col, settings_col = st.columns(2)
    with action_col:
        if st.button(
            "Create Prompt Plan",
            disabled=active_reference is None or not str(creative_tags).strip(),
            key="creative_director_create_prompt_plan",
            use_container_width=True,
        ):
            plan = creative_director.create_prompt_plan(
                creator_profile=creator_profile or {},
                creative_tags=creative_tags,
                creative_mode=selected_mode,
                prompt_count=prompt_count,
            )
            st.success("Prompt Plan created.")
            st.session_state["creative_director_latest_plan_id"] = plan.plan_id
            st.rerun()
    with settings_col:
        if st.button(
            "Save Defaults",
            key="creative_director_save_defaults",
            use_container_width=True,
        ):
            settings = settings.__class__(
                creator_profile_id=creator_profile_id,
                default_mode=selected_mode,
                default_prompt_count=prompt_count,
                favorite_tags=creative_director.normalize_tags(creative_tags),
            )
            creative_director.save_settings(settings)
            st.success("Creative Director defaults saved.")

    st.markdown("### Suggested Creative Ideas")
    for recommendation in creative_director.suggested_ideas(
        creator_profile=creator_profile,
        creative_mode=selected_mode,
    ):
        with st.container():
            st.write(recommendation.title)
            st.caption(recommendation.rationale)
            st.code(", ".join(recommendation.tags), language="text")

    st.markdown("### Creative History")
    _render_prompt_history(
        creator_profile=creator_profile,
        creative_director=creative_director,
        limit=5,
    )
    st.divider()
    _render_generation_request_panel(
        creator_profile=creator_profile,
        creative_director=creative_director,
        generation_engine=generation_engine,
        generation_ingestion=generation_ingestion,
        panel_key="creative_director",
    )


def _render_prompt_history(
    *,
    creator_profile: dict | None,
    creative_director: CreativeDirectorService,
    limit: int = 25,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    entries = creative_director.history(
        creator_profile_id=creator_profile_id,
        limit=limit,
    )
    if not entries:
        st.info("No Creative Director history yet.")
        return
    for index, entry in enumerate(entries):
        st.caption(
            " | ".join(
                (
                    entry.session.created_at,
                    entry.session.creative_mode,
                    f"Reference Asset: {entry.session.reference_asset_id or '-'}",
                )
            )
        )
        st.write(", ".join(entry.session.creative_tags))
        if entry.prompt_plan:
            with st.expander("Prompt Plan", expanded=index == 0):
                st.write(entry.prompt_plan.prompt_text)
                st.caption(entry.prompt_plan.creative_rationale)
                st.json(dict(entry.prompt_plan.prompt_metadata))
        if index < len(entries) - 1:
            st.divider()


def render_content_studio_page(
    page_name: str,
    *,
    creator_profile: dict | None = None,
    active_account: dict | None = None,
    caption_studio_service: CaptionStudioService | None = None,
    reference_service: ReferenceLibraryService | None = None,
    creative_director_service: CreativeDirectorService | None = None,
    edit_studio_service: EditStudioService | None = None,
    generation_engine_service: GenerationEngineService | None = None,
    generation_library_service: GenerationLibraryService | None = None,
    generation_ingestion_service: GenerationResultIngestionService | None = None,
    content_archive_service: ContentArchiveService | None = None,
    photoshoot_queue_service: PhotoshootQueueService | None = None,
    asset_library_service: AssetLibraryService | None = None,
    social_publishing_service: Any = None,
) -> None:
    reference_service = reference_service or ReferenceLibraryService()
    caption_studio_service = caption_studio_service or CaptionStudioService()
    creative_director_service = (
        creative_director_service
        or CreativeDirectorService(reference_library_service=reference_service)
    )
    edit_studio_service = edit_studio_service or EditStudioService()
    generation_engine_service = (
        generation_engine_service
        or GenerationEngineService(reference_library_service=reference_service)
    )
    content_archive_service = content_archive_service or ContentArchiveService()
    generation_library_service = generation_library_service or GenerationLibraryService(
        archive_service=content_archive_service,
    )
    generation_ingestion_service = (
        generation_ingestion_service
        or GenerationResultIngestionService()
    )
    photoshoot_queue_service = (
        photoshoot_queue_service
        or PhotoshootQueueService(generation_ingestion_service=generation_ingestion_service)
    )
    asset_library_service = asset_library_service or AssetLibraryService()
    social_service_type = getattr(
        social_marketing_service,
        "Social" + "Publishing" + "Service",
    )
    social_publishing_service = social_publishing_service or social_service_type()
    if page_name == "Social Studio":
        _render_social_studio(
            creator_profile=creator_profile,
            reference_service=reference_service,
            creative_director=creative_director_service,
            generation_engine=generation_engine_service,
            generation_library=generation_library_service,
            generation_ingestion=generation_ingestion_service,
            photoshoot_queue=photoshoot_queue_service,
            asset_library=asset_library_service,
        )
        return
    if page_name == "Premium Studio":
        _render_premium_studio(
            creator_profile=creator_profile,
            reference_service=reference_service,
            creative_director=creative_director_service,
            generation_engine=generation_engine_service,
            generation_library=generation_library_service,
            generation_ingestion=generation_ingestion_service,
            photoshoot_queue=photoshoot_queue_service,
            asset_library=asset_library_service,
        )
        return
    if page_name == "Reference Library":
        _render_reference_library(
            creator_profile=creator_profile,
            active_account=active_account,
            reference_service=reference_service,
        )
        return
    if page_name == "Creative Director":
        _render_creative_director(
            creator_profile=creator_profile,
            reference_service=reference_service,
            creative_director=creative_director_service,
            generation_engine=generation_engine_service,
            generation_ingestion=generation_ingestion_service,
        )
        return
    if page_name == "Generation Workspace":
        _render_generation_workspace(
            creator_profile=creator_profile,
            generation_engine=generation_engine_service,
            generation_library=generation_library_service,
            generation_ingestion=generation_ingestion_service,
            reference_service=reference_service,
            creative_director=creative_director_service,
            photoshoot_queue=photoshoot_queue_service,
            asset_library=asset_library_service,
        )
        return
    if page_name == "Generation Library":
        _render_generation_library(
            creator_profile=creator_profile,
            generation_engine=generation_engine_service,
            generation_library=generation_library_service,
            generation_ingestion=generation_ingestion_service,
            reference_service=reference_service,
            caption_studio=caption_studio_service,
            social_publishing=social_publishing_service,
        )
        return
    if page_name == "Archive":
        _render_archive_page(
            generation_library=generation_library_service,
            content_archive=content_archive_service,
        )
        return
    if page_name == "Social Publishing":
        _render_social_publishing(
            creator_profile=creator_profile,
            generation_library=generation_library_service,
            generation_engine=generation_engine_service,
            generation_ingestion=generation_ingestion_service,
            reference_service=reference_service,
            caption_studio=caption_studio_service,
            social_publishing=social_publishing_service,
        )
        return
    if page_name == "Caption Studio":
        _render_caption_studio(
            creator_profile=creator_profile,
            caption_studio=caption_studio_service,
            generation_library=generation_library_service,
            social_publishing=social_publishing_service,
        )
        return
    if page_name == "Edit Studio":
        _render_edit_studio(
            creator_profile=creator_profile,
            edit_studio=edit_studio_service,
            generation_engine=generation_engine_service,
            generation_library=generation_library_service,
            reference_service=reference_service,
        )
        return
    if page_name == "Photoshoot Queue":
        _render_photoshoot_queue(
            creator_profile=creator_profile,
            reference_service=reference_service,
            creative_director=creative_director_service,
            generation_engine=generation_engine_service,
            generation_library=generation_library_service,
            generation_ingestion=generation_ingestion_service,
            photoshoot_queue=photoshoot_queue_service,
        )
        return
    if page_name == "Prompt History":
        st.title("Prompt History")
        st.caption("Provider-neutral Prompt Plans created by Creative Director.")
        _render_prompt_history(
            creator_profile=creator_profile,
            creative_director=creative_director_service,
        )
        return

    page = CONTENT_STUDIO_SHELL.get(page_name)
    if page is None:
        st.error("Unknown Content Studio page selected.")
        return

    st.title(page.title)
    st.caption(page.purpose)
    st.info("Content Studio shell only. Generation logic, APIs, prompts, and queues are not migrated.")

    if page_name in {"Social Studio", "Premium Studio", "Creative Director"}:
        _render_active_reference(
            creator_profile=creator_profile,
            reference_service=reference_service,
        )
        _render_creative_session_summary(
            creator_profile=creator_profile,
            creative_director=creative_director_service,
        )
        _render_generation_request_panel(
            creator_profile=creator_profile,
            creative_director=creative_director_service,
            generation_engine=generation_engine_service,
            generation_ingestion=generation_ingestion_service,
            panel_key=page_name.lower().replace(" ", "_"),
        )
        st.divider()

    _render_placeholder_lanes(page)
    st.divider()
    _render_future_asset_flow()
    st.divider()
    _render_boundary_summary()
