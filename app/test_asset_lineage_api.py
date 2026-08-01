from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import asset_lineage


class FakeAssets:
    def __init__(self, creator_profile_id=7):
        self.creator_profile_id = creator_profile_id

    def get_by_id(self, asset_id):
        return SimpleNamespace(
            id=asset_id, creator_profile_id=self.creator_profile_id,
            media_type="image",
        )


class FakeService:
    def __init__(self, creator_profile_id=7):
        self.assets = FakeAssets(creator_profile_id)

    def diagnostics(self, asset_id):
        return {
            "asset_id": asset_id, "classification": "ROOT",
            "ambiguous": False, "complete": True,
            "integrity_status": "VALID", "family_asset_ids": [asset_id],
        }


def client(monkeypatch, creator_profile_id=7, asset_creator_profile_id=7):
    monkeypatch.setattr(
        asset_lineage, "_creator_profile", lambda: {"id": creator_profile_id}
    )
    monkeypatch.setattr(
        asset_lineage, "_service", lambda: FakeService(asset_creator_profile_id)
    )
    app = FastAPI()
    app.include_router(asset_lineage.router)
    return TestClient(app)


def test_lineage_inspection_is_read_only_and_creator_scoped(monkeypatch):
    api = client(monkeypatch)
    response = api.get("/api/v1/asset-lineage/assets/101")
    assert response.status_code == 200
    assert response.json()["asset_id"] == 101
    methods = {
        method
        for route in asset_lineage.router.routes
        for method in route.methods
    }
    assert methods == {"GET"}


def test_lineage_inspection_hides_cross_creator_assets(monkeypatch):
    response = client(
        monkeypatch, creator_profile_id=7, asset_creator_profile_id=8
    ).get("/api/v1/asset-lineage/assets/101")
    assert response.status_code == 404
