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
from app.models.chat_commerce_inventory import ChatCommerceInventoryFilter
from app.services.asset_library_service import AssetLibraryService
from app.services.chat_commerce_inventory_service import ChatCommerceInventoryService


MEDIA_TYPE_OPTIONS = ("all", "image", "video")
CLASSIFICATION_OPTIONS = ("ALL", "TEASE", "VIP", "PREMIUM", "EDGE_CASE")
INVENTORY_FILTER_OPTIONS = (
    "All",
    "Chat Ready",
    "Fulfillment Ready",
    "Waiting For Media Link",
    "Awaiting Destination",
    "Blocked",
    "Temporarily Unavailable",
    "Retired",
    "Recommendation Ready",
)


def _money(cents: int) -> str:
    return f"${int(cents or 0) / 100:.2f}"


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


def _inventory_filter_from_ui(
    *,
    status_filter: str,
    destination: str,
    product_id: str,
    experience_id: str,
    source_workflow: str,
) -> ChatCommerceInventoryFilter:
    flags = {
        "Chat Ready": {"chat_ready": True},
        "Fulfillment Ready": {"fulfillment_ready": True},
        "Waiting For Media Link": {"waiting_for_media_link": True},
        "Awaiting Destination": {"awaiting_destination": True},
        "Blocked": {"blocked": True},
        "Temporarily Unavailable": {"temporarily_unavailable": True},
        "Retired": {"retired": True},
        "Recommendation Ready": {"recommendation_ready": True},
    }.get(status_filter, {})
    return ChatCommerceInventoryFilter(
        destination=(destination or "").strip() or None,
        product_id=(product_id or "").strip() or None,
        experience_id=(experience_id or "").strip() or None,
        source_workflow=(source_workflow or "").strip() or None,
        **flags,
    )


def _render_inventory_summary(summary) -> None:
    rows = (
        (
            ("Total Business Assets", summary.total_business_assets),
            ("Chat Ready", summary.chat_ready),
            ("Fulfillment Ready", summary.fulfillment_ready),
            ("Waiting For Media Link", summary.waiting_for_media_link),
        ),
        (
            ("Awaiting Destination", summary.awaiting_destination),
            ("Blocked", summary.blocked),
            ("Unavailable", summary.temporarily_unavailable),
            ("Retired", summary.retired),
        ),
        (
            ("Recommendation Ready", summary.recommendation_ready),
            ("Recommendation Pending", summary.recommendation_pending),
            ("Total Revenue", _money(summary.total_revenue_cents)),
            ("Total Purchases", summary.total_purchases),
        ),
    )
    for row in rows:
        columns = st.columns(4)
        for column, (label, value) in zip(columns, row):
            column.metric(label, value)
    st.metric("Overall Conversion", f"{summary.overall_conversion:.1%}")


