from uuid import uuid4
from contextlib import contextmanager
from app.database import get_db_connection
from app.models.telegram_relationship_control import TelegramRelationshipControl, TelegramRelationshipMode


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
            TelegramRelationshipMode.AVA_AUTO,0)

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
                    changed_by="SYSTEM_DEFAULT")
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
                VALUES (%s,%s,%s,%s,%s,%s,%s,'AVA_AUTO',COALESCE(%s,FALSE),
                        COALESCE(%s,FALSE),1,%s,%s)
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
                int(telegram_chat_id),TelegramRelationshipMode.AVA_AUTO,0)
            allowed=not control.manual and (captured_version is None or
                                             int(captured_version)==control.control_version)
            yield allowed,control

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
            session_selling_enabled=bool(value.get("session_selling_enabled", False)))
