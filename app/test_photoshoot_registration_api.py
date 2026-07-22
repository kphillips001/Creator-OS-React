from app.api import asset_library as asset_api
from app.api import photoshoot_gallery as gallery_api
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService


def _row(state="PHOTOSHOOT_COMPLETE"):
    return {
        "deliverable_id": "set-1", "photoshoot_session_id": "session-1",
        "creator_profile_id": 7, "display_name": "Golden Hour Escape",
        "display_title": "Golden Hour Escape", "display_description": "A warm outdoor set.",
        "completed_at": "2026-07-21T00:00:00Z", "shot_count": 2,
        "hero_asset_id": 12, "intelligence_status": "READY",
        "registration_state": state, "is_active": True, "is_archived": False,
    }


class Repository:
    state = "PHOTOSHOOT_COMPLETE"
    asset_library_writes = 0
    registration_writes = 0

    def list_gallery(self, creator_id):
        assert creator_id == 7
        return (_row(self.state),)

    def get(self, deliverable_id):
        return _row(self.state) if deliverable_id == "set-1" else None

    def add_to_asset_library(self, _deliverable_id, _creator_id):
        self.asset_library_writes += 1
        self.state = "IN_ASSET_LIBRARY"
        return _row(self.state)

    def register(self, _deliverable_id, _creator_id):
        self.registration_writes += 1
        self.state = "REGISTERED"
        return _row(self.state)


def test_gallery_add_is_idempotent_and_does_not_register(monkeypatch):
    repository = Repository()
    service = PhotoshootCommerceDeliverableService(repository=repository)
    monkeypatch.setattr(gallery_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(gallery_api, "_repository", lambda: repository)
    monkeypatch.setattr(gallery_api, "_service", lambda: service)

    assert gallery_api.list_photoshoots()["items"][0]["registrationState"] == "PHOTOSHOOT_COMPLETE"
    assert gallery_api.add_photoshoot_to_asset_library("set-1")["registrationState"] == "IN_ASSET_LIBRARY"
    assert gallery_api.add_photoshoot_to_asset_library("set-1")["registrationState"] == "IN_ASSET_LIBRARY"
    assert repository.asset_library_writes == 1
    assert repository.registration_writes == 0


def test_asset_library_register_reuses_one_photoshoot_record():
    repository = Repository()
    repository.state = "IN_ASSET_LIBRARY"
    class Workflows:
        calls = 0
        def enqueue(self, _deliverable_id): self.calls += 1; return {"current_stage": "PENDING"}
    workflows = Workflows()
    service = PhotoshootCommerceDeliverableService(repository=repository, workflows=workflows)

    first = service.register("set-1", 7)
    second = service.register("set-1", 7)

    assert first["registration_state"] == second["registration_state"] == "REGISTERED"
    assert repository.registration_writes == 1
    assert workflows.calls == 2


def test_asset_library_projection_is_one_typed_photoshoot_entry():
    payload = asset_api._photoshoot_payload(_row("IN_ASSET_LIBRARY"))
    assert payload["itemKind"] == "photoshoot"
    assert payload["fileName"] == "Golden Hour Escape"
    assert payload["shotCount"] == 2
    assert payload["assetId"] is None