def _render_inventory_actions(item) -> None:
    if not item.quick_actions:
        st.caption("No creator action available.")
        return
    with st.expander(f"Actions for Asset #{item.asset_id}"):
        if "Open Fanvue" in item.quick_actions:
            st.link_button("Open Fanvue", item.media_link or "https://fanvue.com")
        if "Paste Media Link" in item.quick_actions:
            media_link = st.text_input(
                "Fanvue Media Link",
                key=f"inventory_media_link_{item.asset_id}",
            )
            creator_profile_id = st.number_input(
                "Creator Profile ID",
                min_value=0,
                value=0,
                step=1,
                key=f"inventory_creator_profile_{item.asset_id}",
            )
            if st.button(
                "Verify Media Link",
                key=f"inventory_verify_media_link_{item.asset_id}",
            ):
                try:
                    from app.models.fulfillment_registration import MediaLinkSubmission
                    from app.services.fulfillment_registration_service import (
                        FulfillmentRegistrationService,
                    )

                    result = FulfillmentRegistrationService().submit_media_link(
                        MediaLinkSubmission(
                            asset_id=int(item.asset_id),
                            media_link=media_link,
                            creator_profile_id=int(creator_profile_id),
                        )
                    )
                except Exception as error:
                    st.error(f"Verification failed: {error}")
                else:
                    if result.success:
                        st.success("Media Link verified.")
                    else:
                        st.error("; ".join(result.errors) or "Verification failed.")
        if "Retry Upload" in item.quick_actions:
            fanvue_account_id = st.number_input(
                "Fanvue Account ID",
                min_value=0,
                value=0,
                step=1,
                key=f"inventory_fanvue_account_{item.asset_id}",
            )
            if st.button("Retry Upload", key=f"inventory_retry_upload_{item.asset_id}"):
                try:
                    from app.services.fulfillment_registration_service import (
                        FulfillmentRegistrationService,
                    )

                    result = FulfillmentRegistrationService().upload_customer_conversations_asset(
                        asset_id=int(item.asset_id),
                        fanvue_account_id=int(fanvue_account_id),
                    )
                except Exception as error:
                    st.error(f"Upload retry failed: {error}")
                else:
                    if result.success:
                        st.success("Upload queued.")
                    else:
                        st.error("; ".join(result.errors) or "Upload retry failed.")
        if "Change Destination" in item.quick_actions:
            if st.button(
                "Change Destination",
                key=f"inventory_change_destination_{item.asset_id}",
            ):
                st.session_state["commerce_destination_asset_id"] = int(item.asset_id)
                st.session_state["dashboard_page"] = "Asset Library"
                st.info("Destination change is handled by Commerce Destination workflow.")
        if "Temporarily Disable" in item.quick_actions:
            if st.button(
                "Temporarily Disable",
                key=f"inventory_disable_{item.asset_id}",
            ):
                try:
                    from app.services.chat_commerce_registration_service import (
                        ChatCommerceRegistrationService,
                    )

                    result = ChatCommerceRegistrationService().temporarily_disable(
                        int(item.asset_id),
                        reason="Disabled from Asset Library inventory.",
                    )
                except Exception as error:
                    st.error(f"Disable failed: {error}")
                else:
                    st.success("Asset temporarily disabled." if result.success else "Disable failed.")
        if "Re-enable" in item.quick_actions:
            if st.button("Re-enable", key=f"inventory_enable_{item.asset_id}"):
                try:
                    from app.services.chat_commerce_registration_service import (
                        ChatCommerceRegistrationService,
                    )

                    result = ChatCommerceRegistrationService().re_enable(int(item.asset_id))
                except Exception as error:
                    st.error(f"Re-enable failed: {error}")
                else:
                    st.success("Asset re-enabled." if result.success else "Re-enable failed.")
        if "Retire" in item.quick_actions:
            if st.button("Retire", key=f"inventory_retire_{item.asset_id}"):
                try:
                    from app.services.chat_commerce_registration_service import (
                        ChatCommerceRegistrationService,
                    )

                    result = ChatCommerceRegistrationService().retire_asset(
                        int(item.asset_id),
                        reason="Retired from Asset Library inventory.",
                    )
                except Exception as error:
                    st.error(f"Retire failed: {error}")
                else:
                    st.success("Asset retired." if result.success else "Retire failed.")


