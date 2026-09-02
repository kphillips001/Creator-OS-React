"""Durable, globally deduplicated X audience persistence."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app.database import get_db_connection

class XCompetitorAudienceRepository:
    def __init__(self, connection_factory=get_db_connection): self.connection_factory=connection_factory

    def audience_counts(self):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT c.id, CASE WHEN COUNT(DISTINCT s.audience_user_id)>0 OR BOOL_OR(r.status='SUCCEEDED') THEN COUNT(DISTINCT s.audience_user_id) ELSE NULL END AS audience_count
              FROM x_intelligence.competitors c LEFT JOIN x_intelligence.audience_signals s ON s.competitor_id=c.id
              LEFT JOIN x_intelligence.audience_collection_runs r ON r.competitor_id=c.id GROUP BY c.id""")
            return {str(row["id"]):row["audience_count"] for row in cursor.fetchall()}

    def latest_collection_runs(self):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT DISTINCT ON (competitor_id) id,competitor_id,status,created_at,started_at,completed_at
              FROM x_intelligence.audience_collection_runs
              ORDER BY competitor_id,created_at DESC,started_at DESC NULLS LAST,id DESC""")
            return {str(row["competitor_id"]):dict(row) for row in cursor.fetchall()}

    def get_run_diagnostics(self, run_id):
        """Read one persisted collection run and all source progress/post context."""
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT r.*,c.username,c.display_name,c.profile_image_url
              FROM x_intelligence.audience_collection_runs r
              JOIN x_intelligence.competitors c ON c.id=r.competitor_id
              WHERE r.id=%s""",(run_id,))
            run=cursor.fetchone()
            if not run:return None,[]
            cursor.execute("""SELECT p.id,p.signal_type,p.status,p.pages_completed,p.provider_requests,
                p.error_code,p.error_message,p.updated_at,cp.x_tweet_id,cp.posted_at,cp.text
              FROM x_intelligence.audience_collection_progress p
              JOIN x_intelligence.competitor_posts cp ON cp.id=p.competitor_post_id
              WHERE p.run_id=%s
              ORDER BY CASE p.signal_type WHEN 'REPLY' THEN 1 WHEN 'RETWEET' THEN 2 ELSE 3 END,
                cp.posted_at DESC,cp.x_tweet_id""",(run_id,))
            return dict(run),[dict(row) for row in cursor.fetchall()]

    def latest_global_refreshes(self):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT DISTINCT ON (refresh_type) * FROM x_intelligence.global_refresh_runs ORDER BY refresh_type,created_at DESC,id DESC""")
            return {row["refresh_type"]:dict(row) for row in cursor.fetchall()}

    def global_audience_summary(self):
        """Return globally deduplicated audience inventory by canonical signal type."""
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT
              COUNT(DISTINCT audience_user_id) FILTER (WHERE signal_type='REPLY')::int AS commenters,
              COUNT(DISTINCT audience_user_id) FILTER (WHERE signal_type='RETWEET')::int AS retweeters,
              COUNT(DISTINCT audience_user_id) FILTER (WHERE signal_type='QUOTE')::int AS quote_posters,
              COUNT(DISTINCT audience_user_id)::int AS unique_leads
              FROM x_intelligence.audience_signals
              WHERE signal_type IN ('REPLY','RETWEET','QUOTE')""")
            return dict(cursor.fetchone())

    def list_collected_leads(self, *, page=1, page_size=25, search="", sort="account-asc"):
        term=str(search).strip();where="WHERE s.signal_type IN ('REPLY','RETWEET','QUOTE')";params=[]
        if term:
            where+=" AND (u.username ILIKE %s OR COALESCE(u.display_name,'') ILIKE %s)";pattern=f"%{term}%";params.extend((pattern,pattern))
        orders={"account-asc":"LOWER(COALESCE(u.display_name,u.username)) ASC,LOWER(u.username) ASC,u.id ASC","account-desc":"LOWER(COALESCE(u.display_name,u.username)) DESC,LOWER(u.username) DESC,u.id ASC","competitors-desc":"competitor_count DESC,LOWER(COALESCE(u.display_name,u.username)) ASC,LOWER(u.username) ASC,u.id ASC","competitors-asc":"competitor_count ASC,LOWER(COALESCE(u.display_name,u.username)) ASC,LOWER(u.username) ASC,u.id ASC"}
        if sort not in orders: raise ValueError("Unsupported collected-leads sort.")
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(DISTINCT u.id)::int AS total FROM x_intelligence.audience_users u JOIN x_intelligence.audience_signals s ON s.audience_user_id=u.id {where}",params);total=cursor.fetchone()["total"]
            cursor.execute(f"""SELECT u.id,u.x_user_id,u.username,u.display_name,u.profile_image_url,
              BOOL_OR(s.signal_type='REPLY') AS has_reply,BOOL_OR(s.signal_type='RETWEET') AS has_retweet,
              BOOL_OR(s.signal_type='QUOTE') AS has_quote,COUNT(DISTINCT s.competitor_id)::int AS competitor_count
              FROM x_intelligence.audience_users u JOIN x_intelligence.audience_signals s ON s.audience_user_id=u.id
              {where} GROUP BY u.id,u.x_user_id,u.username,u.display_name,u.profile_image_url
              ORDER BY {orders[sort]} LIMIT %s OFFSET %s""",[*params,page_size,(page-1)*page_size])
            return [dict(row) for row in cursor.fetchall()],total

    def list_collected_lead_usernames(self):
        """Return every canonical lead username once for operator export."""
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT username FROM (
              SELECT DISTINCT ON (LOWER(LTRIM(BTRIM(u.username),'@')))
                LTRIM(BTRIM(u.username),'@') AS username,u.first_seen_at,u.id
              FROM x_intelligence.audience_users u
              WHERE NULLIF(LTRIM(BTRIM(u.username),'@'),'') IS NOT NULL AND EXISTS (
                  SELECT 1 FROM x_intelligence.audience_signals s
                  WHERE s.audience_user_id=u.id
                    AND s.signal_type IN ('REPLY','RETWEET','QUOTE')
                )
              ORDER BY LOWER(LTRIM(BTRIM(u.username),'@')),u.first_seen_at,u.id
              ) canonical_usernames ORDER BY LOWER(username),username""")
            return [row["username"] for row in cursor.fetchall()]

    def iter_collected_lead_usernames(self, *, batch_size=1000):
        """Stream each valid stored username once, deduplicated case-insensitively."""
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT username FROM (
              SELECT DISTINCT ON (LOWER(LTRIM(BTRIM(u.username),'@')))
                LTRIM(BTRIM(u.username),'@') AS username,u.first_seen_at,u.id
              FROM x_intelligence.audience_users u
              WHERE NULLIF(LTRIM(BTRIM(u.username),'@'),'') IS NOT NULL AND EXISTS (
                SELECT 1 FROM x_intelligence.audience_signals s
                WHERE s.audience_user_id=u.id AND s.signal_type IN ('REPLY','RETWEET','QUOTE')
              )
              ORDER BY LOWER(LTRIM(BTRIM(u.username),'@')),u.first_seen_at,u.id
              ) canonical_usernames ORDER BY LOWER(username),username""")
            while True:
                rows=cursor.fetchmany(batch_size)
                if not rows: break
                for row in rows: yield row["username"]

    def get_competitor(self, competitor_id):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT * FROM x_intelligence.competitors WHERE id=%s",(competitor_id,));row=cursor.fetchone();return dict(row) if row else None

    def qualifying_posts(self, competitor_id, now):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM x_intelligence.competitor_posts WHERE competitor_id=%s AND posted_at>=%s
              AND is_reply=FALSE AND is_retweet=FALSE ORDER BY posted_at,id""",(competitor_id,now-timedelta(days=7)))
            return [dict(row) for row in cursor.fetchall()]

    def begin_or_resume(self, competitor_id, posts, now):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM x_intelligence.audience_collection_runs WHERE competitor_id=%s AND status IN ('RUNNING','PARTIAL','FAILED') ORDER BY created_at DESC LIMIT 1""",(competitor_id,));run=cursor.fetchone()
            if run:
                cursor.execute("UPDATE x_intelligence.audience_collection_runs SET status='RUNNING',completed_at=NULL,error_code=NULL,error_message=NULL WHERE id=%s RETURNING *",(run["id"],));run=cursor.fetchone()
            else:
                cursor.execute("""INSERT INTO x_intelligence.audience_collection_runs(id,competitor_id,window_started_at,window_ended_at,status,started_at,posts_considered)
                  VALUES(%s,%s,%s,%s,'RUNNING',%s,%s) RETURNING *""",(uuid4(),competitor_id,now-timedelta(days=7),now,now,len(posts)));run=cursor.fetchone()
                for post in posts:
                    for kind,count_key in (("REPLY","reply_count"),("RETWEET","retweet_count"),("QUOTE","quote_count")):
                        status="SUCCEEDED" if post.get(count_key)==0 else "PENDING"
                        cursor.execute("INSERT INTO x_intelligence.audience_collection_progress(id,run_id,competitor_post_id,signal_type,status) VALUES(%s,%s,%s,%s,%s)",(uuid4(),run["id"],post["id"],kind,status))
            return dict(run)

    def pending_progress(self, run_id):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT p.*,cp.x_tweet_id FROM x_intelligence.audience_collection_progress p JOIN x_intelligence.competitor_posts cp ON cp.id=p.competitor_post_id WHERE p.run_id=%s AND p.status<>'SUCCEEDED' ORDER BY cp.posted_at,p.signal_type""",(run_id,));return [dict(row) for row in cursor.fetchall()]

    def persist_page(self, run_id, competitor_id, progress, page):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            for record in page.records:
                u=record.user
                cursor.execute("SELECT id FROM x_intelligence.audience_users WHERE x_user_id=%s",(u.x_user_id,));existing_user=cursor.fetchone()
                cursor.execute("""INSERT INTO x_intelligence.audience_users(id,x_user_id,username,display_name,profile_image_url,followers_count,following_count,verified,account_created_at)
                  VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(x_user_id) DO UPDATE SET username=EXCLUDED.username,display_name=COALESCE(EXCLUDED.display_name,x_intelligence.audience_users.display_name),profile_image_url=COALESCE(EXCLUDED.profile_image_url,x_intelligence.audience_users.profile_image_url),followers_count=COALESCE(EXCLUDED.followers_count,x_intelligence.audience_users.followers_count),following_count=COALESCE(EXCLUDED.following_count,x_intelligence.audience_users.following_count),verified=COALESCE(EXCLUDED.verified,x_intelligence.audience_users.verified),account_created_at=COALESCE(EXCLUDED.account_created_at,x_intelligence.audience_users.account_created_at),last_seen_at=NOW(),updated_at=NOW() RETURNING id""",(uuid4(),u.x_user_id,u.username,u.display_name,u.profile_image_url,u.followers_count,u.following_count,u.verified,u.account_created_at));user_id=cursor.fetchone()["id"]
                cursor.execute("SELECT id FROM x_intelligence.audience_signals WHERE audience_user_id=%s AND competitor_post_id=%s AND signal_type=%s",(user_id,progress["competitor_post_id"],progress["signal_type"]));existing_signal=cursor.fetchone()
                cursor.execute("""INSERT INTO x_intelligence.audience_signals(id,audience_user_id,competitor_id,competitor_post_id,signal_type,source_x_tweet_id)
                  VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(audience_user_id,competitor_post_id,signal_type) DO UPDATE SET last_seen_at=NOW(),updated_at=NOW() RETURNING id""",(uuid4(),user_id,competitor_id,progress["competitor_post_id"],progress["signal_type"],progress["x_tweet_id"]));signal_id=cursor.fetchone()["id"]
                cursor.execute("""INSERT INTO x_intelligence.audience_signal_occurrences(id,audience_signal_id,interaction_x_tweet_id,occurred_at) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id""",(uuid4(),signal_id,record.interaction_x_tweet_id,record.occurred_at));new_occurrence=cursor.fetchone() is not None
                if new_occurrence: cursor.execute("UPDATE x_intelligence.audience_signals SET occurrence_count=(SELECT COUNT(*) FROM x_intelligence.audience_signal_occurrences WHERE audience_signal_id=%s) WHERE id=%s",(signal_id,signal_id))
                cursor.execute("INSERT INTO x_intelligence.audience_collection_run_users(run_id,audience_user_id,was_new) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",(run_id,user_id,not bool(existing_user)))
                cursor.execute("INSERT INTO x_intelligence.audience_collection_run_signals(run_id,audience_signal_id,was_new) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",(run_id,signal_id,not bool(existing_signal)))
            returned_field={"REPLY":"reply_records_returned","RETWEET":"retweeter_records_returned","QUOTE":"quote_records_returned"}[progress["signal_type"]]
            cursor.execute(f"UPDATE x_intelligence.audience_collection_runs SET {returned_field}={returned_field}+%s,provider_requests=provider_requests+1 WHERE id=%s",(len(page.records),run_id))
            status="RUNNING" if page.has_next_page else "SUCCEEDED"
            cursor.execute("UPDATE x_intelligence.audience_collection_progress SET cursor=%s,status=%s,pages_completed=pages_completed+1,provider_requests=provider_requests+1,error_code=NULL,error_message=NULL,updated_at=NOW() WHERE id=%s",(page.next_cursor,status,progress["id"]))

    def fail_progress(self, run_id, progress_id, message):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("UPDATE x_intelligence.audience_collection_progress SET status='FAILED',provider_requests=provider_requests+1,error_code='PROVIDER_ERROR',error_message=%s,updated_at=NOW() WHERE id=%s",(str(message)[:1000],progress_id))
            cursor.execute("UPDATE x_intelligence.audience_collection_runs SET provider_requests=provider_requests+1,error_code='PARTIAL_PROVIDER_FAILURE',error_message='One or more audience sources could not be collected.' WHERE id=%s",(run_id,))

    def finish(self, run_id):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS failed FROM x_intelligence.audience_collection_progress WHERE run_id=%s AND status='FAILED'",(run_id,));failed=cursor.fetchone()["failed"]
            status="PARTIAL" if failed else "SUCCEEDED"
            cursor.execute("""UPDATE x_intelligence.audience_collection_runs r SET status=%s,completed_at=NOW(),posts_processed=(SELECT COUNT(DISTINCT competitor_post_id) FROM x_intelligence.audience_collection_progress WHERE run_id=r.id AND status='SUCCEEDED'),unique_users_observed=(SELECT COUNT(*) FROM x_intelligence.audience_collection_run_users WHERE run_id=r.id),new_users=(SELECT COUNT(*) FROM x_intelligence.audience_collection_run_users WHERE run_id=r.id AND was_new),existing_users=(SELECT COUNT(*) FROM x_intelligence.audience_collection_run_users WHERE run_id=r.id AND NOT was_new),new_signals=(SELECT COUNT(*) FROM x_intelligence.audience_collection_run_signals WHERE run_id=r.id AND was_new),existing_signals=(SELECT COUNT(*) FROM x_intelligence.audience_collection_run_signals WHERE run_id=r.id AND NOT was_new) WHERE id=%s RETURNING *""",(status,run_id));run=dict(cursor.fetchone());run["failed_sources"]=failed
            cursor.execute("SELECT signal_type,SUM(provider_requests)::int AS requests,COUNT(*) FILTER(WHERE status='FAILED')::int AS failed FROM x_intelligence.audience_collection_progress WHERE run_id=%s GROUP BY signal_type",(run_id,))
            breakdown={row["signal_type"]:{"requests":row["requests"],"failed":row["failed"]} for row in cursor.fetchall()};run["source_breakdown"]=breakdown
            return run

    def list_run_users(self, run_id, classification):
        was_new=classification.upper()=="NEW"
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT u.id,u.x_user_id,u.username,u.display_name,u.profile_image_url,
              ARRAY_AGG(DISTINCT s.signal_type ORDER BY s.signal_type) AS signal_types,
              COUNT(DISTINCT s.competitor_post_id)::int AS source_posts,
              COUNT(DISTINCT prior.competitor_id)::int AS previous_competitors,
              MIN(pc.display_name) FILTER (WHERE pc.id IS NOT NULL) AS known_from_display_name,
              MIN(pc.username) FILTER (WHERE pc.id IS NOT NULL) AS known_from_username
              FROM x_intelligence.audience_collection_run_users ru
              JOIN x_intelligence.audience_users u ON u.id=ru.audience_user_id
              JOIN x_intelligence.audience_collection_run_signals rs ON rs.run_id=ru.run_id
              JOIN x_intelligence.audience_signals s ON s.id=rs.audience_signal_id AND s.audience_user_id=u.id
              JOIN x_intelligence.audience_collection_runs r ON r.id=ru.run_id
              LEFT JOIN x_intelligence.audience_signals prior ON prior.audience_user_id=u.id AND prior.competitor_id<>r.competitor_id AND prior.first_seen_at<r.started_at
              LEFT JOIN x_intelligence.competitors pc ON pc.id=prior.competitor_id
              WHERE ru.run_id=%s AND ru.was_new=%s
              GROUP BY u.id,u.x_user_id,u.username,u.display_name,u.profile_image_url
              ORDER BY LOWER(COALESCE(u.display_name,u.username)),LOWER(u.username),u.id""",(run_id,was_new))
            return [dict(row) for row in cursor.fetchall()]

    def get_run(self, run_id):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute("SELECT * FROM x_intelligence.audience_collection_runs WHERE id=%s",(run_id,));row=cursor.fetchone();return dict(row) if row else None
