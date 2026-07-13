"""Canonical Business Learning boundary for Creator OS.

BusinessLearningService owns provider-neutral learning read models. It does not
make decisions, execute commerce, mutate strategy, call provider APIs, or
replace existing runtime behavior.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.models.business_learning import (
    BusinessLearningReview,
    BusinessLearningReviewSummary,
    BusinessLearningSnapshot,
    BusinessOutcome,
    BusinessOutcomeType,
    BusinessPerformanceSummary,
    LearningContext,
    LearningInsight,
    LearningMetadata,
    LearningRecommendation,
    LearningSummary,
    PerformanceEvidence,
    PerformanceMetric,
    PerformanceSnapshot,
    RecommendationEvidence,
)

BusinessOutcomeInput = (
    BusinessLearningSnapshot
    | BusinessOutcome
    | Iterable[BusinessOutcome | Mapping[str, Any]]
    | Mapping[str, Any]
    | None
)
RecommendationEvidenceInput = (
    RecommendationEvidence
    | Iterable[RecommendationEvidence]
    | None
)
LearningInsightInput = LearningInsight | Iterable[LearningInsight] | None
LearningRecommendationInput = (
    LearningRecommendation | Iterable[LearningRecommendation] | None
)


class BusinessLearningService:
    """Build provider-neutral business learning read models."""

    def __init__(
        self,
        *,
        learning_repository: Any | None = None,
        content_commerce_learning_service: Any | None = None,
    ) -> None:
        self.learning_repository = learning_repository
        self.content_commerce_learning_service = content_commerce_learning_service

    def _content_commerce_learning(self) -> Any | None:
        if self.content_commerce_learning_service is not None:
            return self.content_commerce_learning_service
        try:
            from app.repositories.content_commerce_learning_repository import (
                ContentCommerceLearningRepository,
            )
            from app.services.content_commerce_learning_service import (
                ContentCommerceLearningService,
            )

            repository = self.learning_repository or ContentCommerceLearningRepository()
            self.content_commerce_learning_service = ContentCommerceLearningService(
                repository=repository,
                business_learning_service=self,
            )
            return self.content_commerce_learning_service
        except Exception:
            return None

    def record_business_outcome(
        self,
        outcome: BusinessOutcome | Mapping[str, Any],
    ) -> dict[str, Any]:
        """Persist one normalized Business Outcome idempotently."""

        normalized = self.normalize_business_outcomes(outcome)
        if not normalized:
            return {"success": False, "reason": "invalid_business_outcome"}
        service = self._content_commerce_learning()
        if service is None:
            return {"success": False, "reason": "learning_history_unavailable"}
        return service.record_business_outcome(normalized[0])

    def record_outcome(
        self,
        outcome: BusinessOutcome | Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.record_business_outcome(outcome)

    def build_runtime_learning_context(
        self,
        *,
        request: Any | None = None,
        creator_profile_id: int | None = None,
        customer_context: Mapping[str, Any] | None = None,
        conversation_context: Mapping[str, Any] | None = None,
    ) -> Any | None:
        """Return the current content-commerce learning context when available."""

        service = self._content_commerce_learning()
        if service is None:
            return None
        return service.build_runtime_learning_context(
            request=request,
            creator_profile_id=creator_profile_id,
            customer_context=customer_context,
            conversation_context=conversation_context,
        )

    def get_asset_learning_profile(self, asset_id: int | str) -> Any | None:
        service = self._content_commerce_learning()
        if service is None:
            return None
        return service.get_asset_learning_profile(asset_id)

    def list_asset_learning_profiles(self) -> tuple[Any, ...]:
        service = self._content_commerce_learning()
        if service is None:
            return ()
        return service.list_asset_learning_profiles()

    def list_top_performers(self, *, limit: int = 10) -> tuple[Any, ...]:
        service = self._content_commerce_learning()
        if service is None:
            return ()
        return service.list_top_performers(limit=limit)

    def list_underperformers(self, *, limit: int = 10) -> tuple[Any, ...]:
        service = self._content_commerce_learning()
        if service is None:
            return ()
        return service.list_underperformers(limit=limit)

    def build_learning_snapshot(
        self,
        *,
        outcomes: BusinessOutcomeInput = None,
        recommendation_context: LearningContext | Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> BusinessLearningSnapshot:
        normalized_outcomes = self.normalize_business_outcomes(outcomes)
        performance = self.summarize_business_performance(normalized_outcomes)
        performance_snapshot = self.build_performance_snapshot(
            outcomes=normalized_outcomes
        )
        evidence = self.build_recommendation_evidence(
            outcomes=normalized_outcomes,
            recommendation_context=recommendation_context,
        )
        learning_insights = self.generate_learning_insights(
            outcomes=normalized_outcomes,
            performance_snapshot=performance_snapshot,
            recommendation_evidence=evidence,
        )
        learning_recommendations = self.generate_recommendation_evidence(
            outcomes=normalized_outcomes,
            learning_insights=learning_insights,
            recommendation_evidence=evidence,
        )
        return BusinessLearningSnapshot(
            outcomes=normalized_outcomes,
            outcome_categories=self.categorize_outcomes(normalized_outcomes),
            outcome_summary=self.summarize_business_outcomes(normalized_outcomes),
            performance_summary=performance,
            performance_snapshot=performance_snapshot,
            recommendation_evidence=evidence,
            learning_insights=learning_insights,
            learning_recommendations=learning_recommendations,
            learning_intelligence_summary=self.generate_learning_summary(
                learning_insights=learning_insights,
                learning_recommendations=learning_recommendations,
            ),
            learning_summary=self.summarize_learning(
                outcomes=normalized_outcomes,
                performance_summary=performance,
                recommendation_evidence=evidence,
            ),
            metadata=LearningMetadata(metadata=dict(metadata or {})),
        )

    def build_outcome_snapshot(
        self,
        *,
        outcomes: BusinessOutcomeInput = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> BusinessLearningSnapshot:
        return self.build_learning_snapshot(outcomes=outcomes, metadata=metadata)

    def build_learning_context(
        self,
        *,
        outcomes: BusinessOutcomeInput = None,
        snapshot: BusinessLearningSnapshot | None = None,
        context_type: str = "unified_learning",
        subject_reference: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LearningContext:
        resolved = snapshot or self.build_learning_snapshot(outcomes=outcomes)
        return LearningContext(
            context_type=context_type,
            subject_reference=self._text(subject_reference),
            learning_summary=resolved.learning_intelligence_summary,
            recommendation_evidence=resolved.recommendation_evidence,
            learning_insights=resolved.learning_insights,
            learning_recommendations=resolved.learning_recommendations,
            performance_snapshot=resolved.performance_snapshot,
            compatibility_metadata={
                "source": "business_learning",
                "owner": "BusinessLearningService",
                "provider_neutral": True,
                "read_only": True,
                "executes_commerce": False,
                "generates_decisions": False,
                "modifies_strategy": False,
            },
            metadata={
                **dict(metadata or {}),
                "historical_learning_boundary": True,
                "consumer_context": context_type,
            },
        )

    def build_product_learning_context(
        self,
        *,
        outcomes: BusinessOutcomeInput = None,
        snapshot: BusinessLearningSnapshot | None = None,
        product_reference: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LearningContext:
        return self.build_learning_context(
            outcomes=self._filter_outcomes(
                outcomes,
                product_reference=product_reference,
            )
            if snapshot is None
            else None,
            snapshot=snapshot,
            context_type="product_learning",
            subject_reference=product_reference,
            metadata=metadata,
        )

    def build_commerce_learning_context(
        self,
        *,
        outcomes: BusinessOutcomeInput = None,
        snapshot: BusinessLearningSnapshot | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LearningContext:
        return self.build_learning_context(
            outcomes=outcomes if snapshot is None else None,
            snapshot=snapshot,
            context_type="commerce_learning",
            metadata=metadata,
        )

    def build_customer_learning_context(
        self,
        *,
        outcomes: BusinessOutcomeInput = None,
        snapshot: BusinessLearningSnapshot | None = None,
        customer_reference: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LearningContext:
        return self.build_learning_context(
            outcomes=self._filter_outcomes(
                outcomes,
                customer_reference=customer_reference,
            )
            if snapshot is None
            else None,
            snapshot=snapshot,
            context_type="customer_learning",
            subject_reference=customer_reference,
            metadata=metadata,
        )

    def enrich_learning_snapshot(
        self,
        snapshot: BusinessLearningSnapshot | None = None,
        *,
        outcomes: BusinessOutcomeInput = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> BusinessLearningSnapshot:
        base = snapshot or self.build_learning_snapshot(outcomes=outcomes)
        additional = self.normalize_business_outcomes(outcomes)
        combined = base.outcomes + tuple(
            outcome for outcome in additional if outcome not in base.outcomes
        )
        return self.build_learning_snapshot(
            outcomes=combined,
            metadata={
                **dict(base.metadata.metadata),
                **dict(metadata or {}),
                "enriched_by": "BusinessLearningService",
            },
        )

    def summarize_recommendation_evidence(
        self,
        evidence: RecommendationEvidenceInput = None,
    ) -> dict[str, Any]:
        normalized = tuple(
            item
            for item in self._as_tuple(evidence)
            if isinstance(item, RecommendationEvidence)
        )
        return {
            "total_evidence": len(normalized),
            "positive_signal_count": sum(
                item.positive_signal_count for item in normalized
            ),
            "negative_signal_count": sum(
                item.negative_signal_count for item in normalized
            ),
            "average_confidence": (
                sum(item.confidence for item in normalized) / len(normalized)
                if normalized
                else 0.0
            ),
            "recommendation_ids": tuple(
                item.recommendation_id
                for item in normalized
                if item.recommendation_id is not None
            ),
            "metadata": {
                "source": "business_learning",
                "owner": "BusinessLearningService",
                "provider_neutral": True,
                "read_only": True,
                "evidence_only": True,
            },
        }

    def build_business_review(
        self,
        snapshot: BusinessLearningSnapshot | None = None,
        *,
        outcomes: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> BusinessLearningReview:
        resolved = snapshot or self.build_learning_snapshot(outcomes=outcomes)
        metrics = resolved.performance_snapshot.metrics
        top_performers = self.identify_top_performers(metrics)
        underperformers = self.identify_underperformers(metrics)
        review_summary = self.build_business_review_summary(
            snapshot=resolved,
            top_performers=top_performers,
            underperformers=underperformers,
        )
        return BusinessLearningReview(
            outcomes=resolved.outcomes,
            performance_metrics=metrics,
            learning_insights=resolved.learning_insights,
            recommendation_evidence=resolved.recommendation_evidence,
            top_performers=top_performers,
            underperformers=underperformers,
            historical_comparisons={
                "ranked_performance": tuple(
                    metric.metric_type for metric in self.rank_performance(metrics)
                ),
                "average_success_rate": resolved.performance_snapshot.summary.get(
                    "average_success_rate",
                    0.0,
                ),
                "average_confidence": resolved.performance_snapshot.summary.get(
                    "average_confidence",
                    0.0,
                ),
            },
            learning_summary=resolved.learning_intelligence_summary,
            review_summary=review_summary,
            compatibility_metadata={
                "source": "business_learning_review",
                "owner": "BusinessLearningService",
                "provider_neutral": True,
                "read_only": True,
                "presentation_only": True,
                "executes_commerce": False,
                "generates_decisions": False,
                "modifies_strategy": False,
                "modifies_publishing": False,
                "modifies_customer_intelligence": False,
            },
            metadata={
                **dict(metadata or {}),
                "creator_workspace_ready": True,
                "dashboard_ready": True,
            },
        )

    def build_business_review_summary(
        self,
        review: BusinessLearningReview | None = None,
        *,
        snapshot: BusinessLearningSnapshot | None = None,
        top_performers: Any | None = None,
        underperformers: Any | None = None,
    ) -> BusinessLearningReviewSummary:
        if review is not None:
            outcomes = review.outcomes
            metrics = review.performance_metrics
            insights = review.learning_insights
            evidence = review.recommendation_evidence
            top = review.top_performers
            under = review.underperformers
            learning_summary = review.learning_summary
        else:
            resolved = snapshot or self.build_learning_snapshot()
            outcomes = resolved.outcomes
            metrics = resolved.performance_snapshot.metrics
            insights = resolved.learning_insights
            evidence = resolved.recommendation_evidence
            top = tuple(
                item
                for item in self._as_tuple(top_performers)
                if isinstance(item, PerformanceMetric)
            ) or self.identify_top_performers(metrics)
            under = tuple(
                item
                for item in self._as_tuple(underperformers)
                if isinstance(item, PerformanceMetric)
            ) or self.identify_underperformers(metrics)
            learning_summary = resolved.learning_intelligence_summary

        confidence_values = [
            metric.confidence for metric in metrics if isinstance(metric, PerformanceMetric)
        ]
        confidence_values.extend(
            insight.confidence for insight in insights if isinstance(insight, LearningInsight)
        )
        average_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else 0.0
        )
        return BusinessLearningReviewSummary(
            total_outcomes=len(outcomes),
            total_metrics=len(metrics),
            total_insights=len(insights),
            recommendation_evidence_count=len(evidence),
            top_performer_count=len(top),
            underperformer_count=len(under),
            average_confidence=average_confidence,
            has_learning_history=bool(outcomes or insights or evidence),
            metadata={
                "source": "business_learning_review",
                "owner": "BusinessLearningService",
                "provider_neutral": True,
                "read_only": True,
                "presentation_only": True,
                "learning_summary_insights": learning_summary.total_insights,
            },
        )

    def summarize_learning_activity(
        self,
        snapshot: BusinessLearningSnapshot | None = None,
        *,
        outcomes: Any | None = None,
    ) -> dict[str, Any]:
        review = self.build_business_review(snapshot, outcomes=outcomes)
        return {
            "total_outcomes": review.review_summary.total_outcomes,
            "total_metrics": review.review_summary.total_metrics,
            "total_insights": review.review_summary.total_insights,
            "recommendation_evidence_count": (
                review.review_summary.recommendation_evidence_count
            ),
            "top_performer_count": review.review_summary.top_performer_count,
            "underperformer_count": review.review_summary.underperformer_count,
            "has_learning_history": review.review_summary.has_learning_history,
            "metadata": {
                "source": "business_learning_review",
                "owner": "BusinessLearningService",
                "provider_neutral": True,
                "read_only": True,
                "presentation_only": True,
            },
        }

    def record_business_outcome(
        self,
        outcomes: Any | None = None,
        *,
        outcome_type: BusinessOutcomeType | str | None = None,
        timestamp: str | None = None,
        customer_reference: str | None = None,
        product_reference: str | None = None,
        experience_reference: str | None = None,
        provider_metadata: Mapping[str, Any] | None = None,
        evidence_metadata: Mapping[str, Any] | None = None,
        compatibility_metadata: Mapping[str, Any] | None = None,
        **values: Any,
    ) -> tuple[BusinessOutcome, ...]:
        existing = self.normalize_business_outcomes(outcomes)
        if existing and outcome_type is None and not values:
            for item in existing:
                self._persist_business_outcome(item)
            return existing
        outcome = BusinessOutcome(
            outcome_id=self._text(values.get("outcome_id")),
            outcome_type=self._normalize_outcome_type(
                outcome_type or values.get("outcome_type")
            ),
            timestamp=self._text(timestamp or values.get("occurred_at")),
            subject_type=self._normalize_key(values.get("subject_type")),
            subject_id=self._text(values.get("subject_id")),
            customer_id=self._text(values.get("customer_id") or customer_reference),
            customer_reference=self._text(customer_reference or values.get("customer_id")),
            product_id=self._text(values.get("product_id") or product_reference),
            product_reference=self._text(product_reference or values.get("product_id")),
            experience_id=self._text(values.get("experience_id") or experience_reference),
            experience_reference=self._text(
                experience_reference or values.get("experience_id")
            ),
            strategy_source=self._normalize_key(values.get("strategy_source")),
            recommendation_id=self._text(values.get("recommendation_id")),
            status=self._normalize_key(values.get("status")),
            value_cents=self._int(values.get("value_cents")),
            occurred_at=self._text(values.get("occurred_at") or timestamp),
            signals=self._safe_mapping(values.get("signals")),
            provider_metadata=self._safe_mapping(provider_metadata),
            evidence_metadata=self._safe_mapping(evidence_metadata),
            compatibility_metadata={
                **self._safe_mapping(compatibility_metadata),
                "source": "business_learning",
                "read_only": True,
            },
            metadata={
                **self._safe_mapping(values.get("metadata")),
                "source": "business_learning",
                "canonical_business_outcome": True,
            },
        )
        self._persist_business_outcome(outcome)
        return existing + (outcome,)

    def _persist_business_outcome(self, outcome: BusinessOutcome) -> None:
        service = self._content_commerce_learning()
        recorder = getattr(service, "record_business_outcome", None)
        if not callable(recorder):
            return
        try:
            recorder(outcome)
        except Exception:
            return

    def summarize_business_outcomes(
        self,
        outcomes: Any | None = None,
    ) -> dict[str, Any]:
        normalized = self.normalize_business_outcomes(outcomes)
        return {
            "total_outcomes": len(normalized),
            "outcome_type_counts": self._count_raw_values(
                outcome.outcome_type for outcome in normalized
            ),
            "customer_count": len(
                {
                    outcome.customer_reference or outcome.customer_id
                    for outcome in normalized
                    if outcome.customer_reference or outcome.customer_id
                }
            ),
            "product_count": len(
                {
                    outcome.product_reference or outcome.product_id
                    for outcome in normalized
                    if outcome.product_reference or outcome.product_id
                }
            ),
            "experience_count": len(
                {
                    outcome.experience_reference or outcome.experience_id
                    for outcome in normalized
                    if outcome.experience_reference or outcome.experience_id
                }
            ),
            "has_business_outcomes": bool(normalized),
            "metadata": {
                "source": "business_learning",
                "owner": "BusinessLearningService",
                "read_only": True,
                "analytics_enabled": False,
            },
        }

    def build_performance_snapshot(
        self,
        *,
        outcomes: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> PerformanceSnapshot:
        normalized = self.normalize_business_outcomes(outcomes)
        metrics = (
            self.calculate_product_performance(normalized),
            self.calculate_bundle_performance(normalized),
            self.calculate_story_performance(normalized),
            self.calculate_photoshoot_performance(normalized),
            self.calculate_experience_performance(normalized),
            self.calculate_customer_engagement(normalized),
            self.calculate_conversation_effectiveness(normalized),
            self.calculate_cta_effectiveness(normalized),
            self.calculate_offer_effectiveness(normalized),
            self.calculate_delivery_effectiveness(normalized),
        )
        return PerformanceSnapshot(
            metrics=metrics,
            summary=self.summarize_performance(metrics),
            metadata=LearningMetadata(
                metadata={
                    **dict(metadata or {}),
                    "performance_intelligence": True,
                    "generates_recommendations": False,
                }
            ),
        )

    def calculate_product_performance(
        self,
        outcomes: Any | None = None,
    ) -> PerformanceMetric:
        return self._calculate_performance_metric(
            metric_name="Product performance",
            metric_type="product_performance",
            outcomes=outcomes,
            included_types=(
                BusinessOutcomeType.PRODUCT_OFFERED.value,
                BusinessOutcomeType.PRODUCT_PURCHASED.value,
                BusinessOutcomeType.PRODUCT_DELIVERED.value,
                BusinessOutcomeType.PRODUCT_DECLINED.value,
            ),
        )

    def calculate_bundle_performance(
        self,
        outcomes: Any | None = None,
    ) -> PerformanceMetric:
        return self._calculate_performance_metric(
            metric_name="Bundle performance",
            metric_type="bundle_performance",
            outcomes=outcomes,
            included_types=(BusinessOutcomeType.BUNDLE_PURCHASED.value,),
        )

    def calculate_story_performance(
        self,
        outcomes: Any | None = None,
    ) -> PerformanceMetric:
        return self._calculate_performance_metric(
            metric_name="Story performance",
            metric_type="story_performance",
            outcomes=outcomes,
            included_types=(BusinessOutcomeType.STORY_COMPLETED.value,),
        )

    def calculate_photoshoot_performance(
        self,
        outcomes: Any | None = None,
    ) -> PerformanceMetric:
        return self._calculate_performance_metric(
            metric_name="Photoshoot performance",
            metric_type="photoshoot_performance",
            outcomes=outcomes,
            included_types=(BusinessOutcomeType.PHOTOSHOOT_PURCHASED.value,),
        )

    def calculate_experience_performance(
        self,
        outcomes: Any | None = None,
    ) -> PerformanceMetric:
        return self._calculate_performance_metric(
            metric_name="Experience performance",
            metric_type="experience_performance",
            outcomes=outcomes,
            included_types=(BusinessOutcomeType.EXPERIENCE_COMPLETED.value,),
        )

    def calculate_customer_engagement(
        self,
        outcomes: Any | None = None,
    ) -> PerformanceMetric:
        return self._calculate_performance_metric(
            metric_name="Customer engagement",
            metric_type="customer_engagement",
            outcomes=outcomes,
            included_types=(
                BusinessOutcomeType.CONVERSATION_CONTINUED.value,
                BusinessOutcomeType.CONVERSATION_ENDED.value,
                BusinessOutcomeType.CTA_CLICKED.value,
                BusinessOutcomeType.FREE_ASSET_DELIVERED.value,
            ),
        )

    def calculate_conversation_effectiveness(
        self,
        outcomes: Any | None = None,
    ) -> PerformanceMetric:
        return self._calculate_performance_metric(
            metric_name="Conversation effectiveness",
            metric_type="conversation_effectiveness",
            outcomes=outcomes,
            included_types=(
                BusinessOutcomeType.CONVERSATION_CONTINUED.value,
                BusinessOutcomeType.CONVERSATION_ENDED.value,
            ),
        )

    def calculate_cta_effectiveness(
        self,
        outcomes: Any | None = None,
    ) -> PerformanceMetric:
        return self._calculate_performance_metric(
            metric_name="CTA effectiveness",
            metric_type="cta_effectiveness",
            outcomes=outcomes,
            included_types=(
                BusinessOutcomeType.CTA_PRESENTED.value,
                BusinessOutcomeType.CTA_CLICKED.value,
            ),
        )

    def calculate_offer_effectiveness(
        self,
        outcomes: Any | None = None,
    ) -> PerformanceMetric:
        return self._calculate_performance_metric(
            metric_name="Offer effectiveness",
            metric_type="offer_effectiveness",
            outcomes=outcomes,
            included_types=(
                BusinessOutcomeType.PRODUCT_OFFERED.value,
                BusinessOutcomeType.PRODUCT_PURCHASED.value,
                BusinessOutcomeType.PRODUCT_DECLINED.value,
            ),
        )

    def calculate_delivery_effectiveness(
        self,
        outcomes: Any | None = None,
    ) -> PerformanceMetric:
        return self._calculate_performance_metric(
            metric_name="Delivery effectiveness",
            metric_type="delivery_effectiveness",
            outcomes=outcomes,
            included_types=(
                BusinessOutcomeType.PRODUCT_DELIVERED.value,
                BusinessOutcomeType.FREE_ASSET_DELIVERED.value,
            ),
        )

    def summarize_performance(
        self,
        metrics: Any | None = None,
    ) -> dict[str, Any]:
        normalized = tuple(
            metric for metric in self._as_tuple(metrics) if isinstance(metric, PerformanceMetric)
        )
        total_observations = sum(metric.count for metric in normalized)
        average_success_rate = (
            sum(metric.success_rate for metric in normalized) / len(normalized)
            if normalized
            else 0.0
        )
        average_confidence = (
            sum(metric.confidence for metric in normalized) / len(normalized)
            if normalized
            else 0.0
        )
        return {
            "total_metrics": len(normalized),
            "total_observations": total_observations,
            "average_success_rate": average_success_rate,
            "average_confidence": average_confidence,
            "metric_types": tuple(metric.metric_type for metric in normalized),
            "metadata": {
                "source": "business_learning",
                "owner": "BusinessLearningService",
                "provider_neutral": True,
                "read_only": True,
                "generates_recommendations": False,
            },
        }

    def generate_learning_insights(
        self,
        *,
        outcomes: Any | None = None,
        performance_snapshot: PerformanceSnapshot | None = None,
        metrics: Any | None = None,
        recommendation_evidence: Any | None = None,
    ) -> tuple[LearningInsight, ...]:
        normalized_outcomes = self.normalize_business_outcomes(outcomes)
        snapshot = performance_snapshot or self.build_performance_snapshot(
            outcomes=normalized_outcomes
        )
        performance_metrics = tuple(
            metric
            for metric in self._as_tuple(metrics or snapshot.metrics)
            if isinstance(metric, PerformanceMetric)
        )
        evidence = tuple(
            item
            for item in self._as_tuple(recommendation_evidence)
            if isinstance(item, RecommendationEvidence)
        )
        insights: list[LearningInsight] = []
        for index, metric in enumerate(self.identify_top_performers(performance_metrics)):
            insights.append(
                self._build_learning_insight(
                    insight_id=f"learning-top-{index + 1}",
                    insight_type="top_performer",
                    metric=metric,
                    description=(
                        f"{metric.metric_name} is outperforming the observed "
                        "performance baseline."
                    ),
                    recommendation_evidence=evidence,
                )
            )
        for index, metric in enumerate(
            self.identify_underperformers(performance_metrics)
        ):
            insights.append(
                self._build_learning_insight(
                    insight_id=f"learning-under-{index + 1}",
                    insight_type="underperformer",
                    metric=metric,
                    description=(
                        f"{metric.metric_name} is underperforming the observed "
                        "performance baseline."
                    ),
                    recommendation_evidence=evidence,
                )
            )
        return tuple(insights)

    def generate_learning_summary(
        self,
        *,
        learning_insights: Any | None = None,
        learning_recommendations: Any | None = None,
    ) -> LearningSummary:
        insights = tuple(
            insight
            for insight in self._as_tuple(learning_insights)
            if isinstance(insight, LearningInsight)
        )
        recommendations = tuple(
            recommendation
            for recommendation in self._as_tuple(learning_recommendations)
            if isinstance(recommendation, LearningRecommendation)
        )
        average_confidence = (
            sum(insight.confidence for insight in insights) / len(insights)
            if insights
            else 0.0
        )
        return LearningSummary(
            total_insights=len(insights),
            total_recommendations=len(recommendations),
            top_performer_count=sum(
                1 for insight in insights if insight.insight_type == "top_performer"
            ),
            underperformer_count=sum(
                1 for insight in insights if insight.insight_type == "underperformer"
            ),
            average_confidence=average_confidence,
            insight_types=tuple(
                dict.fromkeys(
                    insight.insight_type
                    for insight in insights
                    if insight.insight_type is not None
                )
            ),
            metadata={
                "source": "business_learning",
                "owner": "BusinessLearningService",
                "provider_neutral": True,
                "read_only": True,
                "descriptive_only": True,
                "generates_decisions": False,
            },
        )

    def generate_recommendation_evidence(
        self,
        *,
        outcomes: Any | None = None,
        learning_insights: Any | None = None,
        recommendation_evidence: Any | None = None,
    ) -> tuple[LearningRecommendation, ...]:
        evidence = tuple(
            item
            for item in self._as_tuple(recommendation_evidence)
            if isinstance(item, RecommendationEvidence)
        ) or self.build_recommendation_evidence(outcomes=outcomes)
        insights = tuple(
            insight
            for insight in self._as_tuple(learning_insights)
            if isinstance(insight, LearningInsight)
        )
        if not insights and not evidence:
            return ()
        confidence = self.calculate_learning_confidence(
            insights=insights,
            recommendation_evidence=evidence,
        )
        return (
            LearningRecommendation(
                recommendation_id="learning-evidence-1",
                recommendation_type="historical_learning_evidence",
                summary="Historical learning evidence is available for consumers.",
                evidence=evidence,
                confidence=confidence,
                supporting_insight_ids=tuple(
                    insight.insight_id for insight in insights if insight.insight_id
                ),
                compatibility_metadata={
                    "source": "business_learning",
                    "owner": "BusinessLearningService",
                    "provider_neutral": True,
                    "read_only": True,
                },
                metadata={
                    "descriptive_only": True,
                    "automatic_strategy_change": False,
                    "generates_recommendations": False,
                },
            ),
        )

    def rank_performance(
        self,
        metrics: Any | None = None,
    ) -> tuple[PerformanceMetric, ...]:
        normalized = tuple(
            metric
            for metric in self._as_tuple(metrics)
            if isinstance(metric, PerformanceMetric)
        )
        return tuple(
            sorted(
                normalized,
                key=lambda metric: (
                    metric.success_rate,
                    metric.confidence,
                    metric.count,
                    metric.metric_type,
                ),
                reverse=True,
            )
        )

    def identify_top_performers(
        self,
        metrics: Any | None = None,
    ) -> tuple[PerformanceMetric, ...]:
        observed = tuple(
            metric
            for metric in self._as_tuple(metrics)
            if isinstance(metric, PerformanceMetric) and metric.count > 0
        )
        if not observed:
            return ()
        baseline = sum(metric.success_rate for metric in observed) / len(observed)
        return tuple(
            metric
            for metric in self.rank_performance(observed)
            if metric.success_rate >= baseline and metric.success_count > 0
        )

    def identify_underperformers(
        self,
        metrics: Any | None = None,
    ) -> tuple[PerformanceMetric, ...]:
        observed = tuple(
            metric
            for metric in self._as_tuple(metrics)
            if isinstance(metric, PerformanceMetric) and metric.count > 0
        )
        if not observed:
            return ()
        baseline = sum(metric.success_rate for metric in observed) / len(observed)
        return tuple(
            metric
            for metric in sorted(
                observed,
                key=lambda item: (
                    item.success_rate,
                    -item.failure_count,
                    item.metric_type,
                ),
            )
            if metric.success_rate < baseline
            or metric.failure_count > metric.success_count
        )

    def calculate_learning_confidence(
        self,
        *,
        metrics: Any | None = None,
        insights: Any | None = None,
        recommendation_evidence: Any | None = None,
    ) -> float:
        confidence_values = [
            metric.confidence
            for metric in self._as_tuple(metrics)
            if isinstance(metric, PerformanceMetric)
        ]
        confidence_values.extend(
            insight.confidence
            for insight in self._as_tuple(insights)
            if isinstance(insight, LearningInsight)
        )
        confidence_values.extend(
            evidence.confidence
            for evidence in self._as_tuple(recommendation_evidence)
            if isinstance(evidence, RecommendationEvidence)
        )
        if not confidence_values:
            return 0.0
        return sum(confidence_values) / len(confidence_values)

    def categorize_outcomes(
        self,
        outcomes: Any | None = None,
    ) -> dict[str, tuple[BusinessOutcome, ...]]:
        categories: dict[str, list[BusinessOutcome]] = {}
        for outcome in self.normalize_business_outcomes(outcomes):
            key = outcome.outcome_type or "UNKNOWN"
            categories.setdefault(key, []).append(outcome)
        return {key: tuple(values) for key, values in categories.items()}

    def normalize_business_outcomes(
        self,
        outcomes: Any | None = None,
    ) -> tuple[BusinessOutcome, ...]:
        if outcomes is None:
            return ()
        if isinstance(outcomes, BusinessOutcome):
            values = (outcomes,)
        elif isinstance(outcomes, Mapping):
            values = (outcomes,)
        else:
            try:
                values = tuple(outcomes)
            except TypeError:
                values = (outcomes,)

        return tuple(
            outcome
            for item in values
            if (outcome := self._normalize_outcome(item)) is not None
        )

    def summarize_business_performance(
        self,
        outcomes: Any | None = None,
    ) -> BusinessPerformanceSummary:
        normalized = self.normalize_business_outcomes(outcomes)
        total = len(normalized)
        successful = sum(1 for outcome in normalized if self._is_success(outcome))
        failed = sum(1 for outcome in normalized if self._is_failure(outcome))
        neutral = total - successful - failed
        return BusinessPerformanceSummary(
            total_outcomes=total,
            successful_outcomes=successful,
            failed_outcomes=failed,
            neutral_outcomes=neutral,
            total_value_cents=sum(outcome.value_cents for outcome in normalized),
            outcome_type_counts=self._count_values(
                outcome.outcome_type for outcome in normalized
            ),
            strategy_source_counts=self._count_values(
                outcome.strategy_source for outcome in normalized
            ),
            success_rate=(successful / total) if total else 0.0,
            metadata={
                "source": "business_learning",
                "owner": "BusinessLearningService",
                "read_only": True,
                "provider_neutral": True,
            },
        )

    def build_recommendation_evidence(
        self,
        *,
        outcomes: Any | None = None,
        recommendation_context: Any | None = None,
    ) -> tuple[RecommendationEvidence, ...]:
        normalized = self.normalize_business_outcomes(outcomes)
        grouped: dict[tuple[str | None, str | None], list[BusinessOutcome]] = {}
        for outcome in normalized:
            key = (outcome.recommendation_id, outcome.strategy_source)
            grouped.setdefault(key, []).append(outcome)

        context_recommendation_id = self._text(
            self._first_value(recommendation_context, "recommendation_id")
        )
        context_strategy_source = self._text(
            self._first_value(recommendation_context, "strategy_source")
        )
        if not grouped and (context_recommendation_id or context_strategy_source):
            grouped[(context_recommendation_id, context_strategy_source)] = []

        evidence = []
        for (recommendation_id, strategy_source), items in grouped.items():
            positive = sum(1 for outcome in items if self._is_success(outcome))
            negative = sum(1 for outcome in items if self._is_failure(outcome))
            total = len(items)
            confidence = positive / total if total else 0.0
            evidence.append(
                RecommendationEvidence(
                    recommendation_id=recommendation_id,
                    strategy_source=strategy_source,
                    evidence_type="historical_outcome",
                    confidence=confidence,
                    supporting_outcome_ids=tuple(
                        outcome.outcome_id
                        for outcome in items
                        if outcome.outcome_id is not None
                    ),
                    positive_signal_count=positive,
                    negative_signal_count=negative,
                    rationale=self._evidence_rationale(
                        total=total,
                        positive=positive,
                        negative=negative,
                    ),
                    metadata={
                        "source": "business_learning",
                        "read_only": True,
                        "generates_recommendations": False,
                    },
                )
            )
        return tuple(evidence)

    def summarize_learning(
        self,
        *,
        outcomes: Any | None = None,
        performance_summary: BusinessPerformanceSummary | None = None,
        recommendation_evidence: Any | None = None,
    ) -> dict[str, Any]:
        normalized = self.normalize_business_outcomes(outcomes)
        performance = performance_summary or self.summarize_business_performance(
            normalized
        )
        evidence = tuple(recommendation_evidence or ())
        return {
            "total_outcomes": performance.total_outcomes,
            "success_rate": performance.success_rate,
            "total_value_cents": performance.total_value_cents,
            "outcome_type_counts": dict(performance.outcome_type_counts),
            "strategy_source_counts": dict(performance.strategy_source_counts),
            "recommendation_evidence_count": len(evidence),
            "has_learning_history": bool(normalized or evidence),
            "metadata": {
                "source": "business_learning",
                "owner": "BusinessLearningService",
                "read_only": True,
                "provider_neutral": True,
                "automatic_learning": False,
            },
        }

    def _normalize_outcome(self, value: Any) -> BusinessOutcome | None:
        if isinstance(value, BusinessOutcome):
            return value
        if value is None:
            return None
        return BusinessOutcome(
            outcome_id=self._text(self._first_value(value, "outcome_id", "id")),
            outcome_type=self._normalize_outcome_type(
                self._first_value(value, "outcome_type", "type")
            ),
            timestamp=self._text(
                self._first_value(value, "timestamp", "occurred_at")
            ),
            subject_type=self._normalize_key(self._first_value(value, "subject_type")),
            subject_id=self._text(self._first_value(value, "subject_id")),
            customer_id=self._text(self._first_value(value, "customer_id")),
            customer_reference=self._text(
                self._first_value(value, "customer_reference", "customer_id")
            ),
            product_id=self._text(self._first_value(value, "product_id")),
            product_reference=self._text(
                self._first_value(value, "product_reference", "product_id")
            ),
            experience_id=self._text(self._first_value(value, "experience_id")),
            experience_reference=self._text(
                self._first_value(value, "experience_reference", "experience_id")
            ),
            strategy_source=self._normalize_key(
                self._first_value(value, "strategy_source", "source")
            ),
            recommendation_id=self._text(
                self._first_value(value, "recommendation_id")
            ),
            status=self._normalize_key(
                self._first_value(value, "status", "outcome", "result")
            ),
            value_cents=self._int(
                self._first_value(value, "value_cents", "amount_cents")
            ),
            occurred_at=self._text(self._first_value(value, "occurred_at", "timestamp")),
            signals=self._safe_mapping(self._first_value(value, "signals")),
            provider_metadata=self._safe_mapping(
                self._first_value(value, "provider_metadata")
            ),
            evidence_metadata=self._safe_mapping(
                self._first_value(value, "evidence_metadata")
            ),
            compatibility_metadata=self._safe_mapping(
                self._first_value(value, "compatibility_metadata")
            ),
            metadata=self._safe_mapping(self._first_value(value, "metadata")),
        )

    def _build_learning_insight(
        self,
        *,
        insight_id: str,
        insight_type: str,
        metric: PerformanceMetric,
        description: str,
        recommendation_evidence: tuple[RecommendationEvidence, ...],
    ) -> LearningInsight:
        supporting_outcome_ids = tuple(
            outcome_id
            for evidence in metric.supporting_evidence
            for outcome_id in evidence.outcome_ids
        )
        return LearningInsight(
            insight_id=insight_id,
            insight_type=insight_type,
            subject=metric.metric_type,
            description=description,
            confidence=self.calculate_learning_confidence(metrics=(metric,)),
            supporting_metric_types=(metric.metric_type,),
            supporting_outcome_ids=supporting_outcome_ids,
            recommendation_evidence=recommendation_evidence,
            compatibility_metadata={
                "source": "business_learning",
                "owner": "BusinessLearningService",
                "provider_neutral": True,
                "read_only": True,
            },
            metadata={
                "descriptive_only": True,
                "automatic_strategy_change": False,
                "generates_recommendations": False,
            },
        )

    def _filter_outcomes(
        self,
        outcomes: Any | None,
        *,
        product_reference: str | None = None,
        customer_reference: str | None = None,
    ) -> tuple[BusinessOutcome, ...]:
        product = self._text(product_reference)
        customer = self._text(customer_reference)
        normalized = self.normalize_business_outcomes(outcomes)
        if not product and not customer:
            return normalized
        return tuple(
            outcome
            for outcome in normalized
            if (
                not product
                or outcome.product_reference == product
                or outcome.product_id == product
            )
            and (
                not customer
                or outcome.customer_reference == customer
                or outcome.customer_id == customer
            )
        )

    def _calculate_performance_metric(
        self,
        *,
        metric_name: str,
        metric_type: str,
        outcomes: Any | None = None,
        included_types: tuple[str, ...],
    ) -> PerformanceMetric:
        included = {
            self._normalize_outcome_type(outcome_type)
            for outcome_type in included_types
            if self._normalize_outcome_type(outcome_type)
        }
        selected = tuple(
            outcome
            for outcome in self.normalize_business_outcomes(outcomes)
            if outcome.outcome_type in included
        )
        success = sum(1 for outcome in selected if self._is_success(outcome))
        failure = sum(1 for outcome in selected if self._is_failure(outcome))
        neutral = len(selected) - success - failure
        evidence = PerformanceEvidence(
            evidence_type=f"{metric_type}_outcomes",
            outcome_ids=tuple(
                outcome.outcome_id for outcome in selected if outcome.outcome_id
            ),
            outcome_types=tuple(
                dict.fromkeys(
                    outcome.outcome_type
                    for outcome in selected
                    if outcome.outcome_type is not None
                )
            ),
            positive_count=success,
            negative_count=failure,
            neutral_count=neutral,
            metadata={
                "source": "business_learning",
                "read_only": True,
                "provider_neutral": True,
            },
        )
        return PerformanceMetric(
            metric_name=metric_name,
            metric_type=metric_type,
            count=len(selected),
            success_count=success,
            failure_count=failure,
            neutral_count=neutral,
            success_rate=(success / len(selected)) if selected else 0.0,
            confidence=self._performance_confidence(len(selected)),
            supporting_evidence=(evidence,),
            compatibility_metadata={
                "source": "business_learning",
                "owner": "BusinessLearningService",
                "provider_neutral": True,
                "read_only": True,
            },
            metadata={
                "performance_intelligence": True,
                "generates_recommendations": False,
            },
        )

    @staticmethod
    def _performance_confidence(observation_count: int) -> float:
        if observation_count <= 0:
            return 0.0
        return min(1.0, observation_count / 10)

    @staticmethod
    def _as_tuple(value: Any | None) -> tuple[Any, ...]:
        if value is None:
            return ()
        if isinstance(value, tuple):
            return value
        if isinstance(value, list):
            return tuple(value)
        return (value,)

    @classmethod
    def _first_value(cls, source: Any, *names: str) -> Any | None:
        if source is None:
            return None
        for name in names:
            if isinstance(source, Mapping) and name in source:
                return source[name]
            if hasattr(source, name):
                return getattr(source, name)
        return None

    @staticmethod
    def _safe_mapping(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _normalize_key(cls, value: Any) -> str | None:
        text = cls._text(value)
        return text.lower().replace(" ", "_") if text else None

    @classmethod
    def _normalize_outcome_type(cls, value: Any) -> str | None:
        if isinstance(value, BusinessOutcomeType):
            return value.value
        text = cls._text(value)
        if not text:
            return None
        normalized = text.strip().upper().replace(" ", "_").replace("-", "_")
        aliases = {
            "OFFER": BusinessOutcomeType.PRODUCT_OFFERED.value,
            "PURCHASE": BusinessOutcomeType.PRODUCT_PURCHASED.value,
            "DELIVERY": BusinessOutcomeType.PRODUCT_DELIVERED.value,
            "DECLINE": BusinessOutcomeType.PRODUCT_DECLINED.value,
            "STORY_COMPLETE": BusinessOutcomeType.STORY_COMPLETED.value,
            "EXPERIENCE_COMPLETE": BusinessOutcomeType.EXPERIENCE_COMPLETED.value,
        }
        return aliases.get(normalized, normalized)

    @classmethod
    def _count_values(cls, values: Any) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            text = cls._normalize_key(value)
            if text is None:
                continue
            counts[text] = counts.get(text, 0) + 1
        return counts

    @classmethod
    def _count_raw_values(cls, values: Any) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            text = cls._text(value)
            if text is None:
                continue
            counts[text] = counts.get(text, 0) + 1
        return counts

    @classmethod
    def _is_success(cls, outcome: BusinessOutcome) -> bool:
        successful_types = {
            BusinessOutcomeType.PRODUCT_PURCHASED.value,
            BusinessOutcomeType.PRODUCT_DELIVERED.value,
            BusinessOutcomeType.BUNDLE_PURCHASED.value,
            BusinessOutcomeType.STORY_COMPLETED.value,
            BusinessOutcomeType.PHOTOSHOOT_PURCHASED.value,
            BusinessOutcomeType.FREE_ASSET_DELIVERED.value,
            BusinessOutcomeType.CONVERSATION_CONTINUED.value,
            BusinessOutcomeType.CTA_CLICKED.value,
            BusinessOutcomeType.EXPERIENCE_COMPLETED.value,
        }
        if outcome.outcome_type in successful_types:
            return True
        return (outcome.status or "").lower() in {
            "accepted",
            "converted",
            "delivered",
            "purchased",
            "success",
            "successful",
            "unlocked",
        }

    @classmethod
    def _is_failure(cls, outcome: BusinessOutcome) -> bool:
        failed_types = {
            BusinessOutcomeType.PRODUCT_DECLINED.value,
            BusinessOutcomeType.CONVERSATION_ENDED.value,
        }
        if outcome.outcome_type in failed_types:
            return True
        return (outcome.status or "").lower() in {
            "blocked",
            "declined",
            "failed",
            "ignored",
            "rejected",
            "unsuccessful",
        }

    @staticmethod
    def _evidence_rationale(
        *,
        total: int,
        positive: int,
        negative: int,
    ) -> tuple[str, ...]:
        if total == 0:
            return ("No historical outcomes available yet.",)
        return (
            f"{positive} positive outcome(s)",
            f"{negative} negative outcome(s)",
            f"{total} total observed outcome(s)",
        )