def _render_chat_commerce_inventory() -> None:
    st.markdown("### Chat Commerce Inventory")
    st.caption("Operational inventory for autonomous Customer Conversations.")
    with st.expander("Inventory Filters", expanded=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        status_filter = c1.selectbox(
            "Inventory Status",
            INVENTORY_FILTER_OPTIONS,
            key="chat_inventory_status_filter",
        )
        destination = c2.text_input(
            "Destination",
            key="chat_inventory_destination_filter",
        )
        product_id = c3.text_input("Product", key="chat_inventory_product_filter")
        experience_id = c4.text_input(
            "Experience",
            key="chat_inventory_experience_filter",
        )
        source_workflow = c5.text_input(
            "Source Workflow",
            key="chat_inventory_source_filter",
        )
    try:
        inventory = ChatCommerceInventoryService().build_inventory(
            filters=_inventory_filter_from_ui(
                status_filter=status_filter,
                destination=destination,
                product_id=product_id,
                experience_id=experience_id,
                source_workflow=source_workflow,
            )
        )
    except Exception as error:
        st.warning(f"Chat Commerce Inventory is unavailable: {error}")
        return

    _render_inventory_summary(inventory.summary)
    if not inventory.items:
        st.info("No Business Assets match the current inventory filters.")
        return

    for item in inventory.items:
        with st.container():
            cols = st.columns([1, 2, 2, 2, 2])
            with cols[0]:
                st.caption(f"Asset #{item.asset_id}")
                if item.thumbnail_path:
                    st.image(item.thumbnail_path, use_container_width=True)
            with cols[1]:
                st.write(item.asset_name or f"Asset {item.asset_id}")
                st.caption(f"Source: {item.source_workflow or '-'}")
                st.caption(f"Destination: {item.commerce_destination or '-'}")
                st.caption(f"Lifecycle: {item.current_lifecycle or '-'}")
            with cols[2]:
                st.caption(f"Chat Ready: {'Yes' if item.chat_ready else 'No'}")
                st.caption(f"Fulfillment Ready: {'Yes' if item.fulfillment_ready else 'No'}")
                st.caption(f"Recommendation Ready: {'Yes' if item.recommendation_ready else 'No'}")
                st.caption(f"Availability: {item.availability}")
            with cols[3]:
                st.caption(f"Fanvue Upload: {item.fanvue_upload_status or '-'}")
                st.caption(f"Fanvue Media UUID: {item.fanvue_media_uuid or '-'}")
                st.caption(f"Media Link Status: {item.media_link_status or '-'}")
                st.caption(f"Product: {', '.join(item.product_ids) or '-'}")
                st.caption(f"Experience: {', '.join(item.experience_ids) or '-'}")
            with cols[4]:
                st.caption(f"Recommendations: {item.metrics.recommendation_count}")
                st.caption(f"Offers: {item.metrics.offer_count}")
                st.caption(f"Deliveries: {item.metrics.delivery_count}")
                st.caption(f"Purchases: {item.metrics.purchase_count}")
                st.caption(f"Revenue: {_money(item.metrics.revenue_cents)}")
                st.caption(f"Conversion: {item.metrics.conversion_rate:.1%}")
                st.caption(f"Last Recommended: {item.metrics.last_recommended or '-'}")
                st.caption(f"Last Offered: {item.metrics.last_offered or '-'}")
                st.caption(f"Last Purchased: {item.metrics.last_purchased or '-'}")
            with st.expander(f"Lifecycle for Asset #{item.asset_id}"):
                for label, value in item.lifecycle_steps:
                    st.caption(f"{label}: {value or '-'}")
            _render_inventory_actions(item)
            st.divider()


def _render_library_details(
    details: AssetLibraryDetails | None,
) -> None:
    st.markdown("### Selected Asset Details")
    if not details:
        st.info("Select an asset to view details.")
        return
    item = details.item
    preview_col, meta_col = st.columns([1, 2])
    with preview_col:
        render_asset_thumbnail(item, caption=f"Asset #{item.asset_id}")
    with meta_col:
        st.subheader(item.file_name or f"Asset {item.asset_id}")
        st.caption(f"Media Type: {item.media_type}")
        st.caption(f"Imported: {_format_date(item.created_at)}")
        st.caption(f"Reference Image: {'Yes' if item.is_reference_image else 'No'}")


def _render_intelligence(
    details: AssetLibraryDetails | None,
    service: AssetLibraryService,
) -> None:
    st.markdown("### Asset Intelligence")
    if not details:
        st.info("Select an asset in the Library tab to view its intelligence.")
        return
    item = details.item
    profile = details.intelligence_profile
    st.subheader(item.file_name or f"Asset {item.asset_id}")
    if profile is None or profile.analysis_status.value != "READY":
        st.info("Asset intelligence is not ready yet.")
        return
    st.markdown("#### Description")
    st.write(profile.short_description or "-")
    st.markdown("#### Tags")
    st.write(_display_tags(profile.tags))
    st.markdown("#### Themes")
    st.write(_display_tags(profile.themes))
    st.markdown("#### Safety")
    st.write(profile.safety_classification or "-")
    st.markdown("#### Quality")
    st.write("-" if profile.quality_score is None else f"{profile.quality_score:.2f}")


def _render_operations_details(
    details: AssetLibraryDetails | None,
    service: AssetLibraryService,
) -> None:
    st.markdown("### Selected Asset Operations")
    if not details:
        st.info("Select an asset in the Library tab to view operations.")
        return
    item = details.item
    st.subheader(item.file_name or f"Asset {item.asset_id}")
    st.caption(f"Asset ID: {item.asset_id}")
    st.caption(f"Creator Profile ID: {details.creator_profile_id or '-'}")
    st.caption(f"Legacy Content ID: {item.asset_id}")
    st.caption(f"Status: {item.status or '-'}")
    st.caption(f"Active: {'Yes' if item.is_active else 'No'}")
    _render_publishing(details.publishing)
    st.markdown("#### Upload History")
    upload_history = (
        (details.media_metadata or {}).get("upload_history")
        or (details.media_metadata or {}).get("provider_upload_history")
    )
    if upload_history:
        st.json(upload_history)
    else:
        st.caption("No upload history recorded for this asset.")
    _render_storage(details.storage)
    _render_derivative(details.derivative)

    st.markdown("#### Raw Metadata and Debug Information")
    st.json(
        {
            "analysis_provenance": details.analysis_provenance,
            "classification_result": details.classification_result,
            "media_metadata": details.media_metadata,
        }
    )
    _render_actions(details, service)


def _render_no_selection(title: str, items: tuple[str, ...]) -> None:
    _, content, _ = st.columns([1, 2, 1])
    with content:
        st.markdown(f"### {title}")
        st.markdown("\n".join(f"- {item}" for item in items))


def render_asset_library(
    *,
    asset_library_service: AssetLibraryService | None = None,
) -> None:
    service = asset_library_service or AssetLibraryService()

    st.title("Asset Library")
    st.caption("Your Creator Inventory.")

    library_tab, intelligence_tab, operations_tab = st.tabs(
        ["📦 Library", "🧠 Intelligence", "⚙ Operations"]
    )

    with library_tab:
        with st.expander("Filters", expanded=False):
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
            f4, f5 = st.columns(2)
            tags = f4.text_input("Tags", key="asset_library_tags")
            themes = f5.text_input("Themes", key="asset_library_themes")
            f6, f7, f8 = st.columns(3)
            created_after = f6.text_input(
                "Created After",
                placeholder="YYYY-MM-DD",
                key="asset_library_created_after",
            )
            created_before = f7.text_input(
                "Created Before",
                placeholder="YYYY-MM-DD",
                key="asset_library_created_before",
            )
            reference_filter = f8.selectbox(
                "Reference Image",
                ("Any", "Yes", "No"),
                key="asset_library_reference_filter",
            )

        filters = build_asset_library_filter(
            search=search,
            media_type=media_type,
            classification=classification,
            eligible_only=bool(
                st.session_state.get("asset_library_eligible_only", True)
            ),
            limit=int(st.session_state.get("asset_library_limit", 100)),
            tags=tags,
            themes=themes,
            status=st.session_state.get("asset_library_status", ""),
            creator_profile_id=(
                int(st.session_state.get("asset_library_creator_profile_id", 0))
                or None
            ),
            product_id=st.session_state.get("asset_library_product_id", ""),
            experience_id=st.session_state.get("asset_library_experience_id", ""),
            publishing_status=st.session_state.get(
                "asset_library_publishing_status", ""
            ),
            has_local_vault_original=_optional_bool_filter(
                st.session_state.get("asset_library_local_vault_filter", "Any")
            ),
            has_derivative_preview=_optional_bool_filter(
                st.session_state.get("asset_library_derivative_filter", "Any")
            ),
            is_reference_image=_optional_bool_filter(reference_filter),
            legacy_content_id=(
                int(st.session_state.get("asset_library_legacy_content_id", 0))
                or None
            ),
            created_after=created_after,
            created_before=created_before,
        )
        result = service.search_assets(filters)

        st.caption(f"{result.total} asset(s) found.")
        selected_asset_id = None
        details = None
        if not result.items:
            _, empty_state, _ = st.columns([1, 2, 1])
            with empty_state:
                st.markdown("### 📦 No assets yet")
                st.write(
                    "Assets appear here after you add them from the "
                    "Generation Library."
                )
                st.caption(
                    "Once assets are registered, Creator_OS will organize, "
                    "classify, and prepare them for publishing, commerce, "
                    "and customer conversations."
                )
                if st.button(
                    "Go to Generation Library",
                    key="asset_library_go_to_generation_library",
                ):
                    st.session_state["dashboard_page"] = "Generation Library"
                    st.rerun()
        else:
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
            render_asset_grid(result.items, columns=3)
            details = service.get_asset_details(selected_asset_id)
            _render_library_details(details)

    with intelligence_tab:
        if details is None:
            _render_no_selection(
                "🧠 Select an asset from the Library tab to view:",
                (
                    "Description",
                    "Tags",
                    "Themes",
                    "Safety",
                    "Quality",
                ),
            )
        else:
            st.caption("Everything Creator_OS knows about this asset.")
            _render_intelligence(details, service)

    with operations_tab:
        if details is None:
            _render_no_selection(
                "⚙ Select an asset from the Library tab to manage:",
                (
                    "Publishing",
                    "Fanvue Upload",
                    "Commerce Status",
                    "Chat Availability",
                    "Diagnostics",
                    "Storage",
                    "Analytics",
                ),
            )
        else:
            st.caption("Everything the business does with this asset.")
            with st.expander("Advanced Inventory Filters"):
                o1, o2, o3 = st.columns(3)
                o1.checkbox(
                    "Active library only",
                    value=True,
                    key="asset_library_eligible_only",
                )
                o2.number_input(
                    "Limit",
                    min_value=1,
                    max_value=1000,
                    value=100,
                    step=25,
                    key="asset_library_limit",
                )
                o3.selectbox(
                    "Relationship Filter",
                    ("All", "Use Product ID", "Use Experience ID"),
                    key="asset_library_future_relationship_filter",
                )
                o4, o5, o6 = st.columns(3)
                o4.text_input("Status", key="asset_library_status")
                o5.number_input(
                    "Creator Profile ID",
                    min_value=0,
                    value=0,
                    step=1,
                    key="asset_library_creator_profile_id",
                )
                o6.number_input(
                    "Legacy Content ID",
                    min_value=0,
                    value=0,
                    step=1,
                    key="asset_library_legacy_content_id",
                )
                o7, o8, o9 = st.columns(3)
                o7.text_input("Product ID", key="asset_library_product_id")
                o8.text_input("Experience ID", key="asset_library_experience_id")
                o9.text_input(
                    "Publishing Status",
                    key="asset_library_publishing_status",
                )
                o10, o11 = st.columns(2)
                o10.selectbox(
                    "Local Vault",
                    ("Any", "Yes", "No"),
                    key="asset_library_local_vault_filter",
                )
                o11.selectbox(
                    "Derivative Preview",
                    ("Any", "Yes", "No"),
                    key="asset_library_derivative_filter",
                )

            _render_chat_commerce_inventory()

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
            _render_bulk_actions(
                tuple(int(asset_id) for asset_id in selected_asset_ids)
            )
            _render_operations_details(details, service)
