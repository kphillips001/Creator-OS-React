"""Creator-specific editorial learning models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


LEARNED_DIMENSIONS = (
    "environment",
    "visual_style",
    "composition",
    "pose",
    "season",
    "lighting",
    "wardrobe_category",
)


@dataclass(frozen=True)
class CreativeImageAnalysis:
    environment: str | None = None
    visual_style: str | None = None
    composition: str | None = None
    pose: str | None = None
    season: str | None = None
    lighting: str | None = None
    wardrobe_category: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {
            key: value
            for key in LEARNED_DIMENSIONS
            if (value := getattr(self, key)) is not None
        }


@dataclass(frozen=True)
class CreativeLearningSignal:
    creator_profile_id: int
    image_reference: str
    event_type: str
    source_workflow: str
    signal: str
    source_image_id: str | None = None
    source_asset_id: int | None = None
    event_key: str | None = None
    analysis: CreativeImageAnalysis = field(default_factory=CreativeImageAnalysis)
    analysis_status: str = "not_required"
    analysis_provider: str | None = None
    analysis_error: str | None = None
    operational_metadata: Mapping[str, object] = field(default_factory=dict)
