"""Read-only Asset Library dashboard page."""

from __future__ import annotations

import json
from datetime import datetime

import streamlit as st

from app.dashboard.components.asset_picker import (
    render_asset_grid,
    render_asset_thumbnail,
)
from app.models.asset_library import (
    AssetDerivativeSummary,
    AssetLibraryDetails,
    AssetLibraryFilter,
    AssetPublishingSummary,
    AssetRelationshipSummary,
    AssetStorageSummary,
)
from app.services.asset_library_service import AssetLibraryService


MEDIA_TYPE_OPTIONS = ("all", "image", "video")
CLASSIFICATION_OPTIONS = ("ALL", "TEASE", "VIP", "PREMIUM", "EDGE_CASE")


def build_asset_library_filter(
    *,
    search: str | None,
    media_type: str,
    classification: str,
    eligible_only: bool,
    limit: int,
    tags: str | None = None,
    themes: str | None = None,
    status: str | None = None,
    creator_profile_id: int | None = None,
    product_id: str | None = None,
    experience_id: str | None = None,
    publishing_status: str | None = None,
    has_local_vault_original: bool | None = None,
    has_derivative_preview: bool | None = None,
    is_reference_image: bool | None = None,
    legacy_content_id: int | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
) -> AssetLibraryFilter:
    return AssetLibraryFilter(
        search=(search or "").strip() or None,
        media_type=None if media_type == "all" else media_type,
        classification=None if classification == "ALL" else classification,
        eligible_only=eligible_only,
        limit=int(limit),
        tags=_csv_values(tags or ""),
        themes=_csv_values(themes or ""),
        status=(status or "").strip() or None,
        creator_profile_id=creator_profile_id,
        product_id=(product_id or "").strip() or None,
        experience_id=(experience_id or "").strip() or None,
        publishing_status=(publishing_status or "").strip() or None,
        has_local_vault_original=has_local_vault_original,
        has_derivative_preview=has_derivative_preview,
        is_reference_image=is_reference_image,
        legacy_content_id=legacy_content_id,
        created_after=_parse_date_filter(created_after),
        created_before=_parse_date_filter(created_before),
    )


def _parse_date_filter(value: str | None) -> datetime | None:
    clean = (value or "").strip()
    if not clean:
        return None
    try:
        return datetime.fromisoformat(clean)
    except ValueError:
        return None


def _optional_bool_filter(value: str) -> bool | None:
    if value == "Yes":
        return True
    if value == "No":
        return False
    return None


def _format_date(value: datetime | None) -> str:
    if not value:
        return "Unknown"
    return value.strftime("%Y-%m-%d")


