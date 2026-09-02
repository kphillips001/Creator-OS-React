from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import ig_competitor_intelligence as api
from app.fanvue_callback_server import app


class FakeRepository:
    rows = []

    def list(self, creator_profile_id, *, archived=False):
        return [row for row in self.rows if row["creator_profile_id"] == creator_profile_id and bool(row["archived_at"]) == archived]

    def get_by_username(self, creator_profile_id, username):
        return next((row for row in self.rows if row["creator_profile_id"] == creator_profile_id and row["username"] == username), None)

    def create(self, creator_profile_id, *, username, followers_count):
        now = datetime.now(timezone.utc)
        row = {"id": uuid4(), "creator_profile_id": creator_profile_id, "username": username, "display_name": None, "followers_count": followers_count, "profile_image_url": None, "archived_at": None, "created_at": now, "updated_at": now}
        self.rows.append(row)
        return row

    def update_followers(self, creator_profile_id, competitor_id, followers_count):
        row = next((row for row in self.rows if str(row["id"]) == competitor_id and not row["archived_at"]), None)
        if row:
            row["followers_count"] = followers_count
        return row

    def archive(self, creator_profile_id, competitor_id):
        row = next((row for row in self.rows if str(row["id"]) == competitor_id), None)
        if row:
            row["archived_at"] = datetime.now(timezone.utc)
        return row

    def restore(self, creator_profile_id, competitor_id):
        row = next((row for row in self.rows if str(row["id"]) == competitor_id), None)
        if row:
            row["archived_at"] = None
        return row


@pytest.fixture(autouse=True)
def isolated_api(monkeypatch):
    FakeRepository.rows = []
    monkeypatch.setattr(api, "IgCompetitorIntelligenceRepository", FakeRepository)
    monkeypatch.setattr(api, "_context", lambda: (7, None))


def test_router_is_registered_and_isolated_from_x():
    paths = {route.path for route in app.routes}
    assert "/api/v1/ig-intelligence/competitors" in paths
    assert "/api/v1/x-intelligence/competitors" in paths


def test_create_normalizes_username_and_prevents_duplicates():
    created = api.create_competitor(api.CompetitorCreate(username=" @Creator.Name ", followers=1234))
    assert created["username"] == "creator.name"
    assert "displayName" not in created
    assert created["followers"] == 1234
    with pytest.raises(HTTPException) as error:
        api.create_competitor(api.CompetitorCreate(username="CREATOR.NAME", followers=1))
    assert error.value.status_code == 409


def test_followers_archive_and_restore_lifecycle():
    created = api.create_competitor(api.CompetitorCreate(username="ava", followers=10))
    updated = api.update_followers(created["id"], api.FollowersPatch(followers=25))
    assert updated["followers"] == 25
    api.archive_competitor(created["id"])
    assert api.list_competitors()["items"] == []
    assert [item["id"] for item in api.list_competitors(archived=True)["items"]] == [created["id"]]
    api.restore_competitor(created["id"])
    assert [item["id"] for item in api.list_competitors()["items"]] == [created["id"]]


def test_validation_rejects_invalid_manual_values():
    with pytest.raises(HTTPException) as error:
        api.create_competitor(api.CompetitorCreate(username="bad handle", followers=0))
    assert error.value.status_code == 422
    with pytest.raises(ValueError):
        api.FollowersPatch(followers=-1)
