from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.models.commerce_recommendation import (
    RecommendationCandidate,
    RecommendationContext,
    RecommendationHistoryEntry,
    RecommendationWeights,
)
from app.services.commerce_recommendation_engine import (
    CommerceRecommendationEngine,
    CustomerAffinityStrategy,
    DiversificationStrategy,
    FreshnessStrategy,
    RecentOfferHistoryStrategy,
    SemanticMatchStrategy,
)
from app.services.recommendation_text_normalizer import (
    RecommendationTextNormalizer,
)


NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
ONE = UUID("00000000-0000-0000-0000-000000000001")
TWO = UUID("00000000-0000-0000-0000-000000000002")


def candidate(
    offering_id=ONE, *, title="Private Collection",
    description="", published_at=NOW, offering_type="PHOTOSET",
    intelligence=None, photoshoot=None,
):
    return RecommendationCandidate(
        offering_id=offering_id, creator_profile_id=2, title=title,
        description=description, offering_type=offering_type,
        price_minor=999, currency="USD", published_at=published_at,
        publication_id=offering_id,
        delivery_url=f"https://share.fanvue.com/{offering_id}",
        hero_asset_id=42, member_asset_ids=(42, 43),
        photoshoot_identifier=photoshoot,
        intelligence=intelligence or {},
    )


def context(**changes):
    values = dict(
        creator_profile_id=2, active_purchase_intent_offering_id=None,
        evaluated_at=NOW, current_request=None,
    )
    values.update(changes)
    return RecommendationContext(**values)


def history(
    offering_id=ONE, *, days=1, status="PRESENTED",
    attribution=None, tags=(), offering_type="PHOTOSET", photoshoot=None,
):
    return RecommendationHistoryEntry(
        offering_id=offering_id, offering_type=offering_type,
        status=status, presented_at=NOW - timedelta(days=days),
        purchased_at=(NOW - timedelta(days=days) if status == "PURCHASED" else None),
        attribution_result=attribution, intelligence_tags=tags,
        photoshoot_identifier=photoshoot,
    )


def test_default_weights_are_validated_and_sum_to_one():
    weights = RecommendationWeights()
    assert sum((
        weights.semantic_match, weights.customer_affinity,
        weights.freshness, weights.diversification,
        weights.recent_offer_history,
    )) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="between 0 and 1"):
        RecommendationWeights(semantic_match=-0.1)
    with pytest.raises(ValueError, match="sum to 1"):
        RecommendationWeights(semantic_match=0.5)


def test_normalization_removes_filler_punctuation_and_is_deterministic():
    normalizer = RecommendationTextNormalizer()
    first = normalizer.normalize("Show me BEACH, sunset photos please!")
    second = normalizer.normalize("show me beach sunset photos please")
    assert first == second
    assert first.tokens == ("beach", "sunset")
    assert first.phrases == ("beach sunset",)


def test_semantic_exact_phrase_and_title_beat_partial_token_match():
    strategy = SemanticMatchStrategy()
    query = context(current_request="coastal sunset")
    exact = strategy.evaluate(
        candidate(title="Coastal Sunset Photoset"), query
    )
    partial = strategy.evaluate(
        candidate(title="Coastal Portrait"), query
    )
    assert exact.raw_value > partial.raw_value
    assert "coastal sunset" in exact.evidence["matchedPhrases"]
    assert "title" in exact.evidence["matchedFields"]


def test_semantic_uses_structured_fields_and_handles_missing_metadata():
    strategy = SemanticMatchStrategy()
    structured = strategy.evaluate(candidate(
        intelligence={
            "themes": ("beach",), "activity": ("surfing",),
            "location": ("malibu",), "clothing": ("red bikini",),
        },
    ), context(current_request="surfing in malibu red bikini"))
    missing = strategy.evaluate(
        candidate(title="Untitled", intelligence={}),
        context(current_request="surfing in malibu red bikini"),
    )
    neutral = strategy.evaluate(candidate(), context())
    assert structured.raw_value > missing.raw_value
    assert neutral.raw_value == 0.5


