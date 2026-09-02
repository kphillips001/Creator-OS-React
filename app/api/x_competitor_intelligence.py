import csv
import io
from datetime import date, datetime, timezone
from typing import Literal
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.services.x_competitor_intelligence_service import XCompetitorIntelligenceService
from app.services.x_competitor_archived_post_service import XCompetitorArchivedPostService
from app.services.x_competitor_engagement_service import XCompetitorEngagementService
from app.services.x_competitor_growth_service import XCompetitorGrowthService
from app.services.x_competitor_audience_service import XCompetitorAudienceService
from app.services.x_competitor_manual_intelligence_service import XCompetitorManualIntelligenceService
from app.services.x_competitor_refresh_policy import XCompetitorRefreshPolicy

router = APIRouter(prefix="/api/v1/x-intelligence", tags=["x-intelligence"])


class CompetitorImportRequest(BaseModel):
    usernames: list[str] = Field(min_length=1, max_length=XCompetitorIntelligenceService.MAX_BATCH_SIZE)
    platform: Literal["FANVUE", "ONLYFANS", "OTHER"] = "FANVUE"

    @field_validator("usernames")
    @classmethod
    def validate_usernames(cls, values: list[str]):
        ordered=[]; seen=set()
        for raw in values:
            value=raw.strip().lstrip("@")
            if not value or len(value)>15 or not all(char.isalnum() or char=="_" for char in value):
                raise ValueError("Each username must contain 1-15 letters, numbers, or underscores.")
            key=value.lower()
            if key not in seen: seen.add(key); ordered.append(value)
        return ordered


class CompetitorTelegramIntelligenceRequest(BaseModel):
    presence: str
    telegram_url: str | None = Field(default=None, alias="telegramUrl")
    audience_type: str | None = Field(default=None, alias="audienceType")
    comments_allowed: bool | None = Field(default=None, alias="commentsAllowed")
    joined: bool | None = None
    scraped: bool | None = None

    @field_validator("presence")
    @classmethod
    def validate_presence(cls, value: str):
        if value not in XCompetitorManualIntelligenceService.PRESENCE_VALUES:
            raise ValueError("Telegram presence must be UNKNOWN, YES, or NO.")
        return value

    @field_validator("audience_type")
    @classmethod
    def validate_audience_type(cls, value: str | None):
        if value is not None and value not in XCompetitorManualIntelligenceService.AUDIENCE_TYPES:
            raise ValueError("Audience type must be SUBSCRIBERS, MEMBERS, or null.")
        return value


def _service():
    return XCompetitorIntelligenceService()


@router.post("/competitors/import")
def import_competitors(body: CompetitorImportRequest):
    try: results = _service().import_competitors(body.usernames, platform=body.platform)
    except Exception as error:
        raise HTTPException(status_code=503,detail="X competitor profile resolution is unavailable.") from error
    return {"results":results}


@router.get("/competitors/archived")
def list_archived_competitors():
    rows=_service().list_archived_competitors()
    return {"items":[{"id":str(row["id"]),"xUserId":row["x_user_id"],"username":row["username"],"displayName":row["display_name"],"profileImageUrl":row["profile_image_url"],"platform":row.get("platform","FANVUE"),"followersCount":row["followers_count"],"archivedAt":_iso(row["archived_at"])} for row in rows]}


@router.post("/competitors/{competitor_id}/archive")
def archive_competitor(competitor_id:str):
    try:row=_service().archive_competitor(competitor_id)
    except LookupError as error:raise HTTPException(404,str(error)) from error
    except ValueError as error:raise HTTPException(409,str(error)) from error
    return {"id":str(row["id"]),"archivedAt":_iso(row["archived_at"])}


@router.post("/competitors/{competitor_id}/restore")
def restore_competitor(competitor_id:str):
    try:row=_service().restore_competitor(competitor_id)
    except LookupError as error:raise HTTPException(404,str(error)) from error
    return {"id":str(row["id"]),"archivedAt":None}


