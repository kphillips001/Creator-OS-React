"""Stable PostgreSQL BIGINT advisory-lock key derivation."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable


def deterministic_bigint_advisory_lock_key(
    *, domain: str, components: Iterable[tuple[str, int]],
) -> int:
    """Derive one stable signed BIGINT key from a domain and numeric scope."""
    scope = "|".join(
        [str(domain), *(f"{name}={int(value)}" for name, value in components)]
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(scope).digest()[:8], "big", signed=True)
