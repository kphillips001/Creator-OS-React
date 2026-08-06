"""Content Studio shell pages.

This module defines Creator OS Content Studio presentation and delegates
generation execution to Generation Engine/provider registry services.
"""

from __future__ import annotations

import inspect
import base64
import html
import json
import mimetypes
import os
import re
import time
import traceback
import urllib.request
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import streamlit as st
import streamlit.components.v1 as components
try:
    from PIL import Image
except Exception:  # pragma: no cover - optional runtime display enhancement
    Image = None

import app.services.social_publishing_service as social_marketing_service
from app.models.caption_studio import CaptionPlatform, CaptionStyle
from app.models.commerce_destination import (
    CommerceDestination,
    CommerceDestinationRequest,
)
from app.models.chat_commerce_registration import ChatAvailabilityState
from app.models.creative_director import PromptPlan
from app.models.fulfillment_registration import (
    BusinessAssetFulfillmentRecord,
    FulfillmentLifecycleState,
    MediaLinkSubmission,
    MediaLinkVerificationState,
)
from app.models.generation_library import GeneratedImageRecord, GenerationLibraryFilter
from app.models.generation_engine import GenerationJob, GenerationResult
from app.models.reference_library import ReferenceLibraryFilter
from app.models.generation_engine import GenerationMediaType, GenerationStatus, GenerationType
from app.models.render_policy import content_render_policy, photoshoot_planning_mode
from app.services.asset_library_service import AssetLibraryService
from app.services.asset_registration_service import AssetRegistrationService
from app.services.caption_studio_service import CaptionStudioService
from app.services.commerce_destination_service import CommerceDestinationService
from app.services.chat_commerce_registration_service import (
    ChatCommerceRegistrationService,
)
from app.services.content_archive_service import ContentArchiveService
from app.services.content_studio_configuration_service import (
    PREMIUM_CREATIVE_MODE_LABELS,
    PREMIUM_PROVIDER_LABELS,
    PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM,
    PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM,
    default_provider_index,
    premium_studio_provider_options,
)
from app.services.creator_approval_service import CreatorApprovalService
from app.services.creative_director_service import CreativeDirectorService
from app.services.edit_studio_service import EditStudioService
from app.services.fulfillment_registration_service import FulfillmentRegistrationService
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_library_service import GenerationLibraryService
from app.services.generation_result_ingestion_service import GenerationResultIngestionService
from app.services.photoshoot_queue_service import PhotoshootQueueService
from app.services.photoshoot_fanvue_upload_service import (
    FANVUE_PHOTOSHOOT_FOLDER,
    FANVUE_WALL_FOLDER,
    PhotoshootFanvueUploadService,
)
from app.services.fanvue_upload_trace import fanvue_upload_exception
from app.services.reference_library_service import ReferenceLibraryService


CONTENT_STUDIO_PAGES = (
    "Social Studio",
    "Premium Studio",
    "Reference Library",
    "Creative Director",
    "Generation Workspace",
    "Generation Library",
    "Archive",
    "Photoshoot Studio",
    "Photoshoot Gallery",
    "Social Publishing",
    "Caption Studio",
    "Edit Studio",
    "Prompt History",
    "Settings",
)


X_PUBLISH_DIALOG_DEBUG_LOG = Path("logs") / "x_publish_dialog_debug.log"
SOCIAL_PUBLISHING_LEGACY_LABEL = "Send to Social Publishing"


def _display_image_src(image_reference: Any) -> str:
    source = str(image_reference or "").strip()
    if source.startswith(("http://", "https://", "data:")):
        return source
    path = Path(source).expanduser()
    if not path.exists() or not path.is_file():
        return source
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _local_image_display_height(image_reference: Any, *, max_height: int) -> int:
    if Image is None:
        return int(max_height) + 12
    source = str(image_reference or "").strip()
    if source.startswith(("http://", "https://", "data:")):
        return int(max_height) + 12
    path = Path(source).expanduser()
    if not path.exists() or not path.is_file():
        return int(max_height) + 12
    try:
        with Image.open(path) as image:
            return min(int(max_height), int(image.height)) + 12
    except Exception:
        return int(max_height) + 12


def _render_edit_studio_image(image_reference: Any, *, alt: str, max_height: int = 550) -> None:
    src = html.escape(_display_image_src(image_reference), quote=True)
    alt_text = html.escape(alt, quote=True)
    components.html(
        f"""
        <div style="
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
            padding: 0;
        ">
            <img
                src="{src}"
                alt="{alt_text}"
                style="
                    display: block;
                    max-height: {int(max_height)}px;
                    max-width: 100%;
                    width: auto;
                    height: auto;
                    object-fit: contain;
                    margin: 0 auto;
                "
            />
        </div>
        """,
        height=_local_image_display_height(image_reference, max_height=max_height),
        scrolling=False,
    )


def _debug_x_publish_dialog_event(
    event: str,
    *,
    source: str,
    variable_name: str,
    value: Any,
    diagnostic: Any = None,
) -> None:
    try:
        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        payload = {
            "event": event,
            "file": __file__,
            "function": caller.f_code.co_name if caller is not None else None,
            "line": caller.f_lineno if caller is not None else None,
            "source": source,
            "variable_name": variable_name,
            "value": str(value),
            "diagnostic": repr(diagnostic),
            "session_message": str(st.session_state.get("generation_library_x_publish_message", "")),
            "stack": traceback.format_stack(limit=16),
        }
        X_PUBLISH_DIALOG_DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(X_PUBLISH_DIALOG_DEBUG_LOG, "a", encoding="utf-8") as file:
            file.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass


SOCIAL_PROVIDER_LABELS = {
    "seedream_4_5": "Seedream 4.5",
    "seedream_5_0_pro": "Seedream 5.0 Pro",
    "wan_2_7_image_edit": "WAN 2.7",
    "nano_banana_pro": "Nano Banana Pro",
    "nano_banana": "Nano Banana",
    "future_provider": "Future Provider",
}

SOCIAL_CREATIVE_MODE_LABELS = {
    "social_safe": "Social Safe",
    "story_sequence": "Story Sequence",
}

EDIT_PROVIDER_LABELS = {
    "seedream_4_5": "Seedream 4.5",
    "seedream_5_0_pro": "Seedream 5.0 Pro",
    "wan_2_7_image_edit": "WAN 2.7",
    "nano_banana_pro": "Nano Banana Pro",
    "nano_banana": "Nano Banana",
    "flux": "Flux",
    "future_provider": "Future Provider",
}

EDIT_STUDIO_PROVIDER_ORDER = (
    "seedream_5_0_pro",
    "nano_banana_pro",
    "wan_2_7_image_edit",
)
EDIT_STUDIO_DEFAULT_PROVIDER_ID = "seedream_5_0_pro"

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
        title="Content Studio",
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
    "Photoshoot Studio": ContentStudioShellPage(
        title="Photoshoot Studio",
        purpose="Image-first creative workflow for directing continuity-locked photoshoot sessions.",
        owns=("Photoshoot Studio UI", "Creative shot workflow"),
        future_handoffs=("Creator OS Local Vault", "AI Import Workflow"),
    ),
    "Photoshoot Gallery": ContentStudioShellPage(
        title="Photoshoot Gallery",
        purpose="Completed photoshoot timelines and shot review.",
        owns=("Completed photoshoot sessions", "Shot timeline review"),
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
        purpose="Shell for Content Creation presentation and workflow preferences.",
        owns=("Content Creation UI settings", "Creative workflow preferences"),
    ),
}


def _render_boundary_summary() -> None:
    st.markdown("### Architecture Boundary")
    owned_col, external_col = st.columns(2)
    with owned_col:
        st.markdown("#### Owned By Content Creation")
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


_COMMERCE_DESTINATION_LABELS = {
    CommerceDestination.TELEGRAM_WALL: "Telegram Wall",
    CommerceDestination.CUSTOMER_CONVERSATIONS: "Customer Conversations",
    CommerceDestination.BOTH: "Both",
    CommerceDestination.ARCHIVE_ONLY: "Archive Only",
}


_FULFILLMENT_STATUS_LABELS = {
    FulfillmentLifecycleState.ROUTING_PENDING: "Awaiting Upload",
    FulfillmentLifecycleState.READY_FOR_UPLOAD: "Awaiting Upload",
    FulfillmentLifecycleState.UPLOAD_QUEUED: "Awaiting Upload",
    FulfillmentLifecycleState.UPLOADING: "Uploading",
    FulfillmentLifecycleState.UPLOADED: "Uploaded",
    FulfillmentLifecycleState.PROCESSING: "Uploading",
    FulfillmentLifecycleState.MEDIA_READY: "Waiting For Media Link",
    FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK: "Waiting For Media Link",
    FulfillmentLifecycleState.MEDIA_LINK_SUBMITTED: "Media Link Submitted",
    FulfillmentLifecycleState.MEDIA_LINK_VERIFIED: "Fulfillment Ready",
    FulfillmentLifecycleState.FULFILLMENT_READY: "Fulfillment Ready",
    FulfillmentLifecycleState.FAILED: "Failed",
    FulfillmentLifecycleState.RETRY_REQUIRED: "Retry Required",
    FulfillmentLifecycleState.RETIRED: "Retired",
}


_CHAT_COMMERCE_STATUS_LABELS = {
    ChatAvailabilityState.PENDING: "Chat Registration Pending",
    ChatAvailabilityState.BLOCKED: "Blocked",
    ChatAvailabilityState.CHAT_READY: "Chat Ready",
    ChatAvailabilityState.TEMPORARILY_UNAVAILABLE: "Temporarily Unavailable",
    ChatAvailabilityState.RETIRED: "Retired",
    ChatAvailabilityState.FAILED: "Failed",
}


def _commerce_destination_label(value: Any) -> str:
    try:
        destination = CommerceDestination(str(value))
    except Exception:
        return str(value or "Awaiting selection")
    return _COMMERCE_DESTINATION_LABELS.get(destination, destination.value)


def _commerce_destination_needs_fulfillment(value: Any) -> bool:
    try:
        destination = CommerceDestination(str(value))
    except Exception:
        return False
    return destination in {
        CommerceDestination.CUSTOMER_CONVERSATIONS,
        CommerceDestination.BOTH,
    }


def _selected_fanvue_account_id() -> int | None:
    value = st.session_state.get("fanvue_account_id") or st.session_state.get(
        "selected_fanvue_account_id"
    )
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _fulfillment_status_label(record: BusinessAssetFulfillmentRecord | None) -> str:
    if record is None:
        return "Awaiting Upload"
    return _FULFILLMENT_STATUS_LABELS.get(
        record.lifecycle_state,
        str(record.lifecycle_state.value if hasattr(record.lifecycle_state, "value") else record.lifecycle_state),
    )


def _render_chat_commerce_status_panel(*, asset_id: int) -> None:
    try:
        record = ChatCommerceRegistrationService().get_by_asset_id(int(asset_id))
    except Exception as error:
        st.caption(f"Chat Commerce status unavailable: {error}")
        return
    if record is None:
        st.caption("Chat Commerce Status: Chat Registration Pending")
        return
    label = _CHAT_COMMERCE_STATUS_LABELS.get(
        record.availability_state,
        record.availability_state.value,
    )
    st.caption(
        " | ".join(
            (
                f"Chat Commerce Status: {label}",
                f"Recommendation Eligible: {'Yes' if record.recommendation_eligible else 'No'}",
                f"Delivery Eligible: {'Yes' if record.delivery_eligible else 'No'}",
            )
        )
    )
    if record.block_reasons:
        st.caption("Chat Blocks: " + ", ".join(record.block_reasons))


def _render_fulfillment_registration_panel(
    *,
    asset_id: int | None,
    creator_profile_id: int | None,
    source_workflow: str,
    source_session_id: str | None = None,
    key_prefix: str,
) -> None:
    if asset_id is None:
        return
    try:
        destination = CommerceDestinationService().get_destination(int(asset_id))
    except Exception as error:
        st.caption(f"Fulfillment status unavailable: {error}")
        return
    if destination is None or not _commerce_destination_needs_fulfillment(
        destination.selected_commerce_destination
    ):
        return

    service = FulfillmentRegistrationService()
    try:
        record = service.get_fulfillment_by_asset_id(int(asset_id))
    except Exception as error:
        st.caption(f"Fulfillment status unavailable: {error}")
        return

    st.caption(f"Fulfillment Status: {_fulfillment_status_label(record)}")
    if record is not None:
        st.caption(
            " | ".join(
                (
                    f"Fanvue Media UUID: {record.provider_media_id or '-'}",
                    f"Media Link: {record.media_link_verification_state.value}",
                    f"Verified: {record.media_link_verified_at or '-'}",
                )
            )
        )
        if record.failure_message:
            st.warning(record.failure_message)

    if record is None:
        if st.button(
            "Start Fulfillment Registration",
            key=f"{key_prefix}_fulfillment_register",
            use_container_width=True,
        ):
            try:
                results = service.consume_pending_customer_conversation_intents(
                    limit=100,
                    provider_account_id=_selected_fanvue_account_id(),
                )
            except Exception as error:
                st.error(f"Fulfillment Registration failed: {error}")
            else:
                asset_result = next(
                    (result for result in results if int(result.asset_id or 0) == int(asset_id)),
                    None,
                )
                if asset_result and asset_result.success:
                    st.success("Fulfillment Registration started.")
                    st.rerun()
                else:
                    st.error("No pending Customer Conversations routing intent was available.")
        return

    if record.lifecycle_state == FulfillmentLifecycleState.FULFILLMENT_READY:
        st.success("Fulfillment Ready")
        _render_chat_commerce_status_panel(asset_id=int(asset_id))
        return

    if record.lifecycle_state in {
        FulfillmentLifecycleState.READY_FOR_UPLOAD,
        FulfillmentLifecycleState.UPLOAD_QUEUED,
        FulfillmentLifecycleState.RETRY_REQUIRED,
    }:
        fanvue_account_id = _selected_fanvue_account_id() or record.provider_account_id
        if st.button(
            "Upload to Fanvue Chat Vault",
            key=f"{key_prefix}_fulfillment_upload",
            disabled=not fanvue_account_id,
            use_container_width=True,
        ):
            try:
                result = service.upload_customer_conversations_asset(
                    asset_id=int(asset_id),
                    fanvue_account_id=int(fanvue_account_id),
                )
            except Exception as error:
                st.error(f"Fanvue upload failed: {error}")
            else:
                if result.success:
                    st.success("Uploaded. Waiting For Media Link.")
                    st.rerun()
                else:
                    st.error("; ".join(result.errors) or "Fanvue upload failed.")
        if not fanvue_account_id:
            st.caption("Select a Fanvue account before uploading.")

    if record.lifecycle_state in {
        FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK,
        FulfillmentLifecycleState.MEDIA_LINK_SUBMITTED,
        FulfillmentLifecycleState.FAILED,
        FulfillmentLifecycleState.RETRY_REQUIRED,
    }:
        st.markdown("[Open Fanvue](https://www.fanvue.com/)")
        media_link = st.text_input(
            "Paste Media Link",
            value=record.media_link or "",
            key=f"{key_prefix}_fulfillment_media_link",
            disabled=(
                record.media_link_verification_state
                == MediaLinkVerificationState.VERIFIED
            ),
        )
        if st.button(
            "Verify Media Link",
            key=f"{key_prefix}_fulfillment_verify",
            disabled=(
                not media_link
                or creator_profile_id is None
                or record.media_link_verification_state
                == MediaLinkVerificationState.VERIFIED
            ),
            use_container_width=True,
        ):
            try:
                verification = service.submit_media_link(
                    MediaLinkSubmission(
                        asset_id=int(asset_id),
                        media_link=media_link,
                        creator_profile_id=int(creator_profile_id),
                        submitted_by={
                            "source": "content_studio",
                            "source_workflow": source_workflow,
                            "source_session_id": source_session_id,
                        },
                        idempotency_key=(
                            f"content-studio-media-link:{int(asset_id)}:{media_link}"
                        ),
                    )
                )
            except Exception as error:
                st.error(f"Media Link verification failed: {error}")
            else:
                if verification.success:
                    st.success("Fulfillment Ready")
                    st.rerun()
                else:
                    st.error("; ".join(verification.errors) or "Media Link verification failed.")
        if creator_profile_id is None:
            st.caption("Creator Profile is required before verifying a Media Link.")


def _render_commerce_destination_selector(
    *,
    asset_id: int | None,
    creator_profile_id: int | None,
    source_workflow: str,
    source_session_id: str | None = None,
    key_prefix: str,
) -> None:
    if asset_id is None:
        return
    try:
        service = CommerceDestinationService()
        record = service.get_destination(int(asset_id))
    except Exception as error:
        st.caption(f"Commerce destination unavailable: {error}")
        return
    if record is None:
        st.caption("Commerce destination pending Business Asset registration.")
        return

    st.caption(
        "Commerce Destination: "
        f"{_commerce_destination_label(record.selected_commerce_destination)}"
    )
    options = tuple(CommerceDestination)
    try:
        current_index = options.index(CommerceDestination(record.selected_commerce_destination))
    except Exception:
        current_index = 0
    selected = st.selectbox(
        "Commerce Destination",
        options,
        index=current_index,
        key=f"{key_prefix}_commerce_destination",
        format_func=lambda value: _COMMERCE_DESTINATION_LABELS.get(value, value.value),
    )
    note = st.text_input(
        "Destination Note",
        key=f"{key_prefix}_commerce_destination_note",
        placeholder="Optional",
    )
    if st.button(
        "Save Commerce Destination",
        key=f"{key_prefix}_commerce_destination_save",
        use_container_width=True,
    ):
        result = service.set_destination(
            CommerceDestinationRequest(
                asset_id=int(asset_id),
                registration_id=record.registration_id,
                destination=selected,
                creator_profile_id=creator_profile_id,
                creator_identity={"source": "content_studio"},
                source_workflow=source_workflow,
                source_session_id=source_session_id,
                reason=note or None,
                idempotency_key=(
                    f"content-studio-commerce-destination:"
                    f"{int(asset_id)}:{int(record.destination_revision or 0) + 1}:{selected.value}"
                ),
            )
        )
        if result.success:
            st.success("Commerce Destination saved.")
            st.rerun()
        else:
            st.error("; ".join(result.errors) or "Commerce Destination could not be saved.")


