from pathlib import Path
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import x_competitor_intelligence as api
from app.database import get_db_connection
from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
from app.services.x_competitor_manual_intelligence_service import XCompetitorManualIntelligenceService


class FakeRepository:
    def __init__(self, row=None):
        self.row=row;self.calls=[]

    def update_manual_telegram_intelligence(self, competitor_id, **values):
        self.calls.append((competitor_id,values))
        if self.row is None:return None
        return {**self.row,"telegram_presence":values["presence"],"telegram_url":values["telegram_url"],"telegram_audience_type":values["audience_type"],"telegram_comments_allowed":values["comments_allowed"],"telegram_joined":values["joined"],"telegram_scraped":values.get("scraped") if values.get("scraped") is not None else self.row.get("telegram_scraped",False)}


def test_migration_defines_nullable_operator_owned_fields_and_constrained_audience_type():
    forward=Path("migrations/forward/20260817_064_x_competitor_manual_telegram_intelligence.sql").read_text(encoding="utf-8")
    rollback=Path("migrations/rollback/20260817_064_x_competitor_manual_telegram_intelligence.sql").read_text(encoding="utf-8")
    assert "telegram_audience_type TEXT" in forward
    assert "telegram_comments_allowed BOOLEAN" in forward
    assert "telegram_joined BOOLEAN" in forward
    assert "IN ('SUBSCRIBERS', 'MEMBERS')" in forward
    assert "DROP COLUMN IF EXISTS telegram_audience_type" in rollback


def test_presence_migration_is_tri_state_and_backfills_only_meaningful_metadata():
    forward=Path("migrations/forward/20260817_065_x_competitor_telegram_presence.sql").read_text(encoding="utf-8")
    rollback=Path("migrations/rollback/20260817_065_x_competitor_telegram_presence.sql").read_text(encoding="utf-8")
    assert "DEFAULT 'UNKNOWN'" in forward
    assert "IN ('UNKNOWN','YES','NO')" in forward
    assert "SET telegram_presence='YES'" in forward
    assert "telegram_audience_type IS NOT NULL" in forward
    assert "DROP COLUMN IF EXISTS telegram_presence" in rollback


