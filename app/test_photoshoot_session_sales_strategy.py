import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.repositories.autonomous_sales_progression_repository import AutonomousSalesProgressionRepository
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService
from app.services.photoshoot_session_sales_strategy_service import (
    PhotoshootSessionSalesStrategyService,
)


class Strategies:
    def __init__(self, authored_teaser_asset_id=None): self.rows = {}; self.saved = []; self.authored_teaser_asset_id = authored_teaser_asset_id
    def get(self, session_id, version): return self.rows.get((session_id, version))
    def latest(self, session_id):
        rows = [value for (candidate, _), value in self.rows.items() if candidate == session_id]
        return rows[-1] if rows else None
    def completed_session_teaser_asset_id(self, _deliverable_id): return self.authored_teaser_asset_id
    def save(self, **values):
        model = SimpleNamespace(
            photoshoot_session_id=values["photoshoot_session_id"],
            strategy_version=values["strategy_version"],
            intelligence_version=values["intelligence_version"],
            shots=tuple(SimpleNamespace(**item) for item in values["strategy_data"]["shots"]),
            suggested_sales_progression=tuple(values["strategy_data"]["suggested_sales_progression"]),
            best_teaser_asset_id=values["strategy_data"]["best_teaser_asset_id"],
        )
        self.saved.append(values); self.rows[(values["photoshoot_session_id"], values["strategy_version"])] = model
        return model


class Photoshoots:
    def __init__(self): self.deliverable_id = uuid4()
    def get(self, _deliverable_id):
        return {"deliverable_id": self.deliverable_id, "creator_profile_id": 7,
                "photoshoot_session_id": "session-1", "is_archived": False,
                "selling_mode": "SESSION", "registration_state": "IN_ASSET_LIBRARY"}
    def get_intelligence(self, _session_id):
        production = {"theme": "intimate progression", "story": "gradual reveal",
            "commercial_title": "Complete Session", "subtitle": "A progression",
            "commercial_summary": "A complete commercial sequence.",
            "buyer_profile": {"audience": "collector"},
            "sales_strategy": {"positioning": "guided session"},
            "sales_brain_brief": "Sell the guided progression."}
        return {"status": "READY", "pipeline_stage": "COMPLETE",
                "intelligence_version": "intelligence-v2", "profile_data": production,
                "production_analysis": production,
                "cross_validation": {"teaser_asset_id": 20, "closing_asset_id": 30}}
    def members(self, _session_id):
        return ({"asset_id": 10, "shot_order": 1}, {"asset_id": 20, "shot_order": 2},
                {"asset_id": 30, "shot_order": 3})
    def shot_intelligence(self, _session_id, _version):
        return ({"asset_id": 10, "profile_data": {"sequence_role": "opening", "teaser_suitability": "medium"}},
                {"asset_id": 20, "profile_data": {"sequence_role": "bridge", "teaser_suitability": "high"}},
                {"asset_id": 30, "profile_data": {"sequence_role": "closing", "cover_suitability": "high"}})


def strategy():
    return {
        "best_teaser_asset_id": 20,
        "recommended_customer_entry_point": "Lead with curiosity and establish consent to continue.",
        "suggested_sales_progression": [20, 10, 30],
        "recommended_stopping_points": [{"after_asset_id": 10, "goal": "Check engagement"}],
        "session_completion_strategy": "Close after the finale and acknowledge completion.",
        "customer_engagement_strategy": "Use responses to pace the reveal.",
        "escalation_pacing": "Measured, with one check-in before the finale.",
        "overall_selling_approach": "Sell the progression as a guided experience.",
        "shots": [
            {"asset_id": 10, "sales_position": 2, "sales_role": "FIRST_UNLOCK",
             "teaser_recommended": False, "access_recommendation": "PAID",
             "recommended_progression": "First paid reveal", "suggested_next_asset_id": 30,
             "customer_journey_purpose": "Commitment", "escalation_role": "Begin escalation",
             "psychological_objective": "Reward curiosity", "conversation_goal": "Invite the first unlock"},
            {"asset_id": 20, "sales_position": 1, "sales_role": "FREE_TEASER",
             "teaser_recommended": True, "access_recommendation": "FREE",
             "recommended_progression": "Open the session", "suggested_next_asset_id": 10,
             "customer_journey_purpose": "Entry", "escalation_role": "Set expectation",
             "psychological_objective": "Build curiosity", "conversation_goal": "Gain engagement"},
            {"asset_id": 30, "sales_position": 3, "sales_role": "FINALE",
             "teaser_recommended": False, "access_recommendation": "PAID",
             "recommended_progression": "Complete the experience", "suggested_next_asset_id": None,
             "customer_journey_purpose": "Completion", "escalation_role": "Resolve escalation",
             "psychological_objective": "Deliver payoff", "conversation_goal": "Close the session"},
        ],
    }


def test_completed_photoshoot_generates_complete_strategy_from_persisted_intelligence_only():
    calls = []; repository = Strategies()
    service = PhotoshootSessionSalesStrategyService(
        repository=repository, photoshoots=Photoshoots(),
        strategy_runner=lambda source: calls.append(source) or strategy(),
    )
    result = service.generate("deliverable-1", creator_profile_id=7)
    assert len(result.shots) == 3
    assert {shot.asset_id for shot in result.shots} == {10, 20, 30}
    assert result.suggested_sales_progression == (20, 10, 30)
    assert calls[0]["production_intelligence"]["theme"] == "intimate progression"
    assert calls[0]["ordered_shots"][1]["shot_intelligence"]["teaser_suitability"] == "high"
    assert calls[0]["cross_validation"]["teaser_asset_id"] == 20
    assert "image_reference" not in str(calls[0]) and "file_path" not in str(calls[0])


