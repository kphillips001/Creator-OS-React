"""Canonical Commerce Strategy boundary for Creator OS.

CommerceStrategyService owns reusable commerce strategy recommendations only.
It does not execute conversations, deliver Products, call Telegram APIs, mutate
Publishing, persist Products, or orchestrate DecisionEngine behavior.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.models.business_learning import LearningContext
from app.models.commerce_intelligence import CommerceRecommendation
from app.models.commerce_strategy import (
    CommerceStrategyEvidence,
    CommerceStrategyRecommendation,
    CommerceStrategyResult,
    CustomerJourneyRecommendation,
)
from app.models.content_intelligence import ContentIntelligence
from app.models.experience_intelligence import ExperienceRecommendation
from app.models.product_strategy import (
    ProductStrategyRecommendation,
    ProductStrategyResult,
)


class CommerceStrategyService:
    """Build provider-neutral Commerce Strategy recommendations."""

    def recommend(
        self,
        *,
        creator_intent: Mapping[str, Any] | None = None,
        product_strategy_result: ProductStrategyResult | None = None,
        content_intelligence: ContentIntelligence | None = None,
        content_intelligences: Iterable[ContentIntelligence] | None = None,
        experience_context: ExperienceRecommendation | None = None,
        commerce_intelligence: CommerceRecommendation | None = None,
        learning_context: LearningContext | None = None,
    ) -> CommerceStrategyResult:
        records = self._content_records(
            content_intelligence,
            content_intelligences,
        )
        source_type = self._source_type(
            product_strategy_result,
            experience_context,
            records,
        )
        source_id = self._source_id(
            product_strategy_result,
            experience_context,
            records,
        )
        evidence = self._evidence(
            creator_intent=creator_intent,
            product_strategy_result=product_strategy_result,
            records=records,
            experience_context=experience_context,
            commerce_intelligence=commerce_intelligence,
            learning_context=learning_context,
        )
        recommendations = self._recommendations(
            source_type=source_type,
            source_id=source_id,
            evidence=evidence,
            product_strategy_result=product_strategy_result,
            commerce_intelligence=commerce_intelligence,
        )
        confidence = self._confidence(recommendations)
        return CommerceStrategyResult(
            source_type=source_type,
            source_id=source_id,
            recommendations=recommendations,
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
                "source": "commerce_strategy",
                "owner": "CommerceStrategyService",
                "executes_conversations": False,
                "delivers_products": False,
                "modifies_decision_engine": False,
                "modifies_publishing": False,
                "modifies_telegram": False,
                "persists_products": False,
                "new_ai_analysis": False,
                "product_strategy_consumed": product_strategy_result is not None,
                "commerce_intelligence_consumed": commerce_intelligence is not None,
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
        evidence: tuple[CommerceStrategyEvidence, ...],
        product_strategy_result: ProductStrategyResult | None,
        commerce_intelligence: CommerceRecommendation | None,
    ) -> tuple[CommerceStrategyRecommendation, ...]:
        if not evidence:
            return ()

        product_recommendations = self._product_strategy_recommendations(
            product_strategy_result
        )
        recommendation_type = self._recommendation_type(
            product_strategy_result,
            commerce_intelligence,
        )
        confidence = self._recommendation_confidence(evidence)
        rationale = tuple(item.detail for item in evidence if item.detail)
        if not product_recommendations:
            return (
                self._strategy_recommendation(
                    recommendation_type=recommendation_type,
                    recommended_objective="Prepare reusable commerce guidance.",
                    source_type=source_type,
                    source_id=source_id,
                    confidence=confidence,
                    rationale=rationale,
                    evidence=evidence,
                    product_recommendation=None,
                ),
            )

        recommendations = []
        for product_recommendation in product_recommendations:
            for strategy_type, objective in self._strategy_types(
                product_recommendation
            ):
                recommendations.append(
                    self._strategy_recommendation(
                        recommendation_type=strategy_type,
                        recommended_objective=objective,
                        source_type=source_type,
                        source_id=source_id,
                        confidence=confidence,
                        rationale=rationale,
                        evidence=evidence,
                        product_recommendation=product_recommendation,
                    )
                )
        return tuple(recommendations)

    def _strategy_recommendation(
        self,
        *,
        recommendation_type: str,
        recommended_objective: str,
        source_type: str,
        source_id: str | None,
        confidence: float,
        rationale: tuple[Any, ...],
        evidence: tuple[CommerceStrategyEvidence, ...],
        product_recommendation: ProductStrategyRecommendation | None,
    ) -> CommerceStrategyRecommendation:
        product_type = getattr(product_recommendation, "recommendation_type", None)
        composition = getattr(product_recommendation, "composition", None)
        return CommerceStrategyRecommendation(
            recommendation_type=recommendation_type,
            source_type=source_type,
            source_id=source_id,
            recommended_objective=recommended_objective,
            customer_journey=self._customer_journey(
                recommendation_type=recommendation_type,
                recommended_objective=recommended_objective,
                product_type=str(product_type or ""),
                confidence=confidence,
                rationale=rationale,
                evidence=evidence,
            ),
            confidence=confidence,
            rationale=tuple(str(item) for item in rationale),
            evidence=evidence,
            metadata={
                "source": "commerce_strategy",
                "owner": "CommerceStrategyService",
                "pricing_owner": "CommerceIntelligenceService",
                "delivery_type_owner": "CommerceIntelligenceService",
                "publishing_readiness_owner": "CommerceIntelligenceService",
                "product_strategy_owner": "ProductStrategyService",
                "runtime_owner": "TelegramCommerceService",
                "decision_owner": "DecisionEngine",
                "product_recommendation_type": product_type,
                "composition_type": getattr(composition, "composition_type", None),
                "runtime_action": False,
                "telegram_specific": False,
                "contains_pricing": False,
                "contains_delivery_type": False,
                "contains_publishing_readiness": False,
                "tracks_customer_state": False,
                "contains_customer_memory": False,
            },
        )

    def _customer_journey(
        self,
        *,
        recommendation_type: str,
        recommended_objective: str,
        product_type: str,
        confidence: float,
        rationale: tuple[Any, ...],
        evidence: tuple[CommerceStrategyEvidence, ...],
    ) -> CustomerJourneyRecommendation:
        return CustomerJourneyRecommendation(
            journey_stage=self._journey_stage(product_type),
            recommended_objective=recommended_objective,
            suggested_progression=self._suggested_progression(
                product_type,
                recommendation_type,
            ),
            confidence=confidence,
            rationale=tuple(str(item) for item in rationale),
            evidence=evidence,
            metadata={
                "source": "commerce_strategy",
                "owner": "CommerceStrategyService",
                "customer_state_owner": "Customer Intelligence",
                "decision_owner": "DecisionEngine",
                "tracks_customer_state": False,
                "contains_customer_memory": False,
                "runtime_action": False,
            },
        )

    @staticmethod
    def _product_strategy_recommendations(
        product_strategy_result: ProductStrategyResult | None,
    ) -> tuple[ProductStrategyRecommendation, ...]:
        recommendations = getattr(product_strategy_result, "recommendations", None)
        if recommendations:
            return tuple(item for item in recommendations if item is not None)

        catalog = getattr(product_strategy_result, "catalog_recommendation", None)
        catalog_recommendations = getattr(catalog, "recommended_products", None)
        if catalog_recommendations:
            return tuple(item for item in catalog_recommendations if item is not None)
        return ()

    @classmethod
    def _strategy_types(
        cls,
        product_recommendation: ProductStrategyRecommendation,
    ) -> tuple[tuple[str, str], ...]:
        product_type = str(
            getattr(product_recommendation, "recommendation_type", "")
        ).lower()
        values = [
            (
                "relationship_stage",
                cls._relationship_stage_objective(product_type),
            ),
            (
                "conversation_objective",
                cls._conversation_objective(product_type),
            ),
            (
                "offer_sequencing",
                cls._offer_sequence_objective(product_type),
            ),
            (
                "customer_progression",
                cls._customer_progression_objective(product_type),
            ),
        ]
        if product_type == "free_preview":
            values.extend(
                [
                    (
                        "continue_relationship_building",
                        "Use this recommendation to deepen interest before selling.",
                    ),
                    (
                        "delay_selling",
                        "Use this recommendation when the relationship needs more warm-up.",
                    ),
                    (
                        "best_teaser",
                        "Use this recommendation to open interest before a paid offer.",
                    ),
                    (
                        "best_follow_up",
                        "Follow up by connecting the preview to a related premium product.",
                    ),
                ]
            )
        elif product_type in {"bundle", "collection", "vip_collection"}:
            values.extend(
                [
                    (
                        "introduce_product",
                        "Introduce this recommendation after product interest is clear.",
                    ),
                    (
                        "increase_sales_pressure",
                        "Use this recommendation when customer intent supports a stronger offer.",
                    ),
                    (
                        "best_upsell",
                        "Position this recommendation as a higher-value next step.",
                    ),
                    (
                        "cross_sell_opportunity",
                        "Use this recommendation alongside related Experience products.",
                    ),
                ]
            )
        else:
            values.extend(
                [
                    (
                        "introduce_product",
                        "Introduce this recommendation once content interest is established.",
                    ),
                    (
                        "best_first_offer",
                        "Introduce this recommendation as the first paid offer.",
                    ),
                    (
                        "best_follow_up",
                        "Follow up with a related bundle or collection when available.",
                    ),
                ]
            )
        return tuple(values)

    @staticmethod
    def _relationship_stage_objective(product_type: str) -> str:
        if product_type == "free_preview":
            return "Place this recommendation in the trust-building stage."
        if product_type in {"bundle", "collection", "vip_collection"}:
            return "Place this recommendation in the expansion stage."
        if product_type in {"story_product", "photoshoot_product"}:
            return "Place this recommendation in the Experience engagement stage."
        return "Place this recommendation in the first-offer stage."

    @staticmethod
    def _customer_progression_objective(product_type: str) -> str:
        if product_type == "free_preview":
            return "Progress the customer from awareness to qualified interest."
        if product_type in {"bundle", "collection", "vip_collection"}:
            return "Progress the customer from purchase intent to higher-value interest."
        if product_type in {"story_product", "photoshoot_product"}:
            return "Progress the customer through the Experience before escalating."
        return "Progress the customer from interest to first purchase intent."

    @staticmethod
    def _conversation_objective(product_type: str) -> str:
        if product_type == "free_preview":
            return "Build interest and qualify whether the customer wants more."
        if product_type in {"bundle", "collection", "vip_collection"}:
            return "Move an interested customer toward a larger-value offer."
        if product_type in {"story_product", "photoshoot_product"}:
            return "Continue the Experience arc while preparing a premium offer."
        return "Introduce a clear provider-neutral commerce opportunity."

    @staticmethod
    def _offer_sequence_objective(product_type: str) -> str:
        if product_type == "free_preview":
            return "Sequence before paid recommendations as the teaser step."
        if product_type in {"bundle", "collection", "vip_collection"}:
            return "Sequence after single or teaser recommendations as an upsell."
        if product_type in {"story_product", "photoshoot_product"}:
            return "Sequence after Experience interest has been established."
        return "Sequence after rapport or content interest is visible."

    @staticmethod
    def _journey_stage(product_type: str) -> str:
        normalized = product_type.lower()
        if normalized == "free_preview":
            return "relationship_building"
        if normalized in {"bundle", "collection", "vip_collection"}:
            return "expansion"
        if normalized in {"story_product", "photoshoot_product"}:
            return "experience_engagement"
        if normalized:
            return "first_offer"
        return "strategy_planning"

    @staticmethod
    def _suggested_progression(product_type: str, recommendation_type: str) -> str:
        normalized = product_type.lower()
        if recommendation_type == "delay_selling":
            return "Continue relationship building before introducing paid products."
        if recommendation_type == "increase_sales_pressure":
            return "Escalate only after clear interest or buying intent is present."
        if normalized == "free_preview":
            return "Move from trust-building to a relevant first paid offer."
        if normalized in {"bundle", "collection", "vip_collection"}:
            return "Move from first purchase intent to a larger-value offer."
        if normalized in {"story_product", "photoshoot_product"}:
            return "Move through the Experience arc toward premium interest."
        if normalized:
            return "Move from content interest to a simple first offer."
        return "Use existing context to prepare future customer progression guidance."

    @staticmethod
    def _recommendation_type(
        product_strategy_result: ProductStrategyResult | None,
        commerce_intelligence: CommerceRecommendation | None,
    ) -> str:
        catalog = getattr(product_strategy_result, "catalog_recommendation", None)
        if catalog is not None:
            return "product_catalog_commerce_strategy"
        if product_strategy_result is not None:
            return "product_recommendation_commerce_strategy"
        if commerce_intelligence is not None:
            return "commerce_intelligence_strategy"
        return "commerce_strategy_candidate"

    @staticmethod
    def _content_records(
        content_intelligence: ContentIntelligence | None,
        content_intelligences: Iterable[ContentIntelligence] | None,
    ) -> tuple[ContentIntelligence, ...]:
        records = []
        if content_intelligence is not None:
            records.append(content_intelligence)
        if content_intelligences is not None:
            records.extend(item for item in content_intelligences if item is not None)
        return tuple(records)

    @staticmethod
    def _source_type(
        product_strategy_result: ProductStrategyResult | None,
        experience_context: ExperienceRecommendation | None,
        records: tuple[ContentIntelligence, ...],
    ) -> str:
        value = getattr(product_strategy_result, "source_type", None)
        if value:
            return str(value)
        if experience_context is not None:
            return "experience"
        if records:
            return "content"
        return "commerce"

    @classmethod
    def _source_id(
        cls,
        product_strategy_result: ProductStrategyResult | None,
        experience_context: ExperienceRecommendation | None,
        records: tuple[ContentIntelligence, ...],
    ) -> str | None:
        value = getattr(product_strategy_result, "source_id", None)
        if value is not None:
            return str(value)

        for name in ("experience_id", "id"):
            value = getattr(experience_context, name, None)
            if value is not None:
                return str(value)

        asset_ids = cls._asset_ids(records)
        if len(asset_ids) == 1:
            return str(asset_ids[0])
        if asset_ids:
            return ",".join(str(asset_id) for asset_id in asset_ids)
        return None

    @staticmethod
    def _asset_ids(records: tuple[ContentIntelligence, ...]) -> tuple[int, ...]:
        values = []
        for record in records:
            asset_id = getattr(record, "asset_id", None)
            if asset_id is None:
                identity = getattr(record, "identity", None)
                asset_id = getattr(identity, "asset_id", None)
            if asset_id is None:
                continue
            try:
                values.append(int(asset_id))
            except (TypeError, ValueError):
                continue
        return tuple(dict.fromkeys(values))

    def _evidence(
        self,
        *,
        creator_intent: Mapping[str, Any] | None,
        product_strategy_result: ProductStrategyResult | None,
        records: tuple[ContentIntelligence, ...],
        experience_context: ExperienceRecommendation | None,
        commerce_intelligence: CommerceRecommendation | None,
        learning_context: LearningContext | None,
    ) -> tuple[CommerceStrategyEvidence, ...]:
        evidence = []
        if creator_intent:
            evidence.append(
                CommerceStrategyEvidence(
                    reason="creator_intent",
                    detail="Creator intent is available for strategy context.",
                    weight=10,
                )
            )
        if product_strategy_result is not None:
            evidence.append(
                CommerceStrategyEvidence(
                    reason="product_strategy",
                    detail="Product Strategy recommendations are available.",
                    weight=30,
                )
            )
        if records:
            evidence.append(
                CommerceStrategyEvidence(
                    reason="content_intelligence",
                    detail="Content Intelligence is available.",
                    weight=min(20, 5 + len(records) * 5),
                )
            )
        if experience_context is not None:
            evidence.append(
                CommerceStrategyEvidence(
                    reason="experience_context",
                    detail="Experience context is available.",
                    weight=20,
                )
            )
        if commerce_intelligence is not None:
            evidence.append(
                CommerceStrategyEvidence(
                    reason="commerce_intelligence",
                    detail=(
                        "Commerce Intelligence pricing, Delivery Type, and "
                        "publishing readiness context is available."
                    ),
                    weight=25,
                )
            )
        if learning_context is not None:
            evidence.append(
                CommerceStrategyEvidence(
                    reason="learning_context",
                    detail="Business Learning evidence is available.",
                    weight=5,
                )
            )
        return tuple(evidence)

    @staticmethod
    def _recommendation_confidence(
        evidence: tuple[CommerceStrategyEvidence, ...],
    ) -> float:
        if not evidence:
            return 0.0
        return round(min(0.95, sum(item.weight for item in evidence) / 100), 2)

    @staticmethod
    def _confidence(
        recommendations: tuple[CommerceStrategyRecommendation, ...],
    ) -> float:
        if not recommendations:
            return 0.0
        return round(
            sum(item.confidence for item in recommendations) / len(recommendations),
            2,
        )
