from datetime import datetime,timezone
from unittest.mock import Mock
import pytest
from app.providers.x_twitterapi_io import TwitterApiIoProvider
from app.services.x_competitor_audience_service import XCompetitorAudienceService
from app.repositories.x_competitor_audience_repository import XCompetitorAudienceRepository
from psycopg.errors import UndefinedTable
from fastapi import FastAPI
from fastapi.testclient import TestClient

class Response:
    status_code=200
    def __init__(self,payload):self.payload=payload
    def raise_for_status(self):pass
    def json(self):return self.payload
class Session:
    def __init__(self,payload):self.payload=payload;self.headers={};self.calls=[]
    def get(self,url,**kwargs):self.calls.append((url,kwargs));return Response(self.payload)

def test_reply_page_uses_documented_endpoint_and_embedded_author():
    session=Session({"replies":[{"id":"reply-1","createdAt":"2026-08-16T10:00:00Z","author":{"id":"u1","userName":"AvaFan","name":"Ava Fan","followers":12}}],"has_next_page":True,"next_cursor":"next"})
    page=TwitterApiIoProvider("key",session=session).get_audience_page("REPLY","tweet-1")
    assert session.calls[0][0].endswith("/twitter/tweet/replies")
    assert session.calls[0][1]["params"]=={"tweetId":"tweet-1","cursor":""}
    assert page.records[0].user.x_user_id=="u1" and page.records[0].interaction_x_tweet_id=="reply-1"
    assert page.has_next_page and page.next_cursor=="next"

def test_reply_page_accepts_production_tweets_compatibility_shape():
    session=Session({"tweets":[{"id":"reply-2","author":{"id":"u2","userName":"Fan2"}}],"has_next_page":False})
    page=TwitterApiIoProvider("key",session=session).get_audience_page("REPLY","tweet-1")
    assert page.records[0].interaction_x_tweet_id=="reply-2"
    assert page.records[0].user.x_user_id=="u2"

def test_empty_replies_are_a_successful_terminal_page():
    page=TwitterApiIoProvider("key",session=Session({"replies":[],"has_next_page":True,"next_cursor":"unused"})).get_audience_page("REPLY","tweet-1")
    assert page.records==() and not page.has_next_page

def test_non_advancing_reply_cursor_is_rejected():
    import pytest
    from app.providers.x_twitterapi_io import TwitterApiIoError
    provider=TwitterApiIoProvider("key",session=Session({"replies":[{"id":"r","author":{"id":"u","userName":"fan"}}],"has_next_page":True,"next_cursor":"same"}))
    with pytest.raises(TwitterApiIoError,match="did not advance"): provider.get_audience_page("REPLY","tweet-1",cursor="same")

def test_retweeter_page_uses_users_and_stable_occurrence_identity():
    session=Session({"users":[{"id":"u1","userName":"Fan"}],"has_next_page":False,"next_cursor":""})
    page=TwitterApiIoProvider("key",session=session).get_audience_page("RETWEET","tweet-1")
    assert session.calls[0][0].endswith("/twitter/tweet/retweeters")
    assert page.records[0].interaction_x_tweet_id=="RETWEET:tweet-1:u1"

def test_retweeter_page_preserves_valid_users_when_provider_includes_identityless_account_stub():
    session=Session({"users":[{"unavailable":True,"unavailableReason":"Suspended"},{"id":"u1","userName":"Fan"}],"has_next_page":False,"next_cursor":""})
    page=TwitterApiIoProvider("key",session=session).get_audience_page("RETWEET","tweet-1")
    assert [record.user.x_user_id for record in page.records]==["u1"]

def test_retweeter_page_rejects_wholly_malformed_nonempty_identity_page():
    import pytest
    from app.providers.x_twitterapi_io import TwitterApiIoError
    provider=TwitterApiIoProvider("key",session=Session({"users":[{"unavailable":True},{"name":"No canonical identity"}],"has_next_page":False}))
    with pytest.raises(TwitterApiIoError,match="no usable immutable user identities"):provider.get_audience_page("RETWEET","tweet-1")

def test_retweeter_mixed_page_preserves_pagination_contract():
    page=TwitterApiIoProvider("key",session=Session({"users":[{"id":"u1","userName":"Fan"},{"unavailable":True}],"has_next_page":True,"next_cursor":"next"})).get_audience_page("RETWEET","tweet-1")
    assert len(page.records)==1 and page.has_next_page and page.next_cursor=="next"

