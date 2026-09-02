from app.api.photoshoot_gallery import _payload


def test_photoshoot_gallery_card_uses_asset_thumbnail():
    value = _payload({
        "deliverable_id": "photoshoot-1",
        "photoshoot_session_id": "session-1",
        "display_title": "Gallery title",
        "display_name": "Fallback title",
        "display_description": None,
        "completed_at": "2026-01-01T00:00:00Z",
        "shot_count": 3,
        "hero_asset_id": 42,
        "intelligence_status": "READY",
        "registration_state": "PHOTOSHOOT_COMPLETE",
        "selling_mode": "SESSION",
    })

    assert value["imageUrl"] == "/api/v1/assets/42/thumbnail"
