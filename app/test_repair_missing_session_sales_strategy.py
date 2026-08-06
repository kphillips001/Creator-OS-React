from types import SimpleNamespace

import pytest

from app.models.photoshoot_session_sales_strategy import SessionShotSalesRecommendation
from app.services.photoshoot_sale_preparation_service import PhotoshootSalePreparationService
from tools.repair_missing_session_sales_strategy import (
    MissingSessionSalesStrategyRepair, RepairPrerequisiteError,
)


def strategy():
    return SimpleNamespace(
        strategy_version="photoshoot_session_sales_v1", status="READY",
        creator_profile_id=7,
        shots=(
            SessionShotSalesRecommendation(10, 1, 1, "FREE_TEASER", True, "FREE", "open", 11, "introduce", "tease", "curiosity", "engage"),
            SessionShotSalesRecommendation(11, 2, 2, "FIRST_UNLOCK", False, "PAID", "unlock", None, "convert", "unlock", "value", "purchase"),
        ),
    )


class Photoshoots:
    def __init__(self, *, complete=True):
        self.complete = complete
        self.deliverable = {
            "deliverable_id": "deliverable-1", "photoshoot_session_id": "session-1",
            "creator_profile_id": 7, "display_title": "Legacy Photoshoot",
            "registration_state": "IN_ASSET_LIBRARY",
        }
    def get(self, value): return self.deliverable if value == "deliverable-1" else None
    def get_by_session(self, value): return self.deliverable if value == "session-1" else None
    def get_intelligence(self, _):
        return {"status": "READY", "intelligence_version": "intelligence-v1",
                "production_analysis": {"summary": "complete"},
                "cross_validation": {"consistent": True}}
    def members(self, _): return ({"asset_id": 10, "shot_order": 1}, {"asset_id": 11, "shot_order": 2})
    def shot_intelligence(self, *_):
        if not self.complete: return ({"asset_id": 10, "status": "READY", "profile_data": {"role": "teaser"}},)
        return ({"asset_id": 10, "status": "READY", "profile_data": {"role": "teaser"}},
                {"asset_id": 11, "status": "READY", "profile_data": {"role": "unlock"}})


class Strategies:
    def __init__(self, existing=None): self.existing = existing; self.rows = 1 if existing else 0
    def latest(self, _): return self.existing


class Generator:
    def __init__(self, strategies): self.strategies = strategies; self.calls = 0
    def generate(self, *_args, **_kwargs):
        self.calls += 1
        self.strategies.existing = strategy(); self.strategies.rows += 1
        return self.strategies.existing


def repair(*, photoshoots=None, existing=None):
    strategies = Strategies(existing)
    generator = Generator(strategies)
    utility = MissingSessionSalesStrategyRepair(
        photoshoots=photoshoots or Photoshoots(), strategies=strategies,
        strategy_service=generator,
    )
    return utility, strategies, generator


def test_generates_exactly_one_strategy_and_second_run_is_a_no_op():
    photoshoots = Photoshoots()
    utility, strategies, generator = repair(photoshoots=photoshoots)
    first = utility.run(deliverable_id="deliverable-1")
    second = utility.run(session_id="session-1")
    assert first["session_strategy"] == "GENERATED"
    assert first["status"] == "READY"
    assert first["strategy_version"] == "photoshoot_session_sales_v1"
    assert second["session_strategy"] == "ALREADY READY — NO WORK"
    assert generator.calls == 1
    assert strategies.rows == 1
    readiness = PhotoshootSalePreparationService(
        photoshoots=photoshoots, strategies=strategies,
        assets=SimpleNamespace(get_by_id=lambda asset_id: SimpleNamespace(file_path=__file__)),
        offerings=SimpleNamespace(get_by_idempotency_key=lambda **_: None),
        publications=SimpleNamespace(), uploads=SimpleNamespace(),
        offering_service=SimpleNamespace(), publication_service=SimpleNamespace(),
        executor=SimpleNamespace(),
    ).inspect("deliverable-1", creator_profile_id=7)
    assert readiness["status"] == "NOT_PREPARED"
    assert [item["assetId"] for item in readiness["steps"]] == [10, 11]


def test_existing_ready_strategy_exits_before_prerequisite_or_generation_reads():
    utility, strategies, generator = repair(photoshoots=Photoshoots(complete=False), existing=strategy())
    result = utility.run(deliverable_id="deliverable-1")
    assert result["generated"] is False
    assert generator.calls == 0 and strategies.rows == 1


def test_incomplete_shot_intelligence_stops_without_partial_generation():
    utility, strategies, generator = repair(photoshoots=Photoshoots(complete=False))
    with pytest.raises(RepairPrerequisiteError, match="Shot Intelligence: INCOMPLETE"):
        utility.run(deliverable_id="deliverable-1")
    assert generator.calls == 0 and strategies.rows == 0


@pytest.mark.parametrize("missing,message", [
    ("production", "Production Intelligence: MISSING"),
    ("cross_validation", "Cross-validation: MISSING"),
    ("members", "Approved Photoshoot Assets: MISSING"),
])
def test_each_canonical_prerequisite_is_checked_before_generation(missing, message):
    photoshoots = Photoshoots()
    original_intelligence = photoshoots.get_intelligence
    if missing == "production":
        photoshoots.get_intelligence = lambda value: {**original_intelligence(value), "production_analysis": {}}
    elif missing == "cross_validation":
        photoshoots.get_intelligence = lambda value: {**original_intelligence(value), "cross_validation": {}}
    else:
        photoshoots.members = lambda _: ()
    utility, strategies, generator = repair(photoshoots=photoshoots)
    with pytest.raises(RepairPrerequisiteError, match=message):
        utility.run(deliverable_id="deliverable-1")
    assert generator.calls == 0 and strategies.rows == 0


def test_missing_photoshoot_and_ambiguous_identifier_stop_cleanly():
    utility, strategies, generator = repair()
    with pytest.raises(RepairPrerequisiteError, match="exactly one"):
        utility.run(deliverable_id="deliverable-1", session_id="session-1")
    with pytest.raises(RepairPrerequisiteError, match="NOT FOUND"):
        utility.run(deliverable_id="unknown")
    assert generator.calls == 0 and strategies.rows == 0
