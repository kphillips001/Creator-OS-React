"""PostgreSQL authority for standalone engagement-Teaser controls and sends."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.free_engagement_teaser import (
    FreeEngagementTeaserDeliveryState,
    FreeEngagementTeaserOperation,
)


class FreeEngagementTeaserRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def reserve_next(self, *, creator_profile_id: int, fanvue_account_id: int,
                     fanvue_user_id: int, conversation_thread_id: int,
                     telegram_chat_id: int, correlation_id: str,
                     inbound_telegram_message_id: int | None, caption: str,
                     media_resolver, engagement_strategy: str | None = None,
                     decision_reason_code: str | None = None,
                     decision_evidence: dict | None = None,
                     policy_version: str | None = None) -> FreeEngagementTeaserOperation | None:
        """Reserve the first resolvable unseen candidate; uniqueness is permanent."""
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(self._eligible_sql(), (
                    int(creator_profile_id), int(creator_profile_id),
                    int(fanvue_account_id), int(fanvue_user_id),
                ))
                candidates = cursor.fetchall()
                for row in candidates:
                    asset_id = int(row["asset_id"])
                    try:
                        resolved = media_resolver(asset_id)
                    except Exception:
                        continue
                    media_reference = str(resolved or "").strip()
                    if not media_reference:
                        continue
                    cursor.execute(
                        """INSERT INTO public.telegram_engagement_teaser_delivery_operations (
                               operation_id,correlation_id,creator_profile_id,
                               fanvue_account_id,fanvue_user_id,conversation_thread_id,
                               telegram_chat_id,inbound_telegram_message_id,
                               teaser_asset_id,media_reference,caption,state)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'CREATED')
                           ON CONFLICT DO NOTHING RETURNING *""",
                        (uuid4(), str(correlation_id), int(creator_profile_id),
                         int(fanvue_account_id), int(fanvue_user_id),
                         int(conversation_thread_id), int(telegram_chat_id),
                         inbound_telegram_message_id, asset_id, media_reference,
                         str(caption or "")),
                    )
                    reserved = cursor.fetchone()
                    if reserved is not None:
                        if engagement_strategy:
                            cursor.execute("""UPDATE public.telegram_engagement_teaser_delivery_operations
                                SET engagement_strategy=%s,decision_reason_code=%s,
                                    decision_evidence=%s::jsonb,policy_version=%s,updated_at=NOW()
                                WHERE operation_id=%s RETURNING *""",
                                (engagement_strategy, decision_reason_code,
                                 json.dumps(decision_evidence or {}),
                                 policy_version, reserved['operation_id']))
                            reserved = cursor.fetchone()
                        return self._operation(reserved)
        return None

    @staticmethod
    def _eligible_sql():
        return """
            SELECT asset.id AS asset_id
            FROM public.content_items asset
            JOIN public.asset_content_destinations destination
              ON destination.asset_id=asset.id
             AND destination.destination='TEASER'
             AND destination.metadata->>'purpose'='ENGAGEMENT_TEASER'
            LEFT JOIN public.engagement_teaser_chat_controls control
              ON control.asset_id=asset.id
            WHERE asset.creator_profile_id=%s
              AND COALESCE(asset.is_active,TRUE)=TRUE
              AND COALESCE(asset.is_test,FALSE)=FALSE
              AND asset.status='approved'
              AND COALESCE(control.chat_enabled,TRUE)=TRUE
              AND (LOWER(COALESCE(asset.media_metadata->>'media_type',''))='image'
                   OR LOWER(COALESCE(asset.file_path,'')) ~ '\\.(gif|jpe?g|png|webp)$')
              AND NOT EXISTS (SELECT 1 FROM public.photoshoot_asset_memberships item
                              WHERE item.asset_id=asset.id)
              AND NOT EXISTS (SELECT 1 FROM public.commercial_role_assignments item
                              WHERE item.asset_id=asset.id)
              AND NOT EXISTS (SELECT 1 FROM public.commercial_offering_assets item
                              WHERE item.asset_id=asset.id)
              AND NOT EXISTS (
                  SELECT 1 FROM public.telegram_engagement_teaser_delivery_operations sent
                  WHERE sent.creator_profile_id=%s
                    AND sent.fanvue_account_id=%s
                    AND sent.fanvue_user_id=%s
                    AND sent.teaser_asset_id=asset.id)
            ORDER BY (
                SELECT COUNT(*) FROM public.telegram_engagement_teaser_delivery_operations usage
                WHERE usage.creator_profile_id=asset.creator_profile_id
                  AND usage.teaser_asset_id=asset.id
            ), destination.assigned_at, asset.id
            FOR UPDATE OF asset SKIP LOCKED
        """

    def validate_context(self, *, creator_profile_id, fanvue_account_id,
                         fanvue_user_id, telegram_user_id,
                         conversation_thread_id) -> str | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT 1 FROM public.telegram_identity_map
                   WHERE fanvue_account_id=%s AND local_fanvue_user_id=%s
                     AND telegram_user_id=%s AND is_active=TRUE
                     AND verification_status='VERIFIED'""",
                (int(fanvue_account_id), int(fanvue_user_id), int(telegram_user_id)),
            )
            if cursor.fetchone() is None:
                return "IDENTITY_UNRESOLVED"
            cursor.execute(
                """SELECT 1 FROM public.chat_threads
                   WHERE id=%s AND fanvue_account_id=%s AND fanvue_user_id=%s""",
                (int(conversation_thread_id), int(fanvue_account_id), int(fanvue_user_id)),
            )
            if cursor.fetchone() is None:
                return "CONVERSATION_IDENTITY_MISMATCH"
            cursor.execute(
                """SELECT 1 FROM public.customer_commerce_profiles
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND telegram_user_id=%s LIMIT 1""",
                (int(creator_profile_id), int(fanvue_account_id), int(telegram_user_id)),
            )
            return None if cursor.fetchone() is not None else "CUSTOMER_PROFILE_UNRESOLVED"

    def funnel_conflict(self, *, creator_profile_id, fanvue_account_id,
                        fanvue_user_id, telegram_chat_id) -> str | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT status,attribution_result FROM public.purchase_intents
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND telegram_user_id=%s ORDER BY created_at DESC LIMIT 1""",
                (int(creator_profile_id), int(fanvue_account_id), int(telegram_chat_id)),
            )
            intent = cursor.fetchone()
            if intent and intent["status"] in {"CREATED","PRESENTED","CLICKED"}:
                return "ACTIVE_PURCHASE_INTENT"
            if intent and intent["attribution_result"] == "UNKNOWN":
                return "MANUAL_PURCHASE_ATTRIBUTION_REVIEW"
            cursor.execute(
                """SELECT 1 FROM public.commerce_signal_reconciliations reconciliation
                   JOIN public.fanvue_users customer
                     ON customer.fanvue_account_id=reconciliation.fanvue_account_id
                    AND customer.fanvue_user_uuid=reconciliation.external_fanvue_user_uuid
                   WHERE reconciliation.creator_profile_id=%s
                     AND reconciliation.fanvue_account_id=%s AND customer.id=%s
                     AND (reconciliation.state='PENDING'
                          OR reconciliation.attribution_state IN ('PENDING','UNKNOWN'))
                   LIMIT 1""",
                (int(creator_profile_id), int(fanvue_account_id), int(fanvue_user_id)),
            )
            if cursor.fetchone() is not None:
                return "PAYMENT_RECONCILIATION_PENDING"
            cursor.execute(
                """SELECT 1 FROM public.sales_sessions WHERE creator_profile_id=%s
                   AND fanvue_account_id=%s AND fanvue_user_id=%s
                   AND state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING') LIMIT 1""",
                (int(creator_profile_id), int(fanvue_account_id), int(fanvue_user_id)),
            )
            if cursor.fetchone() is not None:
                return "ACTIVE_SALES_SESSION"
            if intent and intent["status"] == "ABANDONED":
                return "RECENT_DECLINE_OR_BACK_OFF"
            cursor.execute(
                """SELECT 1 FROM public.customer_commerce_profiles
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND telegram_user_id=%s AND last_purchase_at>NOW()-INTERVAL '24 hours'
                   LIMIT 1""",
                (int(creator_profile_id), int(fanvue_account_id), int(telegram_chat_id)),
            )
            if cursor.fetchone() is not None:
                return "RECENT_PURCHASE_COOLDOWN"
        return None

    def get(self, operation_id) -> FreeEngagementTeaserOperation | None:
        return self._one("SELECT * FROM public.telegram_engagement_teaser_delivery_operations WHERE operation_id=%s", (operation_id,))

    def claim(self, operation_id):
        return self._update("""UPDATE public.telegram_engagement_teaser_delivery_operations
            SET state='SENDING',sending_at=NOW(),updated_at=NOW()
            WHERE operation_id=%s AND state='CREATED' RETURNING *""", (operation_id,))

    def accepted(self, operation_id, telegram_message_id):
        return self._update("""UPDATE public.telegram_engagement_teaser_delivery_operations
            SET state='TELEGRAM_ACCEPTED',outbound_telegram_message_id=%s,
                telegram_accepted_at=NOW(),updated_at=NOW()
            WHERE operation_id=%s AND state='SENDING' RETURNING *""",
            (int(telegram_message_id), operation_id))

    def update_caption(self, operation_id, caption):
        caption = str(caption or "").strip()
        if not caption:
            return None
        return self._update("""UPDATE public.telegram_engagement_teaser_delivery_operations
            SET caption=%s,updated_at=NOW() WHERE operation_id=%s AND state='CREATED'
            RETURNING *""", (caption, operation_id))

    def record_next_inbound(self, *, creator_profile_id, fanvue_account_id,
                            fanvue_user_id, telegram_message_id,
                            inbound_at=None, reply_to_message_id=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.telegram_engagement_teaser_delivery_operations operation
                SET next_inbound_message_id=%s,next_inbound_at=COALESCE(%s,NOW()),
                    response_latency_seconds=GREATEST(0,EXTRACT(EPOCH FROM
                      (COALESCE(%s,NOW())-operation.telegram_accepted_at))::bigint),
                    response_attribution=CASE WHEN operation.outbound_telegram_message_id=%s
                      THEN 'DIRECT_REPLY_TO_TEASER' ELSE 'NEXT_INBOUND_AFTER_TEASER' END,
                    updated_at=NOW()
                WHERE operation.operation_id=(SELECT candidate.operation_id
                    FROM public.telegram_engagement_teaser_delivery_operations candidate
                    WHERE candidate.creator_profile_id=%s AND candidate.fanvue_account_id=%s
                      AND candidate.fanvue_user_id=%s AND candidate.state='CONFIRMED'
                      AND candidate.telegram_accepted_at<=COALESCE(%s,NOW())
                      AND candidate.next_inbound_at IS NULL
                    ORDER BY candidate.telegram_accepted_at DESC LIMIT 1)
                RETURNING *""", (int(telegram_message_id), inbound_at, inbound_at,
                    reply_to_message_id, int(creator_profile_id), int(fanvue_account_id),
                    int(fanvue_user_id), inbound_at))
            row = cursor.fetchone()
        return self._operation(row) if row else None

    def confirmed(self, operation_id):
        return self._update("""UPDATE public.telegram_engagement_teaser_delivery_operations
            SET state='CONFIRMED',confirmed_at=NOW(),updated_at=NOW()
            WHERE operation_id=%s AND state='TELEGRAM_ACCEPTED' RETURNING *""", (operation_id,))

    def failed(self, operation_id, reason):
        return self._update("""UPDATE public.telegram_engagement_teaser_delivery_operations
            SET state='FAILED',failure_reason=%s,failed_at=NOW(),updated_at=NOW()
            WHERE operation_id=%s AND state IN ('CREATED','SENDING') RETURNING *""",
            (str(reason)[:1000], operation_id))

    def ambiguous(self, operation_id, reason):
        return self._update("""UPDATE public.telegram_engagement_teaser_delivery_operations
            SET state='AMBIGUOUS',failure_reason=%s,updated_at=NOW()
            WHERE operation_id=%s AND state='SENDING' RETURNING *""",
            (str(reason)[:1000], operation_id))

    def mark_sending_ambiguous(self):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.telegram_engagement_teaser_delivery_operations
                SET state='AMBIGUOUS',failure_reason='Startup recovery: provider outcome unknown',updated_at=NOW()
                WHERE state='SENDING' RETURNING *""")
            return tuple(self._operation(row) for row in cursor.fetchall())

    def list_accepted(self):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.telegram_engagement_teaser_delivery_operations WHERE state='TELEGRAM_ACCEPTED' ORDER BY created_at")
            return tuple(self._operation(row) for row in cursor.fetchall())

    def set_chat_enabled(self, *, asset_id, creator_profile_id, enabled):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO public.engagement_teaser_chat_controls
                (asset_id,creator_profile_id,chat_enabled)
                SELECT asset.id,asset.creator_profile_id,%s
                FROM public.content_items asset
                JOIN public.asset_content_destinations destination
                  ON destination.asset_id=asset.id
                 AND destination.destination='TEASER'
                 AND destination.metadata->>'purpose'='ENGAGEMENT_TEASER'
                WHERE asset.id=%s AND asset.creator_profile_id=%s
                ON CONFLICT (asset_id) DO UPDATE SET chat_enabled=EXCLUDED.chat_enabled,updated_at=NOW()
                RETURNING chat_enabled""", (bool(enabled), int(asset_id), int(creator_profile_id)))
            row = cursor.fetchone()
            return bool(row["chat_enabled"]) if row is not None else None

    def summaries(self, asset_ids):
        if not asset_ids: return {}
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT asset.id,
                  COALESCE(control.chat_enabled,TRUE) chat_enabled,
                  COUNT(operation.operation_id) FILTER (WHERE operation.state IN ('TELEGRAM_ACCEPTED','CONFIRMED')) times_sent,
                  MAX(operation.telegram_accepted_at) last_sent
                FROM public.content_items asset
                LEFT JOIN public.engagement_teaser_chat_controls control ON control.asset_id=asset.id
                LEFT JOIN public.telegram_engagement_teaser_delivery_operations operation ON operation.teaser_asset_id=asset.id
                WHERE asset.id=ANY(%s) GROUP BY asset.id,control.chat_enabled""", (list(asset_ids),))
            return {int(row['id']): dict(row) for row in cursor.fetchall()}

    def _one(self, sql, params):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(sql, params); row=cursor.fetchone()
        return self._operation(row) if row else None

    def _update(self, sql, params):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(sql, params); row=cursor.fetchone()
        return self._operation(row) if row else None

    @staticmethod
    def _operation(row):
        return FreeEngagementTeaserOperation(
            operation_id=UUID(str(row['operation_id'])), correlation_id=str(row['correlation_id']),
            creator_profile_id=int(row['creator_profile_id']), fanvue_account_id=int(row['fanvue_account_id']),
            fanvue_user_id=int(row['fanvue_user_id']), conversation_thread_id=int(row['conversation_thread_id']),
            telegram_chat_id=int(row['telegram_chat_id']), inbound_telegram_message_id=row.get('inbound_telegram_message_id'),
            teaser_asset_id=int(row['teaser_asset_id']), media_reference=str(row['media_reference']),
            caption=str(row.get('caption') or ''), state=FreeEngagementTeaserDeliveryState(row['state']),
            outbound_telegram_message_id=row.get('outbound_telegram_message_id'), failure_reason=row.get('failure_reason'),
            created_at=row.get('created_at'), sending_at=row.get('sending_at'),
            telegram_accepted_at=row.get('telegram_accepted_at'), confirmed_at=row.get('confirmed_at'),
            failed_at=row.get('failed_at'), updated_at=row.get('updated_at'),
            engagement_strategy=row.get('engagement_strategy'),
            decision_reason_code=row.get('decision_reason_code'),
            decision_evidence=dict(row.get('decision_evidence') or {}),
            policy_version=row.get('policy_version'),
            next_inbound_message_id=row.get('next_inbound_message_id'),
            next_inbound_at=row.get('next_inbound_at'),
            response_latency_seconds=row.get('response_latency_seconds'),
            response_attribution=row.get('response_attribution'))
