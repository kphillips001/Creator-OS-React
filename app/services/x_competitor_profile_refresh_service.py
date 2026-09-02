"""Explicit, cost-bounded refresh of tracked competitor profile statistics."""
from __future__ import annotations

from datetime import datetime,timezone
from typing import Any,Callable

from app.providers.x_twitterapi_io import TwitterApiIoError,TwitterApiIoProvider
from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository


class XCompetitorProfileRefreshService:
    def __init__(self,*,provider=None,repository=None,clock:Callable[[],datetime]|None=None):
        self.provider=provider or TwitterApiIoProvider();self.repository=repository or XCompetitorIntelligenceRepository();self.clock=clock or (lambda:datetime.now(timezone.utc))

    def refresh_competitor(self,competitor:Any,*,sync_type:str="MANUAL",run_id=None)->dict[str,Any]:
        try:
            profile=self.provider.get_user_by_username(competitor["username"])
            if competitor.get("x_user_id") and profile.x_user_id!=competitor["x_user_id"]:raise TwitterApiIoError("Resolved X identity changed.")
            kwargs={"observed_at":self.clock()}
            if run_id is not None:kwargs["run_id"]=run_id
            self.repository.persist_profile_refresh(competitor["id"],profile,**kwargs)
            return {"competitorId":str(competitor["id"]),"username":competitor["username"],"status":"REFRESHED","reason":None}
        except TwitterApiIoError:
            if run_id is not None:self.repository.fail_refresh(run_id,completed_at=self.clock(),error_code="PROFILE_PROVIDER_FAILED",error_message="Current profile statistics could not be refreshed.")
            return {"competitorId":str(competitor["id"]),"username":competitor["username"],"status":"FAILED","reason":"Current profile statistics could not be refreshed."}
        except Exception:
            if run_id is not None:self.repository.fail_refresh(run_id,completed_at=self.clock(),error_code="PROFILE_PERSISTENCE_FAILED",error_message="Current profile statistics could not be persisted.")
            return {"competitorId":str(competitor["id"]),"username":competitor["username"],"status":"FAILED","reason":"Current profile statistics could not be persisted."}

    def refresh(self)->dict[str,Any]:
        started=self.clock();run=self.repository.begin_global_refresh("PROFILES",started_at=started);competitors=[];results=[];refreshed=failed=0
        try:
            competitors=self.repository.list_tracked_competitors()
            for competitor in competitors:
                result=self.refresh_competitor(competitor);results.append(result)
                if result["status"]=="REFRESHED":refreshed+=1
                else:failed+=1
        except Exception as error:
            completed=self.clock();self.repository.finish_global_refresh(run["id"],status="FAILED",completed_at=completed,considered=len(competitors),succeeded=refreshed,failed=max(failed,1),error_message=str(error));raise
        status="FAILED" if failed and not refreshed else "PARTIAL" if failed else "SUCCEEDED";completed=self.clock();self.repository.finish_global_refresh(run["id"],status=status,completed_at=completed,considered=len(competitors),succeeded=refreshed,failed=failed)
        return {"considered":len(competitors),"refreshed":refreshed,"failed":failed,"results":results,"completedAt":completed,"status":status}
