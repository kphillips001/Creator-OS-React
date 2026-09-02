"""Rolling follower growth derived exclusively from canonical profile snapshots."""
from __future__ import annotations

from datetime import datetime,timedelta
from typing import Any,Iterable,Mapping

from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
from app.services.x_competitor_engagement_service import XCompetitorEngagementService


def growth_for_window(snapshots:Iterable[Mapping[str,Any]],days:int,tolerance_days:int)->dict[str,Any]|None:
    rows=sorted(snapshots,key=lambda row:(row["observed_at"],str(row.get("id",""))))
    if not rows:return None
    current=rows[-1];current_count=current.get("followers_count")
    if not isinstance(current_count,int) or isinstance(current_count,bool):return None
    target=current["observed_at"]-timedelta(days=days);tolerance=timedelta(days=tolerance_days)
    candidates=[row for row in rows[:-1] if abs(row["observed_at"]-target)<=tolerance]
    if not candidates:return None
    # Nearest observation wins; an equally near earlier observation wins deterministically.
    baseline=min(candidates,key=lambda row:(abs(row["observed_at"]-target),row["observed_at"],str(row.get("id",""))))
    historical=baseline.get("followers_count")
    if not isinstance(historical,int) or isinstance(historical,bool) or historical<=0:return None
    raw=current_count-historical
    return {"raw":raw,"percent":raw/historical*100,"baseline_observed_at":baseline["observed_at"],"current_observed_at":current["observed_at"]}


class XCompetitorGrowthService:
    def __init__(self,repository=None):self.repository=repository or XCompetitorIntelligenceRepository()
    def dashboard(self)->dict[str,Any]:
        data=XCompetitorEngagementService(repository=self.repository).dashboard();histories=self.repository.list_profile_snapshot_histories()
        for item in data["items"]:
            snapshots=histories.get(str(item["id"]),[]);item["growth_7d"]=growth_for_window(snapshots,7,2);item["growth_30d"]=growth_for_window(snapshots,30,4)
        return data
