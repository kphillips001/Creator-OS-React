from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import x_competitor_intelligence as api
from app.providers.x_twitterapi_io import ResolvedXProfile, TwitterApiIoError, TwitterApiIoNotFound, TwitterApiIoProvider
from app.services.x_competitor_intelligence_service import XCompetitorIntelligenceService


def profile(user_id="42", username="AshleyReed", followers=123):
    return ResolvedXProfile(user_id,username,"Ashley Reed","https://img",None,"bio",None,None,True,"Blue",followers,5,8,2,1)


def test_provider_uses_backend_credential_and_normalizes_profile_without_exposing_key():
    response=Mock();response.status_code=200;response.raise_for_status.return_value=None;response.json.return_value={"status":"success","data":{"id":"42","userName":"AshleyReed","name":"Ashley Reed","profilePicture":"https://img","followers":123,"following":5,"statusesCount":8,"mediaCount":2,"favouritesCount":1,"isBlueVerified":True}}
    session=Mock(spec=requests.Session);session.headers={};session.get.return_value=response
    provider=TwitterApiIoProvider("test-secret",session=session);resolved=provider.get_user_by_username("AshleyReed")
    assert resolved.x_user_id=="42" and resolved.followers_count==123 and resolved.statuses_count==8
    assert session.headers["X-API-Key"]=="test-secret"
    assert session.get.call_args.kwargs["params"]=={"userName":"AshleyReed"}
    assert "/twitter/user/info" in session.get.call_args.args[0]


class FakeProvider:
    def get_user_by_username(self,username):
        if username=="missing": raise TwitterApiIoNotFound("@missing was not found.")
        if username=="broken": raise TwitterApiIoError("secret provider detail")
        return profile("same-id" if username in {"oldname","newname"} else username,username)


class FakeRepository:
    def __init__(self): self.ids=set();self.calls=[];self.platforms=[]
    def persist_resolved_profile(self,value,*,observed_at,platform="FANVUE"):
        existed=value.x_user_id in self.ids;self.ids.add(value.x_user_id);self.calls.append(value);self.platforms.append(platform);return {"id":value.x_user_id,"x_user_id":value.x_user_id,"username":value.username,"platform":platform},existed

    def classify_own_account(self,competitor_id):
        return {"id":competitor_id,"x_user_id":competitor_id,"username":"avablackthorne","account_role":"OWN_ACCOUNT"}


class FakeActivityService:
    def __init__(self,failed=()): self.failed=set(failed);self.calls=[]
    def refresh_competitor(self,competitor,*,sync_type):
        self.calls.append((competitor["id"],sync_type));status="FAILED" if competitor["username"] in self.failed else "REFRESHED"
        return {"competitorId":competitor["id"],"username":competitor["username"],"status":status,"reason":None}


def test_bulk_import_is_partial_success_safe_and_deduplicates_canonically_by_x_id():
    repository=FakeRepository();activity=FakeActivityService(failed={"oldname"});service=XCompetitorIntelligenceService(provider=FakeProvider(),repository=repository,activity_service=activity)
    results=service.import_competitors(["AshleyReed","missing","broken","oldname","newname"])
    assert [item["status"] for item in results]==["ADDED","NOT_FOUND","FAILED","ADDED","ALREADY_TRACKED"]
    assert results[2]["reason"]=="Profile lookup failed. Try again later."
    assert results[0]["activityStatus"]=="REFRESHED"
    assert results[3]["activityStatus"]=="FAILED" and results[3]["reason"]=="Activity needs refresh."
    assert results[4]["activityStatus"] is None
    assert activity.calls==[("AshleyReed","INITIAL"),("same-id","INITIAL")]
    assert repository.calls[-1].username=="newname"


def test_import_applies_one_operator_platform_to_the_entire_submission():
    repository=FakeRepository()
    results=XCompetitorIntelligenceService(
        provider=FakeProvider(),repository=repository,
        activity_service=FakeActivityService(),
    ).import_competitors(["AshleyReed","newaccount"],platform="ONLYFANS")
    assert [item["status"] for item in results]==["ADDED","ADDED"]
    assert repository.platforms==["ONLYFANS","ONLYFANS"]


def test_benchmark_registration_reuses_profile_and_activity_intelligence_path():
    repository=FakeRepository();activity=FakeActivityService()
    result=XCompetitorIntelligenceService(provider=FakeProvider(),repository=repository,activity_service=activity).register_own_account()
    assert result["account"]["account_role"]=="OWN_ACCOUNT"
    assert activity.calls==[("avablackthorne","INITIAL")]


def test_unexpected_activity_failure_does_not_roll_back_added_competitor():
    activity=Mock();activity.refresh_competitor.side_effect=RuntimeError("activity persistence failed")
    results=XCompetitorIntelligenceService(provider=FakeProvider(),repository=FakeRepository(),activity_service=activity).import_competitors(["newaccount"])
    assert results[0]["status"]=="ADDED" and results[0]["activityStatus"]=="FAILED"
    assert results[0]["reason"]=="Activity needs refresh."


def test_import_endpoint_validates_and_returns_partial_results(monkeypatch):
    service=SimpleNamespace(import_competitors=lambda names,platform="FANVUE":[{"submittedUsername":name,"resolvedUsername":None,"status":"NOT_FOUND","reason":"Not found.","platform":platform} for name in names])
    monkeypatch.setattr(api,"_service",lambda:service)
    application=FastAPI();application.include_router(api.router);client=TestClient(application)
    response=client.post("/api/v1/x-intelligence/competitors/import",json={"usernames":["AshleyReed","ashleyreed","missing"]})
    assert response.status_code==200
    assert [item["submittedUsername"] for item in response.json()["results"]]==["AshleyReed","missing"]
    assert client.post("/api/v1/x-intelligence/competitors/import",json={"usernames":[]}).status_code==422
    assert client.post("/api/v1/x-intelligence/competitors/import",json={"usernames":[f"user{i}" for i in range(51)]}).status_code==422
    assert client.post("/api/v1/x-intelligence/competitors/import",json={"usernames":["not valid!"]}).status_code==422


def test_competitor_projection_exposes_canonical_creation_timestamp(monkeypatch):
    from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
    created_at=datetime(2026,8,16,12,30,tzinfo=timezone.utc)
    monkeypatch.setattr(XCompetitorIntelligenceRepository,"dashboard",lambda self:{"items":[{
        "id":"competitor-1","x_user_id":"42","username":"AshleyReed","display_name":"Ashley Reed",
        "profile_image_url":None,"tracking_enabled":True,"telegram_presence":"UNKNOWN","telegram_audience_type":None,"telegram_comments_allowed":None,"telegram_joined":None,"followers_count":123,
        "created_at":created_at,"observed_at":created_at,"last_active_at":None,"posts_7d":None,
        "comments_7d":12,"retweets_7d":8,"quotes_7d":3,
    }],"tracked":1,"total_followers":123})
    application=FastAPI();application.include_router(api.router);client=TestClient(application)
    response=client.get("/api/v1/x-intelligence/competitors")
    assert response.status_code==200
    assert response.json()["items"][0]["createdAt"]==created_at.isoformat()
    assert response.json()["items"][0]["comments7d"]==12
    assert response.json()["items"][0]["retweets7d"]==8
    assert response.json()["items"][0]["quotes7d"]==3
    assert response.json()["items"][0]["refresh"]=={"lastSuccessfulAt":None,"nextRefreshAt":None,"due":True}
    assert "watchlisted" not in response.json()["items"][0]
