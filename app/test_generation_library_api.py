from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.api import generation_library as api
from app.services.generation_library_service import GenerationLibraryService
from app.models.generation_library import GeneratedImageRecord, GenerationLibraryFilter, GenerationLibraryResult
from uuid import uuid4


def test_add_to_teasers_returns_canonical_asset_and_analysis_state(monkeypatch):
    service = Mock()
    service.add.return_value = SimpleNamespace(
        asset_id=42, generation_id="image-1", already_registered=False,
        analysis_status="NUDENET_PENDING",
    )
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "EngagementTeaserIntakeService", lambda: service)
    result = api.add_generation_to_teasers("image-1")
    service.add.assert_called_once_with("image-1", creator_profile_id=7)
    assert result["asset_id"] == 42
    assert result["status"] == "analyzing"
    assert result["generation_id"] == "image-1"


def _record(image_id: str, *, status: str = "active"):
    return SimpleNamespace(
        image_id=image_id,
        creator_profile_id=7,
        status=status,
        review_state=status,
        updated_at="2026-01-01T00:00:00",
        created_at="2026-01-01T00:00:00",
        generation_date="2026-01-01T00:00:00",
        generation_metadata={},
    )


def test_assembled_photoshoot_import_returns_durable_operation(monkeypatch):
    operation_id, intake_id = uuid4(), uuid4()
    operation = SimpleNamespace(operation_id=operation_id, status="QUEUED")
    service = Mock()
    service.create.return_value = ({
        "intake_id": intake_id, "deliverable_id": None,
    }, operation, True)
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "_current_account_id", lambda: 3)
    monkeypatch.setattr(api, "AssembledPhotoshootIntakeService", lambda: service)

    result = api.import_generation_library_photoshoot(api.AssembledPhotoshootImportRequest(
        imageIds=["image-b", "image-a"],
        heroImageId="image-a", idempotencyKey="request-1",
    ))

    service.create.assert_called_once_with(
        creator_profile_id=7, account_id=3,
        image_ids=["image-b", "image-a"], hero_image_id="image-a",
        idempotency_key="request-1",
    )
    assert result == {
        "intakeId": str(intake_id), "operationId": str(operation_id),
        "operationStatus": "QUEUED", "created": True, "deliverableId": None,
        "sourceKind": "GENERATION_LIBRARY_IMPORT",
    }


def test_edit_handoff_uses_generation_library_pending_workflow(monkeypatch):
    selected = _record("image-1")
    pending = _record("image-1", status="pending_edit")
    library = Mock()
    library.get.return_value = selected
    library.pending_edit_record.return_value = None
    library.list_records.return_value = (selected,)
    library.send_to_pending_edit.return_value = pending
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    result = api.send_generation_to_edit_studio("image-1")

    library.send_to_pending_edit.assert_called_once_with("image-1")
    assert result == {
        "success": True,
        "message": "Image opened in Edit Studio.",
        "image_id": "image-1",
        "status": "pending_edit",
        "review_state": "pending_edit",
        "source_image_url": "/api/v1/edit-studio/pending-source/image?image_id=image-1&v=2026-01-01T00:00:00",
        "context_refresh": True,
        "redirect": "/content/edit",
    }


def test_edit_handoff_replaces_previous_pending_image(monkeypatch):
    selected = _record("image-2")
    previous = _record("image-1", status="pending_edit")
    candidate = _record("candidate-1", status="edit_candidate")
    candidate.generation_metadata = {"edit_pending_source_image_id": "image-1"}
    chained_candidate = _record("candidate-2", status="edit_candidate")
    chained_candidate.generation_metadata = {"edit_pending_source_image_id": "image-1"}
    library = Mock()
    library.get.return_value = selected
    library.pending_edit_record.return_value = previous
    library.list_records.return_value = (previous, candidate, chained_candidate, selected)
    library.discard_edit_candidate.return_value = SimpleNamespace(success=True, errors=(), message="Discarded")
    library.return_pending_edit_to_library.return_value = SimpleNamespace(success=True, errors=(), message="Returned")
    library.send_to_pending_edit.return_value = _record("image-2", status="pending_edit")
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    result = api.send_generation_to_edit_studio("image-2")

    assert [call.args[0] for call in library.discard_edit_candidate.call_args_list] == [
        "candidate-1", "candidate-2",
    ]
    library.return_pending_edit_to_library.assert_called_once_with("image-1")
    library.send_to_pending_edit.assert_called_once_with("image-2")
    assert result["image_id"] == "image-2"
    assert result["status"] == "pending_edit"
    assert result["review_state"] == "pending_edit"


