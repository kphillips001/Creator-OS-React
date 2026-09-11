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
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s AND scope='GLOBAL'
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
                     AND fanvue_account_id=%s AND scope='GLOBAL'""",
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

    def list_customer(self, *, creator_profile_id: int, fanvue_account_id: int,
                      customer_fanvue_user_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.ai_runtime_instructions
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND scope='CUSTOMER' AND customer_fanvue_user_id=%s
                   ORDER BY CASE status WHEN 'ENABLED' THEN 0 WHEN 'DISABLED' THEN 1
                            WHEN 'REQUIRES_IMPLEMENTATION' THEN 2 WHEN 'DRAFT' THEN 3 ELSE 4 END,
                            priority,instruction_id""",
                (creator_profile_id, fanvue_account_id, customer_fanvue_user_id),
            )
            return [AiTrainingInstruction.from_row(row) for row in cursor.fetchall()]

    def list_all_customer(self, *, creator_profile_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.ai_runtime_instructions
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s AND scope='CUSTOMER'
                   ORDER BY updated_at DESC,instruction_id""",
                (creator_profile_id, fanvue_account_id),
            )
            return [AiTrainingInstruction.from_row(row) for row in cursor.fetchall()]

    def active_customer_conversation_rules(self, *, creator_profile_id: int,
                                           fanvue_account_id: int,
                                           customer_fanvue_user_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.ai_runtime_instructions
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND scope='CUSTOMER' AND customer_fanvue_user_id=%s
                     AND instruction_type='CONVERSATION_RULE' AND enforcement_mode='PROMPT'
                     AND status='ENABLED' ORDER BY priority,instruction_id""",
                (creator_profile_id, fanvue_account_id, customer_fanvue_user_id),
            )
            return [AiTrainingInstruction.from_row(row) for row in cursor.fetchall()]

    def customer_treatment(self, *, creator_profile_id: int, fanvue_account_id: int,
                           customer_fanvue_user_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.ai_runtime_instructions
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND scope='CUSTOMER' AND customer_fanvue_user_id=%s
                     AND instruction_type='CUSTOMER_TREATMENT_POLICY'
                     AND policy_key='CUSTOMER_TREATMENT_POLICY'""",
                (creator_profile_id, fanvue_account_id, customer_fanvue_user_id),
            )
            row = cursor.fetchone()
        return AiTrainingInstruction.from_row(row) if row else None

    def apply_customer_treatment(self, *, creator_profile_id: int, fanvue_account_id: int,
                                 customer_fanvue_user_id: int, configuration: dict,
                                 normalized: str, enabled: bool,
                                 original_text: str | None = None):
        status = "ENABLED" if enabled else "DISABLED"
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.ai_runtime_instructions
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s AND scope='CUSTOMER'
                     AND customer_fanvue_user_id=%s
                     AND instruction_type='CUSTOMER_TREATMENT_POLICY'
                     AND policy_key='CUSTOMER_TREATMENT_POLICY' FOR UPDATE""",
                (creator_profile_id, fanvue_account_id, customer_fanvue_user_id),
            )
            current = cursor.fetchone()
            if current:
                cursor.execute(
                    """UPDATE public.ai_runtime_instructions SET
                           original_operator_text=%s,normalized_instruction=%s,
                           policy_configuration=%s,status=%s,version=version+1,updated_at=NOW(),
                           enabled_at=CASE WHEN %s='ENABLED' THEN NOW() ELSE enabled_at END,
                           disabled_at=CASE WHEN %s='DISABLED' THEN NOW() ELSE disabled_at END
                       WHERE instruction_id=%s AND creator_profile_id=%s
                         AND fanvue_account_id=%s AND customer_fanvue_user_id=%s
                         AND instruction_type='CUSTOMER_TREATMENT_POLICY' RETURNING *""",
                    (original_text or normalized, normalized, Json(configuration), status, status, status,
                     current["instruction_id"], creator_profile_id, fanvue_account_id,
                     customer_fanvue_user_id),
                )
                row = cursor.fetchone()
                action = "EDITED" if enabled else "DISABLED"
            else:
                instruction_id = uuid4()
                cursor.execute(
                    """INSERT INTO public.ai_runtime_instructions(
                           instruction_id,creator_profile_id,fanvue_account_id,scope,
                           customer_fanvue_user_id,instruction_type,original_operator_text,
                           normalized_instruction,status,priority,source,classification_reason,
                           policy_key,enforcement_mode,policy_configuration,enabled_at,disabled_at)
                       VALUES(%s,%s,%s,'CUSTOMER',%s,'CUSTOMER_TREATMENT_POLICY',%s,%s,%s,100,
                              'OPERATOR','Bounded customer treatment modifier; protected authorities remain unchanged.',
                              'CUSTOMER_TREATMENT_POLICY','BACKEND',%s,
                              CASE WHEN %s='ENABLED' THEN NOW() ELSE NULL END,
                              CASE WHEN %s='DISABLED' THEN NOW() ELSE NULL END) RETURNING *""",
                    (instruction_id, creator_profile_id, fanvue_account_id,
                     customer_fanvue_user_id, original_text or normalized, normalized, status,
                     Json(configuration), status, status),
                )
                row = cursor.fetchone()
                action = "CREATED"
            self._revision(cursor, row, action, {
                "scope": "CUSTOMER", "treatment": configuration,
                "runtimeEffect": "BOUNDED_PHASE_2B",
            })
        return AiTrainingInstruction.from_row(row)

    def disable_customer_treatment(self, instruction_id, *, creator_profile_id: int,
                                   fanvue_account_id: int,
                                   customer_fanvue_user_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.ai_runtime_instructions SET status='DISABLED',
                       version=version+1,updated_at=NOW(),disabled_at=NOW()
                   WHERE instruction_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s
                     AND scope='CUSTOMER' AND customer_fanvue_user_id=%s
                     AND instruction_type='CUSTOMER_TREATMENT_POLICY'
                     AND status='ENABLED' RETURNING *""",
                (instruction_id, creator_profile_id, fanvue_account_id,
                 customer_fanvue_user_id),
            )
            row = cursor.fetchone()
            if row:
                self._revision(cursor, row, "DISABLED", {
                    "scope": "CUSTOMER", "treatment": row.get("policy_configuration") or {},
                    "runtimeEffect": "BOUNDED_PHASE_2B",
                })
        return AiTrainingInstruction.from_row(row) if row else None

    def create_customer(self, *, creator_profile_id: int, fanvue_account_id: int,
                        customer_fanvue_user_id: int, original_text: str,
                        normalized: str, status: str, priority: int,
                        classification_reason: str):
        instruction_id = uuid4()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.ai_runtime_instructions(
                       instruction_id,creator_profile_id,fanvue_account_id,scope,
                       customer_fanvue_user_id,instruction_type,original_operator_text,
                       normalized_instruction,status,priority,source,classification_reason,
                       policy_key,enforcement_mode,policy_configuration,enabled_at)
                   VALUES(%s,%s,%s,'CUSTOMER',%s,'CONVERSATION_RULE',%s,%s,%s,%s,
                          'OPERATOR',%s,NULL,'PROMPT','{}'::jsonb,
                          CASE WHEN %s='ENABLED' THEN NOW() ELSE NULL END) RETURNING *""",
                (instruction_id, creator_profile_id, fanvue_account_id,
                 customer_fanvue_user_id, original_text, normalized, status, priority,
                 classification_reason, status),
            )
            row = cursor.fetchone()
            self._revision(cursor, row, "CREATED", {"scope": "CUSTOMER"})
        return AiTrainingInstruction.from_row(row)

    def customer_duplicate_exists(self, *, creator_profile_id: int,
                                  fanvue_account_id: int,
                                  customer_fanvue_user_id: int,
                                  normalized: str, exclude_instruction_id=None) -> bool:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT EXISTS(SELECT 1 FROM public.ai_runtime_instructions
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND scope='CUSTOMER' AND customer_fanvue_user_id=%s
                     AND LOWER(BTRIM(normalized_instruction))=LOWER(BTRIM(%s))
                     AND status<>'ARCHIVED' AND (%s IS NULL OR instruction_id<>%s)) AS found""",
                (creator_profile_id, fanvue_account_id, customer_fanvue_user_id,
                 normalized, exclude_instruction_id, exclude_instruction_id),
            )
            return bool(cursor.fetchone()["found"])

    def get_customer(self, instruction_id, *, creator_profile_id: int,
                     fanvue_account_id: int, customer_fanvue_user_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.ai_runtime_instructions WHERE instruction_id=%s
                   AND creator_profile_id=%s AND fanvue_account_id=%s AND scope='CUSTOMER'
                   AND customer_fanvue_user_id=%s AND instruction_type='CONVERSATION_RULE'""",
                (instruction_id, creator_profile_id, fanvue_account_id, customer_fanvue_user_id),
            )
            row = cursor.fetchone()
        return AiTrainingInstruction.from_row(row) if row else None

    def get_customer_in_account(self, instruction_id, *, creator_profile_id: int,
                                fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.ai_runtime_instructions WHERE instruction_id=%s
                   AND creator_profile_id=%s AND fanvue_account_id=%s AND scope='CUSTOMER'""",
                (instruction_id, creator_profile_id, fanvue_account_id),
            )
            row = cursor.fetchone()
        return AiTrainingInstruction.from_row(row) if row else None

    def edit_customer(self, instruction_id, *, creator_profile_id: int,
                      fanvue_account_id: int, customer_fanvue_user_id: int,
                      original_text: str, normalized: str, priority: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.ai_runtime_instructions SET original_operator_text=%s,
                       normalized_instruction=%s,priority=%s,version=version+1,updated_at=NOW()
                   WHERE instruction_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s
                     AND scope='CUSTOMER' AND customer_fanvue_user_id=%s
                     AND instruction_type='CONVERSATION_RULE'
                     AND status<>'ARCHIVED' RETURNING *""",
                (original_text, normalized, priority, instruction_id, creator_profile_id,
                 fanvue_account_id, customer_fanvue_user_id),
            )
            row = cursor.fetchone()
            if row: self._revision(cursor, row, "EDITED", {"scope": "CUSTOMER"})
        return AiTrainingInstruction.from_row(row) if row else None

    def transition_customer(self, instruction_id, *, creator_profile_id: int,
                            fanvue_account_id: int, customer_fanvue_user_id: int,
                            action: str):
        target = {"enable": "ENABLED", "disable": "DISABLED", "archive": "ARCHIVED"}[action]
        allowed = {"enable": ("DRAFT", "DISABLED"), "disable": ("ENABLED",),
                   "archive": ("DRAFT", "ENABLED", "DISABLED")}[action]
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.ai_runtime_instructions SET status=%s,version=version+1,
                       updated_at=NOW(),enabled_at=CASE WHEN %s='ENABLED' THEN NOW() ELSE enabled_at END,
                       disabled_at=CASE WHEN %s='DISABLED' THEN NOW() ELSE disabled_at END,
                       archived_at=CASE WHEN %s='ARCHIVED' THEN NOW() ELSE archived_at END
                   WHERE instruction_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s
                     AND scope='CUSTOMER' AND customer_fanvue_user_id=%s
                     AND instruction_type='CONVERSATION_RULE'
                     AND status=ANY(%s) RETURNING *""",
                (target, target, target, target, instruction_id, creator_profile_id,
                 fanvue_account_id, customer_fanvue_user_id, list(allowed)),
            )
            row = cursor.fetchone()
            if row: self._revision(cursor, row, action.upper() + "D" if action != "disable" else "DISABLED", {"scope": "CUSTOMER"})
        return AiTrainingInstruction.from_row(row) if row else None

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
                     AND fanvue_account_id=%s AND scope='GLOBAL' AND status<>'ARCHIVED'
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
                     AND fanvue_account_id=%s AND scope='GLOBAL' AND status=ANY(%s)
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
