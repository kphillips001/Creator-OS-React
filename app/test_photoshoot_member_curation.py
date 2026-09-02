from app.services.photoshoot_member_curation_service import PhotoshootMemberCurationService
from app.api import photoshoot_gallery as api


def member(asset_id, order, *, hero=False, status="COMPLETE"):
    return {"asset_id": asset_id, "shot_order": order, "is_hero": hero,
            "file_path": f"/media/{asset_id}.png", "media_metadata": {"source": "generation"},
            "content_profile": {"summary": f"Asset {asset_id}"},
            "normalized_context": {"setting": "studio"},
            "content_intelligence_status": status}


class Repository:
    def __init__(self, *, protected=False, members=None):
        self.protected = protected
        self.rows = list(members or [member(10, 1, hero=True), member(11, 2), member(12, 3), member(13, 4)])
        self.applied = None
        self.standalone = False

    def get(self, deliverable_id):
        return {"deliverable_id": deliverable_id, "creator_profile_id": 7,
                "photoshoot_session_id": "session-1", "display_name": "Set",
                "hero_asset_id": 10, "source_kind": "GENERATION_LIBRARY_IMPORT",
                "registration_state": "IN_ASSET_LIBRARY", "is_archived": False}

    def members(self, session_id): return tuple(self.rows)
    def intelligence_members(self, session_id): return tuple(self.rows)
    def member_curation_blockers(self, deliverable_id, creator_profile_id):
        return {"offering_count": 1 if self.protected else 0, "publication_count": 0,
                "purchase_count": 0, "teaser_count": 0, "lifecycle_count": 0}
    def extracted_assets_are_standalone(self, asset_ids, creator_profile_id): return self.standalone
    def apply_member_extraction(self, **values):
        self.applied = values
        selected = set(values["asset_ids"])
        remaining = tuple(row["asset_id"] for row in self.rows if row["asset_id"] not in selected)
        hero = 10 if 10 in remaining else remaining[0]
        return {"deliverable": {**self.get(values["deliverable_id"]), "hero_asset_id": hero},
                "remaining_asset_ids": remaining, "hero_asset_id": hero}


class Deliverables:
    def __init__(self): self.calls = []
    def build_source_neutral_intelligence(self, **values):
        self.calls.append(values)
        return {"status": "READY", "shot_intelligence": [
            {"asset_id": item["asset_id"], "shot_order": item["shot_order"]}
            for item in values["chapters"]]}


def test_curation_reuses_assets_and_content_intelligence_and_reconciles_hero_order():
    repository, deliverables = Repository(), Deliverables()
    service = PhotoshootMemberCurationService(repository=repository, deliverables=deliverables)

    result = service.move_to_images("set-1", creator_profile_id=7, asset_ids=[10, 12])

    assert result["movedAssetIds"] == [10, 12]
    assert result["remainingAssetIds"] == [11, 13]
    assert result["heroAssetId"] == 11
    assert result["sourceKind"] == "GENERATION_LIBRARY_IMPORT"
    assert repository.applied["asset_ids"] == (10, 12)
    assert [chapter["asset_id"] for chapter in deliverables.calls[0]["chapters"]] == [11, 13]
    assert [chapter["shot_order"] for chapter in deliverables.calls[0]["chapters"]] == [1, 2]
    assert deliverables.calls[0]["chapters"][0]["canonical_content_intelligence"] == {"summary": "Asset 11"}


def test_curation_enforces_minimum_and_commercial_mutability_before_rebuild():
    repository, deliverables = Repository(), Deliverables()
    service = PhotoshootMemberCurationService(repository=repository, deliverables=deliverables)
    try:
        service.move_to_images("set-1", creator_profile_id=7, asset_ids=[10, 11, 12])
        assert False, "minimum-member guard should reject"
    except ValueError as error:
        assert "at least 2" in str(error)
    assert deliverables.calls == []

    protected, protected_deliverables = Repository(protected=True), Deliverables()
    protected_service = PhotoshootMemberCurationService(
        repository=protected, deliverables=protected_deliverables)
    try:
        protected_service.move_to_images("set-1", creator_profile_id=7, asset_ids=[12])
        assert False, "commercial guard should reject"
    except ValueError as error:
        assert "commercial activity" in str(error)
    assert protected_deliverables.calls == []


def test_curation_waits_for_complete_content_intelligence_and_is_idempotent():
    repository = Repository(members=[member(10, 1, hero=True), member(11, 2),
                                     member(12, 3, status="RUNNING")])
    deliverables = Deliverables()
    service = PhotoshootMemberCurationService(repository=repository, deliverables=deliverables)
    try:
        service.move_to_images("set-1", creator_profile_id=7, asset_ids=[11])
        assert False, "incomplete Content Intelligence should reject"
    except ValueError as error:
        assert "complete Content Intelligence" in str(error)
    assert deliverables.calls == []

    repository.rows = [member(10, 1, hero=True), member(12, 2)]
    repository.standalone = True
    repeated = service.move_to_images("set-1", creator_profile_id=7, asset_ids=[11])
    assert repeated["alreadyMoved"] is True
    assert deliverables.calls == []
    assert repository.applied is None


def test_both_imported_and_studio_photoshoots_share_the_unprepared_contract():
    repository = Repository()
    service = PhotoshootMemberCurationService(repository=repository, deliverables=Deliverables())
    assert service.inspect("set-1", creator_profile_id=7)["eligible"] is True
    original_get = repository.get
    repository.get = lambda deliverable_id: {**original_get(deliverable_id), "source_kind": "PHOTOSHOOT_STUDIO"}
    assert service.inspect("set-1", creator_profile_id=7)["eligible"] is True


def test_api_delegates_member_mutation_to_canonical_service(monkeypatch):
    class Service:
        def move_to_images(self, deliverable_id, *, creator_profile_id, asset_ids):
            assert (deliverable_id, creator_profile_id, asset_ids) == ("set-1", 7, [10, 12])
            return {"deliverableId": "set-1", "movedAssetIds": [10, 12],
                    "movedCount": 2, "remainingAssetIds": [11, 13], "shotCount": 2,
                    "heroAssetId": 11, "sourceKind": "GENERATION_LIBRARY_IMPORT",
                    "alreadyMoved": False}
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(api, "PhotoshootMemberCurationService", Service)
    result = api.move_photoshoot_members_to_images(
        "set-1", api.MovePhotoshootMembersRequest(assetIds=[10, 12]))
    assert result["movedCount"] == 2
    assert result["remainingAssetIds"] == [11, 13]


def test_photoshoot_disposition_migration_backfills_only_current_members():
    from pathlib import Path
    sql = Path("migrations/forward/20260815_058_generation_photoshoot_dispositions.sql").read_text()
    assert "generation_image_dispositions" in sql
    assert "photoshoot_asset_memberships" in sql
    assert "membership.approved=TRUE" in sql
    assert "intake.status='SUCCEEDED'" in sql
    repository_source = Path("app/repositories/photoshoot_commerce_repository.py").read_text()
    assert "DELETE FROM public.generation_image_dispositions" in repository_source
    assert "disposition.owner='PHOTOSHOOT'" in repository_source