def test_pending_lookup_fails_with_deterministic_diagnostic_for_multiple_records(tmp_path, caplog):
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    first = _record("pending-a", status="pending_edit")
    second = _record("pending-b", status="pending_edit")
    first.output_reference = str(first_path)
    second.output_reference = str(second_path)
    first.updated_at = second.updated_at = "2026-01-01T00:00:00"
    service = GenerationLibraryService(storage_dir=tmp_path / "library")
    service.list_records = Mock(return_value=(first, second))

    with pytest.raises(RuntimeError, match="pending-b, pending-a"):
        service.pending_edit_record(creator_profile_id=7)

    assert "pending-b" in caplog.text
    assert "pending-a" in caplog.text


def test_generation_thumbnail_uses_cache_and_media_keeps_original(monkeypatch, tmp_path):
    source = tmp_path / "generation.png"
    source.write_bytes(b"original")
    thumbnail = tmp_path / "generation.webp"
    thumbnail.write_bytes(b"thumbnail")
    record = _record("image-1")
    record.output_reference = str(source)
    library = SimpleNamespace(projected_get=lambda _image_id: record)
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)
    monkeypatch.setattr(
        api,
        "GridThumbnailService",
        lambda: SimpleNamespace(
            get_or_create=lambda path, *, identity: thumbnail
        ),
    )

    response = api.generation_library_thumbnail("image-1")

    assert Path(response.path) == thumbnail
    assert response.media_type == "image/webp"
    assert response.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert Path(api.generation_library_media("image-1").path) == source


def test_generation_browse_uses_lightweight_thumbnail_card_projection(monkeypatch):
    record = GeneratedImageRecord(
        image_id="image-1", generation_job_id="job-1",
        generation_request_id="request-1", generation_result_id="result-1",
        output_reference="C:/original.png", creator_profile_id=7,
        provider_id="seedream", prompt_plan_id="plan-1",
        prompt_text="x" * 20_000, creative_mode="premium",
        reference_asset_id=93, generation_recipe_id=None,
        provider_metadata={"large": "x" * 20_000},
        prompt_metadata={"large": "x" * 20_000},
        generation_metadata={"large": "x" * 20_000},
        updated_at="2026-01-02T00:00:00Z",
    )
    library = Mock()
    library.browse_page.return_value = ((record,), 1, ("seedream",), ("premium",))
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    result = api.browse_generation_library(page=1)

    card = result["records"][0]
    assert card["image_url"].startswith("/api/v1/generation-library/image-1/thumbnail")
    assert card["media_url"].startswith("/api/v1/generation-library/image-1/media")
    assert "prompt_text" not in card
    assert "generation_metadata" not in card
    assert "prompt_metadata" not in card
    assert "provider_metadata" not in card


def test_generation_browse_passes_typed_content_origin_without_changing_sort(monkeypatch):
    library = Mock()
    library.browse_page.return_value = ((), 0, (), (), 1)
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    api.browse_generation_library(search="portrait", contentOrigin="NSFW", page=2)

    filters = library.browse_page.call_args.args[0]
    assert filters.search == "portrait"
    assert filters.content_origin == "NSFW"
    assert filters.sort == "newest"
    assert library.browse_page.call_args.kwargs == {"page": 2, "page_size": 24}

    api.browse_generation_library(contentOrigin="UNCLASSIFIED", page=1)
    assert library.browse_page.call_args.args[0].content_origin == "UNCLASSIFIED"


