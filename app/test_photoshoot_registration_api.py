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
        "gallery_path": "Gallery/session-1",
        "registration_state": state, "is_active": True, "is_archived": False,
    }


class Repository:
    state = "PHOTOSHOOT_COMPLETE"
    asset_library_writes = 0
    registration_writes = 0

    def list_gallery(self, creator_id):
        assert creator_id == 7
        return (_row(self.state),) if self.state == "PHOTOSHOOT_COMPLETE" else ()

    def get(self, deliverable_id):
        return _row(self.state) if deliverable_id == "set-1" else None

    def get_intelligence(self, session_id):
        assert session_id == "session-1"
        return {
            "intelligence_version": "completed_photoshoot_v2",
            "profile_data": {"production_analysis": {"production_summary": "A complete progression."}},
            "production_analysis": {"production_summary": "A complete progression.", "theme": "Intimacy"},
            "cross_validation": {"hero_asset_id": 12, "cover_asset_id": 13},
        }

    def shot_intelligence(self, session_id, version):
        assert (session_id, version) == ("session-1", "completed_photoshoot_v2")
        return ({"asset_id": 12, "profile_data": {"sequence_role": "opening", "wardrobe_state": "dressed"}},
                {"asset_id": 13, "profile_data": {"sequence_role": "closing", "wardrobe_state": "undressed"}})

    def latest_shot_intelligence(self, session_id):
        assert session_id == "session-1"
        return ()

    def intelligence_members(self, session_id):
        assert session_id == "session-1"
        return ({"asset_id": 12, "shot_order": 1, "is_hero": True, "content_profile": {}},
                {"asset_id": 13, "shot_order": 2, "is_hero": False, "content_profile": {}})

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
    assert gallery_api.list_photoshoots()["items"] == []
    assert gallery_api.add_photoshoot_to_asset_library("set-1")["registrationState"] == "IN_ASSET_LIBRARY"
    assert repository.asset_library_writes == 1
    assert repository.registration_writes == 0


def test_gallery_repository_selects_only_unregistered_completed_photoshoots():
    import inspect
    from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
    source = inspect.getsource(PhotoshootCommerceRepository.list_gallery)
    assert "d.registration_state='PHOTOSHOOT_COMPLETE'" in source
    assert "registration_state<>'ARCHIVED'" not in source


def test_gallery_details_reads_persisted_production_and_shot_intelligence(monkeypatch):
    repository = Repository()
    monkeypatch.setattr(gallery_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(gallery_api, "_repository", lambda: repository)
    monkeypatch.setattr(gallery_api, "_teaser_repository", lambda: type("Teasers", (), {"get": lambda self, _id: None})())

    result = gallery_api.photoshoot_details("set-1")

    assert result["productionIntelligence"]["production_summary"] == "A complete progression."
    assert result["productionIntelligence"]["hero_shot"] == 12
    assert result["members"][0]["intelligence"]["sequence_role"] == "opening"
    assert result["members"][1]["intelligence"]["wardrobe_state"] == "undressed"


def test_gallery_details_resolves_legacy_persisted_asset_intelligence_by_asset_id(monkeypatch):
    repository = Repository()
    repository.shot_intelligence = lambda *_: ()
    repository.latest_shot_intelligence = lambda *_: ()
    repository.intelligence_members = lambda *_: (
        {"asset_id": 12, "shot_order": 1, "is_hero": True,
         "content_profile": {"summary": "Persisted opening analysis"}, "normalized_context": {}},
        {"asset_id": 13, "shot_order": 2, "is_hero": False,
         "content_profile": {"summary": "Persisted closing analysis"}, "normalized_context": {}},
    )
    monkeypatch.setattr(gallery_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(gallery_api, "_repository", lambda: repository)
    monkeypatch.setattr(gallery_api, "_teaser_repository", lambda: type("Teasers", (), {"get": lambda self, _id: None})())

    result = gallery_api.photoshoot_details("set-1")

    assert [member["assetId"] for member in result["members"]] == [12, 13]
    assert result["members"][0]["intelligence"]["summary"] == "Persisted opening analysis"


def test_gallery_details_projects_promotional_teaser_as_supporting_commercial_asset(monkeypatch):
    repository = Repository()
    monkeypatch.setattr(gallery_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(gallery_api, "_repository", lambda: repository)
    monkeypatch.setattr(gallery_api, "_teaser_repository", lambda: type("Teasers", (), {
        "get": lambda self, deliverable_id: {
            "deliverable_id": deliverable_id, "source_asset_id": 12,
            "teaser_asset_id": 145, "commercial_role": "BUNDLE_PROMOTIONAL_TEASER",
        }
    })())

    result = gallery_api.photoshoot_details("set-1")

    assert [member["assetId"] for member in result["members"]] == [12, 13]
    assert result["commercialAssets"] == [{
        "assetId": 145, "kind": "PROMOTIONAL_TEASER",
        "label": "Promotional Teaser", "status": "READY",
        "previewUrl": "/api/v1/assets/145/media",
    }]


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
