"""Explicit competitor profile intake orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.providers.x_twitterapi_io import TwitterApiIoError, TwitterApiIoNotFound, TwitterApiIoProvider
from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
from app.services.x_competitor_activity_service import XCompetitorActivityService


class XCompetitorIntelligenceService:
    MAX_BATCH_SIZE = 50
    PLATFORMS = frozenset({"FANVUE", "ONLYFANS", "OTHER"})

    def __init__(self, *, provider=None, repository=None, activity_service=None):
        self.provider = provider or TwitterApiIoProvider()
        self.repository = repository or XCompetitorIntelligenceRepository()
        self.activity_service = activity_service or XCompetitorActivityService(provider=self.provider,repository=self.repository)

    def import_competitors(self, usernames: list[str], *, platform: str = "FANVUE") -> list[dict[str, Any]]:
        if platform not in self.PLATFORMS:
            raise ValueError("Creator platform must be FANVUE, ONLYFANS, or OTHER.")
        results = []
        for submitted in usernames:
            try:
                profile = self.provider.get_user_by_username(submitted)
                existing = self.repository.get_by_x_user_id(profile.x_user_id) if hasattr(self.repository,"get_by_x_user_id") else None
                if existing is not None and existing.get("archived_at") is not None:
                    existing = self.repository.update_archived_resolved_profile(existing["id"], profile) or existing
                    results.append({"submittedUsername":submitted,"resolvedUsername":profile.username,"status":"ARCHIVED","reason":"This competitor is archived. Restore them?","activityStatus":None,"competitorId":str(existing["id"])})
                    continue
                competitor, existed = self.repository.persist_resolved_profile(
                    profile, observed_at=datetime.now(timezone.utc), platform=platform,
                )
                if existed:
                    results.append({"submittedUsername":submitted,"resolvedUsername":profile.username,"status":"ALREADY_TRACKED","reason":None,"activityStatus":None})
                    continue
                try: activity=self.activity_service.refresh_competitor(competitor,sync_type="INITIAL")
                except Exception: activity={"status":"FAILED"}
                failed=activity["status"]=="FAILED"
                results.append({"submittedUsername":submitted,"resolvedUsername":profile.username,"status":"ADDED","reason":"Activity needs refresh." if failed else None,"activityStatus":activity["status"]})
            except TwitterApiIoNotFound as error:
                results.append({"submittedUsername":submitted,"resolvedUsername":None,"status":"NOT_FOUND","reason":str(error),"activityStatus":None})
            except TwitterApiIoError:
                results.append({"submittedUsername":submitted,"resolvedUsername":None,"status":"FAILED","reason":"Profile lookup failed. Try again later.","activityStatus":None})
            except Exception:
                results.append({"submittedUsername":submitted,"resolvedUsername":None,"status":"FAILED","reason":"Competitor could not be saved. Try again later.","activityStatus":None})
        return results

    def register_own_account(self, username: str = "avablackthorne") -> dict[str, Any]:
        """Resolve, classify, and run the canonical initial combined intelligence refresh."""
        profile=self.provider.get_user_by_username(username.strip().lstrip("@"))
        competitor,_=self.repository.persist_resolved_profile(profile,observed_at=datetime.now(timezone.utc))
        account=self.repository.classify_own_account(competitor["id"])
        refresh=self.activity_service.refresh_competitor(account,sync_type="INITIAL")
        if refresh.get("status") == "FAILED":
            raise RuntimeError("Benchmark activity collection failed.")
        return {"account":account,"activity":refresh}

    def archive_competitor(self, competitor_id: str):
        existing=self.repository.get(competitor_id)
        if existing and existing.get("account_role") == "OWN_ACCOUNT":raise ValueError("The benchmark account cannot be archived.")
        row=self.repository.archive(competitor_id)
        if row is None:raise LookupError("Competitor not found.")
        return row

    def restore_competitor(self, competitor_id: str):
        row=self.repository.restore(competitor_id)
        if row is None:raise LookupError("Competitor not found.")
        return row

    def list_archived_competitors(self):
        return self.repository.list_archived()
