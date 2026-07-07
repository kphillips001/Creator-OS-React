"""Canonical Product Strategy boundary for Creator OS.

ProductStrategyService owns Product recommendations only. It does not create
Products, Product Drafts, Product metadata, Publishing records, Telegram
payloads, or commerce recommendations.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.models.business_learning import LearningContext
from app.models.commerce_intelligence import CommerceRecommendation
from app.models.content_intelligence import ContentIntelligence
from app.models.creator_intent import CreatorIntent
from app.models.experience_intelligence import ExperienceRecommendation
from app.models.product_strategy import (
    ProductCatalogRecommendation,
    ProductCompositionRecommendation,
    ProductStrategyEvidence,
    ProductStrategyRecommendation,
    ProductStrategyResult,
)


class ProductStrategyService:
    """Build provider-neutral Product Strategy recommendations."""

    def recommend(
        self,
        *,
        creator_intent: CreatorIntent | Mapping[str, Any] | None = None,
        content_intelligence: ContentIntelligence | None = None,
        content_intelligences: Iterable[ContentIntelligence] | None = None,
        experience_context: ExperienceRecommendation | None = None,
        commerce_recommendation: CommerceRecommendation | None = None,
        learning_context: LearningContext | None = None,
    ) -> ProductStrategyResult:
        records = self._content_records(
            content_intelligence,
            content_intelligences,
        )
        asset_ids = self._asset_ids(records, experience_context)
        source_type = self._source_type(records, experience_context)
        source_id = self._source_id(records, experience_context)
        evidence = self._evidence(
            creator_intent=self._creator_intent_context(creator_intent),
            records=records,
            experience_context=experience_context,
            commerce_recommendation=commerce_recommendation,
            learning_context=learning_context,
        )
        recommendations = self._recommendations(
            source_type=source_type,
            source_id=source_id,
            asset_ids=asset_ids,
            evidence=evidence,
            records=records,
            experience_context=experience_context,
        )
        catalog = self._catalog_recommendation(
            source_id=source_id,
            evidence=evidence,
            recommendations=recommendations,
            experience_context=experience_context,
        )
        confidence = self._confidence(recommendations)
        return ProductStrategyResult(
            source_type=source_type,
            source_id=source_id,
            recommendations=recommendations,
            catalog_recommendation=catalog,
            confidence=confidence,
            rationale=tuple(
                dict.fromkeys(
                    reason
                    for recommendation in recommendations
                    for reason in recommendation.rationale
                )
            ),
            evidence=evidence,
            metadata={
                "source": "product_strategy",
                "owner": "ProductStrategyService",
                "creates_products": False,
                "creates_product_drafts": False,
                "new_ai_analysis": False,
                "commerce_intelligence_consumed": (
                    commerce_recommendation is not None
                ),
                "learning_context_consumed": learning_context is not None,
                "learning_context_evidence_only": True,
                "content_intelligence_count": len(records),
            },
        )

    def _recommendations(
        self,
        *,
        source_type: str,
        source_id: str | None,
        asset_ids: tuple[int, ...],
        evidence: tuple[ProductStrategyEvidence, ...],
        records: tuple[ContentIntelligence, ...],
        experience_context: ExperienceRecommendation | None,
    ) -> tuple[ProductStrategyRecommendation, ...]:
        if not records and experience_context is None:
            return ()

        types = self._recommendation_types(
            asset_ids=asset_ids,
            records=records,
            experience_context=experience_context,
        )
        confidence = self._recommendation_confidence(evidence)
        rationale = tuple(item.detail for item in evidence if item.detail)
        return tuple(
            ProductStrategyRecommendation(
                recommendation_type=recommendation_type,
                source_type=source_type,
                source_id=source_id,
                asset_ids=asset_ids,
                composition=self._composition_recommendation(
                    recommendation_type=recommendation_type,
                    asset_ids=asset_ids,
                    records=records,
                    experience_context=experience_context,
                ),
                confidence=confidence,
                rationale=tuple(str(item) for item in rationale),
                evidence=evidence,
                metadata={
                    "content_recommendations": tuple(
                        self._content_recommendation_metadata(record)
                        for record in records
                    ),
                    "experience_type": self._experience_type(experience_context),
                },
            )
            for recommendation_type in types
        )

    def _composition_recommendation(
        self,
        *,
        recommendation_type: str,
        asset_ids: tuple[int, ...],
        records: tuple[ContentIntelligence, ...],
        experience_context: ExperienceRecommendation | None,
    ) -> ProductCompositionRecommendation:
        ordered_asset_ids = self._asset_order(asset_ids, experience_context)
        included_asset_ids = self._included_asset_ids(
            recommendation_type,
            ordered_asset_ids,
        )
        cover_asset_id = self._cover_asset_id(
            included_asset_ids,
            records,
            experience_context,
        )
        composition_type = self._composition_type(recommendation_type)
        return ProductCompositionRecommendation(
            composition_type=composition_type,
            included_asset_ids=included_asset_ids,
            asset_order=tuple(
                asset_id
                for asset_id in ordered_asset_ids
                if asset_id in set(included_asset_ids)
            ),
            cover_asset_id=cover_asset_id,
            experience_id=self._source_id(records, experience_context),
            relationship_type=self._relationship_type(
                recommendation_type,
                experience_context,
            ),
            related_recommendation_types=self._related_recommendation_types(
                recommendation_type,
            ),
            rationale=self._composition_rationale(
                recommendation_type,
                included_asset_ids,
                experience_context,
            ),
        )

    def _catalog_recommendation(
        self,
        *,
        source_id: str | None,
        evidence: tuple[ProductStrategyEvidence, ...],
        recommendations: tuple[ProductStrategyRecommendation, ...],
        experience_context: ExperienceRecommendation | None,
    ) -> ProductCatalogRecommendation | None:
        if experience_context is None:
            return None
        return ProductCatalogRecommendation(
            associated_experience_id=source_id,
            associated_experience_type=self._experience_type(experience_context),
            recommended_products=recommendations,
            confidence=self._confidence(recommendations),
            rationale=tuple(
                dict.fromkeys(
                    reason
                    for recommendation in recommendations
                    for reason in recommendation.rationale
                )
            ),
            evidence=evidence,
            metadata={
                "source": "product_strategy",
                "owner": "ProductStrategyService",
                "creates_products": False,
                "creates_product_drafts": False,
                "contains_product_metadata": False,
            },
        )

    @classmethod
    def _recommendation_types(
        cls,
        *,
        asset_ids: tuple[int, ...],
        records: tuple[ContentIntelligence, ...],
        experience_context: ExperienceRecommendation | None,
    ) -> tuple[str, ...]:
        experience_type = (cls._experience_type(experience_context) or "").upper()
        count = len(asset_ids) or len(records)
        values = ["free_preview"]

        if count <= 1:
            values.append("single_premium")
        else:
            values.append("bundle")
            values.append("collection")

        if experience_type == "PHOTOSHOOT":
            values.append("photoshoot_product")
            if count >= 3:
                values.append("vip_collection")
        elif experience_type == "STORY":
            values.append("story_product")
            values.append("collection")
        elif count >= 3:
            values.append("vip_collection")

        return tuple(dict.fromkeys(values))

    @classmethod
    def _asset_order(
        cls,
        asset_ids: tuple[int, ...],
        experience_context: ExperienceRecommendation | None,
    ) -> tuple[int, ...]:
        ordered = (
            getattr(experience_context, "asset_order", None)
            or getattr(experience_context, "ordered_asset_ids", None)
        )
        values = cls._coerce_asset_ids(ordered)
        if values:
            ordered_set = set(values)
            remaining = tuple(
                asset_id for asset_id in asset_ids if asset_id not in ordered_set
            )
            return values + remaining
        return asset_ids

    @staticmethod
    def _included_asset_ids(
        recommendation_type: str,
        ordered_asset_ids: tuple[int, ...],
    ) -> tuple[int, ...]:
        if not ordered_asset_ids:
            return ()
        if recommendation_type == "free_preview":
            return (ordered_asset_ids[0],)
        if recommendation_type == "single_premium":
            return (ordered_asset_ids[-1],)
        return ordered_asset_ids

    @classmethod
    def _cover_asset_id(
        cls,
        included_asset_ids: tuple[int, ...],
        records: tuple[ContentIntelligence, ...],
        experience_context: ExperienceRecommendation | None,
    ) -> int | None:
        explicit = cls._coerce_int(
            getattr(experience_context, "suggested_cover_asset_id", None)
        )
        if explicit is None:
            explicit = cls._coerce_int(
                getattr(experience_context, "cover_asset_id", None)
            )
        if explicit in included_asset_ids:
            return explicit
        for record in records:
            recommendation = getattr(record, "suggested_cover_image", None)
            if not getattr(recommendation, "recommended", False):
                continue
            asset_id = cls._coerce_int(getattr(recommendation, "asset_id", None))
            if asset_id in included_asset_ids:
                return asset_id
        return included_asset_ids[0] if included_asset_ids else None

    @staticmethod
    def _composition_type(recommendation_type: str) -> str:
        mapping = {
            "free_preview": "single_asset_product",
            "single_premium": "single_asset_product",
            "bundle": "bundle_product",
            "photoshoot_product": "photoshoot_product",
            "story_product": "story_product",
            "collection": "collection_product",
            "vip_collection": "collection_product",
        }
        return mapping.get(recommendation_type, "product")

    @classmethod
    def _relationship_type(
        cls,
        recommendation_type: str,
        experience_context: ExperienceRecommendation | None,
    ) -> str | None:
        if experience_context is None:
            return None
        if recommendation_type in {"free_preview", "single_premium"}:
            return "experience_asset_product"
        return "experience_product"

    @staticmethod
    def _related_recommendation_types(
        recommendation_type: str,
    ) -> tuple[str, ...]:
        if recommendation_type == "free_preview":
            return ("single_premium", "bundle", "collection")
        if recommendation_type == "single_premium":
            return ("free_preview",)
        if recommendation_type in {"bundle", "collection", "vip_collection"}:
            return ("free_preview",)
        if recommendation_type in {"photoshoot_product", "story_product"}:
            return ("free_preview", "collection")
        return ()

    @staticmethod
    def _composition_rationale(
        recommendation_type: str,
        included_asset_ids: tuple[int, ...],
        experience_context: ExperienceRecommendation | None,
    ) -> tuple[str, ...]:
        count = len(included_asset_ids)
        if recommendation_type == "free_preview":
            return ("Use the first ordered asset as the preview product.",)
        if recommendation_type == "single_premium":
            return ("Use one asset as a standalone premium product.",)
        if recommendation_type == "photoshoot_product":
            return (f"Use all {count} Experience assets as a photoshoot product.",)
        if recommendation_type == "story_product":
            return ("Preserve Experience ordering for story progression.",)
        if recommendation_type == "vip_collection":
            return (f"Use all {count} Experience assets as a VIP collection.",)
        if recommendation_type == "collection":
            return ("Use the Experience asset set as a collection product.",)
        if recommendation_type == "bundle":
            return ("Use multiple Experience assets as a bundle product.",)
        return ("Use the available Experience composition.",)

    @staticmethod
    def _recommendation_confidence(
        evidence: tuple[ProductStrategyEvidence, ...],
    ) -> float:
        return round(
            min(0.95, max(0.25, sum(item.weight for item in evidence) / 100)),
            2,
        )

    def _evidence(
        self,
        *,
        creator_intent: Mapping[str, Any] | None,
        records: tuple[ContentIntelligence, ...],
        experience_context: ExperienceRecommendation | None,
        commerce_recommendation: CommerceRecommendation | None,
        learning_context: LearningContext | None,
    ) -> tuple[ProductStrategyEvidence, ...]:
        evidence: list[ProductStrategyEvidence] = []
        if creator_intent:
            content_type = creator_intent.get("content_type")
            evidence.append(
                ProductStrategyEvidence(
                    reason="creator_intent",
                    detail=(
                        f"Creator intent is available: {content_type}."
                        if content_type
                        else "Creator intent is available."
                    ),
                    weight=20,
                )
            )
        if records:
            evidence.append(
                ProductStrategyEvidence(
                    reason="content_intelligence",
                    detail=(
                        f"{len(records)} Content Intelligence record(s) "
                        "available."
                    ),
                    weight=30,
                )
            )
        if any(getattr(record, "suggested_cover_image", None) for record in records):
            evidence.append(
                ProductStrategyEvidence(
                    reason="content_recommendations",
                    detail="Content recommendations are available.",
                    weight=15,
                )
            )
        if experience_context is not None:
            evidence.append(
                ProductStrategyEvidence(
                    reason="experience_context",
                    detail="Experience context is available.",
                    weight=25,
                )
            )
        if commerce_recommendation is not None:
            evidence.append(
                ProductStrategyEvidence(
                    reason="commerce_context",
                    detail="Commerce recommendation is available as context.",
                    weight=10,
                )
            )
        if learning_context is not None:
            evidence.append(
                ProductStrategyEvidence(
                    reason="learning_context",
                    detail="Business Learning evidence is available.",
                    weight=5,
                )
            )
        return tuple(evidence)

    @staticmethod
    def _creator_intent_context(
        creator_intent: CreatorIntent | Mapping[str, Any] | None,
    ) -> Mapping[str, Any] | None:
        if isinstance(creator_intent, CreatorIntent):
            return creator_intent.to_context()
        return creator_intent

    @staticmethod
    def _content_records(
        content_intelligence: ContentIntelligence | None,
        content_intelligences: Iterable[ContentIntelligence] | None,
    ) -> tuple[ContentIntelligence, ...]:
        values = []
        if content_intelligence is not None:
            values.append(content_intelligence)
        if content_intelligences is not None:
            values.extend(item for item in content_intelligences if item is not None)
        return tuple(values)

    @classmethod
    def _coerce_asset_ids(cls, values: Any) -> tuple[int, ...]:
        if values is None:
            return ()
        if isinstance(values, (str, bytes)):
            values = (values,)
        result = []
        seen = set()
        try:
            iterator = iter(values)
        except TypeError:
            iterator = iter((values,))
        for value in iterator:
            asset_id = cls._coerce_int(value)
            if asset_id is None or asset_id in seen:
                continue
            seen.add(asset_id)
            result.append(asset_id)
        return tuple(result)

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _asset_ids(
        cls,
        records: tuple[ContentIntelligence, ...],
        experience_context: ExperienceRecommendation | None,
    ) -> tuple[int, ...]:
        values = list(getattr(experience_context, "asset_ids", ()) or ())
        values.extend(getattr(record, "asset_id", None) for record in records)
        result = []
        seen = set()
        for value in values:
            try:
                asset_id = int(value)
            except (TypeError, ValueError):
                continue
            if asset_id in seen:
                continue
            seen.add(asset_id)
            result.append(asset_id)
        return tuple(result)

    @staticmethod
    def _source_type(
        records: tuple[ContentIntelligence, ...],
        experience_context: ExperienceRecommendation | None,
    ) -> str:
        if experience_context is not None:
            return "experience"
        if len(records) > 1:
            return "content_collection"
        return "content"

    @staticmethod
    def _source_id(
        records: tuple[ContentIntelligence, ...],
        experience_context: ExperienceRecommendation | None,
    ) -> str | None:
        value = (
            getattr(experience_context, "experience_id", None)
            or getattr(experience_context, "source_id", None)
        )
        if value is not None:
            return str(value)
        asset_ids = tuple(getattr(record, "asset_id", None) for record in records)
        clean = tuple(str(asset_id) for asset_id in asset_ids if asset_id is not None)
        return "-".join(clean) if clean else None

    @staticmethod
    def _is_collection(experience_context: ExperienceRecommendation | None) -> bool:
        if experience_context is None:
            return False
        if bool(getattr(experience_context, "is_collection", False)):
            return True
        return len(tuple(getattr(experience_context, "asset_ids", ()) or ())) > 1

    @staticmethod
    def _experience_type(
        experience_context: ExperienceRecommendation | None,
    ) -> str | None:
        if experience_context is None:
            return None
        value = getattr(experience_context, "experience_type", None)
        return getattr(value, "value", value)

    @staticmethod
    def _content_recommendation_metadata(
        record: ContentIntelligence,
    ) -> Mapping[str, Any]:
        recommendation = getattr(record, "suggested_cover_image", None)
        if recommendation is None:
            return {}
        context = getattr(recommendation, "to_context", None)
        return context() if callable(context) else {}

    @staticmethod
    def _confidence(
        recommendations: tuple[ProductStrategyRecommendation, ...],
    ) -> float:
        if not recommendations:
            return 0.0
        return round(
            sum(item.confidence for item in recommendations) / len(recommendations),
            2,
        )
