from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.api import generation_library as api
from app.services.generation_library_service import GenerationLibraryService


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
    library = SimpleNamespace(get=lambda _image_id: record)
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
    assert Path(api.generation_library_media("image-1").path) == source


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
    monkeypatch.setattr(api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)
    monkeypatch.setattr(api, "PhotoshootQueueService", lambda: queue)
    result = api.send_generation_to_photoshoot("image-2")
    queue.return_seed_request_to_library.assert_called_once()
    queue.cancel_session.assert_called_once_with("session-1")
    library.send_to_pending_photoshoot.assert_called_once_with("image-2")
    assert result["image_id"] == "image-2"
    assert result["redirect"] == "/content/photoshoot"


def test_generation_library_photoshoot_route_is_registered():
    from app.fanvue_callback_server import app
    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/v1/generation-library/{generated_image_id}/photoshoot")
    assert route.methods == {"POST"}
    assert route.response_model.__name__ == "PhotoshootHandoffResponse"


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