def _iso(value): return value.isoformat() if isinstance(value,(date,datetime)) else value
def _post(row): return {"id":str(row["id"]),"xTweetId":row["x_tweet_id"],"text":row["text"],"postedAt":_iso(row["posted_at"]),"language":row["language"],"conversationId":row["conversation_id"],"isQuote":row["is_quote"],"hasMedia":row["has_media"],"mediaMetadata":row["media_metadata"],"viewCount":row["view_count"],"likeCount":row["like_count"],"replyCount":row["reply_count"],"retweetCount":row["retweet_count"],"quoteCount":row["quote_count"],"bookmarkCount":row["bookmark_count"],"lastMetricObservedAt":_iso(row.get("last_refreshed_at"))}


@router.get("/competitors")
def list_competitors():
    data=XCompetitorAudienceService().dashboard()
    def growth(value):return None if value is None else {"raw":value["raw"],"percent":value["percent"],"baselineObservedAt":_iso(value["baseline_observed_at"]),"currentObservedAt":_iso(value["current_observed_at"])}
    summary=data["audience_summary"]
    now=datetime.now(timezone.utc)
    def schedule(value):
        next_at=XCompetitorRefreshPolicy.next_at(value)
        return {"lastSuccessfulAt":_iso(value),"nextRefreshAt":_iso(next_at),"due":XCompetitorRefreshPolicy.due(value,now)}
    def item(row):return {"id":str(row["id"]),"xUserId":row["x_user_id"],"username":row["username"],"displayName":row["display_name"],"profileImageUrl":row["profile_image_url"],"accountRole":row.get("account_role","COMPETITOR"),"platform":row.get("platform","FANVUE"),"trackingEnabled":row["tracking_enabled"],"telegramPresence":row["telegram_presence"],"telegramUrl":row.get("telegram_url"),"telegramAudienceType":row["telegram_audience_type"],"telegramCommentsAllowed":row["telegram_comments_allowed"],"telegramJoined":row["telegram_joined"],"telegramScraped":bool(row.get("telegram_scraped",False)),"followersCount":row["followers_count"],"createdAt":_iso(row["created_at"]),"observedAt":_iso(row["observed_at"]),"lastActiveAt":_iso(row["last_active_at"]),"lastAudienceScrapedAt":_iso(row.get("last_audience_scraped_at")),"lastAudienceScrapeStatus":row.get("last_audience_scrape_status"),"lastAudienceRunId":row.get("last_audience_run_id"),"posts7d":row["posts_7d"],"comments7d":row["comments_7d"],"retweets7d":row["retweets_7d"],"quotes7d":row["quotes_7d"],"engagementRate":row.get("engagement_rate"),"audienceCount":row.get("audience_count"),"growth7d":growth(row.get("growth_7d")),"growth30d":growth(row.get("growth_30d")),"refresh":schedule(row.get("last_successful_refresh_at"))}
    return {"items":[item(row) for row in data["items"]],"benchmark":item(data["benchmark"]) if data.get("benchmark") else None,"metrics":{"commenters":summary["commenters"],"retweeters":summary["retweeters"],"quotePosters":summary["quote_posters"],"uniqueLeads":summary["unique_leads"]}}


@router.patch("/competitors/{competitor_id}/telegram-intelligence")
def update_competitor_telegram_intelligence(competitor_id:str,body:CompetitorTelegramIntelligenceRequest):
    try:row=XCompetitorManualIntelligenceService().update_telegram(competitor_id,presence=body.presence,telegram_url=body.telegram_url,audience_type=body.audience_type,comments_allowed=body.comments_allowed,joined=body.joined,scraped=body.scraped)
    except LookupError as error:raise HTTPException(404,str(error)) from error
    except ValueError as error:raise HTTPException(422,str(error)) from error
    return {"presence":row["telegram_presence"],"telegramUrl":row["telegram_url"],"audienceType":row["telegram_audience_type"],"commentsAllowed":row["telegram_comments_allowed"],"joined":row["telegram_joined"],"scraped":bool(row.get("telegram_scraped",False))}

