"""Provider-neutral Product Composition read models.

Product Composition recommends how Products should be structured from Assets
and Experiences. It is advisory only and never creates or mutates Products.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ProductCompositionType(str, Enum):
    FREE_PREVIEW = "FREE_PREVIEW"
    PREMIUM_PRODUCT = "PREMIUM_PRODUCT"
    BUNDLE = "BUNDLE"
    STORY_PRODUCT = "STORY_PRODUCT"
    PHOTOSHOOT_PRODUCT = "PHOTOSHOOT_PRODUCT"
    COLLECTION = "COLLECTION"


@dataclass(frozen=True)
class ProductComposition:
    composition_type: ProductCompositionType
    included_asset_ids: tuple[int, ...] = ()
    preview_asset_ids: tuple[int, ...] = ()
    premium_asset_ids: tuple[int, ...] = ()
    cover_asset_id: int | None = None
    asset_order: tuple[int, ...] = ()
    product_order: tuple[str, ...] = ()
    related_product_ids: tuple[str, ...] = ()
    collection_membership: tuple[str, ...] = ()
    experience_id: str | None = None
    relationship_type: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductCompositionRecommendation:
    composition: ProductComposition
    label: str
    rationale: tuple[str, ...] = ()
    confidence: float = 0.0
    source: str = "ProductCompositionService"
    evidence: Mapping[str, Any] = field(default_factory=dict)
    compatibility: Mapping[str, Any] = field(default_factory=dict)

    @property
    def composition_type(self) -> ProductCompositionType:
        return self.composition.composition_type
