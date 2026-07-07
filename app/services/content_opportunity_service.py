"""Provider-neutral Content Opportunity Intelligence service."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Iterable, Mapping

from app.models.content_opportunity import (
    ContentDemandSummary,
    ContentDemandSignal,
    ContentDemandTopicSummary,
    ContentDemandTrend,
    ContentOpportunity,
    ContentOpportunityHealth,
    ContentOpportunityFollowUp,
    ContentOpportunityFollowUpPriority,
    ContentOpportunityFollowUpStatus,
    ContentOpportunityMatchType,
    ContentOpportunityPriority,
    ContentOpportunityRecommendation,
    ContentOpportunityRecommendationEvidence,
    ContentOpportunityRecommendationPriority,
    ContentOpportunityRecommendationType,
    ContentOpportunityResolution,
    ContentOpportunityResolutionSource,
    ContentOpportunityResolutionStatus,
    ContentOpportunitySnapshot,
    ContentOpportunitySource,
    ContentOpportunityStatus,
    ContentRequestMatch,
    utc_now,
)


class ContentOpportunityService:
    """Track customer content demand without owning runtime or Product logic."""

    SAFE_UNMATCHED_GUIDANCE = {
        "intent": "UNMATCHED_CONTENT_REQUEST_SAFE_GUIDANCE",
        "final_response_owner": "DecisionEngine",
        "guidance": (
            "Acknowledge that no matching content is currently available, thank "
            "the customer for the suggestion, and say it can be kept in mind for "
            "future planning without promising future content."
        ),
        "must_not_promise_future_content": True,
    }

    MATCHED_GUIDANCE = {
        "intent": "MATCHED_CONTENT_REQUEST_EXISTING_CONTENT_AVAILABLE",
        "final_response_owner": "DecisionEngine",
        "guidance": (
            "Existing content appears to satisfy the request. Runtime may decide "
            "whether and how to offer it later."
        ),
    }

    RESOLUTION_GUIDANCE = {
        "intent": "CONTENT_OPPORTUNITY_RESOLUTION_READY",
        "final_response_owner": "DecisionEngine",
        "guidance": (
            "New content may satisfy previous customer demand. Customers previously "
            "requested similar content. Follow-up opportunity is ready for review."
        ),
        "must_not_contact_customers": True,
        "must_not_promise_delivery": True,
    }

    FOLLOW_UP_GUIDANCE = {
        "intent": "CONTENT_OPPORTUNITY_FOLLOW_UP_READY",
        "final_response_owner": "DecisionEngine",
        "guidance": (
            "Customer previously requested similar content. Opportunity is now "
            "available. DecisionEngine may naturally introduce this Product during "
            "conversation."
        ),
        "must_not_contact_customer_automatically": True,
        "must_not_imply_content_was_custom_made": True,
        "must_not_imply_creator_commitment": True,
    }

    def __init__(
        self,
        *,
        product_catalog_service: Any | None = None,
        product_business_service: Any | None = None,
        experience_service: Any | None = None,
        content_intelligence_service: Any | None = None,
        customer_intelligence_service: Any | None = None,
        business_learning_service: Any | None = None,
        content_opportunity_repository: Any | None = None,
    ) -> None:
        self.product_catalog_service = product_catalog_service
        self.product_business_service = product_business_service
        self.experience_service = experience_service
        self.content_intelligence_service = content_intelligence_service
        self.customer_intelligence_service = customer_intelligence_service
        self.business_learning_service = business_learning_service
        self.content_opportunity_repository = content_opportunity_repository
        self._signals: list[ContentDemandSignal] = []
        self._matches: list[ContentRequestMatch] = []
        self._opportunities: list[ContentOpportunity] = []
        self._resolutions: list[ContentOpportunityResolution] = []
        self._follow_ups: list[ContentOpportunityFollowUp] = []
        self._hydrate_from_repository()

    def create_demand_signal(
        self,
        *,
        customer_id: str | int | None = None,
        provider: str | None = None,
        provider_customer_id: str | int | None = None,
        request_text: str,
        normalized_terms: Iterable[str] | None = None,
        requested_content_type: str | None = None,
        requested_format: str | None = None,
        source: ContentOpportunitySource | str | None = None,
        conversation_id: str | int | None = None,
        message_id: str | int | None = None,
        source_metadata: Mapping[str, Any] | None = None,
        is_vip: bool = False,
        customer_importance: str | None = None,
        notes: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ContentDemandSignal:
        terms = self._normalized_terms(request_text, normalized_terms)
        signal = ContentDemandSignal(
            signal_id=f"demand-{len(self._signals) + 1}",
            customer_id=self._text(customer_id),
            provider=provider or "provider_neutral",
            provider_customer_id=self._text(provider_customer_id),
            request_text=request_text,
            normalized_terms=terms,
            requested_content_type=self._clean_text(requested_content_type),
            requested_format=self._clean_text(requested_format),
            source=self._source(source),
            conversation_id=self._text(conversation_id),
            message_id=self._text(message_id),
            source_metadata=dict(source_metadata or {}),
            is_vip=bool(is_vip),
            customer_importance=self._clean_text(customer_importance),
            notes=tuple(str(note) for note in (notes or ()) if str(note).strip()),
            metadata={
                **dict(metadata or {}),
                "read_only": True,
                "provider_neutral": True,
                "owner": "ContentOpportunityService",
            },
        )
        self._signals.append(signal)
        self._persist_records()
        return signal

    def record_content_request(
        self,
        *,
        customer_id: str | int | None = None,
        provider: str | None = None,
        provider_customer_id: str | int | None = None,
        request_text: str,
        match_candidates: Iterable[Mapping[str, Any] | Any] | Mapping[str, Any] | Any | None = None,
        creator_profile_id: int | None = None,
        product_candidates: Iterable[Mapping[str, Any] | Any] | None = None,
        experience_candidates: Iterable[Mapping[str, Any] | Any] | None = None,
        asset_candidates: Iterable[Mapping[str, Any] | Any] | None = None,
        asset_ids: Iterable[str | int] | None = None,
        normalized_terms: Iterable[str] | None = None,
        requested_content_type: str | None = None,
        requested_format: str | None = None,
        source: ContentOpportunitySource | str | None = None,
        conversation_id: str | int | None = None,
        message_id: str | int | None = None,
        source_metadata: Mapping[str, Any] | None = None,
        is_vip: bool = False,
        customer_importance: str | None = None,
        notes: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ContentOpportunity:
        signal = self.create_demand_signal(
            customer_id=customer_id,
            provider=provider,
            provider_customer_id=provider_customer_id,
            request_text=request_text,
            normalized_terms=normalized_terms,
            requested_content_type=requested_content_type,
            requested_format=requested_format,
            source=source,
            conversation_id=conversation_id,
            message_id=message_id,
            source_metadata=source_metadata,
            is_vip=is_vip,
            customer_importance=customer_importance,
            notes=notes,
            metadata=metadata,
        )
        requested_asset_ids = asset_ids
        product_ids, experience_ids, matched_asset_ids, confidence, evidence = (
            self._candidate_evidence(match_candidates)
        )
        if not (product_ids or experience_ids or matched_asset_ids):
            product_ids, experience_ids, matched_asset_ids, confidence, evidence = (
                self._resolve_match_evidence(
                    request_text=request_text,
                    normalized_terms=signal.normalized_terms,
                    creator_profile_id=creator_profile_id,
                    product_candidates=product_candidates,
                    experience_candidates=experience_candidates,
                    asset_candidates=asset_candidates,
                    asset_ids=requested_asset_ids,
                )
            )
        if product_ids or experience_ids or matched_asset_ids:
            return self.record_matched_request(
                demand_signal=signal,
                product_ids=product_ids,
                experience_ids=experience_ids,
                asset_ids=matched_asset_ids,
                confidence=confidence,
                match_evidence=evidence,
                notes=notes,
            )
        return self.record_unmatched_request(
            demand_signal=signal,
            notes=notes,
            supporting_evidence=evidence,
        )

    def resolve_content_request(
        self,
        *,
        customer_id: str | int | None = None,
        provider: str | None = None,
        provider_customer_id: str | int | None = None,
        request_text: str,
        creator_profile_id: int | None = None,
        product_candidates: Iterable[Mapping[str, Any] | Any] | None = None,
        experience_candidates: Iterable[Mapping[str, Any] | Any] | None = None,
        asset_candidates: Iterable[Mapping[str, Any] | Any] | None = None,
        asset_ids: Iterable[str | int] | None = None,
        normalized_terms: Iterable[str] | None = None,
        requested_content_type: str | None = None,
        requested_format: str | None = None,
        source: ContentOpportunitySource | str | None = None,
        conversation_id: str | int | None = None,
        message_id: str | int | None = None,
        source_metadata: Mapping[str, Any] | None = None,
        is_vip: bool = False,
        customer_importance: str | None = None,
        notes: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ContentOpportunity:
        """Resolve a request using read-only Product, Experience, and Asset inputs."""

        return self.record_content_request(
            customer_id=customer_id,
            provider=provider,
            provider_customer_id=provider_customer_id,
            request_text=request_text,
            creator_profile_id=creator_profile_id,
            product_candidates=product_candidates,
            experience_candidates=experience_candidates,
            asset_candidates=asset_candidates,
            asset_ids=asset_ids,
            normalized_terms=normalized_terms,
            requested_content_type=requested_content_type,
            requested_format=requested_format,
            source=source,
            conversation_id=conversation_id,
            message_id=message_id,
            source_metadata=source_metadata,
            is_vip=is_vip,
            customer_importance=customer_importance,
            notes=notes,
            metadata=metadata,
        )

    def create_match_record(
        self,
        demand_signal: ContentDemandSignal,
        *,
        product_ids: Iterable[str | int] = (),
        experience_ids: Iterable[str | int] = (),
        asset_ids: Iterable[str | int] = (),
        confidence: float = 0.0,
        match_evidence: Mapping[str, Any] | None = None,
        notes: Iterable[str] | None = None,
    ) -> ContentOpportunity:
        """Compatibility alias for creating a matched opportunity record."""

        return self.record_matched_request(
            demand_signal=demand_signal,
            product_ids=product_ids,
            experience_ids=experience_ids,
            asset_ids=asset_ids,
            confidence=confidence,
            match_evidence=match_evidence,
            notes=notes,
        )

    def find_matching_products(
        self,
        *,
        request_text: str,
        normalized_terms: Iterable[str] | None = None,
        creator_profile_id: int | None = None,
        product_candidates: Iterable[Mapping[str, Any] | Any] | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        terms = self._normalized_terms(request_text, normalized_terms)
        candidates = tuple(product_candidates or self._load_product_candidates(creator_profile_id))
        matches = []
        for candidate in candidates:
            product = self._read(candidate, "product") or candidate
            match = self._match_candidate(
                candidate=product,
                terms=terms,
                id_names=("product_id", "id"),
                source="ProductCatalogService",
                domain="product",
                weighted_fields=(
                    ("tags", 0.28),
                    ("themes", 0.25),
                    ("keywords", 0.22),
                    ("display_name", 0.2),
                    ("internal_name", 0.18),
                    ("name", 0.18),
                    ("title", 0.18),
                    ("description", 0.14),
                    ("product_type", 0.12),
                    ("delivery_type", 0.08),
                ),
                extra_evidence={
                    "publishing_readiness": self._safe_public_mapping(
                        self._read(candidate, "publishing")
                        or self._read(product, "publishing_readiness")
                    ),
                    "product_business_owner": "ProductBusinessService",
                },
            )
            if match:
                matches.append(match)
        return tuple(self._sort_matches(matches))

    def find_matching_experiences(
        self,
        *,
        request_text: str,
        normalized_terms: Iterable[str] | None = None,
        creator_profile_id: int | None = None,
        experience_candidates: Iterable[Mapping[str, Any] | Any] | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        terms = self._normalized_terms(request_text, normalized_terms)
        candidates = tuple(experience_candidates or self._load_experience_candidates(creator_profile_id))
        matches = []
        for candidate in candidates:
            match = self._match_candidate(
                candidate=candidate,
                terms=terms,
                id_names=("experience_id", "id"),
                source="ExperienceService",
                domain="experience",
                weighted_fields=(
                    ("themes", 0.28),
                    ("keywords", 0.25),
                    ("title", 0.22),
                    ("name", 0.2),
                    ("summary", 0.18),
                    ("description", 0.16),
                    ("experience_type", 0.12),
                ),
            )
            if match:
                matches.append(match)
        return tuple(self._sort_matches(matches))

    def find_matching_assets(
        self,
        *,
        request_text: str,
        normalized_terms: Iterable[str] | None = None,
        asset_candidates: Iterable[Mapping[str, Any] | Any] | None = None,
        asset_ids: Iterable[str | int] | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        terms = self._normalized_terms(request_text, normalized_terms)
        candidates = tuple(asset_candidates or self._load_asset_candidates(asset_ids))
        matches = []
        for candidate in candidates:
            match = self._match_candidate(
                candidate=candidate,
                terms=terms,
                id_names=("asset_id", "id"),
                source="ContentIntelligenceService",
                domain="asset",
                weighted_fields=(
                    ("themes", 0.25),
                    ("keywords", 0.25),
                    ("activities", 0.18),
                    ("environment", 0.16),
                    ("mood", 0.14),
                    ("clothing", 0.14),
                    ("classification", 0.12),
                    ("tags", 0.12),
                    ("summary", 0.1),
                ),
            )
            if match:
                matches.append(match)
        return tuple(self._sort_matches(matches))

    def record_matched_request(
        self,
        *,
        demand_signal: ContentDemandSignal,
        product_ids: Iterable[str | int] = (),
        experience_ids: Iterable[str | int] = (),
        asset_ids: Iterable[str | int] = (),
        confidence: float = 0.0,
        match_evidence: Mapping[str, Any] | None = None,
        notes: Iterable[str] | None = None,
    ) -> ContentOpportunity:
        products = self._text_tuple(product_ids)
        experiences = self._text_tuple(experience_ids)
        assets = self._text_tuple(asset_ids)
        match_type = self._match_type(products, experiences, assets)
        match = ContentRequestMatch(
            match_id=f"match-{len(self._matches) + 1}",
            demand_signal=demand_signal,
            match_type=match_type,
            product_ids=products,
            experience_ids=experiences,
            asset_ids=assets,
            confidence=self._bounded_confidence(confidence or 0.75),
            can_offer_existing_content=True,
            match_evidence=dict(match_evidence or {}),
            safe_response_guidance=dict(self.MATCHED_GUIDANCE),
            notes=tuple(notes or ()),
            metadata={
                "read_only": True,
                "advisory_only": True,
                "executes_offer": False,
                "owner": "ContentOpportunityService",
            },
        )
        self._matches.append(match)
        self._persist_records()
        opportunity = self._store_or_update_opportunity(
            ContentOpportunity(
                opportunity_id=f"content-opportunity-{len(self._opportunities) + 1}",
                demand_signal=demand_signal,
                status=ContentOpportunityStatus.MATCHED,
                priority=self._priority(demand_signal, matched=True),
                normalized_terms=demand_signal.normalized_terms,
                match=match,
                product_ids=products,
                experience_ids=experiences,
                asset_ids=assets,
                confidence=match.confidence,
                vip_demand=demand_signal.is_vip,
                safe_response_guidance=dict(self.MATCHED_GUIDANCE),
                next_recommended_action="Review matched content request",
                supporting_evidence={
                    "matched_product_ids": products,
                    "matched_experience_ids": experiences,
                    "matched_asset_ids": assets,
                    "match_type": match_type.value,
                    "match_evidence": dict(match_evidence or {}),
                },
                notes=tuple(notes or ()),
                metadata=self._opportunity_metadata(),
            )
        )
        return opportunity

    def record_unmatched_request(
        self,
        *,
        demand_signal: ContentDemandSignal,
        supporting_evidence: Mapping[str, Any] | None = None,
        notes: Iterable[str] | None = None,
    ) -> ContentOpportunity:
        return self._store_or_update_opportunity(
            ContentOpportunity(
                opportunity_id=f"content-opportunity-{len(self._opportunities) + 1}",
                demand_signal=demand_signal,
                status=ContentOpportunityStatus.UNMATCHED,
                priority=self._priority(demand_signal, matched=False),
                normalized_terms=demand_signal.normalized_terms,
                confidence=0.45 if not demand_signal.is_vip else 0.65,
                vip_demand=demand_signal.is_vip,
                safe_response_guidance=dict(self.SAFE_UNMATCHED_GUIDANCE),
                next_recommended_action=(
                    "Review VIP unmet content demand"
                    if demand_signal.is_vip
                    else "Review unmet content demand"
                ),
                supporting_evidence={
                    "request_text": demand_signal.request_text,
                    "normalized_terms": demand_signal.normalized_terms,
                    **dict(supporting_evidence or {}),
                },
                notes=tuple(notes or ()),
                metadata=self._opportunity_metadata(),
            )
        )

    def build_snapshot(self) -> ContentOpportunitySnapshot:
        opportunities = tuple(self._opportunities)
        unmatched = tuple(
            item for item in opportunities if item.status == ContentOpportunityStatus.UNMATCHED
        )
        repeat_terms = self._repeat_demand_terms()
        vip_opportunities = tuple(item for item in opportunities if item.vip_demand)
        actions = self._next_actions(opportunities)
        demand_summary = self.summarize_demand()
        topic_summaries = self.summarize_trending_topics()
        growing_topics = tuple(
            topic
            for topic in topic_summaries
            if topic.trend == ContentDemandTrend.GROWING
            or topic.request_count > 1
            or topic.unique_customers > 1
            or topic.vip_request_count > 0
        )
        satisfied_topics = tuple(
            topic
            for topic in topic_summaries
            if topic.matched_count and topic.unmet_percentage == 0.0
        )
        unsatisfied_topics = tuple(
            topic
            for topic in topic_summaries
            if topic.unmatched_count and topic.unmet_percentage > 0.0
        )
        highest_priority = self._highest_priority_opportunities(opportunities)
        creator_recommendations = self.generate_creator_recommendations()
        resolution_ready = self.list_resolution_ready_opportunities()
        waiting_customers = self._waiting_customers_for_dashboard()
        return ContentOpportunitySnapshot(
            demand_signals=tuple(self._signals),
            matched_requests=tuple(self._matches),
            unmatched_opportunities=unmatched,
            opportunities=opportunities,
            repeat_demand_terms=repeat_terms,
            vip_opportunities=vip_opportunities,
            next_recommended_actions=actions,
            matched_count=len(self._matches),
            unmatched_count=len(unmatched),
            repeat_demand_count=len(repeat_terms),
            vip_demand_count=len(vip_opportunities),
            total_requests=demand_summary.total_requests,
            matched_percentage=demand_summary.matched_percentage,
            unmet_percentage=demand_summary.unmet_percentage,
            repeat_request_count=demand_summary.repeat_request_count,
            vip_request_count=demand_summary.vip_request_count,
            unique_customers=demand_summary.unique_customers,
            top_requested_topics=topic_summaries[:10],
            trending_topics=topic_summaries,
            growing_topics=growing_topics,
            satisfied_topics=satisfied_topics,
            unsatisfied_topics=unsatisfied_topics,
            demand_by_content_type=demand_summary.demand_by_content_type,
            demand_by_format=demand_summary.demand_by_format,
            demand_by_customer_segment=demand_summary.demand_by_customer_segment,
            highest_priority_opportunities=highest_priority,
            opportunity_health=demand_summary.opportunity_health,
            demand_summary=demand_summary,
            creator_recommendations=creator_recommendations,
            recommendation_count=len(creator_recommendations),
            resolution_records=tuple(self._resolutions),
            resolution_ready_count=len(resolution_ready),
            waiting_customers=waiting_customers,
            waiting_customer_count=len(waiting_customers),
            follow_up_opportunities=tuple(self._follow_ups),
            pending_follow_up_count=len(self.list_pending_follow_ups()),
            ready_follow_up_count=len(self.list_ready_follow_ups()),
            safe_response_guidance=dict(self.SAFE_UNMATCHED_GUIDANCE),
            summary={
                "demand_signal_count": len(self._signals),
                "total_requests": demand_summary.total_requests,
                "matched_count": len(self._matches),
                "unmatched_count": len(unmatched),
                "matched_requests": demand_summary.matched_requests,
                "unmatched_requests": demand_summary.unmatched_requests,
                "matched_percentage": demand_summary.matched_percentage,
                "unmet_percentage": demand_summary.unmet_percentage,
                "opportunity_count": len(opportunities),
                "repeat_demand_count": len(repeat_terms),
                "repeat_request_count": demand_summary.repeat_request_count,
                "vip_demand_count": len(vip_opportunities),
                "vip_request_count": demand_summary.vip_request_count,
                "unique_customers": demand_summary.unique_customers,
                "recommendation_count": len(creator_recommendations),
                "resolution_ready_count": len(resolution_ready),
                "waiting_customer_count": len(waiting_customers),
                "pending_follow_up_count": len(self.list_pending_follow_ups()),
                "ready_follow_up_count": len(self.list_ready_follow_ups()),
                "opportunity_health": demand_summary.opportunity_health.value,
                "next_recommended_actions": actions,
            },
            compatibility=self._compatibility(),
        )

    def build_opportunity_snapshot(self) -> ContentOpportunitySnapshot:
        """Compatibility alias for consumers that want the intelligence snapshot."""

        return self.build_snapshot()

    def summarize_demand(self) -> ContentDemandSummary:
        """Summarize all recorded demand without generating recommendations."""

        total = len(self._signals)
        matched_signal_ids = self._matched_signal_ids()
        matched = len(matched_signal_ids)
        unmatched = max(0, total - matched)
        repeat_terms = self._repeat_demand_terms()
        vip_count = sum(1 for signal in self._signals if signal.is_vip)
        unique_customers = len(self._customer_keys(self._signals))
        content_type_counts = self._count_signal_field("requested_content_type")
        format_counts = self._count_signal_field("requested_format")
        segment_counts = self._customer_segment_counts(self._signals)
        matched_percentage = self._percentage(matched, total)
        unmet_percentage = self._percentage(unmatched, total)
        health = self._opportunity_health(
            total_requests=total,
            unmatched_requests=unmatched,
            repeat_request_count=len(repeat_terms),
            vip_request_count=vip_count,
        )
        return ContentDemandSummary(
            total_requests=total,
            matched_requests=matched,
            unmatched_requests=unmatched,
            matched_percentage=matched_percentage,
            unmet_percentage=unmet_percentage,
            repeat_request_count=len(repeat_terms),
            vip_request_count=vip_count,
            unique_customers=unique_customers,
            demand_by_content_type=content_type_counts,
            demand_by_format=format_counts,
            demand_by_customer_segment=segment_counts,
            opportunity_health=health,
            evidence={
                "source": "content_opportunity",
                "business_learning_ready": True,
                "recommendations_generated": False,
                "matched_signal_ids": tuple(sorted(matched_signal_ids)),
                "repeat_demand_terms": dict(repeat_terms),
            },
        )

    def summarize_topic(self, terms: Iterable[str] | str) -> ContentDemandTopicSummary:
        """Return demand intelligence for one normalized topic."""

        if isinstance(terms, str):
            normalized = self._normalized_terms(terms, None)
        else:
            normalized = self._normalized_terms("", terms)
        key = self._terms_key(normalized)
        summaries = self._topic_summaries()
        return summaries.get(key) or ContentDemandTopicSummary(
            topic_key=key,
            terms=tuple(sorted(normalized)),
            trend=ContentDemandTrend.UNKNOWN,
            opportunity_health=ContentOpportunityHealth.UNKNOWN,
        )

    def summarize_customer_segment(self, segment: str) -> Mapping[str, Any]:
        """Summarize demand from one provider-neutral customer segment."""

        normalized_segment = self._clean_text(segment) or "unknown"
        signals = tuple(
            signal
            for signal in self._signals
            if normalized_segment in self._signal_segments(signal)
        )
        matched_signal_ids = self._matched_signal_ids()
        matched = sum(1 for signal in signals if signal.signal_id in matched_signal_ids)
        unmatched = len(signals) - matched
        topics = {
            self._terms_key(signal.normalized_terms)
            for signal in signals
            if self._terms_key(signal.normalized_terms)
        }
        return {
            "segment": normalized_segment,
            "request_count": len(signals),
            "matched_requests": matched,
            "unmatched_requests": unmatched,
            "matched_percentage": self._percentage(matched, len(signals)),
            "unmet_percentage": self._percentage(unmatched, len(signals)),
            "unique_customers": len(self._customer_keys(signals)),
            "topic_count": len(topics),
            "evidence_only": True,
        }

    def summarize_matched_demand(self) -> Mapping[str, Any]:
        summary = self.summarize_demand()
        return {
            "matched_requests": summary.matched_requests,
            "matched_percentage": summary.matched_percentage,
            "matched_topics": tuple(
                topic.topic_key
                for topic in self._topic_summaries().values()
                if topic.matched_count
            ),
            "evidence_only": True,
        }

    def summarize_unmatched_demand(self) -> Mapping[str, Any]:
        summary = self.summarize_demand()
        return {
            "unmatched_requests": summary.unmatched_requests,
            "unmet_percentage": summary.unmet_percentage,
            "unsatisfied_topics": tuple(
                topic.topic_key
                for topic in self._topic_summaries().values()
                if topic.unmatched_count
            ),
            "evidence_only": True,
        }

    def summarize_vip_demand(self) -> Mapping[str, Any]:
        topics = tuple(
            topic
            for topic in self._topic_summaries().values()
            if topic.vip_request_count
        )
        return {
            "vip_request_count": sum(topic.vip_request_count for topic in topics),
            "vip_topics": tuple(topic.topic_key for topic in topics),
            "highest_priority_topics": tuple(
                topic.topic_key
                for topic in topics
                if topic.priority in {
                    ContentOpportunityPriority.HIGH,
                    ContentOpportunityPriority.CRITICAL,
                }
            ),
            "evidence_only": True,
        }

    def summarize_repeat_demand(self) -> Mapping[str, Any]:
        repeat_terms = self._repeat_demand_terms()
        return {
            "repeat_request_count": len(repeat_terms),
            "repeat_demand_terms": dict(repeat_terms),
            "repeat_topics": tuple(repeat_terms.keys()),
            "evidence_only": True,
        }

    def summarize_trending_topics(self) -> tuple[ContentDemandTopicSummary, ...]:
        """Return topic summaries ordered by demand strength and priority."""

        return tuple(
            sorted(
                self._topic_summaries().values(),
                key=lambda topic: (
                    self._priority_rank(topic.priority),
                    topic.request_count,
                    topic.vip_request_count,
                    topic.unique_customers,
                    topic.topic_key,
                ),
                reverse=True,
            )
        )

    def generate_creator_recommendations(
        self,
    ) -> tuple[ContentOpportunityRecommendation, ...]:
        """Generate advisory creator recommendations from demand intelligence."""

        recommendations: list[ContentOpportunityRecommendation] = []
        recommendations.extend(self.recommend_from_unmatched_demand())
        recommendations.extend(self.recommend_from_matched_demand())
        recommendations.extend(self.recommend_from_vip_demand())
        recommendations.extend(self.recommend_from_format_demand())
        return self.rank_content_opportunity_recommendations(recommendations)

    def recommend_from_unmatched_demand(
        self,
    ) -> tuple[ContentOpportunityRecommendation, ...]:
        recommendations: list[ContentOpportunityRecommendation] = []
        for topic in self.summarize_trending_topics():
            if topic.unmatched_count <= 0:
                continue
            rec_type = self._creative_recommendation_type(topic)
            recommendations.append(
                self._recommendation(
                    topic=topic,
                    recommendation_type=rec_type,
                    title=self._creative_title(topic, rec_type),
                    summary=(
                        f"Customers are asking for {self._topic_label(topic)}. "
                        "Consider reviewing whether new content would fit the creator's direction."
                    ),
                    priority=self._recommendation_priority(topic),
                    confidence=self._recommendation_confidence(topic, base=0.58),
                    related=self._related_content_for_topic(topic.topic_key),
                )
            )
        return tuple(recommendations)

    def recommend_from_matched_demand(
        self,
    ) -> tuple[ContentOpportunityRecommendation, ...]:
        recommendations: list[ContentOpportunityRecommendation] = []
        for topic in self.summarize_trending_topics():
            if topic.matched_count <= 0:
                continue
            related = self._related_content_for_topic(topic.topic_key)
            if self._has_blocked_publishing(topic.topic_key):
                recommendations.append(
                    self._recommendation(
                        topic=topic,
                        recommendation_type=(
                            ContentOpportunityRecommendationType.IMPROVE_PUBLISHING_READINESS
                        ),
                        title=f"Review publishing readiness for {self._topic_label(topic)}",
                        summary=(
                            "Existing content appears relevant, but publishing readiness needs review "
                            "before the creator relies on it."
                        ),
                        priority=ContentOpportunityRecommendationPriority.HIGH,
                        confidence=self._recommendation_confidence(topic, base=0.62),
                        related=related,
                    )
                )
                continue
            recommendation_type = (
                ContentOpportunityRecommendationType.PROMOTE_EXISTING_PRODUCT_WITH_DEMAND
                if related["product_ids"]
                else ContentOpportunityRecommendationType.REUSE_EXISTING_MATCHED_PRODUCT
            )
            recommendations.append(
                self._recommendation(
                    topic=topic,
                    recommendation_type=recommendation_type,
                    title=f"Reuse matched content for {self._topic_label(topic)}",
                    summary=(
                        "Existing content is matching customer demand. "
                        "Worth reviewing for creator-led promotion or reuse."
                    ),
                    priority=ContentOpportunityRecommendationPriority.NORMAL,
                    confidence=self._recommendation_confidence(topic, base=0.52),
                    related=related,
                )
            )
        return tuple(recommendations)

    def recommend_from_vip_demand(
        self,
    ) -> tuple[ContentOpportunityRecommendation, ...]:
        recommendations: list[ContentOpportunityRecommendation] = []
        for topic in self.summarize_trending_topics():
            if topic.vip_request_count <= 0:
                continue
            recommendations.append(
                self._recommendation(
                    topic=topic,
                    recommendation_type=self._creative_recommendation_type(topic),
                    title=f"Review VIP demand for {self._topic_label(topic)}",
                    summary=(
                        "VIP customer demand is present. Consider prioritizing creator review "
                        "while keeping the response advisory."
                    ),
                    priority=(
                        ContentOpportunityRecommendationPriority.CRITICAL
                        if topic.unmatched_count
                        else ContentOpportunityRecommendationPriority.HIGH
                    ),
                    confidence=self._recommendation_confidence(topic, base=0.66),
                    related=self._related_content_for_topic(topic.topic_key),
                )
            )
        return tuple(recommendations)

    def recommend_from_format_demand(
        self,
    ) -> tuple[ContentOpportunityRecommendation, ...]:
        recommendations: list[ContentOpportunityRecommendation] = []
        for topic in self.summarize_trending_topics():
            requested_format = self._primary_mapping_key(topic.requested_formats)
            if not requested_format:
                continue
            recommendation_type = self._format_recommendation_type(requested_format)
            if recommendation_type is None:
                continue
            recommendations.append(
                self._recommendation(
                    topic=topic,
                    recommendation_type=recommendation_type,
                    title=f"Consider {requested_format} content for {self._topic_label(topic)}",
                    summary=(
                        f"Customers are repeatedly asking for {requested_format} format content "
                        f"around {self._topic_label(topic)}."
                    ),
                    priority=self._recommendation_priority(topic),
                    confidence=self._recommendation_confidence(topic, base=0.55),
                    related=self._related_content_for_topic(topic.topic_key),
                    requested_format=requested_format,
                )
            )
        return tuple(recommendations)

    def rank_content_opportunity_recommendations(
        self,
        recommendations: Iterable[ContentOpportunityRecommendation],
    ) -> tuple[ContentOpportunityRecommendation, ...]:
        by_key: dict[tuple[str, str], ContentOpportunityRecommendation] = {}
        for recommendation in recommendations:
            key = (
                recommendation.evidence.topic_key,
                recommendation.recommendation_type.value,
            )
            existing = by_key.get(key)
            if existing is None or self._recommendation_rank(
                recommendation.priority
            ) > self._recommendation_rank(existing.priority):
                by_key[key] = recommendation
        ordered = sorted(
            by_key.values(),
            key=lambda item: (
                self._recommendation_rank(item.priority),
                item.request_count,
                item.vip_customer_count,
                item.unmatched_request_count,
                item.confidence,
                item.recommendation_id,
            ),
            reverse=True,
        )
        return tuple(
            replace(
                item,
                recommendation_id=f"content-opportunity-rec-{index + 1}",
            )
            for index, item in enumerate(ordered)
        )

    def resolve_opportunities_for_product(
        self,
        product: Mapping[str, Any] | Any,
        *,
        confidence_threshold: float = 0.5,
        notes: Iterable[str] | None = None,
    ) -> tuple[ContentOpportunityResolution, ...]:
        return self._resolve_opportunities_for_candidate(
            candidate=product,
            source=ContentOpportunityResolutionSource.PRODUCT,
            confidence_threshold=confidence_threshold,
            notes=notes,
        )

    def resolve_opportunities_for_experience(
        self,
        experience: Mapping[str, Any] | Any,
        *,
        confidence_threshold: float = 0.5,
        notes: Iterable[str] | None = None,
    ) -> tuple[ContentOpportunityResolution, ...]:
        return self._resolve_opportunities_for_candidate(
            candidate=experience,
            source=ContentOpportunityResolutionSource.EXPERIENCE,
            confidence_threshold=confidence_threshold,
            notes=notes,
        )

    def resolve_opportunities_for_asset(
        self,
        asset: Mapping[str, Any] | Any,
        *,
        confidence_threshold: float = 0.5,
        notes: Iterable[str] | None = None,
    ) -> tuple[ContentOpportunityResolution, ...]:
        return self._resolve_opportunities_for_candidate(
            candidate=asset,
            source=ContentOpportunityResolutionSource.ASSET,
            confidence_threshold=confidence_threshold,
            notes=notes,
        )

    def resolve_opportunities_for_new_content(
        self,
        *,
        product: Mapping[str, Any] | Any | None = None,
        experience: Mapping[str, Any] | Any | None = None,
        asset: Mapping[str, Any] | Any | None = None,
        confidence_threshold: float = 0.5,
        notes: Iterable[str] | None = None,
    ) -> tuple[ContentOpportunityResolution, ...]:
        resolutions: list[ContentOpportunityResolution] = []
        if product is not None:
            resolutions.extend(
                self.resolve_opportunities_for_product(
                    product,
                    confidence_threshold=confidence_threshold,
                    notes=notes,
                )
            )
        if experience is not None:
            resolutions.extend(
                self.resolve_opportunities_for_experience(
                    experience,
                    confidence_threshold=confidence_threshold,
                    notes=notes,
                )
            )
        if asset is not None:
            resolutions.extend(
                self.resolve_opportunities_for_asset(
                    asset,
                    confidence_threshold=confidence_threshold,
                    notes=notes,
                )
            )
        return tuple(resolutions)

    def record_new_product_available(
        self,
        product: Mapping[str, Any] | Any,
        *,
        create_follow_ups: bool = True,
    ) -> tuple[ContentOpportunityFollowUp, ...]:
        """Resolve prior demand for a newly available Product without messaging."""

        resolutions = self.resolve_opportunities_for_product(
            product,
            notes=("New Product availability notification.",),
        )
        if not create_follow_ups:
            return ()
        return tuple(
            follow_up
            for resolution in resolutions
            for follow_up in self.create_follow_up_opportunities(resolution)
        )

    def record_new_experience_available(
        self,
        experience: Mapping[str, Any] | Any,
        *,
        create_follow_ups: bool = True,
    ) -> tuple[ContentOpportunityFollowUp, ...]:
        """Resolve prior demand for a newly available Experience without messaging."""

        resolutions = self.resolve_opportunities_for_experience(
            experience,
            notes=("New Experience availability notification.",),
        )
        if not create_follow_ups:
            return ()
        return tuple(
            follow_up
            for resolution in resolutions
            for follow_up in self.create_follow_up_opportunities(resolution)
        )

    def record_new_asset_available(
        self,
        asset: Mapping[str, Any] | Any,
        *,
        create_follow_ups: bool = True,
    ) -> tuple[ContentOpportunityFollowUp, ...]:
        """Resolve prior demand for a newly available Asset without messaging."""

        resolutions = self.resolve_opportunities_for_asset(
            asset,
            notes=("New Asset availability notification.",),
        )
        if not create_follow_ups:
            return ()
        return tuple(
            follow_up
            for resolution in resolutions
            for follow_up in self.create_follow_up_opportunities(resolution)
        )

    def find_waiting_customers(
        self,
        opportunity: ContentOpportunity | str,
    ) -> tuple[Mapping[str, Any], ...]:
        topic_key = (
            self._terms_key(opportunity.normalized_terms)
            if isinstance(opportunity, ContentOpportunity)
            else str(opportunity)
        )
        matched_signal_ids = self._matched_signal_ids()
        waiting = []
        for signal in self._signals:
            if self._terms_key(signal.normalized_terms) != topic_key:
                continue
            if signal.signal_id in matched_signal_ids:
                continue
            waiting.append(
                {
                    "customer_id": signal.customer_id,
                    "provider": signal.provider,
                    "provider_customer_id": signal.provider_customer_id,
                    "is_vip": signal.is_vip,
                    "customer_importance": signal.customer_importance,
                    "request_text": signal.request_text,
                    "requested_at": signal.created_at,
                    "signal_id": signal.signal_id,
                    "source": signal.source.value,
                }
            )
        return tuple(waiting)

    def build_resolution_record(
        self,
        *,
        opportunity: ContentOpportunity,
        matched_product_ids: Iterable[str | int] = (),
        matched_experience_ids: Iterable[str | int] = (),
        matched_asset_ids: Iterable[str | int] = (),
        confidence: float = 0.0,
        evidence: Mapping[str, Any] | None = None,
        source: ContentOpportunityResolutionSource = (
            ContentOpportunityResolutionSource.UNKNOWN
        ),
        status: ContentOpportunityResolutionStatus = (
            ContentOpportunityResolutionStatus.RESOLUTION_READY
        ),
        notes: Iterable[str] | None = None,
    ) -> ContentOpportunityResolution:
        waiting_customers = self.find_waiting_customers(opportunity)
        customer_ids = self._dedupe(
            item.get("customer_id")
            for item in waiting_customers
            if item.get("customer_id")
        )
        provider_customer_ids = self._dedupe(
            item.get("provider_customer_id")
            for item in waiting_customers
            if item.get("provider_customer_id")
        )
        vip_count = sum(1 for item in waiting_customers if item.get("is_vip"))
        return ContentOpportunityResolution(
            resolution_id=f"content-resolution-{len(self._resolutions) + 1}",
            opportunity_id=opportunity.opportunity_id,
            normalized_terms=opportunity.normalized_terms,
            matched_product_ids=self._text_tuple(matched_product_ids),
            matched_experience_ids=self._text_tuple(matched_experience_ids),
            matched_asset_ids=self._text_tuple(matched_asset_ids),
            waiting_customer_ids=customer_ids,
            waiting_provider_customer_ids=provider_customer_ids,
            request_count=len(waiting_customers),
            customer_count=len(customer_ids or provider_customer_ids),
            vip_customer_count=vip_count,
            confidence=self._bounded_confidence(confidence),
            evidence={
                "source": "content_opportunity_resolution",
                "waiting_customers": waiting_customers,
                "resolution_guidance": dict(self.RESOLUTION_GUIDANCE),
                **dict(evidence or {}),
            },
            status=status,
            source=source,
            safe_guidance=dict(self.RESOLUTION_GUIDANCE),
            notes=tuple(notes or ()),
            metadata={
                "read_only": True,
                "advisory_only": True,
                "provider_neutral": True,
                "contacts_customers": False,
                "executes_offers": False,
                "generates_customer_facing_text": False,
                "creates_products": False,
                "creates_experiences": False,
                "creates_assets": False,
                "modifies_publishing": False,
                "modifies_customer_intelligence": False,
                "modifies_business_learning": False,
                "changes_decision_engine_behavior": False,
            },
        )

    def list_resolution_ready_opportunities(
        self,
    ) -> tuple[ContentOpportunityResolution, ...]:
        return tuple(
            resolution
            for resolution in self._resolutions
            if resolution.status
            in {
                ContentOpportunityResolutionStatus.RESOLUTION_READY,
                ContentOpportunityResolutionStatus.FOLLOW_UP_PENDING,
            }
        )

    def create_follow_up_opportunities(
        self,
        resolution: ContentOpportunityResolution | str,
        *,
        status: ContentOpportunityFollowUpStatus = ContentOpportunityFollowUpStatus.READY,
    ) -> tuple[ContentOpportunityFollowUp, ...]:
        resolved = self._resolve_resolution(resolution)
        if resolved is None:
            return ()
        waiting_customers = tuple(
            self._read(resolved.evidence, "waiting_customers") or ()
        )
        follow_ups = tuple(
            self.create_follow_up_for_customer(
                resolution=resolved,
                waiting_customer=waiting_customer,
                status=status,
            )
            for waiting_customer in waiting_customers
        )
        if follow_ups and resolved.status == ContentOpportunityResolutionStatus.RESOLUTION_READY:
            self._record_resolution(
                replace(
                    resolved,
                    status=ContentOpportunityResolutionStatus.FOLLOW_UP_PENDING,
                    updated_at=utc_now(),
                )
            )
        return follow_ups

    def create_follow_up_for_customer(
        self,
        *,
        resolution: ContentOpportunityResolution,
        waiting_customer: Mapping[str, Any] | Any,
        status: ContentOpportunityFollowUpStatus = ContentOpportunityFollowUpStatus.READY,
    ) -> ContentOpportunityFollowUp:
        signal_id = self._text(self._read(waiting_customer, "signal_id"))
        topic_key = self._terms_key(resolution.normalized_terms)
        existing_index = next(
            (
                index
                for index, item in enumerate(self._follow_ups)
                if item.resolution_id == resolution.resolution_id
                and item.evidence.get("signal_id") == signal_id
            ),
            None,
        )
        vip = bool(self._read(waiting_customer, "is_vip"))
        customer_id = self._text(self._read(waiting_customer, "customer_id"))
        provider_customer_id = self._text(
            self._read(waiting_customer, "provider_customer_id")
        )
        follow_up = ContentOpportunityFollowUp(
            follow_up_id=f"content-follow-up-{len(self._follow_ups) + 1}",
            resolution_id=resolution.resolution_id,
            opportunity_id=resolution.opportunity_id,
            customer_id=customer_id,
            provider=self._text(self._read(waiting_customer, "provider")) or "provider_neutral",
            provider_customer_id=provider_customer_id,
            matched_product_ids=resolution.matched_product_ids,
            matched_experience_ids=resolution.matched_experience_ids,
            matched_asset_ids=resolution.matched_asset_ids,
            original_request_text=self._text(
                self._read(waiting_customer, "request_text")
            )
            or "",
            normalized_terms=resolution.normalized_terms,
            vip_customer=vip,
            priority=self._follow_up_priority(
                resolution=resolution,
                vip_customer=vip,
                signal_id=signal_id,
                customer_id=customer_id,
                provider_customer_id=provider_customer_id,
            ),
            confidence=resolution.confidence,
            evidence={
                "source": "content_opportunity_follow_up",
                "resolution_id": resolution.resolution_id,
                "opportunity_id": resolution.opportunity_id,
                "signal_id": signal_id,
                "topic_key": topic_key,
                "request_count": resolution.request_count,
                "customer_count": resolution.customer_count,
                "vip_customer_count": resolution.vip_customer_count,
                "resolution_evidence": dict(resolution.evidence),
                "read_only": True,
            },
            status=status,
            safe_guidance=dict(self.FOLLOW_UP_GUIDANCE),
            metadata={
                "read_only": True,
                "advisory_only": True,
                "provider_neutral": True,
                "sends_messages": False,
                "creates_offers": False,
                "executes_telegram": False,
                "changes_decision_engine_behavior": False,
                "modifies_products": False,
                "modifies_customer_intelligence": False,
            },
        )
        if existing_index is None:
            self._follow_ups.append(follow_up)
            self._persist_records()
            return follow_up
        previous = self._follow_ups[existing_index]
        updated = replace(
            follow_up,
            follow_up_id=previous.follow_up_id,
            created_at=previous.created_at,
            updated_at=utc_now(),
        )
        self._follow_ups[existing_index] = updated
        self._persist_records()
        return updated

    def list_pending_follow_ups(self) -> tuple[ContentOpportunityFollowUp, ...]:
        return tuple(
            item
            for item in self._follow_ups
            if item.status == ContentOpportunityFollowUpStatus.PENDING
        )

    def list_ready_follow_ups(self) -> tuple[ContentOpportunityFollowUp, ...]:
        return tuple(
            item
            for item in self._follow_ups
            if item.status == ContentOpportunityFollowUpStatus.READY
        )

    def _waiting_customers_for_dashboard(self) -> tuple[Mapping[str, Any], ...]:
        waiting: list[Mapping[str, Any]] = []
        seen: set[tuple[str | None, str | None, str]] = set()
        for resolution in self._resolutions:
            for customer in tuple(self._read(resolution.evidence, "waiting_customers") or ()):
                customer_id = self._text(self._read(customer, "customer_id"))
                provider_customer_id = self._text(
                    self._read(customer, "provider_customer_id")
                )
                key = (
                    customer_id,
                    provider_customer_id,
                    resolution.resolution_id,
                )
                if key in seen:
                    continue
                seen.add(key)
                waiting.append(
                    {
                        "customer_id": customer_id,
                        "provider": self._text(self._read(customer, "provider"))
                        or "provider_neutral",
                        "provider_customer_id": provider_customer_id,
                        "is_vip": bool(self._read(customer, "is_vip")),
                        "request_text": self._text(
                            self._read(customer, "request_text")
                        )
                        or "",
                        "resolution_id": resolution.resolution_id,
                        "opportunity_id": resolution.opportunity_id,
                        "status": resolution.status.value,
                        "source": "ContentOpportunityService",
                    }
                )
        follow_up_keys = {
            (item.customer_id, item.provider_customer_id, item.resolution_id)
            for item in self._follow_ups
        }
        for item in self._follow_ups:
            key = (item.customer_id, item.provider_customer_id, item.resolution_id)
            if key not in follow_up_keys:
                continue
            waiting.append(
                {
                    "customer_id": item.customer_id,
                    "provider": item.provider,
                    "provider_customer_id": item.provider_customer_id,
                    "is_vip": item.vip_customer,
                    "request_text": item.original_request_text,
                    "resolution_id": item.resolution_id,
                    "opportunity_id": item.opportunity_id,
                    "status": item.status.value,
                    "source": "ContentOpportunityFollowUp",
                }
            )
            follow_up_keys.remove(key)
        return tuple(waiting)

    def complete_follow_up(
        self,
        follow_up_id: str,
    ) -> ContentOpportunityFollowUp | None:
        return self._update_follow_up_status(
            follow_up_id,
            ContentOpportunityFollowUpStatus.COMPLETED,
            completed=True,
        )

    def ignore_follow_up(
        self,
        follow_up_id: str,
    ) -> ContentOpportunityFollowUp | None:
        return self._update_follow_up_status(
            follow_up_id,
            ContentOpportunityFollowUpStatus.IGNORED,
        )

    def expire_follow_up(
        self,
        follow_up_id: str,
    ) -> ContentOpportunityFollowUp | None:
        return self._update_follow_up_status(
            follow_up_id,
            ContentOpportunityFollowUpStatus.EXPIRED,
        )

    def _resolve_opportunities_for_candidate(
        self,
        *,
        candidate: Mapping[str, Any] | Any,
        source: ContentOpportunityResolutionSource,
        confidence_threshold: float,
        notes: Iterable[str] | None,
    ) -> tuple[ContentOpportunityResolution, ...]:
        resolutions: list[ContentOpportunityResolution] = []
        for opportunity in self._unresolved_opportunities():
            match = self._resolution_candidate_match(
                opportunity=opportunity,
                candidate=candidate,
                source=source,
            )
            if match is None:
                continue
            confidence = float(match.get("confidence") or 0.0)
            if confidence < confidence_threshold:
                continue
            resolution = self.build_resolution_record(
                opportunity=opportunity,
                matched_product_ids=(
                    (match["id"],)
                    if source == ContentOpportunityResolutionSource.PRODUCT
                    else ()
                ),
                matched_experience_ids=(
                    (match["id"],)
                    if source == ContentOpportunityResolutionSource.EXPERIENCE
                    else ()
                ),
                matched_asset_ids=(
                    (match["id"],)
                    if source == ContentOpportunityResolutionSource.ASSET
                    else ()
                ),
                confidence=confidence,
                evidence={
                    "candidate_match": match,
                    "confidence_threshold": confidence_threshold,
                    "resolution_source": source.value,
                },
                source=source,
                notes=notes,
            )
            self._record_resolution(resolution)
            resolutions.append(resolution)
        return tuple(resolutions)

    def _unresolved_opportunities(self) -> tuple[ContentOpportunity, ...]:
        resolved_ids = {
            resolution.opportunity_id
            for resolution in self._resolutions
            if resolution.status
            in {
                ContentOpportunityResolutionStatus.RESOLUTION_READY,
                ContentOpportunityResolutionStatus.RESOLVED,
                ContentOpportunityResolutionStatus.FOLLOW_UP_PENDING,
                ContentOpportunityResolutionStatus.FOLLOW_UP_CREATED,
            }
        }
        return tuple(
            opportunity
            for opportunity in self._opportunities
            if opportunity.status == ContentOpportunityStatus.UNMATCHED
            and opportunity.opportunity_id not in resolved_ids
        )

    def _resolution_candidate_match(
        self,
        *,
        opportunity: ContentOpportunity,
        candidate: Mapping[str, Any] | Any,
        source: ContentOpportunityResolutionSource,
    ) -> Mapping[str, Any] | None:
        if source == ContentOpportunityResolutionSource.PRODUCT:
            product = self._read(candidate, "product") or candidate
            return self._match_candidate(
                candidate=product,
                terms=opportunity.normalized_terms,
                id_names=("product_id", "id"),
                source="ProductCatalogService",
                domain="product",
                weighted_fields=(
                    ("tags", 0.28),
                    ("themes", 0.25),
                    ("keywords", 0.22),
                    ("display_name", 0.2),
                    ("internal_name", 0.18),
                    ("name", 0.18),
                    ("title", 0.18),
                    ("description", 0.14),
                    ("product_type", 0.12),
                    ("delivery_type", 0.08),
                ),
                extra_evidence={
                    "publishing_readiness": self._safe_public_mapping(
                        self._read(candidate, "publishing")
                        or self._read(product, "publishing_readiness")
                    ),
                    "status": self._safe_public_value(self._read(product, "status")),
                    "resolution_owner": "ContentOpportunityService",
                },
            )
        if source == ContentOpportunityResolutionSource.EXPERIENCE:
            return self._match_candidate(
                candidate=candidate,
                terms=opportunity.normalized_terms,
                id_names=("experience_id", "id"),
                source="ExperienceService",
                domain="experience",
                weighted_fields=(
                    ("themes", 0.28),
                    ("keywords", 0.25),
                    ("title", 0.22),
                    ("name", 0.2),
                    ("summary", 0.18),
                    ("description", 0.16),
                    ("experience_type", 0.12),
                ),
                extra_evidence={"resolution_owner": "ContentOpportunityService"},
            )
        if source == ContentOpportunityResolutionSource.ASSET:
            return self._match_candidate(
                candidate=candidate,
                terms=opportunity.normalized_terms,
                id_names=("asset_id", "id"),
                source="ContentIntelligenceService",
                domain="asset",
                weighted_fields=(
                    ("themes", 0.25),
                    ("keywords", 0.25),
                    ("activities", 0.18),
                    ("environment", 0.16),
                    ("mood", 0.14),
                    ("clothing", 0.14),
                    ("classification", 0.12),
                    ("tags", 0.12),
                    ("summary", 0.1),
                ),
                extra_evidence={"resolution_owner": "ContentOpportunityService"},
            )
        return None

    def _record_resolution(
        self,
        resolution: ContentOpportunityResolution,
    ) -> ContentOpportunityResolution:
        existing_index = next(
            (
                index
                for index, item in enumerate(self._resolutions)
                if item.opportunity_id == resolution.opportunity_id
                and item.source == resolution.source
                and item.matched_product_ids == resolution.matched_product_ids
                and item.matched_experience_ids == resolution.matched_experience_ids
                and item.matched_asset_ids == resolution.matched_asset_ids
            ),
            None,
        )
        if existing_index is None:
            self._resolutions.append(resolution)
            self._persist_records()
            return resolution
        previous = self._resolutions[existing_index]
        updated = replace(
            resolution,
            resolution_id=previous.resolution_id,
            created_at=previous.created_at,
            updated_at=utc_now(),
        )
        self._resolutions[existing_index] = updated
        self._persist_records()
        return updated

    def _resolve_resolution(
        self,
        resolution: ContentOpportunityResolution | str,
    ) -> ContentOpportunityResolution | None:
        if isinstance(resolution, ContentOpportunityResolution):
            return resolution
        resolution_id = str(resolution)
        return next(
            (
                item
                for item in self._resolutions
                if item.resolution_id == resolution_id
            ),
            None,
        )

    def _follow_up_priority(
        self,
        *,
        resolution: ContentOpportunityResolution,
        vip_customer: bool,
        signal_id: str | None,
        customer_id: str | None,
        provider_customer_id: str | None,
    ) -> ContentOpportunityFollowUpPriority:
        same_customer_requests = sum(
            1
            for signal in self._signals
            if (
                (customer_id and signal.customer_id == customer_id)
                or (
                    provider_customer_id
                    and signal.provider_customer_id == provider_customer_id
                )
            )
            and self._terms_key(signal.normalized_terms)
            == self._terms_key(resolution.normalized_terms)
        )
        if vip_customer and resolution.request_count > 1:
            return ContentOpportunityFollowUpPriority.CRITICAL
        if vip_customer or same_customer_requests > 1 or resolution.confidence >= 0.85:
            return ContentOpportunityFollowUpPriority.HIGH
        if resolution.request_count > 1 or resolution.confidence >= 0.65:
            return ContentOpportunityFollowUpPriority.NORMAL
        return ContentOpportunityFollowUpPriority.LOW

    def _update_follow_up_status(
        self,
        follow_up_id: str,
        status: ContentOpportunityFollowUpStatus,
        *,
        completed: bool = False,
    ) -> ContentOpportunityFollowUp | None:
        index = next(
            (
                index
                for index, item in enumerate(self._follow_ups)
                if item.follow_up_id == follow_up_id
            ),
            None,
        )
        if index is None:
            return None
        current = self._follow_ups[index]
        updated = replace(
            current,
            status=status,
            updated_at=utc_now(),
            completed_at=utc_now() if completed else current.completed_at,
        )
        self._follow_ups[index] = updated
        self._persist_records()
        return updated

    def _recommendation(
        self,
        *,
        topic: ContentDemandTopicSummary,
        recommendation_type: ContentOpportunityRecommendationType,
        title: str,
        summary: str,
        priority: ContentOpportunityRecommendationPriority,
        confidence: float,
        related: Mapping[str, tuple[str, ...]],
        requested_format: str | None = None,
    ) -> ContentOpportunityRecommendation:
        content_type = self._primary_mapping_key(topic.requested_content_types)
        output_format = requested_format or self._primary_mapping_key(topic.requested_formats)
        evidence = ContentOpportunityRecommendationEvidence(
            topic_key=topic.topic_key,
            request_count=topic.request_count,
            customer_count=topic.unique_customers,
            vip_customer_count=topic.vip_request_count,
            matched_request_count=topic.matched_count,
            unmatched_request_count=topic.unmatched_count,
            matched_percentage=topic.matched_percentage,
            unmet_percentage=topic.unmet_percentage,
            customer_segments=dict(topic.customer_segments),
            requested_formats=dict(topic.requested_formats),
            requested_content_types=dict(topic.requested_content_types),
            match_statistics={
                "trend": topic.trend.value,
                "opportunity_health": topic.opportunity_health.value,
                "priority": topic.priority.value,
            },
            metadata={
                "read_only": True,
                "advisory_only": True,
                "business_learning_ready": True,
                "recommendation_owner": "ContentOpportunityService",
            },
        )
        return ContentOpportunityRecommendation(
            recommendation_id=self._recommendation_id(
                recommendation_type,
                topic.topic_key,
            ),
            recommendation_type=recommendation_type,
            title=title,
            summary=summary,
            normalized_terms=topic.terms,
            requested_content_type=content_type,
            requested_format=output_format,
            priority=priority,
            confidence=self._bounded_confidence(confidence),
            evidence=evidence,
            related_opportunity_ids=related["opportunity_ids"],
            related_product_ids=related["product_ids"],
            related_experience_ids=related["experience_ids"],
            related_asset_ids=related["asset_ids"],
            customer_count=topic.unique_customers,
            vip_customer_count=topic.vip_request_count,
            request_count=topic.request_count,
            matched_request_count=topic.matched_count,
            unmatched_request_count=topic.unmatched_count,
            safe_creator_note=(
                "Advisory only. Consider demand signals without making customer commitments."
            ),
            created_at=self._topic_created_at(topic.topic_key),
            metadata={
                "read_only": True,
                "advisory_only": True,
                "provider_neutral": True,
                "creates_products": False,
                "creates_experiences": False,
                "creates_assets": False,
                "modifies_publishing": False,
                "executes_offers": False,
                "notifies_customers": False,
                "generates_customer_facing_text": False,
                "modifies_business_learning": False,
                "modifies_business_optimization": False,
            },
        )

    def _topic_created_at(self, topic_key: str):
        created_values = tuple(
            signal.created_at
            for signal in self._signals
            if self._terms_key(signal.normalized_terms) == topic_key
        )
        return min(created_values) if created_values else utc_now()

    def _related_content_for_topic(self, topic_key: str) -> dict[str, tuple[str, ...]]:
        opportunities = tuple(
            opportunity
            for opportunity in self._opportunities
            if self._terms_key(opportunity.normalized_terms) == topic_key
        )
        return {
            "opportunity_ids": self._dedupe(
                opportunity.opportunity_id for opportunity in opportunities
            ),
            "product_ids": self._dedupe(
                product_id
                for opportunity in opportunities
                for product_id in opportunity.product_ids
            ),
            "experience_ids": self._dedupe(
                experience_id
                for opportunity in opportunities
                for experience_id in opportunity.experience_ids
            ),
            "asset_ids": self._dedupe(
                asset_id
                for opportunity in opportunities
                for asset_id in opportunity.asset_ids
            ),
        }

    def _has_blocked_publishing(self, topic_key: str) -> bool:
        for opportunity in self._opportunities:
            if self._terms_key(opportunity.normalized_terms) != topic_key:
                continue
            evidence = self._read(opportunity.supporting_evidence, "match_evidence")
            for match in self._read(evidence, "product_matches") or ():
                readiness = self._read(
                    self._read(match, "supporting_evidence"),
                    "publishing_readiness",
                )
                status = str(self._read(readiness, "status") or "").lower()
                attention = bool(self._read(readiness, "attention_required"))
                if attention or status in {
                    "blocked",
                    "failed",
                    "waiting_for_media_link",
                    "waiting",
                    "not_ready",
                }:
                    return True
        return False

    @staticmethod
    def _primary_mapping_key(values: Mapping[str, int]) -> str | None:
        if not values:
            return None
        return sorted(values.items(), key=lambda item: (item[1], item[0]), reverse=True)[0][0]

    @staticmethod
    def _creative_recommendation_type(
        topic: ContentDemandTopicSummary,
    ) -> ContentOpportunityRecommendationType:
        content_type = (
            ContentOpportunityService._primary_mapping_key(topic.requested_content_types)
            or ""
        ).lower()
        requested_format = (
            ContentOpportunityService._primary_mapping_key(topic.requested_formats)
            or ""
        ).lower()
        combined = " ".join((*topic.terms, content_type, requested_format)).lower()
        if "bundle" in combined:
            return ContentOpportunityRecommendationType.CREATE_BUNDLE
        if "story" in combined:
            return ContentOpportunityRecommendationType.CREATE_STORY
        if "video" in combined:
            return ContentOpportunityRecommendationType.CREATE_VIDEO
        if "free" in combined or "preview" in combined:
            return ContentOpportunityRecommendationType.CREATE_FREE_PREVIEW
        if "experience" in combined or "photoshoot" in combined:
            return ContentOpportunityRecommendationType.CREATE_NEW_EXPERIENCE
        return ContentOpportunityRecommendationType.CREATE_NEW_PRODUCT

    @staticmethod
    def _format_recommendation_type(
        requested_format: str,
    ) -> ContentOpportunityRecommendationType | None:
        text = requested_format.lower()
        if "video" in text:
            return ContentOpportunityRecommendationType.CREATE_VIDEO
        if "story" in text:
            return ContentOpportunityRecommendationType.CREATE_STORY
        if "bundle" in text:
            return ContentOpportunityRecommendationType.CREATE_BUNDLE
        if "free" in text or "preview" in text:
            return ContentOpportunityRecommendationType.CREATE_FREE_PREVIEW
        return None

    @staticmethod
    def _creative_title(
        topic: ContentDemandTopicSummary,
        recommendation_type: ContentOpportunityRecommendationType,
    ) -> str:
        label = ContentOpportunityService._topic_label(topic)
        titles = {
            ContentOpportunityRecommendationType.CREATE_NEW_EXPERIENCE: (
                f"Consider a new Experience for {label}"
            ),
            ContentOpportunityRecommendationType.CREATE_BUNDLE: (
                f"Consider a Bundle around {label}"
            ),
            ContentOpportunityRecommendationType.CREATE_STORY: (
                f"Consider a Story around {label}"
            ),
            ContentOpportunityRecommendationType.CREATE_VIDEO: (
                f"Consider video content for {label}"
            ),
            ContentOpportunityRecommendationType.CREATE_FREE_PREVIEW: (
                f"Consider a FREE preview for {label}"
            ),
        }
        return titles.get(
            recommendation_type,
            f"Consider new content for {label}",
        )

    @staticmethod
    def _topic_label(topic: ContentDemandTopicSummary) -> str:
        return ", ".join(topic.terms) if topic.terms else topic.topic_key

    @staticmethod
    def _recommendation_id(
        recommendation_type: ContentOpportunityRecommendationType,
        topic_key: str,
    ) -> str:
        clean = re.sub(r"[^a-z0-9]+", "-", topic_key.lower()).strip("-")
        return f"{recommendation_type.value.lower()}-{clean or 'topic'}"

    def _recommendation_priority(
        self,
        topic: ContentDemandTopicSummary,
    ) -> ContentOpportunityRecommendationPriority:
        if topic.vip_request_count and topic.unmatched_count:
            return ContentOpportunityRecommendationPriority.CRITICAL
        if topic.vip_request_count or topic.unmatched_count >= 2 or topic.unique_customers >= 3:
            return ContentOpportunityRecommendationPriority.HIGH
        if topic.request_count >= 2 or topic.unmatched_count:
            return ContentOpportunityRecommendationPriority.NORMAL
        return ContentOpportunityRecommendationPriority.LOW

    @staticmethod
    def _recommendation_confidence(
        topic: ContentDemandTopicSummary,
        *,
        base: float,
    ) -> float:
        confidence = base
        confidence += min(topic.request_count, 5) * 0.04
        confidence += min(topic.unique_customers, 5) * 0.03
        confidence += min(topic.vip_request_count, 3) * 0.06
        if topic.unmatched_count:
            confidence += 0.05
        if topic.matched_count:
            confidence += 0.04
        return ContentOpportunityService._bounded_confidence(confidence)

    @staticmethod
    def _recommendation_rank(
        priority: ContentOpportunityRecommendationPriority,
    ) -> int:
        return {
            ContentOpportunityRecommendationPriority.LOW: 1,
            ContentOpportunityRecommendationPriority.NORMAL: 2,
            ContentOpportunityRecommendationPriority.HIGH: 3,
            ContentOpportunityRecommendationPriority.CRITICAL: 4,
        }.get(priority, 0)

    def _topic_summaries(self) -> dict[str, ContentDemandTopicSummary]:
        matched_signal_ids = self._matched_signal_ids()
        signals_by_topic: dict[str, list[ContentDemandSignal]] = {}
        for signal in self._signals:
            key = self._terms_key(signal.normalized_terms)
            if key:
                signals_by_topic.setdefault(key, []).append(signal)

        summaries: dict[str, ContentDemandTopicSummary] = {}
        for key, signals in signals_by_topic.items():
            total = len(signals)
            matched = sum(1 for signal in signals if signal.signal_id in matched_signal_ids)
            unmatched = total - matched
            vip = sum(1 for signal in signals if signal.is_vip)
            unique_customers = len(self._customer_keys(signals))
            segment_counts = self._customer_segment_counts(signals)
            content_type_counts = self._count_signal_field(
                "requested_content_type",
                signals=signals,
            )
            format_counts = self._count_signal_field(
                "requested_format",
                signals=signals,
            )
            trend = self._topic_trend(
                request_count=total,
                matched_count=matched,
                unmatched_count=unmatched,
                unique_customers=unique_customers,
                vip_request_count=vip,
            )
            priority = self._topic_priority(
                request_count=total,
                unmatched_count=unmatched,
                unique_customers=unique_customers,
                vip_request_count=vip,
            )
            health = self._topic_health(
                request_count=total,
                unmatched_count=unmatched,
                vip_request_count=vip,
                priority=priority,
            )
            terms = tuple(sorted(set(term for signal in signals for term in signal.normalized_terms)))
            summaries[key] = ContentDemandTopicSummary(
                topic_key=key,
                terms=terms,
                request_count=total,
                matched_count=matched,
                unmatched_count=unmatched,
                matched_percentage=self._percentage(matched, total),
                unmet_percentage=self._percentage(unmatched, total),
                unique_customers=unique_customers,
                vip_request_count=vip,
                customer_segments=segment_counts,
                requested_content_types=content_type_counts,
                requested_formats=format_counts,
                trend=trend,
                priority=priority,
                opportunity_health=health,
                evidence={
                    "source": "content_opportunity",
                    "business_learning_ready": True,
                    "recommendations_generated": False,
                    "signal_ids": tuple(signal.signal_id for signal in signals),
                    "matched_signal_ids": tuple(
                        signal.signal_id
                        for signal in signals
                        if signal.signal_id in matched_signal_ids
                    ),
                },
            )
        return summaries

    def _matched_signal_ids(self) -> set[str]:
        return {
            match.demand_signal.signal_id
            for match in self._matches
            if match.demand_signal.signal_id
        }

    @classmethod
    def _customer_keys(
        cls,
        signals: Iterable[ContentDemandSignal],
    ) -> set[str]:
        keys = set()
        for signal in signals:
            key = signal.customer_id or signal.provider_customer_id
            if key:
                keys.add(str(key))
        return keys

    def _count_signal_field(
        self,
        field: str,
        *,
        signals: Iterable[ContentDemandSignal] | None = None,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for signal in tuple(signals) if signals is not None else tuple(self._signals):
            value = getattr(signal, field, None)
            if value:
                counts[str(value)] = counts.get(str(value), 0) + 1
        return counts

    def _customer_segment_counts(
        self,
        signals: Iterable[ContentDemandSignal],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for signal in signals:
            for segment in self._signal_segments(signal):
                counts[segment] = counts.get(segment, 0) + 1
        return counts

    def _signal_segments(self, signal: ContentDemandSignal) -> tuple[str, ...]:
        values = []
        for source in (signal.metadata, signal.source_metadata):
            for key in ("customer_segment", "segment", "customer_segments", "segments"):
                raw = self._read(source, key)
                values.extend(self._flatten_text(raw))
        if signal.is_vip:
            values.append("vip")
        normalized = tuple(
            dict.fromkeys(
                self._clean_text(value) or ""
                for value in values
                if self._clean_text(value)
            )
        )
        return normalized or ("unknown",)

    @staticmethod
    def _percentage(value: int, total: int) -> float:
        if total <= 0:
            return 0.0
        return round((value / total) * 100, 2)

    @staticmethod
    def _topic_trend(
        *,
        request_count: int,
        matched_count: int,
        unmatched_count: int,
        unique_customers: int,
        vip_request_count: int,
    ) -> ContentDemandTrend:
        if request_count <= 0:
            return ContentDemandTrend.UNKNOWN
        if unmatched_count >= 2:
            return ContentDemandTrend.UNSATISFIED
        if matched_count == request_count:
            return ContentDemandTrend.SATISFIED
        if request_count >= 2 or unique_customers >= 2 or vip_request_count:
            return ContentDemandTrend.GROWING
        return ContentDemandTrend.STABLE

    def _topic_priority(
        self,
        *,
        request_count: int,
        unmatched_count: int,
        unique_customers: int,
        vip_request_count: int,
    ) -> ContentOpportunityPriority:
        if vip_request_count and unmatched_count:
            return ContentOpportunityPriority.CRITICAL
        if vip_request_count or (unmatched_count >= 2 and unique_customers >= 2):
            return ContentOpportunityPriority.HIGH
        if request_count >= 2 or unmatched_count:
            return ContentOpportunityPriority.NORMAL
        return ContentOpportunityPriority.LOW

    @staticmethod
    def _topic_health(
        *,
        request_count: int,
        unmatched_count: int,
        vip_request_count: int,
        priority: ContentOpportunityPriority,
    ) -> ContentOpportunityHealth:
        if request_count <= 0:
            return ContentOpportunityHealth.UNKNOWN
        if priority == ContentOpportunityPriority.CRITICAL:
            return ContentOpportunityHealth.NEEDS_ATTENTION
        if unmatched_count >= 2 or vip_request_count:
            return ContentOpportunityHealth.HIGH_DEMAND
        if unmatched_count:
            return ContentOpportunityHealth.OPPORTUNITY
        return ContentOpportunityHealth.HEALTHY

    @staticmethod
    def _opportunity_health(
        *,
        total_requests: int,
        unmatched_requests: int,
        repeat_request_count: int,
        vip_request_count: int,
    ) -> ContentOpportunityHealth:
        if total_requests <= 0:
            return ContentOpportunityHealth.UNKNOWN
        if vip_request_count and unmatched_requests:
            return ContentOpportunityHealth.NEEDS_ATTENTION
        if repeat_request_count or unmatched_requests >= 2:
            return ContentOpportunityHealth.HIGH_DEMAND
        if unmatched_requests:
            return ContentOpportunityHealth.OPPORTUNITY
        return ContentOpportunityHealth.HEALTHY

    def _highest_priority_opportunities(
        self,
        opportunities: tuple[ContentOpportunity, ...],
    ) -> tuple[ContentOpportunity, ...]:
        return tuple(
            sorted(
                opportunities,
                key=lambda item: (
                    self._priority_rank(item.priority),
                    item.demand_count,
                    item.vip_demand,
                    item.status == ContentOpportunityStatus.UNMATCHED,
                    item.confidence,
                ),
                reverse=True,
            )[:5]
        )

    def _store_or_update_opportunity(
        self,
        opportunity: ContentOpportunity,
    ) -> ContentOpportunity:
        key = self._terms_key(opportunity.normalized_terms)
        existing_index = next(
            (
                index
                for index, item in enumerate(self._opportunities)
                if item.status == opportunity.status
                and self._terms_key(item.normalized_terms) == key
            ),
            None,
        )
        count = sum(
            1
            for signal in self._signals
            if self._terms_key(signal.normalized_terms) == key
        )
        stored = replace(
            opportunity,
            demand_count=max(1, count),
            repeat_demand=count > 1,
            updated_at=utc_now(),
        )
        if existing_index is None:
            self._opportunities.append(stored)
            self._persist_records()
            return stored
        previous = self._opportunities[existing_index]
        stored = replace(
            stored,
            opportunity_id=previous.opportunity_id,
            created_at=previous.created_at,
            priority=self._max_priority(previous.priority, stored.priority),
            vip_demand=previous.vip_demand or stored.vip_demand,
        )
        self._opportunities[existing_index] = stored
        self._persist_records()
        return stored

    def _repeat_demand_terms(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for signal in self._signals:
            key = self._terms_key(signal.normalized_terms)
            if key:
                counts[key] = counts.get(key, 0) + 1
        return {key: count for key, count in counts.items() if count > 1}

    def _next_actions(
        self,
        opportunities: tuple[ContentOpportunity, ...],
    ) -> tuple[str, ...]:
        ordered = sorted(
            opportunities,
            key=lambda item: (
                self._priority_rank(item.priority),
                item.demand_count,
                item.confidence,
            ),
            reverse=True,
        )
        actions = [item.next_recommended_action for item in ordered]
        return tuple(dict.fromkeys(actions)) or ("Monitor content demand",)

    def _resolve_match_evidence(
        self,
        *,
        request_text: str,
        normalized_terms: tuple[str, ...],
        creator_profile_id: int | None,
        product_candidates: Iterable[Mapping[str, Any] | Any] | None,
        experience_candidates: Iterable[Mapping[str, Any] | Any] | None,
        asset_candidates: Iterable[Mapping[str, Any] | Any] | None,
        asset_ids: Iterable[str | int] | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], float, dict[str, Any]]:
        product_matches = self.find_matching_products(
            request_text=request_text,
            normalized_terms=normalized_terms,
            creator_profile_id=creator_profile_id,
            product_candidates=product_candidates,
        )
        experience_matches = self.find_matching_experiences(
            request_text=request_text,
            normalized_terms=normalized_terms,
            creator_profile_id=creator_profile_id,
            experience_candidates=experience_candidates,
        )
        asset_matches = self.find_matching_assets(
            request_text=request_text,
            normalized_terms=normalized_terms,
            asset_candidates=asset_candidates,
            asset_ids=asset_ids,
        )
        product_ids = self._dedupe(
            str(match["id"]) for match in product_matches if match.get("id")
        )
        experience_ids = self._dedupe(
            str(match["id"]) for match in experience_matches if match.get("id")
        )
        matched_asset_ids = self._dedupe(
            str(match["id"]) for match in asset_matches if match.get("id")
        )
        confidence = self._aggregate_match_confidence(
            product_matches,
            experience_matches,
            asset_matches,
        )
        evidence = {
            "source": "content_opportunity_match_detection",
            "product_matches": product_matches,
            "experience_matches": experience_matches,
            "asset_matches": asset_matches,
            "domain_agreement_count": sum(
                bool(matches)
                for matches in (product_matches, experience_matches, asset_matches)
            ),
            "matching_owner": "ContentOpportunityService",
            "product_owner": "ProductCatalogService/ProductBusinessService",
            "experience_owner": "ExperienceService",
            "asset_intelligence_owner": "ContentIntelligenceService",
        }
        return product_ids, experience_ids, matched_asset_ids, confidence, evidence

    @classmethod
    def _aggregate_match_confidence(
        cls,
        product_matches: tuple[Mapping[str, Any], ...],
        experience_matches: tuple[Mapping[str, Any], ...],
        asset_matches: tuple[Mapping[str, Any], ...],
    ) -> float:
        confidences = [
            float(match.get("confidence") or 0.0)
            for matches in (product_matches, experience_matches, asset_matches)
            for match in matches[:2]
        ]
        if not confidences:
            return 0.0
        domain_count = sum(
            bool(matches)
            for matches in (product_matches, experience_matches, asset_matches)
        )
        base = max(confidences)
        agreement_boost = max(0, domain_count - 1) * 0.08
        return cls._bounded_confidence(base + agreement_boost)

    def _load_product_candidates(
        self,
        creator_profile_id: int | None,
    ) -> tuple[Any, ...]:
        service = self.product_catalog_service
        if service is None or creator_profile_id is None:
            return ()
        list_display = getattr(service, "list_workspace_display_models", None)
        if callable(list_display):
            try:
                return tuple(list_display(creator_profile_id=creator_profile_id))
            except TypeError:
                return tuple(list_display(creator_profile_id))
        list_products = getattr(service, "list_workspace_products", None)
        if callable(list_products):
            try:
                return tuple(list_products(creator_profile_id=creator_profile_id))
            except TypeError:
                return tuple(list_products(creator_profile_id))
        return ()

    def _load_experience_candidates(
        self,
        creator_profile_id: int | None,
    ) -> tuple[Any, ...]:
        service = self.experience_service
        if service is None or creator_profile_id is None:
            return ()
        list_experiences = getattr(service, "list_experiences", None)
        if not callable(list_experiences):
            return ()
        try:
            return tuple(list_experiences(creator_profile_id=creator_profile_id))
        except TypeError:
            return tuple(list_experiences(creator_profile_id))

    def _load_asset_candidates(
        self,
        asset_ids: Iterable[str | int] | None,
    ) -> tuple[Any, ...]:
        service = self.content_intelligence_service
        if service is None:
            return ()
        get_asset = getattr(service, "get_asset_intelligence", None)
        if not callable(get_asset):
            return ()
        candidates = []
        for asset_id in asset_ids or ():
            try:
                candidate = get_asset(asset_id)
            except (TypeError, ValueError):
                continue
            if candidate is not None:
                candidates.append(candidate)
        return tuple(candidates)

    def _match_candidate(
        self,
        *,
        candidate: Any,
        terms: tuple[str, ...],
        id_names: tuple[str, ...],
        source: str,
        domain: str,
        weighted_fields: tuple[tuple[str, float], ...],
        extra_evidence: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any] | None:
        candidate_id = self._candidate_id(candidate, id_names)
        if candidate_id is None:
            return None
        field_hits: dict[str, tuple[str, ...]] = {}
        score = 0.0
        for field, weight in weighted_fields:
            values = self._candidate_field_values(candidate, field)
            hits = self._term_hits(terms, values)
            if hits:
                field_hits[field] = hits
                score += weight * len(hits)
        if not field_hits:
            return None
        total_terms = max(1, len(terms))
        coverage = len(set(hit for hits in field_hits.values() for hit in hits)) / total_terms
        confidence = self._bounded_confidence(min(0.95, 0.25 + score + (coverage * 0.25)))
        return {
            "id": candidate_id,
            "domain": domain,
            "confidence": confidence,
            "matched_terms": tuple(
                dict.fromkeys(hit for hits in field_hits.values() for hit in hits)
            ),
            "field_hits": field_hits,
            "source": source,
            "supporting_evidence": {
                "field_hits": field_hits,
                "read_only": True,
                **dict(extra_evidence or {}),
            },
        }

    @classmethod
    def _candidate_id(cls, candidate: Any, names: tuple[str, ...]) -> str | None:
        for name in names:
            value = cls._read(candidate, name)
            if value is not None:
                return str(value)
        return None

    @classmethod
    def _candidate_field_values(cls, candidate: Any, field: str) -> tuple[str, ...]:
        value = cls._read(candidate, field)
        if value is None:
            nested = cls._read(candidate, "metadata")
            value = cls._read(nested, field)
        return tuple(cls._flatten_text(value))

    @classmethod
    def _flatten_text(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, Mapping):
            flattened = []
            for nested in value.values():
                flattened.extend(cls._flatten_text(nested))
            return tuple(flattened)
        if isinstance(value, (str, int, float, bool)):
            return (str(value).lower(),)
        try:
            flattened = []
            for item in value:
                flattened.extend(cls._flatten_text(item))
            return tuple(flattened)
        except TypeError:
            return (str(value).lower(),)

    @staticmethod
    def _term_hits(terms: tuple[str, ...], values: tuple[str, ...]) -> tuple[str, ...]:
        haystack = " ".join(values).lower()
        return tuple(
            dict.fromkeys(
                term
                for term in terms
                if term and re.search(rf"\b{re.escape(term.lower())}\b", haystack)
            )
        )

    @staticmethod
    def _sort_matches(matches: Iterable[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            sorted(
                matches,
                key=lambda item: (float(item.get("confidence") or 0.0), str(item.get("id") or "")),
                reverse=True,
            )
        )

    @classmethod
    def _safe_public_mapping(cls, value: Any) -> Mapping[str, Any]:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return {
                str(key): cls._safe_public_value(nested)
                for key, nested in value.items()
                if isinstance(key, (str, int, float, bool))
            }
        public = {}
        for name in ("status", "detail", "summary", "ready", "attention_required"):
            nested = getattr(value, name, None)
            if nested is not None:
                public[name] = cls._safe_public_value(nested)
        return public

    @classmethod
    def _safe_public_value(cls, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, Mapping):
            return cls._safe_public_mapping(value)
        if isinstance(value, (tuple, list)):
            return tuple(cls._safe_public_value(item) for item in value)
        enum_value = getattr(value, "value", None)
        if isinstance(enum_value, (str, int, float, bool)):
            return enum_value
        return str(value)

    @classmethod
    def _candidate_evidence(
        cls,
        candidates: Iterable[Mapping[str, Any] | Any] | Mapping[str, Any] | Any | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], float, dict[str, Any]]:
        values = cls._candidate_tuple(candidates)
        product_ids: list[str] = []
        experience_ids: list[str] = []
        asset_ids: list[str] = []
        confidences: list[float] = []
        raw_count = 0
        for candidate in values:
            raw_count += 1
            product_ids.extend(cls._ids_from(candidate, "product_ids", "product_id", "id"))
            experience_ids.extend(cls._ids_from(candidate, "experience_ids", "experience_id"))
            asset_ids.extend(cls._ids_from(candidate, "asset_ids", "asset_id"))
            confidence = cls._read(candidate, "confidence")
            if confidence is not None:
                confidences.append(cls._bounded_confidence(confidence))
        confidence = (
            round(sum(confidences) / len(confidences), 2)
            if confidences
            else 0.75 if (product_ids or experience_ids or asset_ids) else 0.0
        )
        return (
            cls._dedupe(product_ids),
            cls._dedupe(experience_ids),
            cls._dedupe(asset_ids),
            confidence,
            {
                "candidate_count": raw_count,
                "source": "supplied_match_candidates",
            },
        )

    @staticmethod
    def _candidate_tuple(candidates: Any) -> tuple[Any, ...]:
        if candidates is None:
            return ()
        if isinstance(candidates, Mapping):
            return (candidates,)
        if isinstance(candidates, (str, bytes)):
            return ()
        try:
            return tuple(candidates)
        except TypeError:
            return (candidates,)

    @classmethod
    def _ids_from(cls, source: Any, plural: str, singular: str, fallback: str | None = None) -> list[str]:
        values = cls._read(source, plural)
        if values is None:
            values = cls._read(source, singular)
        if values is None and fallback:
            values = cls._read(source, fallback)
        if values is None:
            return []
        if isinstance(values, (str, int, float)):
            return [str(values)]
        try:
            return [str(value) for value in values if value is not None]
        except TypeError:
            return [str(values)]

    @staticmethod
    def _read(source: Any, name: str) -> Any:
        if isinstance(source, Mapping):
            return source.get(name)
        return getattr(source, name, None)

    @classmethod
    def _normalized_terms(
        cls,
        request_text: str,
        normalized_terms: Iterable[str] | None,
    ) -> tuple[str, ...]:
        supplied = tuple(
            dict.fromkeys(
                cls._clean_text(term)
                for term in (normalized_terms or ())
                if cls._clean_text(term)
            )
        )
        if supplied:
            return supplied
        words = re.findall(r"[a-z0-9]+", (request_text or "").lower())
        stopwords = {
            "a",
            "an",
            "and",
            "any",
            "do",
            "have",
            "i",
            "like",
            "me",
            "of",
            "please",
            "show",
            "some",
            "that",
            "the",
            "this",
            "to",
            "want",
            "with",
            "you",
        }
        return tuple(dict.fromkeys(word for word in words if word not in stopwords))

    @staticmethod
    def _terms_key(terms: Iterable[str]) -> str:
        return "|".join(sorted(str(term).lower() for term in terms if str(term).strip()))

    @staticmethod
    def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(str(value) for value in values if str(value).strip()))

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _text_tuple(cls, values: Iterable[str | int]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(text for value in values if (text := cls._text(value))))

    @classmethod
    def _clean_text(cls, value: Any) -> str | None:
        text = cls._text(value)
        return text.lower() if text else None

    @staticmethod
    def _bounded_confidence(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return round(max(0.0, min(1.0, number)), 2)

    @staticmethod
    def _source(source: ContentOpportunitySource | str | None) -> ContentOpportunitySource:
        if isinstance(source, ContentOpportunitySource):
            return source
        if source is None:
            return ContentOpportunitySource.UNKNOWN
        normalized = str(source).strip().upper()
        return ContentOpportunitySource.__members__.get(
            normalized,
            ContentOpportunitySource.UNKNOWN,
        )

    @staticmethod
    def _match_type(
        product_ids: tuple[str, ...],
        experience_ids: tuple[str, ...],
        asset_ids: tuple[str, ...],
    ) -> ContentOpportunityMatchType:
        matched_types = sum(bool(values) for values in (product_ids, experience_ids, asset_ids))
        if matched_types > 1:
            return ContentOpportunityMatchType.MIXED
        if product_ids:
            return ContentOpportunityMatchType.PRODUCT
        if experience_ids:
            return ContentOpportunityMatchType.EXPERIENCE
        if asset_ids:
            return ContentOpportunityMatchType.ASSET
        return ContentOpportunityMatchType.NONE

    @staticmethod
    def _priority(
        signal: ContentDemandSignal,
        *,
        matched: bool,
    ) -> ContentOpportunityPriority:
        if signal.is_vip:
            return ContentOpportunityPriority.HIGH
        importance = (signal.customer_importance or "").lower()
        if importance in {"vip", "high", "high_value", "important"}:
            return ContentOpportunityPriority.HIGH
        return ContentOpportunityPriority.NORMAL if not matched else ContentOpportunityPriority.LOW

    @classmethod
    def _max_priority(
        cls,
        first: ContentOpportunityPriority,
        second: ContentOpportunityPriority,
    ) -> ContentOpportunityPriority:
        return first if cls._priority_rank(first) >= cls._priority_rank(second) else second

    @staticmethod
    def _priority_rank(priority: ContentOpportunityPriority) -> int:
        return {
            ContentOpportunityPriority.LOW: 1,
            ContentOpportunityPriority.NORMAL: 2,
            ContentOpportunityPriority.HIGH: 3,
            ContentOpportunityPriority.CRITICAL: 4,
        }.get(priority, 0)

    @staticmethod
    def _opportunity_metadata() -> dict[str, Any]:
        return {
            "read_only": True,
            "advisory_only": True,
            "provider_neutral": True,
            "executes_telegram": False,
            "modifies_products": False,
            "modifies_experiences": False,
            "modifies_publishing": False,
            "modifies_customer_intelligence": False,
            "records_business_learning": False,
            "changes_decision_engine_behavior": False,
            "owner": "ContentOpportunityService",
        }

    def _hydrate_from_repository(self) -> None:
        repository = self.content_opportunity_repository
        load_records = getattr(repository, "load_records", None)
        if not callable(load_records):
            return
        records = load_records()
        self._signals = list(records.get("signals", ()) or ())
        self._matches = list(records.get("matches", ()) or ())
        self._opportunities = list(records.get("opportunities", ()) or ())
        self._resolutions = list(records.get("resolutions", ()) or ())
        self._follow_ups = list(records.get("follow_ups", ()) or ())

    def _persist_records(self) -> None:
        repository = self.content_opportunity_repository
        save_records = getattr(repository, "save_records", None)
        if not callable(save_records):
            return
        save_records(
            signals=tuple(self._signals),
            matches=tuple(self._matches),
            opportunities=tuple(self._opportunities),
            resolutions=tuple(self._resolutions),
            follow_ups=tuple(self._follow_ups),
        )

    def _compatibility(self) -> dict[str, Any]:
        durable = self.content_opportunity_repository is not None
        return {
            "read_only": True,
            "advisory_only": True,
            "provider_neutral": True,
            "durable_persistence": durable,
            "in_memory_foundation": not durable,
            "executes_telegram": False,
            "sends_messages": False,
            "publishes_products": False,
            "modifies_products": False,
            "modifies_experiences": False,
            "modifies_publishing": False,
            "modifies_customer_intelligence": False,
            "modifies_business_learning": False,
            "modifies_product_strategy": False,
            "modifies_commerce_strategy": False,
            "changes_decision_engine_behavior": False,
            "product_owner": "ProductCatalogService/ProductBusinessService",
            "experience_owner": "ExperienceService",
            "customer_owner": "CustomerIntelligenceService",
            "learning_owner": "BusinessLearningService",
            "runtime_owner": "DecisionEngine/Telegram runtime",
        }
