from __future__ import annotations
from datetime import datetime,timezone
from app.providers.x_twitterapi_io import TwitterApiIoProvider
from app.repositories.x_competitor_audience_repository import XCompetitorAudienceRepository
from app.services.x_competitor_growth_service import XCompetitorGrowthService
import re

class XCompetitorAudienceService:
    def __init__(self,repository=None,provider=None): self.repository=repository or XCompetitorAudienceRepository();self.provider=provider
    def dashboard(self):
        data=XCompetitorGrowthService().dashboard();counts=self.repository.audience_counts();latest=self.repository.latest_collection_runs()
        for item in data["items"]:
            own=item.get("account_role")=="OWN_ACCOUNT"
            item["audience_count"]=None if own else counts.get(str(item["id"]));run=None if own else latest.get(str(item["id"]))
            item["last_audience_scraped_at"]=(run.get("completed_at") or run.get("started_at") or run.get("created_at")) if run else None
            item["last_audience_scrape_status"]=run.get("status") if run else None
            item["last_audience_run_id"]=str(run["id"]) if run else None
        data["audience_summary"]=self.repository.global_audience_summary()
        benchmark=next((item for item in data["items"] if item.get("account_role")=="OWN_ACCOUNT"),None)
        data["items"]=[item for item in data["items"] if item.get("account_role","COMPETITOR")=="COMPETITOR"]
        data["benchmark"]=benchmark
        return data

    @staticmethod
    def _safe_error(value):
        if not value:return None
        message=str(value).replace("\r"," ").replace("\n"," ").strip()
        message=re.sub(r"(?i)bearer\s+\S+","Bearer [redacted]",message)
        message=re.sub(r"(?i)(authorization|api[-_ ]?key|token|secret)\s*[:=]\s*\S+(?:\s+\[redacted\])?",r"\1: [redacted]",message)
        message=re.sub(r"(?:[A-Za-z]:\\|/)(?:[^\s:]+[/\\])+[^\s:]+","[internal path]",message)
        return message[:500]

    def diagnostics(self,run_id):
        run,progress=self.repository.get_run_diagnostics(run_id)
        if run is None:raise LookupError("Audience collection run not found.")
        groups={kind:{"complete":0,"failed":0} for kind in ("REPLY","RETWEET","QUOTE")}
        failures=[]
        for row in progress:
            kind=row["signal_type"]
            if row["status"]=="SUCCEEDED":groups[kind]["complete"]+=1
            elif row["status"]=="FAILED":groups[kind]["failed"]+=1
            if row["status"]=="FAILED":
                failures.append({**row,"error_message":self._safe_error(row.get("error_message"))})
        return run,groups,failures
    def collect(self,competitor_id):
        competitor=self.repository.get_competitor(competitor_id)
        if not competitor: raise LookupError("Competitor not found.")
        if competitor.get("account_role") == "OWN_ACCOUNT": raise ValueError("The benchmark account cannot be scraped for leads.")
        if competitor.get("archived_at") is not None: raise ValueError("Archived competitors cannot be scraped.")
        now=datetime.now(timezone.utc);posts=self.repository.qualifying_posts(competitor_id,now);run=self.repository.begin_or_resume(competitor_id,posts,now);provider=self.provider or TwitterApiIoProvider()
        for progress in self.repository.pending_progress(run["id"]):
            try:
                cursor=progress["cursor"]
                while True:
                    page=provider.get_audience_page(progress["signal_type"],progress["x_tweet_id"],cursor=cursor)
                    self.repository.persist_page(run["id"],competitor_id,progress,page)
                    if not page.has_next_page: break
                    cursor=page.next_cursor
            except Exception as error: self.repository.fail_progress(run["id"],progress["id"],error)
        return self.repository.finish(run["id"])