@router.post("/competitors/{competitor_id}/audience-7d/collect")
def collect_audience_7d(competitor_id:str):
    try: run=XCompetitorAudienceService().collect(competitor_id)
    except LookupError as error: raise HTTPException(404,str(error)) from error
    except ValueError as error: raise HTTPException(409,str(error)) from error
    except Exception as error: raise HTTPException(503,"X audience collection is unavailable.") from error
    source=run.get("source_breakdown",{});detail=lambda kind:{"requests":source.get(kind,{}).get("requests",0),"failed":source.get(kind,{}).get("failed",0)}
    return {"runId":str(run["id"]),"status":run["status"],"completedAt":_iso(run.get("completed_at") or run.get("started_at")),"postsConsidered":run["posts_considered"],"postsProcessed":run["posts_processed"],"repliesReturned":run["reply_records_returned"],"retweetersReturned":run["retweeter_records_returned"],"quotesReturned":run["quote_records_returned"],"uniqueUsersObserved":run["unique_users_observed"],"newUsers":run["new_users"],"existingUsers":run["existing_users"],"newSignals":run["new_signals"],"existingSignals":run["existing_signals"],"providerRequests":run["provider_requests"],"failedSources":run["failed_sources"],"sourceBreakdown":{"replies":detail("REPLY"),"retweets":detail("RETWEET"),"quotes":detail("QUOTE")}}

@router.get("/audience-runs/{run_id}/users")
def list_audience_run_users(run_id:str,classification:str=Query(...,pattern="^(NEW|EXISTING)$")):
    repository=XCompetitorAudienceService().repository;run=repository.get_run(run_id)
    if run is None: raise HTTPException(404,"Audience collection run not found.")
    rows=repository.list_run_users(run_id,classification)
    return {"runId":run_id,"classification":classification,"count":len(rows),"users":[{"id":str(row["id"]),"xUserId":row["x_user_id"],"username":row["username"],"displayName":row["display_name"],"profileImageUrl":row["profile_image_url"],"signalTypes":row["signal_types"],"sourcePosts":row["source_posts"],"previousCompetitors":row["previous_competitors"],"knownFrom":row["known_from_display_name"] or row["known_from_username"]} for row in rows]}

@router.get("/audience-runs/{run_id}/diagnostics")
def audience_run_diagnostics(run_id:str):
    service=XCompetitorAudienceService()
    try:run,sources,failures=service.diagnostics(run_id)
    except LookupError as error:raise HTTPException(404,str(error)) from error
    source=lambda kind:{"complete":sources[kind]["complete"],"failed":sources[kind]["failed"]}
    return {"run":{"id":str(run["id"]),"competitorId":str(run["competitor_id"]),"status":run["status"],"startedAt":_iso(run["started_at"]),"completedAt":_iso(run["completed_at"]),"postsConsidered":run["posts_considered"],"postsProcessed":run["posts_processed"],"repliesReturned":run["reply_records_returned"],"retweetersReturned":run["retweeter_records_returned"],"quotesReturned":run["quote_records_returned"],"uniqueUsersObserved":run["unique_users_observed"],"newUsers":run["new_users"],"existingUsers":run["existing_users"],"newSignals":run["new_signals"],"existingSignals":run["existing_signals"],"providerRequests":run["provider_requests"]},"competitor":{"id":str(run["competitor_id"]),"username":run["username"],"displayName":run["display_name"],"profileImageUrl":run["profile_image_url"]},"sourceStatus":{"replies":source("REPLY"),"retweets":source("RETWEET"),"quotes":source("QUOTE")},"failures":[{"sourceType":row["signal_type"],"sourceTweetId":row["x_tweet_id"],"postedAt":_iso(row["posted_at"]),"textPreview":(row["text"][:180] if row.get("text") else None),"pagesCompleted":row["pages_completed"],"reason":row["error_message"]} for row in failures]}

@router.get("/audience/leads")
def list_collected_leads(page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),search:str=Query("",max_length=100),sort:str=Query("account-asc",pattern="^(account|competitors)-(asc|desc)$")):
    repository=XCompetitorAudienceService().repository;rows,total=repository.list_collected_leads(page=page,page_size=page_size,search=search,sort=sort)
    return {"items":[{"id":str(row["id"]),"xUserId":row["x_user_id"],"username":row["username"],"displayName":row["display_name"],"profileImageUrl":row["profile_image_url"],"hasReply":row["has_reply"],"hasRetweet":row["has_retweet"],"hasQuote":row["has_quote"],"competitorCount":row["competitor_count"]} for row in rows],"total":total,"globalTotal":repository.global_audience_summary()["unique_leads"],"page":page,"pageSize":page_size,"search":search,"sort":sort}

