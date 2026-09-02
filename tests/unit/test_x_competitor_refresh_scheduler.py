from datetime import datetime, timedelta, timezone

from app.services.x_competitor_refresh_policy import XCompetitorRefreshPolicy
from app.services.x_competitor_refresh_scheduler_service import XCompetitorRefreshSchedulerService
from app.services.x_competitor_refresh_service import XCompetitorRefreshService


NOW = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)


def item(value): return {"id":value,"x_user_id":f"x-{value}","username":value}


class DueRepository:
    def __init__(self, due=()): self.due=list(due);self.calls=[]
    def list_due_competitor_refreshes(self, **kwargs):self.calls.append(kwargs);return self.due[:kwargs["limit"]]


class CombinedService:
    def __init__(self):self.calls=[]
    def refresh_competitor(self, competitor, *, sync_type):
        self.calls.append((competitor["id"],sync_type));return {"status":"REFRESHED"}


def test_seven_day_policy_is_exact():
    last=NOW-timedelta(days=7)
    assert XCompetitorRefreshPolicy.next_at(last)==NOW
    assert XCompetitorRefreshPolicy.due(last,NOW)
    assert not XCompetitorRefreshPolicy.due(last+timedelta(seconds=1),NOW)
    assert XCompetitorRefreshPolicy.due(None,NOW)


def test_scheduler_processes_a_bounded_number_of_due_competitors():
    repository=DueRepository([item("one"),item("two"),item("three")]);service=CombinedService()
    result=XCompetitorRefreshSchedulerService(repository=repository,refresh_service=service,clock=lambda:NOW).run_once(limit=2)
    assert result["considered"]==2 and service.calls==[("one","WEEKLY"),("two","WEEKLY")]
    assert repository.calls[0]["due_before"]==NOW-timedelta(days=7)
    assert repository.calls[0]["retry_before"]==NOW-timedelta(hours=6)


class RefreshRepository:
    def __init__(self, claim):self.claim=claim;self.completed=[]
    def claim_competitor_refresh(self,*args,**kwargs):return self.claim
    def complete_competitor_refresh(self,*args,**kwargs):
        self.completed.append((args,kwargs));return {"completed_at":kwargs["completed_at"]}


class Step:
    def __init__(self,status):self.status=status;self.calls=[]
    def refresh_competitor(self,competitor,*,sync_type,run_id):
        self.calls.append((competitor["id"],sync_type,run_id));return {"status":self.status,"competitorId":competitor["id"],"username":competitor["username"],"reason":None}


def test_combined_refresh_runs_profile_then_activity_and_only_then_completes():
    repository=RefreshRepository({"id":"claim","profile_synced":False,"posts_synced":False});profile=Step("REFRESHED");activity=Step("UNCHANGED")
    result=XCompetitorRefreshService(repository=repository,provider=object(),profile_service=profile,activity_service=activity,clock=lambda:NOW).refresh_competitor(item("one"))
    assert result["status"]=="REFRESHED"
    assert profile.calls==[("one","WEEKLY","claim")] and activity.calls==[("one","WEEKLY","claim")]
    assert len(repository.completed)==1


def test_partial_refresh_does_not_complete_combined_clock():
    repository=RefreshRepository({"id":"claim","profile_synced":False,"posts_synced":False});profile=Step("REFRESHED");activity=Step("FAILED")
    result=XCompetitorRefreshService(repository=repository,provider=object(),profile_service=profile,activity_service=activity,clock=lambda:NOW).refresh_competitor(item("one"))
    assert result["status"]=="FAILED" and repository.completed==[]


def test_retry_resumes_completed_profile_subwork():
    repository=RefreshRepository({"id":"claim","profile_synced":True,"posts_synced":False});profile=Step("REFRESHED");activity=Step("NO_ACTIVITY")
    result=XCompetitorRefreshService(repository=repository,provider=object(),profile_service=profile,activity_service=activity,clock=lambda:NOW).refresh_competitor(item("one"))
    assert result["status"]=="REFRESHED" and profile.calls==[] and len(activity.calls)==1


def test_active_combined_claim_prevents_duplicate_provider_work():
    repository=RefreshRepository(None);profile=Step("REFRESHED");activity=Step("REFRESHED")
    result=XCompetitorRefreshService(repository=repository,provider=object(),profile_service=profile,activity_service=activity,clock=lambda:NOW).refresh_competitor(item("one"))
    assert result["status"]=="IN_PROGRESS" and profile.calls==[] and activity.calls==[]
