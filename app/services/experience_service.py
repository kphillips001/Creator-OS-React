"""Provider-neutral Experience domain service.

ExperienceService is the formal Experience boundary. Product/ProductAsset
composition remains available only as a compatibility path behind this service.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from app.models.experience import (
    Experience,
    ExperienceAssetRelationship,
    ExperienceProductRelationship,
    ExperiencePersistenceSupport,
    ExperienceType,
    ProductExperienceRelationship,
)
from app.repositories.experience_repository import ExperienceRepository


class ExperienceService:
    """Domain facade for Experience read models and composition."""

    def __init__(
        self,
        experience_repository: ExperienceRepository | None = None,
        content_opportunity_service: Any | None = None,
    ):
        self.experience_repository = (
            experience_repository or ExperienceRepository()
        )
        self.content_opportunity_service = content_opportunity_service

    def persistence_support(self) -> ExperiencePersistenceSupport:
        support = getattr(self.experience_repository, "support", None)
        if callable(support):
            return support()
        return ExperiencePersistenceSupport(
            dedicated_read_model=False,
            relationship_read_model=False,
            source="experience_service",
            compatibility_fallback="products.product_assets",
        )

    def get_experience(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int | None = None,
    ) -> Experience | None:
        return self.experience_repository.get_experience(
            product_id,
            creator_profile_id=creator_profile_id,
        )

    def get_by_product_id(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int | None = None,
    ) -> Experience | None:
        return self.get_experience(
            product_id,
            creator_profile_id=creator_profile_id,
        )

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
        return self.experience_repository.list_experiences(
            creator_profile_id=creator_profile_id,
            search=search,
            status=status,
            product_type=product_type,
            tag=tag,
            theme=theme,
            include_archived=include_archived,
            limit=limit,
        )

    def build_product_experience(
        self,
        product: Any,
        product_assets=None,
    ) -> Experience:
        return self.experience_repository.build_experience(
            product,
            product_assets,
        )

    def record_experience_available(self, experience: Any) -> tuple[Any, ...]:
        service = self.content_opportunity_service
        notify = getattr(service, "record_new_experience_available", None)
        if not callable(notify):
            return ()
        return tuple(notify(experience))

    def list_asset_relationships(
        self,
        asset_id: int,
    ) -> tuple[ExperienceAssetRelationship, ...]:
        list_relationships = getattr(
            self.experience_repository,
            "list_asset_relationships",
            None,
        )
        if not callable(list_relationships):
            return ()
        return tuple(list_relationships(int(asset_id)))

    def list_asset_experience_ids(self, asset_id: int) -> tuple[str, ...]:
        return tuple(
            relationship.experience_id
            for relationship in self.list_asset_relationships(asset_id)
        )

    def list_product_relationships(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int | None = None,
    ) -> tuple[ProductExperienceRelationship, ...]:
        list_relationships = getattr(
            self.experience_repository,
            "list_product_relationships",
            None,
        )
        if not callable(list_relationships):
            return ()
        return tuple(
            list_relationships(
                product_id,
                creator_profile_id=creator_profile_id,
            )
        )

    def list_experience_product_relationships(
        self,
        experience_id: str,
    ) -> tuple[ExperienceProductRelationship, ...]:
        list_relationships = getattr(
            self.experience_repository,
            "list_experience_product_relationships",
            None,
        )
        if not callable(list_relationships):
            return ()
        return tuple(list_relationships(str(experience_id)))

    def list_product_experience_ids(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int | None = None,
    ) -> tuple[str, ...]:
        return tuple(
            relationship.experience_id
            for relationship in self.list_product_relationships(
                product_id,
                creator_profile_id=creator_profile_id,
            )
        )

    def get_product_experience(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int | None = None,
    ) -> Experience | None:
        return self.get_experience(
            product_id,
            creator_profile_id=creator_profile_id,
        )

    def list_product_experience_assets(
        self,
        product_id: UUID,
        *,
        connection=None,
    ) -> list[Any]:
        return self.experience_repository.list_product_experience_assets(
            product_id,
            connection=connection,
        )

    def count_product_experience_assets(self, product_id: UUID) -> int:
        return self.experience_repository.count_product_experience_assets(
            product_id
        )

    def replace_product_experience_assets(
        self,
        product_id: UUID,
        asset_ids: Iterable[int],
        *,
        connection=None,
    ) -> list[Any]:
        return self.experience_repository.replace_product_experience_assets(
            product_id,
            asset_ids,
            connection=connection,
        )

    def attach_primary_product_experience_asset(
        self,
        product_id: UUID,
        asset_id: int,
    ) -> tuple[Any, bool]:
        return self.experience_repository.attach_primary_product_experience_asset(
            product_id,
            asset_id,
        )

    def delete_product_experience_assets(
        self,
        product_id: UUID,
        *,
        connection=None,
    ) -> int:
        return self.experience_repository.delete_product_experience_assets(
            product_id,
            connection=connection,
        )

    def build_standalone_experience(
        self,
        asset: Any,
        *,
        title: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        experience_id: str | None = None,
    ) -> Experience:
        return self.experience_repository.build_standalone_experience(
            asset,
            title=title,
            description=description,
            metadata=metadata,
            experience_id=experience_id,
        )

    def build_photoshoot_experience(
        self,
        assets,
        *,
        title: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        cover_asset_id: int | None = None,
        asset_order=None,
        experience_id: str | None = None,
    ) -> Experience:
        return self.experience_repository.build_photoshoot_experience(
            assets,
            title=title,
            description=description,
            metadata=metadata,
            cover_asset_id=cover_asset_id,
            asset_order=asset_order,
            experience_id=experience_id,
        )

    def build_story_experience(
        self,
        assets,
        *,
        title: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        cover_asset_id: int | None = None,
        asset_order=None,
        experience_id: str | None = None,
    ) -> Experience:
        return self.experience_repository.build_story_experience(
            assets,
            title=title,
            description=description,
            metadata=metadata,
            cover_asset_id=cover_asset_id,
            asset_order=asset_order,
            experience_id=experience_id,
        )

    def get_experience_type(
        self,
        experience: Experience | None,
    ) -> ExperienceType | None:
        if not experience:
            return None
        return experience.experience_type

    def get_cover_asset_id(self, experience: Experience | None) -> int | None:
        if not experience:
            return None
        return experience.cover_asset_id

    def get_ordered_asset_ids(
        self,
        experience: Experience | None,
    ) -> tuple[int, ...]:
        if not experience:
            return ()
        return experience.ordered_asset_ids

    def get_asset_ids(
        self,
        experience: Experience | None,
    ) -> tuple[int, ...]:
        if not experience:
            return ()
        return experience.asset_ids

    def get_metadata(
        self,
        experience: Experience | None,
    ) -> Mapping[str, Any]:
        if not experience:
            return {}
        return experience.metadata

    def is_standalone(self, experience: Experience | None) -> bool:
        return self.get_experience_type(experience) == ExperienceType.STANDALONE

    def is_photoshoot(self, experience: Experience | None) -> bool:
        return self.get_experience_type(experience) == ExperienceType.PHOTOSHOOT

    def is_story(self, experience: Experience | None) -> bool:
        return self.get_experience_type(experience) == ExperienceType.STORY

    def is_collection(self, experience: Experience | None) -> bool:
        if not experience:
            return False
        return experience.is_collection

    def get_product_experience_type(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int | None = None,
    ) -> ExperienceType | None:
        return self.get_experience_type(
            self.get_experience(
                product_id,
                creator_profile_id=creator_profile_id,
            )
        )

    def get_product_cover_asset_id(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int | None = None,
    ) -> int | None:
        return self.get_cover_asset_id(
            self.get_experience(
                product_id,
                creator_profile_id=creator_profile_id,
            )
        )

    def get_product_ordered_asset_ids(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int | None = None,
    ) -> tuple[int, ...]:
        return self.get_ordered_asset_ids(
            self.get_experience(
                product_id,
                creator_profile_id=creator_profile_id,
            )
        )

    def order_assets_for_experience(
        self,
        experience: Experience | None,
        assets: Iterable[Any],
    ) -> tuple[Any, ...]:
        ordered_asset_ids = self.get_ordered_asset_ids(experience)
        asset_records = tuple(assets)
        if not ordered_asset_ids:
            return asset_records

        assets_by_id = {asset.id: asset for asset in asset_records}
        return tuple(
            assets_by_id[asset_id]
            for asset_id in ordered_asset_ids
            if asset_id in assets_by_id
        )

    def cover_asset_for_experience(
        self,
        experience: Experience | None,
        assets: Iterable[Any],
    ) -> Any | None:
        asset_records = tuple(assets)
        cover_asset_id = self.get_cover_asset_id(experience)
        for asset in asset_records:
            if asset.id == cover_asset_id:
                return asset
        ordered_assets = self.order_assets_for_experience(
            experience,
            asset_records,
        )
        return ordered_assets[0] if ordered_assets else None

    def preview_asset_for_experience(
        self,
        experience: Experience | None,
        assets: Iterable[Any],
    ) -> Any | None:
        return self.cover_asset_for_experience(experience, assets)

    def get_ordered_assets_for_product(
        self,
        product_id: UUID,
        asset_repository,
        *,
        creator_profile_id: int | None = None,
    ) -> tuple[Any, ...]:
        experience = self.get_product_experience(
            product_id,
            creator_profile_id=creator_profile_id,
        )
        asset_ids = self.get_ordered_asset_ids(experience)
        if not asset_ids:
            return ()
        assets = asset_repository.list_by_ids(asset_ids)
        return self.order_assets_for_experience(experience, assets)

    def get_cover_asset_for_product(
        self,
        product_id: UUID,
        asset_repository,
        *,
        creator_profile_id: int | None = None,
    ) -> Any | None:
        experience = self.get_product_experience(
            product_id,
            creator_profile_id=creator_profile_id,
        )
        asset_ids = self.get_ordered_asset_ids(experience)
        assets = asset_repository.list_by_ids(asset_ids) if asset_ids else ()
        return self.cover_asset_for_experience(
            experience,
            assets,
        )

    def get_preview_asset_for_product(
        self,
        product_id: UUID,
        asset_repository,
        *,
        creator_profile_id: int | None = None,
    ) -> Any | None:
        experience = self.get_product_experience(
            product_id,
            creator_profile_id=creator_profile_id,
        )
        asset_ids = self.get_ordered_asset_ids(experience)
        assets = asset_repository.list_by_ids(asset_ids) if asset_ids else ()
        return self.preview_asset_for_experience(
            experience,
            assets,
        )
