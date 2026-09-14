"""Provider-aware, read-only Customer Snapshot contracts."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CustomerSnapshotItem:
    item_id: str
    subject_type: str
    subject_id: str
    section: str
    label: str
    description: str
    value: Any
    attributes: dict[str, Any] = field(default_factory=dict)
    source_authority: str = ""
    source_platform: str = ""
    confidence: float = 0.0
    usage_policy: str = "NORMAL_CONTEXT"
    lifecycle_status: str = "CURRENT"
    observed_at: str | None = None
    last_observed_at: str | None = None
    correctable: bool = False
    native_reference: dict[str, Any] = field(default_factory=dict)
    inferred: bool = False
    exclusion_reason: str | None = None


@dataclass(frozen=True)
class CustomerSnapshot:
    identity_summary: dict[str, Any]
    sections: dict[str, tuple[CustomerSnapshotItem, ...]]
    excluded_items: tuple[CustomerSnapshotItem, ...]
    sources: tuple[str, ...]
    mapping_state: str

