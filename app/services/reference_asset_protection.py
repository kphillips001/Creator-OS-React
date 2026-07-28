"""Role-based protection policy for creator reference assets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

COMMERCIAL_REFERENCE_ERROR = "Canonical/reference assets are identity-only and cannot enter commerce."
_IDENTITY_CLASSIFICATIONS = frozenset({"REFERENCE", "IDENTITY"})
_IDENTITY_TAGS = frozenset({
    "canonical-reference", "identity", "identity-reference",
    "identity-lock", "reference-lock",
})


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


def commercial_asset_ineligibility_reason(value: Any) -> str | None:
    """Return the single authoritative reason an Asset cannot enter commerce."""
    if is_reference_asset(value) or is_protected_reference_asset(value):
        return COMMERCIAL_REFERENCE_ERROR
    classification = (
        value.get("classification") if isinstance(value, Mapping)
        else getattr(value, "classification", None)
    )
    classification = getattr(classification, "value", classification)
    if str(classification or "").upper() in _IDENTITY_CLASSIFICATIONS:
        return COMMERCIAL_REFERENCE_ERROR
    tags = (
        value.get("suggested_tags") if isinstance(value, Mapping)
        else getattr(value, "suggested_tags", ())
    ) or ()
    if {str(tag).lower() for tag in tags}.intersection(_IDENTITY_TAGS):
        return COMMERCIAL_REFERENCE_ERROR
    return None


def is_commercially_eligible_asset(value: Any) -> bool:
    return commercial_asset_ineligibility_reason(value) is None


def require_commercially_eligible_asset(value: Any, *, asset_id: int | None = None) -> None:
    reason = commercial_asset_ineligibility_reason(value)
    if reason:
        suffix = f" Asset {asset_id}." if asset_id is not None else ""
        raise ValueError(f"{reason}{suffix}")


def commercial_asset_eligibility_sql(alias: str) -> str:
    """SQL equivalent of the durable identity/reference markers above."""
    if not alias.replace("_", "").isalnum():
        raise ValueError("A safe SQL table alias is required.")
    return f"""(
        COALESCE({alias}.media_metadata->'reference_library'->>'is_reference', 'false') <> 'true'
        AND COALESCE({alias}.media_metadata->'reference_library'->>'protected', 'false') <> 'true'
        AND COALESCE({alias}.media_metadata->'reference_library'->>'canonical', 'false') <> 'true'
        AND COALESCE({alias}.media_metadata->'canonical_reference'->>'permanent_identity_asset', 'false') <> 'true'
        AND UPPER(COALESCE({alias}.classification, '')) NOT IN ('REFERENCE', 'IDENTITY')
    )"""
