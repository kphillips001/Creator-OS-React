from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import x_competitor_intelligence as api
from app.providers.x_twitterapi_io import ResolvedXActivity, TwitterApiIoError, TwitterApiIoProvider
from app.services.x_competitor_activity_service import XCompetitorActivityService
from app.services.x_competitor_archived_post_service import XCompetitorArchivedPostService


def response(payload):
    value=Mock();value.status_code=200;value.raise_for_status.return_value=None;value.json.return_value=payload;return value


@pytest.mark.parametrize(("tweet","flags"),[
    ({"id":"original","createdAt":"2026-08-16T10:00:00Z","text":"post"},(False,False,False)),
    ({"id":"reply","createdAt":"2026-08-16T10:00:00Z","isReply":True},(True,False,False)),
    ({"id":"quote","createdAt":"2026-08-16T10:00:00Z","quoted_tweet":{"id":"q"}},(False,True,False)),
    ({"id":"repost","createdAt":"Sat Aug 16 10:00:00 +0000 2026","retweeted_tweet":{"id":"r"}},(False,False,True)),
])
def test_latest_activity_normalizes_all_public_timeline_activity_types(tweet,flags):
    session=Mock(spec=requests.Session);session.headers={};session.get.return_value=response({"status":"success","tweets":[tweet]})
    activity=TwitterApiIoProvider("test-secret",session=session).get_latest_activity("42")
    assert (activity.is_reply,activity.is_quote,activity.is_retweet)==flags
    assert session.get.call_count==1
    assert session.get.call_args.kwargs["params"]=={"userId":"42","cursor":""}


def test_latest_activity_uses_newest_item_and_handles_empty_or_malformed_response():
    session=Mock(spec=requests.Session);session.headers={};session.get.side_effect=[
        response({"data":{"tweets":[{"id":"old","createdAt":"2026-08-15T10:00:00Z"},{"id":"new","createdAt":"2026-08-16T10:00:00Z"}]}}),
        response({"tweets":[]}),response({"tweets":[{"id":"missing-time"}]}),
    ]
    provider=TwitterApiIoProvider("test-secret",session=session)
    assert provider.get_latest_activity("42").x_tweet_id=="new"
    assert provider.get_latest_activity("42") is None
    with pytest.raises(TwitterApiIoError,match="malformed"): provider.get_latest_activity("42")


def test_recent_activity_paginates_to_boundary_normalizes_metrics_and_stops():
    session=Mock(spec=requests.Session);session.headers={};session.get.side_effect=[
        response({"tweets":[{"id":"new","createdAt":"2026-08-16T10:00:00Z","viewCount":100,"likeCount":9,"replyCount":3,"retweetCount":2,"quoteCount":1,"bookmarkCount":4,"lang":"en","conversationId":"c","media":[{"type":"photo","url":"https://img"}]}],"has_next_page":True,"next_cursor":"page2"}),
        response({"tweets":[{"id":"old","createdAt":"2026-08-08T10:00:00Z"}],"has_next_page":True,"next_cursor":"page3"}),
    ]
    provider=TwitterApiIoProvider("test-secret",session=session);items=provider.get_recent_activities("42",since=datetime(2026,8,9,tzinfo=timezone.utc))
    assert [item.x_tweet_id for item in items]==["new","old"] and session.get.call_count==2
    assert (items[0].view_count,items[0].like_count,items[0].reply_count,items[0].retweet_count,items[0].quote_count,items[0].bookmark_count)==(100,9,3,2,1,4)
    assert items[0].has_media and items[0].media_metadata[0]["url"]=="https://img"


def test_recent_activity_enforces_defensive_page_bound():
    session=Mock(spec=requests.Session);session.headers={};session.get.return_value=response({"tweets":[{"id":"new","createdAt":"2026-08-16T10:00:00Z"}],"has_next_page":True,"next_cursor":"next"})
    with pytest.raises(TwitterApiIoError,match="page limit"):
        TwitterApiIoProvider("test-secret",session=session).get_recent_activities("42",since=datetime(2026,8,9,tzinfo=timezone.utc),max_pages=1)

def test_targeted_tweet_lookup_is_one_request_and_validates_identity():
    session=Mock(spec=requests.Session);session.headers={};session.get.side_effect=[response({"tweets":[{"id":"42","createdAt":"2026-08-01T10:00:00Z","viewCount":9}]}),response({"tweets":[{"id":"other","createdAt":"2026-08-01T10:00:00Z"}]})]
    provider=TwitterApiIoProvider("test-secret",session=session);assert provider.get_tweet("42").view_count==9
    assert session.get.call_args_list[0].kwargs["params"]=={"tweet_ids":"42"}
    with pytest.raises(TwitterApiIoError,match="different tweet"): provider.get_tweet("42")

def test_manual_archived_refresh_is_idempotent_before_provider_call():
    now=datetime(2026,8,16,tzinfo=timezone.utc);post={"id":"p","x_tweet_id":"t","posted_at":datetime(2026,8,1,tzinfo=timezone.utc),"is_reply":False,"is_retweet":False}
    repository=Mock();repository.get_post_with_competitor.return_value=post;repository.has_manual_snapshot.side_effect=[True,False];repository.persist_manual_metrics.return_value={**post,"view_count":20}
    provider=Mock();provider.get_tweet.return_value=ResolvedXActivity("t",post["posted_at"],None,False,False,False,False,view_count=20)
    service=XCompetitorArchivedPostService(provider=provider,repository=repository,clock=lambda:now)
    assert service.refresh_metrics("p",idempotency_key="same")[1] is True and provider.get_tweet.call_count==0
    assert service.refresh_metrics("p",idempotency_key="new")[0]["view_count"]==20 and provider.get_tweet.call_count==1


