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


def context(active=None, **changes):
    values = dict(
        creator_profile_id=2,
        active_purchase_intent_offering_id=active,
        evaluated_at=NOW,
        conversation_id="conversation-1",
    )
    values.update(changes)
    return RecommendationContext(**values)


def candidate(offering_id=FIRST, published_at=NOW, commercially_eligible=True, **changes):
    values = dict(
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
    values.update(changes)
    return RecommendationCandidate(**values)


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
        "product_type_fit",
        "freshness",
        "diversification",
        "recent_offer_history",
    ]


def opportunity_candidates():
    single = candidate(
        FIRST, title="Warm portrait", description="one intimate portrait",
        price_minor=799,
    )
    bundle = candidate(
        SECOND, title="Complete bedroom set", description="all three photos",
        offering_type="BUNDLE", price_minor=1999,
        photoshoot_identifier="bundle", selling_mode="BUNDLE", member_count=3,
    )
    session = candidate(
        UUID("00000000-0000-0000-0000-000000000003"),
        title="Private progressive session", description="ongoing intimate story",
        offering_type="SINGLE_IMAGE", price_minor=1299,
        photoshoot_identifier="session", selling_mode="SESSION", member_count=3,
    )
    return single, bundle, session


@pytest.mark.parametrize("index", (0, 1, 2))
def test_each_opportunity_type_wins_when_it_is_the_only_candidate(index):
    choices = opportunity_candidates()
    result = CommerceRecommendationEngine().rank((choices[index],), context())
    assert result.selected_candidate == choices[index]


@pytest.mark.parametrize(
    ("request_context", "expected_index", "reason"),
    (
        ({"current_request": "I want the full set"}, 1, "EXPLICIT_BUNDLE_REQUEST"),
        ({"current_request": "just one pic"}, 0, "EXPLICIT_SINGLE_IMAGE_REQUEST"),
        ({"current_request": "something cheaper", "price_sensitive": True}, 0, "PRICE_FIT"),
        ({"engagement_score": 0.95}, 2, "SESSION_HIGH_ENGAGEMENT_MATCH"),
    ),
)
def test_cross_type_selection_follows_explicit_product_fit(
    request_context, expected_index, reason
):
    choices = opportunity_candidates()
    result = CommerceRecommendationEngine().rank(choices, context(**request_context))
    assert result.selected_candidate == choices[expected_index]
    component = next(
        item for item in result.ranked_candidates[0].components
        if item.key == "product_type_fit"
    )
    assert component.evidence["reasonCode"] == reason


def test_relevant_single_beats_unrelated_more_expensive_bundle():
    single, bundle, _ = opportunity_candidates()
    result = CommerceRecommendationEngine().rank(
        (single, bundle), context(current_request="one warm portrait")
    )
    assert result.selected_candidate == single


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
