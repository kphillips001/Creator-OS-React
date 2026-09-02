import inspect

import pytest

from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.services.photoshoot_commercial_intelligence_service import (
    PhotoshootCommercialIntelligenceIncompleteError, PhotoshootCommercialIntelligenceService,
)
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService


def result():
    return {
        "commercial_title": "Quiet Unfolding", "subtitle": "An intimate progression",
        "commercial_summary": "An ordered indoor sequence follows a gradual intimate progression in black clothing.",
        "story": "A private moment unfolds chapter by chapter.", "theme": "intimate home portraiture",
        "experience": "close and gradual", "emotional_journey": "reserved to vulnerable",
        "buyer_profile": {"interest": "editorial intimacy"},
        "sales_strategy": {"positioning": "complete sequence"},
        "sales_brain_brief": "Sell the ordered emotional progression.",
    }


def test_complete_ordered_progression_reaches_production_shots_then_cross_validation():
    calls = []
    service = PhotoshootCommercialIntelligenceService(
        production_runner=lambda payload: calls.append(("production", payload)) or result(),
        shot_runner=lambda shot, production, neighbors: calls.append(("shot", shot, production, neighbors)) or {"sequence_role": f"shot-{shot['shot_order']}"},
        cross_runner=lambda production, shots: calls.append(("cross", shots)) or {"hero_asset_id": 1})
    profile = service.generate(
        chapters=({"asset_id": 2, "shot_order": 2, "approved_prompt": "second"},
                  {"asset_id": 1, "shot_order": 1, "approved_prompt": "first"}),
        approved_metadata={"setting": "inside a house"})
    assert [item["approved_prompt"] for item in calls[0][1]["ordered_chapters"]] == ["first", "second"]
    assert profile["commercial_title"] == "Quiet Unfolding"
    assert [call[0] for call in calls] == ["production", "shot", "shot", "cross"]
    assert calls[1][2]["story"] == result()["story"]
    assert [shot["shot_order"] for shot in profile["shot_intelligence"]] == [1, 2]


def test_empty_normalized_intelligence_never_calls_ai():
    calls = []
    service = PhotoshootCommercialIntelligenceService(
        production_runner=lambda payload: calls.append(payload) or result(),
        shot_runner=lambda *_: {}, cross_runner=lambda *_: {})
    with pytest.raises(ValueError, match="non-empty"):
        service.generate(chapters=({"shot_order": 1, "asset_id": 10},), approved_metadata={})
    assert calls == []


def test_gallery_projection_reads_only_canonical_commercial_copy():
    projection = PhotoshootCommerceRepository.DISPLAY_COLUMNS
    assert "i.commercial_title" in projection
    assert "i.commercial_summary" in projection
    assert "ai_title" not in projection
    assert "ai_description" not in projection


def test_no_standalone_naming_pipeline_is_referenced():
    source = inspect.getsource(PhotoshootCommerceDeliverableService)
    assert "PhotoshootNamingService" not in source
    assert "ensure_naming" not in source
    assert "set_ai_naming" not in source


def test_repository_upsert_is_one_record_per_photoshoot():
    source = inspect.getsource(PhotoshootCommerceRepository.persist_canonical_intelligence)
    source += inspect.getsource(PhotoshootCommerceRepository._persist_canonical_intelligence)
    assert "photoshoot_shot_intelligence_profiles" in source
    assert "ON CONFLICT (photoshoot_session_id,asset_id,intelligence_version) DO UPDATE" in source


def test_regeneration_updates_canonical_record_without_touching_legacy_naming_columns():
    source = inspect.getsource(PhotoshootCommerceDeliverableService.regenerate_commercial_intelligence)
    assert "run_canonical_intelligence" in source
    assert "force=True" in source
    assert "set_ai_naming" not in source


def test_failed_shot_prevents_cross_validation():
    cross = []
    service = PhotoshootCommercialIntelligenceService(
        production_runner=lambda _: result(),
        shot_runner=lambda shot, *_: (_ for _ in ()).throw(RuntimeError("bad shot")) if shot["asset_id"] == 2 else {"sequence_role": "opening"},
        cross_runner=lambda *_: cross.append(True) or {})
    with pytest.raises(Exception, match="SHOT_ANALYSIS_FAILED"):
        service.generate(chapters=({"asset_id": 1, "shot_order": 1, "prompt": "one"},
                                   {"asset_id": 2, "shot_order": 2, "prompt": "two"}),
                         approved_metadata={"plan": "progress"})
    assert cross == []


def test_large_photoshoot_is_sequential_and_bounded():
    active = peak = 0
    def shot_runner(*_):
        nonlocal active, peak
        active += 1; peak = max(peak, active); active -= 1
        return {"sequence_role": "middle"}
    service = PhotoshootCommercialIntelligenceService(
        production_runner=lambda _: result(), shot_runner=shot_runner,
        cross_runner=lambda *_: {"hero_asset_id": 1})
    service.generate(chapters=tuple({"asset_id": i, "shot_order": i, "prompt": str(i)} for i in range(1, 101)),
                     approved_metadata={"plan": "custom"})
    assert peak == 1


@pytest.mark.parametrize("field,value", [
    ("commercial_title", None), ("commercial_summary", None),
    ("buyer_profile", None), ("sales_strategy", None),
    ("sales_brain_brief", None), ("subtitle", "   "),
])
def test_incomplete_production_is_retried_and_reports_missing_field(field, value):
    calls = []
    incomplete = result() | {field: value}
    service = PhotoshootCommercialIntelligenceService(
        production_runner=lambda payload: calls.append(payload) or incomplete,
        shot_runner=lambda *_: {"sequence_role": "opening"},
        cross_runner=lambda *_: {"hero_asset_id": 1},
    )
    with pytest.raises(Exception) as raised:
        service.generate(chapters=({"asset_id": 1, "shot_order": 1, "prompt": "one"},),
                         approved_metadata={"plan": "test"})
    assert len(calls) == 3
    assert field in str(raised.value)
    assert "previous response was incomplete" in calls[1]["corrective_instruction"]


def test_retry_can_recover_to_ready_profile():
    calls = []
    service = PhotoshootCommercialIntelligenceService(
        production_runner=lambda payload: calls.append(payload) or (
            result() if len(calls) == 2 else result() | {"commercial_title": None}),
        shot_runner=lambda *_: {"sequence_role": "opening"},
        cross_runner=lambda *_: {"hero_asset_id": 1},
    )
    profile = service.generate(
        chapters=({"asset_id": 1, "shot_order": 1, "prompt": "one"},),
        approved_metadata={"plan": "test"},
    )
    assert len(calls) == 2
    assert profile["commercial_title"] == "Quiet Unfolding"
