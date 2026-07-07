"""Helpers for interpreting provider publishing state.

Legacy compatibility still stores Fanvue publishing fields on content_items and
Product rows. These helpers keep provider-state interpretation in one place
without moving persistent fields or changing workflows.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


FANVUE_STATUS_UPLOADED = "Uploaded to Fanvue"
FANVUE_STATUS_FAILED = "Failed Fanvue upload"
FANVUE_STATUS_NOT_UPLOADED = "Not uploaded to Fanvue"
FANVUE_STATUS_URL_AVAILABLE = "Fanvue URL available"


def _field(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def fanvue_media_uuid(asset: Any) -> str | None:
    """Return the preferred Fanvue media UUID for a legacy Asset-like row."""

    return _field(asset, "fanvue_media_full_uuid") or _field(
        asset,
        "fanvue_media_preview_uuid",
    )


def has_fanvue_media(asset: Any) -> bool:
    return bool(fanvue_media_uuid(asset))


def fanvue_asset_status(asset: Any) -> tuple[str, str]:
    if not asset:
        return FANVUE_STATUS_NOT_UPLOADED, "No local asset is attached."

    status = str(_field(asset, "fanvue_upload_status") or "").lower()
    error = _field(asset, "fanvue_upload_error")
    media_uuid = fanvue_media_uuid(asset)

    if error or status in {"failed", "error"}:
        return FANVUE_STATUS_FAILED, str(error or status)
    if media_uuid:
        return FANVUE_STATUS_UPLOADED, media_uuid
    return FANVUE_STATUS_NOT_UPLOADED, "Local asset only"


def product_has_provider_url(product: Any) -> bool:
    if not product:
        return False
    media_link = _field(product, "media_link")
    return bool(
        media_link and str(media_link).startswith(("http://", "https://"))
    )


def fanvue_product_status(
    product: Any,
    assets: list[Any] | tuple[Any, ...],
) -> tuple[str, str]:
    if product_has_provider_url(product):
        return FANVUE_STATUS_URL_AVAILABLE, _field(product, "media_link")

    statuses = [fanvue_asset_status(asset)[0] for asset in assets]
    if any(status == FANVUE_STATUS_FAILED for status in statuses):
        return FANVUE_STATUS_FAILED, "At least one asset failed upload."
    if statuses and all(status == FANVUE_STATUS_UPLOADED for status in statuses):
        return FANVUE_STATUS_UPLOADED, "All attached assets have Fanvue media IDs."
    if any(status == FANVUE_STATUS_UPLOADED for status in statuses):
        return FANVUE_STATUS_UPLOADED, "Some attached assets have Fanvue media IDs."
    return FANVUE_STATUS_NOT_UPLOADED, "Local asset only"
