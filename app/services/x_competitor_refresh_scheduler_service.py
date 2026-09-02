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

    def run_once(self, *, limit: int = XCompetitorRefreshPolicy.DEFAULT_BATCH_SIZE) -> dict[str, Any]:
        now=self.clock();bounded=max(1,int(limit));results=[]
        due=self.repository.list_due_competitor_refreshes(due_before=now-XCompetitorRefreshPolicy.INTERVAL,
            retry_before=now-XCompetitorRefreshPolicy.FAILURE_BACKOFF,limit=bounded)
        for competitor in due:
            results.append(self.refresh_service.refresh_competitor(competitor,sync_type="WEEKLY"))
        return {"considered":len(results),"results":results}