def test_customer_affinity_uses_only_supplied_verified_evidence():
    strategy = CustomerAffinityStrategy()
    matched = strategy.evaluate(candidate(
        intelligence={"themes": ("coastal beach",)}
    ), context(
        verified_affinity_tags=("beach", "sunset"),
        verified_affinity_offering_types=("PHOTOSET",),
    ))
    unrelated = strategy.evaluate(candidate(
        intelligence={"themes": ("studio",)}, offering_type="SINGLE_IMAGE",
    ), context(
        verified_affinity_tags=("beach",),
        verified_affinity_offering_types=("PHOTOSET",),
    ))
    neutral = strategy.evaluate(candidate(), context())
    assert matched.raw_value > unrelated.raw_value
    assert matched.evidence["sourceTypes"] == ("ATTRIBUTED_PURCHASE",)
    assert neutral.raw_value == 0.5


def test_customer_affinity_prefers_persisted_observed_learning_profile():
    strategy = CustomerAffinityStrategy()
    learning = {
        "preferences": {
            "themes": {
                "beach": {
                    "score": 1.0, "confidence": 0.8, "observations": 4,
                },
            },
            "photoshoot": {
                "beach-day": {
                    "score": 0.9, "confidence": 0.8, "observations": 4,
                },
            },
        },
        "preferredOfferingType": "PHOTOSET",
        "preferredPriceMinMinor": 899,
        "preferredPriceMaxMinor": 1099,
        "repeatPurchaseFrequency": 0.5,
        "confidence": 0.8,
        "evidenceCount": 8,
    }
    learned = strategy.evaluate(
        candidate(
            title="Beach Collection",
            intelligence={"themes": ("beach",)},
            photoshoot="beach-day",
        ),
        context(commerce_learning_profile=learning),
    )
    unrelated = strategy.evaluate(
        candidate(
            title="Studio Collection",
            intelligence={"themes": ("studio",)},
            photoshoot="studio-day",
            offering_type="SINGLE_IMAGE",
        ),
        context(commerce_learning_profile=learning),
    )

    assert learned.raw_value > unrelated.raw_value
    assert learned.affected_ranking is True
    assert learned.evidence["sourceTypes"] == ("COMMERCE_LEARNING_PROFILE",)
    assert learned.evidence["learningConfidence"] == 0.8
    assert {
        item["reason"] for item in learned.evidence["adaptiveBoosts"]
    } == {
        "preferred_offering_type", "preferred_price_range",
        "preferred_photoshoot", "repeat_purchase_pattern",
    }


@pytest.mark.parametrize(
    ("days", "expected"),
    [(1, 1.0), (7, 0.9), (30, 0.7), (90, 0.5), (180, 0.3), (400, 0.15)],
)
def test_freshness_documented_boundaries(days, expected):
    component = FreshnessStrategy().evaluate(
        candidate(published_at=NOW - timedelta(days=days)), context()
    )
    assert component.raw_value == pytest.approx(expected)


def test_diversification_penalizes_same_offer_collection_and_themes():
    strategy = DiversificationStrategy()
    same = strategy.evaluate(candidate(
        ONE, photoshoot="shoot-1", intelligence={"themes": ("beach",)}
    ), context(recent_offer_history=(
        history(ONE, photoshoot="shoot-1", tags=("beach",)),
    )))
    unrelated = strategy.evaluate(candidate(
        TWO, photoshoot="shoot-2", intelligence={"themes": ("studio",)}
    ), context(recent_offer_history=(
        history(ONE, photoshoot="shoot-1", tags=("beach",)),
    )))
    absent = strategy.evaluate(candidate(), context())
    assert same.raw_value == 0.0
    assert unrelated.raw_value > same.raw_value
    assert absent.raw_value == 1.0


