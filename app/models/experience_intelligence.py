"""Recommendation models for Experience Intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.models.experience import ExperienceType


@dataclass(frozen=True)
class ExperienceIntelligenceEvidence:
    reason: str
    detail: str | None = None
    weight: int = 0


@dataclass(frozen=True)
class ExperienceRecommendation:
    experience_type: ExperienceType
    asset_ids: tuple[int, ...]
    suggested_name: str
    suggested_summary: str | None = None
    suggested_cover_asset_id: int | None = None
    suggested_themes: tuple[str, ...] = ()
    suggested_keywords: tuple[str, ...] = ()
    mood: str | None = None
    setting: str | None = None
    visual_continuity: Mapping[str, Any] = field(default_factory=dict)
    story_progression: Mapping[str, Any] = field(default_factory=dict)
    technical_continuity: Mapping[str, Any] = field(default_factory=dict)
    intelligence_metadata: Mapping[str, Any] = field(default_factory=dict)
    intelligence_provenance: Mapping[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    evidence: tuple[ExperienceIntelligenceEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_collection(self) -> bool:
        return self.experience_type in {
            ExperienceType.PHOTOSHOOT,
            ExperienceType.STORY,
        }
