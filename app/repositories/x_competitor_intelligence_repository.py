"""Canonical PostgreSQL primitives for X Competitor Intelligence."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID, uuid4
from psycopg.types.json import Jsonb

from app.database import get_db_connection
from app.services.x_competitor_post_policy import POSTS_VISIBLE_WINDOW,POST_METRIC_AUTO_REFRESH_WINDOW


EFFECTIVE_REFRESH_LATERAL_SQL = """SELECT COALESCE(
    (SELECT MAX(completed_at) FROM x_intelligence.competitor_sync_runs
     WHERE competitor_id=c.id AND canonical_refresh=TRUE AND status='SUCCEEDED'
       AND profile_synced=TRUE AND posts_synced=TRUE),
    (SELECT MAX(completed_at) FROM x_intelligence.competitor_sync_runs
     WHERE competitor_id=c.id AND canonical_refresh=FALSE AND status='SUCCEEDED'
       AND profile_synced=TRUE AND posts_synced=TRUE),
    (SELECT CASE WHEN profile_completed_at IS NOT NULL AND activity_completed_at IS NOT NULL
                 THEN GREATEST(profile_completed_at,activity_completed_at) END
       FROM (SELECT
         MIN(completed_at) FILTER(WHERE status='SUCCEEDED' AND profile_synced=TRUE) AS profile_completed_at,
         MIN(completed_at) FILTER(WHERE status='SUCCEEDED' AND posts_synced=TRUE) AS activity_completed_at
         FROM x_intelligence.competitor_sync_runs WHERE competitor_id=c.id) legacy),
    CASE WHEN EXISTS(SELECT 1 FROM x_intelligence.competitor_profile_snapshots WHERE competitor_id=c.id)
          AND (EXISTS(SELECT 1 FROM x_intelligence.competitor_posts WHERE competitor_id=c.id)
               OR EXISTS(SELECT 1 FROM x_intelligence.competitor_sync_runs
                         WHERE competitor_id=c.id AND status='SUCCEEDED' AND posts_synced=TRUE))
         THEN c.created_at END
) AS last_successful_refresh_at"""


class XCompetitorIntelligenceRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def create_competitor(self, username: str, *, x_user_id: str | None = None, **values: Any) -> Mapping[str, Any]:
        allowed = ("display_name", "profile_image_url", "profile_banner_url", "bio", "location", "account_created_at", "verified", "verification_type", "tracking_enabled", "watchlisted", "shadow", "telegram_channel", "telegram_members", "joined", "allowed_responses", "telegram_presence", "telegram_audience_type", "telegram_comments_allowed", "telegram_joined", "telegram_scraped", "notes", "platform")
        fields = ["id", "x_user_id", "username"] + [key for key in allowed if key in values]
        params = [uuid4(), x_user_id, username] + [values[key] for key in allowed if key in values]
        placeholders = ",".join(["%s"] * len(fields))
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"INSERT INTO x_intelligence.competitors ({','.join(fields)}) VALUES ({placeholders}) RETURNING *", params)
            return dict(cursor.fetchone())

    def upsert_resolved_competitor(self, x_user_id: str, username: str, **values: Any) -> Mapping[str, Any]:
        allowed = ("display_name", "profile_image_url", "profile_banner_url", "bio", "location", "account_created_at", "verified", "verification_type")
        fields = [key for key in allowed if key in values]
        insert_columns = ["id", "x_user_id", "username", *fields]
        params = [uuid4(), x_user_id, username, *[values[key] for key in fields]]
        updates = ["username=EXCLUDED.username", "updated_at=NOW()", *[f"{key}=EXCLUDED.{key}" for key in fields]]
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"INSERT INTO x_intelligence.competitors ({','.join(insert_columns)}) VALUES ({','.join(['%s']*len(params))}) ON CONFLICT (x_user_id) DO UPDATE SET {','.join(updates)} RETURNING *", params)
            return dict(cursor.fetchone())

    def get(self, competitor_id: UUID | str) -> Mapping[str, Any] | None:
        return self._one("SELECT * FROM x_intelligence.competitors WHERE id=%s", (competitor_id,))

    def get_by_x_user_id(self, x_user_id: str) -> Mapping[str, Any] | None:
        return self._one("SELECT * FROM x_intelligence.competitors WHERE x_user_id=%s", (x_user_id,))

    def get_by_username(self, username: str) -> Mapping[str, Any] | None:
        return self._one("SELECT * FROM x_intelligence.competitors WHERE LOWER(username)=LOWER(%s) ORDER BY updated_at DESC LIMIT 1", (username,))

    def classify_own_account(self, competitor_id: UUID | str) -> Mapping[str, Any]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE x_intelligence.competitors
                SET account_role='OWN_ACCOUNT',archived_at=NULL,tracking_enabled=TRUE,updated_at=NOW()
                WHERE id=%s RETURNING *""", (competitor_id,))
            row=cursor.fetchone()
            if row is None:raise LookupError("X Intelligence account not found.")
            return dict(row)

    def archive(self, competitor_id: UUID | str) -> Mapping[str, Any] | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE x_intelligence.competitors
                SET archived_at=COALESCE(archived_at,NOW()),updated_at=NOW()
                WHERE id=%s RETURNING *""", (competitor_id,))
            row=cursor.fetchone();return dict(row) if row else None

    def restore(self, competitor_id: UUID | str) -> Mapping[str, Any] | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE x_intelligence.competitors
                SET archived_at=NULL,updated_at=NOW()
                WHERE id=%s RETURNING *""", (competitor_id,))
            row=cursor.fetchone();return dict(row) if row else None

    def list_archived(self) -> list[Mapping[str, Any]]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT c.id,c.x_user_id,c.username,c.display_name,c.profile_image_url,
                c.archived_at,c.platform,s.followers_count
                FROM x_intelligence.competitors c
                LEFT JOIN LATERAL (SELECT followers_count FROM x_intelligence.competitor_profile_snapshots
                    WHERE competitor_id=c.id ORDER BY observed_at DESC,id DESC LIMIT 1) s ON TRUE
                WHERE c.account_role='COMPETITOR' AND c.archived_at IS NOT NULL
                ORDER BY c.archived_at DESC,c.id""")
            return [dict(row) for row in cursor.fetchall()]

    def update_archived_resolved_profile(self, competitor_id: UUID | str, profile: Any) -> Mapping[str, Any] | None:
        """Refresh identity metadata after a re-add lookup without collecting intelligence."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE x_intelligence.competitors SET
                username=%s,display_name=%s,profile_image_url=%s,profile_banner_url=%s,bio=%s,
                location=%s,account_created_at=%s,verified=%s,verification_type=%s,updated_at=NOW()
                WHERE id=%s AND archived_at IS NOT NULL RETURNING *""",
                (profile.username,profile.display_name,profile.profile_image_url,profile.profile_banner_url,
                 profile.bio,profile.location,profile.account_created_at,profile.verified,
                 profile.verification_type,competitor_id))
            row=cursor.fetchone();return dict(row) if row else None

    def update_manual_telegram_intelligence(self, competitor_id: UUID | str, *, presence: str, telegram_url: str | None, audience_type: str | None, comments_allowed: bool | None, joined: bool | None, scraped: bool | None = None) -> Mapping[str, Any] | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE x_intelligence.competitors
                SET telegram_presence=%s,telegram_url=%s,telegram_audience_type=%s,telegram_comments_allowed=%s,telegram_joined=%s,telegram_scraped=COALESCE(%s,telegram_scraped),updated_at=NOW()
                WHERE id=%s RETURNING *""",(presence,telegram_url,audience_type,comments_allowed,joined,scraped,competitor_id))
            row=cursor.fetchone();return dict(row) if row else None

    def insert_snapshot(self, competitor_id: UUID | str, *, observed_at: datetime, followers_count: int, following_count: int | None = None, statuses_count: int | None = None, media_count: int | None = None, favorites_count: int | None = None) -> Mapping[str, Any]:
        observed = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc)
        observation_date: date = observed.astimezone(timezone.utc).date()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO x_intelligence.competitor_profile_snapshots(id,competitor_id,observed_at,observation_date,followers_count,following_count,statuses_count,media_count,favorites_count) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(competitor_id,observation_date) DO UPDATE SET observed_at=EXCLUDED.observed_at,followers_count=EXCLUDED.followers_count,following_count=EXCLUDED.following_count,statuses_count=EXCLUDED.statuses_count,media_count=EXCLUDED.media_count,favorites_count=EXCLUDED.favorites_count RETURNING *""", (uuid4(),competitor_id,observed,observation_date,followers_count,following_count,statuses_count,media_count,favorites_count))
            return dict(cursor.fetchone())

    def upsert_post(self, competitor_id: UUID | str, x_tweet_id: str, *, posted_at: datetime, text: str | None = None, media_metadata: list[Mapping[str, Any]] | None = None, **values: Any) -> Mapping[str, Any]:
        allowed = ("language", "conversation_id", "is_reply", "is_quote", "is_retweet", "has_media", "like_count", "reply_count", "retweet_count", "quote_count", "view_count", "bookmark_count")
        fields = [key for key in allowed if key in values]
        columns = ["id", "competitor_id", "x_tweet_id", "posted_at", "text", "media_metadata", *fields]
        params = [uuid4(), competitor_id, x_tweet_id, posted_at, text, Jsonb(media_metadata or []), *[values[key] for key in fields]]
        updates = ["competitor_id=EXCLUDED.competitor_id", "posted_at=EXCLUDED.posted_at", "text=EXCLUDED.text", "media_metadata=EXCLUDED.media_metadata", "last_refreshed_at=NOW()", "updated_at=NOW()", *[f"{key}=EXCLUDED.{key}" for key in fields]]
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"INSERT INTO x_intelligence.competitor_posts ({','.join(columns)}) VALUES ({','.join(['%s']*len(params))}) ON CONFLICT(x_tweet_id) DO UPDATE SET {','.join(updates)} RETURNING *", params)
            return dict(cursor.fetchone())

    def create_sync_run(self, competitor_id: UUID | str, sync_type: str, *, provider: str | None = None, estimated_cost: Decimal | None = None) -> Mapping[str, Any]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO x_intelligence.competitor_sync_runs(id,competitor_id,sync_type,provider,estimated_cost) VALUES(%s,%s,%s,%s,%s) RETURNING *", (uuid4(),competitor_id,sync_type,provider,estimated_cost))
            return dict(cursor.fetchone())

    def begin_global_refresh(self, refresh_type: str, *, started_at: datetime) -> Mapping[str, Any]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO x_intelligence.global_refresh_runs(id,refresh_type,started_at) VALUES(%s,%s,%s) RETURNING *",(uuid4(),refresh_type,started_at))
            return dict(cursor.fetchone())

    def finish_global_refresh(self, run_id: UUID | str, *, status: str, completed_at: datetime, considered: int, succeeded: int, failed: int, error_message: str | None = None) -> Mapping[str, Any]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE x_intelligence.global_refresh_runs SET status=%s,completed_at=%s,considered=%s,succeeded=%s,failed=%s,error_message=%s WHERE id=%s RETURNING *""",(status,completed_at,considered,succeeded,failed,error_message,run_id))
            return dict(cursor.fetchone())

    def list_tracked_competitors(self) -> list[Mapping[str, Any]]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT id,x_user_id,username,account_role FROM x_intelligence.competitors WHERE tracking_enabled=TRUE AND archived_at IS NULL ORDER BY created_at,id")
            return [dict(row) for row in cursor.fetchall()]

    def claim_competitor_refresh(self, competitor_id: UUID | str, *, sync_type: str, started_at: datetime) -> Mapping[str, Any] | None:
        """Atomically claim one combined Profile + Activity refresh."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE x_intelligence.competitor_sync_runs
                SET status='FAILED',completed_at=%s,error_code='STALE_REFRESH_CLAIM',error_message='Refresh worker claim expired before completion.'
                WHERE competitor_id=%s AND canonical_refresh=TRUE AND status='RUNNING'
                  AND started_at<=%s-(INTERVAL '30 minutes')""",(started_at,competitor_id,started_at))
            cursor.execute("""INSERT INTO x_intelligence.competitor_sync_runs
                (id,competitor_id,sync_type,status,started_at,canonical_refresh,profile_synced,posts_synced,provider)
                SELECT %s,%s,%s,'RUNNING',%s,TRUE,
                    COALESCE(previous.profile_synced,FALSE),COALESCE(previous.posts_synced,FALSE),'TWITTERAPI_IO'
                FROM (SELECT 1) seed LEFT JOIN LATERAL (
                    SELECT failed.profile_synced,failed.posts_synced FROM x_intelligence.competitor_sync_runs failed
                    WHERE failed.competitor_id=%s AND failed.canonical_refresh=TRUE AND failed.status='FAILED'
                      AND NOT EXISTS(SELECT 1 FROM x_intelligence.competitor_sync_runs success
                          WHERE success.competitor_id=failed.competitor_id AND success.status='SUCCEEDED'
                            AND success.profile_synced=TRUE AND success.posts_synced=TRUE
                            AND success.completed_at>failed.completed_at)
                    ORDER BY failed.completed_at DESC NULLS LAST LIMIT 1
                ) previous ON TRUE
                WHERE EXISTS(SELECT 1 FROM x_intelligence.competitors WHERE id=%s AND tracking_enabled=TRUE AND archived_at IS NULL)
                ON CONFLICT (competitor_id) WHERE status='RUNNING' AND canonical_refresh DO NOTHING
                RETURNING *""",(uuid4(),competitor_id,sync_type,started_at,competitor_id,competitor_id))
            row=cursor.fetchone();return dict(row) if row else None

    def fail_refresh(self, run_id: UUID | str, *, completed_at: datetime, error_code: str, error_message: str) -> None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE x_intelligence.competitor_sync_runs
                SET status='FAILED',completed_at=%s,error_code=%s,error_message=%s
                WHERE id=%s AND status='RUNNING'""",(completed_at,error_code,error_message,run_id))

    def complete_competitor_refresh(self, run_id: UUID | str, *, completed_at: datetime) -> Mapping[str, Any]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE x_intelligence.competitor_sync_runs
                SET status='SUCCEEDED',completed_at=%s,error_code=NULL,error_message=NULL
                WHERE id=%s AND status='RUNNING' AND canonical_refresh=TRUE
                  AND profile_synced=TRUE AND posts_synced=TRUE RETURNING *""",(completed_at,run_id))
            row=cursor.fetchone()
            if row is None:raise RuntimeError("Combined competitor refresh is incomplete.")
            return dict(row)

    def list_due_competitor_refreshes(self, *, due_before: datetime, retry_before: datetime, limit: int) -> list[Mapping[str, Any]]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"""SELECT c.id,c.x_user_id,c.username,refresh.last_successful_refresh_at
                FROM x_intelligence.competitors c
                LEFT JOIN LATERAL ({EFFECTIVE_REFRESH_LATERAL_SQL}) refresh ON TRUE
                LEFT JOIN LATERAL (
                  SELECT completed_at FROM x_intelligence.competitor_sync_runs
                  WHERE competitor_id=c.id AND status='FAILED' AND canonical_refresh=TRUE
                  ORDER BY completed_at DESC NULLS LAST LIMIT 1
                ) last_failure ON TRUE
                WHERE c.tracking_enabled=TRUE AND c.archived_at IS NULL
                  AND (refresh.last_successful_refresh_at IS NULL OR refresh.last_successful_refresh_at<=%s)
                  AND (last_failure.completed_at IS NULL OR last_failure.completed_at<=%s)
                  AND NOT EXISTS(SELECT 1 FROM x_intelligence.competitor_sync_runs active
                      WHERE active.competitor_id=c.id AND active.canonical_refresh=TRUE AND active.status='RUNNING'
                        AND active.started_at>%s)
                ORDER BY refresh.last_successful_refresh_at ASC NULLS FIRST,c.created_at,c.id LIMIT %s""",
                (due_before,retry_before,retry_before,max(1,int(limit))))
            return [dict(row) for row in cursor.fetchall()]

    def persist_latest_activity(self, competitor_id: UUID | str, activity: Any) -> bool:
        """Upsert one observed timeline activity; return whether Last Active advanced."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT MAX(posted_at) AS last_active_at FROM x_intelligence.competitor_posts WHERE competitor_id=%s",(competitor_id,))
            previous = cursor.fetchone()["last_active_at"]
            cursor.execute("""INSERT INTO x_intelligence.competitor_posts
                (id,competitor_id,x_tweet_id,posted_at,text,is_reply,is_quote,is_retweet,has_media,media_metadata)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(x_tweet_id) DO UPDATE SET competitor_id=EXCLUDED.competitor_id,posted_at=EXCLUDED.posted_at,text=EXCLUDED.text,
                is_reply=EXCLUDED.is_reply,is_quote=EXCLUDED.is_quote,is_retweet=EXCLUDED.is_retweet,has_media=EXCLUDED.has_media,last_refreshed_at=NOW(),updated_at=NOW()
                RETURNING posted_at""",(uuid4(),competitor_id,activity.x_tweet_id,activity.posted_at,activity.text,activity.is_reply,activity.is_quote,activity.is_retweet,activity.has_media,Jsonb([])))
            current = cursor.fetchone()["posted_at"]
            return previous is None or current > previous

    def persist_activity_collection(self, competitor_id: UUID | str, activities: list[Any], *, completed_at: datetime, provider_requests: int, sync_type: str = "MANUAL", run_id: UUID | str | None = None) -> bool:
        """Atomically refresh observed timeline rows and mark the 7-day dataset established."""
        observed=completed_at if completed_at.tzinfo else completed_at.replace(tzinfo=timezone.utc)
        ids=[item.x_tweet_id for item in activities]
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT MAX(posted_at) AS value FROM x_intelligence.competitor_posts WHERE competitor_id=%s",(competitor_id,));previous=cursor.fetchone()["value"]
            existing=set()
            if ids:
                cursor.execute("SELECT x_tweet_id FROM x_intelligence.competitor_posts WHERE x_tweet_id=ANY(%s)",(ids,));existing={row["x_tweet_id"] for row in cursor.fetchall()}
            metric_cutoff=observed-POST_METRIC_AUTO_REFRESH_WINDOW
            for item in activities:
                cursor.execute("SELECT id,posted_at FROM x_intelligence.competitor_posts WHERE x_tweet_id=%s FOR UPDATE",(item.x_tweet_id,));stored=cursor.fetchone()
                # Hard invariant: normal timeline refresh never mutates metrics once >8 days.
                if stored is not None and stored["posted_at"]<metric_cutoff: continue
                cursor.execute("""INSERT INTO x_intelligence.competitor_posts
                    (id,competitor_id,x_tweet_id,posted_at,text,language,conversation_id,is_reply,is_quote,is_retweet,has_media,media_metadata,like_count,reply_count,retweet_count,quote_count,view_count,bookmark_count)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(x_tweet_id) DO UPDATE SET competitor_id=EXCLUDED.competitor_id,posted_at=EXCLUDED.posted_at,text=EXCLUDED.text,language=EXCLUDED.language,
                    conversation_id=EXCLUDED.conversation_id,is_reply=EXCLUDED.is_reply,is_quote=EXCLUDED.is_quote,is_retweet=EXCLUDED.is_retweet,has_media=EXCLUDED.has_media,
                    media_metadata=EXCLUDED.media_metadata,like_count=EXCLUDED.like_count,reply_count=EXCLUDED.reply_count,retweet_count=EXCLUDED.retweet_count,
                    quote_count=EXCLUDED.quote_count,view_count=EXCLUDED.view_count,bookmark_count=EXCLUDED.bookmark_count,last_refreshed_at=NOW(),updated_at=NOW()""",
                    (uuid4(),competitor_id,item.x_tweet_id,item.posted_at,item.text,item.language,item.conversation_id,item.is_reply,item.is_quote,item.is_retweet,item.has_media,Jsonb(list(item.media_metadata)),item.like_count,item.reply_count,item.retweet_count,item.quote_count,item.view_count,item.bookmark_count))
                if item.posted_at>=metric_cutoff and not item.is_reply and not item.is_retweet:
                    cursor.execute("SELECT id FROM x_intelligence.competitor_posts WHERE x_tweet_id=%s",(item.x_tweet_id,));post_id=cursor.fetchone()["id"]
                    cursor.execute("""INSERT INTO x_intelligence.competitor_post_metric_snapshots(id,competitor_post_id,observed_at,observation_source,observation_key,view_count,like_count,reply_count,retweet_count,quote_count,bookmark_count)
                        VALUES(%s,%s,%s,'AUTO_RECENT',%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(competitor_post_id,observation_source,observation_key) DO UPDATE SET observed_at=EXCLUDED.observed_at,view_count=EXCLUDED.view_count,like_count=EXCLUDED.like_count,reply_count=EXCLUDED.reply_count,retweet_count=EXCLUDED.retweet_count,quote_count=EXCLUDED.quote_count,bookmark_count=EXCLUDED.bookmark_count""",
                        (uuid4(),post_id,observed,f"utc-day:{observed.astimezone(timezone.utc).date()}",item.view_count,item.like_count,item.reply_count,item.retweet_count,item.quote_count,item.bookmark_count))
            if sync_type == "INITIAL":
                cursor.execute("""UPDATE x_intelligence.competitor_sync_runs SET status='SUCCEEDED',completed_at=%s,posts_synced=TRUE,
                    posts_returned=%s,new_posts=%s,existing_posts=%s,provider_requests=provider_requests+%s
                    WHERE id=(SELECT id FROM x_intelligence.competitor_sync_runs WHERE competitor_id=%s AND sync_type='INITIAL' ORDER BY created_at DESC LIMIT 1)""",
                    (observed,len(activities),len(ids)-len(existing),len(existing),provider_requests,competitor_id))
            elif run_id is not None:
                cursor.execute("""UPDATE x_intelligence.competitor_sync_runs SET posts_synced=TRUE,
                    posts_returned=%s,new_posts=%s,existing_posts=%s,provider_requests=%s,error_code=NULL,error_message=NULL
                    WHERE id=%s AND status='RUNNING'""",
                    (len(activities),len(ids)-len(existing),len(existing),provider_requests,run_id))
            else:
                cursor.execute("""INSERT INTO x_intelligence.competitor_sync_runs
                    (id,competitor_id,sync_type,status,started_at,completed_at,profile_synced,posts_synced,posts_returned,new_posts,existing_posts,provider,provider_requests)
                    VALUES(%s,%s,'MANUAL','SUCCEEDED',%s,%s,FALSE,TRUE,%s,%s,%s,'TWITTERAPI_IO',%s)""",
                    (uuid4(),competitor_id,observed,observed,len(activities),len(ids)-len(existing),len(existing),provider_requests))
            current=max((item.posted_at for item in activities),default=previous)
            return previous is None and current is not None or previous is not None and current is not None and current>previous

    def mark_initial_activity_failed(self, competitor_id: UUID | str, *, completed_at: datetime, provider_requests: int, error_code: str) -> None:
        observed=completed_at if completed_at.tzinfo else completed_at.replace(tzinfo=timezone.utc)
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""UPDATE x_intelligence.competitor_sync_runs SET status='PARTIAL',completed_at=%s,posts_synced=FALSE,
                provider_requests=provider_requests+%s,error_code=%s,error_message='Initial activity collection needs refresh.'
                WHERE id=(SELECT id FROM x_intelligence.competitor_sync_runs WHERE competitor_id=%s AND sync_type='INITIAL' ORDER BY created_at DESC LIMIT 1)""",
                (observed,provider_requests,error_code,competitor_id))

    def list_posts_7d(self, competitor_id: UUID | str, *, now: datetime | None = None) -> list[Mapping[str, Any]]:
        boundary=(now or datetime.now(timezone.utc))-POSTS_VISIBLE_WINDOW
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT id,x_tweet_id,text,posted_at,language,conversation_id,is_quote,has_media,media_metadata,
                view_count,like_count,reply_count,retweet_count,quote_count,bookmark_count
                FROM x_intelligence.competitor_posts WHERE competitor_id=%s AND posted_at>=%s AND is_reply=FALSE AND is_retweet=FALSE
                ORDER BY posted_at DESC,x_tweet_id""",(competitor_id,boundary))
            return [dict(row) for row in cursor.fetchall()]

    def list_all_posts_7d(self, *, now: datetime | None = None) -> dict[str,list[Mapping[str,Any]]]:
        boundary=(now or datetime.now(timezone.utc))-POSTS_VISIBLE_WINDOW
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT id,competitor_id,x_tweet_id,text,posted_at,language,conversation_id,is_quote,has_media,media_metadata,
                view_count,like_count,reply_count,retweet_count,quote_count,bookmark_count
                FROM x_intelligence.competitor_posts WHERE posted_at>=%s AND is_reply=FALSE AND is_retweet=FALSE ORDER BY competitor_id,posted_at DESC,x_tweet_id""",(boundary,))
            grouped:dict[str,list[Mapping[str,Any]]]={}
            for row in cursor.fetchall():item=dict(row);grouped.setdefault(str(item["competitor_id"]),[]).append(item)
            return grouped

    def latest_followers(self,competitor_id:UUID|str)->int|None:
        row=self._one("SELECT followers_count FROM x_intelligence.competitor_profile_snapshots WHERE competitor_id=%s ORDER BY observed_at DESC LIMIT 1",(competitor_id,))
        return row["followers_count"] if row else None

    def list_profile_snapshot_histories(self)->dict[str,list[Mapping[str,Any]]]:
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT id,competitor_id,observed_at,followers_count FROM x_intelligence.competitor_profile_snapshots ORDER BY competitor_id,observed_at,id")
            grouped:dict[str,list[Mapping[str,Any]]]={}
            for row in cursor.fetchall():item=dict(row);grouped.setdefault(str(item["competitor_id"]),[]).append(item)
            return grouped

    def posts_7d_established(self,competitor_id:UUID|str)->bool:
        return self._one("SELECT id FROM x_intelligence.competitor_sync_runs WHERE competitor_id=%s AND posts_synced=TRUE AND status='SUCCEEDED' ORDER BY completed_at DESC LIMIT 1",(competitor_id,)) is not None

    def list_archived_posts(self,competitor_id:UUID|str,*,page:int=1,page_size:int=25,now:datetime|None=None)->tuple[list[Mapping[str,Any]],int]:
        boundary=(now or datetime.now(timezone.utc))-POSTS_VISIBLE_WINDOW;offset=(page-1)*page_size
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) count FROM x_intelligence.competitor_posts WHERE competitor_id=%s AND posted_at<%s AND is_reply=FALSE AND is_retweet=FALSE",(competitor_id,boundary));total=int(cursor.fetchone()["count"])
            cursor.execute("""SELECT id,x_tweet_id,text,posted_at,language,conversation_id,is_quote,has_media,media_metadata,view_count,like_count,reply_count,retweet_count,quote_count,bookmark_count,last_refreshed_at
                FROM x_intelligence.competitor_posts WHERE competitor_id=%s AND posted_at<%s AND is_reply=FALSE AND is_retweet=FALSE ORDER BY posted_at DESC,x_tweet_id LIMIT %s OFFSET %s""",(competitor_id,boundary,page_size,offset))
            return [dict(row) for row in cursor.fetchall()],total

    def get_post_with_competitor(self,post_id:UUID|str)->Mapping[str,Any]|None:
        return self._one("SELECT p.*,c.username,c.display_name,c.profile_image_url FROM x_intelligence.competitor_posts p JOIN x_intelligence.competitors c ON c.id=p.competitor_id WHERE p.id=%s",(post_id,))

    def has_manual_snapshot(self,post_id:UUID|str,key:str)->bool:
        return self._one("SELECT id FROM x_intelligence.competitor_post_metric_snapshots WHERE competitor_post_id=%s AND observation_source='MANUAL_ARCHIVED' AND observation_key=%s",(post_id,key)) is not None

    def persist_manual_metrics(self,post_id:UUID|str,activity:Any,*,observed_at:datetime,key:str)->Mapping[str,Any]:
        observed=observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc)
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT competitor_id,x_tweet_id FROM x_intelligence.competitor_posts WHERE id=%s FOR UPDATE",(post_id,));post=cursor.fetchone()
            if post is None: raise LookupError("Competitor post not found.")
            if post["x_tweet_id"]!=activity.x_tweet_id: raise ValueError("Tweet identity mismatch.")
            cursor.execute("""UPDATE x_intelligence.competitor_posts SET view_count=%s,like_count=%s,reply_count=%s,retweet_count=%s,quote_count=%s,bookmark_count=%s,last_refreshed_at=%s,updated_at=NOW() WHERE id=%s RETURNING *""",(activity.view_count,activity.like_count,activity.reply_count,activity.retweet_count,activity.quote_count,activity.bookmark_count,observed,post_id));updated=dict(cursor.fetchone())
            cursor.execute("""INSERT INTO x_intelligence.competitor_post_metric_snapshots(id,competitor_post_id,observed_at,observation_source,observation_key,view_count,like_count,reply_count,retweet_count,quote_count,bookmark_count)
                VALUES(%s,%s,%s,'MANUAL_ARCHIVED',%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(competitor_post_id,observation_source,observation_key) DO NOTHING""",(uuid4(),post_id,observed,key,activity.view_count,activity.like_count,activity.reply_count,activity.retweet_count,activity.quote_count,activity.bookmark_count))
            cursor.execute("""INSERT INTO x_intelligence.competitor_sync_runs(id,competitor_id,sync_type,status,started_at,completed_at,profile_synced,posts_synced,provider,provider_requests) VALUES(%s,%s,'MANUAL','SUCCEEDED',%s,%s,FALSE,FALSE,'TWITTERAPI_IO',1)""",(uuid4(),post["competitor_id"],observed,observed))
            return updated

    def persist_resolved_profile(self, profile: Any, *, observed_at: datetime,
                                 platform: str = "FANVUE") -> tuple[Mapping[str, Any], bool]:
        """Atomically upsert provider identity, today's snapshot, and INITIAL sync audit."""
        observed = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc)
        observation_date = observed.astimezone(timezone.utc).date()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT id FROM x_intelligence.competitors WHERE x_user_id=%s", (profile.x_user_id,))
            existing = cursor.fetchone(); already_tracked = existing is not None
            cursor.execute("""INSERT INTO x_intelligence.competitors(id,x_user_id,username,display_name,profile_image_url,profile_banner_url,bio,location,account_created_at,verified,verification_type,platform)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(x_user_id) DO UPDATE SET username=EXCLUDED.username,display_name=EXCLUDED.display_name,profile_image_url=EXCLUDED.profile_image_url,profile_banner_url=EXCLUDED.profile_banner_url,bio=EXCLUDED.bio,location=EXCLUDED.location,account_created_at=EXCLUDED.account_created_at,verified=EXCLUDED.verified,verification_type=EXCLUDED.verification_type,updated_at=NOW() RETURNING *""",
                (uuid4(),profile.x_user_id,profile.username,profile.display_name,profile.profile_image_url,profile.profile_banner_url,profile.bio,profile.location,profile.account_created_at,profile.verified,profile.verification_type,platform))
            competitor = dict(cursor.fetchone()); competitor_id = competitor["id"]
            cursor.execute("""INSERT INTO x_intelligence.competitor_profile_snapshots(id,competitor_id,observed_at,observation_date,followers_count,following_count,statuses_count,media_count,favorites_count)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(competitor_id,observation_date) DO UPDATE SET observed_at=EXCLUDED.observed_at,followers_count=EXCLUDED.followers_count,following_count=EXCLUDED.following_count,statuses_count=EXCLUDED.statuses_count,media_count=EXCLUDED.media_count,favorites_count=EXCLUDED.favorites_count""",
                (uuid4(),competitor_id,observed,observation_date,profile.followers_count,profile.following_count,profile.statuses_count,profile.media_count,profile.favorites_count))
            cursor.execute("""INSERT INTO x_intelligence.competitor_sync_runs(id,competitor_id,sync_type,status,started_at,completed_at,profile_synced,posts_synced,provider,provider_requests)
                VALUES(%s,%s,'INITIAL','RUNNING',%s,NULL,TRUE,FALSE,'TWITTERAPI_IO',1)""", (uuid4(),competitor_id,observed))
            return competitor, already_tracked

    def persist_profile_refresh(self,competitor_id:UUID|str,profile:Any,*,observed_at:datetime,run_id:UUID|str|None=None)->Mapping[str,Any]:
        """Update provider-owned profile facts and upsert the canonical UTC daily observation."""
        observed=observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc);observation_date=observed.astimezone(timezone.utc).date()
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""UPDATE x_intelligence.competitors SET username=%s,display_name=%s,profile_image_url=%s,profile_banner_url=%s,bio=%s,location=%s,
                account_created_at=%s,verified=%s,verification_type=%s,updated_at=NOW() WHERE id=%s RETURNING *""",
                (profile.username,profile.display_name,profile.profile_image_url,profile.profile_banner_url,profile.bio,profile.location,profile.account_created_at,profile.verified,profile.verification_type,competitor_id));competitor=cursor.fetchone()
            if competitor is None:raise LookupError("Competitor not found.")
            cursor.execute("""INSERT INTO x_intelligence.competitor_profile_snapshots(id,competitor_id,observed_at,observation_date,followers_count,following_count,statuses_count,media_count,favorites_count)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(competitor_id,observation_date) DO UPDATE SET observed_at=EXCLUDED.observed_at,followers_count=EXCLUDED.followers_count,
                following_count=EXCLUDED.following_count,statuses_count=EXCLUDED.statuses_count,media_count=EXCLUDED.media_count,favorites_count=EXCLUDED.favorites_count""",
                (uuid4(),competitor_id,observed,observation_date,profile.followers_count,profile.following_count,profile.statuses_count,profile.media_count,profile.favorites_count))
            if run_id is not None:
                cursor.execute("""UPDATE x_intelligence.competitor_sync_runs SET profile_synced=TRUE,
                    provider_requests=1,error_code=NULL,error_message=NULL WHERE id=%s AND status='RUNNING'""",(run_id,))
            else:
                cursor.execute("""INSERT INTO x_intelligence.competitor_sync_runs(id,competitor_id,sync_type,status,started_at,completed_at,profile_synced,posts_synced,provider,provider_requests)
                    VALUES(%s,%s,'MANUAL','SUCCEEDED',%s,%s,TRUE,FALSE,'TWITTERAPI_IO',1)""",(uuid4(),competitor_id,observed,observed))
            return dict(competitor)

    def dashboard(self) -> Mapping[str, Any]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"""SELECT c.id,c.x_user_id,c.username,c.display_name,c.profile_image_url,c.tracking_enabled,c.account_role,c.platform,c.created_at,c.updated_at,
                c.telegram_presence,c.telegram_url,c.telegram_audience_type,c.telegram_comments_allowed,c.telegram_joined,c.telegram_scraped,s.followers_count,s.observed_at,p.last_active_at,
                refresh.last_successful_refresh_at,
                CASE WHEN sync.posts_7d_established THEN p.posts_7d ELSE NULL END AS posts_7d,
                CASE WHEN p.posts_7d > 0 THEN p.comments_7d ELSE NULL END AS comments_7d,
                CASE WHEN p.posts_7d > 0 THEN p.retweets_7d ELSE NULL END AS retweets_7d,
                CASE WHEN p.posts_7d > 0 THEN p.quotes_7d ELSE NULL END AS quotes_7d
                FROM x_intelligence.competitors c LEFT JOIN LATERAL (
                  SELECT followers_count,observed_at FROM x_intelligence.competitor_profile_snapshots WHERE competitor_id=c.id ORDER BY observed_at DESC LIMIT 1
                ) s ON TRUE LEFT JOIN LATERAL (
                  SELECT MAX(posted_at) AS last_active_at,
                    COUNT(*) FILTER(WHERE posted_at>=NOW()-(%s * INTERVAL '1 second') AND is_reply=FALSE AND is_retweet=FALSE)::INTEGER AS posts_7d,
                    COALESCE(SUM(reply_count) FILTER(WHERE posted_at>=NOW()-(%s * INTERVAL '1 second') AND is_reply=FALSE AND is_retweet=FALSE),0)::BIGINT AS comments_7d,
                    COALESCE(SUM(retweet_count) FILTER(WHERE posted_at>=NOW()-(%s * INTERVAL '1 second') AND is_reply=FALSE AND is_retweet=FALSE),0)::BIGINT AS retweets_7d,
                    COALESCE(SUM(quote_count) FILTER(WHERE posted_at>=NOW()-(%s * INTERVAL '1 second') AND is_reply=FALSE AND is_retweet=FALSE),0)::BIGINT AS quotes_7d
                    FROM x_intelligence.competitor_posts WHERE competitor_id=c.id
                ) p ON TRUE LEFT JOIN LATERAL (
                  SELECT EXISTS(SELECT 1 FROM x_intelligence.competitor_sync_runs WHERE competitor_id=c.id AND posts_synced=TRUE AND status='SUCCEEDED') AS posts_7d_established
                ) sync ON TRUE LEFT JOIN LATERAL ({EFFECTIVE_REFRESH_LATERAL_SQL}) refresh ON TRUE
                WHERE c.archived_at IS NULL
                ORDER BY LOWER(c.username)""",(int(POSTS_VISIBLE_WINDOW.total_seconds()),)*4)
            items = [dict(row) for row in cursor.fetchall()]
        tracked = [item for item in items if item["tracking_enabled"] and item["account_role"] == "COMPETITOR"]
        return {"items": items, "tracked": len(tracked), "total_followers": sum(int(item["followers_count"] or 0) for item in tracked)}

    def _one(self, sql: str, params: tuple[Any, ...]) -> Mapping[str, Any] | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(sql, params); row = cursor.fetchone(); return dict(row) if row else None