def _display_tags(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "-"


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


def _render_storage(summary: AssetStorageSummary | None) -> None:
    st.markdown("#### Storage")
    if not summary:
        st.caption("Storage metadata unavailable.")
        return
    st.write(f"Original: {summary.original_path or '-'}")
    st.write(f"Original Source: {summary.original_source or '-'}")
    st.write(f"Original Exists: {'Yes' if summary.original_exists else 'No'}")
    st.write(f"Local Vault: {summary.local_vault_path or '-'}")
    st.write(f"Legacy Path: {summary.legacy_file_path or '-'}")


def _render_derivative(summary: AssetDerivativeSummary | None) -> None:
    st.markdown("#### Derivatives")
    if not summary:
        st.caption("Derivative metadata unavailable.")
        return
    st.write(f"Preview: {summary.preview_path or '-'}")
    st.write(f"Type: {summary.derivative_type}")
    st.write(f"Storage: {summary.storage or '-'}")
    st.write(f"Generated: {summary.generated_at or '-'}")
    st.write(f"Source: {summary.source or '-'}")


def _render_relationships(summary: AssetRelationshipSummary | None) -> None:
    st.markdown("#### Relationships")
    if not summary:
        st.caption("Relationship metadata unavailable.")
        return
    c1, c2 = st.columns(2)
    c1.metric("Products", summary.product_count)
    c2.metric("Experiences", summary.experience_count)
    if summary.product_ids:
        st.caption(f"Products: {', '.join(summary.product_ids)}")
    if summary.product_delivery_types:
        st.caption(
            f"Delivery Types: {', '.join(summary.product_delivery_types)}"
        )
    if summary.experience_ids:
        st.caption(f"Experiences: {', '.join(summary.experience_ids)}")
    for experience in summary.experience_summaries:
        label = experience.title or experience.experience_id
        detail_parts = [
            value
            for value in (
                experience.experience_type,
                experience.relationship_source,
                "compatibility" if experience.compatibility else None,
            )
            if value
        ]
        st.caption(
            f"Experience: {label}"
            + (f" ({' | '.join(detail_parts)})" if detail_parts else "")
        )
        if experience.summary:
            st.caption(experience.summary)
        if experience.themes:
            st.caption(f"Themes: {', '.join(experience.themes)}")
        if experience.keywords:
            st.caption(f"Keywords: {', '.join(experience.keywords)}")
        if experience.mood:
            st.caption(f"Mood: {experience.mood}")
        if experience.story_progression:
            st.caption(f"Story: {experience.story_progression}")
        if experience.publishing_readiness:
            st.caption(f"Publishing Readiness: {experience.publishing_readiness}")
    if summary.legacy_product_id:
        st.caption(f"Legacy Product: {summary.legacy_product_id}")


def _render_publishing(summary: AssetPublishingSummary | None) -> None:
    st.markdown("#### Publishing")
    if not summary:
        st.caption("Publishing metadata unavailable.")
        return
    st.write(f"Status: {summary.status}")
    st.write(f"Detail: {summary.detail or '-'}")
    st.write(f"Provider Media ID: {summary.provider_media_id or '-'}")
    st.write(f"Provider Preview ID: {summary.provider_preview_media_id or '-'}")
    st.write(f"Provider Full ID: {summary.provider_full_media_id or '-'}")
    if summary.provider_error:
        st.error(summary.provider_error)


def _render_actions(
    details: AssetLibraryDetails,
    service: AssetLibraryService,
) -> None:
    item = details.item
    st.markdown("### Actions")
    with st.expander("Copy", expanded=True):
        st.code(str(item.asset_id), language="text")
        if details.storage:
            st.text_area(
                "Original Path",
                value=details.storage.original_path or "",
                key=f"asset_library_copy_original_{item.asset_id}",
                disabled=True,
            )
            st.text_area(
                "Local Vault Path",
                value=details.storage.local_vault_path or "",
                key=f"asset_library_copy_vault_{item.asset_id}",
                disabled=True,
            )
        metadata_summary = {
            "asset_id": item.asset_id,
            "file_name": item.file_name,
            "media_type": item.media_type,
            "classification": item.classification,
            "status": item.status,
            "tags": list(item.tags),
            "themes": list(item.themes),
            "summary": details.summary,
        }
        st.text_area(
            "Metadata Summary",
            value=json.dumps(metadata_summary, indent=2),
            key=f"asset_library_copy_metadata_{item.asset_id}",
            disabled=True,
        )

    with st.expander("Derivative Preview"):
        if st.button(
            "Regenerate Preview",
            key=f"asset_library_regenerate_preview_{item.asset_id}",
        ):
            result = service.regenerate_derivative_preview(item.asset_id)
            if result.success:
                st.success(result.message)
                if result.data:
                    st.json(result.data)
            else:
                st.error(result.message)
        if st.button(
            "Refresh Derivative Metadata",
            key=f"asset_library_refresh_derivative_{item.asset_id}",
        ):
            result = service.refresh_derivative_summary(item.asset_id)
            if result.success:
                st.success(result.message)
                st.json(result.data or {})
            else:
                st.error(result.message)

    with st.expander("Metadata Edit"):
        classification = st.text_input(
            "Classification",
            value=item.classification or "",
            key=f"asset_library_edit_classification_{item.asset_id}",
        )
        tags = st.text_input(
            "Tags",
            value=", ".join(item.tags),
            key=f"asset_library_edit_tags_{item.asset_id}",
        )
        themes = st.text_input(
            "Themes",
            value=", ".join(item.themes),
            key=f"asset_library_edit_themes_{item.asset_id}",
        )
        if st.button(
            "Save Metadata",
            key=f"asset_library_save_metadata_{item.asset_id}",
        ):
            result = service.update_asset_metadata(
                item.asset_id,
                classification=classification,
                tags=_csv_values(tags),
                themes=_csv_values(themes),
            )
            if result.success:
                st.success(result.message)
            else:
                st.error(result.message)

    with st.expander("Workflow Handoff"):
        if st.button(
            "Create Product Draft",
            key=f"asset_library_handoff_product_{item.asset_id}",
        ):
            _handoff_to_product_workflow((item.asset_id,))
        if st.button(
            "Add to Experience",
            key=f"asset_library_handoff_experience_{item.asset_id}",
        ):
            _handoff_to_experience_workflow((item.asset_id,))
        if st.button(
            "Send to Publishing Workflow",
            key=f"asset_library_handoff_publishing_{item.asset_id}",
        ):
            _handoff_to_publishing_workflow((item.asset_id,))


def _handoff_to_product_workflow(asset_ids: tuple[int, ...]) -> None:
    st.session_state["asset_library_handoff_asset_ids"] = list(asset_ids)
    st.session_state["product_catalog_prefill_asset_ids"] = list(asset_ids)
    if asset_ids:
        st.session_state["product_catalog_retry_asset_id"] = int(asset_ids[0])
    st.session_state["dashboard_page"] = "Product Catalog"
    st.success("Selected asset IDs were handed off to Product Catalog.")


def _handoff_to_experience_workflow(asset_ids: tuple[int, ...]) -> None:
    st.session_state["asset_library_handoff_asset_ids"] = list(asset_ids)
    st.session_state["experience_prefill_asset_ids"] = list(asset_ids)
    st.success("Selected asset IDs are ready for the Experience workflow.")


def _handoff_to_publishing_workflow(asset_ids: tuple[int, ...]) -> None:
    st.session_state["asset_library_handoff_asset_ids"] = list(asset_ids)
    st.session_state["publishing_prefill_asset_ids"] = list(asset_ids)
    st.session_state["dashboard_page"] = "Wall Scheduler"
    st.success("Selected asset IDs were handed off to the Publishing workflow.")


def _render_bulk_actions(selected_asset_ids: tuple[int, ...]) -> None:
    st.markdown("### Bulk Actions")
    st.caption("Safe handoffs only. Publishing, archiving, and deletion are not performed here.")
    st.code(", ".join(str(asset_id) for asset_id in selected_asset_ids), language="text")
    c1, c2, c3 = st.columns(3)
    if c1.button(
        "Handoff to Products",
        disabled=not selected_asset_ids,
        key="asset_library_bulk_product_handoff",
    ):
        _handoff_to_product_workflow(selected_asset_ids)
    if c2.button(
        "Handoff to Experiences",
        disabled=not selected_asset_ids,
        key="asset_library_bulk_experience_handoff",
    ):
        _handoff_to_experience_workflow(selected_asset_ids)
    if c3.button(
        "Handoff to Publishing",
        disabled=not selected_asset_ids,
        key="asset_library_bulk_publishing_handoff",
    ):
        _handoff_to_publishing_workflow(selected_asset_ids)


def _render_details(
    details: AssetLibraryDetails | None,
    service: AssetLibraryService,
) -> None:
    st.markdown("### Asset Details")
    if not details:
        st.info("Select an asset to view details.")
        return
    item = details.item
    preview_col, meta_col = st.columns([1, 2])
    with preview_col:
        render_asset_thumbnail(item, caption=f"Asset #{item.asset_id}")
    with meta_col:
        st.subheader(item.file_name or f"Asset {item.asset_id}")
        st.caption(f"Asset ID: {item.asset_id}")
        st.caption(f"Media Type: {item.media_type}")
        st.caption(f"Status: {item.status or '-'}")
        st.caption(f"Active: {'Yes' if item.is_active else 'No'}")
        st.caption(f"Reference Image: {'Yes' if item.is_reference_image else 'No'}")
        st.caption(f"Imported: {_format_date(item.created_at)}")
        st.metric("Classification", item.classification or "-")
        st.metric("Confidence", "-" if details.confidence is None else f"{details.confidence:.2f}")

    st.markdown("#### Metadata")
    st.write(f"Tags: {_display_tags(item.tags)}")
    st.write(f"Themes: {_display_tags(item.themes)}")
    st.write(f"Summary: {details.summary or '-'}")
    st.write(f"Reasoning: {details.reasoning or '-'}")
    st.write(f"Risk Flags: {_display_tags(details.risk_flags)}")
    st.write(f"Explicit: {'Yes' if details.is_explicit else 'No'}")
    st.write(f"Nudity Level: {details.nudity_level or '-'}")
    st.write(f"Sexual Intensity: {details.sexual_intensity or '-'}")

    _render_storage(details.storage)
    _render_derivative(details.derivative)
    _render_relationships(details.relationship)
    _render_publishing(details.publishing)
    _render_actions(details, service)


def render_asset_library(
    *,
    asset_library_service: AssetLibraryService | None = None,
) -> None:
    service = asset_library_service or AssetLibraryService()

    st.title("Asset Library")
    st.caption("Read-only media management view for Creator OS assets.")

    with st.expander("Filters", expanded=True):
        f1, f2, f3 = st.columns(3)
        search = f1.text_input("Search", key="asset_library_search")
        media_type = f2.selectbox(
            "Media Type",
            MEDIA_TYPE_OPTIONS,
            key="asset_library_media_type",
        )
        classification = f3.selectbox(
            "Classification",
            CLASSIFICATION_OPTIONS,
            key="asset_library_classification",
        )
        f4, f5, f6 = st.columns(3)
        eligible_only = f4.checkbox(
            "Active library only",
            value=True,
            key="asset_library_eligible_only",
        )
        limit = f5.number_input(
            "Limit",
            min_value=1,
            max_value=1000,
            value=100,
            step=25,
            key="asset_library_limit",
        )
        f6.selectbox(
            "Relationship Filter",
            ("All", "Use Product ID", "Use Experience ID"),
            key="asset_library_future_relationship_filter",
        )
        f7, f8, f9 = st.columns(3)
        tags = f7.text_input("Tags", key="asset_library_tags")
        themes = f8.text_input("Themes", key="asset_library_themes")
        status = f9.text_input("Status", key="asset_library_status")
        f10, f11, f12 = st.columns(3)
        creator_profile_id = f10.number_input(
            "Creator Profile ID",
            min_value=0,
            value=0,
            step=1,
            key="asset_library_creator_profile_id",
        )
        product_id = f11.text_input("Product ID", key="asset_library_product_id")
        experience_id = f12.text_input(
            "Experience ID",
            key="asset_library_experience_id",
        )
        f13, f14, f15 = st.columns(3)
        publishing_status = f13.text_input(
            "Publishing Status",
            key="asset_library_publishing_status",
        )
        vault_filter = f14.selectbox(
            "Local Vault",
            ("Any", "Yes", "No"),
            key="asset_library_local_vault_filter",
        )
        derivative_filter = f15.selectbox(
            "Derivative Preview",
            ("Any", "Yes", "No"),
            key="asset_library_derivative_filter",
        )
        f16, f17, f18, f19 = st.columns(4)
        legacy_content_id_raw = f16.number_input(
            "Legacy Content ID",
            min_value=0,
            value=0,
            step=1,
            key="asset_library_legacy_content_id",
        )
        reference_filter = f17.selectbox(
            "Reference Image",
            ("Any", "Yes", "No"),
            key="asset_library_reference_filter",
        )
        created_after = f18.text_input(
            "Created After",
            placeholder="YYYY-MM-DD",
            key="asset_library_created_after",
        )
        created_before = f19.text_input(
            "Created Before",
            placeholder="YYYY-MM-DD",
            key="asset_library_created_before",
        )

    filters = build_asset_library_filter(
        search=search,
        media_type=media_type,
        classification=classification,
        eligible_only=eligible_only,
        limit=limit,
        tags=tags,
        themes=themes,
        status=status,
        creator_profile_id=(
            int(creator_profile_id) if creator_profile_id else None
        ),
        product_id=product_id,
        experience_id=experience_id,
        publishing_status=publishing_status,
        has_local_vault_original=_optional_bool_filter(vault_filter),
        has_derivative_preview=_optional_bool_filter(derivative_filter),
        is_reference_image=_optional_bool_filter(reference_filter),
        legacy_content_id=(
            int(legacy_content_id_raw) if legacy_content_id_raw else None
        ),
        created_after=created_after,
        created_before=created_before,
    )
    result = service.search_assets(filters)

    st.markdown("### Assets")
    st.caption(f"{result.total} asset(s) found.")
    if not result.items:
        st.info("No assets match the current filters.")
        return

    labels = {
        f"#{item.asset_id} - {item.file_name or item.media_type}": item.asset_id
        for item in result.items
    }
    selected_label = st.selectbox(
        "Selected Asset",
        list(labels),
        key="asset_library_selected_asset",
    )
    selected_asset_id = labels[selected_label]
    selected_asset_ids = st.multiselect(
        "Bulk Selected Assets",
        options=[item.asset_id for item in result.items],
        default=[selected_asset_id],
        format_func=lambda asset_id: (
            f"#{asset_id} - "
            f"{next(item.file_name or item.media_type for item in result.items if item.asset_id == asset_id)}"
        ),
        key="asset_library_bulk_selected_assets",
    )

    render_asset_grid(result.items, columns=3)
    _render_bulk_actions(tuple(int(asset_id) for asset_id in selected_asset_ids))

    details = service.get_asset_details(selected_asset_id)
    _render_details(details, service)