def test_quote_page_uses_tweets_and_embedded_author():
    session=Session({"tweets":[{"id":"quote-1","author":{"id":"u2","userName":"Fan2"}}],"has_next_page":False})
    page=TwitterApiIoProvider("key",session=session).get_audience_page("QUOTE","tweet-1")
    assert session.calls[0][0].endswith("/twitter/tweet/quotes") and page.records[0].user.x_user_id=="u2"

class Repo:
    def __init__(self):self.persisted=[]
    def get_competitor(self,_):return {"id":"c1"}
    def qualifying_posts(self,_,now):return [{"id":"p1","x_tweet_id":"t1","reply_count":1,"retweet_count":0,"quote_count":0}]
    def begin_or_resume(self,*_):return {"id":"r1"}
    def pending_progress(self,_):return [{"id":"pr1","competitor_post_id":"p1","signal_type":"REPLY","x_tweet_id":"t1","cursor":""}]
    def persist_page(self,*args):self.persisted.append(args[-1])
    def fail_progress(self,*_):raise AssertionError("unexpected failure")
    def finish(self,_):return {"id":"r1","status":"SUCCEEDED"}
class Provider:
    def get_audience_page(self,*_,**__):
        from app.providers.x_twitterapi_io import ResolvedXAudiencePage
        return ResolvedXAudiencePage((),"",False)

def test_collection_reuses_canonical_posts_and_persists_pages():
    repository=Repo();result=XCompetitorAudienceService(repository,Provider()).collect("c1")
    assert result["status"]=="SUCCEEDED" and len(repository.persisted)==1

def test_partial_resume_requests_only_repository_selected_failed_retweet_sources():
    class ResumeRepo(Repo):
        def qualifying_posts(self,_,now):return [{"id":"reply-complete"},{"id":"quote-complete"},{"id":"retweet-complete"},{"id":"retweet-failed"}]
        def pending_progress(self,_):return [{"id":"retry","competitor_post_id":"retweet-failed","signal_type":"RETWEET","x_tweet_id":"tweet-failed","cursor":"saved-cursor"}]
    class RecordingProvider(Provider):
        def __init__(self):self.calls=[]
        def get_audience_page(self,*args,**kwargs):self.calls.append((args,kwargs));return super().get_audience_page(*args,**kwargs)
    repository=ResumeRepo();provider=RecordingProvider();XCompetitorAudienceService(repository,provider).collect("c1")
    assert provider.calls==[(("RETWEET","tweet-failed"),{"cursor":"saved-cursor"})]
    assert len(repository.persisted)==1

class AggregateCursor:
    def __init__(self): self.sql=""
    def __enter__(self): return self
    def __exit__(self,*_): pass
    def execute(self,sql,*_): self.sql=sql
    def fetchone(self): return {"commenters":2,"retweeters":3,"quote_posters":2,"unique_leads":4}
class AggregateConnection:
    def __init__(self,cursor): self.value=cursor
    def __enter__(self): return self
    def __exit__(self,*_): pass
    def cursor(self): return self.value

def test_global_summary_counts_distinct_users_per_type_and_once_overall():
    cursor=AggregateCursor();summary=XCompetitorAudienceRepository(lambda:AggregateConnection(cursor)).global_audience_summary()
    assert summary=={"commenters":2,"retweeters":3,"quote_posters":2,"unique_leads":4}
    assert cursor.sql.count("COUNT(DISTINCT audience_user_id)")==4
    assert "signal_type='REPLY'" in cursor.sql and "signal_type='RETWEET'" in cursor.sql and "signal_type='QUOTE'" in cursor.sql

class LeadCursor:
    def __init__(self):self.calls=[]
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def execute(self,sql,params=None):self.calls.append((sql,params))
    def fetchone(self):return {"total":1}
    def fetchall(self):return [{"id":"u1","x_user_id":"42","username":"fan","display_name":"Fan","profile_image_url":None,"has_reply":True,"has_retweet":True,"has_quote":False,"competitor_count":3}]

def test_collected_leads_projection_groups_identity_and_distinct_competitors_with_search_sort_pagination():
    cursor=LeadCursor();rows,total=XCompetitorAudienceRepository(lambda:AggregateConnection(cursor)).list_collected_leads(page=2,page_size=25,search="FAN",sort="competitors-desc")
    assert total==1 and len(rows)==1 and rows[0]["competitor_count"]==3
    query,params=cursor.calls[1]
    assert "GROUP BY u.id" in query and "BOOL_OR(s.signal_type='REPLY')" in query
    assert "COUNT(DISTINCT s.competitor_id)" in query and "competitor_count DESC" in query
    assert params==["%FAN%","%FAN%",25,25]

