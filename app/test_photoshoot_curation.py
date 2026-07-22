from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.models.generation_library import GenerationLibraryActionResult
from app.services.photoshoot_curation_service import PhotoshootCurationService


def fixture(existing=None):
    requests = (
        SimpleNamespace(status="approved", sequence_index=1, imported_asset_ids=(90,), metadata={"is_seed_image": True, "generated_image_ids": ("seed",)}),
        SimpleNamespace(status="approved", sequence_index=2, imported_asset_ids=(91,), metadata={"generated_image_ids": ("image-1",), "creative_direction": {"title": "One", "creative_direction": "First"}}),
        SimpleNamespace(status="approved", sequence_index=3, imported_asset_ids=(92,), metadata={"generated_image_ids": ("image-2",), "creative_direction": {"title": "Two", "creative_direction": "Second"}}),
    )
    continuity = {"session_plan": ({"title": "One"}, {"title": "Two"})}
    if existing: continuity["curation"] = existing
    session = SimpleNamespace(session_id="session-1", creator_profile_id=2, title="Shoot", status="running", reference_asset_id=90, creative_continuity=continuity)
    records = {
        "seed": SimpleNamespace(image_id="seed", imported_asset_id=None, prompt_text="Canonical portrait", output_reference="C:/gallery/seed.png"),
        "image-1": SimpleNamespace(image_id="image-1", imported_asset_id=91, prompt_text="First", output_reference="C:/gallery/one.png"),
        "image-2": SimpleNamespace(image_id="image-2", imported_asset_id=92, prompt_text="Second", output_reference="C:/gallery/two.png"),
    }
    queue = Mock()
    queue.get_session.return_value = session
    queue.requests_for_session.return_value = requests
    queue.archive_curated_session.side_effect = lambda _, curation: SimpleNamespace(**{**session.__dict__, "status": "archived", "creative_continuity": {**continuity, "curation": curation}})
    library = Mock()
    library.get.side_effect = lambda image_id: records[image_id]
    library.list_records.return_value = tuple(records.values())
    library.finish_photoshoot_session.return_value = GenerationLibraryActionResult(True, "done", ("image-1", "image-2"))
    library.approve_creator_content.return_value = GenerationLibraryActionResult(
        True, "seed approved", ("seed",), imported_asset_ids=(90,))
    library.stage_photoshoot_image_in_asset_library.side_effect = lambda image_id: (records[image_id], False)
    deliverables = Mock()
    auto = Mock()
    return PhotoshootCurationService(queue=queue, library=library, deliverables=deliverables, auto_run=auto), queue, library, deliverables


def test_review_displays_seed_first_and_preserves_generated_order_and_descriptions():
    service, *_ = fixture()
    review = service.review(creator_profile_id=2, session_id="session-1")
    assert review["seed_image"]["image_id"] == "seed"
    assert review["seed_image"]["asset_id"] is None
    assert review["seed_image"]["title"] == "Seed Image"
    assert review["seed_image"]["is_seed"] is True
    assert [(shot["image_id"], shot["shot_number"], shot["title"], shot["description"]) for shot in review["shots"]] == [
        ("image-1", 1, "One", "First"), ("image-2", 2, "Two", "Second")]


@pytest.mark.parametrize("selected,staged", [(["image-2"], 1), ([], 0)])
def test_declined_session_optionally_stages_images_and_creates_no_photoshoot(selected, staged):
    service, queue, library, deliverables = fixture()
    result = service.confirm(creator_profile_id=2, session_id="session-1", selected_image_ids=selected, photoshoot_decision="DECLINED")
    assert result["status"] == "archived"
    assert library.stage_photoshoot_image_in_asset_library.call_count == staged
    deliverables.repository.replace_members.assert_not_called()
    queue.archive_curated_session.assert_called_once()


def test_repeated_confirmation_returns_persisted_result_without_duplicate_writes():
    existing = {"mode": "BOTH", "selected_image_ids": ["image-1"], "photoshoot_created": True,
                "photoshoot_deliverable_id": "set-1", "image_asset_generation_ids": ["image-1"]}
    service, queue, library, deliverables = fixture(existing)
    result = service.confirm(creator_profile_id=2, session_id="session-1", selected_image_ids=["image-2"], photoshoot_decision="DECLINED")
    assert result["already_confirmed"] is True
    assert result["photoshoot_decision"] == "APPROVED"
    queue.reconcile_curation.assert_called_once()
    library.finish_photoshoot_session.assert_not_called()
    queue.archive_curated_session.assert_not_called()
    deliverables.repository.replace_members.assert_not_called()


@pytest.mark.parametrize("mode,decision", [
    ("PHOTOSHOOT", "APPROVED"), ("BOTH", "APPROVED"),
    ("IMAGES", "DECLINED"), ("ARCHIVE_ONLY", "DECLINED"),
])
def test_legacy_modes_reconcile_idempotently(mode, decision):
    existing = {"mode": mode, "selected_image_ids": [], "photoshoot_created": decision == "APPROVED"}
    service, queue, *_ = fixture(existing)
    review = service.review(creator_profile_id=2, session_id="session-1")
    assert review["photoshoot_decision"] == decision
    assert review["curation"]["photoshoot_decided_at"]
    assert "mode" not in review["curation"]
    queue.reconcile_curation.assert_called_once()


def test_approved_photoshoot_includes_seed_and_creates_no_standalone_images():
    service, queue, library, deliverables = fixture()
    row = {"deliverable_id": "set-1", "registration_state": "PHOTOSHOOT_COMPLETE"}
    deliverables.repository.upsert_deliverable.return_value = row
    deliverables.repository.add_to_asset_library.return_value = {**row, "registration_state": "IN_ASSET_LIBRARY"}
    deliverables.repository.get.return_value = {**row, "registration_state": "IN_ASSET_LIBRARY"}
    deliverables.naming.generate.return_value = ("AI Shoot", "AI Description")
    deliverables._completed_at.return_value = "now"
    result = service.confirm(creator_profile_id=2, session_id="session-1",
                             selected_image_ids=["image-2", "image-1"], photoshoot_decision="APPROVED")
    assert result["photoshoot_created"] is True
    assert result["photoshoot_decision"] == "APPROVED"
    library.approve_creator_content.assert_called_once()
    library.stage_photoshoot_image_in_asset_library.assert_not_called()
    deliverables.repository.replace_members.assert_called_once_with("session-1", ((90, 1), (92, 2), (91, 3)), 90)
    deliverables.repository.add_to_asset_library.assert_called_once_with("set-1", 2)
    deliverables.workflows.enqueue.assert_not_called()
