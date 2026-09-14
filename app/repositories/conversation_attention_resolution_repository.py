"""Scoped persistence and single-use claims for attention resolution."""
from __future__ import annotations

import json
from contextlib import contextmanager
from uuid import UUID, uuid4

from app.database import get_db_connection


class ConversationAttentionResolutionRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    @contextmanager
    def inspection_singleflight(self, request_id):
        """Cross-process lock for one operator inspection intent."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))",(str(request_id),))
            try:
                yield
            finally:
                cursor.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))",(str(request_id),))

    def create_inspection(self, **v):
        return self._one("""INSERT INTO conversation_attention_inspections(
          inspection_id,creator_profile_id,fanvue_account_id,relationship_key,
          telegram_user_id,attention_occurrence_id,evidence_digest,state_fingerprint,
          failure_signature,root_cause_scope,validated_result,evidence_references,
          request_id,conflict_report)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb)
          RETURNING *""", (
          v["inspection_id"],v["creator_profile_id"],v["fanvue_account_id"],
          v["relationship_key"],v["telegram_user_id"],v["attention_occurrence_id"],
          v["evidence_digest"],v["state_fingerprint"],v["failure_signature"],
          v["root_cause_scope"],json.dumps(v["validated_result"],default=str),
          json.dumps(v["evidence_references"],default=str),v.get("request_id"),
          json.dumps(v.get("conflict_report"),default=str)))

    def create_plan(self, **v):
        return self._one("""INSERT INTO conversation_resolution_plans(
          plan_id,inspection_id,creator_profile_id,fanvue_account_id,relationship_key,
          telegram_user_id,attention_occurrence_id,state_fingerprint,root_cause_scope,
          target_operation_id,causal_operation_id,action_type,parameters,
          expected_mutation_entities,provider_generation_possible,
          customer_visible_send_possible,code_change_required,schema_change_required,
          config_change_required,runtime_restart_required,global_impact_possible,
          risk_level,signature,idempotency_key,expires_at)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,
                 %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()+INTERVAL '15 minutes')
          RETURNING *""", (
          v["plan_id"],v["inspection_id"],v["creator_profile_id"],v["fanvue_account_id"],
          v["relationship_key"],v["telegram_user_id"],v["attention_occurrence_id"],
          v["state_fingerprint"],v["root_cause_scope"],v.get("target_operation_id"),
          v.get("causal_operation_id"),v["action_type"],json.dumps(v.get("parameters") or {},default=str),
          json.dumps(v["expected_mutation_entities"],default=str),v["provider_generation_possible"],
          v["customer_visible_send_possible"],False,False,False,False,False,
          v["risk_level"],v["signature"],v["idempotency_key"]))

    def get_inspection(self, inspection_id, *, creator_profile_id, fanvue_account_id):
        return self._one("""SELECT * FROM conversation_attention_inspections
          WHERE inspection_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s""",
          (inspection_id,creator_profile_id,fanvue_account_id))

    def get_inspection_by_request(self, request_id, *, creator_profile_id,
                                  fanvue_account_id, relationship_key,
                                  attention_occurrence_id, state_fingerprint):
        return self._one("""SELECT * FROM conversation_attention_inspections
          WHERE request_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s
            AND relationship_key=%s AND attention_occurrence_id=%s
            AND state_fingerprint=%s""", (request_id,creator_profile_id,
          fanvue_account_id,relationship_key,attention_occurrence_id,state_fingerprint))

    def get_plan_for_inspection(self, inspection_id):
        return self._one("""SELECT * FROM conversation_resolution_plans
          WHERE inspection_id=%s ORDER BY created_at DESC LIMIT 1""", (inspection_id,))

    def get_plan(self, plan_id, *, creator_profile_id, fanvue_account_id):
        return self._one("""SELECT * FROM conversation_resolution_plans
          WHERE plan_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s""",
          (plan_id,creator_profile_id,fanvue_account_id))

    def approve(self, plan_id, *, creator_profile_id, fanvue_account_id, approved_by):
        return self._one("""UPDATE conversation_resolution_plans SET
          approval_state='APPROVED',approved_by=%s,approved_at=NOW(),updated_at=NOW()
          WHERE plan_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s
            AND approval_state='PENDING' AND execution_state='NOT_STARTED'
            AND expires_at>NOW() RETURNING *""",
          (approved_by,plan_id,creator_profile_id,fanvue_account_id))

    def reject(self, plan_id, *, creator_profile_id, fanvue_account_id, rejected_by):
        row = self._one("""UPDATE conversation_resolution_plans SET
          approval_state='REJECTED',updated_at=NOW(),
          execution_result=jsonb_build_object('rejectedBy',%s::text)
          WHERE plan_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s
            AND approval_state='PENDING' AND execution_state='NOT_STARTED' RETURNING *""",
          (rejected_by,plan_id,creator_profile_id,fanvue_account_id))
        return row

    def claim_execution(self, plan_id, *, creator_profile_id, fanvue_account_id,
                        signature, current_fingerprint, canonical_service):
        """Atomically consume an approved plan; a plan can create one execution."""
        rejection = None
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(plan_id),))
            cursor.execute("""SELECT * FROM conversation_resolution_plans
              WHERE plan_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s
              FOR UPDATE""", (plan_id,creator_profile_id,fanvue_account_id))
            plan = cursor.fetchone()
            if plan is None:
                raise LookupError("Resolution plan was not found.")
            if plan["signature"] != signature:
                raise PermissionError("Resolution plan signature is invalid.")
            if plan["approval_state"] != "APPROVED" or not plan["approved_by"]:
                raise PermissionError("Exact resolution plan approval is required.")
            if plan["expires_at"] <= self._database_now(cursor):
                cursor.execute("""UPDATE conversation_resolution_plans SET
                  approval_state='EXPIRED',updated_at=NOW() WHERE plan_id=%s""", (plan_id,))
                rejection = "Resolution plan expired; re-inspection required."
            elif plan["state_fingerprint"] != current_fingerprint:
                cursor.execute("""UPDATE conversation_resolution_plans SET
                  execution_state='STALE_REJECTED',updated_at=NOW(),
                  execution_result='{"error":"RESOLUTION_PLAN_OUT_OF_DATE"}'::jsonb
                  WHERE plan_id=%s""", (plan_id,))
                rejection = "RESOLUTION PLAN OUT OF DATE: re-inspection required."
            if rejection is None:
                cursor.execute("SELECT * FROM conversation_resolution_executions WHERE plan_id=%s", (plan_id,))
                existing = cursor.fetchone()
                if existing:
                    return dict(existing), True
                if plan["execution_state"] != "NOT_STARTED":
                    raise RuntimeError("Resolution plan has already been consumed.")
                execution_id=uuid4()
                cursor.execute("""INSERT INTO conversation_resolution_executions(
                  execution_id,plan_id,action_type,status,canonical_service)
                  VALUES(%s,%s,%s,'EXECUTING',%s) RETURNING *""",
                  (execution_id,plan_id,plan["action_type"],canonical_service))
                execution=cursor.fetchone()
                cursor.execute("""UPDATE conversation_resolution_plans SET
                  execution_state='EXECUTING',updated_at=NOW() WHERE plan_id=%s""", (plan_id,))
                return dict(execution), False
        if rejection:
            raise RuntimeError(rejection)

    def finish_execution(self, execution_id, *, status, result, records_changed=()):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE conversation_resolution_executions SET status=%s,
              result=%s::jsonb,records_changed=%s::jsonb,completed_at=NOW()
              WHERE execution_id=%s RETURNING *""",
              (status,json.dumps(result,default=str),json.dumps(list(records_changed),default=str),execution_id))
            execution=cursor.fetchone()
            if execution:
                cursor.execute("""UPDATE conversation_resolution_plans SET
                  execution_state=%s,execution_result=%s::jsonb,updated_at=NOW()
                  WHERE plan_id=%s""", (status,json.dumps(result,default=str),execution["plan_id"]))
            return dict(execution) if execution else None

    def get_execution(self, execution_id, *, creator_profile_id, fanvue_account_id):
        return self._one("""SELECT execution.* FROM conversation_resolution_executions execution
          JOIN conversation_resolution_plans plan USING(plan_id)
          WHERE execution.execution_id=%s AND plan.creator_profile_id=%s
            AND plan.fanvue_account_id=%s""", (execution_id,creator_profile_id,fanvue_account_id))

    def mark_stale(self, plan_id, *, creator_profile_id, fanvue_account_id, reason):
        return self._one("""UPDATE conversation_resolution_plans SET
          execution_state='STALE_REJECTED',updated_at=NOW(),
          execution_result=jsonb_build_object('error','RESOLUTION_PLAN_OUT_OF_DATE',
                                               'reason',%s::text)
          WHERE plan_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s
            AND execution_state='NOT_STARTED' RETURNING *""",
          (reason,plan_id,creator_profile_id,fanvue_account_id))

    def add_event(self, event_type, *, inspection_id=None, plan_id=None,
                  execution_id=None, event_data=None):
        return self._one("""INSERT INTO conversation_resolution_events(
          inspection_id,plan_id,execution_id,event_type,event_data)
          VALUES(%s,%s,%s,%s,%s::jsonb) RETURNING *""",
          (inspection_id,plan_id,execution_id,event_type,json.dumps(event_data or {},default=str)))

    def list_similar(self, failure_signature, *, creator_profile_id, fanvue_account_id):
        return self._all("""SELECT inspection_id,relationship_key,attention_occurrence_id,
          root_cause_scope,created_at FROM conversation_attention_inspections
          WHERE creator_profile_id=%s AND fanvue_account_id=%s AND failure_signature=%s
          ORDER BY created_at DESC LIMIT 100""",
          (creator_profile_id,fanvue_account_id,failure_signature))

    @staticmethod
    def _database_now(cursor):
        cursor.execute("SELECT NOW() AS value")
        return cursor.fetchone()["value"]

    def _one(self, query, params):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, params); row=cursor.fetchone()
        return dict(row) if row else None

    def _all(self, query, params):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, params); return [dict(row) for row in cursor.fetchall()]
