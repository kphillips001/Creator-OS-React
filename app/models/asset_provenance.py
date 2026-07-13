"""Canonical Asset provenance classifications.

Approval is a service-layer business event. Repositories may persist Assets,
but they do not infer whether an Asset is allowed to enter autonomous commerce.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


ASSET_PROVENANCE_METADATA_KEY = "asset_provenance"


class AssetProvenanceClassification(str, Enum):
    CREATOR_APPROVAL = "CREATOR_APPROVAL"
    ADMINISTRATIVE_IMPORT = "ADMINISTRATIVE_IMPORT"
    LEGACY_MIGRATION = "LEGACY_MIGRATION"
    REPAIR_BACKFILL = "REPAIR_BACKFILL"
    SYSTEM_PROJECTION = "SYSTEM_PROJECTION"


def provenance_context(
    classification: AssetProvenanceClassification | str,
    *,
    source: str,
    source_workflow: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = AssetProvenanceClassification(classification)
    return {
        "classification": resolved.value,
        "source": str(source),
        "source_workflow": source_workflow,
        "metadata": dict(metadata or {}),
    }


def administrative_import_context(
    *,
    source: str,
    source_workflow: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return provenance_context(
        AssetProvenanceClassification.ADMINISTRATIVE_IMPORT,
        source=source,
        source_workflow=source_workflow,
        metadata=metadata,
    )
