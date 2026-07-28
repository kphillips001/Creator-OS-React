from datetime import datetime, timedelta, timezone
from uuid import UUID
import pytest

from app.models.commerce_recommendation import (
    RecommendationCandidate,
    RecommendationContext,
)
from app.services.commerce_recommendation_engine import (
    CommerceRecommendationEngine,
)


NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
FIRST = UUID("00000000-0000-0000-0000-000000000001")
SECOND = UUID("00000000-0000-0000-0000-000000000002")


def context(active=None):
    return RecommendationContext(
        creator_profile_id=2,
        active_purchase_intent_offering_id=active,
        evaluated_at=NOW,
        conversation_id="conversation-1",
    )


def candidate(offering_id=FIRST, published_at=NOW, commercially_eligible=True):
    return RecommendationCandidate(
        offering_id=offering_id,
        creator_profile_id=2,
        title=f"Offering {offering_id}",
        description="",
        offering_type="SINGLE_IMAGE",
        price_minor=999,
        currency="USD",
        published_at=published_at,
        publication_id=offering_id,
        delivery_url=f"https://share.fanvue.com/{offering_id}",
        hero_asset_id=42,
        member_asset_ids=(42,),
        commercially_eligible=commercially_eligible,
    )


def test_zero_candidates_returns_no_selection_and_versioned_trace():
    result = CommerceRecommendationEngine().rank((), context())
    assert result.selected_candidate is None
    assert result.ranked_candidates == ()
    assert result.selection_reason == "NO_ELIGIBLE_OFFERING"
    assert result.engine_version == "commerce_recommendation_v2_intelligent"
    assert result.candidate_count == 0


def test_reference_candidate_is_defensively_rejected_before_ranking():
    with pytest.raises(ValueError, match="identity-only"):
        CommerceRecommendationEngine().rank(
            (candidate(commercially_eligible=False),), context()
        )


def test_one_candidate_is_selected_with_inspectable_components():
    result = CommerceRecommendationEngine().rank((candidate(),), context())
    assert result.selected_candidate.offering_id == FIRST
    assert result.selection_reason == "MOST_RECENT"
    assert result.ranked_candidates[0].selected is True
    assert [component.key for component in result.ranked_candidates[0].components] == [
        "active_purchase_intent",
        "semantic_match",
        "customer_affinity",
        "freshness",
        "diversification",
        "recent_offer_history",
    ]


def test_newest_publication_wins_independent_of_input_order():
    old = candidate(FIRST, NOW - timedelta(days=1))
    newest = candidate(SECOND, NOW)
    engine = CommerceRecommendationEngine()
    forward = engine.rank((old, newest), context())
    reverse = engine.rank((newest, old), context())
    assert forward.selected_candidate == newest
    assert reverse.selected_candidate == newest
    assert forward.ranked_candidates == reverse.ranked_candidates


def test_stable_offering_id_breaks_equal_timestamp_ties():
    result = CommerceRecommendationEngine().rank(
        (candidate(SECOND), candidate(FIRST)), context()
    )
    assert result.selected_candidate.offering_id == FIRST
    assert result.selection_reason == "DEFAULT_ORDER"


def test_active_purchase_intent_wins_when_present_and_eligible():
    newest = candidate(FIRST, NOW)
    active = candidate(SECOND, NOW - timedelta(days=30))
    result = CommerceRecommendationEngine().rank(
        (newest, active), context(active=SECOND)
    )
    assert result.selected_candidate == active
    assert result.selection_reason == "ACTIVE_INTENT"
    component = result.ranked_candidates[0].components[0]
    assert component.raw_value == 1.0
    assert "active Purchase Intent" in component.explanation


def test_absent_active_intent_candidate_falls_back_to_parity_order():
    newest = candidate(FIRST, NOW)
    result = CommerceRecommendationEngine().rank(
        (newest,), context(active=SECOND)
    )
    assert result.selected_candidate == newest
    assert result.selection_reason == "MOST_RECENT"


def test_repeat_calls_are_deterministic_and_do_not_mutate_inputs():
    candidates = (
        candidate(SECOND, NOW - timedelta(hours=1)),
        candidate(FIRST, NOW),
    )
    before = candidates
    engine = CommerceRecommendationEngine()
    first = engine.rank(candidates, context(), rejection_count=3)
    second = engine.rank(candidates, context(), rejection_count=3)
    assert first == second
    assert candidates == before
    assert first.rejection_count == 3
