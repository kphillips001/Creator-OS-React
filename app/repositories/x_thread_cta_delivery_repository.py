"""Durable, non-queue delivery authority for X thread CTAs."""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.database import get_db_connection


class XThreadCtaDeliveryRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def claim_once(self, *, creator_profile_id: int, fanvue_account_id: int,
                   publish_operation_id: str, x_account_name: str,
                   primary_x_post_id: str, x_link_attribution_id: str,
                   timing: str, cta_text: str, cta_url: str) -> dict[str, Any]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.x_thread_cta_deliveries
                    (delivery_id,creator_profile_id,fanvue_account_id,
                     publish_operation_id,x_account_name,primary_x_post_id,
                     x_link_attribution_id,timing,cta_text,cta_url,state)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DELIVERING')
                ON CONFLICT (creator_profile_id,fanvue_account_id,
                             publish_operation_id,x_account_name) DO NOTHING
                RETURNING *
            """, (uuid4(), creator_profile_id, fanvue_account_id,
                  publish_operation_id, x_account_name, primary_x_post_id,
                  UUID(x_link_attribution_id), timing, cta_text, cta_url))
            row = cursor.fetchone()
            if row:
                return {**dict(row), "_claim_acquired": True}
            cursor.execute("""
                SELECT * FROM public.x_thread_cta_deliveries
                 WHERE creator_profile_id=%s AND fanvue_account_id=%s
                   AND publish_operation_id=%s AND x_account_name=%s
            """, (creator_profile_id, fanvue_account_id,
                  publish_operation_id, x_account_name))
            return {**dict(cursor.fetchone()), "_claim_acquired": False}

    def mark_posted(self, delivery_id: str, *, reply_id: str,
                    output_url: str | None) -> dict[str, Any]:
        return self._transition(delivery_id, "POSTED",
                                resulting_x_reply_id=reply_id,
                                provider_output_url=output_url,
                                sent_at="NOW()")

    def mark_uncertain(self, delivery_id: str, reason: str) -> dict[str, Any]:
        return self._transition(delivery_id, "SEND_UNCERTAIN",
                                failure_reason=reason)

    def _transition(self, delivery_id: str, state: str, **values) -> dict[str, Any]:
        columns = []
        parameters: list[Any] = []
        for key, value in values.items():
            if key == "sent_at" and value == "NOW()":
                columns.append("sent_at=NOW()")
            else:
                columns.append(f"{key}=%s")
                parameters.append(value)
        columns.extend(("state=%s", "updated_at=NOW()"))
        parameters.extend((state, UUID(delivery_id)))
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE public.x_thread_cta_deliveries SET {','.join(columns)} "
                "WHERE delivery_id=%s AND state='DELIVERING' RETURNING *",
                tuple(parameters),
            )
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("X CTA delivery is no longer active.")
            return dict(row)
