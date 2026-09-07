"""Canonical authority for production versus controlled-test inventory."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


CONTROLLED_SMOKE_TEST_PURPOSE_PREFIX = "controlled_smoke_test"


def publication_metadata(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    value = candidate.get("publication_metadata")
    return value if isinstance(value, Mapping) else {}


def is_test_specific_inventory(candidate: Mapping[str, Any]) -> bool:
    """Return whether inventory is explicitly barred from ordinary selection."""
    metadata = publication_metadata(candidate)
    return (
        metadata.get("test_specific") is True
        or str(metadata.get("purpose") or "").startswith(
            CONTROLLED_SMOKE_TEST_PURPOSE_PREFIX
        )
    )


def is_designated_controlled_smoke_inventory(
    candidate: Mapping[str, Any],
) -> bool:
    """Return whether the exact controlled-smoke authority is present."""
    metadata = publication_metadata(candidate)
    return (
        metadata.get("test_specific") is True
        and str(metadata.get("purpose") or "").startswith(
            CONTROLLED_SMOKE_TEST_PURPOSE_PREFIX
        )
    )