def test_generation_detail_preserves_full_prompt_metadata_and_original_url(monkeypatch):
    record = GeneratedImageRecord(
        image_id="image-1", generation_job_id="job-1",
        generation_request_id="request-1", generation_result_id="result-1",
        output_reference="C:/original.png", creator_profile_id=7,
        provider_id="seedream", prompt_plan_id="plan-1",
        prompt_text="Full canonical prompt", creative_mode="premium",
        reference_asset_id=93, generation_metadata={"model": "seedream-v5"},
    )
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: SimpleNamespace(get_with_effective_classification=lambda _: record))

    result = api.generation_library_details("image-1")

    assert result["prompt_text"] == "Full canonical prompt"
    assert result["generation_metadata"] == {"model": "seedream-v5"}
    assert "/media?" in result["image_url"]


def test_manual_classification_route_persists_only_for_owned_record(monkeypatch):
    record = _record("image-1")
    library = Mock()
    library.get.return_value = record
    library.classify_content.return_value = {
        "content_classification": "SFW", "classification_source": "MANUAL",
    }
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    result = api.classify_generation_content(
        "image-1", api.ContentClassificationRequest(classification="SFW"),
    )

    library.classify_content.assert_called_once_with(
        "image-1", creator_profile_id=7, classification="SFW",
    )
    assert result["content_classification"] == "SFW"
    assert result["classification_source"] == "MANUAL"


def test_manual_classification_route_rejects_resolved_record(monkeypatch):
    library = Mock()
    library.get.return_value = _record("image-1")
    library.classify_content.side_effect = ValueError(
        "Only an Unclassified Generation Library image can be manually classified."
    )
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    with pytest.raises(api.HTTPException) as raised:
        api.classify_generation_content(
            "image-1", api.ContentClassificationRequest(classification="NSFW"),
        )
    assert raised.value.status_code == 409


@pytest.mark.parametrize("classification", ["SFW", "NSFW"])
def test_bulk_classification_route_uses_one_atomic_service_call(monkeypatch, classification):
    library = Mock()
    library.bulk_classify_content.return_value = (
        {"image_id": "image-1", "content_classification": classification, "classification_source": "MANUAL"},
        {"image_id": "image-2", "content_classification": classification, "classification_source": "MANUAL"},
    )
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    result = api.bulk_classify_generation_content(api.BulkContentClassificationRequest(
        image_ids=["image-1", "image-2"], classification=classification,
    ))

    library.bulk_classify_content.assert_called_once_with(
        ["image-1", "image-2"], creator_profile_id=7, classification=classification,
    )
    assert result == {
        "image_ids": ["image-1", "image-2"], "content_classification": classification,
        "classification_source": "MANUAL", "classified_count": 2,
    }


def test_bulk_classification_rejects_whole_batch_on_service_conflict(monkeypatch):
    library = Mock()
    library.bulk_classify_content.side_effect = ValueError(
        "Every selected image must exist, belong to the active creator, and still be Unclassified."
    )
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)
    with pytest.raises(api.HTTPException) as raised:
        api.bulk_classify_generation_content(api.BulkContentClassificationRequest(
            image_ids=["valid", "automatic"], classification="SFW",
        ))
    assert raised.value.status_code == 409


def test_bulk_classification_request_rejects_empty_duplicate_and_invalid_values():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        api.BulkContentClassificationRequest(image_ids=[], classification="SFW")
    with pytest.raises(ValidationError):
        api.BulkContentClassificationRequest(image_ids=["same", "same"], classification="NSFW")
    with pytest.raises(ValidationError):
        api.BulkContentClassificationRequest(image_ids=["image-1"], classification="UNKNOWN")