class FakeRepository:
    def __init__(self):
        self.competitors=[{"id":"1","x_user_id":"x1","username":"one"},{"id":"2","x_user_id":"x2","username":"two"},{"id":"3","x_user_id":"x3","username":"three"}];self.persisted=[];self.global_run=None
    def begin_global_refresh(self,refresh_type,**kwargs):self.global_run={"id":"run","refresh_type":refresh_type,**kwargs};return self.global_run
    def finish_global_refresh(self,run_id,**kwargs):self.global_run={**self.global_run,**kwargs};return self.global_run
    def list_tracked_competitors(self): return self.competitors
    def persist_activity_collection(self,competitor_id,activities,**kwargs): self.persisted.append((competitor_id,activities,kwargs));return competitor_id=="1"


class FakeProvider:
    last_timeline_request_count=1
    def get_recent_activities(self,user_id,**kwargs):
        if user_id=="x2": return []
        if user_id=="x3": raise TwitterApiIoError("provider detail")
        return [ResolvedXActivity("tweet-1",datetime(2026,8,16,tzinfo=timezone.utc),None,False,False,False,False)]


def test_manual_refresh_is_partial_success_safe_and_only_uses_repository_tracked_set():
    repository=FakeRepository();result=XCompetitorActivityService(provider=FakeProvider(),repository=repository).refresh_last_active()
    assert {key:result[key] for key in ("considered","refreshed","unchanged","noActivity","failed")}=={"considered":3,"refreshed":1,"unchanged":0,"noActivity":1,"failed":1}
    assert [item[0] for item in repository.persisted]==["1","2"]
    assert repository.persisted[1][1]==[]  # durable confirmed-zero dataset
    assert all(item[2]["sync_type"]=="MANUAL" for item in repository.persisted)
    assert result["results"][2]["reason"]=="Latest public activity could not be refreshed."
    assert result["status"]=="PARTIAL" and repository.global_run["status"]=="PARTIAL"


def test_initial_activity_reuses_eight_day_collection_and_initial_sync_accounting():
    now=datetime(2026,8,16,tzinfo=timezone.utc);repository=Mock();repository.persist_activity_collection.return_value=True
    provider=Mock();provider.last_timeline_request_count=2;provider.get_recent_activities.return_value=[ResolvedXActivity("tweet",now,None,False,False,False,False,view_count=10)]
    result=XCompetitorActivityService(provider=provider,repository=repository,clock=lambda:now).refresh_competitor({"id":"new","x_user_id":"x1","username":"one"},sync_type="INITIAL")
    assert result["status"]=="REFRESHED"
    assert provider.get_recent_activities.call_args.kwargs["since"]==datetime(2026,8,8,tzinfo=timezone.utc)
    assert repository.persist_activity_collection.call_args.kwargs["sync_type"]=="INITIAL"
    assert repository.persist_activity_collection.call_args.kwargs["provider_requests"]==2


def test_obsolete_separate_activity_refresh_endpoint_is_not_exposed():
    application=FastAPI();application.include_router(api.router)
    response_value=TestClient(application).post("/api/v1/x-intelligence/competitors/last-active/refresh")
    assert response_value.status_code==404


def test_posts_7d_endpoint_reads_only_canonical_repository_projection(monkeypatch):
    from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
    now=datetime(2026,8,16,tzinfo=timezone.utc)
    monkeypatch.setattr(XCompetitorIntelligenceRepository,"get",lambda self,value:{"id":"1","username":"ava","display_name":"Ava","profile_image_url":None})
    monkeypatch.setattr(XCompetitorIntelligenceRepository,"list_posts_7d",lambda self,value:[{"id":"p","x_tweet_id":"t","text":"post","posted_at":now,"language":"en","conversation_id":"c","is_quote":False,"has_media":False,"media_metadata":[],"view_count":10,"like_count":2,"reply_count":1,"retweet_count":0,"quote_count":0,"bookmark_count":None}])
    application=FastAPI();application.include_router(api.router);result=TestClient(application).get("/api/v1/x-intelligence/competitors/1/posts-7d")
    assert result.status_code==200 and result.json()["posts"][0]["viewCount"]==10 and result.json()["count"]==1

def test_archived_endpoint_is_database_only_and_preserves_pagination(monkeypatch):
    from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
    now=datetime(2026,7,1,tzinfo=timezone.utc);calls=[]
    monkeypatch.setattr(XCompetitorIntelligenceRepository,"get",lambda self,value:{"id":"1","username":"ava","display_name":"Ava","profile_image_url":None})
    def archived(self,value,*,page,page_size):
        calls.append((page,page_size));return [{"id":"p","x_tweet_id":"t","text":"old","posted_at":now,"language":None,"conversation_id":None,"is_quote":False,"has_media":False,"media_metadata":[],"view_count":1,"like_count":None,"reply_count":None,"retweet_count":None,"quote_count":None,"bookmark_count":None,"last_refreshed_at":now}],51
    monkeypatch.setattr(XCompetitorIntelligenceRepository,"list_archived_posts",archived)
    application=FastAPI();application.include_router(api.router);result=TestClient(application).get("/api/v1/x-intelligence/competitors/1/posts-archived?page=2&page_size=25")
    assert result.status_code==200 and result.json()["count"]==51 and result.json()["page"]==2 and calls==[(2,25)]
