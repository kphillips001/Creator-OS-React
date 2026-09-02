"""Durable Telegram-native prospect persistence."""
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.telegram_sales_prospect import TelegramSalesProspect


class TelegramSalesProspectRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def observe(self, *, creator_profile_id, fanvue_account_id,
                telegram_user_id, telegram_chat_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """WITH authoritative_inbound AS (
                           SELECT COUNT(*)::BIGINT AS count
                           FROM public.ordinary_chat_reply_operations
                           WHERE telegram_account_scope='AVA_TELETHON_PRIVATE'
                             AND inbound_sender_telegram_user_id=%s
                       )
                       INSERT INTO public.telegram_sales_prospects (
                           telegram_sales_prospect_id,creator_profile_id,
                           fanvue_account_id,telegram_user_id,telegram_chat_id,
                           inbound_message_count)
                       SELECT %s,%s,%s,%s,%s,count FROM authoritative_inbound
                       ON CONFLICT (creator_profile_id,fanvue_account_id,telegram_user_id)
                       DO UPDATE SET telegram_chat_id=EXCLUDED.telegram_chat_id,
                           inbound_message_count=CASE
                               WHEN EXCLUDED.inbound_message_count>0
                               THEN EXCLUDED.inbound_message_count
                               ELSE telegram_sales_prospects.inbound_message_count
                           END,
                           last_observed_at=NOW() RETURNING *""",
                    (telegram_user_id, uuid4(), creator_profile_id, fanvue_account_id,
                     telegram_user_id, telegram_chat_id),
                )
                return self._model(cursor.fetchone())

    def get(self, *, creator_profile_id, fanvue_account_id, telegram_user_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.telegram_sales_prospects
                       WHERE creator_profile_id=%s AND fanvue_account_id=%s
                         AND telegram_user_id=%s""",
                    (creator_profile_id, fanvue_account_id, telegram_user_id),
                )
                row = cursor.fetchone()
        return self._model(row) if row else None

    def graduate(self, *, creator_profile_id, fanvue_account_id,
                 telegram_user_id, mapping_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE public.telegram_sales_prospects SET
                    graduated_mapping_id=COALESCE(graduated_mapping_id,%s),
                    graduated_at=COALESCE(graduated_at,NOW()),last_observed_at=NOW()
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND telegram_user_id=%s
                      AND (graduated_mapping_id IS NULL OR graduated_mapping_id=%s)
                    RETURNING *""", (mapping_id, creator_profile_id,
                    fanvue_account_id, telegram_user_id, mapping_id))
                row = cursor.fetchone()
        if row is None:
            raise ValueError("Telegram prospect graduated to another mapping.")
        return self._model(row)

    def merge_conversational_memory(self, *, creator_profile_id,
                                    fanvue_account_id, telegram_user_id,
                                    values):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE public.telegram_sales_prospects
                    SET preference_state=COALESCE(preference_state,'{}'::jsonb) || %s::jsonb,
                        last_observed_at=NOW()
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND telegram_user_id=%s RETURNING *""",
                    (json.dumps(dict(values)), creator_profile_id,
                     fanvue_account_id, telegram_user_id))
                row = cursor.fetchone()
        return self._model(row) if row else None

    def record_contact_block(self, *, creator_profile_id, fanvue_account_id,
                             telegram_user_id, reason, correlation_id):
        value = {
            "state": "PERMANENT_BLOCKED", "authority": "QUALIFYING_ABUSE",
            "reason": str(reason), "correlationId": str(correlation_id),
            "blockedAt": datetime.now(timezone.utc).isoformat(),
        }
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.telegram_sales_prospects
                   SET relationship_state=jsonb_set(
                       COALESCE(relationship_state,'{}'::jsonb),
                       '{telegramContactBlock}',%s::jsonb,TRUE),last_observed_at=NOW()
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND telegram_user_id=%s RETURNING *""",
                (json.dumps(value), creator_profile_id, fanvue_account_id,
                 telegram_user_id),
            )
            row = cursor.fetchone()
        return self._model(row) if row else None

    def record_supporter_boundary_delivery(self, *, creator_profile_id,
                                           fanvue_account_id, telegram_user_id,
                                           correlation_id, provider_message_id):
        value = {
            "appropriate": True, "delivered": True,
            "deliveredAt": datetime.now(timezone.utc).isoformat(),
            "correlationId": str(correlation_id),
            "providerMessageId": str(provider_message_id),
        }
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.telegram_sales_prospects
                   SET relationship_state=jsonb_set(
                       COALESCE(relationship_state,'{}'::jsonb),
                       '{supporterAttentionBoundary}',%s::jsonb,TRUE),
                       last_observed_at=NOW()
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND telegram_user_id=%s
                     AND COALESCE(relationship_state#>>'{supporterAttentionBoundary,delivered}','false')<>'true'
                   RETURNING *""",
                (json.dumps(value), creator_profile_id, fanvue_account_id,
                 telegram_user_id),
            )
            row = cursor.fetchone()
        return self._model(row) if row else self.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )

    def record_sales_progression(self, *, creator_profile_id,
                                 fanvue_account_id, telegram_user_id,
                                 progression, correlation_id):
        """Persist prospect progression once per inbound operation."""
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE public.telegram_sales_prospects
                    SET relationship_state=COALESCE(relationship_state,'{}'::jsonb)
                        || jsonb_build_object(
                            'salesProgression', %s::jsonb,
                            'salesProgressionCorrelationId', %s::text
                        ),
                        last_observed_at=NOW()
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND telegram_user_id=%s
                      AND COALESCE(
                          relationship_state->>'salesProgressionCorrelationId',''
                      )<>%s
                    RETURNING *""",
                    (json.dumps(dict(progression)), str(correlation_id),
                     creator_profile_id, fanvue_account_id,
                     telegram_user_id, str(correlation_id)))
                row = cursor.fetchone()
        if row is not None:
            return self._model(row)
        return self.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )

    def record_deferred_continuation(self, *, creator_profile_id,
                                     fanvue_account_id, telegram_user_id,
                                     source_inbound_message_id,
                                     source_correlation_id,
                                     purchase_intent_id,
                                     continuation_type="EXPLICIT_MORE"):
        value = {
            "state": "PENDING_ACKNOWLEDGEMENT",
            "sourceInboundMessageId": int(source_inbound_message_id),
            "sourceCorrelationId": str(source_correlation_id),
            "purchaseIntentId": str(purchase_intent_id),
            "continuationType": str(continuation_type),
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE public.telegram_sales_prospects
                    SET relationship_state=jsonb_set(
                        COALESCE(relationship_state,'{}'::jsonb),
                        '{deferredContinuation}',%s::jsonb,TRUE),
                        last_observed_at=NOW()
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND telegram_user_id=%s
                      AND COALESCE(relationship_state#>>'{deferredContinuation,sourceCorrelationId}','')<>%s
                    RETURNING *""", (json.dumps(value), creator_profile_id,
                    fanvue_account_id, telegram_user_id, str(source_correlation_id)))
                row = cursor.fetchone()
        return self._model(row) if row else self.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id)

    def transition_deferred_continuation(self, *, creator_profile_id,
                                         fanvue_account_id, telegram_user_id,
                                         from_states, target_state,
                                         correlation_id=None, reason=None):
        states = tuple(str(value) for value in from_states)
        patch = {"state": str(target_state), "updatedAt": datetime.now(timezone.utc).isoformat()}
        if correlation_id is not None:
            patch["claimCorrelationId"] = str(correlation_id)
        if reason is not None:
            patch["reason"] = str(reason)
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE public.telegram_sales_prospects
                    SET relationship_state=jsonb_set(
                        COALESCE(relationship_state,'{}'::jsonb),
                        '{deferredContinuation}',
                        COALESCE(relationship_state->'deferredContinuation','{}'::jsonb) || %s::jsonb,
                        TRUE),last_observed_at=NOW()
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND telegram_user_id=%s
                      AND relationship_state#>>'{deferredContinuation,state}'=ANY(%s)
                      AND (%s::text IS NULL OR
                           COALESCE(relationship_state#>>'{deferredContinuation,claimCorrelationId}',%s)= %s)
                    RETURNING *""", (json.dumps(patch), creator_profile_id,
                    fanvue_account_id, telegram_user_id, list(states),
                    correlation_id, str(correlation_id), str(correlation_id)))
                row = cursor.fetchone()
        return self._model(row) if row else None

    def record_session_proposal(self, *, creator_profile_id, fanvue_account_id,
                                telegram_user_id, correlation_id,
                                session_offering_id=None,
                                source_inbound=None,
                                delivery_correlation_id=None,
                                delivery_provider_message_id=None,
                                delivered_at=None, expires_at=None):
        delivered_at = delivered_at or datetime.now(timezone.utc)
        expires_at = expires_at or (delivered_at + timedelta(hours=24))
        value = {
            "state": "PENDING", "correlationId": str(correlation_id),
            "proposalId": str(correlation_id),
            "sourceInbound": str(source_inbound or correlation_id),
            "deliveryCorrelationId": str(
                delivery_correlation_id or correlation_id
            ),
            "deliveryProviderMessageId": (
                str(delivery_provider_message_id)
                if delivery_provider_message_id is not None else None
            ),
            "sessionOfferingId": (
                str(session_offering_id) if session_offering_id else None
            ),
            "createdAt": delivered_at.isoformat(),
            "deliveredAt": delivered_at.isoformat(),
            "expiresAt": expires_at.isoformat(),
            "sessionEscalationDecision": "PROPOSE_SESSION",
            "delivered": True,
            "consumed": False,
        }
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE public.telegram_sales_prospects
                    SET relationship_state=jsonb_set(
                        COALESCE(relationship_state,'{}'::jsonb),
                        '{sessionProposal}',%s::jsonb,TRUE),last_observed_at=NOW()
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND telegram_user_id=%s
                      AND COALESCE(relationship_state#>>'{sessionProposal,state}','')
                          NOT IN ('PENDING','ACCEPTED') RETURNING *""",
                    (json.dumps(value), creator_profile_id, fanvue_account_id,
                     telegram_user_id))
                row = cursor.fetchone()
        return self._model(row) if row else self.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )

    def transition_session_proposal(self, *, creator_profile_id,
                                    fanvue_account_id, telegram_user_id,
                                    target_state, reaction,
                                    reaction_source_inbound=None,
                                    invalidation_reason=None):
        patch = {"state": str(target_state), "reaction": str(reaction),
                 "updatedAt": datetime.now(timezone.utc).isoformat(),
                 "consumed": str(target_state) != "PENDING"}
        if reaction_source_inbound is not None:
            patch["reactionSourceInbound"] = str(reaction_source_inbound)
        if invalidation_reason is not None:
            patch["invalidationReason"] = str(invalidation_reason)
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE public.telegram_sales_prospects
                    SET relationship_state=jsonb_set(
                        COALESCE(relationship_state,'{}'::jsonb),
                        '{sessionProposal}',
                        COALESCE(relationship_state->'sessionProposal','{}'::jsonb)
                            || %s::jsonb,TRUE),last_observed_at=NOW()
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND telegram_user_id=%s
                      AND relationship_state#>>'{sessionProposal,state}'='PENDING'
                    RETURNING *""", (json.dumps(patch), creator_profile_id,
                    fanvue_account_id, telegram_user_id))
                row = cursor.fetchone()
        return self._model(row) if row else None

    @staticmethod
    def _model(row):
        values = dict(row)
        values["telegram_sales_prospect_id"] = UUID(str(values["telegram_sales_prospect_id"]))
        values["relationship_state"] = values.get("relationship_state") or {}
        values["preference_state"] = values.get("preference_state") or {}
        return TelegramSalesProspect(**values)
