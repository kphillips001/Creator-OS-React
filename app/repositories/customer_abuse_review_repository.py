"""Durable mapped-customer abuse review and operator alert operations."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from app.database import get_db_connection


class CustomerAbuseReviewRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def active_for_customer(self, *, creator_profile_id, fanvue_account_id,
                            fanvue_user_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.customer_abuse_review_incidents
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND fanvue_user_id=%s
                     AND review_status IN ('OPEN','MANUALLY_BLOCKED')
                   ORDER BY created_at DESC LIMIT 1""",
                (creator_profile_id, fanvue_account_id, fanvue_user_id),
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def create_or_append_open(self, **values):
        incident_id = uuid4()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.customer_abuse_review_incidents (
                       incident_id,creator_profile_id,fanvue_account_id,fanvue_user_id,
                       telegram_user_id,telegram_chat_id,mapping_state,abuse_severity,
                       abuse_category,abuse_reason,inbound_message_id,
                       inbound_correlation_id,sanitized_excerpt,buyer_stage_snapshot,
                       value_tier_snapshot,lifetime_spend_minor_snapshot,
                       incident_group_key)
                   VALUES (%s,%s,%s,%s,%s,%s,'MAPPED_CUSTOMER',%s,%s,%s,%s,%s,
                           %s,%s,%s,%s,%s)
                   ON CONFLICT (creator_profile_id,fanvue_account_id,fanvue_user_id)
                       WHERE review_status='OPEN'
                   DO UPDATE SET evidence_count=customer_abuse_review_incidents.evidence_count+1,
                       last_evidence_at=NOW(),updated_at=NOW()
                   RETURNING *""",
                (incident_id, values["creator_profile_id"], values["fanvue_account_id"],
                 values["fanvue_user_id"], values["telegram_user_id"],
                 values["telegram_chat_id"], values["abuse_severity"],
                 values["abuse_category"], values["abuse_reason"],
                 values["inbound_message_id"], values["inbound_correlation_id"],
                 values.get("sanitized_excerpt"), values.get("buyer_stage_snapshot"),
                 values.get("value_tier_snapshot"),
                 int(values.get("lifetime_spend_minor_snapshot") or 0),
                 values["incident_group_key"]),
            )
            row = dict(cursor.fetchone())
        row["created"] = row["incident_id"] == incident_id
        return row

    def resolve(self, *, incident_id, target_status, reviewed_by, reason,
                creator_profile_id=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.customer_abuse_review_incidents
                   SET review_status=%s,interaction_hold_active=%s,reviewed_at=NOW(),
                       reviewed_by=%s,review_reason=%s,updated_at=NOW()
                   WHERE incident_id=%s AND review_status='OPEN'
                     AND (%s::bigint IS NULL OR creator_profile_id=%s)
                   RETURNING *""",
                (target_status, target_status == "MANUALLY_BLOCKED", reviewed_by,
                 reason, incident_id, creator_profile_id, creator_profile_id),
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def create_notification(self, *, incident_id=None, destination_chat_id, payload,
                            notification_type="ABUSIVE_CUSTOMER_REVIEW",
                            correlation_id=None, context=None):
        context = dict(context or {})
        delivery_correlation_id = correlation_id or f"operator_abuse_review:{incident_id}"
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.operator_notification_operations (
                       notification_operation_id,notification_type,abuse_incident_id,
                       destination_chat_id,delivery_correlation_id,payload,state,failure_reason,
                       creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,
                       source_correlation_id,quality_reason,severity,incident_window_started_at)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                           COALESCE(%s,NOW()))
                   ON CONFLICT (delivery_correlation_id) DO UPDATE SET
                       delivery_correlation_id=EXCLUDED.delivery_correlation_id
                   RETURNING *""",
                (uuid4(), notification_type, incident_id, destination_chat_id,
                 delivery_correlation_id, json.dumps(dict(payload)),
                 "AUTHORIZED" if destination_chat_id else "FAILED",
                 None if destination_chat_id else "OPERATOR_ALERT_DESTINATION_NOT_CONFIGURED",
                 context.get("creator_profile_id"), context.get("fanvue_account_id"),
                 context.get("telegram_user_id"), context.get("telegram_chat_id"),
                 context.get("source_correlation_id"), context.get("quality_reason"),
                 context.get("severity"), context.get("incident_window_started_at"),
                 ),
            )
            return dict(cursor.fetchone())

    def claim_notification(self, *, operation_id, owner):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.operator_notification_operations
                   SET state='CLAIMED',claim_owner=%s,claimed_at=NOW(),attempted_at=NOW(),
                       updated_at=NOW()
                   WHERE notification_operation_id=%s AND state='AUTHORIZED'
                   RETURNING *""", (owner, operation_id),
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def confirm_notification(self, *, operation_id, provider_message_id):
        return self._finish_notification(operation_id, "SENT_CONFIRMED",
                                         provider_message_id, None)

    def fail_notification(self, *, operation_id, reason):
        return self._finish_notification(operation_id, "FAILED", None, reason)

    def _finish_notification(self, operation_id, state, provider_id, reason):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.operator_notification_operations SET state=%s,
                   provider_message_id=%s,failure_reason=%s,
                   confirmed_at=CASE WHEN %s='SENT_CONFIRMED' THEN NOW() ELSE NULL END,
                   updated_at=NOW() WHERE notification_operation_id=%s
                   AND state='CLAIMED' RETURNING *""",
                (state, provider_id, reason, state, operation_id),
            )
            row = cursor.fetchone()
        return dict(row) if row else None
