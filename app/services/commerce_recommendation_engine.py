"""Deterministic intelligent ranking for already-eligible offerings."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import timezone
import logging

from app.models.commerce_recommendation import (
    RankedRecommendationCandidate,
    RecommendationCandidate,
    RecommendationContext,
    RecommendationResult,
    RecommendationScoreComponent,
    RecommendationWeights,
)
from app.services.recommendation_text_normalizer import (
    RecommendationTextNormalizer,
)


logger = logging.getLogger("commerce-recommendation-engine")


class RecommendationRankingStrategy(ABC):
    @abstractmethod
    def evaluate(
        self, candidate: RecommendationCandidate, context: RecommendationContext,
    ) -> RecommendationScoreComponent:
        """Return a deterministic normalized component without database access."""


class ActivePurchaseIntentStrategy(RecommendationRankingStrategy):
    def evaluate(self, candidate, context):
        matches = (
            context.active_purchase_intent_offering_id is not None
            and candidate.offering_id
            == context.active_purchase_intent_offering_id
        )
        return RecommendationScoreComponent(
            key="active_purchase_intent", raw_value=1.0 if matches else 0.0,
            ordering_value=0 if matches else 1, contribution=0.0,
            explanation=(
                "Candidate matches the active Purchase Intent."
                if matches else "Candidate does not match an active Purchase Intent."
            ),
            affected_ranking=matches, evidence={"matched": matches},
        )


class SemanticMatchStrategy(RecommendationRankingStrategy):
    FIELD_WEIGHTS = {
        "title": 1.00, "offering_type": 0.95,
        "search_phrases": 0.90, "themes": 0.88, "activity": 0.86,
        "keywords": 0.76, "setting": 0.74, "environment": 0.74,
        "location": 0.74, "wardrobe": 0.72, "outfit": 0.72,
        "clothing": 0.72, "description": 0.58,
        "content_summary": 0.58, "photoshoot_summary": 0.58,
        "mood": 0.40, "atmosphere": 0.38,
        "emotional_tone": 0.38, "visual_style": 0.38,
    }

    def __init__(self, normalizer=None):
        self.normalizer = normalizer or RecommendationTextNormalizer()

    def evaluate(self, candidate, context):
        query = self.normalizer.normalize(
            context.current_request,
            " ".join(context.requested_themes),
            context.requested_media_type,
            *context.recent_conversation_requests[-3:],
        )
        if not query.tokens:
            return self._component(
                0.5, (), (), "No meaningful commerce query; semantic score is neutral."
            )
        fields = self._fields(candidate)
        token_matches = []
        for token in query.tokens:
            matched = [
                (name, weight) for name, (weight, normalized) in fields.items()
                if token in normalized.tokens
            ]
            if matched:
                token_matches.append((token, *max(matched, key=lambda item: item[1])))
        phrase_matches = []
        for phrase in query.phrases:
            matched = [
                (name, weight) for name, (weight, normalized) in fields.items()
                if phrase in normalized.normalized
            ]
            if matched:
                phrase_matches.append((phrase, *max(matched, key=lambda item: item[1])))
        token_score = (
            sum(match[2] for match in token_matches) / len(query.tokens)
        )
        phrase_bonus = min(
            0.20,
            sum(0.05 * match[2] for match in phrase_matches),
        )
        score = min(1.0, token_score + phrase_bonus)
        explanation = (
            "Matched " + ", ".join(
                f"{token} in {field}" for token, field, _ in token_matches[:5]
            )
            if token_matches else "No request terms matched offering intelligence."
        )
        return self._component(
            score, tuple(item[0] for item in token_matches),
            tuple(item[0] for item in phrase_matches), explanation,
            fields=tuple(dict.fromkeys(item[1] for item in (
                *token_matches, *phrase_matches
            ))),
        )

    def _fields(self, candidate):
        values = {
            "title": (candidate.title,),
            "description": (candidate.description,),
            "offering_type": (candidate.offering_type.replace("_", " "),),
            **dict(candidate.intelligence),
        }
        return {
            name: (
                self.FIELD_WEIGHTS.get(name, 0.50),
                self.normalizer.normalize(*items),
            )
            for name, items in values.items() if any(items)
        }

    @staticmethod
    def _component(score, tokens, phrases, explanation, fields=()):
        return RecommendationScoreComponent(
            key="semantic_match", raw_value=round(score, 8),
            ordering_value=-score, contribution=0.0,
            explanation=explanation, affected_ranking=score != 0.5,
            evidence={
                "matchedTokens": tokens, "matchedPhrases": phrases,
                "matchedFields": fields,
            },
        )


class CustomerAffinityStrategy(RecommendationRankingStrategy):
    def __init__(self, normalizer=None):
        self.normalizer = normalizer or RecommendationTextNormalizer()

    def evaluate(self, candidate, context):
        learning = dict(context.commerce_learning_profile or {})
        if learning:
            return self._learning_profile_component(candidate, learning)
        affinity = self.normalizer.normalize(*context.verified_affinity_tags)
        types = frozenset(context.verified_affinity_offering_types)
        if not affinity.tokens and not types:
            return self._component(
                0.5, (), False,
                "No verified purchase affinity exists; affinity is neutral.",
            )
        candidate_tags = self.normalizer.normalize(
            candidate.title, candidate.description,
            *(item for values in candidate.intelligence.values() for item in values),
        )
        matches = tuple(
            token for token in affinity.tokens if token in candidate_tags.tokens
        )
        tag_score = (
            len(matches) / len(affinity.tokens) if affinity.tokens else 0.0
        )
        type_match = candidate.offering_type in types
        score = min(1.0, tag_score * 0.8 + (0.2 if type_match else 0.0))
        return self._component(
            score, matches, type_match,
            (
                "Matched verified purchase affinity: " + ", ".join(matches)
                if matches or type_match else
                "Offering does not match verified purchase affinity."
            ),
        )

    def _learning_profile_component(self, candidate, learning):
        preferences = dict(learning.get("preferences") or {})
        candidate_values = {
            str(item).strip().lower()
            for values in candidate.intelligence.values() for item in values
        }
        candidate_tokens = set(self.normalizer.normalize(
            candidate.title, candidate.description, *candidate_values
        ).tokens)
        matches, weighted = [], []
        for category, values in preferences.items():
            if not isinstance(values, dict):
                continue
            for name, evidence in values.items():
                if not isinstance(evidence, dict):
                    continue
                normalized = self.normalizer.normalize(str(name))
                if set(normalized.tokens) & candidate_tokens:
                    score = float(evidence.get("score") or 0)
                    confidence = float(evidence.get("confidence") or 0)
                    weighted.append(score * max(0.25, confidence))
                    matches.append({
                        "category": category, "value": name,
                        "score": score, "confidence": confidence,
                    })
        bonuses = []
        preferred_type = learning.get("preferredOfferingType")
        if preferred_type and candidate.offering_type == preferred_type:
            bonuses.append({
                "reason": "preferred_offering_type", "value": 0.15,
            })
        minimum = learning.get("preferredPriceMinMinor")
        maximum = learning.get("preferredPriceMaxMinor")
        if (
            minimum is not None and maximum is not None
            and int(minimum) <= candidate.price_minor <= int(maximum)
        ):
            bonuses.append({
                "reason": "preferred_price_range", "value": 0.15,
            })
        photoshoots = dict(preferences.get("photoshoot") or {})
        if candidate.photoshoot_identifier in photoshoots:
            bonuses.append({
                "reason": "preferred_photoshoot", "value": 0.10,
            })
        repeat_frequency = float(
            learning.get("repeatPurchaseFrequency") or 0
        )
        if preferred_type and candidate.offering_type == preferred_type:
            repeat_boost = min(0.10, repeat_frequency * 0.10)
            if repeat_boost:
                bonuses.append({
                    "reason": "repeat_purchase_pattern",
                    "value": round(repeat_boost, 8),
                })
        base = sum(weighted) / len(weighted) if weighted else 0.0
        score = min(
            1.0,
            base * 0.60 + sum(item["value"] for item in bonuses),
        )
        return RecommendationScoreComponent(
            key="customer_affinity", raw_value=round(score, 8),
            ordering_value=-score, contribution=0.0,
            explanation=(
                "Matched persisted observed Commerce learning."
                if matches or bonuses else
                "Candidate does not match persisted observed preferences."
            ),
            affected_ranking=bool(matches or bonuses),
            evidence={
                "learningMatches": tuple(matches),
                "adaptiveBoosts": tuple(bonuses),
                "learningConfidence": learning.get("confidence", 0),
                "evidenceCount": learning.get("evidenceCount", 0),
                "sourceTypes": ("COMMERCE_LEARNING_PROFILE",),
            },
        )

    @staticmethod
    def _component(score, matches, type_match, explanation):
        return RecommendationScoreComponent(
            key="customer_affinity", raw_value=round(score, 8),
            ordering_value=-score, contribution=0.0,
            explanation=explanation, affected_ranking=score != 0.5,
            evidence={
                "matchedTags": matches,
                "offeringTypeMatch": type_match,
                "sourceTypes": ("ATTRIBUTED_PURCHASE",) if matches or type_match else (),
            },
        )


class ProductTypeFitStrategy(RecommendationRankingStrategy):
    """Explainable fit between canonical opportunity type and current intent."""

    FULL_SET_TERMS = (
        "full set", "complete set", "whole set", "entire set",
        "all the photos", "all photos", "multiple images", "more photos",
    )
    SINGLE_TERMS = (
        "one pic", "one photo", "one image", "single pic",
        "single photo", "single image", "a pic", "a photo",
    )
    PRICE_TERMS = ("cheaper", "cheap", "affordable", "lower price", "less expensive")

    def evaluate(self, candidate, context):
        current_request = str(context.current_request or "").lower()
        recent_request = " ".join(context.recent_conversation_requests[-3:]).lower()
        request = current_request or recent_request
        kind = self._kind(candidate)
        reason = "SINGLE_IMAGE_LOW_FRICTION"
        score = 0.75 if kind == "SINGLE_IMAGE" else 0.50 if kind == "BUNDLE" else 0.45

        full_set = (
            context.requested_media_type in {"PHOTOSET", "BUNDLE"}
            or any(term in request for term in self.FULL_SET_TERMS)
        )
        single = (
            context.requested_media_type == "SINGLE_IMAGE"
            or any(term in request for term in self.SINGLE_TERMS)
        )
        price_sensitive = context.price_sensitive or any(
            term in request for term in self.PRICE_TERMS
        )
        high_engagement = (
            context.engagement_score >= 0.70
            or context.buyer_stage in {"REPEAT_BUYER", "HIGH_VALUE_BUYER"}
        )

        if full_set:
            score = 1.0 if kind == "BUNDLE" else 0.15 if kind == "SINGLE_IMAGE" else 0.30
            reason = "EXPLICIT_BUNDLE_REQUEST" if kind == "BUNDLE" else "PRODUCT_TYPE_INTENT_MISMATCH"
        elif single:
            score = 1.0 if kind == "SINGLE_IMAGE" else 0.10 if kind == "BUNDLE" else 0.35
            reason = "EXPLICIT_SINGLE_IMAGE_REQUEST" if kind == "SINGLE_IMAGE" else "PRODUCT_TYPE_INTENT_MISMATCH"
        elif price_sensitive:
            price_score = 1.0 if candidate.price_minor <= 1000 else 0.70 if candidate.price_minor <= 1500 else 0.20
            type_bias = 0.15 if kind == "SINGLE_IMAGE" else 0.0
            score = min(1.0, price_score + type_bias)
            reason = "PRICE_FIT"
        elif high_engagement and kind == "SESSION":
            score, reason = 1.0, "SESSION_HIGH_ENGAGEMENT_MATCH"
        elif high_engagement and kind == "BUNDLE":
            score, reason = 0.75, "BUNDLE_MULTI_IMAGE_INTENT"

        return RecommendationScoreComponent(
            key="product_type_fit", raw_value=round(score, 8),
            ordering_value=-score, contribution=0.0,
            explanation=f"{kind} opportunity fit: {reason}.",
            affected_ranking=True,
            evidence={
                "opportunityType": kind, "reasonCode": reason,
                "fullSetIntent": full_set, "singleImageIntent": single,
                "priceSensitive": price_sensitive,
                "highEngagement": high_engagement,
            },
        )

    @staticmethod
    def _kind(candidate):
        if candidate.offering_type == "BUNDLE":
            return "BUNDLE"
        if str(candidate.selling_mode or "").upper() == "SESSION":
            return "SESSION"
        return "SINGLE_IMAGE"

class FreshnessStrategy(RecommendationRankingStrategy):
    POINTS = (
        (1.0, 1.00), (7.0, 0.90), (30.0, 0.70),
        (90.0, 0.50), (180.0, 0.30),
    )

    def evaluate(self, candidate, context):
        if candidate.published_at is None:
            score, age = 0.15, None
        else:
            now = context.evaluated_at
            published = candidate.published_at
            if published.tzinfo is None and now.tzinfo is not None:
                published = published.replace(tzinfo=timezone.utc)
            age = max(0.0, (now - published).total_seconds() / 86400)
            score = self._score(age)
        return RecommendationScoreComponent(
            key="freshness", raw_value=round(score, 8),
            ordering_value=-score, contribution=0.0,
            explanation=(
                f"Published {age:.2f} days ago."
                if age is not None else "Publication timestamp is missing."
            ),
            affected_ranking=True,
            evidence={"ageDays": round(age, 4) if age is not None else None},
        )

    @classmethod
    def _score(cls, age):
        if age <= cls.POINTS[0][0]:
            return cls.POINTS[0][1]
        for (left_age, left_score), (right_age, right_score) in zip(
            cls.POINTS, cls.POINTS[1:]
        ):
            if age <= right_age:
                ratio = (age - left_age) / (right_age - left_age)
                return left_score + ratio * (right_score - left_score)
        return 0.15 if age > 365 else max(
            0.15, 0.30 - ((age - 180) / 185) * 0.15
        )


class DiversificationStrategy(RecommendationRankingStrategy):
    def __init__(self, normalizer=None, history_limit=10, window_days=30):
        self.normalizer = normalizer or RecommendationTextNormalizer()
        self.history_limit = history_limit
        self.window_days = window_days

    def evaluate(self, candidate, context):
        recent = self._recent(context)
        if not recent:
            return self._component(
                1.0, (), "No recent offer history; candidate is fully diverse."
            )
        candidate_tags = self.normalizer.normalize(
            *(item for values in candidate.intelligence.values() for item in values)
        ).tokens
        penalties, evidence = [], []
        for item in recent:
            if item.offering_id == candidate.offering_id:
                penalties.append(1.0); evidence.append("same_offering")
            if (
                candidate.photoshoot_identifier
                and item.photoshoot_identifier == candidate.photoshoot_identifier
            ):
                penalties.append(0.75); evidence.append("same_collection")
            overlap = set(candidate_tags) & set(item.intelligence_tags)
            if overlap:
                penalties.append(min(0.6, len(overlap) * 0.15))
                evidence.append("theme_overlap:" + ",".join(sorted(overlap)[:4]))
            if item.offering_type == candidate.offering_type:
                penalties.append(0.15); evidence.append("same_offering_type")
        score = max(0.0, 1.0 - max(penalties, default=0.0))
        return self._component(
            score, tuple(dict.fromkeys(evidence)),
            "Recent similarity reduced diversity." if evidence else
            "Candidate differs from recent offers.",
        )

    def _recent(self, context):
        threshold = context.evaluated_at.timestamp() - self.window_days * 86400
        return tuple(
            item for item in context.recent_offer_history
            if item.presented_at is not None
            and item.presented_at.timestamp() >= threshold
        )[:self.history_limit]

    @staticmethod
    def _component(score, evidence, explanation):
        return RecommendationScoreComponent(
            key="diversification", raw_value=round(score, 8),
            ordering_value=-score, contribution=0.0,
            explanation=explanation, affected_ranking=score < 1.0,
            evidence={"recentSimilarity": evidence},
        )


class RecentOfferHistoryStrategy(RecommendationRankingStrategy):
    def evaluate(self, candidate, context):
        presented = [
            item.presented_at for item in context.recent_offer_history
            if item.offering_id == candidate.offering_id
            and item.presented_at is not None
        ]
        if not presented:
            score, age = 1.0, None
        else:
            age = max(
                0.0,
                (context.evaluated_at - max(presented)).total_seconds() / 86400,
            )
            score = (
                0.05 if age <= 1 else 0.30 if age <= 3
                else 0.55 if age <= 7 else 0.80 if age <= 30 else 1.0
            )
        return RecommendationScoreComponent(
            key="recent_offer_history", raw_value=score,
            ordering_value=-score, contribution=0.0,
            explanation=(
                "Offering has never been presented recently."
                if age is None else f"Offering was last presented {age:.2f} days ago."
            ),
            affected_ranking=score < 1.0,
            evidence={"daysSincePresented": round(age, 4) if age is not None else None},
        )


class CommerceRecommendationEngine:
    ENGINE_VERSION = "commerce_recommendation_v2_intelligent"

    def __init__(self, strategies=None, weights=None) -> None:
        self.weights = weights or RecommendationWeights()
        self.active_intent_strategy = ActivePurchaseIntentStrategy()
        self.strategies = tuple(strategies or (
            SemanticMatchStrategy(), CustomerAffinityStrategy(),
            ProductTypeFitStrategy(),
            FreshnessStrategy(), DiversificationStrategy(),
            RecentOfferHistoryStrategy(),
        ))

    def rank(self, candidates, context, *, rejection_count=None):
        candidates = tuple(candidates)
        if any(not candidate.commercially_eligible for candidate in candidates):
            raise ValueError(
                "Canonical/reference assets are identity-only and cannot enter commerce."
            )
        evaluated = tuple(self._evaluate(candidate, context) for candidate in candidates)
        active = context.active_purchase_intent_offering_id
        if active is not None and any(item[0].offering_id == active for item in evaluated):
            ordered = sorted(
                evaluated,
                key=lambda item: (
                    item[0].offering_id != active,
                    -item[2], self._recency_key(item[0]), str(item[0].offering_id),
                ),
            )
            selection_reason = "ACTIVE_INTENT"
        else:
            ordered = sorted(
                evaluated,
                key=lambda item: (
                    -item[2], self._recency_key(item[0]), str(item[0].offering_id),
                ),
            )
            selection_reason = self._selection_reason(ordered)
        selected = ordered[0][0] if ordered else None
        ranked = tuple(
            RankedRecommendationCandidate(
                rank=index, candidate=candidate, components=components,
                deterministic_reason=self._candidate_reason(
                    candidate, components, selection_reason
                ),
                selected=index == 1, final_score=final_score,
            )
            for index, (candidate, components, final_score) in enumerate(ordered, 1)
        )
        result = RecommendationResult(
            ranked_candidates=ranked, selected_candidate=selected,
            selection_reason=selection_reason, engine_version=self.ENGINE_VERSION,
            candidate_count=len(ordered), rejection_count=rejection_count,
            recommendation_summary=(
                ranked[0].deterministic_reason if ranked else None
            ),
        )
        logger.info(
            "event=commerce_recommendation_ranked engine_version=%s "
            "candidate_count=%s selected_offering_id=%s ranking_duration_source=in_memory",
            result.engine_version, result.candidate_count,
            selected.offering_id if selected else None,
        )
        return result

    def _evaluate(self, candidate, context):
        active = self.active_intent_strategy.evaluate(candidate, context)
        weighted = []
        for strategy in self.strategies:
            component = strategy.evaluate(candidate, context)
            weight = self.weights.for_key(component.key)
            weighted.append(replace(
                component,
                contribution=round(float(component.raw_value) * weight, 8),
            ))
        final_score = round(sum(item.contribution for item in weighted), 8)
        return candidate, (active, *weighted), final_score

    @staticmethod
    def _recency_key(candidate):
        return -(
            candidate.published_at.timestamp()
            if candidate.published_at is not None else float("-inf")
        )

    @staticmethod
    def _selection_reason(ordered):
        if not ordered:
            return "NO_ELIGIBLE_OFFERING"
        scores = {item[2] for item in ordered}
        if len(scores) == 1:
            selected = ordered[0][0]
            same_timestamp = sum(
                item[0].published_at == selected.published_at for item in ordered
            )
            return (
                "MOST_RECENT"
                if selected.published_at is not None
                and (len(ordered) == 1 or same_timestamp == 1)
                else "DEFAULT_ORDER"
            )
        return "INTELLIGENT_RANKING"

    @staticmethod
    def _candidate_reason(candidate, components, selection_reason):
        if selection_reason == "ACTIVE_INTENT":
            return "Active Purchase Intent offering remains eligible."
        material = sorted(
            (
                component for component in components
                if component.key != "active_purchase_intent"
                and component.affected_ranking
            ),
            key=lambda component: component.contribution,
            reverse=True,
        )
        if not material:
            return (
                "Intelligent signals were neutral; publication recency and "
                "stable offering ID determined ordering."
            )
        keys = ", ".join(item.key.replace("_", " ") for item in material[:3])
        return f'Selected "{candidate.title}" using {keys}.'
