"""Deterministic customer learning from observed Commerce outcomes."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from uuid import UUID

from app.models.commerce_learning import CommerceRecommendationOutcomeType
from app.repositories.commerce_learning_repository import CommerceLearningRepository


class CommerceLearningService:
    EFFECTS = {
        "PRESENTED": 0.0, "OPENED": 0.20, "PURCHASED": 1.0,
        "IGNORED": -0.10, "EXPIRED": -0.08, "DECLINED": -0.20,
        "ABANDONED": -0.12, "REFUNDED": -1.0,
        "WOULD_HAVE_SOLD": 0.15,
    }
    CATEGORIES = {
        "themes", "activity", "location", "clothing", "wardrobe", "outfit",
        "suggested_collections", "collections", "conversation_themes",
    }

    def __init__(self, repository=None, clock=lambda: datetime.now(timezone.utc)):
        self.repository = repository or CommerceLearningRepository()
        self.clock = clock

    def record_observed_outcome(
        self, *, creator_profile_id, fanvue_account_id,
        external_fanvue_user_uuid, telegram_user_id,
        commercial_offering_id, outcome_type, source_event_key,
        purchase_intent_id=None, observed_at=None, evidence=None,
        recommendation_trace=None,
    ):
        normalized = (
            outcome_type if isinstance(outcome_type, CommerceRecommendationOutcomeType)
            else CommerceRecommendationOutcomeType(str(outcome_type).upper())
        )
        observed = observed_at or self.clock()
        offering_evidence = self.repository.offering_evidence(
            UUID(str(commercial_offering_id))
        )
        trace = dict(recommendation_trace or {})
        merged = self._normalize_evidence({
            **offering_evidence,
            **dict(evidence or {}),
            "conversation_themes": self._observed_conversation_themes(trace),
        })
        outcome = self.repository.record_outcome(
            creator_profile_id=int(creator_profile_id),
            fanvue_account_id=int(fanvue_account_id),
            external_fanvue_user_uuid=UUID(str(external_fanvue_user_uuid)),
            telegram_user_id=telegram_user_id,
            commercial_offering_id=UUID(str(commercial_offering_id)),
            purchase_intent_id=(
                UUID(str(purchase_intent_id)) if purchase_intent_id else None
            ),
            outcome_type=normalized, observed_at=observed,
            source_event_key=str(source_event_key),
            evidence=merged, recommendation_trace=trace,
        )
        return outcome, self.rebuild_profile(
            creator_profile_id=int(creator_profile_id),
            fanvue_account_id=int(fanvue_account_id),
            external_fanvue_user_uuid=UUID(str(external_fanvue_user_uuid)),
            telegram_user_id=telegram_user_id,
        )

    def observe_purchase_intent(self, intent, outcome_type, *, source_event_key):
        if intent.external_fanvue_user_uuid is None:
            return None
        return self.record_observed_outcome(
            creator_profile_id=intent.creator_profile_id,
            fanvue_account_id=intent.fanvue_account_id,
            external_fanvue_user_uuid=intent.external_fanvue_user_uuid,
            telegram_user_id=intent.telegram_user_id,
            commercial_offering_id=intent.commercial_offering_id,
            purchase_intent_id=intent.purchase_intent_id,
            outcome_type=outcome_type, source_event_key=source_event_key,
            observed_at=(
                intent.purchased_at or intent.clicked_at or intent.presented_at
                or intent.abandoned_at or intent.updated_at or self.clock()
            ),
            evidence={
                "price_minor": intent.expected_price_minor,
            },
            recommendation_trace=dict(intent.created_metadata or {}).get(
                "recommendation_trace", {}
            ),
        )

    def rebuild_profile(
        self, *, creator_profile_id, fanvue_account_id,
        external_fanvue_user_uuid, telegram_user_id=None,
    ):
        outcomes = self.repository.list_outcomes(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=external_fanvue_user_uuid,
        )
        strengths = defaultdict(lambda: defaultdict(float))
        counts = defaultdict(lambda: defaultdict(int))
        outcome_counts = Counter()
        purchases = []
        purchase_prices = []
        offering_types = Counter()
        for outcome in outcomes:
            kind = outcome.outcome_type.value
            outcome_counts[kind] += 1
            effect = self.EFFECTS[kind]
            evidence = dict(outcome.evidence)
            if effect == 0:
                continue
            for category in self.CATEGORIES:
                for value in evidence.get(category, ()):
                    key = str(value).strip().lower()
                    if key:
                        strengths[category][key] += effect
                        counts[category][key] += 1
            offering_type = str(evidence.get("offering_type") or "")
            if offering_type:
                strengths["offering_type"][offering_type] += effect
                counts["offering_type"][offering_type] += 1
                if kind == "PURCHASED":
                    offering_types[offering_type] += 1
            photoshoot = str(evidence.get("photoshoot_identifier") or "")
            if photoshoot:
                strengths["photoshoot"][photoshoot] += effect
                counts["photoshoot"][photoshoot] += 1
            price = evidence.get("price_minor")
            if kind == "PURCHASED":
                purchases.append(outcome.observed_at)
                if price is not None:
                    purchase_prices.append(int(price))
        preferences = {}
        for category in sorted(strengths):
            preferences[category] = {
                key: {
                    "score": round(max(0.0, min(1.0, 0.5 + value / 2)), 4),
                    "confidence": round(min(1.0, counts[category][key] / 5), 4),
                    "observations": counts[category][key],
                    "netEvidence": round(value, 4),
                }
                for key, value in sorted(strengths[category].items())
            }
        purchases.sort()
        intervals = [
            (right - left).total_seconds() / 86400
            for left, right in zip(purchases, purchases[1:])
        ]
        purchase_count = len(purchases)
        evidence_count = sum(
            count for kind, count in outcome_counts.items()
            if self.EFFECTS[kind] != 0
        )
        preferred_type = (
            offering_types.most_common(1)[0][0] if offering_types else None
        )
        return self.repository.upsert_profile(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=external_fanvue_user_uuid,
            telegram_user_id=telegram_user_id,
            preferences=preferences, outcome_counts=dict(outcome_counts),
            preferred_offering_type=preferred_type,
            favorite_media_type=preferred_type,
            average_price_minor=(
                round(sum(purchase_prices) / len(purchase_prices))
                if purchase_prices else None
            ),
            preferred_price_min_minor=(
                min(purchase_prices) if purchase_prices else None
            ),
            preferred_price_max_minor=(
                max(purchase_prices) if purchase_prices else None
            ),
            repeat_purchase_frequency=(
                max(0, purchase_count - 1) / purchase_count
                if purchase_count else 0.0
            ),
            average_purchase_interval_days=(
                sum(intervals) / len(intervals) if intervals else None
            ),
            confidence=min(1.0, evidence_count / 10),
            evidence_count=evidence_count,
            last_observed_at=(outcomes[-1].observed_at if outcomes else None),
        )

    @classmethod
    def _normalize_evidence(cls, evidence):
        result = dict(evidence)
        intelligence = result.pop("intelligence", ()) or ()
        for profile in intelligence:
            if not isinstance(profile, dict):
                continue
            for category in cls.CATEGORIES:
                raw = profile.get(category)
                values = raw if isinstance(raw, (list, tuple)) else (raw,) if raw else ()
                result.setdefault(category, [])
                result[category].extend(str(item) for item in values)
        for category in cls.CATEGORIES:
            raw = result.get(category, ())
            values = raw if isinstance(raw, (list, tuple)) else (raw,) if raw else ()
            result[category] = list(dict.fromkeys(
                str(item).strip().lower() for item in values if str(item).strip()
            ))
        return result

    @staticmethod
    def _observed_conversation_themes(trace):
        ranked = trace.get("rankedCandidates")
        if not isinstance(ranked, (list, tuple)):
            return []
        selected = next((
            item for item in ranked
            if isinstance(item, dict) and item.get("selected")
        ), None)
        if not selected:
            return []
        components = selected.get("components")
        if not isinstance(components, (list, tuple)):
            return []
        semantic = next((
            item for item in components
            if isinstance(item, dict) and item.get("key") == "semantic_match"
        ), None)
        evidence = semantic.get("evidence") if semantic else None
        tokens = evidence.get("matchedTokens") if isinstance(evidence, dict) else ()
        return list(tokens) if isinstance(tokens, (list, tuple)) else []
