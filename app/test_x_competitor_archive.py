from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import x_competitor_intelligence as api
from app.database import get_db_connection
from app.providers.x_twitterapi_io import ResolvedXProfile
from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
from app.services.x_competitor_audience_service import XCompetitorAudienceService
from app.services.x_competitor_intelligence_service import XCompetitorIntelligenceService


def test_archive_migration_is_nullable_and_recoverable():
    forward=Path("migrations/forward/20260818_068_x_competitor_archive.sql").read_text(encoding="utf-8")
    rollback=Path("migrations/rollback/20260818_068_x_competitor_archive.sql").read_text(encoding="utf-8")
    assert "archived_at TIMESTAMPTZ" in forward
    assert "WHERE archived_at IS NULL" in forward
    assert "DROP COLUMN IF EXISTS archived_at" in rollback


def test_archive_preserves_history_excludes_work_and_restore_reuses_same_record():
    repository=XCompetitorIntelligenceRepository();suffix=uuid4().hex[:8]
    competitor=repository.create_competitor(f"Archive_{suffix}",x_user_id=f"archive-{suffix}",platform="OTHER")
    now=datetime.now(timezone.utc)
    try:
        repository.update_manual_telegram_intelligence(competitor["id"],presence="YES",telegram_url="https://t.me/+privateToken",audience_type="MEMBERS",comments_allowed=True,joined=True,scraped=True)
        repository.insert_snapshot(competitor["id"],observed_at=now,followers_count=321)
        repository.upsert_post(competitor["id"],f"post-{suffix}",posted_at=now,text="preserved")
        archived=repository.archive(competitor["id"])
        assert archived and archived["archived_at"] is not None
        assert archived["platform"]=="OTHER"
        assert competitor["id"] not in {row["id"] for row in repository.dashboard()["items"]}
        assert competitor["id"] not in {row["id"] for row in repository.list_tracked_competitors()}
        assert competitor["id"] not in {row["id"] for row in repository.list_due_competitor_refreshes(due_before=now,retry_before=now,limit=500)}
        assert repository.claim_competitor_refresh(competitor["id"],sync_type="MANUAL",started_at=now) is None
        archived_row=next(row for row in repository.list_archived() if row["id"]==competitor["id"])
        assert archived_row["followers_count"]==321
        with get_db_connection() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT telegram_url,telegram_scraped FROM x_intelligence.competitors WHERE id=%s",(competitor["id"],));telegram=cursor.fetchone();assert telegram["telegram_url"]=="https://t.me/+privateToken" and telegram["telegram_scraped"] is True
            cursor.execute("SELECT COUNT(*) AS count FROM x_intelligence.competitor_profile_snapshots WHERE competitor_id=%s",(competitor["id"],));assert cursor.fetchone()["count"]==1
            cursor.execute("SELECT COUNT(*) AS count FROM x_intelligence.competitor_posts WHERE competitor_id=%s",(competitor["id"],));assert cursor.fetchone()["count"]==1
        restored=repository.restore(competitor["id"])
        assert restored and restored["id"]==competitor["id"] and restored["archived_at"] is None
        assert restored["platform"]=="OTHER"
        assert competitor["id"] in {row["id"] for row in repository.dashboard()["items"]}
        assert repository.get(competitor["id"])["telegram_url"]=="https://t.me/+privateToken"
        assert repository.get(competitor["id"])["telegram_scraped"] is True
    finally:
        with get_db_connection() as connection,connection.cursor() as cursor:
            cursor.execute("DELETE FROM x_intelligence.competitors WHERE id=%s",(competitor["id"],))


def test_archived_readd_returns_restore_candidate_without_collection():
    profile=ResolvedXProfile("immutable-1","new_name","New Name",None,None,None,None,None,False,None,50,1,1,1,1)
    class Provider:
        def get_user_by_username(self,username):return profile
    class Repository:
        def __init__(self):self.persisted=False;self.updated=False
        def get_by_x_user_id(self,x_user_id):return {"id":"same-record","x_user_id":x_user_id,"username":"old_name","archived_at":datetime.now(timezone.utc)}
        def update_archived_resolved_profile(self,competitor_id,value):self.updated=True;return {"id":competitor_id,"archived_at":datetime.now(timezone.utc)}
        def persist_resolved_profile(self,*args,**kwargs):self.persisted=True;raise AssertionError("must not create or refresh")
    repository=Repository();activity=type("Activity",(),{"refresh_competitor":lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError("must not collect"))})()
    result=XCompetitorIntelligenceService(provider=Provider(),repository=repository,activity_service=activity).import_competitors(["old_name"])[0]
    assert result=={"submittedUsername":"old_name","resolvedUsername":"new_name","status":"ARCHIVED","reason":"This competitor is archived. Restore them?","activityStatus":None,"competitorId":"same-record"}
    assert repository.updated is True and repository.persisted is False


def test_manual_audience_collection_rejects_archived_before_provider_work():
    class Repository:
        def get_competitor(self,competitor_id):return {"id":competitor_id,"archived_at":datetime.now(timezone.utc)}
    provider=type("Provider",(),{"get_audience_page":lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError("provider called"))})()
    with pytest.raises(ValueError,match="Archived competitors"):
        XCompetitorAudienceService(repository=Repository(),provider=provider).collect("archived")


def test_archive_restore_and_list_archived_endpoints_use_explicit_lifecycle(monkeypatch):
    archived_at=datetime(2026,8,18,17,tzinfo=timezone.utc);calls=[]
    class Service:
        def list_archived_competitors(self):return [{"id":"same","x_user_id":"42","username":"maya","display_name":"MAYA","profile_image_url":None,"platform":"FANVUE","followers_count":123,"archived_at":archived_at}]
        def archive_competitor(self,competitor_id):calls.append(("archive",competitor_id));return {"id":competitor_id,"archived_at":archived_at}
        def restore_competitor(self,competitor_id):calls.append(("restore",competitor_id));return {"id":competitor_id,"archived_at":None}
    monkeypatch.setattr(api,"_service",lambda:Service())
    application=FastAPI();application.include_router(api.router);client=TestClient(application)
    listed=client.get("/api/v1/x-intelligence/competitors/archived")
    assert listed.status_code==200 and listed.json()["items"][0]["archivedAt"]==archived_at.isoformat()
    assert client.post("/api/v1/x-intelligence/competitors/same/archive").status_code==200
    assert client.post("/api/v1/x-intelligence/competitors/same/restore").status_code==200
    assert calls==[("archive","same"),("restore","same")]