def test_telegram_url_migration_adds_one_nullable_canonical_field():
    forward=Path("migrations/forward/20260818_067_x_competitor_telegram_url.sql").read_text(encoding="utf-8")
    rollback=Path("migrations/rollback/20260818_067_x_competitor_telegram_url.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS telegram_url TEXT" in forward
    assert "DROP COLUMN IF EXISTS telegram_url" in rollback


def test_scraped_migration_adds_a_non_nullable_false_boolean_and_is_reversible():
    forward=Path("migrations/forward/20260820_073_x_competitor_telegram_scraped.sql").read_text(encoding="utf-8")
    rollback=Path("migrations/rollback/20260820_073_x_competitor_telegram_scraped.sql").read_text(encoding="utf-8")
    assert "telegram_scraped BOOLEAN NOT NULL DEFAULT FALSE" in forward
    assert "DROP COLUMN IF EXISTS telegram_scraped" in rollback


def test_service_persists_manual_fields_and_rejects_unknown_audience_type_without_provider_calls():
    repository=FakeRepository({"id":"c1"});service=XCompetitorManualIntelligenceService(repository=repository)
    row=service.update_telegram("c1",presence="YES",telegram_url=" https://t.me/+8pzjrgbAegIxMDA0 ",audience_type="MEMBERS",comments_allowed=True,joined=None,scraped=True)
    assert (row["telegram_audience_type"],row["telegram_comments_allowed"],row["telegram_joined"])==("MEMBERS",True,None)
    assert row["telegram_url"]=="https://t.me/+8pzjrgbAegIxMDA0"
    assert row["telegram_scraped"] is True
    assert repository.calls==[("c1",{"presence":"YES","telegram_url":"https://t.me/+8pzjrgbAegIxMDA0","audience_type":"MEMBERS","comments_allowed":True,"joined":None,"scraped":True})]
    with pytest.raises(ValueError):service.update_telegram("c1",presence="YES",audience_type="GROUP",comments_allowed=None,joined=None)
    assert len(repository.calls)==1
    for invalid in ("http://t.me/channel", "https://example.com/channel", "https://t.me/"):
        with pytest.raises(ValueError):service.update_telegram("c1",presence="YES",telegram_url=invalid,audience_type=None,comments_allowed=None,joined=None)
    assert len(repository.calls)==1


def test_endpoint_accepts_canonical_values_rejects_invalid_values_and_returns_not_found(monkeypatch):
    calls=[]
    class Service:
        AUDIENCE_TYPES={"SUBSCRIBERS","MEMBERS"}
        PRESENCE_VALUES={"UNKNOWN","YES","NO"}
        def update_telegram(self,competitor_id,**values):
            calls.append((competitor_id,values))
            if competitor_id=="missing":raise LookupError("Competitor not found.")
            return {"telegram_presence":values["presence"],"telegram_url":values["telegram_url"],"telegram_audience_type":values["audience_type"],"telegram_comments_allowed":values["comments_allowed"],"telegram_joined":values["joined"],"telegram_scraped":values.get("scraped",False)}
    monkeypatch.setattr(api,"XCompetitorManualIntelligenceService",Service)
    application=FastAPI();application.include_router(api.router);client=TestClient(application)
    response=client.patch("/api/v1/x-intelligence/competitors/c1/telegram-intelligence",json={"presence":"YES","telegramUrl":"https://t.me/channelname","audienceType":"SUBSCRIBERS","commentsAllowed":False,"joined":True,"scraped":True})
    assert response.status_code==200 and response.json()=={"presence":"YES","telegramUrl":"https://t.me/channelname","audienceType":"SUBSCRIBERS","commentsAllowed":False,"joined":True,"scraped":True}
    assert calls==[("c1",{"presence":"YES","telegram_url":"https://t.me/channelname","audience_type":"SUBSCRIBERS","comments_allowed":False,"joined":True,"scraped":True})]
    assert client.patch("/api/v1/x-intelligence/competitors/c1/telegram-intelligence",json={"audienceType":"INVALID"}).status_code==422
    assert client.patch("/api/v1/x-intelligence/competitors/missing/telegram-intelligence",json={"presence":"UNKNOWN","audienceType":None}).status_code==404


def test_postgres_update_survives_fresh_repository_read_and_dashboard_projection():
    repository=XCompetitorIntelligenceRepository();suffix=uuid4().hex[:8];created=repository.create_competitor(f"Telegram_{suffix}",x_user_id=f"telegram-{suffix}")
    try:
        saved=XCompetitorManualIntelligenceService(repository=repository).update_telegram(str(created["id"]),presence="YES",telegram_url="https://t.me/+8pzjrgbAegIxMDA0",audience_type="MEMBERS",comments_allowed=True,joined=True,scraped=True)
        assert (saved["telegram_presence"],saved["telegram_url"],saved["telegram_audience_type"],saved["telegram_comments_allowed"],saved["telegram_joined"])==("YES","https://t.me/+8pzjrgbAegIxMDA0","MEMBERS",True,True)
        assert saved["telegram_scraped"] is True
        fresh=XCompetitorIntelligenceRepository();row=fresh.get(created["id"])
        assert (row["telegram_presence"],row["telegram_url"],row["telegram_audience_type"],row["telegram_comments_allowed"],row["telegram_joined"])==("YES","https://t.me/+8pzjrgbAegIxMDA0","MEMBERS",True,True)
        assert row["telegram_scraped"] is True
        projected=next(item for item in fresh.dashboard()["items"] if item["id"]==created["id"])
        assert (projected["telegram_presence"],projected["telegram_url"],projected["telegram_audience_type"],projected["telegram_comments_allowed"],projected["telegram_joined"])==("YES","https://t.me/+8pzjrgbAegIxMDA0","MEMBERS",True,True)
        assert projected["telegram_scraped"] is True
        preserved=XCompetitorManualIntelligenceService(repository=fresh).update_telegram(str(created["id"]),presence="NO",telegram_url=row["telegram_url"],audience_type="MEMBERS",comments_allowed=True,joined=True)
        assert preserved["telegram_url"]=="https://t.me/+8pzjrgbAegIxMDA0"
        assert preserved["telegram_scraped"] is True
    finally:
        with get_db_connection() as connection,connection.cursor() as cursor:cursor.execute("DELETE FROM x_intelligence.competitors WHERE id=%s",(created["id"],))
