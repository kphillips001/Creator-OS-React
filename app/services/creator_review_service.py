"""Build presentation-only Creator Review objects from import workflow results."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from app.models.creator_review import (
    CreatorReview,
    CreatorReviewDashboardItem,
    CreatorReviewDashboardSummary,
    CreatorReviewSection,
)
from app.models.experience import Experience, ExperienceType
from app.services.experience_service import ExperienceService
from app.services.content_intelligence_service import ContentIntelligenceService


class CreatorReviewService:
    """Aggregate completed AI import workflow results for creator review."""

    def __init__(
        self,
        *,
        experience_service: ExperienceService | None = None,
        content_intelligence_service: ContentIntelligenceService | None = None,
    ):
        self._experiences = experience_service
        self._content_intelligence = content_intelligence_service

    @property
    def experiences(self) -> ExperienceService:
        if self._experiences is None:
            self._experiences = ExperienceService()
        return self._experiences

    @property
    def content_intelligence(self) -> ContentIntelligenceService:
        if self._content_intelligence is None:
            self._content_intelligence = ContentIntelligenceService()
        return self._content_intelligence

    def build_review(
        self,
        workflow_result: Any,
        *,
        manual_overrides: Mapping[str, Any] | None = None,
    ) -> CreatorReview:
        asset_results = self._asset_results(workflow_result)
        asset_ids = self._asset_ids(workflow_result, asset_results)
        organization = getattr(workflow_result, "organization_result", None)
        experience = getattr(workflow_result, "experience_recommendation", None)
        commerce = getattr(workflow_result, "commerce_recommendation", None)
        product_strategy = getattr(workflow_result, "product_strategy_result", None)
        commerce_strategy = getattr(workflow_result, "commerce_strategy_result", None)
        product_draft = getattr(workflow_result, "product_draft_result", None)
        publishing = getattr(workflow_result, "publishing_readiness", {}) or {}
        warnings = self._warnings(
            workflow_result,
            asset_results=asset_results,
            organization=organization,
            product_draft=product_draft,
            publishing_readiness=publishing,
        )

        review = CreatorReview(
            review_type=self._review_type(workflow_result, organization),
            asset_ids=asset_ids,
            asset=self._asset_section(workflow_result, asset_results),
            asset_understanding=self._understanding_section(asset_results),
            content_intelligence=self._content_intelligence_section(
                asset_results
            ),
            experience=self._experience_review_section(
                experience,
                organization=organization,
                product_draft=product_draft,
                publishing_readiness=publishing,
            ),
            experience_recommendation=self._experience_section(experience),
            product_strategy=self._product_strategy_section(product_strategy),
            commerce_strategy=self._commerce_strategy_section(commerce_strategy),
            commerce_recommendation=self._commerce_section(commerce),
            product_draft=self._product_draft_section(product_draft),
            delivery_type=self._delivery_section(commerce, organization),
            publishing_readiness=self._publishing_section(publishing),
            organization=self._organization_section(organization),
            warnings=warnings,
            manual_overrides=dict(manual_overrides or {}),
        )
        return review

    def build_workspace_review_summary(
        self,
        *,
        asset_summary: Any,
        experience_cards: Iterable[Any] = (),
        product_cards: Iterable[Any] = (),
        publishing_cards: Iterable[Any] = (),
    ) -> CreatorReviewDashboardSummary:
        """Build read-only Creator Review dashboard projections."""

        items: list[CreatorReviewDashboardItem] = []
        assets_awaiting = self._metric_as_int(
            asset_summary,
            "Needs Classification",
        ) + self._metric_as_int(asset_summary, "Asset Alerts")
        if assets_awaiting:
            items.append(
                CreatorReviewDashboardItem(
                    review_type="assets",
                    title="Assets awaiting review",
                    detail=f"{assets_awaiting} Asset(s) need creator review.",
                    status="pending",
                    priority="warning",
                    target="Asset Library",
                    evidence_available=True,
                    override_proposals=("classification", "tags", "themes"),
                    completeness="partial",
                )
            )

        experience_items = tuple(experience_cards or ())
        experiences_awaiting = sum(
            1
            for card in experience_items
            if self._value(card, "intelligence_coverage") in {"Missing", "Partial"}
            or self._value(card, "compatibility") is True
            or not self._value(card, "cover_asset_id")
        )
        if experiences_awaiting:
            items.append(
                CreatorReviewDashboardItem(
                    review_type="experiences",
                    title="Experiences awaiting review",
                    detail=(
                        f"{experiences_awaiting} Experience(s) need "
                        "creator review."
                    ),
                    status="pending",
                    priority="info",
                    target=None,
                    confidence=self._average_confidence(experience_items),
                    evidence_available=any(
                        bool(self._value(card, "themes"))
                        or bool(self._value(card, "keywords"))
                        or bool(self._value(card, "story_progression"))
                        for card in experience_items
                    ),
                    override_proposals=(
                        "experience_name",
                        "experience_summary",
                        "cover_asset_id",
                        "themes",
                        "keywords",
                    ),
                    completeness=self._review_completeness(
                        len(experience_items),
                        experiences_awaiting,
                    ),
                )
            )

        product_items = tuple(product_cards or ())
        products_awaiting = sum(
            1
            for card in product_items
            if self._value(card, "review_status") not in {"Ready", "Published"}
        )
        if products_awaiting:
            items.append(
                CreatorReviewDashboardItem(
                    review_type="products",
                    title="Products awaiting review",
                    detail=f"{products_awaiting} Product(s) need review.",
                    status="pending",
                    priority="warning",
                    target="Product Catalog",
                    evidence_available=any(
                        self._value(card, "suggested_price") not in {None, "-"}
                        for card in product_items
                    ),
                    override_proposals=("price", "delivery_type", "description"),
                    completeness=self._review_completeness(
                        len(product_items),
                        products_awaiting,
                    ),
                )
            )

        publishing_items = tuple(publishing_cards or ())
        publishing_remaining = sum(
            1
            for card in publishing_items
            if bool(self._value(card, "missing_requirements"))
            or self._value(card, "provider_error")
        )
        if publishing_remaining:
            items.append(
                CreatorReviewDashboardItem(
                    review_type="publishing",
                    title="Publishing readiness awaiting review",
                    detail=(
                        f"{publishing_remaining} publishing item(s) need "
                        "creator review."
                    ),
                    status="pending",
                    priority="critical"
                    if any(self._value(card, "provider_error") for card in publishing_items)
                    else "warning",
                    target="Wall Scheduler",
                    evidence_available=True,
                    override_proposals=("media_link", "provider_status"),
                    completeness=self._review_completeness(
                        len(publishing_items),
                        publishing_remaining,
                    ),
                )
            )

        total_pending = (
            assets_awaiting
            + experiences_awaiting
            + products_awaiting
            + publishing_remaining
        )
        high_priority = sum(
            1 for item in items if item.priority in {"critical", "warning"}
        )
        return CreatorReviewDashboardSummary(
            total_pending=total_pending,
            assets_awaiting_review=assets_awaiting,
            experiences_awaiting_review=experiences_awaiting,
            products_awaiting_review=products_awaiting,
            high_priority_reviews=high_priority,
            publishing_reviews_remaining=publishing_remaining,
            completed_reviews=None,
            review_completion_percentage=None,
            items=tuple(sorted(items, key=self._review_item_sort_key)),
        )

    @staticmethod
    def _review_item_sort_key(item: CreatorReviewDashboardItem) -> tuple[int, str]:
        priorities = {"critical": 0, "warning": 1, "info": 2}
        return priorities.get(item.priority, 3), item.title

    @staticmethod
    def _value(item: Any, name: str, default: Any = None) -> Any:
        if isinstance(item, Mapping):
            return item.get(name, default)
        return getattr(item, name, default)

    def _metric_as_int(self, summary: Any, label: str) -> int:
        metrics = self._value(summary, "metrics", ()) or ()
        for metric in metrics:
            if self._value(metric, "label") != label:
                continue
            value = self._value(metric, "value", "0")
            try:
                return int(str(value).replace(",", ""))
            except (TypeError, ValueError):
                return 0
        return 0

    @staticmethod
    def _average_confidence(items: Iterable[Any]) -> float | None:
        values = [
            float(value)
            for item in items
            if (value := getattr(item, "confidence", None)) is not None
        ]
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    @staticmethod
    def _review_completeness(total: int, pending: int) -> str:
        if total <= 0:
            return "Unavailable"
        complete = max(0, total - pending)
        return f"{round((complete / total) * 100)}%"

    def _experience_review_section(
        self,
        recommendation: Any | None,
        *,
        organization: Any | None,
        product_draft: Any | None,
        publishing_readiness: Mapping[str, Any],
    ) -> CreatorReviewSection:
        if recommendation is None:
            return CreatorReviewSection(
                title="Experience",
                status="missing",
                warnings=("Experience is unavailable for review.",),
            )

        experience = self._experience_contract_from_recommendation(
            recommendation
        )
        metadata = self.experiences.get_metadata(experience)
        asset_ids = self.experiences.get_ordered_asset_ids(experience)
        cover_asset_id = self.experiences.get_cover_asset_id(experience)
        experience_type = self.experiences.get_experience_type(experience)
        product_id = self._product_id_from_draft(product_draft)
        product_relationships = self._product_relationships(product_id)
        product_relationship_ids = tuple(
            relationship.product_id for relationship in product_relationships
        )
        experience_product_relationships = self._experience_product_relationships(
            getattr(experience, "experience_id", None)
        )
        asset_relationships = self._asset_relationships(asset_ids)
        return CreatorReviewSection(
            title="Experience",
            status="available",
            summary=experience.description or experience.title,
            confidence=self._float_or_none(
                getattr(recommendation, "confidence", None)
            ),
            data={
                "experience_id": getattr(experience, "experience_id", None),
                "experience_name": experience.title,
                "experience_type": getattr(
                    experience_type,
                    "value",
                    experience_type,
                ),
                "experience_summary": experience.description,
                "cover_asset_id": cover_asset_id,
                "asset_ids": asset_ids,
                "themes": tuple(
                    getattr(recommendation, "suggested_themes", ()) or ()
                ),
                "keywords": tuple(
                    getattr(recommendation, "suggested_keywords", ()) or ()
                ),
                "mood": getattr(recommendation, "mood", None),
                "setting": getattr(recommendation, "setting", None),
                "visual_continuity": dict(
                    getattr(recommendation, "visual_continuity", {}) or {}
                ),
                "story_progression": dict(
                    getattr(recommendation, "story_progression", {}) or {}
                ),
                "technical_continuity": dict(
                    getattr(recommendation, "technical_continuity", {}) or {}
                ),
                "experience_relationships": asset_relationships,
                "product_relationships": product_relationship_ids
                or tuple(
                    relationship.product_id
                    for relationship in experience_product_relationships
                ),
                "publishing_readiness": dict(publishing_readiness or {}),
                "organization_type": getattr(
                    organization,
                    "organization_type",
                    None,
                ),
                "intelligence_metadata": dict(
                    getattr(recommendation, "intelligence_metadata", {}) or {}
                ),
                "intelligence_provenance": dict(
                    getattr(recommendation, "intelligence_provenance", {}) or {}
                ),
                "experience_metadata": dict(metadata or {}),
                "supported_overrides": (
                    "experience_name",
                    "experience_summary",
                    "cover_asset_id",
                    "themes",
                    "keywords",
                ),
            },
            evidence=self._evidence(getattr(recommendation, "evidence", ()) or ()),
        )

    def _experience_contract_from_recommendation(
        self,
        recommendation: Any,
    ) -> Experience:
        experience_type = self._experience_type(
            getattr(recommendation, "experience_type", None)
        )
        asset_ids = tuple(int(value) for value in getattr(
            recommendation,
            "asset_ids",
            (),
        ) or ())
        metadata = {
            "source": "creator_review",
            "experience_intelligence": dict(
                getattr(recommendation, "intelligence_metadata", {}) or {}
            ),
            "intelligence_provenance": dict(
                getattr(recommendation, "intelligence_provenance", {}) or {}
            ),
            "suggested_themes": tuple(
                getattr(recommendation, "suggested_themes", ()) or ()
            ),
            "suggested_keywords": tuple(
                getattr(recommendation, "suggested_keywords", ()) or ()
            ),
            "mood": getattr(recommendation, "mood", None),
            "setting": getattr(recommendation, "setting", None),
            "visual_continuity": dict(
                getattr(recommendation, "visual_continuity", {}) or {}
            ),
            "story_progression": dict(
                getattr(recommendation, "story_progression", {}) or {}
            ),
            "technical_continuity": dict(
                getattr(recommendation, "technical_continuity", {}) or {}
            ),
        }
        metadata.update(dict(getattr(recommendation, "metadata", {}) or {}))
        return Experience(
            experience_id=metadata.get("experience_id"),
            experience_type=experience_type,
            title=getattr(recommendation, "suggested_name", None)
            or "Experience",
            description=getattr(recommendation, "suggested_summary", None),
            cover_asset_id=getattr(
                recommendation,
                "suggested_cover_asset_id",
                None,
            ),
            asset_ids=asset_ids,
            asset_order=asset_ids,
            metadata=metadata,
        )

    @staticmethod
    def _experience_type(value: Any) -> ExperienceType:
        normalized = getattr(value, "value", value) or ExperienceType.STANDALONE.value
        try:
            return ExperienceType(str(normalized))
        except ValueError:
            return ExperienceType.STANDALONE

    def _asset_relationships(
        self,
        asset_ids: tuple[int, ...],
    ) -> tuple[Mapping[str, Any], ...]:
        relationships = []
        for asset_id in asset_ids:
            for relationship in self.experiences.list_asset_relationships(asset_id):
                relationships.append(
                    {
                        "asset_id": relationship.asset_id,
                        "experience_id": relationship.experience_id,
                        "position": relationship.position,
                        "role": relationship.role,
                        "source": relationship.source,
                        "compatibility": relationship.compatibility,
                    }
                )
        return tuple(relationships)

    def _product_relationships(
        self,
        product_id: UUID | None,
    ) -> tuple[Any, ...]:
        if product_id is None:
            return ()
        try:
            return tuple(self.experiences.list_product_relationships(product_id))
        except Exception:
            return ()

    def _experience_product_relationships(
        self,
        experience_id: Any,
    ) -> tuple[Any, ...]:
        if not experience_id:
            return ()
        try:
            return tuple(
                self.experiences.list_experience_product_relationships(
                    str(experience_id)
                )
            )
        except Exception:
            return ()

    def _product_id_from_draft(self, product_draft: Any | None) -> UUID | None:
        data = self._product_draft_data(product_draft) if product_draft else {}
        product_id = data.get("product_id")
        if not product_id:
            return None
        try:
            return UUID(str(product_id))
        except ValueError:
            return None

    @staticmethod
    def _asset_results(workflow_result: Any) -> tuple[Any, ...]:
        values = getattr(workflow_result, "asset_results", None)
        if values is None:
            return (workflow_result,)
        return tuple(values)

    def _asset_ids(
        self,
        workflow_result: Any,
        asset_results: tuple[Any, ...],
    ) -> tuple[int, ...]:
        content_ids = getattr(workflow_result, "content_ids", None)
        if content_ids:
            return tuple(int(asset_id) for asset_id in content_ids)
        values = []
        for result in asset_results:
            content_id = getattr(result, "content_id", None)
            if content_id is not None:
                values.append(int(content_id))
        return tuple(values)

    @staticmethod
    def _review_type(workflow_result: Any, organization: Any | None) -> str:
        organization_type = getattr(organization, "organization_type", None)
        if organization_type:
            return str(organization_type)
        if getattr(workflow_result, "asset_results", None) is not None:
            return "batch"
        return "standalone"

    def _asset_section(
        self,
        workflow_result: Any,
        asset_results: tuple[Any, ...],
    ) -> CreatorReviewSection:
        assets = [getattr(result, "asset", None) for result in asset_results]
        available_assets = [asset for asset in assets if asset is not None]
        asset_ids = self._asset_ids(workflow_result, asset_results)
        media_paths = tuple(
            str(getattr(result, "media_path", ""))
            for result in asset_results
            if getattr(result, "media_path", None)
        )
        return CreatorReviewSection(
            title="Asset",
            status="available" if available_assets else "pending",
            summary=self._asset_summary(available_assets, asset_ids),
            data={
                "asset_ids": asset_ids,
                "asset_count": len(asset_ids),
                "media_paths": media_paths,
                "upload_intents": tuple(
                    getattr(result, "upload_intent", None)
                    for result in asset_results
                    if getattr(result, "upload_intent", None)
                ),
            },
            warnings=()
            if available_assets
            else ("Asset projection is unavailable for review.",),
        )

    @staticmethod
    def _asset_summary(assets: list[Any], asset_ids: tuple[int, ...]) -> str:
        if len(asset_ids) > 1:
            return f"{len(asset_ids)} imported assets are ready for review."
        if assets:
            name = getattr(assets[0], "file_name", None)
            if name:
                return f"Imported asset {name} is ready for review."
        if asset_ids:
            return f"Imported asset {asset_ids[0]} is ready for review."
        return "Imported asset is pending projection."

    def _understanding_section(
        self,
        asset_results: tuple[Any, ...],
    ) -> CreatorReviewSection:
        understandings = tuple(
            getattr(result, "asset_understanding", None)
            for result in asset_results
            if getattr(result, "asset_understanding", None) is not None
        )
        classifications = tuple(
            self._classification_value(understanding)
            for understanding in understandings
            if self._classification_value(understanding)
        )
        confidence = self._average(
            self._classification_confidence(understanding)
            for understanding in understandings
        )
        summaries = tuple(
            self._visual_summary(understanding)
            for understanding in understandings
            if self._visual_summary(understanding)
        )
        return CreatorReviewSection(
            title="Asset Understanding",
            status="available" if understandings else "missing",
            summary=summaries[0] if summaries else None,
            confidence=confidence,
            data={
                "asset_count": len(understandings),
                "classifications": classifications,
                "summaries": summaries,
                "risk_flags": self._risk_flags(understandings),
            },
            warnings=()
            if understandings
            else ("Asset Understanding is unavailable.",),
        )

    def _content_intelligence_section(
        self,
        asset_results: tuple[Any, ...],
    ) -> CreatorReviewSection:
        records = self._content_intelligence_records(asset_results)
        if not records:
            return CreatorReviewSection(
                title="Content Intelligence",
                status="missing",
                warnings=("Content Intelligence is unavailable.",),
            )

        cover_recommendations = tuple(
            recommendation.to_context()
            for recommendation in (
                getattr(record, "suggested_cover_image", None)
                for record in records
            )
            if recommendation is not None
        )
        recommended_covers = tuple(
            item.get("asset_id")
            for item in cover_recommendations
            if item.get("recommended") and item.get("asset_id") is not None
        )
        rationale = tuple(
            reason
            for recommendation in cover_recommendations
            for reason in recommendation.get("rationale", ()) or ()
        )
        return CreatorReviewSection(
            title="Content Intelligence",
            status="available",
            summary=self._first_available(
                getattr(record, "summary", None) for record in records
            ),
            confidence=self._average(
                getattr(
                    getattr(record, "suggested_cover_image", None),
                    "confidence",
                    None,
                )
                for record in records
            ),
            data={
                "asset_count": len(records),
                "environments": self._unique_values(
                    getattr(record, "environment", None) for record in records
                ),
                "activities": self._unique_values(
                    value
                    for record in records
                    for value in getattr(record, "activities", ()) or ()
                ),
                "moods": self._unique_values(
                    getattr(record, "mood", None) for record in records
                ),
                "clothing": self._unique_values(
                    getattr(record, "clothing", None) for record in records
                ),
                "themes": self._unique_values(
                    value
                    for record in records
                    for value in getattr(record, "themes", ()) or ()
                ),
                "keywords": self._unique_values(
                    value
                    for record in records
                    for value in getattr(record, "keywords", ()) or ()
                ),
                "technical_quality": tuple(
                    dict(getattr(record, "technical_quality", {}) or {})
                    for record in records
                ),
                "suggested_cover_image": recommended_covers[0]
                if recommended_covers
                else None,
                "cover_recommendations": cover_recommendations,
                "recommendation_rationale": tuple(dict.fromkeys(rationale)),
                "ownership": {
                    "content_intelligence_owner": "ContentIntelligenceService",
                    "creator_review_owner": "CreatorReviewService",
                },
            },
        )

    def _content_intelligence_records(
        self,
        asset_results: tuple[Any, ...],
    ) -> tuple[Any, ...]:
        records = []
        for result in asset_results:
            record = getattr(result, "content_intelligence", None)
            if record is not None:
                records.append(record)
                continue
            understanding = getattr(result, "asset_understanding", None)
            if understanding is None:
                continue
            try:
                records.append(
                    self.content_intelligence.build_from_understanding(
                        understanding
                    )
                )
            except Exception:
                continue
        return tuple(records)

    @staticmethod
    def _classification_value(understanding: Any) -> str | None:
        classification = getattr(understanding, "classification", None)
        return (
            getattr(classification, "final_classification", None)
            or getattr(classification, "classification", None)
        )

    @staticmethod
    def _classification_confidence(understanding: Any) -> float | None:
        classification = getattr(understanding, "classification", None)
        value = getattr(classification, "confidence", None)
        return float(value) if value is not None else None

    @staticmethod
    def _visual_summary(understanding: Any) -> str | None:
        visual = getattr(understanding, "visual", None)
        return getattr(visual, "summary", None)

    @staticmethod
    def _risk_flags(understandings: Iterable[Any]) -> tuple[str, ...]:
        flags = []
        for understanding in understandings:
            safety = getattr(understanding, "safety", None)
            flags.extend(getattr(safety, "risk_flags", ()) or ())
        return tuple(dict.fromkeys(str(flag) for flag in flags if flag))

    @staticmethod
    def _first_available(values: Iterable[Any]) -> str | None:
        for value in values:
            if value is not None and str(value).strip():
                return str(value)
        return None

    @staticmethod
    def _unique_values(values: Iterable[Any]) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(text)
        return tuple(result)

    def _experience_section(
        self,
        experience: Any | None,
    ) -> CreatorReviewSection:
        if experience is None:
            return CreatorReviewSection(
                title="Experience Recommendation",
                status="missing",
                warnings=("Experience recommendation is unavailable.",),
            )
        experience_type = getattr(experience, "experience_type", None)
        return CreatorReviewSection(
            title="Experience Recommendation",
            summary=getattr(experience, "suggested_name", None),
            confidence=self._float_or_none(getattr(experience, "confidence", None)),
            data={
                "experience_type": getattr(
                    experience_type,
                    "value",
                    experience_type,
                ),
                "asset_ids": tuple(getattr(experience, "asset_ids", ()) or ()),
                "suggested_summary": getattr(experience, "suggested_summary", None),
                "suggested_cover_asset_id": getattr(
                    experience,
                    "suggested_cover_asset_id",
                    None,
                ),
            },
            evidence=self._evidence(getattr(experience, "evidence", ()) or ()),
        )

    def _product_strategy_section(
        self,
        product_strategy: Any | None,
    ) -> CreatorReviewSection:
        if product_strategy is None:
            return CreatorReviewSection(
                title="Product Strategy",
                status="missing",
                warnings=("Product Strategy recommendation is unavailable.",),
            )

        recommendations = tuple(
            getattr(product_strategy, "recommendations", ()) or ()
        )
        catalog = getattr(product_strategy, "catalog_recommendation", None)
        catalog_products = tuple(
            getattr(catalog, "recommended_products", ()) or ()
        )
        recommended_products = catalog_products or recommendations
        recommendation_types = tuple(
            getattr(recommendation, "recommendation_type", None)
            for recommendation in recommended_products
            if getattr(recommendation, "recommendation_type", None)
        )
        return CreatorReviewSection(
            title="Product Strategy",
            status="available" if recommended_products else "missing",
            summary=self._product_strategy_summary(recommended_products),
            confidence=self._float_or_none(
                getattr(product_strategy, "confidence", None)
            ),
            data={
                "source_type": getattr(product_strategy, "source_type", None),
                "source_id": getattr(product_strategy, "source_id", None),
                "catalog_recommendation": self._catalog_strategy_data(catalog),
                "recommended_product_types": recommendation_types,
                "recommended_products": tuple(
                    self._product_strategy_recommendation_data(recommendation)
                    for recommendation in recommended_products
                ),
                "recommendation_rationale": tuple(
                    getattr(product_strategy, "rationale", ()) or ()
                ),
                "ownership": {
                    "product_strategy_owner": "ProductStrategyService",
                    "creator_review_owner": "CreatorReviewService",
                },
            },
            evidence=self._evidence(getattr(product_strategy, "evidence", ()) or ()),
            warnings=()
            if recommended_products
            else ("Product Strategy has no recommended Products.",),
        )

    @staticmethod
    def _product_strategy_summary(recommendations: tuple[Any, ...]) -> str | None:
        if not recommendations:
            return None
        return (
            f"{len(recommendations)} Product Strategy recommendation(s) "
            "ready for creator review."
        )

    def _catalog_strategy_data(self, catalog: Any | None) -> dict[str, Any]:
        if catalog is None:
            return {}
        return {
            "associated_experience_id": getattr(
                catalog,
                "associated_experience_id",
                None,
            ),
            "associated_experience_type": getattr(
                catalog,
                "associated_experience_type",
                None,
            ),
            "confidence": self._float_or_none(
                getattr(catalog, "confidence", None)
            ),
            "rationale": tuple(getattr(catalog, "rationale", ()) or ()),
        }

    def _product_strategy_recommendation_data(
        self,
        recommendation: Any,
    ) -> dict[str, Any]:
        composition = getattr(recommendation, "composition", None)
        return {
            "recommendation_type": getattr(
                recommendation,
                "recommendation_type",
                None,
            ),
            "source_type": getattr(recommendation, "source_type", None),
            "source_id": getattr(recommendation, "source_id", None),
            "asset_ids": tuple(getattr(recommendation, "asset_ids", ()) or ()),
            "confidence": self._float_or_none(
                getattr(recommendation, "confidence", None)
            ),
            "rationale": tuple(getattr(recommendation, "rationale", ()) or ()),
            "composition": self._composition_strategy_data(composition),
        }

    @staticmethod
    def _composition_strategy_data(composition: Any | None) -> dict[str, Any]:
        if composition is None:
            return {}
        return {
            "composition_type": getattr(composition, "composition_type", None),
            "included_asset_ids": tuple(
                getattr(composition, "included_asset_ids", ()) or ()
            ),
            "asset_order": tuple(getattr(composition, "asset_order", ()) or ()),
            "cover_asset_id": getattr(composition, "cover_asset_id", None),
            "experience_id": getattr(composition, "experience_id", None),
            "relationship_type": getattr(composition, "relationship_type", None),
            "related_recommendation_types": tuple(
                getattr(composition, "related_recommendation_types", ()) or ()
            ),
            "rationale": tuple(getattr(composition, "rationale", ()) or ()),
        }

    def _commerce_strategy_section(
        self,
        commerce_strategy: Any | None,
    ) -> CreatorReviewSection:
        if commerce_strategy is None:
            return CreatorReviewSection(
                title="Commerce Strategy",
                status="missing",
                warnings=("Commerce Strategy recommendation is unavailable.",),
            )

        recommendations = tuple(
            getattr(commerce_strategy, "recommendations", ()) or ()
        )
        recommendation_types = tuple(
            getattr(recommendation, "recommendation_type", None)
            for recommendation in recommendations
            if getattr(recommendation, "recommendation_type", None)
        )
        customer_journeys = tuple(
            self._customer_journey_data(
                getattr(recommendation, "customer_journey", None)
            )
            for recommendation in recommendations
            if getattr(recommendation, "customer_journey", None) is not None
        )
        return CreatorReviewSection(
            title="Commerce Strategy",
            status="available" if recommendations else "missing",
            summary=self._commerce_strategy_summary(recommendations),
            confidence=self._float_or_none(
                getattr(commerce_strategy, "confidence", None)
            ),
            data={
                "source_type": getattr(commerce_strategy, "source_type", None),
                "source_id": getattr(commerce_strategy, "source_id", None),
                "recommendation_types": recommendation_types,
                "commerce_recommendations": tuple(
                    self._commerce_strategy_recommendation_data(recommendation)
                    for recommendation in recommendations
                ),
                "marketing_recommendations": tuple(
                    self._commerce_strategy_recommendation_data(recommendation)
                    for recommendation in recommendations
                    if getattr(recommendation, "recommendation_type", None)
                    in {
                        "best_teaser",
                        "best_first_offer",
                        "best_follow_up",
                        "best_upsell",
                        "cross_sell_opportunity",
                        "offer_sequencing",
                    }
                ),
                "customer_journey_recommendations": customer_journeys,
                "relationship_stages": self._unique_values(
                    item.get("journey_stage")
                    for item in customer_journeys
                    if item.get("journey_stage")
                ),
                "conversation_objectives": tuple(
                    getattr(recommendation, "recommended_objective", None)
                    for recommendation in recommendations
                    if getattr(recommendation, "recommendation_type", None)
                    == "conversation_objective"
                ),
                "offer_sequencing": tuple(
                    getattr(recommendation, "recommended_objective", None)
                    for recommendation in recommendations
                    if getattr(recommendation, "recommendation_type", None)
                    == "offer_sequencing"
                ),
                "recommendation_rationale": tuple(
                    getattr(commerce_strategy, "rationale", ()) or ()
                ),
                "ownership": {
                    "commerce_strategy_owner": "CommerceStrategyService",
                    "creator_review_owner": "CreatorReviewService",
                    "runtime_owner": "DecisionEngine",
                    "telegram_owner": "TelegramCommerceService",
                },
            },
            evidence=self._evidence(
                getattr(commerce_strategy, "evidence", ()) or ()
            ),
            warnings=()
            if recommendations
            else ("Commerce Strategy has no recommendations.",),
        )

    @staticmethod
    def _commerce_strategy_summary(recommendations: tuple[Any, ...]) -> str | None:
        if not recommendations:
            return None
        return (
            f"{len(recommendations)} Commerce Strategy recommendation(s) "
            "ready for creator review."
        )

    def _commerce_strategy_recommendation_data(
        self,
        recommendation: Any,
    ) -> dict[str, Any]:
        return {
            "recommendation_type": getattr(
                recommendation,
                "recommendation_type",
                None,
            ),
            "source_type": getattr(recommendation, "source_type", None),
            "source_id": getattr(recommendation, "source_id", None),
            "recommended_objective": getattr(
                recommendation,
                "recommended_objective",
                None,
            ),
            "customer_journey": self._customer_journey_data(
                getattr(recommendation, "customer_journey", None)
            ),
            "confidence": self._float_or_none(
                getattr(recommendation, "confidence", None)
            ),
            "rationale": tuple(getattr(recommendation, "rationale", ()) or ()),
            "metadata": dict(getattr(recommendation, "metadata", {}) or {}),
        }

    def _customer_journey_data(self, customer_journey: Any | None) -> dict[str, Any]:
        if customer_journey is None:
            return {}
        return {
            "journey_stage": getattr(customer_journey, "journey_stage", None),
            "recommended_objective": getattr(
                customer_journey,
                "recommended_objective",
                None,
            ),
            "suggested_progression": getattr(
                customer_journey,
                "suggested_progression",
                None,
            ),
            "confidence": self._float_or_none(
                getattr(customer_journey, "confidence", None)
            ),
            "rationale": tuple(getattr(customer_journey, "rationale", ()) or ()),
            "evidence": self._evidence(
                getattr(customer_journey, "evidence", ()) or ()
            ),
            "metadata": dict(getattr(customer_journey, "metadata", {}) or {}),
        }

    def _commerce_section(self, commerce: Any | None) -> CreatorReviewSection:
        if commerce is None:
            return CreatorReviewSection(
                title="Commerce Recommendation",
                status="missing",
                warnings=("Commerce recommendation is unavailable.",),
            )
        product_type = getattr(commerce, "product_type", None)
        price = getattr(commerce, "price", None)
        return CreatorReviewSection(
            title="Commerce Recommendation",
            summary=getattr(commerce, "suggested_name", None),
            confidence=self._float_or_none(getattr(commerce, "confidence", None)),
            data={
                "source_type": getattr(commerce, "source_type", None),
                "source_id": getattr(commerce, "source_id", None),
                "asset_ids": tuple(getattr(commerce, "asset_ids", ()) or ()),
                "product_type": getattr(product_type, "value", product_type),
                "suggested_description": getattr(
                    commerce,
                    "suggested_description",
                    None,
                ),
                "suggested_tags": tuple(
                    getattr(commerce, "suggested_tags", ()) or ()
                ),
                "suggested_themes": tuple(
                    getattr(commerce, "suggested_themes", ()) or ()
                ),
                "suggested_keywords": tuple(
                    getattr(commerce, "suggested_keywords", ()) or ()
                ),
                "price": {
                    "suggested_price_cents": getattr(
                        price,
                        "suggested_price_cents",
                        None,
                    ),
                    "min_price_cents": getattr(price, "min_price_cents", None),
                    "max_price_cents": getattr(price, "max_price_cents", None),
                    "currency": getattr(price, "currency", None),
                    "pricing_rule": getattr(price, "pricing_rule", None),
                }
                if price
                else None,
            },
            evidence=self._evidence(getattr(commerce, "evidence", ()) or ()),
        )

    def _product_draft_section(
        self,
        product_draft: Any | None,
    ) -> CreatorReviewSection:
        if not product_draft:
            return CreatorReviewSection(
                title="Product Draft",
                status="missing",
                warnings=("Product Draft is unavailable or deferred.",),
            )
        data = self._product_draft_data(product_draft)
        success = data.get("success")
        return CreatorReviewSection(
            title="Product Draft",
            status="available" if success is not False else "requires_attention",
            summary=self._product_draft_summary(data),
            data=data,
            warnings=()
            if success is not False
            else (data.get("error") or data.get("reason") or "Product Draft failed.",),
        )

    @staticmethod
    def _product_draft_data(product_draft: Any) -> dict[str, Any]:
        if isinstance(product_draft, Mapping):
            return dict(product_draft)
        product = getattr(product_draft, "product", None)
        return {
            "success": True,
            "created": getattr(product_draft, "created", None),
            "updated": getattr(product_draft, "updated", None),
            "activated": getattr(product_draft, "activated", None),
            "product_id": str(getattr(product, "id", ""))
            if product is not None
            else None,
            "product_type": getattr(
                getattr(product, "product_type", None),
                "value",
                getattr(product, "product_type", None),
            ),
            "delivery_type": getattr(
                getattr(product, "delivery_type", None),
                "value",
                getattr(product, "delivery_type", None),
            ),
            "status": getattr(
                getattr(product, "status", None),
                "value",
                getattr(product, "status", None),
            ),
            "price_cents": getattr(product, "price_cents", None),
        }

    @staticmethod
    def _product_draft_summary(data: Mapping[str, Any]) -> str | None:
        product_id = data.get("product_id")
        if product_id:
            return f"Product Draft {product_id} is ready for review."
        reason = data.get("reason")
        if reason:
            return str(reason)
        return "Product Draft is ready for review."

    def _delivery_section(
        self,
        commerce: Any | None,
        organization: Any | None,
    ) -> CreatorReviewSection:
        delivery_type = None
        if commerce is not None:
            commerce_delivery = getattr(commerce, "delivery_type", None)
            delivery_type = getattr(commerce_delivery, "value", commerce_delivery)
        if delivery_type is None and organization is not None:
            delivery_type = getattr(organization, "delivery_type", None)
        return CreatorReviewSection(
            title="Delivery Type",
            status="available" if delivery_type else "missing",
            summary=str(delivery_type) if delivery_type else None,
            data={"delivery_type": delivery_type},
            warnings=()
            if delivery_type
            else ("Delivery Type recommendation is unavailable.",),
        )

    @staticmethod
    def _publishing_section(
        publishing: Mapping[str, Any],
    ) -> CreatorReviewSection:
        if not publishing:
            return CreatorReviewSection(
                title="Publishing Readiness",
                status="missing",
                warnings=("Publishing readiness is unavailable.",),
            )
        return CreatorReviewSection(
            title="Publishing Readiness",
            status=str(publishing.get("status") or "available"),
            summary=publishing.get("detail") or publishing.get("status"),
            data=dict(publishing),
        )

    @staticmethod
    def _organization_section(
        organization: Any | None,
    ) -> CreatorReviewSection:
        if organization is None:
            return CreatorReviewSection(
                title="Organization",
                status="missing",
                warnings=("Automatic organization is unavailable.",),
            )
        return CreatorReviewSection(
            title="Organization",
            status="available",
            summary=getattr(organization, "organization_type", None),
            data={
                "asset_ids": tuple(getattr(organization, "asset_ids", ()) or ()),
                "organization_type": getattr(
                    organization,
                    "organization_type",
                    None,
                ),
                "asset_library_visible": getattr(
                    organization,
                    "asset_library_visible",
                    False,
                ),
                "local_vault_owned": getattr(
                    organization,
                    "local_vault_owned",
                    False,
                ),
                "relationship_chain": tuple(
                    getattr(organization, "relationship_chain", ()) or ()
                ),
                "notes": tuple(getattr(organization, "notes", ()) or ()),
            },
            warnings=tuple(getattr(organization, "notes", ()) or ()),
        )

    def _warnings(
        self,
        workflow_result: Any,
        *,
        asset_results: tuple[Any, ...],
        organization: Any | None,
        product_draft: Any | None,
        publishing_readiness: Mapping[str, Any],
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if not getattr(workflow_result, "success", False):
            warnings.append("Import workflow did not complete successfully.")
        for result in asset_results:
            legacy_result = getattr(result, "legacy_result", {}) or {}
            if legacy_result.get("error"):
                warnings.append(str(legacy_result["error"]))
        if organization is not None:
            warnings.extend(str(note) for note in getattr(organization, "notes", ()))
        if product_draft:
            product_data = self._product_draft_data(product_draft)
            if product_data.get("success") is False:
                warnings.append(
                    str(
                        product_data.get("error")
                        or product_data.get("reason")
                        or "Product Draft requires attention."
                    )
                )
        else:
            warnings.append("Product Draft is unavailable or deferred.")
        status = str(publishing_readiness.get("status") or "").lower()
        if status in {"missing", "partial", "requires_attention"}:
            warnings.append(
                str(
                    publishing_readiness.get("detail")
                    or publishing_readiness.get("status")
                    or "Publishing readiness requires attention."
                )
            )
        return tuple(dict.fromkeys(warnings))

    @staticmethod
    def _evidence(values: Iterable[Any]) -> tuple[Mapping[str, Any], ...]:
        result = []
        for item in values:
            result.append(
                {
                    "reason": getattr(item, "reason", None),
                    "detail": getattr(item, "detail", None),
                    "weight": getattr(item, "weight", None),
                }
            )
        return tuple(result)

    @staticmethod
    def _average(values: Iterable[float | None]) -> float | None:
        numbers = [value for value in values if value is not None]
        if not numbers:
            return None
        return round(sum(numbers) / len(numbers), 4)

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        return float(value) if value is not None else None
