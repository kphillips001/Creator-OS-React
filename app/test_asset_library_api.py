from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import asset_library as asset_api
from app.api import generation_library as generation_api
from app.models.asset_library import (
    AssetLibraryDetails,
    AssetLibraryItem,
    AssetLibraryResult,
    AssetPublishingSummary,
    AssetRelationshipSummary,
    AssetStorageSummary,
)
from app.services.asset_registration_service import AssetRegistrationResult


def _record(**changes):
    values = {
        "image_id": "generated-1",
        "creator_profile_id": 7,
        "status": "active",
        "imported_asset_id": None,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _item(asset_id=42, original_path="C:/vault/portrait.png"):
    return AssetLibraryItem(
        asset_id=asset_id,
        file_name="portrait.png",
        media_type="image",
        classification="premium",
        status="approved",
        is_active=True,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        preview_path=None,
        original_path=original_path,
        tags=("portrait",),
        themes=("studio",),
        ready_for_rotation=True,
        relationship=AssetRelationshipSummary(),
        publishing=AssetPublishingSummary(status="unpublished"),
    )


def _registration_setup(monkeypatch, record, result):
    library = SimpleNamespace(get=lambda _image_id: record)
    monkeypatch.setattr(generation_api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(generation_api, "GenerationLibraryService", lambda: library)
    monkeypatch.setattr(
        generation_api,
        "ReferenceLibraryService",
        lambda: SimpleNamespace(get_active_reference=lambda **_kwargs: None),
    )
    service = SimpleNamespace(register_generated_image=lambda *_args, **_kwargs: result)
    monkeypatch.setattr(generation_api, "AssetRegistrationService", lambda **_kwargs: service)


def test_register_generation_asset_uses_existing_registration_service(monkeypatch):
    _registration_setup(
        monkeypatch,
        _record(),
        AssetRegistrationResult(success=True, asset_id=42, message="Asset registered."),
    )
    result = generation_api.register_generation_asset("generated-1")
    assert result == {
        "success": True,
        "asset_id": 42,
        "generation_id": "generated-1",
        "already_registered": False,
        "status": "registered",
        "message": "Asset registered.",
    }


def test_register_generation_asset_reports_existing_asset(monkeypatch):
    _registration_setup(
        monkeypatch,
        _record(imported_asset_id=42),
        AssetRegistrationResult(success=True, asset_id=42, already_registered=True, message="Already registered."),
    )
    assert generation_api.register_generation_asset("generated-1")["already_registered"] is True


@pytest.mark.parametrize("status", ["removed", "pending_edit"])
def test_register_generation_asset_rejects_unavailable_records(monkeypatch, status):
    _registration_setup(monkeypatch, _record(status=status), AssetRegistrationResult(success=True, asset_id=42))
    with pytest.raises(HTTPException) as error:
        generation_api.register_generation_asset("generated-1")
    assert error.value.status_code == 409


def test_register_generation_asset_returns_missing_and_missing_media_errors(monkeypatch):
    monkeypatch.setattr(generation_api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(
        generation_api,
        "GenerationLibraryService",
        lambda: SimpleNamespace(get=lambda _image_id: (_ for _ in ()).throw(KeyError("missing"))),
    )
    with pytest.raises(HTTPException) as missing:
        generation_api.register_generation_asset("missing")
    assert missing.value.status_code == 404

    _registration_setup(
        monkeypatch,
        _record(),
        AssetRegistrationResult(success=False, message="Generated image file is missing."),
    )
    with pytest.raises(HTTPException) as unavailable:
        generation_api.register_generation_asset("generated-1")
    assert unavailable.value.status_code == 409
    assert "missing" in unavailable.value.detail


def test_register_generation_asset_preserves_canonical_reference(monkeypatch):
    record = _record(imported_asset_id=93)
    library = SimpleNamespace(get=lambda _image_id: record)
    monkeypatch.setattr(generation_api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(generation_api, "GenerationLibraryService", lambda: library)
    monkeypatch.setattr(
        generation_api,
        "ReferenceLibraryService",
        lambda: SimpleNamespace(get_active_reference=lambda **_kwargs: SimpleNamespace(asset_id=93, metadata={"canonical": True})),
    )
    monkeypatch.setattr(
        generation_api,
        "AssetRegistrationService",
        lambda **_kwargs: pytest.fail("canonical reference must not be re-registered"),
    )
    result = generation_api.register_generation_asset("generated-1")
    assert result["status"] == "protected"
    assert result["asset_id"] == 93


def test_list_assets_applies_filters_and_pagination(monkeypatch):
    items = tuple(_item(asset_id=index) for index in range(1, 22))
    captured = {}
    service = SimpleNamespace(search_assets=lambda filters: captured.setdefault("result", AssetLibraryResult(items, filters, len(items))))
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_canonical_asset_id", lambda _profile_id: 2)
    monkeypatch.setattr(asset_api, "AssetLibraryService", lambda: service)

    result = asset_api.list_assets(search="face", media_type="image", classification="premium", page=2, page_size=10)
    assert [item["assetId"] for item in result["assets"]] == list(range(11, 21))
    assert result["totalPages"] == 3
    assert result["assets"][0]["isCanonicalReference"] is False
    filters = captured["result"].filters
    assert (filters.search, filters.media_type, filters.classification, filters.creator_profile_id) == ("face", "image", "premium", 7)


def test_asset_details_and_media_are_creator_scoped(monkeypatch, tmp_path: Path):
    media = tmp_path / "portrait.png"
    media.write_bytes(b"png")
    details = AssetLibraryDetails(
        item=_item(original_path=str(media)),
        creator_profile_id=7,
        storage=AssetStorageSummary(original_path=str(media), original_exists=True),
        media_metadata={"asset_registration": {"source": "generation_library"}},
    )
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_canonical_asset_id", lambda _profile_id: None)
    monkeypatch.setattr(asset_api, "AssetLibraryService", lambda: SimpleNamespace(get_asset_details=lambda _asset_id: details))

    payload = asset_api.asset_details(42)
    assert payload["registrationSource"] == "generation_library"
    assert payload["mediaAvailable"] is True
    assert Path(asset_api.asset_media(42).path) == media


def test_asset_media_reports_missing_file(monkeypatch):
    details = AssetLibraryDetails(
        item=_item(original_path=None),
        creator_profile_id=7,
        storage=AssetStorageSummary(original_path=None, original_exists=False),
    )
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "AssetLibraryService", lambda: SimpleNamespace(get_asset_details=lambda _asset_id: details))
    with pytest.raises(HTTPException) as error:
        asset_api.asset_media(42)
    assert error.value.status_code == 404
