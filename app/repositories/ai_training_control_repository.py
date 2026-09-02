"""PostgreSQL authority for versioned runtime AI instructions."""
import json
from uuid import uuid4
from psycopg.types.json import Json

from app.database import get_db_connection
from app.models.ai_training_control import AiTrainingInstruction


class AiTrainingControlRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def list(self, *, creator_profile_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.ai_runtime_instructions
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                   ORDER BY CASE status WHEN 'ENABLED' THEN 0 WHEN 'DISABLED' THEN 1
                            WHEN 'REQUIRES_IMPLEMENTATION' THEN 2 WHEN 'DRAFT' THEN 3 ELSE 4 END,
                            priority,instruction_id""",
                (creator_profile_id, fanvue_account_id),
            )
            return [AiTrainingInstruction.from_row(row) for row in cursor.fetchall()]

    def get(self, instruction_id, *, creator_profile_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.ai_runtime_instructions
                   WHERE instruction_id=%s AND creator_profile_id=%s
                     AND fanvue_account_id=%s""",
                (instruction_id, creator_profile_id, fanvue_account_id),
            )
            row = cursor.fetchone()
        return AiTrainingInstruction.from_row(row) if row else None

    def active_global_conversation_rules(self, *, creator_profile_id: int,
                                         fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.ai_runtime_instructions
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND scope='GLOBAL' AND instruction_type='CONVERSATION_RULE'
                     AND status='ENABLED'
                   ORDER BY priority,instruction_id""",
                (creator_profile_id, fanvue_account_id),
            )
            return [AiTrainingInstruction.from_row(row) for row in cursor.fetchall()]

    def is_backend_policy_enabled(self, *, creator_profile_id: int,
                                  fanvue_account_id: int, policy_key: str) -> bool:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT EXISTS(SELECT 1 FROM public.ai_runtime_instructions
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND scope='GLOBAL' AND instruction_type='SAFETY_HARD_STOP'
                     AND policy_key=%s AND enforcement_mode='BACKEND'
                     AND status='ENABLED') AS enabled""",
                (creator_profile_id, fanvue_account_id, policy_key),
            )
            return bool(cursor.fetchone()["enabled"])

    def create(self, *, creator_profile_id: int, fanvue_account_id: int,
               instruction_type: str, original_text: str, normalized: str,
               status: str, priority: int, classification_reason: str | None,
               policy_key: str | None = None, enforcement_mode: str = "PROMPT",
               policy_configuration: dict | None = None):
        instruction_id = uuid4()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.ai_runtime_instructions(
                       instruction_id,creator_profile_id,fanvue_account_id,scope,
                       instruction_type,original_operator_text,normalized_instruction,
                       status,priority,source,classification_reason,policy_key,
                       enforcement_mode,policy_configuration,enabled_at)
                   VALUES(%s,%s,%s,'GLOBAL',%s,%s,%s,%s,%s,'OPERATOR',%s,%s,%s,%s,
                          CASE WHEN %s='ENABLED' THEN NOW() ELSE NULL END)
                   RETURNING *""",
                (instruction_id, creator_profile_id, fanvue_account_id,
                 instruction_type, original_text, normalized, status, priority,
                 classification_reason, policy_key, enforcement_mode,
                 Json(policy_configuration or {}), status),
            )
            row = cursor.fetchone()
            self._revision(cursor, row, "CREATED", {"activationRequested": status == "ENABLED"})
        return AiTrainingInstruction.from_row(row)

    def edit(self, instruction_id, *, creator_profile_id: int, fanvue_account_id: int,
             instruction_type: str, original_text: str, normalized: str,
             status: str, priority: int, classification_reason: str | None,
             policy_key: str | None = None, enforcement_mode: str = "PROMPT",
             policy_configuration: dict | None = None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.ai_runtime_instructions SET
                       instruction_type=%s,original_operator_text=%s,
                       normalized_instruction=%s,status=%s,priority=%s,
                       classification_reason=%s,policy_key=%s,enforcement_mode=%s,
                       policy_configuration=%s,
                       version=version+1,updated_at=NOW(),
                       enabled_at=CASE WHEN %s='ENABLED' THEN COALESCE(enabled_at,NOW()) ELSE enabled_at END,
                       disabled_at=CASE WHEN %s='REQUIRES_IMPLEMENTATION' THEN NOW() ELSE disabled_at END
                   WHERE instruction_id=%s AND creator_profile_id=%s
                     AND fanvue_account_id=%s AND status<>'ARCHIVED'
                   RETURNING *""",
                (instruction_type, original_text, normalized, status, priority,
                 classification_reason, policy_key, enforcement_mode,
                 Json(policy_configuration or {}), status, status, instruction_id,
                 creator_profile_id, fanvue_account_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            self._revision(cursor, row, "EDITED", {})
        return AiTrainingInstruction.from_row(row)

    def transition(self, instruction_id, *, creator_profile_id: int,
                   fanvue_account_id: int, action: str):
        target = {"enable": "ENABLED", "disable": "DISABLED", "archive": "ARCHIVED"}[action]
        allowed = {
            "enable": ("DRAFT", "DISABLED"),
            "disable": ("ENABLED",),
            "archive": ("DRAFT", "ENABLED", "DISABLED", "REQUIRES_IMPLEMENTATION"),
        }[action]
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.ai_runtime_instructions SET
                       status=%s,version=version+1,updated_at=NOW(),
                       enabled_at=CASE WHEN %s='ENABLED' THEN NOW() ELSE enabled_at END,
                       disabled_at=CASE WHEN %s='DISABLED' THEN NOW() ELSE disabled_at END,
                       archived_at=CASE WHEN %s='ARCHIVED' THEN NOW() ELSE archived_at END
                   WHERE instruction_id=%s AND creator_profile_id=%s
                     AND fanvue_account_id=%s AND status=ANY(%s)
                   RETURNING *""",
                (target, target, target, target, instruction_id, creator_profile_id,
                 fanvue_account_id, list(allowed)),
            )
            row = cursor.fetchone()
            if not row:
                return None
            self._revision(cursor, row, action.upper() + "D" if action != "disable" else "DISABLED", {})
        return AiTrainingInstruction.from_row(row)

    def revisions(self, instruction_id, *, creator_profile_id: int,
                  fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT revision.* FROM public.ai_runtime_instruction_revisions revision
                   JOIN public.ai_runtime_instructions instruction USING(instruction_id)
                   WHERE revision.instruction_id=%s AND instruction.creator_profile_id=%s
                     AND instruction.fanvue_account_id=%s ORDER BY revision.version DESC""",
                (instruction_id, creator_profile_id, fanvue_account_id),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _revision(cursor, row, action: str, evidence: dict):
        cursor.execute(
            """INSERT INTO public.ai_runtime_instruction_revisions(
                   revision_id,instruction_id,version,action,original_operator_text,
                   normalized_instruction,instruction_type,status,priority,source,
                   classification_reason,policy_key,enforcement_mode,policy_configuration,evidence)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
            (uuid4(), row["instruction_id"], row["version"], action,
             row["original_operator_text"], row["normalized_instruction"],
             row["instruction_type"], row["status"], row["priority"], row["source"],
             row["classification_reason"], row.get("policy_key"),
             row.get("enforcement_mode") or "PROMPT", Json(row.get("policy_configuration") or {}),
             json.dumps(evidence)),
        )
