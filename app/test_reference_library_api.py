from pathlib import Path
from types import SimpleNamespace

from app.api import reference_library as api


def _reference(path: Path):
    asset = SimpleNamespace(file_name="ava-reference.png", media_type="image", classification="REFERENCE", status="approved", preview_path=str(path), original_path=str(path))
    return SimpleNamespace(asset_id=84, asset=asset, is_active=True, is_favorite=True, added_at="2026-01-01T00:00:00", last_used_at="2026-07-18T00:00:00", creator_profile_id=2, metadata={"canonical": True, "protected": True})


def test_active_reference_returns_canonical_asset_and_creator(monkeypatch, tmp_path):
    image = tmp_path / "ava-reference.png"
    image.write_bytes(b"image")
    service = SimpleNamespace(get_active_reference=lambda **kwargs: _reference(image))
    monkeypatch.setattr(api, "_current_account_id", lambda: 1)
    monkeypatch.setattr(api, "get_active_creator_profile", lambda account_id: {"id": 2, "name": "Ava"})
    monkeypatch.setattr(api, "ReferenceLibraryService", lambda: service)

    result = api.active_reference()

    assert result["creator"] == {"id": 2, "name": "Ava"}
    assert result["active_reference"]["asset_id"] == 84
    assert result["active_reference"]["is_canonical"] is True
    assert result["active_reference"]["creator_profile_id"] == 2
    assert result["active_reference"]["image_url"].startswith("/api/v1/reference-library/active/image")
    response = api.active_reference_image()
    assert Path(response.path) == image
