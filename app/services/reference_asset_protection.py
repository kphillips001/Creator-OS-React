"""Role-based protection policy for creator reference assets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def reference_metadata(value: Any) -> dict[str, Any]:
    media_metadata = value if isinstance(value, Mapping) else getattr(value, "media_metadata", None)
    if not isinstance(media_metadata, Mapping):
        return {}
    reference = media_metadata.get("reference_library")
    return dict(reference) if isinstance(reference, Mapping) else {}


def is_reference_asset(value: Any) -> bool:
    return bool(reference_metadata(value).get("is_reference"))


def is_protected_reference_asset(value: Any) -> bool:
    media_metadata = value if isinstance(value, Mapping) else getattr(value, "media_metadata", None)
    media_metadata = media_metadata if isinstance(media_metadata, Mapping) else {}
    metadata = reference_metadata(media_metadata)
    permanent = media_metadata.get("canonical_reference")
    return bool(
        (metadata.get("is_reference") and (metadata.get("protected") or metadata.get("canonical")))
        or (isinstance(permanent, Mapping) and permanent.get("permanent_identity_asset"))
    )


def is_protected_generation_metadata(value: Mapping[str, Any] | None) -> bool:
    metadata = dict(value or {})
    reference = metadata.get("reference_library")
    if not isinstance(reference, Mapping):
        return False
    return bool(reference.get("is_reference") and (reference.get("protected") or reference.get("canonical")))
