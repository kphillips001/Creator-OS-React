"""Canonical Sales Brain recommendation at the Photoshoot Experience layer."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID


@dataclass(frozen=True)
class PhotoshootExperienceRecommendation:
    photoshoot_id: str
    title: str
    theme: str | None
    description: str
    hero_asset_id: int
    supporting_asset_ids: tuple[int, ...]
    photoshoot_intelligence: Mapping[str, tuple[str, ...]]
    commercial_offering_id: UUID
    commercial_publication_id: UUID
    delivery_url: str
    recommendation_score: float
    recommendation_explanation: str
    fulfillment_offering_type: str
    fulfillment_price_minor: int
    fulfillment_currency: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "photoshoot_intelligence",
            MappingProxyType(dict(self.photoshoot_intelligence)),
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
