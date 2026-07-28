from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.models.commerce_learning import (
    CommerceRecommendationOutcome,
    CustomerCommerceLearningProfile,
)
from app.services.commerce_learning_service import CommerceLearningService
from app.services.schema_manager_service import SchemaManagerService


NOW = datetime(2026, 7, 25, 12, tzinfo=timezone.utc)
BUYER = UUID("10000000-0000-0000-0000-000000000001")
OFFERING = UUID("20000000-0000-0000-0000-000000000001")


class MemoryLearningRepository:
    def __init__(self):
        self.outcomes = {}
        self.profile = None
        self.evidence = {
            "offering_type": "PHOTOSET",
            "price_minor": 999,
            "photoshoot_identifier": "beach-day",
            "intelligence": [{
                "themes": ["beach"],
                "activity": ["sunbathing"],
                "location": ["malibu"],
                "outfit": ["red bikini"],
                "suggested_collections": ["summer"],
            }],
        }

    def offering_evidence(self, _offering_id):
        return self.evidence

    def record_outcome(self, **values):
        existing = self.outcomes.get(values["source_event_key"])
        if existing:
            return existing
        outcome = CommerceRecommendationOutcome(
            outcome_id=uuid4(),
            creator_profile_id=values["creator_profile_id"],
            fanvue_account_id=values["fanvue_account_id"],
            external_fanvue_user_uuid=values["external_fanvue_user_uuid"],
            telegram_user_id=values["telegram_user_id"],
            commercial_offering_id=values["commercial_offering_id"],
            purchase_intent_id=values["purchase_intent_id"],
            outcome_type=values["outcome_type"],
            observed_at=values["observed_at"],
            source_event_key=values["source_event_key"],
            evidence=values["evidence"],
            recommendation_trace=values["recommendation_trace"],
        )
        self.outcomes[values["source_event_key"]] = outcome
        return outcome

    def list_outcomes(self, **_values):
        return tuple(sorted(
            self.outcomes.values(), key=lambda item: (item.observed_at, item.outcome_id)
        ))

    def upsert_profile(self, **values):
        self.profile = CustomerCommerceLearningProfile(
            learning_profile_id=(
                self.profile.learning_profile_id if self.profile else uuid4()
            ),
            creator_profile_id=values["creator_profile_id"],
            fanvue_account_id=values["fanvue_account_id"],
            external_fanvue_user_uuid=values["external_fanvue_user_uuid"],
            telegram_user_id=values["telegram_user_id"],
            preferences=values["preferences"],
            outcome_counts=values["outcome_counts"],
            preferred_offering_type=values["preferred_offering_type"],
            favorite_media_type=values["favorite_media_type"],
            average_price_minor=values["average_price_minor"],
            preferred_price_min_minor=values["preferred_price_min_minor"],
            preferred_price_max_minor=values["preferred_price_max_minor"],
            repeat_purchase_frequency=values["repeat_purchase_frequency"],
            average_purchase_interval_days=values["average_purchase_interval_days"],
            confidence=values["confidence"],
            evidence_count=values["evidence_count"],
            last_observed_at=values["last_observed_at"],
            created_at=NOW,
            updated_at=NOW,
        )
        return self.profile


def record(service, kind, key, when=NOW, recommendation_trace=None):
    return service.record_observed_outcome(
        creator_profile_id=1,
        fanvue_account_id=2,
        external_fanvue_user_uuid=BUYER,
        telegram_user_id=3,
        commercial_offering_id=OFFERING,
        outcome_type=kind,
        source_event_key=key,
        observed_at=when,
        recommendation_trace=recommendation_trace,
    )[1]


def test_purchase_builds_verified_multidimensional_affinity():
    profile = record(
        CommerceLearningService(MemoryLearningRepository()), "PURCHASED", "purchase:1"
    )

    assert profile.preferences["themes"]["beach"]["score"] == 1.0
    assert profile.preferences["location"]["malibu"]["netEvidence"] == 1.0
    assert profile.preferences["photoshoot"]["beach-day"]["score"] == 1.0
    assert profile.preferred_offering_type == "PHOTOSET"
    assert profile.average_price_minor == 999