def test_diversification_history_is_bounded_to_ten_records():
    recent = tuple(
            history(
                UUID(f"00000000-0000-0000-0000-{index:012d}"),
                tags=("beach",) if index == 11 else ("studio",),
                offering_type="SINGLE_IMAGE",
            )
        for index in range(1, 12)
    )
    component = DiversificationStrategy(history_limit=10).evaluate(
        candidate(
            UUID("00000000-0000-0000-0000-000000000999"),
            intelligence={"themes": ("beach",)},
        ),
        context(recent_offer_history=recent),
    )
    assert component.raw_value == 1.0


def test_recent_offer_history_penalty_decays_and_never_offered_is_full():
    strategy = RecentOfferHistoryStrategy()
    just = strategy.evaluate(
        candidate(), context(recent_offer_history=(history(days=0.5),))
    )
    old = strategy.evaluate(
        candidate(), context(recent_offer_history=(history(days=40),))
    )
    never = strategy.evaluate(candidate(), context())
    assert just.raw_value == 0.05
    assert old.raw_value == 1.0
    assert never.raw_value == 1.0


def test_semantic_and_affinity_can_change_selection_between_eligible_candidates():
    semantic_old = candidate(
        ONE, title="Coastal Sunset Photoset",
        published_at=NOW - timedelta(days=200),
        intelligence={"themes": ("beach", "sunset")},
    )
    fresh_unrelated = candidate(
        TWO, title="Studio Portrait", published_at=NOW,
        intelligence={"themes": ("studio",)},
    )
    result = CommerceRecommendationEngine().rank(
        (fresh_unrelated, semantic_old),
        context(
            current_request="coastal sunset beach",
            verified_affinity_tags=("beach", "sunset"),
            verified_affinity_offering_types=("PHOTOSET",),
        ),
    )
    assert result.selected_candidate == semantic_old
    assert result.selection_reason == "INTELLIGENT_RANKING"


def test_custom_weights_change_ranking_without_strategy_changes():
    semantic_old = candidate(
        ONE, title="Beach", published_at=NOW - timedelta(days=200)
    )
    fresh = candidate(TWO, title="Studio", published_at=NOW)
    semantic_only = RecommendationWeights(
        semantic_match=1, customer_affinity=0, freshness=0,
        diversification=0, recent_offer_history=0,
    )
    freshness_only = RecommendationWeights(
        semantic_match=0, customer_affinity=0, freshness=1,
        diversification=0, recent_offer_history=0,
    )
    request = context(current_request="beach")
    assert CommerceRecommendationEngine(
        weights=semantic_only
    ).rank((semantic_old, fresh), request).selected_candidate == semantic_old
    assert CommerceRecommendationEngine(
        weights=freshness_only
    ).rank((semantic_old, fresh), request).selected_candidate == fresh


def test_trace_contributions_sum_and_active_intent_overrides_weights():
    active = candidate(ONE, title="Studio", published_at=NOW - timedelta(days=300))
    semantic = candidate(TWO, title="Beach Sunset", published_at=NOW)
    result = CommerceRecommendationEngine().rank(
        (semantic, active),
        context(active_purchase_intent_offering_id=ONE, current_request="beach sunset"),
    )
    assert result.selected_candidate == active
    assert result.selection_reason == "ACTIVE_INTENT"
    for ranked in result.ranked_candidates:
        weighted = [
            item.contribution for item in ranked.components
            if item.key != "active_purchase_intent"
        ]
        assert sum(weighted) == pytest.approx(ranked.final_score)


def test_neutral_signals_preserve_newest_then_uuid_fallback():
    old = candidate(ONE, published_at=NOW - timedelta(days=2))
    newest = candidate(TWO, published_at=NOW)
    assert CommerceRecommendationEngine().rank(
        (old, newest), context()
    ).selected_candidate == newest
    tied = CommerceRecommendationEngine().rank(
        (candidate(TWO), candidate(ONE)), context()
    )
    assert tied.selected_candidate.offering_id == ONE
