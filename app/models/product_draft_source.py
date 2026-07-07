"""Provider-neutral Product draft source contract.

This contract is the narrow Product-facing view of source material used by
draft creation. It intentionally avoids raw media paths, provider upload
fields, and repository-specific objects while legacy workflows continue to
carry those details in compatibility metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.models.product import (
    ProductDeliveryType,
    ProductType,
    normalize_product_delivery_type,
)


@dataclass(frozen=True)
class ProductDraftSource:
    source_id: str
    source_type: str
    product_type: ProductType
    suggested_title: str
    delivery_type: ProductDeliveryType | str | None = None
    suggested_description: str | None = None
    suggested_price_cents: int | None = None
    base_price_cents: int | None = None
    min_price_cents: int | None = None
    max_price_cents: int | None = None
    tags: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    experience_id: str | None = None
    asset_ids: tuple[int, ...] = ()
    classification: str | None = None
    confidence: float | None = None
    intensity: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", str(self.source_id))
        object.__setattr__(self, "source_type", str(self.source_type))
        object.__setattr__(self, "product_type", ProductType(self.product_type))
        object.__setattr__(
            self,
            "delivery_type",
            normalize_product_delivery_type(self.delivery_type),
        )
        object.__setattr__(self, "tags", _text_tuple(self.tags))
        object.__setattr__(self, "themes", _text_tuple(self.themes))
        object.__setattr__(
            self,
            "asset_ids",
            tuple(int(asset_id) for asset_id in self.asset_ids),
        )
        if self.confidence is not None:
            object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        values = (value,)
    else:
        values = tuple(value)
    return tuple(str(item) for item in values if item is not None)