class UsernameCursor:
    def __init__(self):self.sql=""
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def execute(self,sql):self.sql=sql
    def fetchall(self):return [{"username":"alpha"},{"username":"Beta"}]

def test_collected_lead_username_export_is_canonical_filtered_and_deterministic():
    cursor=UsernameCursor();usernames=XCompetitorAudienceRepository(lambda:AggregateConnection(cursor)).list_collected_lead_usernames()
    assert usernames==["alpha","Beta"]
    assert "EXISTS" in cursor.sql and "s.audience_user_id=u.id" in cursor.sql
    assert "REPLY','RETWEET','QUOTE" in cursor.sql
    assert "NULLIF(LTRIM(BTRIM(u.username),'@'),'') IS NOT NULL" in cursor.sql
    assert "DISTINCT ON (LOWER(LTRIM(BTRIM(u.username),'@')))" in cursor.sql

class ExportCursor:
    def __init__(self):self.sql="";self.batches=[[{"username":"SomeUser"}],[]];self.closed=False
    def execute(self,sql):self.sql=sql
    def fetchmany(self,size):assert size==1000;return self.batches.pop(0)
    def close(self):self.closed=True
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
class ExportConnection:
    def __init__(self,cursor):self.value=cursor;self.closed=False
    def cursor(self):return self.value
    def close(self):self.closed=True
    def __enter__(self):return self
    def __exit__(self,*_):self.close()

def test_collected_leads_csv_export_streams_one_row_per_case_insensitive_username():
    cursor=ExportCursor();connection=ExportConnection(cursor)
    rows=list(XCompetitorAudienceRepository(lambda:connection).iter_collected_lead_usernames())
    assert rows==["SomeUser"]
    assert "DISTINCT ON (LOWER(LTRIM(BTRIM(u.username),'@')))" in cursor.sql
    assert "signal_type IN ('REPLY','RETWEET','QUOTE')" in cursor.sql
    assert cursor.closed and connection.closed