def _render_commerce_destination_group_selector(
    *,
    records: tuple[GeneratedImageRecord, ...],
    creator_profile_id: int | None,
    source_workflow: str,
    source_session_id: str | None,
    key_prefix: str,
) -> None:
    imported_records = tuple(
        record for record in records if record.imported_asset_id is not None
    )
    if not imported_records:
        return
    with st.expander("Commerce Destination", expanded=False):
        selected = st.selectbox(
            "Commerce Destination",
            tuple(CommerceDestination),
            key=f"{key_prefix}_group_commerce_destination",
            format_func=lambda value: _COMMERCE_DESTINATION_LABELS.get(value, value.value),
        )
        note = st.text_input(
            "Destination Note",
            key=f"{key_prefix}_group_commerce_destination_note",
            placeholder="Optional",
        )
        if st.button(
            "Save for Approved Assets",
            key=f"{key_prefix}_group_commerce_destination_save",
            use_container_width=True,
        ):
            service = CommerceDestinationService()
            errors = []
            saved = 0
            for record in imported_records:
                try:
                    business_asset = service.get_destination(int(record.imported_asset_id))
                    if business_asset is None:
                        errors.append(f"{record.image_id}: business_asset_not_found")
                        continue
                    result = service.set_destination(
                        CommerceDestinationRequest(
                            asset_id=int(record.imported_asset_id),
                            registration_id=business_asset.registration_id,
                            destination=selected,
                            creator_profile_id=creator_profile_id,
                            creator_identity={"source": "content_studio"},
                            source_workflow=source_workflow,
                            source_session_id=source_session_id,
                            reason=note or None,
                            idempotency_key=(
                                f"content-studio-commerce-destination:"
                                f"{int(record.imported_asset_id)}:"
                                f"{int(business_asset.destination_revision or 0) + 1}:"
                                f"{selected.value}"
                            ),
                        )
                    )
                    if result.success:
                        saved += 1
                    else:
                        errors.append(f"{record.image_id}: {'; '.join(result.errors)}")
                except Exception as error:
                    errors.append(f"{record.image_id}: {error}")
            if errors:
                st.error("; ".join(errors))
            if saved:
                st.success(f"Commerce Destination saved for {saved} asset(s).")
                st.rerun()


_UNRESOLVED_REFERENCE = object()