def test_bulk_archive_uses_one_canonical_service_call(monkeypatch):
    library = Mock()
    library.bulk_archive_unclassified.return_value = SimpleNamespace(
        image_ids=("image-1", "image-2"), message="Content moved to Archive / Removed Content.",
    )
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)
    result = api.bulk_archive_generation_content(api.BulkArchiveRequest(
        image_ids=["image-1", "image-2"],
    ))
    library.bulk_archive_unclassified.assert_called_once_with(
        ["image-1", "image-2"], creator_profile_id=7,
    )
    assert result["archived_count"] == 2
    assert result["image_ids"] == ["image-1", "image-2"]


def test_bulk_archive_rejects_invalid_batch_atomically(monkeypatch):
    library = Mock()
    library.bulk_archive_unclassified.side_effect = ValueError(
        "Every selected image must belong to the active creator and still be an eligible Unclassified image."
    )
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)
    with pytest.raises(api.HTTPException) as raised:
        api.bulk_archive_generation_content(api.BulkArchiveRequest(
            image_ids=["unclassified", "automatic-sfw"],
        ))
    assert raised.value.status_code == 409


def test_bulk_archive_request_rejects_empty_duplicate_and_oversized_batches():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        api.BulkArchiveRequest(image_ids=[])
    with pytest.raises(ValidationError):
        api.BulkArchiveRequest(image_ids=["same", "same"])
    with pytest.raises(ValidationError):
        api.BulkArchiveRequest(image_ids=[f"image-{index}" for index in range(101)])


def test_bulk_archive_service_validates_every_record_before_canonical_archive(tmp_path):
    projection = Mock()
    projection.eligible_unclassified_ids.return_value = {"image-1", "image-2"}
    service = GenerationLibraryService(storage_dir=tmp_path, projection_repository=projection)
    service.ensure_read_projection = Mock()
    service.delete = Mock(return_value=SimpleNamespace(
        success=True, image_ids=("image-1", "image-2"), errors=(),
    ))
    result = service.bulk_archive_unclassified(
        ("image-1", "image-2"), creator_profile_id=7,
    )
    projection.eligible_unclassified_ids.assert_called_once_with(
        ("image-1", "image-2"), creator_profile_id=7,
    )
    service.delete.assert_called_once_with(("image-1", "image-2"))
    assert result.image_ids == ("image-1", "image-2")


def test_bulk_archive_service_archives_zero_when_one_record_is_ineligible(tmp_path):
    projection = Mock()
    projection.eligible_unclassified_ids.return_value = {"image-1"}
    service = GenerationLibraryService(storage_dir=tmp_path, projection_repository=projection)
    service.ensure_read_projection = Mock()
    service.delete = Mock()
    with pytest.raises(ValueError, match="eligible Unclassified"):
        service.bulk_archive_unclassified(
            ("image-1", "automatic-nsfw"), creator_profile_id=7,
        )
    service.delete.assert_not_called()


def test_posting_stage_route_uses_canonical_service_and_returns_metadata(monkeypatch):
    record = GeneratedImageRecord(
        image_id="image-1", generation_job_id="job-1", generation_request_id="request-1",
        generation_result_id="result-1", output_reference="C:/original.png",
        creator_profile_id=7, provider_id="seedream", prompt_plan_id="plan-1",
        prompt_text="Prompt", creative_mode="premium", reference_asset_id=93,
    )
    updated = record.__class__(**{**record.__dict__, "is_staged": True, "staged_at": "2026-08-15T10:00:00Z"})
    library = Mock()
    library.get.return_value = record
    library.set_posting_stage.return_value = updated
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    result = api.update_generation_posting_stage("image-1", api.PostingStageRequest(is_staged=True))

    library.set_posting_stage.assert_called_once_with("image-1", staged=True)
    assert result["is_staged"] is True
    assert result["staged_at"] == "2026-08-15T10:00:00Z"


def test_generation_library_edit_route_is_registered():
    from app.fanvue_callback_server import app

    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/generation-library/{generated_image_id}/edit"
    )
    assert route.methods == {"POST"}
    assert route.response_model.__name__ == "EditStudioHandoffResponse"


