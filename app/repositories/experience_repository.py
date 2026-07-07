"""Experience repository boundary with Product compatibility fallback.

Phase 1.6.1 keeps Product/ProductAsset projection as compatibility-only while
preparing a dedicated Experience read-model repository. Dedicated read-model
data wins when injected; existing Product/ProductAsset storage remains the
fallback so current workflows keep their behavior.
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
from app.models.product import ProductType
from app.repositories.experience_read_model_repository import (
    ExperienceReadModelRepository,
)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


class ExperienceRepository:
    """Experience repository with compatibility projection fallback.

    ProductAsset remains a compatibility persistence bridge only. Composition
    reads and writes are exposed here so callers use the Experience boundary
    without knowing whether data came from a dedicated read model or the legacy
    Product/ProductAsset projection.
    """

    def __init__(
        self,
        *,
        product_repository=None,
        product_asset_repository=None,
        experience_read_model_repository=None,
    ):
        if product_repository is None:
            from app.repositories.product_repository import ProductRepository

            product_repository = ProductRepository()
        if product_asset_repository is None:
            from app.repositories.product_asset_repository import (
                ProductAssetRepository,
            )

            product_asset_repository = ProductAssetRepository()

        self.products = product_repository
        self.product_assets = product_asset_repository
        self.experience_read_model = (
            experience_read_model_repository or ExperienceReadModelRepository()
        )

    def support(self) -> ExperiencePersistenceSupport:
        read_model_support = self.experience_read_model.support()
        return ExperiencePersistenceSupport(
            dedicated_read_model=read_model_support.dedicated_read_model,
            relationship_read_model=read_model_support.relationship_read_model,
            source="experience_repository",
            compatibility_fallback="products.product_assets",
        )

    def get_experience(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int | None = None,
    ) -> Experience | None:
        dedicated = self.experience_read_model.get_by_product_id(
            product_id,
            creator_profile_id=creator_profile_id,
        )
        if dedicated is not None:
            return dedicated
        product = self.products.get_by_id(
            product_id,
            creator_profile_id=creator_profile_id,
        )
        if not product:
            return None
        product_assets = self.product_assets.list_for_product(product_id)
        return self.build_experience(product, product_assets)

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
        dedicated = self.experience_read_model.list_experiences(
            creator_profile_id=creator_profile_id,
            search=search,
            status=status,
            product_type=product_type,
            tag=tag,
            theme=theme,
            include_archived=include_archived,
            limit=limit,
        )
        if dedicated:
            return dedicated[:limit]

        products = self.products.list_products(
            creator_profile_id=creator_profile_id,
            search=search,
            status=status,
            product_type=product_type,
            tag=tag,
            theme=theme,
            include_archived=include_archived,
            limit=limit,
        )
        experiences = []
        for product in products:
            product_assets = self.product_assets.list_for_product(
                _get(product, "id")
            )
            experiences.append(self.build_experience(product, product_assets))
        return experiences

    def list_asset_relationships(
        self,
        asset_id: int,
    ) -> tuple[ExperienceAssetRelationship, ...]:
        dedicated = self.experience_read_model.list_asset_relationships(
            int(asset_id)
        )
        if dedicated:
            return dedicated
        return self._compatibility_asset_relationships(asset_id)

    def list_product_relationships(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int | None = None,
    ) -> tuple[ProductExperienceRelationship, ...]:
        list_relationships = getattr(
            self.experience_read_model,
            "list_product_relationships",
            None,
        )
        dedicated = (
            list_relationships(product_id)
            if callable(list_relationships)
            else ()
        )
        if dedicated:
            return dedicated

        experience = self.get_experience(
            product_id,
            creator_profile_id=creator_profile_id,
        )
        if experience is None:
            return ()
        return (
            self._product_relationship_from_experience(
                product_id,
                experience,
            ),
        )

    def list_experience_product_relationships(
        self,
        experience_id: str,
    ) -> tuple[ExperienceProductRelationship, ...]:
        list_relationships = getattr(
            self.experience_read_model,
            "list_experience_product_relationships",
            None,
        )
        dedicated = (
            list_relationships(experience_id)
            if callable(list_relationships)
            else ()
        )
        if dedicated:
            return dedicated

        product_id = self._product_id_from_compatibility_experience_id(
            experience_id
        )
        if product_id is None:
            return ()
        return (
            ExperienceProductRelationship(
                experience_id=experience_id,
                product_id=product_id,
                role="primary",
                source="products.product_assets",
                compatibility=True,
                compatibility_experience_id=True,
                metadata={
                    "compatibility_source": "products.product_assets",
                    "source_product_id": product_id,
                },
            ),
        )

    def build_experience(
        self,
        product: Any,
        product_assets: Iterable[Any] | None = None,
    ) -> Experience:
        metadata = dict(_get(product, "metadata") or {})
        ordered_links = self._ordered_product_assets(product_assets or ())
        asset_order = tuple(int(_get(link, "asset_id")) for link in ordered_links)
        asset_ids = asset_order or self._metadata_asset_ids(metadata)

        if not asset_ids:
            legacy_asset_id = _get(product, "legacy_content_item_id")
            if legacy_asset_id is not None:
                asset_ids = (int(legacy_asset_id),)

        if not asset_order:
            asset_order = self._metadata_asset_order(metadata) or asset_ids

        compatibility_metadata = {
            **metadata,
            "compatibility_source": "products.product_assets",
            "compatibility_experience_id": True,
            "source_product_id": str(_get(product, "id")),
            "source_product_type": self._product_type_value(product),
            "legacy_content_item_id": _get(product, "legacy_content_item_id"),
        }

        return Experience(
            experience_id=f"product:{_get(product, 'id')}",
            experience_type=self._experience_type_for_product(
                product,
                metadata=metadata,
                asset_count=len(asset_ids),
            ),
            title=_get(product, "display_name") or _get(product, "internal_name"),
            description=_get(product, "description"),
            cover_asset_id=self._cover_asset_id(metadata),
            asset_ids=asset_ids,
            asset_order=asset_order,
            metadata=compatibility_metadata,
            created_at=_get(product, "created_at"),
            updated_at=_get(product, "updated_at"),
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
        asset_id = int(_get(asset, "id"))
        compatibility_metadata = {
            **dict(metadata or {}),
            "compatibility_source": "assets",
            "source_asset_id": asset_id,
        }
        return Experience(
            experience_id=experience_id or f"asset:{asset_id}",
            experience_type=ExperienceType.STANDALONE,
            title=title or self._asset_title(asset),
            description=description or _get(asset, "summary"),
            cover_asset_id=asset_id,
            asset_ids=(asset_id,),
            asset_order=(asset_id,),
            metadata=compatibility_metadata,
            created_at=_get(asset, "created_at"),
            updated_at=_get(asset, "updated_at"),
        )

    def build_photoshoot_experience(
        self,
        assets: Iterable[Any],
        *,
        title: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        cover_asset_id: int | None = None,
        asset_order: Iterable[int] | None = None,
        experience_id: str | None = None,
    ) -> Experience:
        return self._build_asset_collection_experience(
            assets,
            experience_type=ExperienceType.PHOTOSHOOT,
            title=title,
            description=description,
            metadata=metadata,
            cover_asset_id=cover_asset_id,
            asset_order=asset_order,
            experience_id=experience_id,
        )

    def build_story_experience(
        self,
        assets: Iterable[Any],
        *,
        title: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        cover_asset_id: int | None = None,
        asset_order: Iterable[int] | None = None,
        experience_id: str | None = None,
    ) -> Experience:
        return self._build_asset_collection_experience(
            assets,
            experience_type=ExperienceType.STORY,
            title=title,
            description=description,
            metadata=metadata,
            cover_asset_id=cover_asset_id,
            asset_order=asset_order,
            experience_id=experience_id,
        )

    def list_product_experience_assets(
        self,
        product_id: UUID,
        *,
        connection=None,
    ) -> list[Any]:
        return self.product_assets.list_for_product(
            product_id,
            connection=connection,
        )

    def count_product_experience_assets(self, product_id: UUID) -> int:
        return self.product_assets.count_for_product(product_id)

    def replace_product_experience_assets(
        self,
        product_id: UUID,
        asset_ids: Iterable[int],
        *,
        connection=None,
    ) -> list[Any]:
        # Compatibility write path: Product Drafting and Product Catalog still
        # persist composition through ProductAsset until Experience persistence
        # exists. Callers must reach this only through ExperienceService.
        return self.product_assets.replace_product_assets(
            product_id,
            asset_ids,
            connection=connection,
        )

    def attach_primary_product_experience_asset(
        self,
        product_id: UUID,
        asset_id: int,
    ) -> tuple[Any, bool]:
        # Compatibility write path; see replace_product_experience_assets.
        return self.product_assets.attach_primary(product_id, asset_id)

    def delete_product_experience_assets(
        self,
        product_id: UUID,
        *,
        connection=None,
    ) -> int:
        # Compatibility write path; see replace_product_experience_assets.
        return self.product_assets.delete_for_product(
            product_id,
            connection=connection,
        )

    def _compatibility_asset_relationships(
        self,
        asset_id: int,
    ) -> tuple[ExperienceAssetRelationship, ...]:
        product_ids = []
        list_for_asset = getattr(self.product_assets, "list_product_ids_for_asset", None)
        if callable(list_for_asset):
            product_ids.extend(list_for_asset(int(asset_id)))
        legacy_product = None
        get_legacy_product = getattr(
            self.products,
            "get_by_legacy_content_item_id",
            None,
        )
        if callable(get_legacy_product):
            legacy_product = get_legacy_product(int(asset_id))
            if legacy_product is not None:
                legacy_product_id = _get(legacy_product, "id")
                if legacy_product_id is not None:
                    product_ids.append(legacy_product_id)

        relationships = []
        seen = set()
        for product_id in product_ids:
            key = str(product_id)
            if key in seen:
                continue
            seen.add(key)
            list_for_product = getattr(self.product_assets, "list_for_product", None)
            product_assets = (
                list_for_product(product_id)
                if callable(list_for_product)
                else ()
            )
            ordered_links = self._ordered_product_assets(product_assets)
            position = next(
                (
                    index
                    for index, link in enumerate(ordered_links)
                    if int(_get(link, "asset_id")) == int(asset_id)
                ),
                0,
            )
            relationships.append(
                ExperienceAssetRelationship(
                    experience_id=f"product:{product_id}",
                    asset_id=int(asset_id),
                    position=position,
                    role="member",
                    source="products.product_assets",
                    compatibility=True,
                    metadata={
                        "compatibility_source": "products.product_assets",
                        "compatibility_experience_id": True,
                        "source_product_id": key,
                    },
                )
            )
        return tuple(relationships)

    @staticmethod
    def _product_relationship_from_experience(
        product_id: UUID,
        experience: Experience,
    ) -> ProductExperienceRelationship:
        metadata = dict(experience.metadata or {})
        compatibility = bool(metadata.get("compatibility_source"))
        experience_id = str(experience.experience_id)
        compatibility_experience_id = bool(
            metadata.get("compatibility_experience_id")
            or experience_id.startswith("product:")
        )
        return ProductExperienceRelationship(
            product_id=product_id,
            experience_id=experience_id,
            role="primary",
            source=metadata.get("compatibility_source") or "experience",
            compatibility=compatibility,
            compatibility_experience_id=compatibility_experience_id,
            metadata={
                "experience_type": experience.experience_type.value,
                "compatibility_source": metadata.get("compatibility_source"),
                "source_product_id": str(product_id),
            },
        )

    @staticmethod
    def _product_id_from_compatibility_experience_id(
        experience_id: str,
    ) -> str | None:
        text = str(experience_id or "")
        prefix = "product:"
        if not text.startswith(prefix):
            return None
        product_id = text[len(prefix):]
        return product_id or None

    def _build_asset_collection_experience(
        self,
        assets: Iterable[Any],
        *,
        experience_type: ExperienceType,
        title: str | None,
        description: str | None,
        metadata: Mapping[str, Any] | None,
        cover_asset_id: int | None,
        asset_order: Iterable[int] | None,
        experience_id: str | None,
    ) -> Experience:
        asset_records = tuple(assets)
        asset_ids = tuple(int(_get(asset, "id")) for asset in asset_records)
        ordered_ids = (
            self._coerce_asset_ids(asset_order)
            if asset_order is not None
            else asset_ids
        )
        compatibility_metadata = {
            **dict(metadata or {}),
            "compatibility_source": "assets",
            "source_asset_ids": list(asset_ids),
            "asset_count": len(asset_ids),
        }
        first_asset = asset_records[0] if asset_records else None
        return Experience(
            experience_id=experience_id or self._asset_collection_id(
                experience_type,
                asset_ids,
            ),
            experience_type=experience_type,
            title=title or self._collection_title(experience_type, first_asset),
            description=description,
            cover_asset_id=cover_asset_id,
            asset_ids=asset_ids,
            asset_order=ordered_ids,
            metadata=compatibility_metadata,
            created_at=_get(first_asset, "created_at") if first_asset else None,
            updated_at=_get(first_asset, "updated_at") if first_asset else None,
        )

    @staticmethod
    def _ordered_product_assets(product_assets: Iterable[Any]) -> list[Any]:
        return sorted(
            list(product_assets),
            key=lambda item: (
                _get(item, "position", 0),
                _get(item, "asset_id", 0),
            ),
        )

    @staticmethod
    def _coerce_asset_ids(value: Any) -> tuple[int, ...]:
        return Experience._coerce_asset_ids(value)

    @staticmethod
    def _asset_title(asset: Any) -> str:
        return (
            _get(asset, "file_name")
            or _get(asset, "file_path")
            or f"Asset {_get(asset, 'id')}"
        )

    @classmethod
    def _collection_title(
        cls,
        experience_type: ExperienceType,
        first_asset: Any | None,
    ) -> str:
        if first_asset is None:
            return experience_type.value.title()
        return f"{experience_type.value.title()} - {cls._asset_title(first_asset)}"

    @staticmethod
    def _asset_collection_id(
        experience_type: ExperienceType,
        asset_ids: tuple[int, ...],
    ) -> str:
        suffix = "-".join(str(asset_id) for asset_id in asset_ids) or "empty"
        return f"{experience_type.value.lower()}:{suffix}"

    @classmethod
    def _metadata_asset_ids(cls, metadata: Mapping[str, Any]) -> tuple[int, ...]:
        return (
            cls._coerce_asset_ids(metadata.get("asset_ids"))
            or cls._coerce_asset_ids(metadata.get("source_asset_ids"))
        )

    @classmethod
    def _metadata_asset_order(cls, metadata: Mapping[str, Any]) -> tuple[int, ...]:
        return cls._coerce_asset_ids(metadata.get("asset_order"))

    @classmethod
    def _cover_asset_id(cls, metadata: Mapping[str, Any]) -> int | None:
        value = metadata.get("cover_asset_id")
        if value is None or str(value).strip() == "":
            return None
        return int(value)

    @staticmethod
    def _product_type_value(product: Any) -> str | None:
        product_type = _get(product, "product_type")
        if product_type is None:
            return None
        return getattr(product_type, "value", str(product_type))

    @classmethod
    def _experience_type_for_product(
        cls,
        product: Any,
        *,
        metadata: Mapping[str, Any],
        asset_count: int,
    ) -> ExperienceType:
        explicit_type = metadata.get("experience_type")
        if explicit_type:
            return ExperienceType(str(explicit_type).upper())

        product_structure = str(metadata.get("product_structure") or "").lower()
        if product_structure in {"photo_set", "photoshoot"}:
            return ExperienceType.PHOTOSHOOT
        if product_structure == "story":
            return ExperienceType.STORY

        product_type = cls._product_type_value(product)
        # STORY has no reliable asset-count equivalent in legacy records, so
        # keep ProductType.STORY as a compatibility fallback when explicit
        # Experience metadata is unavailable.
        if product_type == ProductType.STORY.value:
            return ExperienceType.STORY

        if asset_count > 1:
            return ExperienceType.PHOTOSHOOT

        # ProductType is compatibility-only Experience inference. Prefer
        # explicit Experience metadata and asset composition whenever present.
        if product_type in {
            ProductType.PHOTO_SET.value,
            ProductType.VIDEO_SET.value,
        }:
            return ExperienceType.PHOTOSHOOT

        return ExperienceType.STANDALONE
