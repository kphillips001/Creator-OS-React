"""Product Composition advisory service.

ProductCompositionService recommends how Products should be composed from
Assets, Experiences, Product Strategy, Content Intelligence, and Product
Business snapshots. It does not create Products or generate Product Strategy.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING

from app.models.content_intelligence import ContentIntelligence
from app.models.experience_intelligence import ExperienceRecommendation
from app.models.product_business import ProductBusinessSnapshot
from app.models.product_composition import (
    ProductComposition,
    ProductCompositionRecommendation,
    ProductCompositionType,
)

if TYPE_CHECKING:
    from app.services.content_intelligence_service import ContentIntelligenceService
    from app.services.experience_intelligence_service import ExperienceIntelligenceService
    from app.services.experience_service import ExperienceService


RECOMMENDATION_TYPE_MAP = {
    "free_preview": ProductCompositionType.FREE_PREVIEW,
    "single_premium": ProductCompositionType.PREMIUM_PRODUCT,
    "bundle": ProductCompositionType.BUNDLE,
    "story_product": ProductCompositionType.STORY_PRODUCT,
    "photoshoot_product": ProductCompositionType.PHOTOSHOOT_PRODUCT,
    "collection": ProductCompositionType.COLLECTION,
    "vip_collection": ProductCompositionType.COLLECTION,
}


class ProductCompositionService:
    """Build read-only composition recommendations."""

    def __init__(
        self,
        *,
        experience_service: "ExperienceService | None" = None,
        experience_intelligence_service: "ExperienceIntelligenceService | None" = None,
        content_intelligence_service: "ContentIntelligenceService | None" = None,
    ) -> None:
        self._experience_service = experience_service
        self._experience_intelligence_service = experience_intelligence_service
        self._content_intelligence_service = content_intelligence_service

    def recommend_compositions(
        self,
        *,
        product_strategy_result: Any | None = None,
        experience_context: ExperienceRecommendation | Mapping[str, Any] | Any | None = None,
        content_intelligence: ContentIntelligence | Mapping[str, Any] | Any | None = None,
        content_intelligences: Iterable[
            ContentIntelligence | Mapping[str, Any] | Any
        ]
        | None = None,
        product_business_snapshots: Iterable[
            ProductBusinessSnapshot | Mapping[str, Any]
        ]
        | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[ProductCompositionRecommendation, ...]:
        records = self._content_records(content_intelligence, content_intelligences)
        product_business = tuple(product_business_snapshots or ())
        recommendations = list(
            self._from_product_strategy(
                product_strategy_result,
                records=records,
                product_business_snapshots=product_business,
            )
        )
        existing_types = {item.composition_type for item in recommendations}
        fallback = self._fallback_recommendations(
            experience_context=experience_context,
            records=records,
            product_business_snapshots=product_business,
            existing_types=existing_types,
        )
        recommendations.extend(fallback)
        return tuple(
            self._with_metadata(recommendation, metadata or {})
            for recommendation in recommendations
        )

    def recommend_free_preview(
        self,
        *,
        experience_context: Any | None = None,
        content_intelligences: Iterable[Any] | None = None,
    ) -> ProductCompositionRecommendation | None:
        records = self._content_records(None, content_intelligences)
        asset_ids = self._asset_ids(experience_context, records)
        if not asset_ids:
            return None
        cover = self._cover_asset_id(experience_context, records, asset_ids)
        preview_asset = cover or asset_ids[0]
        return self._recommendation(
            composition_type=ProductCompositionType.FREE_PREVIEW,
            included_asset_ids=(preview_asset,),
            preview_asset_ids=(preview_asset,),
            cover_asset_id=preview_asset,
            asset_order=(preview_asset,),
            experience_id=self._safe_text(self._read(experience_context, "experience_id")),
            relationship_type="preview",
            label="FREE Preview composition",
            rationale=("Use the best cover/preview Asset as the free teaser.",),
            confidence=0.7,
            evidence={"source": "fallback_free_preview"},
        )

    def _from_product_strategy(
        self,
        product_strategy_result: Any | None,
        *,
        records: tuple[Any, ...],
        product_business_snapshots: tuple[Any, ...],
    ) -> tuple[ProductCompositionRecommendation, ...]:
        strategy_recommendations = tuple(
            self._read(product_strategy_result, "recommendations") or ()
        )
        items: list[ProductCompositionRecommendation] = []
        for strategy in strategy_recommendations:
            recommendation_type = self._safe_text(
                self._read(strategy, "recommendation_type")
            )
            composition_type = RECOMMENDATION_TYPE_MAP.get(recommendation_type or "")
            if composition_type is None:
                continue
            composition_hint = self._read(strategy, "composition")
            included_asset_ids = self._int_tuple(
                self._read(composition_hint, "included_asset_ids")
                or self._read(strategy, "asset_ids")
            )
            asset_order = self._int_tuple(
                self._read(composition_hint, "asset_order") or included_asset_ids
            )
            cover_asset_id = self._int_or_none(
                self._read(composition_hint, "cover_asset_id")
            ) or self._cover_asset_id(None, records, asset_order or included_asset_ids)
            items.append(
                self._recommendation(
                    composition_type=composition_type,
                    included_asset_ids=included_asset_ids,
                    preview_asset_ids=(
                        (cover_asset_id,) if composition_type == ProductCompositionType.FREE_PREVIEW and cover_asset_id else ()
                    ),
                    premium_asset_ids=(
                        included_asset_ids
                        if composition_type
                        in {
                            ProductCompositionType.PREMIUM_PRODUCT,
                            ProductCompositionType.BUNDLE,
                            ProductCompositionType.STORY_PRODUCT,
                            ProductCompositionType.PHOTOSHOOT_PRODUCT,
                            ProductCompositionType.COLLECTION,
                        }
                        else ()
                    ),
                    cover_asset_id=cover_asset_id,
                    asset_order=asset_order,
                    product_order=self._product_order(product_business_snapshots),
                    related_product_ids=self._related_product_ids(
                        product_business_snapshots
                    ),
                    collection_membership=self._collection_membership(
                        product_business_snapshots
                    ),
                    experience_id=self._safe_text(
                        self._read(composition_hint, "experience_id")
                    )
                    or self._safe_text(self._read(product_strategy_result, "source_id")),
                    relationship_type=self._safe_text(
                        self._read(composition_hint, "relationship_type")
                    ),
                    label=self._label_for(composition_type),
                    rationale=tuple(
                        self._read(composition_hint, "rationale")
                        or self._read(strategy, "rationale")
                        or ()
                    ),
                    confidence=self._float(self._read(strategy, "confidence")),
                    evidence={
                        "source": "product_strategy",
                        "recommendation_type": recommendation_type,
                    },
                )
            )
        return tuple(items)

    def _fallback_recommendations(
        self,
        *,
        experience_context: Any | None,
        records: tuple[Any, ...],
        product_business_snapshots: tuple[Any, ...],
        existing_types: set[ProductCompositionType],
    ) -> tuple[ProductCompositionRecommendation, ...]:
        asset_ids = self._asset_ids(experience_context, records)
        if not asset_ids:
            return ()
        cover = self._cover_asset_id(experience_context, records, asset_ids)
        experience_type = self._text(self._read(experience_context, "experience_type"))
        recommendations: list[ProductCompositionRecommendation] = []
        if ProductCompositionType.FREE_PREVIEW not in existing_types:
            preview = self.recommend_free_preview(
                experience_context=experience_context,
                content_intelligences=records,
            )
            if preview is not None:
                recommendations.append(preview)
        if ProductCompositionType.PREMIUM_PRODUCT not in existing_types:
            recommendations.append(
                self._recommendation(
                    composition_type=ProductCompositionType.PREMIUM_PRODUCT,
                    included_asset_ids=asset_ids,
                    premium_asset_ids=asset_ids,
                    cover_asset_id=cover,
                    asset_order=asset_ids,
                    experience_id=self._safe_text(
                        self._read(experience_context, "experience_id")
                    ),
                    relationship_type="premium_product",
                    label="Premium Product composition",
                    rationale=("Use available Experience Assets as the premium Product.",),
                    confidence=0.6,
                    evidence={"source": "fallback_premium"},
                )
            )
        if len(asset_ids) > 1 and ProductCompositionType.BUNDLE not in existing_types:
            recommendations.append(
                self._recommendation(
                    composition_type=ProductCompositionType.BUNDLE,
                    included_asset_ids=asset_ids,
                    premium_asset_ids=asset_ids,
                    cover_asset_id=cover,
                    asset_order=asset_ids,
                    product_order=self._product_order(product_business_snapshots),
                    related_product_ids=self._related_product_ids(
                        product_business_snapshots
                    ),
                    experience_id=self._safe_text(
                        self._read(experience_context, "experience_id")
                    ),
                    relationship_type="bundle",
                    label="Bundle composition",
                    rationale=("Group related Assets into a Bundle composition.",),
                    confidence=0.62,
                    evidence={"source": "fallback_bundle"},
                )
            )
        if experience_type == "STORY" and ProductCompositionType.STORY_PRODUCT not in existing_types:
            recommendations.append(
                self._recommendation(
                    composition_type=ProductCompositionType.STORY_PRODUCT,
                    included_asset_ids=asset_ids,
                    premium_asset_ids=asset_ids,
                    cover_asset_id=cover,
                    asset_order=asset_ids,
                    experience_id=self._safe_text(
                        self._read(experience_context, "experience_id")
                    ),
                    relationship_type="story_sequence",
                    label="Story Product composition",
                    rationale=("Preserve Experience ordering for story progression.",),
                    confidence=0.68,
                    evidence={"source": "fallback_story"},
                )
            )
        if experience_type == "PHOTOSHOOT" and ProductCompositionType.PHOTOSHOOT_PRODUCT not in existing_types:
            recommendations.append(
                self._recommendation(
                    composition_type=ProductCompositionType.PHOTOSHOOT_PRODUCT,
                    included_asset_ids=asset_ids,
                    premium_asset_ids=asset_ids,
                    cover_asset_id=cover,
                    asset_order=asset_ids,
                    experience_id=self._safe_text(
                        self._read(experience_context, "experience_id")
                    ),
                    relationship_type="photoshoot_set",
                    label="Photoshoot Product composition",
                    rationale=("Preserve photoshoot continuity and cover selection.",),
                    confidence=0.68,
                    evidence={"source": "fallback_photoshoot"},
                )
            )
        if len(product_business_snapshots) > 1 and ProductCompositionType.COLLECTION not in existing_types:
            recommendations.append(
                self._recommendation(
                    composition_type=ProductCompositionType.COLLECTION,
                    included_asset_ids=asset_ids,
                    premium_asset_ids=asset_ids,
                    cover_asset_id=cover,
                    asset_order=asset_ids,
                    product_order=self._product_order(product_business_snapshots),
                    related_product_ids=self._related_product_ids(
                        product_business_snapshots
                    ),
                    collection_membership=self._collection_membership(
                        product_business_snapshots
                    ),
                    experience_id=self._safe_text(
                        self._read(experience_context, "experience_id")
                    ),
                    relationship_type="collection_membership",
                    label="Collection composition",
                    rationale=("Connect related Products into a collection.",),
                    confidence=0.58,
                    evidence={"source": "fallback_collection"},
                )
            )
        return tuple(recommendations)

    def _recommendation(
        self,
        *,
        composition_type: ProductCompositionType,
        included_asset_ids: tuple[int, ...],
        label: str,
        preview_asset_ids: tuple[int, ...] = (),
        premium_asset_ids: tuple[int, ...] = (),
        cover_asset_id: int | None = None,
        asset_order: tuple[int, ...] = (),
        product_order: tuple[str, ...] = (),
        related_product_ids: tuple[str, ...] = (),
        collection_membership: tuple[str, ...] = (),
        experience_id: str | None = None,
        relationship_type: str | None = None,
        rationale: tuple[str, ...] = (),
        confidence: float = 0.0,
        evidence: Mapping[str, Any] | None = None,
    ) -> ProductCompositionRecommendation:
        composition = ProductComposition(
            composition_type=composition_type,
            included_asset_ids=included_asset_ids,
            preview_asset_ids=preview_asset_ids,
            premium_asset_ids=premium_asset_ids,
            cover_asset_id=cover_asset_id,
            asset_order=asset_order or included_asset_ids,
            product_order=product_order,
            related_product_ids=related_product_ids,
            collection_membership=collection_membership,
            experience_id=experience_id,
            relationship_type=relationship_type,
            metadata={"provider_neutral": True},
        )
        return ProductCompositionRecommendation(
            composition=composition,
            label=label,
            rationale=rationale,
            confidence=confidence,
            evidence=dict(evidence or {}),
            compatibility={
                "source": "product_composition",
                "owner": "ProductCompositionService",
                "read_only": True,
                "provider_neutral": True,
                "advisory_only": True,
                "creates_products": False,
                "modifies_products": False,
                "publishes_products": False,
                "executes_telegram": False,
                "generates_product_strategy": False,
                "product_strategy_owner_preserved": True,
                "product_catalog_owner_preserved": True,
            },
        )

    @staticmethod
    def _with_metadata(
        recommendation: ProductCompositionRecommendation,
        metadata: Mapping[str, Any],
    ) -> ProductCompositionRecommendation:
        if not metadata:
            return recommendation
        return ProductCompositionRecommendation(
            composition=recommendation.composition,
            label=recommendation.label,
            rationale=recommendation.rationale,
            confidence=recommendation.confidence,
            source=recommendation.source,
            evidence={**dict(recommendation.evidence), "metadata": dict(metadata)},
            compatibility=recommendation.compatibility,
        )

    @staticmethod
    def _content_records(
        content_intelligence: Any | None,
        content_intelligences: Iterable[Any] | None,
    ) -> tuple[Any, ...]:
        records = []
        if content_intelligence is not None:
            records.append(content_intelligence)
        records.extend(tuple(content_intelligences or ()))
        return tuple(records)

    @classmethod
    def _asset_ids(cls, experience_context: Any | None, records: tuple[Any, ...]) -> tuple[int, ...]:
        values = (
            cls._read(experience_context, "asset_order")
            or cls._read(experience_context, "asset_ids")
            or cls._read(experience_context, "ordered_asset_ids")
        )
        ids = cls._int_tuple(values)
        if ids:
            return ids
        return tuple(
            asset_id
            for asset_id in (cls._int_or_none(cls._read(record, "asset_id")) for record in records)
            if asset_id is not None
        )

    @classmethod
    def _cover_asset_id(
        cls,
        experience_context: Any | None,
        records: tuple[Any, ...],
        asset_ids: tuple[int, ...],
    ) -> int | None:
        cover = cls._int_or_none(
            cls._read(experience_context, "suggested_cover_asset_id")
            or cls._read(experience_context, "cover_asset_id")
        )
        if cover:
            return cover
        for record in records:
            recommendation = cls._read(record, "suggested_cover_image")
            if cls._read(recommendation, "recommended"):
                asset_id = cls._int_or_none(cls._read(recommendation, "asset_id"))
                if asset_id:
                    return asset_id
        return asset_ids[0] if asset_ids else None

    @classmethod
    def _product_order(cls, snapshots: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(
            product_id
            for product_id in (
                cls._safe_text(cls._read(snapshot, "product_id")) for snapshot in snapshots
            )
            if product_id
        )

    @classmethod
    def _related_product_ids(cls, snapshots: tuple[Any, ...]) -> tuple[str, ...]:
        return cls._product_order(snapshots)

    @classmethod
    def _collection_membership(cls, snapshots: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(
            product_id
            for product_id in cls._product_order(snapshots)
            if product_id
        )

    @staticmethod
    def _label_for(composition_type: ProductCompositionType) -> str:
        return {
            ProductCompositionType.FREE_PREVIEW: "FREE Preview composition",
            ProductCompositionType.PREMIUM_PRODUCT: "Premium Product composition",
            ProductCompositionType.BUNDLE: "Bundle composition",
            ProductCompositionType.STORY_PRODUCT: "Story Product composition",
            ProductCompositionType.PHOTOSHOOT_PRODUCT: "Photoshoot Product composition",
            ProductCompositionType.COLLECTION: "Collection composition",
        }[composition_type]

    @staticmethod
    def _read(value: Any, key: str) -> Any:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return value.get(key)
        return getattr(value, key, None)

    @staticmethod
    def _safe_text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value))

    @staticmethod
    def _text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value)).strip().upper()

    @staticmethod
    def _int_tuple(value: Any) -> tuple[int, ...]:
        if value is None:
            return ()
        if isinstance(value, (str, bytes)):
            values = (value,)
        else:
            try:
                values = tuple(value)
            except TypeError:
                values = (value,)
        results = []
        for item in values:
            converted = ProductCompositionService._int_or_none(item)
            if converted is not None:
                results.append(converted)
        return tuple(results)

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