@router.get("/audience/leads/usernames")
def list_collected_lead_usernames():
    usernames=XCompetitorAudienceService().repository.list_collected_lead_usernames()
    return {"usernames":usernames,"count":len(usernames)}


@router.get("/audience/leads/export.csv")
def export_collected_leads_csv():
    repository=XCompetitorAudienceService().repository

    def rows():
        buffer=io.StringIO(newline="")
        writer=csv.writer(buffer,lineterminator="\r\n")
        writer.writerow(("username",))
        yield "\ufeff"+buffer.getvalue()
        for username in repository.iter_collected_lead_usernames():
            buffer.seek(0);buffer.truncate(0)
            writer.writerow((username,))
            yield buffer.getvalue()

    filename=f"creator_os_x_leads_{date.today().isoformat()}.csv"
    return StreamingResponse(rows(),media_type="text/csv; charset=utf-8",headers={
      "Content-Disposition":f'attachment; filename="{filename}"',
      "Cache-Control":"no-store",
    })


@router.get("/competitors/{competitor_id}/engagement-7d")
def engagement_7d(competitor_id:str):
    try:competitor,analysis=XCompetitorEngagementService().analyze(competitor_id)
    except LookupError as error:raise HTTPException(404,str(error)) from error
    top=[]
    for row in analysis["top_posts"]:
        item=_post(row);item["followerEngagementRate"]=row["follower_engagement_rate"];top.append(item)
    return {"competitor":{"id":str(competitor["id"]),"username":competitor["username"],"displayName":competitor["display_name"],"profileImageUrl":competitor["profile_image_url"]},"sampleSize":analysis["sample_size"],"followersCount":analysis["followers_count"],"medianFollowerEngagementRate":analysis["median_follower_engagement_rate"],"medianViewedEngagementRate":analysis["median_viewed_engagement_rate"],"medianReachRatio":analysis["median_reach_ratio"],"typical":analysis["typical"],"mix":analysis["mix"],"consistency":analysis["consistency"],"topPosts":top}


@router.get("/competitors/{competitor_id}/posts-7d")
def list_posts_7d(competitor_id: str):
    from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
    repository=XCompetitorIntelligenceRepository();competitor=repository.get(competitor_id)
    if competitor is None: raise HTTPException(status_code=404,detail="Competitor not found.")
    posts=repository.list_posts_7d(competitor_id)
    return {"competitor":{"id":str(competitor["id"]),"username":competitor["username"],"displayName":competitor["display_name"],"profileImageUrl":competitor["profile_image_url"]},"count":len(posts),"posts":[_post(row) for row in posts]}

@router.get("/competitors/{competitor_id}/posts-archived")
def list_archived_posts(competitor_id:str,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100)):
    from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
    repository=XCompetitorIntelligenceRepository();competitor=repository.get(competitor_id)
    if competitor is None: raise HTTPException(404,"Competitor not found.")
    posts,total=repository.list_archived_posts(competitor_id,page=page,page_size=page_size)
    return {"competitor":{"id":str(competitor["id"]),"username":competitor["username"],"displayName":competitor["display_name"],"profileImageUrl":competitor["profile_image_url"]},"count":total,"page":page,"pageSize":page_size,"posts":[_post(row) for row in posts]}

@router.post("/posts/{post_id}/refresh-metrics")
def refresh_archived_metrics(post_id:str,idempotency_key:str=Header(alias="Idempotency-Key",min_length=1,max_length=128)):
    try: post,replay=XCompetitorArchivedPostService().refresh_metrics(post_id,idempotency_key=idempotency_key)
    except LookupError as error: raise HTTPException(404,str(error)) from error
    except ValueError as error: raise HTTPException(409,str(error)) from error
    except Exception as error: raise HTTPException(503,"Archived post metrics could not be refreshed.") from error
    return {"post":_post(post),"idempotentReplay":replay}