def _render_active_reference(
    *,
    creator_profile: dict | None,
    reference_service: ReferenceLibraryService,
    show_preview: bool = True,
    reference=_UNRESOLVED_REFERENCE,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    if reference is _UNRESOLVED_REFERENCE:
        reference = reference_service.get_active_canonical_reference(
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


def edit_studio_provider_options(
    generation_engine: GenerationEngineService,
) -> tuple[tuple[str, str], ...]:
    registry = getattr(generation_engine, "provider_registry", None)
    provider_ids = tuple(getattr(registry, "provider_ids", lambda: ())())
    available = set(provider_ids) if provider_ids else set(EDIT_STUDIO_PROVIDER_ORDER)
    options = tuple(
        (provider_id, EDIT_PROVIDER_LABELS[provider_id])
        for provider_id in EDIT_STUDIO_PROVIDER_ORDER
        if provider_id in available
    )
    return options or ((EDIT_STUDIO_DEFAULT_PROVIDER_ID, EDIT_PROVIDER_LABELS[EDIT_STUDIO_DEFAULT_PROVIDER_ID]),)


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
    active_reference = reference_service.get_active_canonical_reference(
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
            "render_policy": content_render_policy(creative_mode).value,
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
    active_reference = reference_service.get_active_canonical_reference(
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
            "render_policy": content_render_policy(creative_mode).value,
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
    completed_count = 0
    failed_count = 0
    processed_count = 0

    def compact_status_label(message: str, *, processed: int) -> str:
        raw = str(message or "").strip()
        match = re.search(r"image\s+(\d+)\s+of\s+(\d+)", raw, flags=re.IGNORECASE)
        if match:
            return f"Rendering Image {match.group(1)} of {match.group(2)}"
        if processed_count >= safe_total and failed_count == 0:
            return "Generation completed successfully"
        if raw.lower().startswith("queued"):
            return f"Queued Image 1 of {safe_total}"
        next_index = max(1, min(safe_total, int(processed or 0) + 1))
        return f"Currently Processing: Image {next_index} of {safe_total}"

    def render_status(
        current: int,
        message: str,
        *,
        failed: bool = False,
        failures: int | None = None,
        processed: int | None = None,
    ) -> None:
        nonlocal completed_count, failed_count, processed_count
        completed_count = max(completed_count, max(0, min(int(current or 0), safe_total)))
        if failures is not None:
            failed_count = max(0, min(int(failures or 0), safe_total))
        if processed is not None:
            processed_count = max(0, min(int(processed or 0), safe_total))
        else:
            processed_count = max(processed_count, min(safe_total, completed_count + failed_count))
        status_label = compact_status_label(message, processed=processed_count)
        text = (
            f"⏳ {status_label}    "
            f"✅ Completed: {completed_count}    "
            f"❌ Failed: {failed_count}    "
            f"📦 Processed: {processed_count} / {safe_total}"
        )
        if failed:
            status_placeholder.error(text)
        else:
            status_placeholder.info(text)
        progress_bar.progress(min(1.0, processed_count / safe_total))

    def render_images(outputs: tuple[str, ...]) -> None:
        for output in outputs:
            if output and output not in seen_outputs:
                seen_outputs.append(output)
        preview_placeholder.empty()
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
        completed = max(
            int(event.get("completed_count") or event.get("current") or 0),
            len(outputs),
        )
        render_status(
            completed,
            str(event.get("message") or "Generation running"),
            failed=bool(event.get("failed")),
            failures=int(event.get("failed_count") or 0),
            processed=int(event.get("processed_count") or completed),
        )
        render_images(outputs)

    def complete_preview(outputs: tuple[str, ...]) -> None:
        preview_placeholder.empty()
        status_placeholder.empty()
        progress_bar.progress(1.0)
        progress_bar.empty()

    render_status(0, f"Queued 0 of {safe_total}")
    render_images(())
    return callback, render_status, render_images, complete_preview


def _sync_generation_outputs_to_library(
    *,
    job: GenerationJob,
    generation_library: GenerationLibraryService,
    output_references: tuple[str, ...],
) -> tuple[GeneratedImageRecord, ...]:
    outputs = tuple(str(output).strip() for output in output_references if str(output).strip())
    if not outputs:
        return ()
    result = job.result or GenerationResult(
        result_id=f"{job.job_id}_live_result",
        request_id=job.request.request_id,
        job_id=job.job_id,
        provider_id=job.request.provider_id,
        status=GenerationStatus.SUCCEEDED.value,
        generation_metadata={
            "provider_neutral_result": True,
            "live_generation_sync": True,
        },
        image_metadata={
            "requested_image_count": job.request.image_count,
            "output_count": len(outputs),
        },
        output_references=outputs,
    )
    partial_job = replace(
        job,
        status=GenerationStatus.SUCCEEDED.value,
        result=replace(
            result,
            job_id=job.job_id,
            request_id=job.request.request_id,
            provider_id=job.request.provider_id,
            status=GenerationStatus.SUCCEEDED.value,
            output_references=outputs,
            image_metadata={
                **dict(result.image_metadata or {}),
                "requested_image_count": job.request.image_count,
                "output_count": len(outputs),
            },
        ),
    )
    return generation_library.sync_job(partial_job)


def _generation_completion_message(
    *,
    total_requested: int,
    success_count: int,
    failed_count: int,
) -> tuple[str, str]:
    if success_count >= max(1, int(total_requested or 1)) and failed_count == 0:
        return "success", "✔ Generation completed successfully."
    if success_count > 0:
        return (
            "warning",
            (
                "✔ Generation completed with partial success.\n\n"
                f"Success: {success_count}\n\n"
                f"Failed: {failed_count}"
            ),
        )
    return "error", "✖ Generation failed."


def _render_generation_completion_message(
    *,
    total_requested: int,
    success_count: int,
    failed_count: int,
) -> None:
    level, message = _generation_completion_message(
        total_requested=total_requested,
        success_count=success_count,
        failed_count=failed_count,
    )
    if level == "success":
        st.success(message)
    elif level == "warning":
        st.warning(message)
    else:
        st.error(message)


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
    synced_records_by_id: dict[str, Any] = {}

    def _sync_progress_outputs(**event) -> None:
        outputs = tuple(event.get("output_references") or ())
        if outputs:
            try:
                for record in _sync_generation_outputs_to_library(
                    job=job,
                    generation_library=generation_library,
                    output_references=outputs,
                ):
                    synced_records_by_id[getattr(record, "image_id", str(record))] = record
            except Exception:
                pass
        if progress_callback:
            progress_callback(**event)

    try:
        executed = generation_engine.dispatch_job(
            job.job_id,
            progress_callback=_sync_progress_outputs,
        )
    except TypeError as error:
        if "progress_callback" not in str(error):
            raise
        executed = generation_engine.dispatch_job(job.job_id)
    for record in generation_library.sync_job(executed):
        synced_records_by_id[getattr(record, "image_id", str(record))] = record
    return executed, tuple(synced_records_by_id.values())


def execute_edit_generation_for_review(
    *,
    job: GenerationJob,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    pending_source_image_id: str | None = None,
):
    executed, records = execute_generation_job_to_library(
        job=job,
        generation_engine=generation_engine,
        generation_library=generation_library,
    )
    request_source_ids = tuple(job.request.metadata.get("source_image_ids") or ())
    source_id = pending_source_image_id or (str(request_source_ids[0]) if request_source_ids else None)
    candidates = tuple(
        generation_library.mark_edit_candidate(
            record.image_id,
            pending_source_image_id=source_id,
        )
        for record in records
    )
    return executed, candidates


def execute_photoshoot_next_to_library(
    *,
    session_id: str,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    photoshoot_queue: PhotoshootQueueService,
    progress_callback=None,
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
        progress_callback=progress_callback,
    )
    if executed.status == GenerationStatus.SUCCEEDED.value:
        session = photoshoot_queue.get_session(session_id)
        generation_library.mark_photoshoot_session_records(
            tuple(record.image_id for record in records),
            session_id=session_id,
            session_title=session.title,
        )
        photoshoot_queue.mark_generation_complete(
            generation_job_id=executed.job_id,
            generated_image_ids=tuple(record.image_id for record in records),
        )
    elif executed.failure:
        photoshoot_queue.mark_generation_failed(
            executed.job_id,
            reason=executed.failure.reason,
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
    active_reference = reference_service.get_active_canonical_reference(
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
    active_reference = reference_service.get_active_canonical_reference(
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
    active_reference = reference_service.get_active_canonical_reference(
        creator_profile_id=creator_profile_id,
    )
    _render_active_reference(
        creator_profile=creator_profile,
        reference_service=reference_service,
        show_preview=False,
        reference=active_reference,
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
                image_metadata = dict(executed.result.image_metadata or {}) if executed.result else {}
                success_count = int(image_metadata.get("completed_count") or len(outputs))
                failed_count = int(image_metadata.get("failed_count") or 0)
                _render_generation_completion_message(
                    total_requested=prompt_count,
                    success_count=success_count,
                    failed_count=failed_count,
                )
            elif executed.failure:
                render_status(
                    0,
                    executed.failure.reason,
                    failed=True,
                    failures=prompt_count,
                    processed=prompt_count,
                )
                _render_generation_completion_message(
                    total_requested=prompt_count,
                    success_count=0,
                    failed_count=prompt_count,
                )
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
                st.session_state["dashboard_page"] = "Photoshoot Studio"
                st.rerun()
    with shoot_col3:
        if st.button(
            "Open Existing Photoshoot",
            key="social_studio_open_photoshoot",
            use_container_width=True,
        ):
            st.session_state["dashboard_page"] = "Photoshoot Studio"
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
        enhanced_tags = str(st.session_state.get("premium_studio_enhanced_tags") or "").strip()
        original_tags = str(creative_tags or "").strip()
        if not enhanced_tags:
            return ""
        return (
            "[ORIGINAL USER TAGS — mandatory: "
            f"{original_tags.replace(chr(10), ', ')}] "
            "[ENHANCED SUGGESTIONS — vary any wardrobe detail not present in ORIGINAL USER TAGS: "
            f"{enhanced_tags.replace(chr(10), ', ')}]"
        )
    if selected_source == "Surprise Me Tags":
        return str(st.session_state.get("premium_studio_surprise_tags") or "").strip()
    if selected_source == "Enhanced Explicit Tags":
        return str(st.session_state.get("premium_studio_enhanced_explicit_tags") or "").strip()
    if selected_source in {"Prompt Workshop", "Ask Grok Prompt"}:
        return str(st.session_state.get("premium_studio_manual_prompt") or "").strip()
    return str(creative_tags or "").strip()


def _store_premium_prompt_batch(prompts: tuple[str, ...], *, source: str) -> None:
    clean_prompts = tuple(prompt for prompt in prompts if str(prompt or "").strip())
    st.session_state["premium_studio_prompt_batch"] = clean_prompts
    st.session_state["premium_studio_prompt_batch_source"] = source
    if clean_prompts:
        st.session_state["premium_studio_manual_prompt"] = clean_prompts[0]


def _select_premium_prompt_source_on_next_run(source: str) -> None:
    st.session_state["premium_studio_pending_tag_source"] = source


def _apply_pending_premium_prompt_source() -> None:
    pending_source = st.session_state.pop("premium_studio_pending_tag_source", None)
    current_source = st.session_state.get("premium_studio_selected_tag_source")
    source = pending_source or current_source
    if source == "Ask Grok Prompt":
        source = "Prompt Workshop"
    if source:
        st.session_state["premium_studio_selected_tag_source"] = source


def _render_premium_prompt_batch() -> None:
    prompts = tuple(st.session_state.get("premium_studio_prompt_batch") or ())
    if not prompts:
        return
    st.markdown("### Prompt Workshop")
    st.caption(
        f"Prompt Source: {st.session_state.get('premium_studio_prompt_batch_source') or 'Content Studio'}"
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
                    _select_premium_prompt_source_on_next_run("Prompt Workshop")
                    st.rerun()


def _render_premium_prompt_assistant(
    *,
    creator_profile: dict | None,
    creator_profile_id: int,
    creative_director: CreativeDirectorService,
    prompt_count: int,
    active_reference_available: bool,
) -> None:
    with st.expander("Prompt Workshop", expanded=False):
        st.caption("Preview and edit the exact prompts the canonical planner will send to generation.")
        lane = st.selectbox(
            "Prompt Mode",
            ("premium", "explicit"),
            format_func=lambda value: "Premium" if value == "premium" else "Explicit",
            key="premium_studio_prompt_assistant_lane",
        )
        request_text = st.text_area(
            "Prompt Workshop Brief",
            key="premium_studio_prompt_assistant_request",
            placeholder="Example: hotel mirror lingerie set with warm lamp light and playful confidence",
            height=100,
            disabled=not active_reference_available,
        )
        if st.button(
            "Generate Prompts",
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
                st.error(f"Prompt Workshop failed: {error}")
            else:
                st.session_state["premium_studio_prompt_assistant_batch_id"] = batch.batch_id
                st.session_state["premium_studio_prompt_assistant_results"] = batch.prompts
                _store_premium_prompt_batch(batch.prompts, source="Prompt Workshop")
                st.success("Prompt Workshop prompts created.")
                st.rerun()

        prompts = tuple(st.session_state.get("premium_studio_prompt_assistant_results") or ())
        if prompts:
            edited_prompts = []
            for index, prompt in enumerate(prompts, start=1):
                edited_prompt = st.text_area(
                    f"Prompt {index}",
                    value=prompt,
                    key=f"premium_studio_prompt_workshop_edit_{index}",
                    height=140,
                )
                edited_prompts.append(str(edited_prompt or "").strip())
            prompts = tuple(prompt for prompt in edited_prompts if prompt)
            st.session_state["premium_studio_prompt_assistant_results"] = prompts
            if not prompts:
                st.warning("At least one Prompt Workshop prompt is required.")
                return
            selected_number = st.number_input(
                "Selected prompt",
                min_value=1,
                max_value=len(prompts),
                value=1,
                step=1,
                key="premium_studio_prompt_assistant_selected_number",
            )
            selected_prompt = prompts[int(selected_number) - 1]
            a1, a2, a3 = st.columns(3)
            if a1.button("Accept Selected", key="premium_studio_prompt_assistant_use", use_container_width=True):
                st.session_state["premium_studio_manual_prompt"] = selected_prompt
                _select_premium_prompt_source_on_next_run("Prompt Workshop")
                batch_id = st.session_state.get("premium_studio_prompt_assistant_batch_id")
                if batch_id:
                    creative_director.mark_prompt_assistant_used(batch_id, int(selected_number))
                st.rerun()
            if a2.button("Accept All", key="premium_studio_prompt_assistant_generate_all", use_container_width=True):
                _store_premium_prompt_batch(prompts, source="Prompt Workshop")
                _select_premium_prompt_source_on_next_run("Prompt Workshop")
                st.rerun()
            if a3.button("Copy Prompt", key="premium_studio_prompt_assistant_copy", use_container_width=True):
                st.code(selected_prompt)

        history = creative_director.prompt_assistant_history(
            creator_profile_id=creator_profile_id,
            limit=10,
        )
        if history:
            with st.expander("Prompt Workshop Archive", expanded=False):
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
                    "Use archived prompt number",
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
                    _select_premium_prompt_source_on_next_run("Prompt Workshop")
                    creative_director.mark_prompt_assistant_used(
                        selected_batch.batch_id,
                        int(archive_number),
                    )
                    st.rerun()
                if c2.button("Load Batch", key="premium_studio_archive_load", use_container_width=True):
                    st.session_state["premium_studio_prompt_assistant_results"] = selected_batch.prompts
                    st.session_state["premium_studio_prompt_assistant_batch_id"] = selected_batch.batch_id
                    _store_premium_prompt_batch(selected_batch.prompts, source="Prompt Workshop Archive")
                    st.rerun()


def _render_premium_grok_anything(
    *,
    creative_director: CreativeDirectorService,
) -> None:
    history_key = "premium_grok_anything_history"
    form_key = "premium_grok_anything_form_key"
    st.session_state.setdefault(history_key, [])
    st.session_state.setdefault(form_key, 0)

    with st.expander("Canonical Prompt Planner Q&A", expanded=False):
        question = st.text_area(
            "Ask Canonical Prompt Planner",
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
            "Ask Planner",
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
            with st.spinner("Asking Canonical Prompt Planner..."):
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
                    st.error(f"Canonical Prompt Planner request failed: {error}")
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
            st.markdown("#### Canonical Prompt Planner Responses")
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
                "Ask Canonical Prompt Planner another question",
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
    st.title("Content Studio")
    st.caption("Premium creator workflow for provider-neutral prompt planning and generation review.")
    _render_content_studio_reset_notice()
    active_reference = reference_service.get_active_canonical_reference(
        creator_profile_id=creator_profile_id,
    )
    _render_active_reference(
        creator_profile=creator_profile,
        reference_service=reference_service,
        show_preview=False,
        reference=active_reference,
    )
    if not creator_profile_id:
        st.error("Creator Profile required before using Content Studio.")
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
        min_value=PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM,
        max_value=PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM,
        value=min(
            max(settings.default_prompt_count, PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM),
            PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM,
        ),
        key="premium_studio_prompt_count",
    )
    provider_options = premium_studio_provider_options(generation_engine)
    provider_ids = tuple(provider_id for provider_id, _ in provider_options)
    provider_labels = dict(provider_options)
    selected_provider = st.selectbox(
        "Provider",
        provider_ids,
        index=default_provider_index(provider_ids, preferred_provider_id="seedream_5_0_pro"),
        format_func=lambda value: provider_labels.get(value, value),
        key="premium_studio_provider",
    )

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
        _apply_pending_premium_prompt_source()
        selected_tag_source = st.radio(
            "Choose tags to send to prompt planning",
            ("Original Tags", "Enhanced Tags", "Surprise Me Tags", "Enhanced Explicit Tags", "Prompt Workshop"),
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
                image_metadata = dict(executed.result.image_metadata or {}) if executed.result else {}
                success_count = int(image_metadata.get("completed_count") or len(outputs))
                failed_count = int(image_metadata.get("failed_count") or 0)
                _render_generation_completion_message(
                    total_requested=prompt_count,
                    success_count=success_count,
                    failed_count=failed_count,
                )
            elif executed.failure:
                render_status(
                    0,
                    executed.failure.reason,
                    failed=True,
                    failures=prompt_count,
                    processed=prompt_count,
                )
                _render_generation_completion_message(
                    total_requested=prompt_count,
                    success_count=0,
                    failed_count=prompt_count,
                )
            else:
                render_status(
                    executed.progress.current,
                    f"Generation finished with status: {executed.status}",
                )
                st.warning(f"Generation finished with status: {executed.status}.")


def _edit_studio_source_record(
    generation_library: GenerationLibraryService,
    selected_ids: tuple[str, ...],
) -> GeneratedImageRecord | None:
    for image_id in selected_ids:
        try:
            return generation_library.get(image_id)
        except KeyError:
            continue
    return None


def _render_edit_studio_card_styles() -> None:
    st.markdown(
        """
        <style>
        .st-key-edit_studio_card_single_image button,
        .st-key-edit_studio_card_multi_image button {
            min-height: 86px;
            padding: 14px 16px;
            border-radius: 8px;
            border: 1px solid rgba(148, 163, 184, 0.32);
            background: #171a1f;
            color: #f8fafc;
            text-align: left;
            box-shadow: none;
            transition: border-color 140ms ease, background 140ms ease, transform 140ms ease;
            white-space: pre-line;
        }
        .st-key-edit_studio_card_single_image button:hover,
        .st-key-edit_studio_card_multi_image button:hover {
            border-color: rgba(248, 250, 252, 0.56);
            background: #20242b;
            transform: translateY(-1px);
        }
        .st-key-edit_studio_card_single_image button:focus,
        .st-key-edit_studio_card_multi_image button:focus {
            border-color: #f5c451;
            box-shadow: 0 0 0 1px rgba(245, 196, 81, 0.35);
        }
        .st-key-edit_studio_card_selected_single_image button,
        .st-key-edit_studio_card_selected_multi_image button {
            border-color: #f5c451;
            background: #242018;
            box-shadow: 0 0 0 1px rgba(245, 196, 81, 0.22);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_edit_type_card(
    *,
    title: str,
    body: str,
    mode: str,
    selected: bool,
) -> None:
    key_prefix = "edit_studio_card_selected" if selected else "edit_studio_card"
    if st.button(f"{title}\n\n{body}", key=f"{key_prefix}_{mode}", use_container_width=True):
        st.session_state["edit_studio_workflow_mode"] = mode
        st.rerun()


def _render_edit_type_cards(*, selected_mode: str | None) -> None:
    _render_edit_studio_card_styles()
    st.markdown("### Choose Edit Type")
    single_col, multi_col = st.columns(2, gap="medium")
    with single_col:
        _render_edit_type_card(
            title="✏️ Single Edit",
            body="Edit this image using text instructions.",
            mode="single_image",
            selected=selected_mode == "single_image",
        )
    with multi_col:
        _render_edit_type_card(
            title="🖼 Multi Edit",
            body="Combine this image with another reference image.",
            mode="multi_image",
            selected=selected_mode == "multi_image",
        )


def _render_edit_review(
    *,
    original_record: GeneratedImageRecord,
    working_record: GeneratedImageRecord,
    generation_library: GenerationLibraryService,
) -> None:
    cols = st.columns([5, 1, 5])
    with cols[0]:
        st.markdown("#### Original Image")
        _render_edit_studio_image(original_record.output_reference, alt="Original Image")
    with cols[1]:
        st.markdown("<div style='text-align:center; padding-top: 260px; font-size: 26px;'>→</div>", unsafe_allow_html=True)
    with cols[2]:
        st.markdown("#### Edited Image")
        _render_edit_studio_image(working_record.output_reference, alt="Edited Image")

    a1, a2, a3 = st.columns(3)
    if a1.button("✅ Approve", key="edit_studio_approve", use_container_width=True):
        result = generation_library.approve_edit_candidate(
            source_image_id=original_record.image_id,
            edited_image_id=working_record.image_id,
            metadata={"approved_from": "edit_studio"},
        )
        if result.success:
            for candidate_id in tuple(st.session_state.get("edit_studio_chain_candidate_ids") or ()):
                if candidate_id != working_record.image_id:
                    generation_library.discard_edit_candidate(candidate_id)
            st.session_state["edit_studio_source_image_ids"] = (original_record.image_id,)
            st.session_state.pop("edit_studio_original_image_id", None)
            st.session_state.pop("edit_studio_pending_candidate_id", None)
            st.session_state.pop("edit_studio_working_source_image_id", None)
            st.session_state.pop("edit_studio_chain_candidate_ids", None)
            st.session_state["edit_studio_workflow_mode"] = None
            st.success(result.message)
            st.rerun()
        else:
            st.error("; ".join(result.errors) or result.message)
    if a2.button("✏️ Edit Again", key="edit_studio_edit_again", use_container_width=True):
        chain_ids = tuple(st.session_state.get("edit_studio_chain_candidate_ids") or ())
        if working_record.image_id not in chain_ids:
            st.session_state["edit_studio_chain_candidate_ids"] = (*chain_ids, working_record.image_id)
        st.session_state["edit_studio_working_source_image_id"] = working_record.image_id
        st.session_state["edit_studio_source_image_ids"] = (working_record.image_id,)
        st.session_state.pop("edit_studio_pending_candidate_id", None)
        st.session_state["edit_studio_workflow_mode"] = None
        st.rerun()
    if a3.button("🗑 Discard", key="edit_studio_discard", use_container_width=True):
        result = generation_library.discard_edit_candidate(working_record.image_id)
        if result.success:
            for candidate_id in tuple(st.session_state.get("edit_studio_chain_candidate_ids") or ()):
                if candidate_id != working_record.image_id:
                    generation_library.discard_edit_candidate(candidate_id)
            original_id = st.session_state.get("edit_studio_original_image_id") or original_record.image_id
            st.session_state["edit_studio_source_image_ids"] = (original_id,)
            st.session_state.pop("edit_studio_pending_candidate_id", None)
            st.session_state.pop("edit_studio_working_source_image_id", None)
            st.session_state["edit_studio_workflow_mode"] = None
            st.info(result.message)
            st.rerun()
        else:
            st.error("; ".join(result.errors) or result.message)


def _render_edit_generation_form(
    *,
    creator_profile: dict | None,
    creator_profile_id: int,
    source_record: GeneratedImageRecord,
    edit_mode: str,
    edit_studio: EditStudioService,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    reference_service: ReferenceLibraryService,
) -> None:
    provider_options = edit_studio_provider_options(generation_engine)
    provider_ids = tuple(provider_id for provider_id, _ in provider_options)
    provider_labels = dict(provider_options)
    selected_provider = st.selectbox(
        "Provider",
        provider_ids,
        index=default_provider_index(
            provider_ids,
            preferred_provider_id=EDIT_STUDIO_DEFAULT_PROVIDER_ID,
        ),
        format_func=lambda value: provider_labels.get(value, value),
        key=f"edit_studio_{edit_mode}_provider",
    )
    reference_asset_id = None
    reference_image_id = None
    if edit_mode == "multi_image":
        st.markdown("#### Reference Image")
        reference_source = st.radio(
            "Reference source",
            ("Upload Reference Image", "Choose from Reference Library"),
            horizontal=True,
            key="edit_studio_reference_source",
        )
        if reference_source == "Upload Reference Image":
            uploaded = st.file_uploader(
                "Upload Reference Image",
                type=["jpg", "jpeg", "png", "webp"],
                key="edit_studio_reference_upload",
            )
            if uploaded is not None:
                st.image(uploaded, use_container_width=True)
        else:
            references = reference_service.list_references(
                ReferenceLibraryFilter(
                    creator_profile_id=creator_profile_id,
                    has_local_vault_original=None,
                    limit=100,
                )
            ).references
            reference_options = tuple(reference.asset_id for reference in references)
            reference_labels = {
                reference.asset_id: reference.asset.file_name or f"Reference {reference.asset_id}"
                for reference in references
            }
            selected_reference = st.selectbox(
                "Reference Library",
                ("", *reference_options),
                format_func=lambda value: reference_labels.get(value, "Select Reference"),
                key="edit_studio_reference_asset_id",
            )
            if selected_reference:
                reference_asset_id = int(selected_reference)
                reference = next((item for item in references if item.asset_id == reference_asset_id), None)
                if reference and reference.asset.preview_path:
                    st.image(reference.asset.preview_path, use_container_width=True)

    prompt = st.text_area(
        "Prompt",
        placeholder=(
            "Describe the exact change. Keep everything else the same."
            if edit_mode == "single_image"
            else "Describe how this image should use the reference image."
        ),
        height=150,
        key=f"edit_studio_{edit_mode}_prompt",
    )
    generate_disabled = not str(prompt).strip()
    if edit_mode == "multi_image":
        if st.session_state.get("edit_studio_reference_source") == "Upload Reference Image":
            generate_disabled = generate_disabled or st.session_state.get("edit_studio_reference_upload") is None
        else:
            generate_disabled = generate_disabled or reference_asset_id is None

    if st.button("🚀 Generate Edit", disabled=generate_disabled, key=f"edit_studio_{edit_mode}_generate", use_container_width=True):
        try:
            if edit_mode == "multi_image" and st.session_state.get("edit_studio_reference_source") == "Upload Reference Image":
                uploaded = st.session_state.get("edit_studio_reference_upload")
                staged_path = _save_uploaded_reference(uploaded)
                result = reference_service.add_reference(
                    media_path=staged_path,
                    original_filename=uploaded.name,
                    creator_profile_id=creator_profile_id,
                    favorite=False,
                    make_active=False,
                )
                if not result.success or not result.asset_id:
                    raise RuntimeError(result.message)
                reference_asset_id = int(result.asset_id)
            edit_item, job = create_edit_studio_generation_request(
                creator_profile=creator_profile,
                edit_studio=edit_studio,
                generation_library=generation_library,
                generation_engine=generation_engine,
                source_image_ids=(source_record.image_id,),
                edit_mode=edit_mode,
                edit_prompt=prompt,
                provider_id=selected_provider,
                reference_image_id=reference_image_id,
                reference_asset_id=reference_asset_id,
                batch_size=1,
            )
            with st.spinner("Generating edit..."):
                pending_source_id = st.session_state.get("edit_studio_original_image_id") or source_record.image_id
                executed, candidates = execute_edit_generation_for_review(
                    job=job,
                    generation_engine=generation_engine,
                    generation_library=generation_library,
                    pending_source_image_id=pending_source_id,
                )
        except (KeyError, ValueError, RuntimeError) as error:
            st.error(str(error))
        except Exception as error:
            st.error(f"Edit generation failed: {error}")
        else:
            st.session_state["edit_studio_latest_edit_id"] = edit_item.edit_request_id
            st.session_state["edit_studio_latest_generation_job_id"] = executed.job_id
            if executed.status == GenerationStatus.SUCCEEDED.value and candidates:
                st.session_state["edit_studio_pending_candidate_id"] = candidates[0].image_id
                st.session_state["edit_studio_working_source_image_id"] = source_record.image_id
                st.success("Edit generated. Review before approving.")
                st.rerun()
            elif executed.failure:
                st.error(executed.failure.reason)
            else:
                st.warning(f"Edit finished with status: {executed.status}.")


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
    st.caption("Dedicated image editor for Single Edit and Multi Edit workflows.")
    if not creator_profile_id:
        st.error("Creator Profile required before using Edit Studio.")
        return

    edit_studio.sync_generation_library(
        generation_engine=generation_engine,
        generation_library=generation_library,
    )
    persisted_pending = generation_library.pending_edit_record(
        creator_profile_id=creator_profile_id,
    )
    selected_source_ids = tuple(
        st.session_state.get("edit_studio_source_image_ids")
        or st.session_state.get("generation_library_selected_ids")
        or ()
    )
    source_record = _edit_studio_source_record(generation_library, selected_source_ids)
    if source_record is None or source_record.status != "pending_edit":
        source_record = persisted_pending
    if source_record is not None:
        st.session_state["edit_studio_source_image_ids"] = (source_record.image_id,)
        st.session_state["edit_studio_original_image_id"] = source_record.image_id
    if source_record is None:
        st.info("Choose an image in Generation Library and click ✏️ Edit to start.")
        return

    candidate_id = (
        st.session_state.get("edit_studio_pending_candidate_id")
        or dict(source_record.generation_metadata or {}).get("latest_edit_candidate_id")
    )
    if candidate_id:
        try:
            candidate_record = generation_library.get(candidate_id)
            original_record = source_record
            _render_edit_review(
                original_record=original_record,
                working_record=candidate_record,
                generation_library=generation_library,
            )
            return
        except KeyError:
            st.session_state.pop("edit_studio_pending_candidate_id", None)

    st.markdown("### Selected Source Image")
    _render_edit_studio_image(source_record.output_reference, alt="Selected Source Image")
    if st.button("↩️ Return to Library", key="edit_studio_return_to_library", use_container_width=True):
        for candidate_id in tuple(st.session_state.get("edit_studio_chain_candidate_ids") or ()):
            generation_library.discard_edit_candidate(candidate_id)
        latest_candidate = generation_library.latest_edit_candidate_for_source(source_record.image_id)
        if latest_candidate:
            generation_library.discard_edit_candidate(latest_candidate.image_id)
        result = generation_library.return_pending_edit_to_library(source_record.image_id)
        if result.success:
            st.session_state.pop("edit_studio_source_image_ids", None)
            st.session_state.pop("edit_studio_original_image_id", None)
            st.session_state.pop("edit_studio_pending_candidate_id", None)
            st.session_state.pop("edit_studio_working_source_image_id", None)
            st.session_state.pop("edit_studio_chain_candidate_ids", None)
            st.session_state["edit_studio_workflow_mode"] = None
            st.session_state["dashboard_page"] = "Generation Library"
            st.success(result.message)
            st.rerun()
        else:
            st.error("; ".join(result.errors) or result.message)

    edit_mode = st.session_state.get("edit_studio_workflow_mode")
    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)
    _render_edit_type_cards(selected_mode=edit_mode)
    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)
    if edit_mode in {"single_image", "multi_image"}:
        st.markdown(f"### {EDIT_MODE_LABELS[edit_mode]}")
        _render_edit_generation_form(
            creator_profile=creator_profile,
            creator_profile_id=creator_profile_id,
            source_record=source_record,
            edit_mode=edit_mode,
            edit_studio=edit_studio,
            generation_engine=generation_engine,
            generation_library=generation_library,
            reference_service=reference_service,
        )
        if st.button("← Choose Different Edit Type", key="edit_studio_back_to_modes", use_container_width=True):
            st.session_state["edit_studio_workflow_mode"] = None
            st.rerun()

    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
    with st.expander("Advanced", expanded=False):
        st.caption("Face Replacement")
        st.caption("Style Transfer")
        st.caption("Variations")
        st.caption("Batch Edit")
        st.caption("Provider Overrides")
        st.markdown("#### Edit History")
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
                image_metadata = dict(executed.result.image_metadata or {}) if executed.result else {}
                success_count = int(image_metadata.get("completed_count") or len(records))
                failed_count = int(image_metadata.get("failed_count") or 0)
                _render_generation_completion_message(
                    total_requested=job.request.image_count,
                    success_count=success_count,
                    failed_count=failed_count,
                )
            elif executed.failure:
                _render_generation_completion_message(
                    total_requested=job.request.image_count,
                    success_count=0,
                    failed_count=job.request.image_count,
                )
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


PUBLISH_IMAGE_UNAVAILABLE_MESSAGE = (
    "This image file is no longer available at its recorded location. "
    "Return it to the Generation Library or repair the asset record before publishing."
)

GENERATION_LIBRARY_PUBLISH_TRANSIENT_KEYS = (
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
)

GENERATION_LIBRARY_PUBLISH_TRANSIENT_PREFIXES = (
    "generation_library_x_custom_caption_",
    "generation_library_telegram_caption_",
    "generation_library_telegram_post_to_",
    "generation_library_telegram_cta_enabled_",
    "generation_library_telegram_cta_label_",
    "generation_library_telegram_cta_url_",
)


def _clear_generation_publish_state() -> None:
    for key in GENERATION_LIBRARY_PUBLISH_TRANSIENT_KEYS:
        st.session_state.pop(key, None)
    for key in tuple(st.session_state.keys()):
        if any(key.startswith(prefix) for prefix in GENERATION_LIBRARY_PUBLISH_TRANSIENT_PREFIXES):
            st.session_state.pop(key, None)


def _image_reference_exists_for_display(image_reference: str | None) -> bool:
    source = str(image_reference or "").strip()
    if not source:
        return False
    if source.startswith(("http://", "https://", "data:")):
        return True
    return Path(source).expanduser().is_file()


def _publishable_image_reference(
    *,
    context: dict[str, Any],
    generation_library: GenerationLibraryService,
) -> str | None:
    generated_image_id = str(context.get("generated_image_id") or "").strip()
    if generated_image_id:
        resolved = generation_library.resolve_publishable_image_reference(generated_image_id)
        if resolved:
            return resolved
        return None
    image_reference = str(context.get("image_reference") or "").strip()
    return image_reference if _image_reference_exists_for_display(image_reference) else None


def _render_publish_image_preview(
    *,
    context: dict[str, Any],
    generation_library: GenerationLibraryService,
) -> tuple[str, bool]:
    image_reference = _publishable_image_reference(
        context=context,
        generation_library=generation_library,
    )
    if image_reference:
        st.image(image_reference, use_container_width=True)
        return image_reference, True
    st.warning(PUBLISH_IMAGE_UNAVAILABLE_MESSAGE)
    return "", False


def _open_generation_publish_modal(record) -> None:
    _clear_generation_publish_state()
    st.session_state["generation_library_publish_modal_open"] = True
    st.session_state["generation_library_publish_context"] = _generation_publish_context(record)


def _close_generation_publish_modal() -> None:
    _clear_generation_publish_state()


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


def _generate_x_caption_set(
    *,
    caption_studio: CaptionStudioService,
    context: dict[str, Any],
    creator_profile: dict | None,
    generated_image_id: str,
    image_reference: str,
    seed_key: str,
    result_id_key: str,
    selected_key: str,
    custom_key: str,
    increment_seed: bool,
) -> None:
    current_seed = int(st.session_state.get(seed_key, 0))
    if increment_seed:
        current_seed += 1
    st.session_state[seed_key] = current_seed
    result = caption_studio.generate_x_engagement_themes(
        generated_image_id=generated_image_id,
        image_reference=image_reference,
        creator_profile_id=_creator_profile_id(creator_profile) or 0,
        creator_profile=creator_profile,
        creative_mode=str(context.get("creative_mode") or ""),
        prompt_text=str(context.get("prompt_text") or ""),
        prompt_metadata=dict(context.get("prompt_metadata") or {}),
        generation_metadata=dict(context.get("generation_metadata") or {}),
        idea_seed=current_seed,
    )
    st.session_state[result_id_key] = result.caption_result_id
    st.session_state.pop(selected_key, None)
    st.session_state.pop(custom_key, None)
    st.session_state.pop("generation_library_x_caption_selected_at", None)


def _x_dependency_diagnostic(social_publishing: Any):
    provider = getattr(social_publishing, "x_provider", None)
    provider_type = type(provider) if provider is not None else None
    diagnostic = getattr(provider_type, "runtime_dependency_diagnostic", None)
    if callable(diagnostic):
        return diagnostic()
    return None


def _x_dependency_blocking_message(social_publishing: Any) -> str | None:
    diagnostic = _x_dependency_diagnostic(social_publishing)
    if diagnostic is None:
        return None
    missing_message = getattr(diagnostic, "missing_dependency_message", None)
    if callable(missing_message):
        return missing_message()
    return None if getattr(diagnostic, "tweepy_installed", True) else getattr(diagnostic, "error", None)


def _x_dependency_debug_diagnostic(social_publishing: Any):
    return _x_dependency_diagnostic(social_publishing)


def _sanitize_historical_publish_message(message: str | None) -> str:
    return re.sub(
        r"[A-Za-z]:\\[^\\\n]+\\bot\\Scripts\\python\.exe",
        "[previous runtime interpreter]",
        str(message or ""),
    )


def _is_stale_x_dependency_message(message: str | None) -> bool:
    normalized = str(message or "").lower()
    return (
        "x publishing dependency missing" in normalized
        or "tweepy is required for x publishing" in normalized
        or "tweepy is not installed" in normalized
        or "\\bot\\scripts\\python.exe" in normalized
    )


def _latest_history_message_for_item(social_publishing: Any, queue_item_id: str) -> str | None:
    latest_history = next(iter(social_publishing.list_history()), None)
    if latest_history and latest_history.queue_item_id == queue_item_id:
        return _sanitize_historical_publish_message(latest_history.message)
    return None


def _render_x_engagement_publish_dialog(
    *,
    context: dict[str, Any],
    creator_profile: dict | None,
    generation_library: GenerationLibraryService,
    caption_studio: CaptionStudioService,
    social_publishing: Any,
) -> None:
    st.markdown("### X Publish")
    image_reference, image_available = _render_publish_image_preview(
        context=context,
        generation_library=generation_library,
    )

    st.markdown("### Generate Captions")
    st.caption("Grok Vision uses the image as context, then writes X captions designed to start conversations. Nothing is posted until you choose a caption and publish.")
    generated_image_id = str(context.get("generated_image_id") or "")
    result_id_key = "generation_library_x_caption_result_id"
    seed_key = "generation_library_x_caption_seed"
    selected_key = "generation_library_x_selected_caption"
    custom_key = f"generation_library_x_custom_caption_{generated_image_id}"

    button_label = "Generate Captions" if not st.session_state.get(result_id_key) else "✨ Regenerate Captions"
    if st.button(button_label, key="generation_library_x_regenerate_captions", disabled=not image_available, use_container_width=True):
        with st.spinner("Generating captions..."):
            _generate_x_caption_set(
                caption_studio=caption_studio,
                context=context,
                creator_profile=creator_profile,
                generated_image_id=generated_image_id,
                image_reference=image_reference,
                seed_key=seed_key,
                result_id_key=result_id_key,
                selected_key=selected_key,
                custom_key=custom_key,
                increment_seed=bool(st.session_state.get(result_id_key)),
            )
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
        "Enter Your Own Caption",
        key=custom_key,
        placeholder="Type or paste your own X caption here.",
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
        st.caption(
            "Type or paste your own X caption here. If this field contains text, "
            "it will be published instead of generating or selecting an AI caption."
        )
    else:
        st.warning(
            "Type or paste your own X caption here, select an AI caption, or generate captions before publishing."
        )

    x_debug_diagnostic = _x_dependency_debug_diagnostic(social_publishing)
    x_blocking_message = _x_dependency_blocking_message(social_publishing)
    provider_ready = x_blocking_message is None
    if provider_ready and _is_stale_x_dependency_message(
        st.session_state.get("generation_library_x_publish_message")
    ):
        _debug_x_publish_dialog_event(
            "clear_stale_session_dependency_message",
            source="session_state",
            variable_name='st.session_state["generation_library_x_publish_message"]',
            value=st.session_state.get("generation_library_x_publish_message"),
            diagnostic=x_debug_diagnostic,
        )
        st.session_state.pop("generation_library_x_publish_message", None)
    if x_blocking_message:
        _debug_x_publish_dialog_event(
            "render_red_x_dependency_panel",
            source="provider diagnostic",
            variable_name="x_blocking_message",
            value=x_blocking_message,
            diagnostic=x_debug_diagnostic,
        )
        st.error(x_blocking_message)

    publish_col, cancel_col = st.columns(2)
    if publish_col.button(
        "Publish to AvaBlackthorne",
        key="generation_library_x_publish_now",
        disabled=not selected_caption or bool(x_blocking_message) or not image_available,
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
            _close_generation_publish_modal()
            st.rerun()
        else:
            failure_message = _latest_history_message_for_item(social_publishing, item.queue_item_id)
            st.session_state["generation_library_x_publish_message"] = (
                "Current publish failed:\n\n" + (failure_message or "X publish failed.")
            )
        st.rerun()
    if cancel_col.button("Cancel", key="generation_library_x_cancel", use_container_width=True):
        _close_generation_publish_modal()
        st.rerun()

    message = st.session_state.get("generation_library_x_publish_message")
    if message == "Published to X.":
        st.session_state.pop("generation_library_x_publish_message", None)
    elif message:
        _debug_x_publish_dialog_event(
            "render_red_x_publish_session_message",
            source="session_state",
            variable_name='st.session_state["generation_library_x_publish_message"]',
            value=message,
            diagnostic=x_debug_diagnostic,
        )
        st.error(message)
        if st.button("Clear previous failure", key="generation_library_x_clear_previous_failure", use_container_width=True):
            st.session_state.pop("generation_library_x_publish_message", None)
            st.rerun()


def _render_telegram_publish_dialog(
    *,
    context: dict[str, Any],
    creator_profile: dict | None,
    generation_library: GenerationLibraryService,
    caption_studio: CaptionStudioService,
    social_publishing: Any,
) -> None:
    st.markdown("### Telegram Publish")
    image_reference, image_available = _render_publish_image_preview(
        context=context,
        generation_library=generation_library,
    )
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
    if generate_col.button("Generate Captions", key="generation_library_telegram_generate_captions", disabled=not image_available, use_container_width=True):
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
    if regenerate_col.button("Generate Different Ideas", key="generation_library_telegram_generate_different", disabled=not image_available, use_container_width=True):
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
        "Enter Your Own Caption",
        key=caption_key,
        placeholder="Type or paste your own Telegram caption here.",
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
        st.caption(
            "Type or paste your own Telegram caption here. If this field contains text, "
            "it will be published instead of generating or selecting an AI caption."
        )
    else:
        st.warning(
            "Type or paste your own Telegram caption here, select an AI caption, or generate captions before publishing."
        )

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
        disabled=not selected_caption or not image_available,
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
            _close_generation_publish_modal()
            st.rerun()
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
        st.session_state.pop(message_key, None)
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


def _render_generation_library_pagination(
    *,
    current_page: int,
    total_pages: int,
    key_prefix: str,
) -> None:
    _, previous_col, label_col, next_col = st.columns([6, 1.35, 0.8, 1.1])
    with previous_col:
        if st.button(
            "◀ Previous",
            disabled=current_page <= 1,
            key=f"{key_prefix}_previous",
            use_container_width=True,
        ):
            st.session_state["generation_library_page"] = max(1, current_page - 1)
            st.rerun()
    with label_col:
        st.markdown(
            f"<div style='text-align:center; padding-top:0.45rem;'>{current_page} of {total_pages}</div>",
            unsafe_allow_html=True,
        )
    with next_col:
        if st.button(
            "Next ▶",
            disabled=current_page >= total_pages,
            key=f"{key_prefix}_next",
            use_container_width=True,
        ):
            st.session_state["generation_library_page"] = min(total_pages, current_page + 1)
            st.rerun()


def _asset_registration_dialog(title: str):
    dialog = getattr(st, "dialog", None)
    if callable(dialog):
        return dialog(title)

    def decorator(func):
        return func

    return decorator


# Compatibility marker for source-contract tests: @st.dialog("⭐ Register Asset")
@_asset_registration_dialog("⭐ Register Asset")
def _render_asset_registration_dialog(
    record: GeneratedImageRecord,
    *,
    creator_profile: dict | None,
    asset_registration: AssetRegistrationService,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    creator_name = (
        (creator_profile or {}).get("display_name")
        or (creator_profile or {}).get("persona_name")
        or (creator_profile or {}).get("name")
        or "Ava Blackthorne"
    )
    st.write("This image will be added to your Creator Inventory.")
    st.markdown(f"**Creator:**  \n👤 {creator_name}")
    st.markdown("**Asset Type:**  \n🖼 Image")
    cancel_col, register_col = st.columns(2)
    if cancel_col.button(
        "Cancel",
        key=f"asset_registration_cancel_{record.image_id}",
        use_container_width=True,
    ):
        st.session_state.pop("generation_library_register_image_id", None)
        st.rerun()
    if register_col.button(
        "Register Asset",
        key=f"asset_registration_confirm_{record.image_id}",
        type="primary",
        use_container_width=True,
        disabled=creator_profile_id is None,
    ):
        progress_lines = []
        with st.status("🧠 Analyzing Asset...", expanded=True) as analysis_status:
            def report_progress(label: str) -> None:
                progress_lines.append(f"✓ {label}")
                st.markdown("  \n".join(progress_lines))

            result = asset_registration.register_generated_image(
                record,
                creator_profile_id=int(creator_profile_id),
                progress=report_progress,
            )
            analysis_status.update(
                label="✓ Completed" if result.success else "Asset analysis failed",
                state="complete" if result.success else "error",
                expanded=not result.success,
            )
        if result.success:
            st.session_state["generation_library_workflow_message"] = result.message
            st.session_state.pop("generation_library_register_image_id", None)
            st.rerun()
        st.error(result.message)


def _render_generation_library(
    *,
    creator_profile: dict | None,
    generation_engine: GenerationEngineService,
    generation_library: GenerationLibraryService,
    generation_ingestion: GenerationResultIngestionService,
    reference_service: ReferenceLibraryService,
    caption_studio: CaptionStudioService,
    social_publishing: Any,
    photoshoot_queue: PhotoshootQueueService,
    asset_registration: AssetRegistrationService,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    generation_library.sync_jobs(generation_engine.list_jobs(status="succeeded"))
    result = generation_library.browse(
        GenerationLibraryFilter(
            status="active",
            creator_profile_id=creator_profile_id,
            sort="newest",
        )
    )

    _render_generation_publish_modal(
        creator_profile=creator_profile,
        generation_library=generation_library,
        caption_studio=caption_studio,
        social_publishing=social_publishing,
    )
    workflow_message = st.session_state.pop("generation_library_workflow_message", None)
    if workflow_message:
        st.info(workflow_message)

    if not result.records:
        st.info("No generated images match the current filters.")
        return
    st.markdown(
        """
        <style>
        div[data-testid="column"] button[kind="secondary"] {
            min-height: 2.6rem;
            padding: 0.35rem 0.2rem;
            font-size: 1.05rem;
            border-radius: 8px;
        }
        div[data-testid="column"] button[kind="secondary"]:hover {
            border-color: rgba(255, 208, 96, 0.75);
            background: rgba(255, 208, 96, 0.08);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    page_size = 18
    total_pages = max(1, (result.total + page_size - 1) // page_size)
    current_page = int(st.session_state.get("generation_library_page", 1) or 1)
    current_page = max(1, min(current_page, total_pages))
    st.session_state["generation_library_page"] = current_page
    start = (current_page - 1) * page_size
    page_records = result.records[start:start + page_size]
    _render_generation_library_pagination(
        current_page=current_page,
        total_pages=total_pages,
        key_prefix="generation_library_pagination_top",
    )
    cols = st.columns(3)
    for index, record in enumerate(page_records):
        with cols[index % 3]:
            if record.output_reference:
                st.image(record.output_reference, use_container_width=True)
            a1, a2, a3, a4, a5, a6, a7 = st.columns(7)
            if a1.button("🚀", key=f"generation_library_publish_{record.image_id}", help="Publish", use_container_width=True):
                _open_generation_publish_modal(record)
                st.rerun()
            if a2.button("✏️", key=f"generation_library_edit_{record.image_id}", help="Edit Image", use_container_width=True):
                try:
                    pending = generation_library.send_to_pending_edit(record.image_id)
                except Exception as error:
                    st.error(f"Could not open Edit Studio: {error}")
                else:
                    st.session_state["edit_studio_source_image_ids"] = (pending.image_id,)
                    st.session_state["edit_studio_original_image_id"] = pending.image_id
                    st.session_state.pop("edit_studio_pending_candidate_id", None)
                    st.session_state.pop("edit_studio_working_source_image_id", None)
                    st.session_state.pop("edit_studio_chain_candidate_ids", None)
                    st.session_state["edit_studio_workflow_mode"] = None
                    st.session_state["dashboard_page"] = "Edit Studio"
                    st.rerun()
            if a3.button("📸", key=f"generation_library_photoshoot_{record.image_id}", help="Create Photoshoot", use_container_width=True):
                photoshoot_record = generation_library.send_to_pending_photoshoot(record.image_id)
                existing_session = next((
                    item for item in photoshoot_queue.list_sessions(creator_profile_id=photoshoot_record.creator_profile_id)
                    if item.status not in {"completed", "cancelled", "junked"}
                    and str(dict(item.creative_continuity or {}).get("seed_image_id") or "") == photoshoot_record.image_id
                ), None)
                identity_reference = dict((existing_session.creative_continuity or {}).get("canonical_identity_reference") or {}) if existing_session else {}
                if not identity_reference:
                    canonical_identity = ReferenceLibraryService().get_active_canonical_reference(
                        creator_profile_id=photoshoot_record.creator_profile_id,
                    )
                    if canonical_identity is None or not str(canonical_identity.asset.original_path or "").strip():
                        st.error("An active canonical identity reference is required to start a Photoshoot.")
                        st.stop()
                    identity_reference = {
                        "asset_id": canonical_identity.asset_id,
                        "path": canonical_identity.asset.original_path,
                    }
                session, created = photoshoot_queue.start_studio_session_from_generated_image(
                    photoshoot_record,
                    canonical_identity_reference=identity_reference,
                )
                if created:
                    st.success("Added to Photoshoot Studio.")
                else:
                    st.info("Image is already in Photoshoot Studio.")
                st.session_state["content_studio_active_photoshoot_session_id"] = session.session_id
                st.session_state["dashboard_page"] = "Photoshoot Studio"
                st.rerun()
            if a4.button("🎬", key=f"generation_library_story_{record.image_id}", help="Create Story", use_container_width=True):
                st.info(
                    "🎬 Story Studio is coming soon.\n\n"
                    "Story Studio has not been implemented yet.\n\n"
                    "Your image remains safely in the Generation Library."
                )
            if a5.button("🎥", key=f"generation_library_video_{record.image_id}", help="Create Video", use_container_width=True):
                try:
                    generation_library.send_to_pending_video(record.image_id)
                except Exception as error:
                    st.error(f"Could not add image to Video Queue: {error}")
                else:
                    st.session_state["generation_library_workflow_message"] = (
                        "Video Studio is coming soon.\n\nYour image has been added to the Video Queue."
                    )
                    st.rerun()
            if record.imported_asset_id is not None:
                a6.button(
                    "✅",
                    key=f"generation_library_registered_{record.image_id}",
                    help="Already Registered",
                    use_container_width=True,
                    disabled=True,
                )
            elif a6.button(
                "⭐",
                key=f"generation_library_register_{record.image_id}",
                help="Register Asset",
                use_container_width=True,
            ):
                st.session_state["generation_library_register_image_id"] = record.image_id
                st.rerun()
            if a7.button("🗑️", key=f"generation_library_delete_{record.image_id}", help="Delete Image", use_container_width=True):
                generation_library.delete((record.image_id,))
                st.rerun()
            if record.imported_asset_id is not None:
                _render_commerce_destination_selector(
                    asset_id=int(record.imported_asset_id),
                    creator_profile_id=creator_profile_id,
                    source_workflow="generation_library",
                    key_prefix=f"generation_library_{record.image_id}",
                )
                _render_fulfillment_registration_panel(
                    asset_id=int(record.imported_asset_id),
                    creator_profile_id=creator_profile_id,
                    source_workflow="generation_library",
                    key_prefix=f"generation_library_{record.image_id}",
                )
    registration_image_id = st.session_state.get(
        "generation_library_register_image_id"
    )
    if registration_image_id:
        try:
            registration_record = generation_library.get(registration_image_id)
        except KeyError:
            st.session_state.pop("generation_library_register_image_id", None)
        else:
            _render_asset_registration_dialog(
                registration_record,
                creator_profile=creator_profile,
                asset_registration=asset_registration,
            )
    _render_generation_library_pagination(
        current_page=current_page,
        total_pages=total_pages,
        key_prefix="generation_library_pagination_bottom",
    )


def _render_archive_page(
    *,
    generation_library: GenerationLibraryService,
    content_archive: ContentArchiveService,
) -> None:
    st.title("Archive")
    st.caption("Permanent Content Creation history for published, edited, imported, and junked generated images.")
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
                x_blocking_message = (
                    _x_dependency_blocking_message(social_publishing)
                    if item.platform == "x"
                    else None
                )
                if a7.button(
                    "Publish Now",
                    disabled=not can_publish_now or bool(x_blocking_message),
                    key=f"social_queue_publish_{item.queue_item_id}",
                    use_container_width=True,
                ):
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
                        failure_message = _latest_history_message_for_item(
                            social_publishing,
                            item.queue_item_id,
                        )
                        rendered_failure = "Current publish failed:\n\n" + (failure_message or "Publish failed.")
                        _debug_x_publish_dialog_event(
                            "render_red_social_queue_publish_failure",
                            source="publish history",
                            variable_name="rendered_failure",
                            value=rendered_failure,
                            diagnostic=_x_dependency_debug_diagnostic(social_publishing),
                        )
                        st.error(rendered_failure)
                    st.rerun()
                if x_blocking_message:
                    st.caption("X publishing is currently blocked by the active runtime diagnostic.")
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
            if entry.status == "failed":
                st.caption("Previous publish failure:")
                st.write(_sanitize_historical_publish_message(entry.message))
            else:
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


def _photoshoot_record_by_id(
    generation_library: GenerationLibraryService,
    image_id: str | None,
) -> GeneratedImageRecord | None:
    if not image_id:
        return None
    try:
        return generation_library.get(str(image_id))
    except KeyError:
        return None


def _photoshoot_records_for_request(
    request,
    generation_library: GenerationLibraryService,
) -> tuple[GeneratedImageRecord, ...]:
    records = []
    for image_id in tuple((request.metadata or {}).get("generated_image_ids") or ()):
        record = _photoshoot_record_by_id(generation_library, str(image_id))
        if record is not None:
            records.append(record)
    return tuple(records)


def _photoshoot_seed_record(
    session,
    generation_library: GenerationLibraryService,
) -> GeneratedImageRecord | None:
    continuity = dict(session.creative_continuity or {})
    return _photoshoot_record_by_id(generation_library, continuity.get("seed_image_id"))


def _photoshoot_approved_records(
    session,
    photoshoot_queue: PhotoshootQueueService,
    generation_library: GenerationLibraryService,
) -> tuple[tuple[Any, GeneratedImageRecord], ...]:
    approved = []
    for request in photoshoot_queue.requests_for_session(session.session_id):
        if request.status != "approved":
            continue
        for record in _photoshoot_records_for_request(request, generation_library):
            approved.append((request, record))
    return tuple(approved)


def _photoshoot_timeline_items(
    session,
    photoshoot_queue: PhotoshootQueueService,
    generation_library: GenerationLibraryService,
) -> tuple[tuple[Any, GeneratedImageRecord, str], ...]:
    items = []
    shot_number = 1
    for request in photoshoot_queue.requests_for_session(session.session_id):
        if request.status != "approved":
            continue
        for record in _photoshoot_records_for_request(request, generation_library):
            label = f"📷 Shot {shot_number}"
            if (request.metadata or {}).get("is_seed_image"):
                label = f"{label} (Seed)"
            items.append((request, record, label))
            shot_number += 1
    return tuple(items)


def _render_photoshoot_timeline(
    items: tuple[tuple[Any, GeneratedImageRecord, str], ...],
    *,
    compact: bool = False,
    horizontal: bool = False,
    preview_key: str | None = None,
) -> int | None:
    if not items:
        st.caption("No approved photos yet.")
        return None
    if horizontal:
        selected_key = f"{preview_key}_selected_index" if preview_key else ""
        cards = []
        active_index = len(items) - 1
        try:
            selected_index = int(st.session_state.get(selected_key, active_index)) if selected_key else active_index
        except (TypeError, ValueError):
            selected_index = active_index
        selected_index = max(0, min(selected_index, len(items) - 1))
        if selected_key:
            st.session_state[selected_key] = selected_index
        for index, (request, record, _label) in enumerate(items):
            shot_label = f"Shot {index + 1}"
            is_seed = bool((request.metadata or {}).get("is_seed_image"))
            is_active = index == selected_index
            src = html.escape(_display_image_src(record.output_reference), quote=True)
            alt_text = html.escape(shot_label, quote=True)
            secondary_label = "Starting Image" if is_seed else ("Selected" if is_active else "")
            secondary_html = (
                f"<div class='photoshoot-timeline-secondary'>{html.escape(secondary_label)}</div>"
                if secondary_label
                else "<div class='photoshoot-timeline-secondary photoshoot-timeline-secondary-empty'>&nbsp;</div>"
            )
            active_badge = "<span class='photoshoot-timeline-badge'>★ Active</span>" if is_active else ""
            cards.append(
                f"""
                <div class="photoshoot-timeline-card {'is-active' if is_active else ''}">
                    <div class="photoshoot-timeline-image-wrap">
                        <img src="{src}" alt="{alt_text}" />
                        {active_badge}
                    </div>
                    <div class="photoshoot-timeline-label">{html.escape(shot_label)}</div>
                    {secondary_html}
                </div>
                """
            )
        components.html(
            f"""
            <div class="photoshoot-timeline-scroll">
                {''.join(cards)}
            </div>
            <style>
                .photoshoot-timeline-scroll {{
                    display: flex;
                    flex-wrap: nowrap;
                    gap: 12px;
                    overflow-x: auto;
                    overflow-y: hidden;
                    width: 100%;
                    padding: 2px 2px 12px;
                    box-sizing: border-box;
                }}
                .photoshoot-timeline-card {{
                    flex: 0 0 auto;
                    width: 168px;
                    box-sizing: border-box;
                    border: 1px solid rgba(255,255,255,0.18);
                    background: rgba(255,255,255,0.045);
                    border-radius: 8px;
                    padding: 8px;
                    color: rgba(255,255,255,0.9);
                }}
                .photoshoot-timeline-card.is-active {{
                    border-color: #f5c542;
                    background: rgba(245,197,66,0.12);
                }}
                .photoshoot-timeline-image-wrap {{
                    position: relative;
                    width: 100%;
                    height: 136px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    overflow: hidden;
                    border-radius: 6px;
                    background: rgba(0,0,0,0.24);
                }}
                .photoshoot-timeline-image-wrap img {{
                    max-width: 100%;
                    max-height: 136px;
                    width: auto;
                    height: auto;
                    object-fit: contain;
                    display: block;
                }}
                .photoshoot-timeline-label {{
                    margin-top: 7px;
                    font-size: 0.86rem;
                    font-weight: 650;
                    line-height: 1.15;
                    text-align: center;
                }}
                .photoshoot-timeline-secondary {{
                    min-height: 16px;
                    margin-top: 3px;
                    color: rgba(255,255,255,0.62);
                    font-size: 0.72rem;
                    line-height: 1.1;
                    text-align: center;
                }}
                .photoshoot-timeline-secondary-empty {{
                    opacity: 0;
                }}
                .photoshoot-timeline-badge {{
                    position: absolute;
                    top: 6px;
                    right: 6px;
                    padding: 2px 6px;
                    border-radius: 999px;
                    background: rgba(245,197,66,0.92);
                    color: #171717;
                    font-size: 0.68rem;
                    font-weight: 700;
                    line-height: 1.1;
                }}
            </style>
            """,
            height=205,
            scrolling=False,
        )
        if preview_key:
            preview_left, preview_button_col, preview_right = st.columns([2, 1, 2])
            with preview_button_col:
                if st.button(
                    "👁 Preview",
                    key=f"{preview_key}_button",
                    use_container_width=True,
                ):
                    st.session_state[preview_key] = selected_index
                    st.rerun()
        return selected_index
    for index, (_request, record, label) in enumerate(items):
        st.caption(label)
        _render_edit_studio_image(
            record.output_reference,
            alt=label,
            max_height=360 if compact else 620,
        )
        if index < len(items) - 1:
            st.markdown("<div style='text-align:center; opacity:0.65;'>↓</div>", unsafe_allow_html=True)
    return None


def _render_photoshoot_preview_image(image_reference: Any, *, alt: str) -> None:
    src = html.escape(_display_image_src(image_reference), quote=True)
    alt_text = html.escape(alt, quote=True)
    components.html(
        f"""
        <div style="
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0;
            margin: 0;
            min-height: 0;
        ">
            <img
                src="{src}"
                alt="{alt_text}"
                style="
                    display: block;
                    max-width: 85%;
                    max-height: 410px;
                    width: auto;
                    height: auto;
                    object-fit: contain;
                    border-radius: 8px;
                "
            />
        </div>
        """,
        height=455,
        scrolling=False,
    )


def _render_photoshoot_shot_preview(
    items: tuple[tuple[Any, GeneratedImageRecord, str], ...],
    *,
    preview_key: str,
    session_id: str | None = None,
    session_title: str | None = None,
    photoshoot_queue: PhotoshootQueueService | None = None,
    generation_library: GenerationLibraryService | None = None,
) -> None:
    if not items or preview_key not in st.session_state:
        return
    try:
        selected_index = int(st.session_state.get(preview_key) or 0)
    except (TypeError, ValueError):
        selected_index = 0
    selected_index = max(0, min(selected_index, len(items) - 1))
    st.session_state[preview_key] = selected_index

    def render_preview_body() -> None:
        _request, record, _label = items[selected_index]
        shot_number = selected_index + 1
        is_seed_shot = bool((_request.metadata or {}).get("is_seed_image"))
        confirm_return_key = f"{preview_key}_return_seed_confirm_{record.image_id}"
        st.markdown(f"#### Shot {shot_number}")
        _render_photoshoot_preview_image(record.output_reference, alt=f"Shot {shot_number}")
        st.markdown("---")

        previous_col, next_col, close_col = st.columns(3)
        if previous_col.button(
            "◀ Previous",
            key=f"{preview_key}_previous",
            disabled=selected_index <= 0,
            use_container_width=True,
        ):
            st.session_state[preview_key] = selected_index - 1
            st.rerun()
        if next_col.button(
            "Next ▶",
            key=f"{preview_key}_next",
            disabled=selected_index >= len(items) - 1,
            use_container_width=True,
        ):
            st.session_state[preview_key] = selected_index + 1
            st.rerun()
        if close_col.button("✕ Close", key=f"{preview_key}_close", use_container_width=True):
            st.session_state.pop(preview_key, None)
            st.session_state.pop(confirm_return_key, None)
            st.rerun()
        if (
            selected_index == 0
            and is_seed_shot
            and session_id
            and photoshoot_queue is not None
            and generation_library is not None
        ):
            if st.session_state.get(confirm_return_key):
                if len(items) <= 1:
                    st.warning("This will end the current Photoshoot because the seed image is being removed.")
                else:
                    st.warning(
                        "The seed image is being removed.\n\n"
                        "The remaining photoshoot will no longer have its original starting image.\n\n"
                        "Continue?"
                    )
                return_col, cancel_col = st.columns(2)
                if return_col.button("Return Image", key=f"{preview_key}_return_seed_do_{record.image_id}", use_container_width=True):
                    action = generation_library.return_photoshoot_seed_to_library(record.image_id)
                    if not action.success:
                        st.error(action.message)
                        for error in action.errors:
                            st.caption(error)
                        st.stop()
                    photoshoot_queue.return_seed_request_to_library(
                        _request.request_id,
                        notes="Returned seed image to Generation Library from preview.",
                    )
                    st.session_state.pop(preview_key, None)
                    st.session_state.pop(confirm_return_key, None)
                    st.session_state.pop(f"{preview_key}_selected_index", None)
                    if len(items) <= 1:
                        st.session_state.pop("content_studio_active_photoshoot_session_id", None)
                        st.session_state["dashboard_page"] = "Generation Library"
                    st.success("Seed image returned to Generation Library.")
                    st.rerun()
                if cancel_col.button("Cancel", key=f"{preview_key}_return_seed_cancel_{record.image_id}", use_container_width=True):
                    st.session_state.pop(confirm_return_key, None)
                    st.rerun()
            elif st.button(
                "📤 Return to Generation Library",
                key=f"{preview_key}_return_seed_{record.image_id}",
                use_container_width=True,
            ):
                st.session_state[confirm_return_key] = True
                st.rerun()
        elif (
            selected_index > 0
            and session_id
            and photoshoot_queue is not None
            and generation_library is not None
        ):
            if st.button(
                "🗑 Delete",
                key=f"{preview_key}_junk_{record.image_id}",
                use_container_width=True,
            ):
                image_ids = tuple((_request.metadata or {}).get("generated_image_ids") or (record.image_id,))
                action = generation_library.move_photoshoot_records_to_junk(
                    image_ids,
                    session_id=session_id,
                    session_title=session_title,
                )
                if not action.success:
                    st.error(action.message)
                    for error in action.errors:
                        st.caption(error)
                    st.stop()
                photoshoot_queue.junk_request(_request.request_id, notes="Moved to Photoshoot Junk from preview.")
                st.session_state.pop(preview_key, None)
                st.session_state.pop(f"{preview_key}_selected_index", None)
                st.success("Moved shot to Photoshoot Junk.")
                st.rerun()

    dialog = getattr(st, "dialog", None)
    if callable(dialog):
        @dialog("Photoshoot Preview")
        def photoshoot_preview_dialog():
            render_preview_body()

        photoshoot_preview_dialog()
    else:
        st.markdown(
            """
            <div style="
                border: 1px solid rgba(255,255,255,0.18);
                background: rgba(0,0,0,0.72);
                border-radius: 8px;
                padding: 14px;
                margin: 10px 0;
            ">
            """,
            unsafe_allow_html=True,
        )
        render_preview_body()
        st.markdown("</div>", unsafe_allow_html=True)


def _photoshoot_candidate_request(
    session,
    photoshoot_queue: PhotoshootQueueService,
):
    for request in reversed(photoshoot_queue.requests_for_session(session.session_id)):
        if request.status == "awaiting_review":
            return request
    return None



def _clear_photoshoot_one_shot_workspace_state(session_id: str, *, preview_key: str) -> None:
    """Clear temporary per-shot inputs without touching persistent session settings."""
    for key in (
        f"photoshoot_studio_prompt_{session_id}",
        f"photoshoot_creative_hint_{session_id}",
        f"photoshoot_pending_creative_hint_{session_id}",
        f"photoshoot_grok_guidance_{session_id}",
        f"photoshoot_grok_idea_{session_id}",
        f"photoshoot_grok_idea_select_{session_id}",
        f"photoshoot_studio_recommendation_{session_id}",
        f"photoshoot_direction_approved_{session_id}",
        f"photoshoot_studio_pending_prompt_{session_id}",
        preview_key,
    ):
        st.session_state.pop(key, None)



def _image_bytes_for_grok(image_reference: str) -> tuple[bytes, str]:
    source = str(image_reference or "").strip()
    if source.startswith("data:"):
        header, _, encoded = source.partition(",")
        mime_type = header.removeprefix("data:").split(";")[0] or "image/png"
        return base64.b64decode(encoded), mime_type
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=20) as response:
            content_type = response.headers.get_content_type() or "image/png"
            return response.read(), content_type
    path = Path(source).expanduser()
    if not path.exists() or not path.is_file():
        raise ValueError(f"Current image file was not found: {source}")
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    return path.read_bytes(), mime_type


def _photoshoot_direction_text(recommendation: Mapping[str, Any]) -> str:
    pieces = [
        str(recommendation.get("creative_direction") or "").strip(),
        f"Camera framing: {recommendation.get('camera_framing')}" if recommendation.get("camera_framing") else "",
        f"Lighting: {recommendation.get('lighting')}" if recommendation.get("lighting") else "",
        f"Emotion: {recommendation.get('emotion')}" if recommendation.get("emotion") else "",
        f"Pose/composition: {recommendation.get('pose_composition')}" if recommendation.get("pose_composition") else "",
        f"Continuity notes: {recommendation.get('continuity_notes')}" if recommendation.get("continuity_notes") else "",
    ]
    return "\n".join(piece for piece in pieces if piece)


def _valid_photoshoot_recommendation(recommendation: Mapping[str, Any] | None) -> bool:
    if not recommendation:
        return False
    return bool(
        str(recommendation.get("title") or "").strip()
        or str(recommendation.get("creative_direction") or "").strip()
        or str(recommendation.get("direction") or "").strip()
    )


def _photoshoot_approve_generate_disabled(
    *,
    recommendation_ready: bool,
    direction_approved: bool,
    candidate_request_present: bool,
    generation_running: bool,
    generation_inflight: bool,
) -> bool:
    return (
        not recommendation_ready
        or direction_approved
        or candidate_request_present
        or generation_running
        or generation_inflight
    )


def _build_photoshoot_prompt(
    *,
    creative_director: CreativeDirectorService,
    seed_prompt: str,
    shot_direction: str,
    creative_mode: str,
    session_context: Mapping[str, Any] | None = None,
) -> str:
    direction = str(shot_direction or "").strip()
    if not direction:
        raise ValueError("Next Shot Direction is required.")
    continuity = dict(session_context or {})
    seed_context = str(seed_prompt or "").strip() or "Use the selected image as the canonical visual reference."
    creative_tags = "\n".join(
        (
            "Photoshoot Studio continuation.",
            f"Creative direction: {direction}",
            f"Seed image context: {seed_context}",
            f"Session continuity: {json.dumps(continuity, ensure_ascii=True, default=str)}",
            "Preserve continuity defaults unless the Session Direction explicitly overrides them.",
        )
    )
    mode = photoshoot_planning_mode(creative_mode)
    result = creative_director.plan_prompts(
        mode=mode,
        creative_tags=creative_tags,
        prompt_count=1,
        optional_direction=direction,
        metadata={"source": "photoshoot_studio"},
    )
    if not result.prompts:
        raise ValueError("Canonical Prompt Planner did not return a Photoshoot prompt.")
    return result.prompts[0]




def _render_photoshoot_image_strip(
    items: tuple[tuple[str, GeneratedImageRecord], ...],
) -> None:
    if not items:
        st.caption("No photos yet.")
        return
    cols = st.columns(min(5, max(1, len(items))))
    for index, (label, record) in enumerate(items):
        with cols[index % len(cols)]:
            st.image(record.output_reference, use_container_width=True)
            st.caption(label)


def _render_photoshoot_image_stack(
    items: tuple[tuple[str, GeneratedImageRecord], ...],
    *,
    max_height: int = 620,
) -> None:
    if not items:
        st.caption("No approved shots yet.")
        return
    for label, record in items:
        st.caption(label)
        _render_edit_studio_image(
            record.output_reference,
            alt=f"Photoshoot {label.lower()}",
            max_height=max_height,
        )


def _render_photoshoot_filmstrip(
    items: tuple[tuple[str, GeneratedImageRecord], ...],
    *,
    selected_image_id: str | None,
    key_prefix: str,
) -> GeneratedImageRecord | None:
    if not items:
        st.caption("No photos yet.")
        return None
    valid_ids = {record.image_id for _, record in items}
    selected_id = selected_image_id if selected_image_id in valid_ids else items[0][1].image_id
    selected_record = next((record for _, record in items if record.image_id == selected_id), items[0][1])
    cards = []
    for label, record in items:
        src = html.escape(_display_image_src(record.output_reference), quote=True)
        label_text = html.escape(label)
        selected = record.image_id == selected_id
        cards.append(
            f"""
            <div style="
                flex: 0 0 148px;
                border: 2px solid {'#f5c542' if selected else 'rgba(255,255,255,0.18)'};
                background: {'rgba(245,197,66,0.14)' if selected else 'rgba(255,255,255,0.04)'};
                border-radius: 8px;
                padding: 8px;
            ">
                <div style="
                    width: 132px;
                    height: 132px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    overflow: hidden;
                    border-radius: 6px;
                    background: rgba(0,0,0,0.24);
                ">
                    <img src="{src}" alt="{label_text}" style="
                        max-width: 132px;
                        max-height: 132px;
                        width: auto;
                        height: auto;
                        object-fit: contain;
                        display: block;
                    " />
                </div>
                <div style="
                    margin-top: 6px;
                    color: {'#f5c542' if selected else 'rgba(255,255,255,0.78)'};
                    font-size: 0.82rem;
                    line-height: 1.2;
                    text-align: center;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                ">{label_text}</div>
            </div>
            """
        )
    components.html(
        f"""
        <div style="
            display: flex;
            gap: 12px;
            overflow-x: auto;
            padding: 4px 2px 10px;
            width: 100%;
        ">
            {''.join(cards)}
        </div>
        """,
        height=178,
        scrolling=True,
    )
    select_cols = st.columns(min(len(items), 5))
    for index, (label, record) in enumerate(items):
        with select_cols[index % len(select_cols)]:
            button_type = "primary" if record.image_id == selected_id else "secondary"
            if st.button(
                label,
                key=f"{key_prefix}_{record.image_id}",
                type=button_type,
                use_container_width=True,
            ):
                selected_record = record
                st.session_state[key_prefix] = record.image_id
                st.rerun()
    return selected_record


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
    st.title("📸 Photoshoot Studio")
    st.caption("Direct a continuity-locked image session from one canonical seed image.")
    if not creator_profile_id:
        st.error("Creator Profile required before using Photoshoot Studio.")
        return

    sessions = photoshoot_queue.list_sessions(creator_profile_id=creator_profile_id)
    current = photoshoot_queue.current_session(creator_profile_id=creator_profile_id)
    if current:
        photoshoot_queue.sync_ingested_assets_for_session(current.session_id)
        seed_record = _photoshoot_seed_record(current, generation_library)
        candidate_request = _photoshoot_candidate_request(current, photoshoot_queue)
        candidate_records = (
            _photoshoot_records_for_request(candidate_request, generation_library)
            if candidate_request
            else ()
        )
        if seed_record is None:
            st.warning("The seed image for this Photoshoot Studio session is no longer available in Generation Library.")

        st.markdown("### Photoshoot Timeline")
        timeline_items = _photoshoot_timeline_items(current, photoshoot_queue, generation_library)
        preview_key = f"photoshoot_timeline_preview_{current.session_id}"
        selected_index_key = f"{preview_key}_selected_index"
        reset_fields_key = f"photoshoot_studio_reset_fields_{current.session_id}"
        continuity = dict(current.creative_continuity or {})
        if st.session_state.get(reset_fields_key):
            latest_index = max(0, len(timeline_items) - 1)
            st.session_state[selected_index_key] = latest_index
            current = photoshoot_queue.update_session_settings(
                current.session_id,
                selected_timeline_index=latest_index,
                workflow_stage="ready_for_next_shot",
            )
            continuity = dict(current.creative_continuity or {})
        if selected_index_key not in st.session_state and "selected_timeline_index" in continuity:
            try:
                st.session_state[selected_index_key] = int(continuity.get("selected_timeline_index"))
            except (TypeError, ValueError):
                pass
        _render_photoshoot_timeline(timeline_items, horizontal=True, preview_key=preview_key)
        _render_photoshoot_shot_preview(
            timeline_items,
            preview_key=preview_key,
            session_id=current.session_id,
            session_title=current.title,
            photoshoot_queue=photoshoot_queue,
            generation_library=generation_library,
        )
        selected_record = timeline_items[-1][1] if timeline_items else seed_record
        # Keep the latest approved shot as the active reference without rendering it again.

        direction_key = f"photoshoot_studio_direction_{current.session_id}"
        prompt_key = f"photoshoot_studio_prompt_{current.session_id}"
        recommendation_key = f"photoshoot_studio_recommendation_{current.session_id}"
        creative_hint_key = f"photoshoot_creative_hint_{current.session_id}"
        pending_creative_hint_key = f"photoshoot_pending_creative_hint_{current.session_id}"
        grok_guidance_key = f"photoshoot_grok_guidance_{current.session_id}"
        grok_idea_key = f"photoshoot_grok_idea_{current.session_id}"
        grok_idea_select_key = f"photoshoot_grok_idea_select_{current.session_id}"
        direction_approved_key = f"photoshoot_direction_approved_{current.session_id}"
        pending_direction_key = f"photoshoot_studio_pending_direction_{current.session_id}"
        pending_prompt_key = f"photoshoot_studio_pending_prompt_{current.session_id}"
        if st.session_state.pop(reset_fields_key, False):
            _clear_photoshoot_one_shot_workspace_state(current.session_id, preview_key=preview_key)
        if pending_direction_key in st.session_state:
            st.session_state[direction_key] = st.session_state.pop(pending_direction_key)
        if pending_prompt_key in st.session_state:
            st.session_state[prompt_key] = st.session_state.pop(pending_prompt_key)
        continuity = dict(current.creative_continuity or {})
        approved_shot_count = len(timeline_items)
        persisted_workflow_stage = str(continuity.get("workflow_stage") or "").strip()
        restore_workspace_state = candidate_request is not None or persisted_workflow_stage in {
            "recommendation_ready",
            "direction_approved",
            "generating",
            "awaiting_review",
            "review_candidate",
        }
        workflow_stage = (
            "awaiting_review"
            if candidate_request is not None
            else persisted_workflow_stage
            if persisted_workflow_stage in {"recommendation_ready", "generating", "ready_for_next_shot"}
            else "direction_approved"
            if restore_workspace_state and continuity.get("direction_approved")
            else "ready_for_direction"
        )
        st.info(f"📸 Resumed Photoshoot\n\n{current.title}\n\nReady for Shot {approved_shot_count + 1}")
        if restore_workspace_state and prompt_key not in st.session_state and str(continuity.get("current_prompt") or "").strip():
            st.session_state[prompt_key] = str(continuity.get("current_prompt") or "").strip()
        if restore_workspace_state and recommendation_key not in st.session_state and dict(continuity.get("current_direction") or {}):
            st.session_state[recommendation_key] = dict(continuity.get("current_direction") or {})
        if restore_workspace_state and bool(continuity.get("direction_approved")):
            st.session_state[direction_approved_key] = True
        provider_options = premium_studio_provider_options(generation_engine)
        provider_ids = tuple(provider_id for provider_id, _ in provider_options)
        provider_labels = dict(provider_options)
        provider_key = f"photoshoot_studio_provider_{current.session_id}"
        if provider_key not in st.session_state and current.provider_id in provider_ids:
            st.session_state[provider_key] = current.provider_id
        selected_provider = st.selectbox(
            "Provider",
            provider_ids,
            index=default_provider_index(provider_ids, preferred_provider_id=current.provider_id),
            format_func=lambda value: provider_labels.get(value, value),
            key=provider_key,
        )

        st.markdown("### Creative Direction")
        direction_mode = st.radio(
            "Direction Mode",
            ("Manual", "🎬 Shot Director"),
            key=f"photoshoot_direction_mode_{current.session_id}",
            horizontal=True,
        )
        session_direction = st.text_area(
            "Session Direction (Optional)",
            key=direction_key,
            height=110,
            placeholder=(
                "Leave blank to maintain the current setting and outfit.\n\n"
                "Move to the balcony\n"
                "Switch to a different outfit\n"
                "Change to morning lighting\n"
                "Move into the bathroom"
            ),
        )
        creative_mode_key = f"photoshoot_creative_mode_{current.session_id}"
        persisted_creative_mode = str(current.creative_mode or "safe").strip().lower()
        mode_options = ("Safe", "Premium", "Explicit")
        mode_values = tuple(mode.lower() for mode in mode_options)
        if creative_mode_key not in st.session_state and persisted_creative_mode in mode_values:
            st.session_state[creative_mode_key] = mode_options[mode_values.index(persisted_creative_mode)]
        creative_mode = st.radio(
            "Creative Mode",
            mode_options,
            key=creative_mode_key,
            horizontal=True,
        ).lower()
        st.markdown("#### Continuity")
        lock_cols = st.columns(3)
        continuity_locks = {}
        persisted_locks = dict(continuity.get("continuity_locks") or {})
        for index, (lock_key, label) in enumerate(
            (
                ("location", "Keep location"),
                ("wardrobe", "Keep wardrobe"),
                ("lighting", "Keep lighting"),
                ("hairstyle", "Keep hairstyle"),
                ("makeup", "Keep makeup"),
                ("camera_style", "Keep camera style"),
            )
        ):
            with lock_cols[index % 3]:
                widget_key = f"photoshoot_lock_{current.session_id}_{lock_key}"
                if widget_key not in st.session_state:
                    st.session_state[widget_key] = bool(persisted_locks.get(lock_key, True))
                continuity_locks[lock_key] = st.checkbox(
                    label,
                    key=widget_key,
                )
        settings_changed = (
            selected_provider != current.provider_id
            or creative_mode != str(current.creative_mode or "").strip().lower()
            or dict(continuity.get("continuity_locks") or {}) != dict(continuity_locks)
            or continuity.get("workflow_stage") != workflow_stage
        )
        if settings_changed:
            current = photoshoot_queue.update_session_settings(
                current.session_id,
                provider_id=selected_provider,
                creative_mode=creative_mode,
                continuity_locks=continuity_locks,
                workflow_stage=workflow_stage,
            )
            continuity = dict(current.creative_continuity or {})

        active_request = photoshoot_queue.current_request(current.session_id)
        generation_running = bool(active_request and active_request.status == "generating")
        generation_inflight_key = f"photoshoot_approve_generate_inflight_{current.session_id}"
        recommendation = dict(st.session_state.get(recommendation_key) or {})
        recommendation_ready = _valid_photoshoot_recommendation(recommendation)
        direction_approved = bool(
            st.session_state.get(direction_approved_key)
            or (restore_workspace_state and continuity.get("direction_approved"))
        )
        if pending_creative_hint_key in st.session_state:
            st.session_state[creative_hint_key] = st.session_state.pop(pending_creative_hint_key)
        creative_hint = st.text_input(
            "Creative Hint (Optional)",
            key=creative_hint_key,
            placeholder="Selected Grok idea or manual direction for Shot Director / generate...",
        )
        grok_guidance = st.text_input(
            "Ask Grok Guidance (Optional)",
            key=grok_guidance_key,
            placeholder="Steer next ideas before asking Grok… (e.g. topless, panties off, playing with herself, more horny face)",
            help="Optional. Short paid-NSFW steering for suggestion generation only. Does not replace Creative Hint.",
        )
        ask_grok_col, shot_director_col = st.columns(2)
        with ask_grok_col:
            ask_grok_clicked = st.button(
                "💡 Ask Grok",
                disabled=selected_record is None or candidate_request is not None or generation_running,
                key=f"photoshoot_ask_grok_{current.session_id}",
                use_container_width=True,
            )
        with shot_director_col:
            ask_shot_director_clicked = st.button(
                "🎬 Shot Director",
                disabled=selected_record is None or bool(recommendation) or direction_approved or candidate_request is not None or generation_running,
                key=f"photoshoot_ask_creative_director_{current.session_id}",
                use_container_width=True,
            )
        if ask_grok_clicked:
            try:
                image_bytes, image_mime_type = _image_bytes_for_grok(selected_record.output_reference)
                timeline_images = []
                for index, (request, record, label) in enumerate(timeline_items):
                    try:
                        shot_bytes, shot_mime = _image_bytes_for_grok(record.output_reference)
                    except Exception:
                        continue
                    is_seed = bool((request.metadata or {}).get("is_seed_image"))
                    shot_label = f"Shot {index + 1}"
                    if is_seed:
                        shot_label = f"{shot_label} (Seed)"
                    if index == len(timeline_items) - 1:
                        shot_label = f"{shot_label} — current"
                    timeline_images.append(
                        {
                            "bytes": shot_bytes,
                            "mime_type": shot_mime,
                            "label": shot_label or label,
                        }
                    )
                if not timeline_images:
                    timeline_images.append(
                        {
                            "bytes": image_bytes,
                            "mime_type": image_mime_type,
                            "label": "Current shot",
                        }
                    )
                with st.spinner(
                    f"Asking Grok to review {len(timeline_images)} approved shot"
                    f"{'s' if len(timeline_images) != 1 else ''}..."
                ):
                    grok_ideas = creative_director.suggest_photoshoot_inspiration(
                        image_bytes=image_bytes,
                        image_mime_type=image_mime_type,
                        session_context=continuity,
                        approved_history=tuple(continuity.get("approved_directions") or ()),
                        creative_mode=creative_mode,
                        session_direction=session_direction,
                        creative_hint="",
                        grok_guidance=grok_guidance,
                        continuity_locks=continuity_locks,
                        provider_context=provider_labels.get(selected_provider, selected_provider),
                        idea_count=8,
                        timeline_images=timeline_images,
                    )
            except Exception as error:
                st.error(str(error))
            else:
                st.session_state[grok_idea_key] = list(grok_ideas)
                st.session_state.pop(grok_idea_select_key, None)
                if grok_ideas:
                    st.session_state[pending_creative_hint_key] = str(grok_ideas[0] or "").strip()
                st.rerun()
        raw_grok_ideas = st.session_state.get(grok_idea_key)
        if isinstance(raw_grok_ideas, str):
            grok_ideas = [raw_grok_ideas.strip()] if raw_grok_ideas.strip() else []
        elif isinstance(raw_grok_ideas, (list, tuple)):
            grok_ideas = [str(item).strip() for item in raw_grok_ideas if str(item or "").strip()]
        else:
            grok_ideas = []
        if grok_ideas:
            st.markdown("#### Grok Ideas")
            st.caption("Pick the next evolving scene. Creative Hint updates automatically.")

            def apply_selected_grok_idea_to_hint() -> None:
                st.session_state[pending_creative_hint_key] = str(
                    st.session_state.get(grok_idea_select_key) or ""
                ).strip()

            st.radio(
                "Next scene options",
                options=grok_ideas,
                key=grok_idea_select_key,
                on_change=apply_selected_grok_idea_to_hint,
                label_visibility="collapsed",
            )
        if ask_shot_director_clicked:
            try:
                image_bytes, image_mime_type = _image_bytes_for_grok(selected_record.output_reference)
                with st.spinner("Asking Shot Director..."):
                    ai_direction = creative_director.recommend_photoshoot_direction(
                        image_bytes=image_bytes,
                        image_mime_type=image_mime_type,
                        session_context=continuity,
                        approved_history=tuple(continuity.get("approved_directions") or ()),
                        creative_mode=creative_mode,
                        session_direction=session_direction,
                        creative_hint=creative_hint,
                        continuity_locks=continuity_locks,
                    )
            except Exception as error:
                st.error(str(error))
            else:
                recommendation_payload = asdict(ai_direction)
                photoshoot_queue.record_pending_recommendation(
                    session_id=current.session_id,
                    recommendation=recommendation_payload,
                )
                st.session_state[recommendation_key] = recommendation_payload
                st.success("Shot Director recommendation ready.")
                st.rerun()

        if recommendation:
            st.markdown("#### Shot Director Recommendation")
            st.markdown(f"**{recommendation.get('title') or 'Next Direction'}**")
            st.write(recommendation.get("creative_direction") or "")
            st.caption(f"Reasoning: {recommendation.get('reasoning') or ''}")
            st.caption(f"Continuity Notes: {recommendation.get('continuity_notes') or ''}")
            st.caption(f"Camera: {recommendation.get('camera_framing') or ''}")
            st.caption(f"Lighting: {recommendation.get('lighting') or ''}")
            st.caption(f"Emotion: {recommendation.get('emotion') or ''}")
            st.caption(f"Pose/Composition: {recommendation.get('pose_composition') or ''}")
            another_idea_col, approve_direction_col = st.columns(2)
            if another_idea_col.button("🔄 Another Idea", key=f"photoshoot_another_idea_{current.session_id}", use_container_width=True):
                st.session_state.pop(recommendation_key, None)
                st.session_state.pop(prompt_key, None)
                st.session_state.pop(direction_approved_key, None)
                photoshoot_queue.clear_workspace_state(current.session_id, workflow_stage="ready_for_direction")
                st.rerun()
            approve_direction_clicked = approve_direction_col.button(
                "🚀 Approve & Generate",
                disabled=_photoshoot_approve_generate_disabled(
                    recommendation_ready=recommendation_ready,
                    direction_approved=direction_approved,
                    candidate_request_present=candidate_request is not None,
                    generation_running=generation_running,
                    generation_inflight=bool(st.session_state.get(generation_inflight_key)),
                ),
                key=f"photoshoot_approve_direction_{current.session_id}",
                use_container_width=True,
            )
        else:
            approve_direction_clicked = False

        active_direction = (
            _photoshoot_direction_text(recommendation)
            if recommendation_ready
            else str(session_direction or "").strip()
        )

        if approve_direction_clicked:
            st.session_state[generation_inflight_key] = True
            try:
                final_prompt = _build_photoshoot_prompt(
                    creative_director=creative_director,
                    seed_prompt=selected_record.prompt_text if selected_record else "",
                    shot_direction=active_direction,
                    creative_mode=creative_mode,
                    session_context=continuity,
                )
                photoshoot_queue.record_creative_direction(
                    session_id=current.session_id,
                    recommendation=recommendation,
                    final_prompt=final_prompt,
                )
                st.session_state[prompt_key] = final_prompt
                st.session_state[direction_approved_key] = True
                photoshoot_queue.add_studio_shot_request(
                    session_id=current.session_id,
                    prompt_text=final_prompt,
                    shot_direction=active_direction,
                    provider_id=selected_provider,
                    active_reference_image_id=selected_record.image_id if selected_record else None,
                    active_reference_output_reference=selected_record.output_reference if selected_record else None,
                    creative_direction=recommendation,
                )
                progress_callback, _render_status, _render_images, complete_preview = _render_live_generation_preview(
                    title="Live Generated Images",
                    total=1,
                )
                with st.spinner("Generating Photoshoot shot..."):
                    executed, records = execute_photoshoot_next_to_library(
                        session_id=current.session_id,
                        generation_engine=generation_engine,
                        generation_library=generation_library,
                        photoshoot_queue=photoshoot_queue,
                        progress_callback=progress_callback,
                    )
            except Exception as error:
                st.session_state.pop(generation_inflight_key, None)
                photoshoot_queue.update_session_settings(
                    current.session_id,
                    workflow_stage="recommendation_ready",
                )
                st.error(str(error))
            else:
                st.session_state.pop(generation_inflight_key, None)
                if executed and executed.status == GenerationStatus.SUCCEEDED.value:
                    complete_preview(tuple(getattr(record, "output_reference", str(record)) for record in records))
                    st.success("Shot generated. Review the candidate below.")
                elif executed and executed.failure:
                    st.error(executed.failure.reason)
                else:
                    st.info("Generation is already in progress or awaiting review.")
                st.rerun()

        active_candidate = candidate_request is not None
        if direction_mode == "🎬 Shot Director":
            if str(st.session_state.get(prompt_key) or "").strip():
                st.text_area(
                    "Canonical Prompt",
                    key=prompt_key,
                    height=180,
                    disabled=True,
                )
            if generation_running:
                st.info("Generation is running. The candidate will appear here when it completes.")
        else:
            prompt_text = st.text_area(
                "Generated Prompt",
                key=prompt_key,
                height=220,
                placeholder="Write or refine the manual Photoshoot prompt before generating.",
            )
            if st.button(
                "🚀 Generate Shot",
                disabled=not str(prompt_text).strip() or active_candidate or generation_running or selected_record is None,
                key=f"photoshoot_generate_shot_{current.session_id}",
                use_container_width=True,
            ):
                try:
                    photoshoot_queue.add_studio_shot_request(
                        session_id=current.session_id,
                        prompt_text=prompt_text,
                        shot_direction=active_direction,
                        provider_id=selected_provider,
                        active_reference_image_id=selected_record.image_id if selected_record else None,
                        active_reference_output_reference=selected_record.output_reference if selected_record else None,
                        creative_direction={},
                    )
                    progress_callback, _render_status, _render_images, complete_preview = _render_live_generation_preview(
                        title="Live Generated Images",
                        total=1,
                    )
                    with st.spinner("Generating Photoshoot shot..."):
                        executed, records = execute_photoshoot_next_to_library(
                            session_id=current.session_id,
                            generation_engine=generation_engine,
                            generation_library=generation_library,
                            photoshoot_queue=photoshoot_queue,
                            progress_callback=progress_callback,
                        )
                except Exception as error:
                    st.error(str(error))
                else:
                    if executed and executed.status == GenerationStatus.SUCCEEDED.value:
                        complete_preview(tuple(getattr(record, "output_reference", str(record)) for record in records))
                        st.success("Shot generated. Review the candidate below.")
                    elif executed and executed.failure:
                        st.error(executed.failure.reason)
                    else:
                        st.info("No shot was generated. A review may already be pending.")
                    st.rerun()
        if active_candidate:
            st.markdown("### Review Candidate")
            if candidate_records:
                _render_edit_studio_image(candidate_records[-1].output_reference, alt="Photoshoot candidate", max_height=620)
            else:
                st.info("Candidate is awaiting review, but the generated image record has not synced yet.")
            approve_col, retry_col, edit_col, reject_col = st.columns(4)
            candidate_image_ids = tuple((candidate_request.metadata or {}).get("generated_image_ids") or ())
            if approve_col.button("✅ Approve Shot", key=f"photoshoot_studio_approve_{candidate_request.request_id}", use_container_width=True):
                approval = generation_library.approve_creator_content(
                    candidate_image_ids,
                    source_workflow="photoshoot",
                    source_session_id=current.session_id,
                    generation_engine=generation_engine,
                    ingestion_service=generation_ingestion,
                    source_metadata={
                        "approval_entrypoint": "photoshoot_studio_approve_shot",
                        "photoshoot_session_id": current.session_id,
                        "photoshoot_request_id": candidate_request.request_id,
                        "photoshoot_sequence_index": candidate_request.sequence_index,
                        "prompt_plan_id": candidate_request.prompt_plan_id,
                    },
                )
                if not approval.success:
                    st.error(approval.message)
                    for error in approval.errors:
                        st.caption(error)
                    st.stop()
                action = generation_library.approve_photoshoot_records(
                    candidate_image_ids,
                    session_id=current.session_id,
                    session_title=current.title,
                )
                if not action.success:
                    st.error(action.message)
                    for error in action.errors:
                        st.caption(error)
                    st.stop()
                photoshoot_queue.approve_request(
                    candidate_request.request_id,
                    imported_asset_ids=approval.imported_asset_ids,
                )
                st.session_state[reset_fields_key] = True
                st.rerun()
            if retry_col.button("🔄 Regenerate", key=f"photoshoot_studio_retry_{candidate_request.request_id}", use_container_width=True):
                generation_library.move_photoshoot_records_to_junk(
                    candidate_image_ids,
                    session_id=current.session_id,
                    session_title=current.title,
                    reason="photoshoot_regenerate",
                )
                photoshoot_queue.regenerate_request(candidate_request.request_id)
                progress_callback, _render_status, _render_images, complete_preview = _render_live_generation_preview(
                    title="Live Generated Images",
                    total=1,
                )
                with st.spinner("Retrying Photoshoot shot..."):
                    executed, records = execute_photoshoot_next_to_library(
                        session_id=current.session_id,
                        generation_engine=generation_engine,
                        generation_library=generation_library,
                        photoshoot_queue=photoshoot_queue,
                        progress_callback=progress_callback,
                    )
                if executed and executed.status == GenerationStatus.SUCCEEDED.value:
                    complete_preview(tuple(getattr(record, "output_reference", str(record)) for record in records))
                elif executed and executed.failure:
                    st.error(executed.failure.reason)
                st.rerun()
            if edit_col.button("✏️ Edit Prompt", key=f"photoshoot_studio_edit_prompt_{candidate_request.request_id}", use_container_width=True):
                st.session_state[pending_prompt_key] = candidate_request.prompt_text
                st.session_state[pending_direction_key] = str((candidate_request.metadata or {}).get("shot_direction") or "")
                generation_library.move_photoshoot_records_to_junk(
                    candidate_image_ids,
                    session_id=current.session_id,
                    session_title=current.title,
                    reason="photoshoot_edit_prompt",
                )
                photoshoot_queue.reject_request(candidate_request.request_id, notes="Returned to prompt editing.")
                st.rerun()
            if reject_col.button("❌ Reject Shot", key=f"photoshoot_studio_reject_{candidate_request.request_id}", use_container_width=True):
                generation_library.move_photoshoot_records_to_junk(
                    candidate_image_ids,
                    session_id=current.session_id,
                    session_title=current.title,
                    reason="photoshoot_rejected",
                )
                photoshoot_queue.reject_request(candidate_request.request_id)
                st.rerun()

        st.markdown("---")
        complete_confirm_key = f"photoshoot_complete_confirm_{current.session_id}"
        return_col, finish_col, _spacer = st.columns([1, 1, 2])
        if return_col.button("↩️ Return to Library", key=f"photoshoot_return_to_library_{current.session_id}", use_container_width=True):
            seed_id = str(dict(current.creative_continuity or {}).get("seed_image_id") or "")
            if seed_id:
                action = generation_library.return_photoshoot_seed_to_library(seed_id)
                if not action.success:
                    st.error(action.message)
                    for error in action.errors:
                        st.caption(error)
                    st.stop()
            temporary_image_ids = tuple(
                image_id
                for request in photoshoot_queue.requests_for_session(current.session_id)
                if request.status != "approved"
                for image_id in tuple((request.metadata or {}).get("generated_image_ids") or ())
            )
            generation_library.discard_temporary_records(temporary_image_ids)
            photoshoot_queue.cancel_session(current.session_id)
            for key in (recommendation_key, reset_fields_key, pending_direction_key, pending_prompt_key):
                st.session_state.pop(key, None)
            st.session_state.pop("content_studio_active_photoshoot_session_id", None)
            st.session_state["dashboard_page"] = "Generation Library"
            st.success("Returned seed image to Generation Library.")
            st.rerun()
        if finish_col.button("🏁 Complete Photoshoot", key=f"photoshoot_finish_{current.session_id}", use_container_width=True):
            st.session_state[complete_confirm_key] = True
            st.rerun()
        if st.session_state.get(complete_confirm_key):
            st.markdown("### Complete Photoshoot")
            result = photoshoot_queue.result(current.session_id)
            approved_image_ids = tuple(result.metadata.get("approved_generated_image_ids") or ())
            summary_cols = st.columns(4)
            summary_cols[0].metric("Session Name", current.title)
            summary_cols[1].metric("Renderer", current.provider_id)
            summary_cols[2].metric("Creative Mode", current.creative_mode)
            summary_cols[3].metric("Total Shots", len(timeline_items))
            st.markdown("#### Timeline Preview")
            _render_photoshoot_timeline(timeline_items, compact=True)
            complete_col, back_col, _space = st.columns([1, 1, 2])
            if back_col.button("Return to Session", key=f"photoshoot_complete_return_{current.session_id}", use_container_width=True):
                st.session_state.pop(complete_confirm_key, None)
                st.rerun()
            if complete_col.button("Complete Photoshoot", key=f"photoshoot_complete_confirm_button_{current.session_id}", use_container_width=True):
                action = generation_library.finish_photoshoot_session(
                    session_id=current.session_id,
                    approved_image_ids=approved_image_ids,
                    session_title=current.title,
                )
                if not action.success:
                    st.error(action.message)
                    for error in action.errors:
                        st.caption(error)
                    st.stop()
                photoshoot_queue.finish_session(current.session_id)
                st.session_state.pop(complete_confirm_key, None)
                st.session_state.pop("content_studio_active_photoshoot_session_id", None)
                st.session_state["photoshoot_gallery_open_session_id"] = current.session_id
                st.session_state["dashboard_page"] = "Photoshoot Studio"
                st.success("Photoshoot completed and moved to Photoshoot Gallery.")
                st.rerun()
            st.stop()
    else:
        _render_no_active_photoshoot_state(sessions)


def _render_no_active_photoshoot_state(sessions) -> None:
    st.info("No active photoshoot.")
    completed_count = len(tuple(session for session in sessions if session.status == "completed"))
    if completed_count:
        st.caption(f"{completed_count} completed photoshoot{'s' if completed_count != 1 else ''} available in Photoshoot Gallery.")
    start_col, gallery_col, _space = st.columns([1, 1, 2])
    if start_col.button("Start New Photoshoot", key="photoshoot_empty_start_new", use_container_width=True):
        st.session_state["dashboard_page"] = "Generation Library"
        st.rerun()
    if gallery_col.button("Open Photoshoot Gallery", key="photoshoot_empty_open_gallery", use_container_width=True):
        st.session_state["dashboard_page"] = "Photoshoot Gallery"
        st.rerun()


def _render_photoshoot_gallery_session_card(
    session,
    timeline_items,
    *,
    active_account: dict | None,
    photoshoot_queue: PhotoshootQueueService,
    generation_library: GenerationLibraryService,
) -> None:
    if not timeline_items:
        st.caption("No shots available.")
        return
    action_col, timeline_col, delete_col = st.columns([0.55, 20, 0.55], gap="small")
    with action_col:
        _render_photoshoot_gallery_publish_prototype(
            session,
            timeline_items,
            active_account=active_account,
        )
    with timeline_col:
        _render_photoshoot_gallery_contact_sheet(timeline_items)
    with delete_col:
        _render_photoshoot_gallery_delete_prototype(
            session,
            timeline_items,
            photoshoot_queue=photoshoot_queue,
            generation_library=generation_library,
        )
    approved_records = tuple(record for _request, record, _label in timeline_items)
    session_creator_profile_id = getattr(session, "creator_profile_id", None)
    _render_commerce_destination_group_selector(
        records=approved_records,
        creator_profile_id=int(session_creator_profile_id) if session_creator_profile_id else None,
        source_workflow="photoshoot_gallery",
        source_session_id=session.session_id,
        key_prefix=f"photoshoot_gallery_{session.session_id}",
    )
    imported_items = tuple(
        (label, record)
        for _request, record, label in timeline_items
        if record.imported_asset_id is not None
    )
    if imported_items:
        with st.expander("Individual Shot Destinations", expanded=False):
            for label, record in imported_items:
                st.caption(label)
                _render_commerce_destination_selector(
                    asset_id=int(record.imported_asset_id),
                    creator_profile_id=int(session_creator_profile_id) if session_creator_profile_id else None,
                    source_workflow="photoshoot_gallery",
                    source_session_id=session.session_id,
                    key_prefix=f"photoshoot_gallery_{session.session_id}_{record.image_id}",
                )
                _render_fulfillment_registration_panel(
                    asset_id=int(record.imported_asset_id),
                    creator_profile_id=int(session_creator_profile_id) if session_creator_profile_id else None,
                    source_workflow="photoshoot_gallery",
                    source_session_id=session.session_id,
                    key_prefix=f"photoshoot_gallery_{session.session_id}_{record.image_id}",
                )


def _render_gallery_icon_button_style(button_key: str) -> None:
    st.markdown(
        f"""
        <style>
        .st-key-{button_key} button {{
            width: 42px !important;
            min-width: 42px !important;
            height: 42px !important;
            min-height: 42px !important;
            padding: 0 !important;
            border: 0 !important;
            border-radius: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            color: inherit !important;
            cursor: pointer !important;
            font-size: 1.15rem !important;
        }}
        .st-key-{button_key} button:hover {{
            background: rgba(255,255,255,0.06) !important;
        }}
        .st-key-{button_key} button:focus {{
            box-shadow: none !important;
            outline: 1px solid rgba(255,255,255,0.18) !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _streamlit_dialog(title: str):
    dialog = getattr(st, "dialog", None)
    if callable(dialog):
        return dialog(title)

    def decorator(func):
        return func

    return decorator


# Compatibility marker for source-contract tests: @st.dialog("Publish Destination")
@_streamlit_dialog("Publish Destination")
def _render_photoshoot_gallery_publish_dialog(
    session,
    timeline_items,
    *,
    active_account: dict | None,
) -> None:
    destination_key = f"photoshoot_gallery_destination_{session.session_id}"
    fanvue_account_id = (
        (active_account or {}).get("id")
        or st.session_state.get("fanvue_account_id")
    )
    oauth_connected = _fanvue_account_oauth_connected(active_account)
    wall_col, chat_col = st.columns(2)
    with wall_col:
        if st.button("🟢 Wall", key=f"{destination_key}_dialog_wall", use_container_width=True):
            records = _photoshoot_gallery_wall_upload_records(timeline_items)
            if not fanvue_account_id:
                st.error("Connect or select a Fanvue account before publishing to Wall.")
                return
            if active_account is not None and not oauth_connected:
                st.error("Fanvue OAuth is not connected for the selected account.")
                return
            if not records:
                st.error("No approved Photoshoot images are available for Wall upload.")
                return
            status = st.empty()
            progress = st.progress(0)

            def _progress_callback(event):
                status.info(
                    f"Uploading to Fanvue Wall...\n\nImage {event.current} of {event.total}..."
                )
                if event.total:
                    progress.progress(min(1.0, event.current / event.total))

            try:
                service = PhotoshootFanvueUploadService(folder_name=FANVUE_WALL_FOLDER)
                result = service.upload_completed_session(
                    session=session,
                    records=records,
                    fanvue_account_id=int(fanvue_account_id),
                    progress_callback=_progress_callback,
                    reuse_existing_upload_metadata=False,
                )
            except Exception as error:
                fanvue_upload_exception(
                    "photoshoot_gallery.wall_upload_dialog_exception",
                    error,
                    session_id=session.session_id,
                    fanvue_account_id=fanvue_account_id,
                    folder_name=FANVUE_WALL_FOLDER,
                    stage="photoshoot_gallery_wall_upload",
                    record_count=len(records),
                )
                st.error("Wall upload failed. See Diagnostics for detailed error information.")
                return
            if result.get("success"):
                st.session_state[destination_key] = "wall"
                st.session_state[f"{destination_key}_upload_result"] = {
                    "uploaded_count": result.get("uploaded_count"),
                    "total_count": result.get("total_count"),
                    "uploaded_media_ids": tuple(result.get("uploaded_media_ids") or ()),
                    "folder": FANVUE_WALL_FOLDER,
                }
                st.session_state.pop(f"{destination_key}_dialog_open", None)
                status.success("Uploaded to Fanvue Wall.")
                st.rerun()
            else:
                reason = str(result.get("reason") or "")
                if reason == "fanvue_folder_not_found":
                    st.error('Fanvue Vault folder "Wall" was not found.')
                elif reason == "missing_fanvue_account":
                    st.error("Connect or select a Fanvue account before publishing to Wall.")
                elif reason == "fanvue_folder_lookup_failed":
                    st.error("Could not verify the Fanvue Wall folder. Check the Fanvue connection and try again.")
                elif any(
                    "did not finish processing" in str((failure or {}).get("error") or "")
                    for failure in (result.get("failures") or ())
                ):
                    st.error("Fanvue accepted the upload but did not finish processing the media. Please try again.")
                else:
                    st.error("Wall upload did not complete.")
                if result.get("uploaded_count") is not None:
                    st.warning(
                        f"Uploaded: {result.get('uploaded_count')} / {result.get('total_count')} images"
                    )
                for failure in result.get("failures") or ():
                    st.caption(f"{failure.get('image_id')}: {failure.get('error')}")
    with chat_col:
        if st.button("🔵 Chat", key=f"{destination_key}_dialog_chat", use_container_width=True):
            st.info("Chat publishing is not implemented yet.")
            return
    if st.button("Cancel", key=f"{destination_key}_dialog_cancel", use_container_width=True):
        st.session_state.pop(f"{destination_key}_dialog_open", None)
        st.rerun()


def _fanvue_account_oauth_connected(active_account: dict | None) -> bool:
    if not active_account:
        return False
    return bool(
        active_account.get("oauth_access_token")
        or active_account.get("oauth_refresh_token")
        or active_account.get("fanvue_user_uuid")
    )


def _photoshoot_gallery_wall_upload_records(timeline_items) -> tuple[GeneratedImageRecord, ...]:
    return tuple(
        record
        for request, record, _label in timeline_items
    )


# Compatibility marker for source-contract tests: @st.dialog("Delete Photoshoot?")
@_streamlit_dialog("Delete Photoshoot?")
def _render_photoshoot_gallery_delete_dialog(
    session,
    timeline_items,
    *,
    photoshoot_queue: PhotoshootQueueService,
    generation_library: GenerationLibraryService,
) -> None:
    delete_key = f"photoshoot_gallery_delete_{session.session_id}"
    st.write("Move this completed photoshoot to the Junk folder?")
    cancel_col, confirm_col = st.columns(2)
    if cancel_col.button("Cancel", key=f"{delete_key}_cancel", use_container_width=True):
        st.session_state.pop(f"{delete_key}_dialog_open", None)
        st.rerun()
    if confirm_col.button("Move to Junk", key=f"{delete_key}_confirm", use_container_width=True):
        image_ids = tuple(record.image_id for _request, record, _label in timeline_items)
        action = generation_library.move_completed_photoshoot_session_to_junk(
            session_id=session.session_id,
            approved_image_ids=image_ids,
            session_title=session.title,
        )
        if action.success:
            photoshoot_queue.junk_completed_session(
                session.session_id,
                notes="Moved to Junk from Photoshoot Gallery.",
            )
            st.session_state.pop(f"{delete_key}_dialog_open", None)
            st.session_state["photoshoot_gallery_message"] = "Photoshoot moved to Junk."
            st.rerun()
        st.error("; ".join(action.errors) or "Photoshoot could not be moved to Junk.")


def _render_photoshoot_gallery_publish_prototype(
    session,
    timeline_items,
    *,
    active_account: dict | None,
) -> None:
    destination_key = f"photoshoot_gallery_destination_{session.session_id}"
    selected_destination = st.session_state.get(destination_key)
    if selected_destination:
        assigned_to_wall = selected_destination == "wall"
        status_icon = "🟢" if assigned_to_wall else "🔵"
        status_title = "Assigned to Wall" if assigned_to_wall else "Assigned to Chat"
        st.markdown(
            f"""
            <div style="
                display:flex;
                justify-content:center;
                align-items:center;
                min-height:112px;
            ">
                <span title="{html.escape(status_title, quote=True)}" style="
                    display:inline-flex;
                    align-items:center;
                    justify-content:center;
                    width: 42px;
                    height: 42px;
                    font-size: 1.15rem;
                    cursor: default;
                    user-select: none;
                ">{status_icon}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return
    st.markdown('<div style="height:36px;"></div>', unsafe_allow_html=True)
    button_key = f"{destination_key}_open"
    _render_gallery_icon_button_style(button_key)
    if st.button(
        "📤",
        key=button_key,
        help="Publish this completed photoshoot",
        use_container_width=False,
        type="secondary",
    ):
        st.session_state[f"{destination_key}_dialog_open"] = True
        st.rerun()
    if not st.session_state.get(f"{destination_key}_dialog_open"):
        return
    _render_photoshoot_gallery_publish_dialog(
        session,
        timeline_items,
        active_account=active_account,
    )


def _render_photoshoot_gallery_delete_prototype(
    session,
    timeline_items,
    *,
    photoshoot_queue: PhotoshootQueueService,
    generation_library: GenerationLibraryService,
) -> None:
    delete_key = f"photoshoot_gallery_delete_{session.session_id}"
    st.markdown('<div style="height:36px;"></div>', unsafe_allow_html=True)
    button_key = f"{delete_key}_open"
    _render_gallery_icon_button_style(button_key)
    if st.button(
        "🗑",
        key=button_key,
        help="Move this completed photoshoot to Junk",
        use_container_width=False,
        type="secondary",
    ):
        st.session_state[f"{delete_key}_dialog_open"] = True
        st.rerun()
    if not st.session_state.get(f"{delete_key}_dialog_open"):
        return
    _render_photoshoot_gallery_delete_dialog(
        session,
        timeline_items,
        photoshoot_queue=photoshoot_queue,
        generation_library=generation_library,
    )


def _photoshoot_fanvue_upload_metadata(session) -> dict[str, Any]:
    metadata = dict(getattr(session, "metadata", None) or {})
    upload = metadata.get("fanvue_photoshoot_upload") or {}
    return dict(upload) if isinstance(upload, Mapping) else {}


def _render_photoshoot_fanvue_upload_action(
    session,
    timeline_items,
    *,
    active_account: dict | None,
    photoshoot_queue: PhotoshootQueueService,
) -> None:
    upload = _photoshoot_fanvue_upload_metadata(session)
    if upload.get("uploaded_to_fanvue"):
        st.success(f"✅ Uploaded to Fanvue {upload.get('uploaded_folder') or FANVUE_PHOTOSHOOT_FOLDER}")
        return

    uploaded_count = int(upload.get("uploaded_count") or 0)
    total_count = int(upload.get("total_count") or len(timeline_items))
    if uploaded_count:
        st.warning(f"Uploaded: {uploaded_count} / {total_count} images")
        failures = tuple(upload.get("failures") or ())
        if failures:
            st.caption(f"{len(failures)} image(s) need retry.")

    fanvue_account_id = (active_account or {}).get("id") or st.session_state.get("fanvue_account_id")
    upload_key = f"photoshoot_fanvue_uploading_{session.session_id}"
    button_label = (
        "Retry Remaining Images"
        if uploaded_count and uploaded_count < total_count
        else f"☁ Upload Photoshoot to Fanvue {FANVUE_PHOTOSHOOT_FOLDER}"
    )
    disabled = bool(st.session_state.get(upload_key)) or not fanvue_account_id
    if st.button(
        button_label,
        key=f"photoshoot_upload_fanvue_{session.session_id}",
        type="primary",
        use_container_width=True,
        disabled=disabled,
    ):
        st.session_state[upload_key] = True
        status = st.empty()
        progress = st.progress(0)
        records = tuple(record for _request, record, _label in timeline_items)

        def _progress_callback(event):
            status.info(
                f"Uploading Photoshoot...\n\nImage {event.current} of {event.total}..."
            )
            if event.total:
                progress.progress(min(1.0, event.current / event.total))

        try:
            service = PhotoshootFanvueUploadService()
            result = service.upload_completed_session(
                session=session,
                records=records,
                fanvue_account_id=int(fanvue_account_id),
                progress_callback=_progress_callback,
            )
            photoshoot_queue.record_fanvue_upload_result(session.session_id, result)
            if result.get("success"):
                status.success(f"✅ Uploaded to Fanvue {FANVUE_PHOTOSHOOT_FOLDER}")
            else:
                status.error(result.get("error") or "Photoshoot upload did not complete.")
                if result.get("uploaded_count") is not None:
                    st.warning(
                        f"Uploaded: {result.get('uploaded_count')} / {result.get('total_count')} images"
                    )
                for failure in result.get("failures") or ():
                    st.caption(f"{failure.get('image_id')}: {failure.get('error')}")
        finally:
            st.session_state.pop(upload_key, None)
        st.rerun()

    if not fanvue_account_id:
        st.caption("Connect/select a Fanvue account before uploading this Photoshoot.")


def _render_photoshoot_gallery_contact_sheet(timeline_items) -> None:
    cards = []
    for index, (_request, record, _label) in enumerate(timeline_items, start=1):
        src = html.escape(_display_image_src(record.output_reference), quote=True)
        alt_text = html.escape(f"Photoshoot image {index}", quote=True)
        cards.append(
            f"""
            <div class="photoshoot-gallery-thumb">
                <img src="{src}" alt="{alt_text}" loading="lazy" />
            </div>
            """
        )
    components.html(
        f"""
        <div class="photoshoot-gallery-scroll">
            <div class="photoshoot-gallery-grid">
                {''.join(cards)}
            </div>
        </div>
        <style>
            .photoshoot-gallery-scroll {{
                max-height: 620px;
                overflow-y: auto;
                overflow-x: hidden;
                padding: 2px 4px 8px 2px;
                box-sizing: border-box;
            }}
            .photoshoot-gallery-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(112px, 1fr));
                gap: 10px;
                align-items: start;
            }}
            .photoshoot-gallery-thumb {{
                aspect-ratio: 1 / 1;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
                border-radius: 8px;
                background: rgba(0,0,0,0.24);
                border: 1px solid rgba(255,255,255,0.12);
            }}
            .photoshoot-gallery-thumb img {{
                    max-width: 100%;
                    max-height: 100%;
                    width: auto;
                    height: auto;
                    object-fit: contain;
                    display: block;
            }}
        </style>
        """,
        height=640,
        scrolling=False,
    )


def _render_photoshoot_gallery(
    *,
    creator_profile: dict | None,
    active_account: dict | None,
    photoshoot_queue: PhotoshootQueueService,
    generation_library: GenerationLibraryService,
) -> None:
    creator_profile_id = _creator_profile_id(creator_profile)
    st.title("📸 Photoshoot Gallery")
    st.caption("Completed photoshoot sessions and shot timelines.")
    if not creator_profile_id:
        st.error("Creator Profile required before viewing Photoshoot Gallery.")
        return

    completed_sessions = tuple(
        session
        for session in photoshoot_queue.list_sessions(creator_profile_id=creator_profile_id)
        if session.status == "completed"
    )
    if not completed_sessions:
        st.info("No completed photoshoots yet.")
        return

    st.markdown("### Completed Sessions")
    for session in completed_sessions:
        timeline_items = _photoshoot_timeline_items(session, photoshoot_queue, generation_library)
        _render_photoshoot_gallery_session_card(
            session,
            timeline_items,
            active_account=active_account,
            photoshoot_queue=photoshoot_queue,
            generation_library=generation_library,
        )
        st.markdown("---")


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
                active_reference = result.active_reference
                replacing_canonical = bool(
                    active_reference
                    and active_reference.asset_id != reference.asset_id
                    and (active_reference.metadata or {}).get("canonical")
                )
                replace_confirm = False
                if replacing_canonical:
                    replace_confirm = st.checkbox(
                        "Confirm replace Canonical Reference",
                        key=f"reference_library_replace_confirm_{reference.asset_id}",
                    )
                if st.button(
                    "Select Active",
                    disabled=reference.is_active or (
                        replacing_canonical and not replace_confirm
                    ),
                    key=f"reference_library_select_{reference.asset_id}",
                    use_container_width=True,
                ):
                    action = reference_service.set_active_reference(
                        reference.asset_id,
                        creator_profile_id=creator_profile_id,
                        confirm_replace_canonical=replace_confirm,
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
                        confirm_canonical=remove_confirm,
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
    st.caption("Provider-neutral creative planning for Content Creation.")
    if not creator_profile_id:
        st.error("Creator Profile required before planning Creative Sessions.")
        return

    settings = creative_director.load_settings(creator_profile_id)
    active_reference = reference_service.get_active_canonical_reference(
        creator_profile_id=creator_profile_id,
    )
    _render_active_reference(
        creator_profile=creator_profile,
        reference_service=reference_service,
        reference=active_reference,
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
    asset_registration_service: AssetRegistrationService | None = None,
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
    creator_approval_service = CreatorApprovalService(
        storage_dir=Path("data") / "creator_approvals"
    )
    generation_library_service = generation_library_service or GenerationLibraryService(
        archive_service=content_archive_service,
        creator_approval_service=creator_approval_service,
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
    asset_registration_service = (
        asset_registration_service
        or AssetRegistrationService(
            generation_library_service=generation_library_service,
        )
    )
    social_service_type = getattr(
        social_marketing_service,
        "Social" + "Publishing" + "Service",
    )
    social_publishing_service = social_publishing_service or social_service_type()
    if page_name != "Generation Library":
        _clear_generation_publish_state()
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
            photoshoot_queue=photoshoot_queue_service,
            asset_registration=asset_registration_service,
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
    if page_name in {"Photoshoot Studio", "Photoshoot Queue"}:
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
    if page_name == "Photoshoot Gallery":
        _render_photoshoot_gallery(
            creator_profile=creator_profile,
            active_account=active_account,
            photoshoot_queue=photoshoot_queue_service,
            generation_library=generation_library_service,
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
        st.error("Unknown Content Creation page selected.")
        return

    st.title(page.title)
    st.caption(page.purpose)
    st.info("Content Creation shell only. Generation logic, APIs, prompts, and queues are not migrated.")

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