def test_collected_leads_csv_endpoint_contains_only_normalized_username(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import x_competitor_intelligence as api
    class Repository:
        def iter_collected_lead_usernames(self):yield "AvaFan"
    monkeypatch.setattr(api.XCompetitorAudienceService,"__init__",lambda self:setattr(self,"repository",Repository()))
    application=FastAPI();application.include_router(api.router)
    response=TestClient(application).get("/api/v1/x-intelligence/audience/leads/export.csv")
    assert response.status_code==200 and response.headers["content-type"].startswith("text/csv")
    assert "creator_os_x_leads_" in response.headers["content-disposition"]
    import csv,io
    parsed=list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert parsed==[["username"],["AvaFan"]]

class LatestRunCursor:
    def __init__(self):self.sql=""
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def execute(self,sql):self.sql=sql
    def fetchall(self):return [{"id":"r1","competitor_id":"c1","status":"PARTIAL","created_at":datetime(2026,8,17,13,39,tzinfo=timezone.utc),"started_at":datetime(2026,8,17,13,40,tzinfo=timezone.utc),"completed_at":datetime(2026,8,17,13,42,tzinfo=timezone.utc)}]

def test_latest_collection_run_projection_uses_authoritative_newest_run_per_competitor():
    cursor=LatestRunCursor();runs=XCompetitorAudienceRepository(lambda:AggregateConnection(cursor)).latest_collection_runs()
    assert runs["c1"]["status"]=="PARTIAL"
    assert runs["c1"]["completed_at"]==datetime(2026,8,17,13,42,tzinfo=timezone.utc)
    assert "DISTINCT ON (competitor_id)" in cursor.sql
    assert "ORDER BY competitor_id,created_at DESC,started_at DESC NULLS LAST,id DESC" in cursor.sql

class GlobalRefreshCursor:
    def __init__(self):self.sql=""
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def execute(self,sql):self.sql=sql
    def fetchall(self):return [{"id":"r2","refresh_type":"ACTIVITY","status":"PARTIAL","completed_at":datetime(2026,8,17,14,tzinfo=timezone.utc)},{"id":"r1","refresh_type":"PROFILES","status":"SUCCEEDED","completed_at":datetime(2026,8,17,13,tzinfo=timezone.utc)}]

def test_global_refresh_projection_selects_latest_run_per_type_in_one_query():
    cursor=GlobalRefreshCursor();runs=XCompetitorAudienceRepository(lambda:AggregateConnection(cursor)).latest_global_refreshes()
    assert runs["ACTIVITY"]["status"]=="PARTIAL" and runs["PROFILES"]["status"]=="SUCCEEDED"
    assert "DISTINCT ON (refresh_type)" in cursor.sql and "ORDER BY refresh_type,created_at DESC,id DESC" in cursor.sql

def test_dashboard_keeps_competitors_and_leads_when_optional_global_refresh_history_is_unavailable(monkeypatch):
    import app.services.x_competitor_audience_service as module
    class DashboardRepo:
        def audience_counts(self):return {"c1":7}
        def latest_collection_runs(self):return {}
        def global_audience_summary(self):return {"commenters":4,"retweeters":3,"quote_posters":1,"unique_leads":7}
        def latest_global_refreshes(self):raise UndefinedTable("legacy database")
    monkeypatch.setattr(module,"XCompetitorGrowthService",lambda:type("Growth",(),{"dashboard":lambda self:{"items":[{"id":"c1"}]}})())
    result=XCompetitorAudienceService(repository=DashboardRepo()).dashboard()
    assert result["items"]==[{"id":"c1","audience_count":7,"last_audience_scraped_at":None,"last_audience_scrape_status":None,"last_audience_run_id":None}]
    assert result["audience_summary"]["unique_leads"]==7 and "global_refreshes" not in result


def test_own_account_is_never_eligible_for_audience_lead_collection():
    repository=Mock();repository.get_competitor.return_value={"id":"own","account_role":"OWN_ACCOUNT","archived_at":None}
    with pytest.raises(ValueError,match="benchmark account"):
        XCompetitorAudienceService(repository=repository).collect("own")
    repository.qualifying_posts.assert_not_called()

def test_diagnostics_groups_persisted_progress_and_sanitizes_operator_errors_without_provider():
    class DiagnosticRepo:
        def get_run_diagnostics(self,run_id):
            assert run_id=="r1"
            return {"id":"r1","competitor_id":"c1"},[
                {"signal_type":"REPLY","status":"SUCCEEDED","error_message":None},
                {"signal_type":"REPLY","status":"FAILED","error_message":"Authorization: Bearer secret-token at C:\\private\\worker.py"},
                {"signal_type":"RETWEET","status":"SUCCEEDED","error_message":None},
                {"signal_type":"QUOTE","status":"FAILED","error_message":None},
            ]
    run,sources,failures=XCompetitorAudienceService(repository=DiagnosticRepo()).diagnostics("r1")
    assert run["id"]=="r1" and sources=={"REPLY":{"complete":1,"failed":1},"RETWEET":{"complete":1,"failed":0},"QUOTE":{"complete":0,"failed":1}}
    assert "secret-token" not in failures[0]["error_message"] and "C:\\private" not in failures[0]["error_message"]

def test_diagnostics_route_returns_persisted_run_source_failures_and_post_context(monkeypatch):
    from app.api import x_competitor_intelligence as api
    run={"id":"r1","competitor_id":"c1","status":"PARTIAL","started_at":datetime(2026,8,17,13,40,tzinfo=timezone.utc),"completed_at":datetime(2026,8,17,13,42,tzinfo=timezone.utc),"posts_considered":2,"posts_processed":1,"reply_records_returned":4,"retweeter_records_returned":3,"quote_records_returned":1,"unique_users_observed":4,"new_users":3,"existing_users":1,"new_signals":5,"existing_signals":2,"provider_requests":6,"username":"ava","display_name":"Ava","profile_image_url":None}
    failures=[{"signal_type":"QUOTE","x_tweet_id":"tweet-1","posted_at":datetime(2026,8,17,12,tzinfo=timezone.utc),"text":"persisted context","pages_completed":2,"error_message":"Safe timeout"}]
    monkeypatch.setattr(api.XCompetitorAudienceService,"diagnostics",lambda self,run_id:(run,{"REPLY":{"complete":2,"failed":0},"RETWEET":{"complete":1,"failed":0},"QUOTE":{"complete":0,"failed":1}},failures))
    application=FastAPI();application.include_router(api.router);response=TestClient(application).get("/api/v1/x-intelligence/audience-runs/r1/diagnostics")
    assert response.status_code==200;body=response.json();assert body["run"]["id"]=="r1" and body["competitor"]["username"]=="ava"
    assert body["sourceStatus"]["quotes"]=={"complete":0,"failed":1} and body["failures"][0]["textPreview"]=="persisted context" and body["failures"][0]["pagesCompleted"]==2
