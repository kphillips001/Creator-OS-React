"""Streamlit Publishing Queue page."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID

import streamlit as st

from app.models.publishing_queue import PublishingQueueItem
from app.services.publishing_service import PublishingService

PUBLISHING_STATUS_FILTERS = [
    "All",
    "NOT_QUEUED",
    "QUEUED",
    "UPLOADING",
    "UPLOADED",
    "WAITING_FOR_MEDIA_LINK",
    "MEDIA_LINK_VERIFIED",
    "PUBLISHING_COMPLETE",
    "FAILED",
    "RETRY_REQUIRED",
    "ARCHIVED",
]


def open_product(product_id: UUID | str | None) -> None:
    if not product_id:
        return
    st.session_state["product_catalog_mode"] = "EDIT"
    st.session_state["product_catalog_selected_product_id"] = str(product_id)
    st.session_state.dashboard_page = "Product Catalog"


def open_product_review(
    *,
    product_name: str | None = None,
    status: str | None = None,
) -> None:
    if product_name:
        st.session_state["product_review_search"] = product_name
    if status:
        st.session_state["product_review_status_filter"] = status
    st.session_state.dashboard_page = "Product Review"


def filter_queue_items(
    items: Iterable[PublishingQueueItem],
    *,
    search: str = "",
    status: str = "All",
    provider: str = "All",
    retry_filter: str = "All",
    upload_date_filter: str = "All",
    ready_to_upload: bool = False,
    waiting_for_media_link: bool = False,
    failed_upload: bool = False,
    retry_required: bool = False,
    now: datetime | None = None,
) -> tuple[PublishingQueueItem, ...]:
    now = now or datetime.now(timezone.utc)
    search_text = search.strip().lower()
    filtered = []
    for item in items:
        if search_text and search_text not in _search_text(item):
            continue
        if status != "All" and item.status != status:
            continue
        if provider != "All" and item.provider != provider:
            continue
        if retry_filter == "Retryable" and not item.retry_visible:
            continue
        if retry_filter == "Retry Required" and item.retry_state != "RETRY_REQUIRED":
            continue
        if retry_filter == "Retried" and item.retry_count <= 0:
            continue
        if retry_filter == "Never Retried" and item.retry_count != 0:
            continue
        if not _matches_upload_date(item, upload_date_filter, now=now):
            continue
        if ready_to_upload and not item.ready_to_upload:
            continue
        if waiting_for_media_link and not item.waiting_for_media_link:
            continue
        if failed_upload and not item.failed_upload:
            continue
        if retry_required and item.retry_state != "RETRY_REQUIRED":
            continue
        filtered.append(item)
    return tuple(filtered)


def _search_text(item: PublishingQueueItem) -> str:
    values = (
        item.product_name,
        item.provider,
        item.status,
        item.provider_status,
        item.upload_status,
        item.media_link_status,
        item.retry_state,
        item.provider_media_id,
        item.provider_output_url,
        item.provider_metadata_summary,
        item.failure_summary,
    )
    return " ".join(str(value or "") for value in values).lower()


def _matches_upload_date(
    item: PublishingQueueItem,
    upload_date_filter: str,
    *,
    now: datetime,
) -> bool:
    if upload_date_filter == "All":
        return True
    timestamp = item.upload_timestamp
    if upload_date_filter == "No Upload Timestamp":
        return timestamp is None
    if timestamp is None:
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    if upload_date_filter == "Last 24 Hours":
        return timestamp >= now - timedelta(hours=24)
    if upload_date_filter == "Last 7 Days":
        return timestamp >= now - timedelta(days=7)
    return True


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.isoformat()


def _render_stats(service: PublishingService, items: tuple[PublishingQueueItem, ...]) -> None:
    summary = service.build_publishing_queue_summary(items)
    columns = st.columns(7)
    columns[0].metric("Jobs", str(summary.total_jobs))
    columns[1].metric("Ready", str(summary.ready_to_upload))
    columns[2].metric("Waiting Link", str(summary.waiting_for_media_link))
    columns[3].metric("Failed", str(summary.failed_uploads))
    columns[4].metric("Retryable", str(summary.retryable))
    columns[5].metric("Uploading", str(summary.uploading))
    columns[6].metric("Completed", str(summary.completed))


def _render_filters(items: tuple[PublishingQueueItem, ...]) -> dict:
    providers = sorted({item.provider for item in items})
    search = st.text_input(
        "Search",
        key="publishing_queue_search",
        placeholder="Search products, providers, status, metadata, failures",
    )
    c1, c2, c3, c4 = st.columns(4)
    toggles = st.columns(4)
    return {
        "search": search,
        "status": c1.selectbox(
            "Publishing Status",
            PUBLISHING_STATUS_FILTERS,
            key="publishing_queue_status",
        ),
        "provider": c2.selectbox(
            "Provider",
            ["All"] + providers,
            key="publishing_queue_provider",
        ),
        "retry_filter": c3.selectbox(
            "Retry",
            ["All", "Retry Required", "Retryable", "Retried", "Never Retried"],
            key="publishing_queue_retry",
        ),
        "upload_date_filter": c4.selectbox(
            "Upload Date",
            ["All", "Last 24 Hours", "Last 7 Days", "No Upload Timestamp"],
            key="publishing_queue_upload_date",
        ),
        "ready_to_upload": toggles[0].checkbox(
            "Ready To Upload",
            key="publishing_queue_ready",
        ),
        "waiting_for_media_link": toggles[1].checkbox(
            "Waiting For Media Link",
            key="publishing_queue_waiting_link",
        ),
        "failed_upload": toggles[2].checkbox(
            "Failed Upload",
            key="publishing_queue_failed",
        ),
        "retry_required": toggles[3].checkbox(
            "Retry Required",
            key="publishing_queue_retry_required",
        ),
    }


def _render_job_card(
    service: PublishingService,
    item: PublishingQueueItem,
    *,
    provider_account_id: int | None,
    creator_profile_id: int | None,
    fanvue_url: str,
) -> None:
    with st.container(border=True):
        header, action = st.columns([4, 2])
        with header:
            st.subheader(item.product_name)
            st.caption(f"Job {item.id}")
        with action:
            if st.button(
                "Open Product",
                key=f"publishing_queue_open_product_{item.id}",
                use_container_width=True,
            ):
                open_product(item.product_id)
                st.rerun()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Provider", item.provider)
        c2.metric("Publishing Status", item.status)
        c3.metric("Provider Status", item.provider_status)
        c4.metric("Upload Status", item.upload_status)

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Media Link", item.media_link_status)
        c6.metric("Retry State", item.retry_state)
        c7.metric("Retry Count", str(item.retry_count))
        c8.metric("Priority", item.publishing_priority)

        c9, c10, c11, c12 = st.columns(4)
        c9.metric("Upload Started", _format_datetime(item.job.upload_started_at))
        c10.metric("Upload Completed", _format_datetime(item.upload_completed_at))
        c11.metric("Last Attempted", _format_datetime(item.last_attempted_at))
        c12.metric("Retry Scheduled", _format_datetime(item.retry_scheduled_at))

        st.caption(f"Provider Metadata: {item.provider_metadata_summary}")
        if item.provider_media_id:
            st.caption(f"Provider Media ID: {item.provider_media_id}")
        if item.provider_output_url:
            st.caption(f"Provider Output URL: {item.provider_output_url}")
        if item.failure_summary:
            st.error(item.failure_summary)

        if item.waiting_for_media_link:
            link_col, input_col, verify_col = st.columns([1, 3, 1])
            link_col.link_button(
                "Open Fanvue",
                fanvue_url,
                use_container_width=True,
            )
            media_link = input_col.text_input(
                "Paste Media Link",
                key=f"publishing_queue_media_link_{item.id}",
                placeholder="https://...",
            )
            if verify_col.button(
                "Verify Link",
                key=f"publishing_queue_verify_media_link_{item.id}",
                disabled=not creator_profile_id,
                use_container_width=True,
            ):
                _run_media_link_action(
                    service,
                    item,
                    creator_profile_id,
                    media_link,
                )

        upload_col, retry_col, review_col, catalog_col = st.columns(4)
        if upload_col.button(
            "Upload",
            key=f"publishing_queue_upload_{item.id}",
            disabled=not provider_account_id or not item.ready_to_upload,
            use_container_width=True,
        ):
            _run_upload_action(service, item, provider_account_id)
        if retry_col.button(
            "Retry Upload",
            key=f"publishing_queue_retry_upload_{item.id}",
            disabled=not provider_account_id or not item.retry_visible,
            use_container_width=True,
        ):
            _run_upload_action(service, item, provider_account_id, retry=True)
        if review_col.button(
            "Open Product Review",
            key=f"publishing_queue_review_{item.id}",
            use_container_width=True,
        ):
            open_product_review(product_name=item.product_name)
            st.rerun()
        if catalog_col.button(
            "Open Product Catalog",
            key=f"publishing_queue_catalog_{item.id}",
            use_container_width=True,
        ):
            open_product(item.product_id)
            st.rerun()


def _run_upload_action(
    service: PublishingService,
    item: PublishingQueueItem,
    provider_account_id: int | None,
    *,
    retry: bool = False,
) -> None:
    if not provider_account_id:
        st.error("Provider account is required before uploading.")
        return
    if retry:
        result = service.retry_publishing_queue_item(
            item.id,
            provider_account_id=provider_account_id,
        )
    else:
        result = service.upload_publishing_queue_item(
            item.id,
            provider_account_id=provider_account_id,
        )
    if result.get("success"):
        st.success("Publishing upload started.")
    else:
        st.error(f"Publishing upload failed: {result.get('reason') or result}")
    st.rerun()


def _run_media_link_action(
    service: PublishingService,
    item: PublishingQueueItem,
    creator_profile_id: int | None,
    media_link: str | None,
) -> None:
    if not creator_profile_id:
        st.error("Creator profile is required before verifying a Media Link.")
        return
    result = service.complete_publishing_media_link_workflow(
        item.id,
        creator_profile_id=creator_profile_id,
        media_link=media_link,
    )
    if result.get("success"):
        st.success("Publishing complete. Product is active.")
        for warning in result.get("warnings") or ():
            st.warning(str(warning))
    else:
        errors = result.get("errors") or (result.get("reason"),)
        st.error("Media Link verification failed: " + ", ".join(map(str, errors)))
    st.rerun()


def _fanvue_url(active_account: dict | None) -> str:
    account = active_account or {}
    username = account.get("username") or account.get("account_name")
    if username:
        return f"https://www.fanvue.com/{username}"
    return "https://www.fanvue.com"


def render_publishing_queue(
    *,
    active_account: dict | None = None,
    creator_profile: dict | None = None,
    publishing_service: PublishingService | None = None,
) -> None:
    st.title("Publishing Queue")
    st.caption("Operational queue for provider execution.")

    service = publishing_service or PublishingService()
    provider_account_id = (active_account or {}).get("id")
    creator_profile_id = (creator_profile or {}).get("id")
    fanvue_url = _fanvue_url(active_account)

    try:
        items = service.list_publishing_queue_items()
    except Exception as error:
        st.error(f"Publishing Queue is unavailable: {error}")
        return

    _render_stats(service, items)
    st.divider()

    filters = _render_filters(items)
    filtered = filter_queue_items(items, **filters)
    st.caption(f"Showing {len(filtered)} of {len(items)} Publishing Jobs")

    if not filtered:
        st.info("No Publishing Jobs match the current filters.")
        return

    for item in filtered:
        _render_job_card(
            service,
            item,
            provider_account_id=provider_account_id,
            creator_profile_id=creator_profile_id,
            fanvue_url=fanvue_url,
        )
