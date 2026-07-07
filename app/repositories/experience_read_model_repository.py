"""Dedicated Experience read-model repository contract.

Phase 1.6.1 prepares first-class Experience persistence without adding schema.
The default implementation is intentionally empty so current Product/ProductAsset
compatibility projections remain untouched until a real read model exists.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.models.experience import (
    Experience,
    ExperienceAssetRelationship,
    ExperienceProductRelationship,
    ExperiencePersistenceSupport,
    ProductExperienceRelationship,
)


class ExperienceReadModelRepository:
    """No-op first-class Experience read-model boundary."""

    def get_experience(
        self,
        experience_id: str,
        *,
        creator_profile_id: int | None = None,
    ) -> Experience | None:
        return None

    def get_by_product_id(
        self,
        product_id: Any,
        *,
        creator_profile_id: int | None = None,
    ) -> Experience | None:
        return None

    def list_experiences(
        self,
        *,
        creator_profile_id: int,
        search: str | None = None,
        status=None,
        product_type=None,
        tag: str | None = None,
        theme: str | None = None,
        include_archived: bool = False,
        limit: int = 500,
    ) -> list[Experience]:
        return []

    def list_asset_relationships(
        self,
        asset_id: int,
    ) -> tuple[ExperienceAssetRelationship, ...]:
        return ()

    def list_relationships_for_experience(
        self,
        experience_id: str,
    ) -> tuple[ExperienceAssetRelationship, ...]:
        return ()

    def list_product_relationships(
        self,
        product_id: Any,
    ) -> tuple[ProductExperienceRelationship, ...]:
        return ()

    def list_experience_product_relationships(
        self,
        experience_id: str,
    ) -> tuple[ExperienceProductRelationship, ...]:
        return ()

    def replace_asset_relationships(
        self,
        experience_id: str,
        asset_ids: Iterable[int],
    ) -> tuple[ExperienceAssetRelationship, ...]:
        return ()

    def support(self) -> ExperiencePersistenceSupport:
        return ExperiencePersistenceSupport(
            dedicated_read_model=False,
            relationship_read_model=False,
            source="experience_read_model_repository",
            compatibility_fallback="products.product_assets",
        )
