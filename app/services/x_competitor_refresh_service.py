"""Canonical combined Profile + Activity refresh orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.providers.x_twitterapi_io import TwitterApiIoProvider
from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
from app.services.x_competitor_activity_service import XCompetitorActivityService
from app.services.x_competitor_profile_refresh_service import XCompetitorProfileRefreshService


class XCompetitorRefreshService:
    def __init__(self, *, repository=None, provider=None, profile_service=None,
                 activity_service=None, clock: Callable[[], datetime] | None = None):
        self.repository=repository or XCompetitorIntelligenceRepository();self.clock=clock or (lambda:datetime.now(timezone.utc))
        shared_provider=provider or TwitterApiIoProvider()
        self.profiles=profile_service or XCompetitorProfileRefreshService(provider=shared_provider,repository=self.repository,clock=self.clock)
        self.activity=activity_service or XCompetitorActivityService(provider=shared_provider,repository=self.repository,clock=self.clock)

    def refresh_competitor(self, competitor: Any, *, sync_type: str = "WEEKLY") -> dict[str, Any]:
        claim=self.repository.claim_competitor_refresh(competitor["id"],sync_type=sync_type,started_at=self.clock())
        if claim is None:return {"competitorId":str(competitor["id"]),"username":competitor["username"],"status":"IN_PROGRESS","reason":"Competitor refresh is already running."}
        if not claim.get("profile_synced"):
            profile=self.profiles.refresh_competitor(competitor,sync_type=sync_type,run_id=claim["id"])
            if profile["status"]!="REFRESHED":return {**profile,"status":"FAILED"}
        if not claim.get("posts_synced"):
            activity=self.activity.refresh_competitor(competitor,sync_type=sync_type,run_id=claim["id"])
            if activity["status"]=="FAILED":return activity
        completed=self.repository.complete_competitor_refresh(claim["id"],completed_at=self.clock())
        return {"competitorId":str(competitor["id"]),"username":competitor["username"],"status":"REFRESHED","reason":None,"completedAt":completed["completed_at"]}