def test_repeat_purchases_update_frequency_interval_and_confidence():
    repository = MemoryLearningRepository()
    service = CommerceLearningService(repository)
    record(service, "PURCHASED", "purchase:1", NOW)
    profile = record(service, "PURCHASED", "purchase:2", NOW + timedelta(days=4))

    assert profile.repeat_purchase_frequency == pytest.approx(0.5)
    assert profile.average_purchase_interval_days == pytest.approx(4)
    assert profile.confidence == pytest.approx(0.2)
    assert profile.outcome_counts == {"PURCHASED": 2}


def test_negative_outcomes_weaken_and_refund_strongly_reverses_affinity():
    repository = MemoryLearningRepository()
    service = CommerceLearningService(repository)
    purchased = record(service, "PURCHASED", "purchase:1")
    ignored = record(service, "IGNORED", "ignored:1")
    expired = record(service, "EXPIRED", "expired:1")
    refunded = record(service, "REFUNDED", "refund:1")

    assert ignored.preferences["themes"]["beach"]["score"] < (
        purchased.preferences["themes"]["beach"]["score"]
    )
    assert expired.preferences["themes"]["beach"]["score"] < (
        ignored.preferences["themes"]["beach"]["score"]
    )
    assert refunded.preferences["themes"]["beach"]["score"] < (
        expired.preferences["themes"]["beach"]["score"]
    )


def test_duplicate_source_is_idempotent_and_unknown_outcome_is_rejected():
    repository = MemoryLearningRepository()
    service = CommerceLearningService(repository)
    first = record(service, "OPENED", "open:1")
    second = record(service, "OPENED", "open:1")

    assert first.evidence_count == second.evidence_count == 1
    assert len(repository.outcomes) == 1
    with pytest.raises(ValueError):
        record(service, "INFERRED_INTEREST", "invalid:1")


def test_cold_start_profile_is_neutral_and_deterministic():
    repository = MemoryLearningRepository()
    service = CommerceLearningService(repository)
    profile = service.rebuild_profile(
        creator_profile_id=1,
        fanvue_account_id=2,
        external_fanvue_user_uuid=BUYER,
    )

    assert profile.preferences == {}
    assert profile.confidence == 0
    assert profile.evidence_count == 0
    assert profile.preferred_offering_type is None


def test_presentation_is_audited_but_does_not_infer_preference():
    profile = record(
        CommerceLearningService(MemoryLearningRepository()),
        "PRESENTED",
        "presented:1",
    )

    assert profile.outcome_counts == {"PRESENTED": 1}
    assert profile.preferences == {}
    assert profile.confidence == 0
    assert profile.evidence_count == 0


def test_observed_selected_conversation_theme_becomes_explainable_evidence():
    trace = {"rankedCandidates": [{
        "selected": True,
        "components": [{
            "key": "semantic_match",
            "evidence": {"matchedTokens": ["beach", "sunset"]},
        }],
    }]}
    profile = record(
        CommerceLearningService(MemoryLearningRepository()),
        "OPENED",
        "opened:conversation-theme",
        recommendation_trace=trace,
    )

    assert set(profile.preferences["conversation_themes"]) == {
        "beach", "sunset",
    }


def test_learning_migration_enforces_one_profile_and_idempotent_outcomes():
    forward = Path(
        "migrations/forward/20260725_010_commerce_recommendation_learning.sql"
    ).read_text(encoding="utf-8")
    rollback = Path(
        "migrations/rollback/20260725_010_commerce_recommendation_learning.sql"
    ).read_text(encoding="utf-8")

    assert "source_event_key TEXT NOT NULL UNIQUE" in forward
    assert (
        "UNIQUE (creator_profile_id,fanvue_account_id,"
        "external_fanvue_user_uuid)"
    ) in forward
    assert "'REFUNDED'" in forward
    assert "DROP TABLE IF EXISTS" in rollback
    requirements = SchemaManagerService.MIGRATION_SCHEMA_REQUIREMENTS[
        "20260725_010_commerce_recommendation_learning.sql"
    ]
    assert "commerce_recommendation_outcomes" in requirements
    assert "customer_commerce_learning_profiles" in requirements
    assert "idx_commerce_recommendation_outcomes_customer" in forward
