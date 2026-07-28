from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import creator_world_model as api


class MemoryRepository:
    def __init__(self):
        self.documents = {}
        self.save_calls = []

    def get(self, *, creator_profile_id, fanvue_account_id):
        return self.documents.get((creator_profile_id, fanvue_account_id))

    def save(
        self, *, creator_profile_id, fanvue_account_id, document,
    ):
        self.save_calls.append(
            (creator_profile_id, fanvue_account_id, document)
        )
        key = (creator_profile_id, fanvue_account_id)
        saved = {
            "id": len(self.documents) + 1,
            "creator_profile_id": creator_profile_id,
            "fanvue_account_id": fanvue_account_id,
            **document,
            "created_at": "2026-07-27T14:00:00",
            "updated_at": "2026-07-27T14:00:00",
        }
        self.documents[key] = saved
        return saved


def _client():
    application = FastAPI()
    application.include_router(api.router)
    return TestClient(application)


def test_missing_world_model_loads_exact_starter_document(monkeypatch):
    repository = MemoryRepository()
    monkeypatch.setattr(api, "_account_id", lambda: 2)
    monkeypatch.setattr(
        api, "get_active_creator_profile",
        lambda account_id: {"id": 2, "fanvue_account_id": account_id},
    )
    monkeypatch.setattr(api, "_repository", lambda: repository)

    response = _client().get("/api/v1/creator/world-model")

    assert response.status_code == 200
    assert response.json()["id"] is None
    assert response.json()["internal_home_base"] == (
        api.DEFAULT_DOCUMENT["internal_home_base"]
    )
    assert response.json()["public_location_description"] == (
        api.DEFAULT_DOCUMENT["public_location_description"]
    )
    assert "bedroom" in response.json()["home_and_indoor_environments"]
    assert repository.documents == {}


def test_world_model_saves_and_reloads_for_active_account(monkeypatch):
    repository = MemoryRepository()
    monkeypatch.setattr(api, "_account_id", lambda: 2)
    monkeypatch.setattr(
        api, "get_active_creator_profile",
        lambda _: {"id": 2, "fanvue_account_id": "2"},
    )
    monkeypatch.setattr(api, "_repository", lambda: repository)
    payload = {
        **api.DEFAULT_DOCUMENT,
        "public_location_description": "Edited public description",
    }

    saved = _client().put("/api/v1/creator/world-model", json=payload)
    loaded = _client().get("/api/v1/creator/world-model")

    assert saved.status_code == 200
    assert loaded.json()["public_location_description"] == (
        "Edited public description"
    )
    assert repository.save_calls[0][:2] == (2, "2")


def test_amanda_and_ava_world_models_remain_independent(monkeypatch):
    repository = MemoryRepository()
    account = {"id": 2}
    profiles = {
        "2": {"id": 2, "fanvue_account_id": "2"},
        "3": {"id": 1, "fanvue_account_id": "3"},
    }
    monkeypatch.setattr(api, "_account_id", lambda: account["id"])
    monkeypatch.setattr(
        api, "get_active_creator_profile",
        lambda account_id: profiles[account_id],
    )
    monkeypatch.setattr(api, "_repository", lambda: repository)
    client = _client()

    client.put(
        "/api/v1/creator/world-model",
        json={**api.DEFAULT_DOCUMENT, "internal_home_base": "Ava private"},
    )
    account["id"] = 3
    client.put(
        "/api/v1/creator/world-model",
        json={**api.DEFAULT_DOCUMENT, "internal_home_base": "Amanda private"},
    )

    assert repository.documents[(2, "2")]["internal_home_base"] == "Ava private"
    assert repository.documents[(1, "3")]["internal_home_base"] == (
        "Amanda private"
    )
    assert len(repository.documents) == 2
