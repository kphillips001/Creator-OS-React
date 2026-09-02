"""Manual, one-page Last Active refresh for tracked X competitors."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.providers.x_twitterapi_io import TwitterApiIoError, TwitterApiIoProvider
from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
from app.services.x_competitor_post_policy import POST_METRIC_AUTO_REFRESH_WINDOW


class XCompetitorActivityService:
    def __init__(self, *, provider: Any | None = None, repository: Any | None = None, clock:Callable[[],datetime]|None=None):
        self.provider = provider or TwitterApiIoProvider()
        self.repository = repository or XCompetitorIntelligenceRepository()
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def refresh_competitor(self, competitor: Any, *, sync_type: str = "MANUAL", run_id=None) -> dict[str, Any]:
        now=self.clock();boundary=now-POST_METRIC_AUTO_REFRESH_WINDOW;username=competitor["username"]
        try:
            if not competitor.get("x_user_id"): raise TwitterApiIoError("Canonical X identity is unavailable.")
            timeline=self.provider.get_recent_activities(competitor["x_user_id"],since=boundary)
            latest=max(timeline,key=lambda item:item.posted_at) if timeline else None
            recent=[item for item in timeline if item.posted_at>=boundary];persisted={item.x_tweet_id:item for item in recent}
            if latest is not None: persisted[latest.x_tweet_id]=latest
            kwargs={"completed_at":now,"provider_requests":getattr(self.provider,"last_timeline_request_count",1),"sync_type":sync_type}
            if run_id is not None:kwargs["run_id"]=run_id
            changed=self.repository.persist_activity_collection(competitor["id"],list(persisted.values()),**kwargs)
            status="NO_ACTIVITY" if not timeline else "REFRESHED" if changed else "UNCHANGED";reason=None
        except TwitterApiIoError:
            status="FAILED";reason="Latest public activity could not be refreshed."
        except Exception:
            status="FAILED";reason="Latest public activity could not be persisted."
        if status=="FAILED" and run_id is not None:
            self.repository.fail_refresh(run_id,completed_at=self.clock(),error_code="ACTIVITY_REFRESH_FAILED",error_message=reason)
        if status=="FAILED" and sync_type=="INITIAL" and hasattr(self.repository,"mark_initial_activity_failed"):
            try: self.repository.mark_initial_activity_failed(competitor["id"],completed_at=now,provider_requests=getattr(self.provider,"last_timeline_request_count",0),error_code="ACTIVITY_COLLECTION_FAILED")
            except Exception: pass  # The durable competitor remains valid even if audit annotation fails.
        return {"competitorId":str(competitor["id"]),"username":username,"status":status,"reason":reason}

    def refresh_last_active(self) -> dict[str, Any]:
        started=self.clock();run=self.repository.begin_global_refresh("ACTIVITY",started_at=started);competitors=[];results=[]; counts={"refreshed":0,"unchanged":0,"noActivity":0,"failed":0}
        try:
            competitors = self.repository.list_tracked_competitors()
            for competitor in competitors:
                result=self.refresh_competitor(competitor);status=result["status"]
                counts[{"REFRESHED":"refreshed","UNCHANGED":"unchanged","NO_ACTIVITY":"noActivity","FAILED":"failed"}[status]]+=1;results.append(result)
        except Exception as error:
            completed=self.clock();self.repository.finish_global_refresh(run["id"],status="FAILED",completed_at=completed,considered=len(competitors),succeeded=len(results)-counts["failed"],failed=max(counts["failed"],1),error_message=str(error));raise
        succeeded=len(competitors)-counts["failed"];status="FAILED" if counts["failed"] and not succeeded else "PARTIAL" if counts["failed"] else "SUCCEEDED";completed=self.clock();self.repository.finish_global_refresh(run["id"],status=status,completed_at=completed,considered=len(competitors),succeeded=succeeded,failed=counts["failed"])
        return {"considered":len(competitors),**counts,"results":results,"completedAt":completed,"status":status}