def test_photoshoot_handoff_replaces_previous_seed_and_starts_selected(monkeypatch):
    selected = _record("image-2")
    previous = _record("image-1", status="pending_photoshoot")
    previous_session = SimpleNamespace(session_id="session-1", status="running", creative_continuity={"seed_image_id": "image-1"})
    previous_request = SimpleNamespace(request_id="request-1", status="approved", metadata={"is_seed_image": True})
    new_session = SimpleNamespace(session_id="session-2")
    library = Mock()
    library.get.return_value = selected
    library.list_records.return_value = (previous, selected)
    library.return_photoshoot_seed_to_library.return_value = SimpleNamespace(success=True, errors=(), message="Returned")
    library.send_to_pending_photoshoot.return_value = _record("image-2", status="pending_photoshoot")
    queue = Mock()
    queue.list_sessions.return_value = (previous_session,)
    queue.requests_for_session.return_value = (previous_request,)
    queue.start_studio_session_from_generated_image.return_value = (new_session, True)
    canonical = SimpleNamespace(asset_id=55, asset=SimpleNamespace(original_path="C:/identity.png"))
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)
    monkeypatch.setattr(api, "PhotoshootQueueService", lambda: queue)
    monkeypatch.setattr(api, "ReferenceLibraryService", lambda: SimpleNamespace(
        get_active_canonical_reference=lambda **_: canonical,
    ))
    result = api.send_generation_to_photoshoot("image-2")
    queue.return_seed_request_to_library.assert_called_once()
    queue.cancel_session.assert_called_once_with("session-1")
    library.send_to_pending_photoshoot.assert_called_once_with("image-2")
    queue.start_studio_session_from_generated_image.assert_called_once_with(
        library.send_to_pending_photoshoot.return_value,
        canonical_identity_reference={"asset_id": 55, "path": "C:/identity.png"},
    )
    assert result["image_id"] == "image-2"
    assert result["redirect"] == "/content/photoshoot"


def test_generation_library_photoshoot_route_is_registered():
    from app.fanvue_callback_server import app
    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/v1/generation-library/{generated_image_id}/photoshoot")
    assert route.methods == {"POST"}
    assert route.response_model.__name__ == "PhotoshootHandoffResponse"


def test_move_to_asset_library_registers_and_starts_canonical_intelligence(monkeypatch):
    selected = _record("image-1")
    selected.imported_asset_id = None
    staged = _record("image-1", status="staged_asset_library")
    staged.imported_asset_id = None
    library = Mock()
    library.get.return_value = selected
    library.move_to_asset_library.return_value = (staged, False)
    registrar = Mock()
    registrar.register.return_value = SimpleNamespace(
        success=True, asset_id=51, already_registered=False,
        analysis_status="NUDENET_PENDING",
        message="Asset is registered. Intelligence analysis is in progress.",
    )
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)
    monkeypatch.setattr(api, "StagedAssetRegistrationService", lambda **kwargs: registrar)

    result = api.move_generation_to_asset_library("image-1")

    library.move_to_asset_library.assert_called_once_with("image-1")
    registrar.register.assert_called_once_with(staged, creator_profile_id=7)
    assert result["asset_id"] == 51
    assert result["analysis_status"] == "NUDENET_PENDING"
    assert result["status"] == "analyzing"


def test_move_repairs_already_registered_asset_without_restaging(monkeypatch):
    selected = _record("image-1", status="business_asset_registered")
    selected.imported_asset_id = 51
    library = Mock()
    library.get.return_value = selected
    registrar = Mock()
    registrar.register.return_value = SimpleNamespace(
        success=True, asset_id=51, already_registered=True,
        analysis_status="VISION_PENDING",
        message="Asset is registered. Intelligence analysis is in progress.",
    )
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)
    monkeypatch.setattr(api, "StagedAssetRegistrationService", lambda **kwargs: registrar)

    result = api.move_generation_to_asset_library("image-1")

    library.move_to_asset_library.assert_not_called()
    registrar.register.assert_called_once_with(selected, creator_profile_id=7)
    assert result["already_moved"] is True
    assert result["asset_id"] == 51


