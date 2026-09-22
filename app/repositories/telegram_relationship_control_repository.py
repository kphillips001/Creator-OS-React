import json
from uuid import uuid4
from contextlib import contextmanager
from app.database import get_db_connection
from app.models.telegram_relationship_control import (
    TelegramCommunicationDisposition, TelegramRelationshipControl,
    TelegramRelationshipMode,
)


class TelegramRelationshipControlRepository:
    def __init__(self, connection_factory=get_db_connection): self.connection_factory=connection_factory

    def get(self, *, creator_profile_id, fanvue_account_id, telegram_user_id, telegram_chat_id=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM public.telegram_relationship_controls
                WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s""",
                (creator_profile_id,fanvue_account_id,telegram_user_id))
            row=cursor.fetchone()
        if row: return self._model(row)
        return TelegramRelationshipControl(None,int(creator_profile_id),int(fanvue_account_id),
            int(telegram_user_id),int(telegram_chat_id or telegram_user_id),
            TelegramRelationshipMode.AVA_AUTO,0,
            content_selling_enabled=True, session_selling_enabled=True)

    def transition(self, *, creator_profile_id, fanvue_account_id, telegram_user_id,
                   telegram_chat_id, mode, changed_by, reason=None,
                   telegram_identity_mapping_id=None, local_fanvue_user_id=None):
        selected=TelegramRelationshipMode(str(getattr(mode,"value",mode)))
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"telegram-relationship:{creator_profile_id}:{fanvue_account_id}:{telegram_user_id}",),
            )
            cursor.execute("""SELECT * FROM public.telegram_relationship_controls
                WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s""",
                (creator_profile_id,fanvue_account_id,telegram_user_id))
            existing=cursor.fetchone()
            if existing is None and selected is TelegramRelationshipMode.AVA_AUTO:
                return TelegramRelationshipControl(None,int(creator_profile_id),int(fanvue_account_id),
                    int(telegram_user_id),int(telegram_chat_id),TelegramRelationshipMode.AVA_AUTO,0,
                    changed_by="SYSTEM_DEFAULT", content_selling_enabled=True,
                    session_selling_enabled=True)
            cursor.execute("""INSERT INTO public.telegram_relationship_controls (
                relationship_control_id,creator_profile_id,fanvue_account_id,telegram_user_id,
                telegram_chat_id,telegram_identity_mapping_id,local_fanvue_user_id,mode,
                control_version,changed_by,reason)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s)
                ON CONFLICT (creator_profile_id,fanvue_account_id,telegram_user_id)
                DO UPDATE SET telegram_chat_id=EXCLUDED.telegram_chat_id,
                  telegram_identity_mapping_id=COALESCE(EXCLUDED.telegram_identity_mapping_id,telegram_relationship_controls.telegram_identity_mapping_id),
                  local_fanvue_user_id=COALESCE(EXCLUDED.local_fanvue_user_id,telegram_relationship_controls.local_fanvue_user_id),
                  mode=EXCLUDED.mode,
                  control_version=CASE WHEN telegram_relationship_controls.mode<>EXCLUDED.mode
                    THEN telegram_relationship_controls.control_version+1 ELSE telegram_relationship_controls.control_version END,
                  changed_at=CASE WHEN telegram_relationship_controls.mode<>EXCLUDED.mode THEN NOW() ELSE telegram_relationship_controls.changed_at END,
                  changed_by=CASE WHEN telegram_relationship_controls.mode<>EXCLUDED.mode THEN EXCLUDED.changed_by ELSE telegram_relationship_controls.changed_by END,
                  reason=CASE WHEN telegram_relationship_controls.mode<>EXCLUDED.mode THEN EXCLUDED.reason ELSE telegram_relationship_controls.reason END,
                  updated_at=NOW() RETURNING *""",(uuid4(),creator_profile_id,fanvue_account_id,
                    telegram_user_id,telegram_chat_id,telegram_identity_mapping_id,local_fanvue_user_id,
                    selected.value,changed_by,reason))
            return self._model(cursor.fetchone())

    def set_permissions(self, *, creator_profile_id, fanvue_account_id,
                        telegram_user_id, telegram_chat_id,
                        content_selling_enabled=None,
                        session_selling_enabled=None,
                        changed_by="CREATOR_OS_OPERATOR", reason=None,
                        telegram_identity_mapping_id=None,
                        local_fanvue_user_id=None):
        if content_selling_enabled is None and session_selling_enabled is None:
            raise ValueError("At least one customer selling permission is required.")
        for value in (content_selling_enabled, session_selling_enabled):
            if value is not None and not isinstance(value, bool):
                raise ValueError("Customer selling permissions must be boolean.")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"telegram-relationship:{creator_profile_id}:{fanvue_account_id}:{telegram_user_id}",),
            )
            cursor.execute("""INSERT INTO public.telegram_relationship_controls (
                relationship_control_id,creator_profile_id,fanvue_account_id,
                telegram_user_id,telegram_chat_id,telegram_identity_mapping_id,
                local_fanvue_user_id,mode,content_selling_enabled,
                session_selling_enabled,control_version,changed_by,reason)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'AVA_AUTO',COALESCE(%s,TRUE),
                        COALESCE(%s,TRUE),1,%s,%s)
                ON CONFLICT (creator_profile_id,fanvue_account_id,telegram_user_id)
                DO UPDATE SET
                  telegram_chat_id=EXCLUDED.telegram_chat_id,
                  telegram_identity_mapping_id=COALESCE(EXCLUDED.telegram_identity_mapping_id,telegram_relationship_controls.telegram_identity_mapping_id),
                  local_fanvue_user_id=COALESCE(EXCLUDED.local_fanvue_user_id,telegram_relationship_controls.local_fanvue_user_id),
                  content_selling_enabled=COALESCE(%s,telegram_relationship_controls.content_selling_enabled),
                  session_selling_enabled=COALESCE(%s,telegram_relationship_controls.session_selling_enabled),
                  control_version=CASE WHEN
                    telegram_relationship_controls.content_selling_enabled IS DISTINCT FROM COALESCE(%s,telegram_relationship_controls.content_selling_enabled)
                    OR telegram_relationship_controls.session_selling_enabled IS DISTINCT FROM COALESCE(%s,telegram_relationship_controls.session_selling_enabled)
                    THEN telegram_relationship_controls.control_version+1
                    ELSE telegram_relationship_controls.control_version END,
                  changed_at=CASE WHEN
                    telegram_relationship_controls.content_selling_enabled IS DISTINCT FROM COALESCE(%s,telegram_relationship_controls.content_selling_enabled)
                    OR telegram_relationship_controls.session_selling_enabled IS DISTINCT FROM COALESCE(%s,telegram_relationship_controls.session_selling_enabled)
                    THEN NOW() ELSE telegram_relationship_controls.changed_at END,
                  changed_by=CASE WHEN
                    telegram_relationship_controls.content_selling_enabled IS DISTINCT FROM COALESCE(%s,telegram_relationship_controls.content_selling_enabled)
                    OR telegram_relationship_controls.session_selling_enabled IS DISTINCT FROM COALESCE(%s,telegram_relationship_controls.session_selling_enabled)
                    THEN EXCLUDED.changed_by ELSE telegram_relationship_controls.changed_by END,
                  reason=CASE WHEN
                    telegram_relationship_controls.content_selling_enabled IS DISTINCT FROM COALESCE(%s,telegram_relationship_controls.content_selling_enabled)
                    OR telegram_relationship_controls.session_selling_enabled IS DISTINCT FROM COALESCE(%s,telegram_relationship_controls.session_selling_enabled)
                    THEN EXCLUDED.reason ELSE telegram_relationship_controls.reason END,
                  updated_at=NOW() RETURNING *""",
                (uuid4(),creator_profile_id,fanvue_account_id,telegram_user_id,
                 telegram_chat_id,telegram_identity_mapping_id,local_fanvue_user_id,
                 content_selling_enabled,session_selling_enabled,changed_by,reason,
                 content_selling_enabled,session_selling_enabled,
                 content_selling_enabled,session_selling_enabled,
                 content_selling_enabled,session_selling_enabled,
                 content_selling_enabled,session_selling_enabled,
                 content_selling_enabled,session_selling_enabled))
            return self._model(cursor.fetchone())

    def set_ignored(self, *, creator_profile_id, fanvue_account_id,
                    telegram_user_id, telegram_chat_id, ignored, changed_by,
                    reason=None, expected_control_version=None,
                    telegram_identity_mapping_id=None,
                    local_fanvue_user_id=None):
        """Atomically change Ignore and neutralize only definitely-unsent work."""
        disposition = "IGNORED" if ignored else "ACTIVE"
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (
                f"telegram-relationship:{creator_profile_id}:{fanvue_account_id}:{telegram_user_id}",))
            cursor.execute("""INSERT INTO public.telegram_relationship_controls(
                relationship_control_id,creator_profile_id,fanvue_account_id,
                telegram_user_id,telegram_chat_id,telegram_identity_mapping_id,
                local_fanvue_user_id,mode,control_version,changed_by)
                VALUES(%s,%s,%s,%s,%s,%s,%s,'AVA_AUTO',0,'SYSTEM_DEFAULT')
                ON CONFLICT(creator_profile_id,fanvue_account_id,telegram_user_id)
                DO UPDATE SET telegram_chat_id=EXCLUDED.telegram_chat_id,
                  telegram_identity_mapping_id=COALESCE(EXCLUDED.telegram_identity_mapping_id,telegram_relationship_controls.telegram_identity_mapping_id),
                  local_fanvue_user_id=COALESCE(EXCLUDED.local_fanvue_user_id,telegram_relationship_controls.local_fanvue_user_id)
                RETURNING *""", (uuid4(),creator_profile_id,fanvue_account_id,
                    telegram_user_id,telegram_chat_id,telegram_identity_mapping_id,
                    local_fanvue_user_id))
            current = self._model(cursor.fetchone())
            if current.communication_disposition.value == disposition:
                return current, False, {"ordinary": 0, "commercial": 0}
            if (expected_control_version is not None and
                    int(expected_control_version) != current.control_version):
                raise ValueError("Relationship control version is stale.")
            cursor.execute("""SELECT GREATEST(
                COALESCE((SELECT MAX(inbound_telegram_message_id) FROM ordinary_chat_reply_operations
                  WHERE telegram_account_scope='AVA_TELETHON_PRIVATE' AND telegram_chat_id=%s
                    AND inbound_sender_telegram_user_id=%s),0),
                COALESCE((SELECT MAX(telegram_message_id) FROM telegram_private_inbound_messages
                  WHERE telegram_account_scope='AVA_TELETHON_PRIVATE' AND telegram_chat_id=%s
                    AND telegram_user_id=%s),0)) AS boundary""",
                (telegram_chat_id,telegram_user_id,telegram_chat_id,telegram_user_id))
            boundary = int(cursor.fetchone()["boundary"] or 0)
            evidence = {"ordinary": 0, "commercial": 0, "ignoredBacklog": 0}
            if ignored:
                cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                    state='SUPPRESSED',last_error='RELATIONSHIP_IGNORED',next_retry_at=NULL,
                    claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW(),
                    delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||
                      jsonb_build_object('relationshipIgnore',jsonb_build_object(
                        'disposition','IGNORED','controlVersion',%s))
                  WHERE telegram_account_scope='AVA_TELETHON_PRIVATE'
                    AND telegram_chat_id=%s AND inbound_sender_telegram_user_id=%s
                    AND state IN ('PENDING_GENERATION','GENERATED','RETRYABLE')
                    AND outbound_telegram_message_id IS NULL""",
                    (current.control_version+1,telegram_chat_id,telegram_user_id))
                evidence["ordinary"] = cursor.rowcount
                cursor.execute("""UPDATE telegram_sales_delivery_operations SET
                    state='SUPPRESSED',failure_reason='RELATIONSHIP_IGNORED',updated_at=NOW()
                  WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_chat_id=%s
                    AND state IN ('CREATED','RETRYABLE') AND outbound_telegram_message_id IS NULL""",
                    (creator_profile_id,fanvue_account_id,telegram_chat_id))
                evidence["commercial"] = cursor.rowcount
            else:
                cursor.execute("""UPDATE telegram_private_inbound_messages SET
                    reconciliation_state='NO_RESPONSE_REQUIRED',reconciled_at=NOW(),updated_at=NOW()
                  WHERE telegram_account_scope='AVA_TELETHON_PRIVATE'
                    AND creator_profile_id=%s AND fanvue_account_id=%s
                    AND telegram_user_id=%s AND telegram_chat_id=%s
                    AND telegram_message_id<=%s AND reconciliation_state='CAPTURED'""",
                    (creator_profile_id,fanvue_account_id,telegram_user_id,
                     telegram_chat_id,boundary))
                evidence["ignoredBacklog"] = cursor.rowcount
            cursor.execute("""UPDATE telegram_relationship_controls SET
                communication_disposition=%s,ignore_version=ignore_version+1,
                control_version=control_version+1,
                ignored_at=CASE WHEN %s THEN NOW() ELSE ignored_at END,
                ignored_by=CASE WHEN %s THEN %s ELSE ignored_by END,
                ignore_reason=CASE WHEN %s THEN %s ELSE ignore_reason END,
                unignored_at=CASE WHEN %s THEN unignored_at ELSE NOW() END,
                unignored_by=CASE WHEN %s THEN unignored_by ELSE %s END,
                resume_after_inbound_message_id=CASE WHEN %s THEN resume_after_inbound_message_id ELSE %s END,
                changed_at=NOW(),changed_by=%s,reason=%s,updated_at=NOW()
              WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s
              RETURNING *""", (disposition,ignored,ignored,changed_by,ignored,reason,
                    ignored,ignored,changed_by,ignored,boundary,changed_by,reason,
                    creator_profile_id,fanvue_account_id,telegram_user_id))
            updated = self._model(cursor.fetchone())
            cursor.execute("""INSERT INTO telegram_relationship_ignore_events(
                event_id,creator_profile_id,fanvue_account_id,telegram_user_id,
                telegram_chat_id,action,ignore_version,control_version,changed_by,
                reason,resume_after_inbound_message_id,neutralization_evidence)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                (uuid4(),creator_profile_id,fanvue_account_id,telegram_user_id,
                 telegram_chat_id,("IGNORED" if ignored else "UNIGNORED"),updated.ignore_version,
                 updated.control_version,changed_by,reason,
                 updated.resume_after_inbound_message_id,json.dumps(evidence)))
            return updated, True, evidence

    @contextmanager
    def autonomous_send_guard(self, *, creator_profile_id, fanvue_account_id,
                              telegram_user_id, telegram_chat_id, captured_version=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"telegram-relationship:{creator_profile_id}:{fanvue_account_id}:{telegram_user_id}",))
            cursor.execute("""SELECT * FROM public.telegram_relationship_controls
                WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s""",
                (creator_profile_id,fanvue_account_id,telegram_user_id))
            row=cursor.fetchone()
            control=self._model(row) if row else TelegramRelationshipControl(
                None,int(creator_profile_id),int(fanvue_account_id),int(telegram_user_id),
                int(telegram_chat_id),TelegramRelationshipMode.AVA_AUTO,0,
                content_selling_enabled=True, session_selling_enabled=True)
            allowed=not control.manual and not control.ignored and (captured_version is None or
                                             int(captured_version)==control.control_version)
            yield allowed,control

    @contextmanager
    def manual_send_guard(self, *, creator_profile_id, fanvue_account_id,
                          telegram_user_id, expected_version):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"telegram-relationship:{creator_profile_id}:{fanvue_account_id}:{telegram_user_id}",))
            cursor.execute("""SELECT * FROM telegram_relationship_controls
                WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s""",
                (creator_profile_id,fanvue_account_id,telegram_user_id))
            row=cursor.fetchone()
            if not row or row['mode']!='HUMAN_OPERATOR' or row['control_version']!=expected_version:
                raise ValueError('Manual Mode/control version changed before delivery.')
            yield self._model(row)

    def touch_manual_activity(self, control):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.telegram_relationship_controls SET
                last_manual_activity_at=NOW(),updated_at=NOW()
                WHERE relationship_control_id=%s RETURNING *""",(control.relationship_control_id,))
            return self._model(cursor.fetchone())

    @staticmethod
    def _model(row):
        value=dict(row)
        return TelegramRelationshipControl(
            relationship_control_id=value.get("relationship_control_id"),
            creator_profile_id=int(value["creator_profile_id"]),fanvue_account_id=int(value["fanvue_account_id"]),
            telegram_user_id=int(value["telegram_user_id"]),telegram_chat_id=int(value["telegram_chat_id"]),
            mode=TelegramRelationshipMode(value["mode"]),control_version=int(value["control_version"]),
            changed_at=value.get("changed_at"),changed_by=value.get("changed_by") or "SYSTEM_DEFAULT",
            reason=value.get("reason"),last_manual_activity_at=value.get("last_manual_activity_at"),
            telegram_identity_mapping_id=value.get("telegram_identity_mapping_id"),
            local_fanvue_user_id=value.get("local_fanvue_user_id"),
            content_selling_enabled=bool(value.get("content_selling_enabled", False)),
            session_selling_enabled=bool(value.get("session_selling_enabled", False)),
            communication_disposition=TelegramCommunicationDisposition(
                value.get("communication_disposition") or "ACTIVE"),
            ignore_version=int(value.get("ignore_version") or 0),
            ignored_at=value.get("ignored_at"), ignored_by=value.get("ignored_by"),
            ignore_reason=value.get("ignore_reason"),
            unignored_at=value.get("unignored_at"), unignored_by=value.get("unignored_by"),
            resume_after_inbound_message_id=value.get("resume_after_inbound_message_id"))
