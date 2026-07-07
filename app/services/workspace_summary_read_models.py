"""Pure read-model builders for Creator Workspace summaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.product import (
    ProductApprovalStatus,
    ProductDeliveryType,
    ProductFulfillmentStatus,
    ProductStatus,
    product_approval_status_from_metadata,
)
from app.models.workspace_dashboard import (
    WorkspaceActivitySummary,
    WorkspaceAssetsSummary,
    WorkspaceConversationSummary,
    WorkspaceExperiencesSummary,
    WorkspaceMetric,
    WorkspaceNotificationSummary,
    WorkspaceProductsSummary,
    WorkspacePublishingSummary,
    WorkspaceSummary,
)


def format_count(value: Any) -> str:
    if value is None:
        return "Unavailable"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def attribute(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def enum_value(value: Any) -> str:
    return getattr(value, "value", value)


def approval_ready(value: Any) -> bool:
    metadata = attribute(value, "metadata", {}) or {}
    if "approval" not in metadata:
        return True
    status = product_approval_status_from_metadata(metadata)
    return status in {
        ProductApprovalStatus.APPROVED,
        ProductApprovalStatus.READY_TO_PUBLISH,
    }


def metric_value_as_int(summary: WorkspaceSummary, label: str) -> int:
    value = next(
        (
            metric.value
            for metric in summary.metrics
            if metric.label == label
        ),
        "0",
    )
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0


def metric_value(summary: WorkspaceSummary, label: str) -> str:
    return next(
        (
            metric.value
            for metric in summary.metrics
            if metric.label == label
        ),
        "Unavailable",
    )


def is_recent(value: datetime | None, *, after: datetime) -> bool:
    if value is None:
        return False
    candidate = value
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    return candidate >= after


def build_asset_summary(
    assets,
    *,
    now: datetime | None = None,
) -> WorkspaceAssetsSummary:
    assets = tuple(assets)
    current_time = now or datetime.now(timezone.utc)
    recent_after = current_time - timedelta(days=7)
    recent_imports = [
        asset
        for asset in assets
        if is_recent(attribute(asset, "created_at"), after=recent_after)
    ]
    processing = [
        asset
        for asset in assets
        if str(attribute(asset, "status") or "").lower()
        in {"importing", "processing"}
    ]
    active = [
        asset
        for asset in assets
        if bool(attribute(asset, "is_active", True))
    ]
    inactive = [
        asset
        for asset in assets
        if not bool(attribute(asset, "is_active", True))
    ]
    classified = [
        asset
        for asset in assets
        if bool(attribute(asset, "classification"))
    ]
    ready_for_rotation = [
        asset
        for asset in assets
        if bool(attribute(asset, "ready_for_rotation"))
    ]
    preview_ready = [
        asset
        for asset in assets
        if bool(
            attribute(asset, "blurred_preview_path")
            or attribute(asset, "preview_path")
            or attribute(asset, "fanvue_media_preview_uuid")
            or attribute(asset, "fanvue_media_full_uuid")
        )
    ]
    attention = [
        asset
        for asset in assets
        if str(attribute(asset, "status") or "").lower()
        in {"failed", "error"}
        or bool(attribute(asset, "fanvue_upload_error"))
    ]
    return WorkspaceAssetsSummary(
        title="Assets",
        metrics=(
            WorkspaceMetric("Total Assets", format_count(len(assets))),
            WorkspaceMetric("Recently Imported", format_count(len(recent_imports))),
            WorkspaceMetric("Assets Processing", format_count(len(processing))),
            WorkspaceMetric("Asset Library", format_count(len(active)), "Active"),
            WorkspaceMetric("Inactive Assets", format_count(len(inactive))),
            WorkspaceMetric("Classified Assets", format_count(len(classified))),
            WorkspaceMetric(
                "Needs Classification",
                format_count(len(assets) - len(classified)),
            ),
            WorkspaceMetric("Ready for Rotation", format_count(len(ready_for_rotation))),
            WorkspaceMetric("Preview Ready", format_count(len(preview_ready))),
            WorkspaceMetric("Asset Alerts", format_count(len(attention))),
        ),
    )


def build_missing_experience_summary() -> WorkspaceExperiencesSummary:
    return WorkspaceExperiencesSummary(
        title="Experiences",
        metrics=(
            WorkspaceMetric("Total Experiences", "Unavailable"),
            WorkspaceMetric("Recent Experiences", "Unavailable"),
            WorkspaceMetric("Standalone", "Unavailable"),
            WorkspaceMetric("Collections", "Unavailable"),
            WorkspaceMetric("Assets Organized", "Unavailable"),
            WorkspaceMetric("Story Ready", "Unavailable"),
            WorkspaceMetric("Needs Review", "Unavailable"),
            WorkspaceMetric("Ready for Product Review", "Unavailable"),
            WorkspaceMetric("Ready for Publishing", "Unavailable"),
            WorkspaceMetric("Without Products", "Coming Soon"),
        ),
        note="Creator profile required.",
    )


def build_experience_summary(experiences) -> WorkspaceExperiencesSummary:
    experiences = tuple(experiences)
    recent = experiences[:5]
    standalone = [
        experience
        for experience in experiences
        if bool(attribute(experience, "is_standalone", False))
    ]
    collections = [
        experience
        for experience in experiences
        if bool(attribute(experience, "is_collection", False))
    ]
    organized_asset_ids = {
        asset_id
        for experience in experiences
        for asset_id in (
            attribute(experience, "ordered_asset_ids", None)
            or attribute(experience, "asset_ids", ())
            or ()
        )
    }
    missing_cover = [
        experience
        for experience in experiences
        if not attribute(experience, "cover_asset_id")
    ]
    with_intelligence = [
        experience
        for experience in experiences
        if bool(
            (
                attribute(experience, "metadata", {})
                or {}
            ).get("experience_intelligence")
            or (
                attribute(experience, "metadata", {})
                or {}
            ).get("intelligence_provenance")
        )
    ]
    story_ready = [
        experience
        for experience in experiences
        if bool((attribute(experience, "metadata", {}) or {}).get("story_progression"))
    ]
    ready_for_product_review = [
        experience
        for experience in experiences
        if bool(attribute(experience, "cover_asset_id"))
        and bool(
            (
                attribute(experience, "metadata", {})
                or {}
            ).get("experience_intelligence")
            or (
                attribute(experience, "metadata", {})
                or {}
            ).get("intelligence_provenance")
        )
    ]
    ready_for_publishing = [
        experience
        for experience in experiences
        if str(
            (attribute(experience, "metadata", {}) or {}).get(
                "publishing_readiness",
                "",
            )
        ).lower()
        == "ready"
    ]
    needs_review = [
        experience
        for experience in experiences
        if experience in missing_cover
        or experience not in ready_for_product_review
    ]
    return WorkspaceExperiencesSummary(
        title="Experiences",
        metrics=(
            WorkspaceMetric("Total Experiences", format_count(len(experiences))),
            WorkspaceMetric("Recent Experiences", format_count(len(recent))),
            WorkspaceMetric("Standalone", format_count(len(standalone))),
            WorkspaceMetric("Collections", format_count(len(collections))),
            WorkspaceMetric("Assets Organized", format_count(len(organized_asset_ids))),
            WorkspaceMetric("With Intelligence", format_count(len(with_intelligence))),
            WorkspaceMetric("Story Ready", format_count(len(story_ready))),
            WorkspaceMetric("Missing Covers", format_count(len(missing_cover))),
            WorkspaceMetric("Needs Review", format_count(len(needs_review))),
            WorkspaceMetric(
                "Ready for Product Review",
                format_count(len(ready_for_product_review)),
            ),
            WorkspaceMetric(
                "Ready for Publishing",
                format_count(len(ready_for_publishing)),
            ),
            WorkspaceMetric("Without Products", "Coming Soon"),
        ),
        note="Projected from current Product/ProductAsset compatibility data.",
    )


def build_missing_product_summary() -> WorkspaceProductsSummary:
    return WorkspaceProductsSummary(
        title="Products",
        metrics=(
            WorkspaceMetric("Total Products", "Unavailable"),
            WorkspaceMetric("Active Products", "Unavailable"),
            WorkspaceMetric("Draft Products", "Unavailable"),
            WorkspaceMetric("Archived Products", "Unavailable"),
            WorkspaceMetric("Disabled Products", "Unavailable"),
            WorkspaceMetric("Ready for Publishing", "Unavailable"),
            WorkspaceMetric("Ready To Publish", "Unavailable"),
            WorkspaceMetric("Published Products", "Unavailable"),
            WorkspaceMetric("Products Needing Review", "Unavailable"),
            WorkspaceMetric("Not Ready", "Unavailable"),
            WorkspaceMetric("Fulfillment Failed", "Unavailable"),
            WorkspaceMetric("Missing Price", "Unavailable"),
            WorkspaceMetric("Missing Experience", "Unavailable"),
            WorkspaceMetric("Missing Assets", "Unavailable"),
            WorkspaceMetric("Priced Products", "Unavailable"),
            WorkspaceMetric("Free Products", "Unavailable"),
            WorkspaceMetric("Paid Products", "Unavailable"),
        ),
        note="Creator profile required.",
    )


def build_product_summary(counts: dict, products) -> WorkspaceProductsSummary:
    products = tuple(products)
    product_records = tuple(
        attribute(item, "product", item)
        for item in products
        if attribute(item, "product", item) is not None
    )
    missing_experience = [
        item
        for item in products
        if attribute(item, "experience_presentation", None) is None
        and attribute(item, "experience", None) is None
    ]
    missing_assets = [
        item
        for item in products
        if len(attribute(item, "ordered_assets", ()) or ()) == 0
        and len(attribute(item, "asset_ids", ()) or ()) == 0
    ]
    ready = [
        product
        for product in product_records
        if attribute(product, "fulfillment_status") == ProductFulfillmentStatus.READY
        or enum_value(attribute(product, "fulfillment_status"))
        == ProductFulfillmentStatus.READY.value
    ]
    not_ready = [
        product
        for product in product_records
        if attribute(product, "fulfillment_status") == ProductFulfillmentStatus.NOT_READY
        or enum_value(attribute(product, "fulfillment_status"))
        == ProductFulfillmentStatus.NOT_READY.value
    ]
    failed = [
        product
        for product in product_records
        if attribute(product, "fulfillment_status") == ProductFulfillmentStatus.FAILED
        or enum_value(attribute(product, "fulfillment_status"))
        == ProductFulfillmentStatus.FAILED.value
    ]
    missing_price = [
        product
        for product in product_records
        if (
            attribute(product, "status") == ProductStatus.ACTIVE
            or enum_value(attribute(product, "status")) == ProductStatus.ACTIVE.value
        )
        and attribute(product, "price_cents") is None
    ]
    priced = [
        product
        for product in product_records
        if attribute(product, "price_cents") is not None
    ]
    free_products = [
        product
        for product in product_records
        if enum_value(attribute(product, "delivery_type"))
        == ProductDeliveryType.FREE.value
    ]
    paid_products = [
        product
        for product in product_records
        if enum_value(attribute(product, "delivery_type"))
        == ProductDeliveryType.PAID.value
    ]
    draft_products = [
        product
        for product in product_records
        if attribute(product, "status") == ProductStatus.DRAFT
        or enum_value(attribute(product, "status")) == ProductStatus.DRAFT.value
    ]
    published_products = [
        product
        for product in product_records
        if enum_value(attribute(product, "fulfillment_status"))
        == ProductFulfillmentStatus.READY.value
        and enum_value(attribute(product, "status")) == ProductStatus.ACTIVE.value
        and approval_ready(product)
    ]
    needing_review = []
    for product in not_ready + failed + missing_price + draft_products:
        if not any(existing is product for existing in needing_review):
            needing_review.append(product)
    return WorkspaceProductsSummary(
        title="Products",
        metrics=(
            WorkspaceMetric("Total Products", format_count(len(product_records))),
            WorkspaceMetric(
                "Active Products",
                format_count(counts.get(ProductStatus.ACTIVE.value, 0)),
            ),
            WorkspaceMetric(
                "Draft Products",
                format_count(counts.get(ProductStatus.DRAFT.value, 0)),
            ),
            WorkspaceMetric(
                "Archived Products",
                format_count(counts.get(ProductStatus.ARCHIVED.value, 0)),
            ),
            WorkspaceMetric(
                "Disabled Products",
                format_count(counts.get(ProductStatus.DISABLED.value, 0)),
            ),
            WorkspaceMetric("Ready for Publishing", format_count(len(ready))),
            WorkspaceMetric("Ready To Publish", format_count(len(ready))),
            WorkspaceMetric("Published Products", format_count(len(published_products))),
            WorkspaceMetric("Products Needing Review", format_count(len(needing_review))),
            WorkspaceMetric("Not Ready", format_count(len(not_ready))),
            WorkspaceMetric("Fulfillment Failed", format_count(len(failed))),
            WorkspaceMetric("Missing Price", format_count(len(missing_price))),
            WorkspaceMetric("Missing Experience", format_count(len(missing_experience))),
            WorkspaceMetric("Missing Assets", format_count(len(missing_assets))),
            WorkspaceMetric("Priced Products", format_count(len(priced))),
            WorkspaceMetric("Free Products", format_count(len(free_products))),
            WorkspaceMetric("Paid Products", format_count(len(paid_products))),
        ),
    )


def build_missing_publishing_summary() -> WorkspacePublishingSummary:
    return WorkspacePublishingSummary(
        title="Publishing",
        metrics=(
            WorkspaceMetric("Total Publishable Products", "Unavailable"),
            WorkspaceMetric("Ready To Publish", "Unavailable"),
            WorkspaceMetric("Needs Attention", "Unavailable"),
            WorkspaceMetric("Published / Active", "Unavailable"),
            WorkspaceMetric("Missing Media Link", "Unavailable"),
            WorkspaceMetric("Missing Price", "Unavailable"),
            WorkspaceMetric("Missing Assets", "Unavailable"),
            WorkspaceMetric("FREE Delivery Items", "Unavailable"),
            WorkspaceMetric("PAID Delivery Items", "Unavailable"),
            WorkspaceMetric("Fanvue-ready Items", "Unavailable"),
            WorkspaceMetric("Telegram-ready Items", "Unavailable"),
            WorkspaceMetric("Pending Uploads", "Unavailable"),
            WorkspaceMetric("Failed Uploads", "Unavailable"),
            WorkspaceMetric("Recently Published", "Unavailable"),
            WorkspaceMetric("Wall Pending", "Unavailable"),
            WorkspaceMetric("Wall Processing", "Unavailable"),
            WorkspaceMetric("Wall Failed", "Unavailable"),
            WorkspaceMetric("Mass PPV Pending", "Unavailable"),
            WorkspaceMetric("Mass PPV Failed", "Unavailable"),
            WorkspaceMetric("Publishing Health", "Unavailable"),
            WorkspaceMetric("Publishing Queue Count", "Unavailable"),
            WorkspaceMetric("Uploading Count", "Unavailable"),
            WorkspaceMetric("Uploaded Count", "Unavailable"),
            WorkspaceMetric("Waiting For Media Link", "Unavailable"),
            WorkspaceMetric("Failed Count", "Unavailable"),
            WorkspaceMetric("Retry Required Count", "Unavailable"),
            WorkspaceMetric("Publishing Complete", "Unavailable"),
            WorkspaceMetric("Product ACTIVE Count", "Unavailable"),
            WorkspaceMetric("Provider Summary", "Unavailable"),
        ),
        note="Provider account required.",
    )


def build_publishing_summary(
    *,
    wall_counts: dict,
    pending_mass: int,
    failed_mass: int,
    products=(),
    publishing_queue_items=(),
) -> WorkspacePublishingSummary:
    failed_total = int(wall_counts.get("failed", 0) or 0) + int(failed_mass or 0)
    pending_total = int(wall_counts.get("pending", 0) or 0) + int(pending_mass or 0)
    completed = int(wall_counts.get("completed", 0) or 0)
    wall_processing = int(wall_counts.get("processing", 0) or 0)
    wall_failed = int(wall_counts.get("failed", 0) or 0)
    product_displays = tuple(products or ())
    product_records = tuple(
        attribute(item, "product", item)
        for item in product_displays
        if attribute(item, "product", item) is not None
    )
    queue_items = tuple(publishing_queue_items or ())
    queue_count = len(queue_items)
    uploading_count = sum(
        1 for item in queue_items if attribute(item, "status") == "UPLOADING"
    )
    uploaded_count = sum(
        1 for item in queue_items if attribute(item, "upload_status") == "UPLOADED"
    )
    waiting_media_link_count = sum(
        1 for item in queue_items if bool(attribute(item, "waiting_for_media_link"))
    )
    failed_job_count = sum(
        1 for item in queue_items if bool(attribute(item, "failed_upload"))
    )
    retry_required_count = sum(
        1
        for item in queue_items
        if attribute(item, "retry_state") == "RETRY_REQUIRED"
    )
    publishing_complete_count = sum(
        1
        for item in queue_items
        if attribute(item, "status") == "PUBLISHING_COMPLETE"
    )
    providers = tuple(
        sorted(
            {
                str(attribute(item, "provider"))
                for item in queue_items
                if attribute(item, "provider")
            }
        )
    )
    publishable = [
        item
        for item in product_displays
        if enum_value(attribute(attribute(item, "product", item), "status"))
        != ProductStatus.ARCHIVED.value
    ]
    missing_media_link = [
        product
        for product in product_records
        if not attribute(product, "media_link")
    ]
    missing_price = [
        product
        for product in product_records
        if enum_value(attribute(product, "delivery_type"))
        == ProductDeliveryType.PAID.value
        and attribute(product, "price_cents") is None
    ]
    missing_assets = [
        item
        for item in product_displays
        if len(attribute(item, "ordered_assets", ()) or ()) == 0
    ]
    free_items = [
        product
        for product in product_records
        if enum_value(attribute(product, "delivery_type"))
        == ProductDeliveryType.FREE.value
    ]
    paid_items = [
        product
        for product in product_records
        if enum_value(attribute(product, "delivery_type"))
        == ProductDeliveryType.PAID.value
    ]
    fanvue_ready = [
        item
        for item in product_displays
        if "Uploaded" in str(attribute(attribute(item, "publishing", None), "status", ""))
        or "URL available" in str(
            attribute(attribute(item, "publishing", None), "status", "")
        )
    ]
    telegram_ready = [
        product
        for product in product_records
        if bool(attribute(product, "delivery_type"))
    ]
    ready_to_publish = [
        product
        for product in product_records
        if enum_value(attribute(product, "fulfillment_status"))
        == ProductFulfillmentStatus.READY.value
        and approval_ready(product)
    ]
    published_active = [
        item
        for item in product_displays
        if enum_value(attribute(attribute(item, "product", item), "status"))
        == ProductStatus.ACTIVE.value
        and item in fanvue_ready
    ]
    active_products = [
        product
        for product in product_records
        if enum_value(attribute(product, "status")) == ProductStatus.ACTIVE.value
    ]
    needs_attention = (
        len(missing_media_link)
        + len(missing_price)
        + len(missing_assets)
        + failed_total
        + failed_job_count
        + retry_required_count
        + waiting_media_link_count
    )
    return WorkspacePublishingSummary(
        title="Publishing",
        metrics=(
            WorkspaceMetric(
                "Total Publishable Products",
                format_count(len(publishable)),
            ),
            WorkspaceMetric("Ready To Publish", format_count(len(ready_to_publish))),
            WorkspaceMetric("Needs Attention", format_count(needs_attention)),
            WorkspaceMetric("Published / Active", format_count(len(published_active))),
            WorkspaceMetric("Missing Media Link", format_count(len(missing_media_link))),
            WorkspaceMetric("Missing Price", format_count(len(missing_price))),
            WorkspaceMetric("Missing Assets", format_count(len(missing_assets))),
            WorkspaceMetric("FREE Delivery Items", format_count(len(free_items))),
            WorkspaceMetric("PAID Delivery Items", format_count(len(paid_items))),
            WorkspaceMetric("Fanvue-ready Items", format_count(len(fanvue_ready))),
            WorkspaceMetric("Telegram-ready Items", format_count(len(telegram_ready))),
            WorkspaceMetric("Pending Uploads", format_count(pending_total)),
            WorkspaceMetric("Failed Uploads", format_count(failed_total)),
            WorkspaceMetric("Recently Published", format_count(completed)),
            WorkspaceMetric("Wall Pending", format_count(wall_counts.get("pending", 0))),
            WorkspaceMetric("Wall Processing", format_count(wall_processing)),
            WorkspaceMetric("Wall Failed", format_count(wall_failed)),
            WorkspaceMetric("Mass PPV Pending", format_count(pending_mass)),
            WorkspaceMetric("Mass PPV Failed", format_count(failed_mass)),
            WorkspaceMetric(
                "Publishing Health",
                "Attention"
                if failed_total
                or failed_job_count
                or retry_required_count
                or waiting_media_link_count
                else "OK",
            ),
            WorkspaceMetric(
                "Queue Attention",
                format_count(
                    failed_total
                    + wall_processing
                    + failed_job_count
                    + retry_required_count
                    + waiting_media_link_count
                ),
            ),
            WorkspaceMetric("Publishing Queue Count", format_count(queue_count)),
            WorkspaceMetric("Uploading Count", format_count(uploading_count)),
            WorkspaceMetric("Uploaded Count", format_count(uploaded_count)),
            WorkspaceMetric(
                "Waiting For Media Link",
                format_count(waiting_media_link_count),
            ),
            WorkspaceMetric("Failed Count", format_count(failed_job_count)),
            WorkspaceMetric("Retry Required Count", format_count(retry_required_count)),
            WorkspaceMetric(
                "Publishing Complete",
                format_count(publishing_complete_count),
            ),
            WorkspaceMetric("Product ACTIVE Count", format_count(len(active_products))),
            WorkspaceMetric(
                "Provider Summary",
                ", ".join(providers) if providers else "None",
            ),
        ),
        note="Includes existing publishing queue summaries.",
    )


def build_missing_conversation_summary() -> WorkspaceConversationSummary:
    return WorkspaceConversationSummary(
        title="Customer Conversations",
        metrics=(
            WorkspaceMetric("Active Conversations", "Coming Soon"),
            WorkspaceMetric("Customers Awaiting Reply", "Coming Soon"),
            WorkspaceMetric("Known Customers", "Unavailable"),
            WorkspaceMetric("Followers", "Unavailable"),
            WorkspaceMetric("Subscribers", "Unavailable"),
            WorkspaceMetric("Missing Profiles", "Unavailable"),
            WorkspaceMetric("Customer Insights", "Coming Soon"),
            WorkspaceMetric("DecisionEngine", "Configured"),
        ),
        note="Provider account required.",
    )


def build_conversation_summary(stats: dict) -> WorkspaceConversationSummary:
    return WorkspaceConversationSummary(
        title="Customer Conversations",
        metrics=(
            WorkspaceMetric("Active Conversations", "Coming Soon"),
            WorkspaceMetric("Customers Awaiting Reply", "Coming Soon"),
            WorkspaceMetric("Known Customers", format_count(stats.get("total_users"))),
            WorkspaceMetric("Followers", format_count(stats.get("followers"))),
            WorkspaceMetric("Subscribers", format_count(stats.get("subscribers"))),
            WorkspaceMetric("Missing Profiles", format_count(stats.get("missing"))),
            WorkspaceMetric("Customer Insights", "Coming Soon"),
            WorkspaceMetric("DecisionEngine", "Configured"),
        ),
        note="Conversation counts require a future conversation dashboard service.",
    )


def build_missing_activity_summary() -> WorkspaceActivitySummary:
    return WorkspaceActivitySummary(
        title="Activity",
        metrics=(
            WorkspaceMetric("Recent Imports", "See Assets"),
            WorkspaceMetric("Product Changes", "See Products"),
            WorkspaceMetric("Delayed Followups", "Unavailable"),
            WorkspaceMetric("Delayed Processing", "Unavailable"),
            WorkspaceMetric("Delayed Cancelled", "Unavailable"),
            WorkspaceMetric("Delayed Expired", "Unavailable"),
            WorkspaceMetric("Activity Feed", "Coming Soon"),
        ),
        note="Provider account required.",
    )


def build_activity_summary(delayed: dict) -> WorkspaceActivitySummary:
    return WorkspaceActivitySummary(
        title="Activity",
        metrics=(
            WorkspaceMetric("Recent Imports", "See Assets"),
            WorkspaceMetric("Product Changes", "See Products"),
            WorkspaceMetric("Delayed Pending", format_count(delayed["pending"])),
            WorkspaceMetric("Delayed Processing", format_count(delayed["processing"])),
            WorkspaceMetric("Delayed Completed", format_count(delayed["completed"])),
            WorkspaceMetric("Delayed Failed", format_count(delayed["failed"])),
            WorkspaceMetric("Delayed Cancelled", format_count(delayed["cancelled"])),
            WorkspaceMetric("Delayed Expired", format_count(delayed["expired"])),
            WorkspaceMetric("Activity Feed", "Coming Soon"),
        ),
    )


def build_notification_summary(
    *,
    creator_profile: dict | None,
    active_account: dict | None,
    publishing: WorkspaceSummary,
    activity: WorkspaceSummary,
) -> WorkspaceNotificationSummary:
    profile_missing = not bool(creator_profile)
    oauth_connected = bool(
        (active_account or {}).get("oauth_access_token")
        or (active_account or {}).get("oauth_refresh_token")
        or (active_account or {}).get("fanvue_user_uuid")
    )
    publishing_attention = any(
        metric.label == "Publishing Health" and metric.value == "Attention"
        for metric in publishing.metrics
    )
    delayed_failed = metric_value_as_int(activity, "Delayed Failed")
    queue_failures = metric_value_as_int(publishing, "Failed Uploads")
    attention_items = sum(
        (
            1 if profile_missing else 0,
            0 if oauth_connected else 1,
            1 if publishing_attention else 0,
            1 if delayed_failed else 0,
        )
    )
    return WorkspaceNotificationSummary(
        title="Notifications",
        metrics=(
            WorkspaceMetric("Profile", "Missing" if profile_missing else "OK"),
            WorkspaceMetric("Attention Items", format_count(attention_items)),
            WorkspaceMetric("Provider OAuth", "Connected" if oauth_connected else "Check"),
            WorkspaceMetric("Publishing", "Attention" if publishing_attention else "OK"),
            WorkspaceMetric("Queue Failures", format_count(queue_failures)),
            WorkspaceMetric("Processing Errors", format_count(delayed_failed)),
            WorkspaceMetric("Notification Inbox", "Coming Soon"),
        ),
        note="Notification rollup is read-only.",
    )
