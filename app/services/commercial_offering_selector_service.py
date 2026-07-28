"""Deterministic, read-only Commercial Offering eligibility and selection."""
from __future__ import annotations

import logging
import time
import json
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

from app.models.commercial_offering_selection import (
    OfferingEligibilityEvaluation,
    OfferingExclusionReason,
    OfferingSelectionReason,
    SelectedOfferingResult,
    immutable_selector_metadata,
)
from app.models.commerce_recommendation import (
    RecommendationCandidate,
    RecommendationContext,
    RecommendationHistoryEntry,
)
from app.repositories.commercial_offering_selector_repository import (
    CommercialOfferingSelectorRepository,
)
from app.services.commerce_recommendation_engine import (
    CommerceRecommendationEngine,
)


logger = logging.getLogger("commercial-offering-selector")


class CommercialOfferingSelectorService:
    """Select one provider-ready offering without AI, scoring, or mutation."""

    def __init__(
        self, repository=None, clock=lambda: datetime.now(timezone.utc),
        recommendation_engine=None,
    ):
        self.repository = (
            repository or CommercialOfferingSelectorRepository()
        )
        self.clock = clock
        self.recommendation_engine = (
            recommendation_engine or CommerceRecommendationEngine()
        )

    def select(
        self, *, creator_profile_id: int, telegram_user_id: int | None,
        customer_profile, commerce_signal, active_purchase_intent,
        conversation_context: dict | None = None,
    ) -> SelectedOfferingResult:
        started = time.perf_counter()
        context = dict(conversation_context or {})
        channel = str(
            context.get("primary_sales_channel") or "AI_CHAT"
        ).strip().upper()
        recommendation_context = RecommendationContext(
            creator_profile_id=int(creator_profile_id),
            active_purchase_intent_offering_id=(
                UUID(str(active_purchase_intent.commercial_offering_id))
                if active_purchase_intent is not None else None
            ),
            evaluated_at=self.clock(),
            requested_media_type=context.get("requested_media_type"),
            conversation_id=(
                str(context["conversation_id"])
                if context.get("conversation_id") is not None else None
            ),
            current_request=context.get("latest_message"),
            requested_themes=tuple(context.get("requested_themes") or ()),
            recent_conversation_requests=tuple(
                context.get("recent_conversation_requests") or ()
            )[-3:],
        )
        account_id = int(getattr(customer_profile, "fanvue_account_id", 0))
        buyer_uuid = getattr(
            customer_profile, "external_fanvue_user_uuid", None
        )
        purchased = self.repository.list_purchased_offering_ids(
            creator_profile_id=int(creator_profile_id),
            fanvue_account_id=account_id,
            external_fanvue_user_uuid=buyer_uuid,
            telegram_user_id=telegram_user_id,
        )

        if active_purchase_intent is not None:
            candidate = self.repository.get_candidate(
                active_purchase_intent.commercial_offering_id,
                creator_profile_id=int(creator_profile_id),
            )
            if candidate is None:
                recommendation = self.recommendation_engine.rank(
                    (), recommendation_context, rejection_count=0
                )
                return self._result(
                    started=started, channel=channel, selected=None,
                    reason=OfferingSelectionReason.NO_ELIGIBLE_OFFERING,
                    evaluations=(), candidate_count=0, purchased=purchased,
                    active_intent=True,
                    extra_exclusions=("ACTIVE_INTENT_OFFERING_UNAVAILABLE",),
                    recommendation=recommendation,
                )
            evaluation = self._evaluate(
                candidate, creator_profile_id=int(creator_profile_id),
                channel=channel, purchased=frozenset(),
            )
            if evaluation.eligible:
                recommendation = self._rank(
                    (candidate,), recommendation_context, rejection_count=0
                )
                return self._result(
                    started=started, channel=channel,
                    selected=self._selected_projection(
                        (candidate,), recommendation
                    ),
                    reason=OfferingSelectionReason(
                        recommendation.selection_reason
                    ),
                    evaluations=(evaluation,), candidate_count=1,
                    purchased=purchased, active_intent=True,
                    recommendation=recommendation,
                )
            recommendation = self.recommendation_engine.rank(
                (), recommendation_context, rejection_count=1
            )
            return self._result(
                started=started, channel=channel, selected=None,
                reason=OfferingSelectionReason.NO_ELIGIBLE_OFFERING,
                evaluations=(evaluation,), candidate_count=1,
                purchased=purchased, active_intent=True,
                recommendation=recommendation,
            )

        history_rows = (
            tuple(self.repository.list_recommendation_history(
                creator_profile_id=int(creator_profile_id),
                fanvue_account_id=account_id,
                external_fanvue_user_uuid=buyer_uuid,
                telegram_user_id=telegram_user_id,
            ))
            if hasattr(self.repository, "list_recommendation_history")
            else ()
        )
        history = tuple(self._history_entry(row) for row in history_rows)
        verified = tuple(
            item for item in history
            if item.status == "PURCHASED"
            and item.attribution_result == "ATTRIBUTED"
        )
        recommendation_context = replace(
            recommendation_context,
            verified_affinity_tags=tuple(dict.fromkeys(
                tag for item in verified for tag in item.intelligence_tags
            )),
            verified_affinity_offering_types=tuple(dict.fromkeys(
                item.offering_type for item in verified
            )),
            recent_offer_history=history,
            commerce_learning_profile=self._learning_context(
                self.repository.get_commerce_learning_profile(
                    creator_profile_id=int(creator_profile_id),
                    fanvue_account_id=account_id,
                    external_fanvue_user_uuid=buyer_uuid,
                )
                if hasattr(self.repository, "get_commerce_learning_profile")
                else None
            ),
        )
        candidates = tuple(self.repository.list_candidates(
            creator_profile_id=int(creator_profile_id),
            primary_sales_channel=channel,
        ))
        evaluations = tuple(
            self._evaluate(
                candidate, creator_profile_id=int(creator_profile_id),
                channel=channel, purchased=purchased,
            )
            for candidate in candidates
        )
        eligible = tuple(
            candidate for candidate, evaluation in zip(
                candidates, evaluations, strict=True
            ) if evaluation.eligible
        )
        if not eligible:
            recommendation = self.recommendation_engine.rank(
                (), recommendation_context,
                rejection_count=sum(not item.eligible for item in evaluations),
            )
            return self._result(
                started=started, channel=channel, selected=None,
                reason=OfferingSelectionReason.NO_ELIGIBLE_OFFERING,
                evaluations=evaluations, candidate_count=len(candidates),
                purchased=purchased, active_intent=False,
                recommendation=recommendation,
            )

        recommendation = self._rank(
            eligible, recommendation_context,
            rejection_count=sum(not item.eligible for item in evaluations),
        )
        selected = self._selected_projection(eligible, recommendation)
        return self._result(
            started=started, channel=channel, selected=selected,
            reason=OfferingSelectionReason(recommendation.selection_reason),
            evaluations=evaluations,
            candidate_count=len(candidates), purchased=purchased,
            active_intent=False,
            recommendation=recommendation,
        )

    def _evaluate(
        self, candidate, *, creator_profile_id: int, channel: str,
        purchased: frozenset[UUID],
    ) -> OfferingEligibilityEvaluation:
        reasons: list[str] = []
        if candidate.get("commercially_eligible") is False:
            reasons.append(
                OfferingExclusionReason.CANONICAL_REFERENCE_ASSET.value
            )
        status = str(candidate.get("offering_status") or "")
        if int(candidate.get("creator_profile_id") or 0) != creator_profile_id:
            reasons.append(OfferingExclusionReason.CREATOR_MISMATCH.value)
        if status == "ARCHIVED":
            reasons.append(OfferingExclusionReason.OFFERING_ARCHIVED.value)
        elif status != "READY":
            reasons.append(OfferingExclusionReason.OFFERING_NOT_ACTIVE.value)
        if str(candidate.get("primary_sales_channel") or "") != channel:
            reasons.append(
                OfferingExclusionReason.SALES_CHANNEL_MISMATCH.value
            )
        if candidate.get("publication_status") != "LIVE":
            reasons.append(
                OfferingExclusionReason.PUBLICATION_NOT_LIVE.value
            )
        if not candidate.get("provider"):
            reasons.append(
                OfferingExclusionReason.PROVIDER_NOT_ENABLED.value
            )
        if candidate.get("provider_resource_status") != "PRESENT":
            reasons.append(
                OfferingExclusionReason.PROVIDER_RESOURCE_NOT_PRESENT.value
            )
        if not candidate.get("delivery_url"):
            reasons.append(
                OfferingExclusionReason.DELIVERY_URL_MISSING.value
            )
        if (
            candidate.get("price_minor") is None
            or not 300 <= int(candidate["price_minor"]) <= 50000
        ):
            reasons.append(OfferingExclusionReason.PRICE_INVALID.value)
        destination_reason = self._destination_reason(candidate)
        if destination_reason:
            reasons.append(destination_reason)
        offering_id = UUID(str(candidate["offering_id"]))
        if offering_id in purchased:
            reasons.append(
                OfferingExclusionReason.OFFERING_ALREADY_PURCHASED.value
            )
        unique_reasons = tuple(dict.fromkeys(reasons))
        evaluation = OfferingEligibilityEvaluation(
            offering_id=offering_id,
            title=str(candidate.get("title") or ""),
            eligible=not unique_reasons,
            exclusion_reasons=unique_reasons,
            publication_id=(
                UUID(str(candidate["publication_id"]))
                if candidate.get("publication_id") else None
            ),
            publication_provider=candidate.get("provider"),
            publication_status=candidate.get("publication_status"),
            delivery_url_available=bool(candidate.get("delivery_url")),
            offering_status=status,
            offering_type=str(candidate.get("offering_type") or ""),
            primary_sales_channel=str(
                candidate.get("primary_sales_channel") or ""
            ),
            published_at=(
                candidate["published_at"].isoformat()
                if candidate.get("published_at") else None
            ),
        )
        logger.info(
            "event=offer_evaluated offering_id=%s eligible=%s "
            "rejection_reasons=%s",
            offering_id, evaluation.eligible,
            ",".join(unique_reasons) or "NONE",
        )
        return evaluation

    @staticmethod
    def _destination_reason(candidate) -> str | None:
        offering_type = str(candidate.get("offering_type") or "")
        destinations = tuple(candidate.get("destinations") or ())
        expected = (
            "SINGLE_PPV" if offering_type in {"SINGLE_IMAGE", "VIDEO"}
            else "PHOTOSET" if offering_type == "PHOTOSET" else None
        )
        if (
            expected is None
            or not destinations
            or any(value != expected for value in destinations)
        ):
            return (
                OfferingExclusionReason
                .DESTINATION_NOT_COMMERCIALLY_AVAILABLE.value
            )
        return None

    def _rank(self, eligible, context, *, rejection_count):
        return self.recommendation_engine.rank(
            tuple(
                RecommendationCandidate.from_eligible_projection(
                    self._enriched_projection(candidate)
                )
                for candidate in eligible
            ),
            context,
            rejection_count=rejection_count,
        )

    @classmethod
    def _enriched_projection(cls, candidate):
        value = dict(candidate)
        intelligence: dict[str, list[str]] = {}
        for asset in cls._sequence(value.get("asset_intelligence")):
            profile = (
                asset.get("profile_data", {})
                if isinstance(asset, dict) else {}
            )
            cls._merge_intelligence(intelligence, profile)
        cls._merge_intelligence(
            intelligence, cls._mapping(value.get("photoshoot_intelligence")),
            prefix="photoshoot_",
        )
        value["recommendation_intelligence"] = {
            key: tuple(dict.fromkeys(items))
            for key, items in intelligence.items() if items
        }
        return value

    @classmethod
    def _history_entry(cls, row):
        value = dict(row)
        intelligence: dict[str, list[str]] = {}
        for profile in cls._sequence(value.get("asset_intelligence")):
            cls._merge_intelligence(intelligence, cls._mapping(profile))
        tags = tuple(dict.fromkeys(
            item.lower().strip()
            for items in intelligence.values() for item in items
            if item.strip()
        ))
        return RecommendationHistoryEntry(
            offering_id=UUID(str(value["commercial_offering_id"])),
            offering_type=str(value.get("offering_type") or ""),
            status=str(
                getattr(value.get("status"), "value", value.get("status") or "")
            ),
            presented_at=value.get("presented_at"),
            purchased_at=value.get("purchased_at"),
            attribution_result=str(
                getattr(
                    value.get("attribution_result"), "value",
                    value.get("attribution_result") or "",
                )
            ),
            photoshoot_identifier=(
                str(value["photoshoot_identifier"])
                if value.get("photoshoot_identifier") else None
            ),
            intelligence_tags=tags,
        )

    @staticmethod
    def _mapping(value):
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _sequence(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return ()
        return tuple(value) if isinstance(value, (list, tuple)) else ()

    @classmethod
    def _merge_intelligence(cls, target, profile, prefix=""):
        aliases = {
            "location_type": "location", "short_description": "content_summary",
            "detailed_description": "content_summary",
            "suggested_collections": "themes", "tags": "keywords",
            "clothing": "clothing", "pose": "pose", "activity": "activity",
            "setting": "setting", "environment": "environment",
            "themes": "themes", "keywords": "keywords",
            "search_phrases": "search_phrases", "mood": "mood",
            "atmosphere": "atmosphere", "emotional_tone": "emotional_tone",
            "visual_style": "visual_style", "content_summary": "content_summary",
        }
        for source, destination in aliases.items():
            raw = profile.get(source) if isinstance(profile, dict) else None
            values = (
                raw if isinstance(raw, (list, tuple))
                else (raw,) if raw is not None else ()
            )
            clean = [
                str(item).strip() for item in values
                if str(item).strip()
            ]
            if clean:
                target.setdefault(prefix + destination, []).extend(clean)

    @staticmethod
    def _learning_context(profile):
        if profile is None:
            return {}
        return {
            "preferences": dict(profile.preferences or {}),
            "preferredOfferingType": profile.preferred_offering_type,
            "favoriteMediaType": profile.favorite_media_type,
            "averagePriceMinor": profile.average_price_minor,
            "preferredPriceMinMinor": profile.preferred_price_min_minor,
            "preferredPriceMaxMinor": profile.preferred_price_max_minor,
            "repeatPurchaseFrequency": profile.repeat_purchase_frequency,
            "confidence": profile.confidence,
            "evidenceCount": profile.evidence_count,
        }

    @staticmethod
    def _selected_projection(eligible, recommendation):
        selected = recommendation.selected_candidate
        if selected is None:
            return None
        return next(
            candidate for candidate in eligible
            if UUID(str(candidate["offering_id"])) == selected.offering_id
        )

    def _result(
        self, *, started, channel, selected, reason, evaluations,
        candidate_count, purchased, active_intent,
        extra_exclusions=(), recommendation=None,
    ):
        exclusions = tuple(dict.fromkeys((
            *extra_exclusions,
            *(
                value
                for evaluation in evaluations
                for value in evaluation.exclusion_reasons
            ),
        )))
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        result = SelectedOfferingResult(
            offering_id=(
                UUID(str(selected["offering_id"])) if selected else None
            ),
            publication_id=(
                UUID(str(selected["publication_id"]))
                if selected and selected.get("publication_id") else None
            ),
            publication_provider=(
                selected.get("provider") if selected else None
            ),
            delivery_url=(
                selected.get("delivery_url") if selected else None
            ),
            offering_type=(
                selected.get("offering_type") if selected else None
            ),
            primary_sales_channel=(
                selected.get("primary_sales_channel") if selected else None
            ),
            selection_reason=reason,
            exclusion_reasons=exclusions,
            evaluations=tuple(evaluations),
            selector_metadata=immutable_selector_metadata({
                "candidateCount": candidate_count,
                "eligibleCount": sum(
                    evaluation.eligible for evaluation in evaluations
                ),
                "rejectedCount": sum(
                    not evaluation.eligible for evaluation in evaluations
                ),
                "purchasedOfferingCount": len(purchased),
                "activeIntentApplied": active_intent,
                "primarySalesChannel": channel,
                "featuredSupported": False,
                "ordering": (
                    "ACTIVE_INTENT, FEATURED_IF_SUPPORTED, "
                    "PUBLISHED_AT_DESC, OFFERING_ID_ASC"
                ),
                "selectorTimingMs": elapsed,
                "evaluatedAt": self.clock().isoformat(),
                "recommendationEngineVersion": (
                    recommendation.engine_version if recommendation else None
                ),
                "recommendationTrace": (
                    [
                        {
                            "rank": ranked.rank,
                            "offeringId": str(ranked.candidate.offering_id),
                            "title": ranked.candidate.title,
                            "offeringType": ranked.candidate.offering_type,
                            "priceMinor": ranked.candidate.price_minor,
                            "currency": ranked.candidate.currency,
                            "publishedAt": (
                                ranked.candidate.published_at.isoformat()
                                if ranked.candidate.published_at else None
                            ),
                            "activeIntentMatch": (
                                next(
                                    component.raw_value
                                    for component in ranked.components
                                    if component.key
                                    == "active_purchase_intent"
                                )
                            ),
                            "components": [
                                {
                                    "key": component.key,
                                    "rawValue": component.raw_value,
                                    "weightedContribution": (
                                        component.contribution
                                    ),
                                    "weight": (
                                        self.recommendation_engine.weights.for_key(
                                            component.key
                                        )
                                        if component.key
                                        != "active_purchase_intent" else None
                                    ),
                                    "explanation": component.explanation,
                                    "affectedRanking": (
                                        component.affected_ranking
                                    ),
                                    "evidence": dict(component.evidence),
                                }
                                for component in ranked.components
                            ],
                            "reason": ranked.deterministic_reason,
                            "selected": ranked.selected,
                            "finalScore": ranked.final_score,
                            "tieBreak": {
                                "publishedAtDescending": (
                                    ranked.candidate.published_at.isoformat()
                                    if ranked.candidate.published_at else None
                                ),
                                "offeringIdAscending": str(
                                    ranked.candidate.offering_id
                                ),
                            },
                        }
                        for ranked in recommendation.ranked_candidates
                    ] if recommendation else []
                ),
                "recommendationSummary": (
                    recommendation.recommendation_summary
                    if recommendation else None
                ),
                "unsupportedSchemaRules": [
                    "offering_expiration",
                    "offering_withdrawn",
                    "offering_disabled",
                    "featured_flag",
                ],
            }),
            title=(str(selected.get("title") or "") if selected else None),
            short_description=(
                str(selected.get("description") or "") if selected else None
            ),
            price_minor=(
                int(selected["price_minor"])
                if selected and selected.get("price_minor") is not None
                else None
            ),
            currency=(
                str(selected.get("currency") or "") if selected else None
            ),
            recommendation_result=recommendation,
        )
        logger.info(
            "event=offer_selected offering_id=%s selection_reason=%s "
            "selector_timing_ms=%s",
            result.offering_id, reason.value, elapsed,
        )
        return result