def test_authored_session_teaser_can_lack_original_shot_intelligence_and_is_only_free_step():
    photoshoots = Photoshoots()
    photoshoots.members = lambda _session_id: (
        {"asset_id": 40, "shot_order": 1}, {"asset_id": 10, "shot_order": 2},
        {"asset_id": 20, "shot_order": 3}, {"asset_id": 30, "shot_order": 4},
    )
    result = strategy()
    result["best_teaser_asset_id"] = 40
    result["suggested_sales_progression"] = [40, 10, 20, 30]
    result["recommended_stopping_points"] = [{"after_asset_id": 10, "goal": "Check engagement"}]
    result["shots"] = [
        {"asset_id": 40, "sales_position": 1, "sales_role": "FREE_TEASER",
         "teaser_recommended": True, "access_recommendation": "FREE",
         "recommended_progression": "Open the session", "suggested_next_asset_id": 10,
         "customer_journey_purpose": "Entry", "escalation_role": "Set expectation",
         "psychological_objective": "Build curiosity", "conversation_goal": "Gain engagement"},
        *[{**item, "sales_position": index + 2, "shot_order": index + 2,
           "access_recommendation": "PAID", "sales_role": item["sales_role"] if item["sales_role"] != "FREE_TEASER" else "ESCALATION"}
          for index, item in enumerate(strategy()["shots"])],
    ]
    calls = []
    generated = PhotoshootSessionSalesStrategyService(
        repository=Strategies(authored_teaser_asset_id=40), photoshoots=photoshoots,
        strategy_runner=lambda source: calls.append(source) or result,
    ).generate("deliverable-1", creator_profile_id=7)

    assert calls[0]["ordered_shots"][0]["shot_intelligence"]["purpose"] == "PHOTOSHOOT_SESSION_TEASER"
    assert [shot.access_recommendation for shot in generated.shots].count("FREE") == 1
    assert [shot.access_recommendation for shot in generated.shots].count("PAID") == 3


def test_same_version_is_idempotent_and_new_version_generates_cleanly():
    calls = []; repository = Strategies()
    service = PhotoshootSessionSalesStrategyService(
        repository=repository, photoshoots=Photoshoots(),
        strategy_runner=lambda source: calls.append(source) or strategy(),
    )
    first = service.generate("deliverable-1", creator_profile_id=7, strategy_version="v1")
    assert service.generate("deliverable-1", creator_profile_id=7, strategy_version="v1") is first
    second = service.generate("deliverable-1", creator_profile_id=7, strategy_version="v2")
    assert second.strategy_version == "v2"
    assert len(calls) == 2 and len(repository.saved) == 2


def test_strategy_rejects_missing_shots_unknown_assets_and_incomplete_progression():
    photoshoots = Photoshoots()
    for mutation, message in (
        (lambda value: value.update(suggested_sales_progression=[20, 10]), "every approved"),
        (lambda value: value["shots"].pop(), "Every approved shot"),
        (lambda value: value.update(best_teaser_asset_id=999), "Best teaser"),
    ):
        value = strategy(); mutation(value)
        service = PhotoshootSessionSalesStrategyService(
            repository=Strategies(), photoshoots=photoshoots,
            strategy_runner=lambda _source, value=value: value,
        )
        with pytest.raises(ValueError, match=message):
            service.generate("deliverable-1", creator_profile_id=7)


def test_completion_stops_at_intelligence_and_sales_brain_reads_lazy_strategy():
    completion = inspect.getsource(PhotoshootCommerceDeliverableService.complete)
    assert "run_canonical_intelligence" in completion
    assert "session_sales_strategy.generate" not in completion
    progression = inspect.getsource(AutonomousSalesProgressionRepository.ordered_assets)
    assert "photoshoot_session_sales_strategies" in progression
    assert "sales_position" in progression
    assert "access_recommendation" in progression
    generator = inspect.getsource(PhotoshootSessionSalesStrategyService)
    assert "input_image" not in generator
    assert "persist_canonical_intelligence" not in generator


def test_strategy_migration_is_versioned_and_photoshoot_scoped():
    migration = open(
        "migrations/forward/20260804_037_photoshoot_session_sales_strategies.sql",
        encoding="utf-8",
    ).read()
    assert "PRIMARY KEY (photoshoot_session_id, strategy_version)" in migration
    assert "REFERENCES public.photoshoot_commerce_deliverables" in migration
    assert "strategy_data JSONB" in migration


def test_strategy_generation_requires_session_mode_and_creator_scope():
    photoshoots = Photoshoots()
    original = photoshoots.get
    photoshoots.get = lambda value: {**original(value), "selling_mode": "BUNDLE"}
    service = PhotoshootSessionSalesStrategyService(
        repository=Strategies(), photoshoots=photoshoots, strategy_runner=lambda _: strategy())
    with pytest.raises(ValueError, match="SESSION selling mode"):
        service.generate("deliverable-1", creator_profile_id=7)
    photoshoots.get = original
    with pytest.raises(KeyError, match="not found"):
        service.generate("deliverable-1", creator_profile_id=99)


def test_incomplete_commercial_contract_is_rejected_before_ai_generation():
    photoshoots = Photoshoots()
    canonical = photoshoots.get_intelligence("session-1")
    canonical["profile_data"] = {**canonical["profile_data"], "commercial_summary": None}
    photoshoots.get_intelligence = lambda _: canonical
    calls = []
    service = PhotoshootSessionSalesStrategyService(
        repository=Strategies(), photoshoots=photoshoots,
        strategy_runner=lambda value: calls.append(value) or strategy())
    with pytest.raises(ValueError, match="commercial_summary"):
        service.generate("deliverable-1", creator_profile_id=7)
    assert calls == []