def test_move_surfaces_intelligence_dispatch_failure_for_retry(monkeypatch):
    selected = _record("image-1")
    selected.imported_asset_id = None
    staged = _record("image-1", status="staged_asset_library")
    staged.imported_asset_id = 51
    library = Mock()
    library.get.return_value = selected
    library.move_to_asset_library.return_value = (staged, False)
    registrar = Mock()
    registrar.register.side_effect = RuntimeError("provider dispatch unavailable")
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)
    monkeypatch.setattr(api, "StagedAssetRegistrationService", lambda **kwargs: registrar)

    with pytest.raises(api.HTTPException) as error:
        api.move_generation_to_asset_library("image-1")

    assert error.value.status_code == 409
    assert "Retry Move to Asset Library" in error.value.detail


def test_version_history_api_exposes_current_and_archived_versions(monkeypatch):
    current = _record("image-1")
    current.provider_id = "nano_banana_pro"
    current.prompt_text = "Current prompt"
    current.prompt_plan_id = "plan-2"
    current.output_reference = "D:/Ava_CMS/Content/Generation/Active/image-1.png"
    current.generation_metadata = {"asset_version": 2, "edit_approved_at": "2026-01-02", "approved_from": "edit_studio"}
    archived = SimpleNamespace(
        image_id="image-1",
        provider_id="seedream_5_0_pro",
        prompt_text="Original prompt",
        original_output_reference="D:/Ava_CMS/Content/Pending_Edit/image-1.png",
        current_file_path="D:/Ava_CMS/Content/Archive/Versions/image-1/Version_0001/image-1.png",
        metadata={
            "version_number": 1,
            "approval_timestamp": "2026-01-02",
            "prompt_plan_id": "plan-1",
            "generation_metadata": {"source": "premium_studio"},
            "edit_source": "edit_studio",
        },
    )
    library = Mock()
    library.get.return_value = current
    library.archive_service.list_asset_versions.return_value = (archived,)
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    result = api.generation_asset_versions("image-1")

    assert result["generation_library_record_id"] == "image-1"
    assert result["current_version"] == 2
    assert [item["version_number"] for item in result["versions"]] == [2, 1]
    assert result["versions"][0]["is_current"] is True
    assert result["versions"][1]["archived_file_path"].endswith("image-1.png")


def test_generation_library_version_route_is_registered():
    from app.fanvue_callback_server import app

    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/generation-library/{generated_image_id}/versions"
    )
    assert route.methods == {"GET"}
    assert route.response_model.__name__ == "AssetVersionHistoryResponse"


def test_generation_library_version_media_route_is_registered():
    from app.fanvue_callback_server import app

    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None)
        == "/api/v1/generation-library/{generated_image_id}/versions/{version_number}/media"
    )
    assert route.methods == {"GET"}


def test_version_media_uses_archived_record_without_mutation(monkeypatch, tmp_path):
    current = _record("image-1")
    media = tmp_path / "version-1.png"
    media.write_bytes(b"archived image")
    archived = SimpleNamespace(
        current_file_path=str(media),
        metadata={"version_number": 1},
    )
    library = Mock()
    library.get.return_value = current
    library.archive_service.list_asset_versions.return_value = (archived,)
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    result = api.generation_asset_version_media("image-1", 1)

    assert result.path == media
    assert result.headers["cache-control"] == "private, max-age=31536000, immutable"
    library.archive_service.list_asset_versions.assert_called_once_with("image-1")


def test_generation_library_version_restore_route_is_registered():
    from app.fanvue_callback_server import app

    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None)
        == "/api/v1/generation-library/{generated_image_id}/versions/{version_number}/restore"
    )
    assert route.methods == {"POST"}
    assert route.response_model.__name__ == "AssetVersionRestoreResponse"
