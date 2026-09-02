from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation, UniqueViolation

from app.database import get_db_connection
from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
from app.providers.x_twitterapi_io import ResolvedXActivity, ResolvedXProfile


MIGRATION = Path("migrations/forward/20260816_059_x_competitor_intelligence_foundation.sql")


def test_migration_defines_only_the_four_canonical_x_intelligence_tables():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS x_intelligence" in sql
    for table in ("competitors", "competitor_profile_snapshots", "competitor_posts", "competitor_sync_runs"):
        assert f"CREATE TABLE IF NOT EXISTS x_intelligence.{table}" in sql
    for excluded in ("audience_users", "competitor_followers", "audience_interactions", "competitor_post_snapshots"):
        assert excluded not in sql


def test_schema_constraints_indexes_defaults_and_repository_primitives():
    repository = XCompetitorIntelligenceRepository()
    suffix = uuid4().hex[:10]
    competitor = repository.create_competitor(f"Test_{suffix[:8]}", x_user_id=f"test-user-{suffix}")
    competitor_id = competitor["id"]
    try:
        assert competitor["tracking_enabled"] is True
        assert competitor["watchlisted"] is False
        assert repository.get(competitor_id)["id"] == competitor_id
        assert repository.get_by_x_user_id(f"test-user-{suffix}")["id"] == competitor_id
        assert repository.get_by_username(f"TEST_{suffix[:8].upper()}")["id"] == competitor_id

        first = repository.insert_snapshot(competitor_id, observed_at=datetime(2026, 8, 16, 8, tzinfo=timezone.utc), followers_count=100)
        retry = repository.insert_snapshot(competitor_id, observed_at=datetime(2026, 8, 16, 18, tzinfo=timezone.utc), followers_count=105)
        assert retry["id"] == first["id"]
        assert retry["followers_count"] == 105

        first_post = repository.upsert_post(competitor_id, f"tweet-{suffix}", posted_at=datetime.now(timezone.utc), like_count=2)
        refreshed = repository.upsert_post(competitor_id, f"tweet-{suffix}", posted_at=datetime.now(timezone.utc), like_count=4)
        assert refreshed["id"] == first_post["id"]
        assert refreshed["like_count"] == 4

        run = repository.create_sync_run(competitor_id, "INITIAL")
        assert run["status"] == "QUEUED"
        assert run["posts_returned"] == 0

        with pytest.raises(UniqueViolation), get_db_connection() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO x_intelligence.competitors(id,x_user_id,username) VALUES(%s,%s,%s)", (uuid4(), f"test-user-{suffix}", "OtherUser"))
        with pytest.raises(CheckViolation), get_db_connection() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO x_intelligence.competitor_profile_snapshots(id,competitor_id,observed_at,observation_date,followers_count) VALUES(%s,%s,NOW(),CURRENT_DATE,-1)", (uuid4(), competitor_id))
        with pytest.raises(CheckViolation), get_db_connection() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO x_intelligence.competitor_sync_runs(id,competitor_id,sync_type) VALUES(%s,%s,'DAILY')", (uuid4(), competitor_id))
        with pytest.raises(CheckViolation), get_db_connection() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO x_intelligence.competitor_sync_runs(id,competitor_id,sync_type,status) VALUES(%s,%s,'MANUAL','UNKNOWN')", (uuid4(), competitor_id))
        with pytest.raises(CheckViolation), get_db_connection() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO x_intelligence.competitor_posts(id,competitor_id,x_tweet_id,posted_at,like_count) VALUES(%s,%s,%s,NOW(),-1)", (uuid4(), competitor_id, f"negative-{suffix}"))
        with pytest.raises(UniqueViolation), get_db_connection() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO x_intelligence.competitor_posts(id,competitor_id,x_tweet_id,posted_at) VALUES(%s,%s,%s,NOW())", (uuid4(), competitor_id, f"tweet-{suffix}"))

        with get_db_connection() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT indexname FROM pg_indexes WHERE schemaname='x_intelligence'""")
            indexes = {row["indexname"] for row in cursor.fetchall()}
        assert {"idx_x_intelligence_competitors_username_lower", "idx_x_intelligence_competitors_tracking", "idx_x_intelligence_competitors_watchlist", "idx_x_intelligence_profile_snapshots_observed", "idx_x_intelligence_posts_competitor_posted", "idx_x_intelligence_sync_runs_competitor_started", "idx_x_intelligence_sync_runs_active"}.issubset(indexes)
    finally:
        with get_db_connection() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM x_intelligence.competitors WHERE id=%s", (competitor_id,))


def test_live_schema_has_metric_history_primary_key_and_cascade_foreign_key():
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("""SELECT table_name FROM information_schema.tables WHERE table_schema='x_intelligence' ORDER BY table_name""")
        tables={row["table_name"] for row in cursor.fetchall()}
        foundation={"competitor_post_metric_snapshots", "competitor_posts", "competitor_profile_snapshots", "competitor_sync_runs", "competitors"}
        assert foundation.issubset(tables)
        cursor.execute("""SELECT c.relname table_name, con.contype, con.confdeltype FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='x_intelligence' AND c.relname=ANY(%s) AND con.contype IN ('p','f')""",(list(foundation),))
        constraints = cursor.fetchall()
    assert {row["table_name"] for row in constraints if row["contype"] == "p"} == {"competitors", "competitor_profile_snapshots", "competitor_posts", "competitor_sync_runs", "competitor_post_metric_snapshots"}
    foreign_keys = [row for row in constraints if row["contype"] == "f"]
    assert len(foreign_keys) == 4
    assert all(row["confdeltype"] == "c" for row in foreign_keys)


def test_resolved_profile_refresh_preserves_manual_research_and_daily_snapshot_identity():
    repository=XCompetitorIntelligenceRepository();suffix=uuid4().hex[:10]
    created=repository.create_competitor("OldName",x_user_id=f"refresh-{suffix}",watchlisted=True,shadow=True,telegram_channel="channel",telegram_members=17,telegram_audience_type="MEMBERS",telegram_comments_allowed=True,telegram_joined=True,notes="manual")
    try:
        value=ResolvedXProfile(f"refresh-{suffix}","NewName","New Name",None,None,"provider bio",None,None,True,"Blue",200,10,20,3,4)
        row,existed=repository.persist_resolved_profile(value,observed_at=datetime(2026,8,16,10,tzinfo=timezone.utc));repository.persist_resolved_profile(value,observed_at=datetime(2026,8,16,14,tzinfo=timezone.utc))
        assert existed is True and row["username"]=="NewName"
        refreshed=repository.get(created["id"])
        assert (refreshed["watchlisted"],refreshed["shadow"],refreshed["telegram_channel"],refreshed["telegram_members"],refreshed["telegram_audience_type"],refreshed["telegram_comments_allowed"],refreshed["telegram_joined"],refreshed["notes"])==(True,True,"channel",17,"MEMBERS",True,True,"manual")
        with get_db_connection() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) count FROM x_intelligence.competitor_profile_snapshots WHERE competitor_id=%s",(created["id"],));assert cursor.fetchone()["count"]==1
            cursor.execute("SELECT COUNT(*) count FROM x_intelligence.competitor_sync_runs WHERE competitor_id=%s AND posts_synced=FALSE",(created["id"],));assert cursor.fetchone()["count"]==2
    finally:
        with get_db_connection() as connection,connection.cursor() as cursor: cursor.execute("DELETE FROM x_intelligence.competitors WHERE id=%s",(created["id"],))


def test_latest_activity_upsert_is_idempotent_and_dashboard_derives_max_posted_at():
    repository=XCompetitorIntelligenceRepository();suffix=uuid4().hex[:10]
    created=repository.create_competitor(f"Activity_{suffix[:6]}",x_user_id=f"activity-{suffix}")
    disabled=repository.create_competitor(f"Disabled_{suffix[:6]}",x_user_id=f"disabled-{suffix}",tracking_enabled=False)
    posted_at=datetime.now(timezone.utc)
    activity=ResolvedXActivity(f"activity-tweet-{suffix}",posted_at,"activity",False,False,False,False,like_count=2,view_count=10)
    try:
        assert repository.persist_latest_activity(created["id"],activity) is True
        assert repository.persist_latest_activity(created["id"],activity) is False
        refreshed=ResolvedXActivity(activity.x_tweet_id,posted_at,"updated",False,False,False,False,like_count=7,view_count=30,reply_count=4,retweet_count=3,quote_count=2)
        quote=ResolvedXActivity(f"quote-{suffix}",posted_at-timedelta(days=1),"quote",False,True,False,False,reply_count=5,retweet_count=6,quote_count=7)
        reply=ResolvedXActivity(f"reply-{suffix}",posted_at-timedelta(days=1),"reply",True,False,False,False)
        repost=ResolvedXActivity(f"repost-{suffix}",posted_at-timedelta(days=1),"repost",False,False,True,False)
        boundary=ResolvedXActivity(f"boundary-{suffix}",posted_at-timedelta(days=7),"boundary",False,False,False,False)
        old=ResolvedXActivity(f"old-{suffix}",posted_at-timedelta(days=8),"old",False,False,False,False)
        repository.persist_activity_collection(created["id"],[refreshed,quote,reply,repost,boundary,old],completed_at=posted_at,provider_requests=2)
        repository.persist_activity_collection(disabled["id"],[],completed_at=posted_at,provider_requests=1)
        assert created["id"] in {row["id"] for row in repository.list_tracked_competitors()}
        assert disabled["id"] not in {row["id"] for row in repository.list_tracked_competitors()}
        item=next(row for row in repository.dashboard()["items"] if row["id"]==created["id"])
        assert item["last_active_at"]==posted_at and item["posts_7d"]==2
        assert (item["comments_7d"],item["retweets_7d"],item["quotes_7d"])==(9,9,9)
        disabled_item=next(row for row in repository.dashboard()["items"] if row["id"]==disabled["id"])
        assert disabled_item["posts_7d"]==0
        assert (disabled_item["comments_7d"],disabled_item["retweets_7d"],disabled_item["quotes_7d"])==(None,None,None)
        assert {row["x_tweet_id"] for row in repository.list_posts_7d(created["id"],now=posted_at)}=={activity.x_tweet_id,quote.x_tweet_id,boundary.x_tweet_id}
        with get_db_connection() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) count,MAX(like_count) likes,MAX(view_count) views FROM x_intelligence.competitor_posts WHERE competitor_id=%s",(created["id"],))
            row=cursor.fetchone();assert (row["count"],row["likes"],row["views"])==(6,7,30)
    finally:
        with get_db_connection() as connection,connection.cursor() as cursor: cursor.execute("DELETE FROM x_intelligence.competitors WHERE id IN (%s,%s)",(created["id"],disabled["id"]))


def test_dashboard_distinguishes_empty_filtered_windows_from_true_zero_engagement():
    repository=XCompetitorIntelligenceRepository();suffix=uuid4().hex[:8];now=datetime.now(timezone.utc)
    competitors={
        kind:repository.create_competitor(f"Metric_{kind}_{suffix}",x_user_id=f"metric-{kind}-{suffix}")
        for kind in ("empty","zero","repost","reply")
    }
    try:
        repository.persist_activity_collection(competitors["empty"]["id"],[],completed_at=now,provider_requests=0)
        repository.persist_activity_collection(competitors["zero"]["id"],[ResolvedXActivity(f"zero-{suffix}",now,"zero",False,False,False,False,reply_count=0,retweet_count=0,quote_count=0)],completed_at=now,provider_requests=0)
        repository.persist_activity_collection(competitors["repost"]["id"],[ResolvedXActivity(f"repost-only-{suffix}",now,"repost",False,False,True,False,reply_count=8,retweet_count=5,quote_count=2)],completed_at=now,provider_requests=0)
        repository.persist_activity_collection(competitors["reply"]["id"],[ResolvedXActivity(f"reply-only-{suffix}",now,"reply",True,False,False,False,reply_count=3,retweet_count=2,quote_count=1)],completed_at=now,provider_requests=0)
        rows={str(row["id"]):row for row in repository.dashboard()["items"]}
        empty=rows[str(competitors["empty"]["id"])]
        zero=rows[str(competitors["zero"]["id"])]
        repost=rows[str(competitors["repost"]["id"])]
        reply=rows[str(competitors["reply"]["id"])]
        assert (empty["posts_7d"],empty["comments_7d"],empty["retweets_7d"],empty["quotes_7d"])==(0,None,None,None)
        assert (zero["posts_7d"],zero["comments_7d"],zero["retweets_7d"],zero["quotes_7d"])==(1,0,0,0)
        assert (repost["posts_7d"],repost["comments_7d"],repost["retweets_7d"],repost["quotes_7d"])==(0,None,None,None)
        assert (reply["posts_7d"],reply["comments_7d"],reply["retweets_7d"],reply["quotes_7d"])==(0,None,None,None)
    finally:
        with get_db_connection() as connection,connection.cursor() as cursor:
            cursor.execute("DELETE FROM x_intelligence.competitors WHERE id=ANY(%s)",([row["id"] for row in competitors.values()],))

def test_seven_day_visibility_eight_day_metric_grace_and_historical_freeze():
    repository=XCompetitorIntelligenceRepository();suffix=uuid4().hex[:8];now=datetime.now(timezone.utc)
    competitor=repository.create_competitor(f"Window_{suffix}",x_user_id=f"window-{suffix}")
    recent=ResolvedXActivity(f"recent-{suffix}",now-timedelta(days=6,hours=21),"recent",False,False,False,False,view_count=10)
    grace=ResolvedXActivity(f"grace-{suffix}",now-timedelta(days=7,hours=12),"grace",False,False,False,False,view_count=20)
    frozen=ResolvedXActivity(f"frozen-{suffix}",now-timedelta(days=8,minutes=1),"frozen",False,False,False,False,view_count=30)
    try:
        repository.persist_activity_collection(competitor["id"],[recent,grace,frozen],completed_at=now,provider_requests=2)
        repository.persist_activity_collection(competitor["id"],[ResolvedXActivity(recent.x_tweet_id,recent.posted_at,"recent",False,False,False,False,view_count=11),ResolvedXActivity(grace.x_tweet_id,grace.posted_at,"grace",False,False,False,False,view_count=21),ResolvedXActivity(frozen.x_tweet_id,frozen.posted_at,"frozen",False,False,False,False,view_count=999)],completed_at=now,provider_requests=2)
        assert [row["x_tweet_id"] for row in repository.list_posts_7d(competitor["id"],now=now)]==[recent.x_tweet_id]
        archived,total=repository.list_archived_posts(competitor["id"],now=now);assert total==2 and [row["x_tweet_id"] for row in archived]==[grace.x_tweet_id,frozen.x_tweet_id]
        with get_db_connection() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT id,x_tweet_id,view_count FROM x_intelligence.competitor_posts WHERE competitor_id=%s",(competitor["id"],));post_rows=cursor.fetchall();metrics={row["x_tweet_id"]:row["view_count"] for row in post_rows};frozen_id=next(row["id"] for row in post_rows if row["x_tweet_id"]==frozen.x_tweet_id)
            assert metrics=={recent.x_tweet_id:11,grace.x_tweet_id:21,frozen.x_tweet_id:30}
            cursor.execute("SELECT COUNT(*) count FROM x_intelligence.competitor_post_metric_snapshots s JOIN x_intelligence.competitor_posts p ON p.id=s.competitor_post_id WHERE p.competitor_id=%s",(competitor["id"],));assert cursor.fetchone()["count"]==2
        manual=ResolvedXActivity(frozen.x_tweet_id,frozen.posted_at,"frozen",False,False,False,False,view_count=50)
        repository.persist_manual_metrics(frozen_id,manual,observed_at=now,key="request-1");repository.persist_manual_metrics(frozen_id,manual,observed_at=now,key="request-1");repository.persist_manual_metrics(frozen_id,manual,observed_at=now+timedelta(days=1),key="request-2")
        with get_db_connection() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) count FROM x_intelligence.competitor_post_metric_snapshots WHERE competitor_post_id=%s AND observation_source='MANUAL_ARCHIVED'",(frozen_id,));assert cursor.fetchone()["count"]==2
    finally:
        with get_db_connection() as connection,connection.cursor() as cursor: cursor.execute("DELETE FROM x_intelligence.competitors WHERE id=%s",(competitor["id"],))


def test_effective_refresh_bootstrap_is_shared_by_dashboard_and_scheduler():
    repository=XCompetitorIntelligenceRepository();suffix=uuid4().hex[:8]
    created_at=datetime(2026,8,15,10,tzinfo=timezone.utc)
    profile_at=created_at+timedelta(minutes=1);activity_at=created_at+timedelta(minutes=2)
    canonical_at=datetime(2026,8,17,12,tzinfo=timezone.utc)
    ids={name:uuid4() for name in ("legacy","fallback","canonical","partial")}
    try:
        with get_db_connection() as connection,connection.cursor() as cursor:
            for name,competitor_id in ids.items():
                cursor.execute("INSERT INTO x_intelligence.competitors(id,x_user_id,username,created_at,updated_at) VALUES(%s,%s,%s,%s,%s)",(competitor_id,f"bootstrap-{name}-{suffix}",f"Bootstrap_{name}_{suffix}",created_at,created_at))
                cursor.execute("INSERT INTO x_intelligence.competitor_profile_snapshots(id,competitor_id,observed_at,observation_date,followers_count) VALUES(%s,%s,%s,%s,100)",(uuid4(),competitor_id,profile_at,profile_at.date()))
            cursor.execute("""INSERT INTO x_intelligence.competitor_sync_runs(id,competitor_id,sync_type,status,started_at,completed_at,profile_synced,posts_synced,canonical_refresh)
                VALUES(%s,%s,'INITIAL','SUCCEEDED',%s,%s,TRUE,FALSE,FALSE),(%s,%s,'MANUAL','SUCCEEDED',%s,%s,FALSE,TRUE,FALSE)""",
                (uuid4(),ids["legacy"],profile_at,profile_at,uuid4(),ids["legacy"],activity_at,activity_at))
            cursor.execute("INSERT INTO x_intelligence.competitor_posts(id,competitor_id,x_tweet_id,posted_at) VALUES(%s,%s,%s,%s)",(uuid4(),ids["fallback"],f"fallback-{suffix}",created_at))
            cursor.execute("""INSERT INTO x_intelligence.competitor_sync_runs(id,competitor_id,sync_type,status,started_at,completed_at,profile_synced,posts_synced,canonical_refresh)
                VALUES(%s,%s,'INITIAL','SUCCEEDED',%s,%s,TRUE,FALSE,FALSE),(%s,%s,'WEEKLY','SUCCEEDED',%s,%s,TRUE,TRUE,TRUE)""",
                (uuid4(),ids["canonical"],profile_at,profile_at,uuid4(),ids["canonical"],canonical_at,canonical_at))
            cursor.execute("""INSERT INTO x_intelligence.competitor_sync_runs(id,competitor_id,sync_type,status,started_at,completed_at,profile_synced,posts_synced,canonical_refresh)
                VALUES(%s,%s,'INITIAL','PARTIAL',%s,%s,TRUE,FALSE,FALSE)""",(uuid4(),ids["partial"],profile_at,profile_at))
        items={row["id"]:row for row in repository.dashboard()["items"] if row["id"] in ids.values()}
        assert items[ids["legacy"]]["last_successful_refresh_at"]==activity_at
        assert items[ids["fallback"]]["last_successful_refresh_at"]==created_at
        assert items[ids["canonical"]]["last_successful_refresh_at"]==canonical_at
        assert items[ids["partial"]]["last_successful_refresh_at"] is None
        before=repository.list_due_competitor_refreshes(due_before=activity_at-timedelta(seconds=1),retry_before=canonical_at,limit=100)
        at_boundary=repository.list_due_competitor_refreshes(due_before=activity_at,retry_before=canonical_at,limit=100)
        assert ids["legacy"] not in {row["id"] for row in before}
        assert ids["legacy"] in {row["id"] for row in at_boundary}
        assert next(row for row in at_boundary if row["id"]==ids["legacy"])["last_successful_refresh_at"]==activity_at
    finally:
        with get_db_connection() as connection,connection.cursor() as cursor:
            cursor.execute("DELETE FROM x_intelligence.competitors WHERE id=ANY(%s)",(list(ids.values()),))
