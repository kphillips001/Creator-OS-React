"""Immutable creator identity provenance for generation operations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping


class GenerationReferenceRole(str, Enum):
    CANONICAL_IDENTITY = "CANONICAL_IDENTITY"
    CREATIVE_INSPIRATION = "CREATIVE_INSPIRATION"
    ORIGINAL_PHOTOSHOOT_SEED = "ORIGINAL_PHOTOSHOOT_SEED"
    PHOTOSHOOT_CONTINUITY = "PHOTOSHOOT_CONTINUITY"
    EDIT_SOURCE = "EDIT_SOURCE"
    STYLE_REFERENCE = "STYLE_REFERENCE"
    VIDEO_SOURCE = "VIDEO_SOURCE"


@dataclass(frozen=True)
class CanonicalCreatorIdentityContract:
    creator_profile_id: int
    creator_identity_key: str
    canonical_asset_id: int
    canonical_content_sha256: str
    canonical_local_path: str
    canonical_provider_reference: str
    identity_version: str
    resolved_at: str
    reference_role: str
    identity_prompt_policy_id: str
    identity_prompt_policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None):
        if not isinstance(value, Mapping):
            return None
        try:
            return cls(**{name: value[name] for name in cls.__dataclass_fields__})
        except (KeyError, TypeError, ValueError):
            return None


def canonical_identity_version(
    *, creator_profile_id: int, canonical_asset_id: int,
    canonical_content_sha256: str, identity_prompt_policy_id: str,
    identity_prompt_policy_version: str,
) -> str:
    """Return a deterministic fingerprint that excludes hosted-reference URLs."""
    stable = {
        "canonical_asset_id": int(canonical_asset_id),
        "canonical_content_sha256": str(canonical_content_sha256).upper(),
        "creator_profile_id": int(creator_profile_id),
        "identity_prompt_policy_id": str(identity_prompt_policy_id),
        "identity_prompt_policy_version": str(identity_prompt_policy_version),
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"canonical_identity_v1:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"
