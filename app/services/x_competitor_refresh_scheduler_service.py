"""Cost-bounded rolling Profile and Activity refresh scheduling."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
from app.services.x_competitor_refresh_policy import XCompetitorRefreshPolicy
from app.services.x_competitor_refresh_service import XCompetitorRefreshService


class XCompetitorRefreshSchedulerService:
    def __init__(self, *, repository=None, refresh_service=None,
                 clock: Callable[[], datetime] | None = None):
        self.repository=repository or XCompetitorIntelligenceRepository()
        self.refresh_service=refresh_service or XCompetitorRefreshService(repository=self.repository)
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def run_once(self, *, limit: int = XCompetitorRefreshPolicy.DEFAULT_BATCH_SIZE,
                 exclude_competitor_ids: tuple[str, ...] = ()) -> dict[str, Any]:
        now=self.clock();bounded=max(1,int(limit));results=[]
        due=self.repository.list_due_competitor_refreshes(due_before=now-XCompetitorRefreshPolicy.INTERVAL,
            retry_before=now-XCompetitorRefreshPolicy.FAILURE_BACKOFF,limit=bounded,
            exclude_competitor_ids=exclude_competitor_ids)
        for competitor in due:
            try:
                results.append(self.refresh_service.refresh_competitor(competitor,sync_type="WEEKLY"))
            except Exception as error:
                # One provider/persistence failure must not strand the rest of the
                # weekly cycle. The canonical refresh claim remains the authority
                # for retry/backoff handling.
                results.append({"competitorId":str(competitor["id"]),
                    "username":competitor["username"],"status":"FAILED",
                    "reason":str(error)})
        return {"considered":len(results),"competitorIds":[str(item["id"]) for item in due],"results":results}

    def run_weekly_cycle(self, *, limit: int = XCompetitorRefreshPolicy.DEFAULT_BATCH_SIZE,
                         between_batches: Callable[[float], None] | None = None) -> dict[str, Any]:
        """Drain one weekly due set in sequential, rate-bounded batches."""
        bounded=max(1,int(limit));pause=between_batches or (lambda _seconds:None)
        results=[];batches=0;considered_ids=[]
        while True:
            batch=self.run_once(limit=bounded,exclude_competitor_ids=tuple(considered_ids));batches+=1
            results.extend(batch["results"])
            considered_ids.extend(batch["competitorIds"])
            if batch["considered"] < bounded:
                break
            pause(XCompetitorRefreshPolicy.BATCH_PAUSE_SECONDS)
        return {"considered":len(results),"batches":batches,"results":results}
