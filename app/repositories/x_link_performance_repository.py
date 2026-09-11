"""PostgreSQL persistence for X-to-Telegram CTA attribution and clicks."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.database import get_db_connection


class XLinkPerformanceRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def get_or_create_attribution(
        self, *, attribution_token: str, creator_profile_id: int,
        fanvue_account_id: int, publish_operation_id: str,
        social_queue_item_id: str, generation_image_id: str,
        primary_x_post_id: str, x_account_name: str, primary_caption: str,
        primary_published_at: datetime,
    ) -> dict[str, Any]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.x_link_attributions (
                    x_link_attribution_id,attribution_token,creator_profile_id,
                    fanvue_account_id,publish_operation_id,social_queue_item_id,
                    generation_image_id,primary_x_post_id,x_account_name,
                    primary_caption,primary_published_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (creator_profile_id,fanvue_account_id,publish_operation_id,x_account_name)
                DO UPDATE SET
                    primary_x_post_id=EXCLUDED.primary_x_post_id,
                    primary_caption=EXCLUDED.primary_caption,
                    primary_published_at=EXCLUDED.primary_published_at,
                    updated_at=NOW()
                RETURNING *
                """,
                (uuid4(), attribution_token, creator_profile_id, fanvue_account_id,
                 publish_operation_id, social_queue_item_id, generation_image_id,
                 primary_x_post_id, x_account_name, primary_caption,
                 primary_published_at),
            )
            row = dict(cursor.fetchone())
            connection.commit()
            return row

    def attach_cta_post(self, attribution_id: str, cta_x_post_id: str) -> None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.x_link_attributions
                      SET cta_x_post_id=%s,updated_at=NOW()
                    WHERE x_link_attribution_id=%s""",
                (cta_x_post_id, UUID(str(attribution_id))),
            )
            connection.commit()

    def ingest_event(self, *, event_id: str, attribution_token: str,
                     occurred_at: datetime, event_type: str,
                     classification: str, classification_reason: str,
                     schema_version: int) -> dict[str, Any]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT x_link_attribution_id,status
                     FROM public.x_link_attributions
                    WHERE attribution_token=%s""", (attribution_token,))
            attribution = cursor.fetchone()
            if not attribution or attribution["status"] != "ACTIVE":
                return {"accepted": False, "duplicate": False, "reason": "UNKNOWN_OR_REVOKED_TOKEN"}
            cursor.execute(
                """INSERT INTO public.x_link_click_events (
                       event_id,x_link_attribution_id,occurred_at,event_type,
                       classification,classification_reason,schema_version
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (event_id) DO NOTHING
                   RETURNING event_id""",
                (UUID(str(event_id)), attribution["x_link_attribution_id"], occurred_at,
                 event_type, classification,
                 classification_reason, schema_version),
            )
            inserted = cursor.fetchone()
            connection.commit()
            return {"accepted": True, "duplicate": inserted is None, "reason": None}

    def attributed_posts(self, *, creator_profile_id: int, fanvue_account_id: int,
                         start: datetime | None, end: datetime) -> list[dict[str, Any]]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT attribution.*,
                       COUNT(event.event_id) AS link_clicks
                  FROM public.x_link_attributions attribution
                  LEFT JOIN public.x_link_click_events event
                    ON event.x_link_attribution_id=attribution.x_link_attribution_id
                   AND event.occurred_at >= COALESCE(%s, '-infinity'::timestamptz)
                   AND event.occurred_at < %s
                 WHERE attribution.creator_profile_id=%s
                   AND attribution.fanvue_account_id=%s
                   AND attribution.primary_published_at >= COALESCE(%s, '-infinity'::timestamptz)
                   AND attribution.primary_published_at < %s
                 GROUP BY attribution.x_link_attribution_id
                 ORDER BY attribution.primary_published_at DESC,
                          attribution.x_link_attribution_id
                """, (start, end, creator_profile_id, fanvue_account_id, start, end))
            return [dict(row) for row in cursor.fetchall()]
