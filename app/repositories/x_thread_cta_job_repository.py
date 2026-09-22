"""Durable, account-scoped X thread CTA queue."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from app.database import get_db_connection


class XThreadCtaJobRepository:
    def __init__(self, connection_factory=get_db_connection): self.connection_factory = connection_factory

    def create_once(self, *, creator_profile_id: int, fanvue_account_id: int,
                    publish_operation_id: str, social_queue_item_id: str,
                    generation_image_id: str, primary_x_post_id: str,
                    primary_published_at: datetime,
                    x_account_name: str, x_link_attribution_id: str,
                    asset_reference: str | None, thumbnail_reference: str | None,
                    caption_preview: str, cta_text: str, cta_url: str,
                    sampled_delay_seconds: int, scheduled_at: datetime) -> dict[str, Any]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.x_thread_cta_jobs
                (job_id,creator_profile_id,fanvue_account_id,publish_operation_id,
                 social_queue_item_id,generation_image_id,primary_x_post_id,primary_published_at,x_account_name,
                 x_link_attribution_id,asset_reference,thumbnail_reference,caption_preview,
                 cta_text,cta_url,sampled_delay_seconds,scheduled_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (creator_profile_id,fanvue_account_id,publish_operation_id,x_account_name)
                DO UPDATE SET updated_at=public.x_thread_cta_jobs.updated_at
                RETURNING *
            """, (uuid4(),creator_profile_id,fanvue_account_id,publish_operation_id,
                  social_queue_item_id,generation_image_id,primary_x_post_id,primary_published_at,x_account_name,
                  UUID(x_link_attribution_id),asset_reference,thumbnail_reference,caption_preview,
                  cta_text,cta_url,sampled_delay_seconds,scheduled_at))
            return dict(cursor.fetchone())

    def find_by_operation(self, *, creator_profile_id: int, fanvue_account_id: int,
                          publish_operation_id: str, x_account_name: str) -> dict[str, Any] | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.x_thread_cta_jobs WHERE creator_profile_id=%s AND fanvue_account_id=%s AND publish_operation_id=%s AND x_account_name=%s",(creator_profile_id,fanvue_account_id,publish_operation_id,x_account_name))
            row=cursor.fetchone(); return dict(row) if row else None

    def get(self, job_id: str, *, creator_profile_id: int, fanvue_account_id: int) -> dict[str, Any] | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.x_thread_cta_jobs WHERE job_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s",(UUID(job_id),creator_profile_id,fanvue_account_id))
            row=cursor.fetchone(); return dict(row) if row else None

    def list(self, *, creator_profile_id: int, fanvue_account_id: int, history: bool, limit: int=100) -> list[dict[str, Any]]:
        states=("POSTED","FAILED","SEND_UNCERTAIN","CANCELED") if history else ("SCHEDULED","CLAIMED")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.x_thread_cta_jobs WHERE creator_profile_id=%s AND fanvue_account_id=%s AND state=ANY(%s) ORDER BY scheduled_at ASC LIMIT %s",(creator_profile_id,fanvue_account_id,list(states),limit))
            return [dict(row) for row in cursor.fetchall()]

    def claim(self, *, worker_id: str, job_id: str | None=None, force: bool=False, now: datetime | None=None) -> dict[str, Any] | None:
        now=now or datetime.now(timezone.utc)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            job_filter = " AND job_id=%s" if job_id else ""
            cursor.execute(f"""
              WITH candidate AS (
                SELECT job_id FROM public.x_thread_cta_jobs
                 WHERE state='SCHEDULED' AND (%s OR scheduled_at<=%s){job_filter}
                 ORDER BY scheduled_at,job_id FOR UPDATE SKIP LOCKED LIMIT 1)
              UPDATE public.x_thread_cta_jobs job SET state='CLAIMED',claim_owner=%s,
                claimed_at=%s,lease_expires_at=%s,attempt_count=attempt_count+1,updated_at=%s
              FROM candidate WHERE job.job_id=candidate.job_id RETURNING job.*
            """,(force,now)+((UUID(job_id),) if job_id else ())+(
                worker_id,now,now+timedelta(minutes=5),now))
            row=cursor.fetchone(); return dict(row) if row else None

    def mark_posted(self, job_id: str, *, reply_id: str, output_url: str | None, now: datetime | None=None) -> dict[str, Any]:
        now=now or datetime.now(timezone.utc)
        return self._transition(job_id,"POSTED", resulting_x_reply_id=reply_id,provider_output_url=output_url,sent_at=now)

    def mark_uncertain(self, job_id: str, reason: str) -> dict[str, Any]: return self._transition(job_id,"SEND_UNCERTAIN",failure_reason=reason)
    def cancel(self, job_id: str, *, creator_profile_id: int, fanvue_account_id: int, actor: str) -> dict[str, Any] | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE public.x_thread_cta_jobs SET state='CANCELED',canceled_at=NOW(),canceled_by=%s,updated_at=NOW() WHERE job_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s AND state='SCHEDULED' RETURNING *",(actor,UUID(job_id),creator_profile_id,fanvue_account_id))
            row=cursor.fetchone(); return dict(row) if row else None
    def expire_claims_to_uncertain(self) -> int:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE public.x_thread_cta_jobs SET state='SEND_UNCERTAIN',failure_reason='CLAIM_EXPIRED_OUTCOME_UNKNOWN',updated_at=NOW() WHERE state='CLAIMED' AND lease_expires_at<NOW()")
            return cursor.rowcount
    def _transition(self, job_id: str, state: str, **values) -> dict[str, Any]:
        allowed={"resulting_x_reply_id","provider_output_url","sent_at","failure_reason"}; fields=[key for key in values if key in allowed]
        sql=",".join([f"{key}=%s" for key in fields]+["state=%s","updated_at=NOW()"])
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"UPDATE public.x_thread_cta_jobs SET {sql} WHERE job_id=%s AND state='CLAIMED' RETURNING *",tuple(values[k] for k in fields)+(state,UUID(job_id)))
            row=cursor.fetchone()
            if not row: raise RuntimeError("X CTA job is no longer claimed.")
            return dict(row)
