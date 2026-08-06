from types import SimpleNamespace

import pytest

from tools.backfill_legacy_photoshoot_intelligence import (
    BackfillPrerequisiteError, LegacyPhotoshootIntelligenceBackfill,
)


class Photoshoots:
    def __init__(self):
        self.deliverable = {"deliverable_id": "deliverable-1", "photoshoot_session_id": "session-1",
                            "creator_profile_id": 7, "display_name": "Legacy", "display_title": "Legacy",
                            "ordered_member_asset_ids": [10, 20]}
        self.intelligence = {"status": "READY", "pipeline_stage": "PENDING",
                             "commercial_title": "Legacy", "profile_data": {"commercial_title": "Legacy"},
                             "production_analysis": {}, "cross_validation": {}, "analysis_completed_at": None}
        self.members_value = ({"asset_id": 10, "shot_order": 1, "approved": True},
                              {"asset_id": 20, "shot_order": 2, "approved": True})
        self.shots = ()
    def get(self, value): return self.deliverable if value == "deliverable-1" else None
    def get_by_session(self, value): return self.deliverable if value == "session-1" else None
    def members(self, _): return self.members_value
    def get_intelligence(self, _): return self.intelligence
    def latest_shot_intelligence(self, _): return self.shots
    def shot_intelligence(self, *_): return self.shots


class Strategies:
    def __init__(self): self.value = None
    def latest(self, _): return self.value


class Pipeline:
    def __init__(self, photoshoots):
        self.photoshoots = photoshoots; self.calls = []
        self.queue = SimpleNamespace(get_session=lambda _: SimpleNamespace(creator_profile_id=7))
    def run_canonical_intelligence(self, session, **kwargs):
        self.calls.append(kwargs)
        self.photoshoots.intelligence.update({
            "status": "READY", "pipeline_stage": "COMPLETE", "intelligence_version": "completed_photoshoot_v2",
            "production_analysis": {"theme": "home"}, "cross_validation": {"valid": True},
            "analysis_completed_at": "now",
        })
        self.photoshoots.shots = (
            {"asset_id": 10, "shot_order": 1, "status": "READY"},
            {"asset_id": 20, "shot_order": 2, "status": "READY"},
        )


class StrategyService:
    def __init__(self, strategies): self.strategies = strategies; self.calls = 0
    def generate(self, *_args, **_kwargs):
        self.calls += 1
        self.strategies.value = SimpleNamespace(status="READY", strategy_version="photoshoot_session_sales_v1")
        return self.strategies.value


class Audit:
    def protected_snapshot(self, *_): return {"unchanged": True}


def build():
    photoshoots = Photoshoots(); strategies = Strategies(); pipeline = Pipeline(photoshoots)
    strategy = StrategyService(strategies)
    sale = SimpleNamespace(inspect=lambda *_args, **_kwargs: {"steps": [{}, {}]})
    utility = LegacyPhotoshootIntelligenceBackfill(
        photoshoots=photoshoots, strategies=strategies, pipeline=pipeline,
        strategy_service=strategy, sale_preparation=sale, audit=Audit(),
    )
    return utility, photoshoots, strategies, pipeline, strategy


def test_backfill_runs_canonical_pipeline_then_strategy_and_is_idempotent():
    utility, photoshoots, _, pipeline, strategy = build()
    first = utility.run(deliverable_id="deliverable-1")
    assert first["production_intelligence"] == "GENERATED"
    assert first["shot_intelligence"] == "GENERATED (2)"
    assert first["prepare_for_sale"] == "READY"
    assert pipeline.calls == [{"intelligence_version": "completed_photoshoot_v2", "force": True,
                               "preserve_commercial_intelligence": True}]
    assert strategy.calls == 1
    assert photoshoots.intelligence["commercial_title"] == "Legacy"
    second = utility.run(session_id="session-1")
    assert second["status"] == "SKIPPED" and second["generated"] is False
    assert len(pipeline.calls) == 1 and strategy.calls == 1


def test_backfill_rejects_invalid_membership_order_before_generation():
    utility, photoshoots, _, pipeline, _ = build()
    photoshoots.members_value = ({"asset_id": 10, "shot_order": 2, "approved": True},)
    with pytest.raises(BackfillPrerequisiteError, match="ordering is invalid"):
        utility.run(deliverable_id="deliverable-1")
    assert pipeline.calls == []


def test_backfill_rejects_any_existing_canonical_intelligence_without_work():
    utility, photoshoots, _, pipeline, strategy = build()
    photoshoots.intelligence["production_analysis"] = {"already": True}
    result = utility.run(deliverable_id="deliverable-1")
    assert result["status"] == "SKIPPED"
    assert pipeline.calls == [] and strategy.calls == 0
