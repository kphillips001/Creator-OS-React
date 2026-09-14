import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.conversation_attention_resolution_repository import (
    ConversationAttentionResolutionRepository,
)


ROOT=Path(__file__).resolve().parents[1]
FORWARD=ROOT/"migrations/forward/20260913_122_conversation_attention_resolution.sql"
ROLLBACK=ROOT/"migrations/rollback/20260913_122_conversation_attention_resolution.sql"
RELIABILITY_FORWARD=ROOT/"migrations/forward/20260913_123_attention_inspection_reliability.sql"
RELIABILITY_ROLLBACK=ROOT/"migrations/rollback/20260913_123_attention_inspection_reliability.sql"
TABLES=("conversation_attention_inspections","conversation_resolution_plans",
        "conversation_resolution_executions","conversation_resolution_events")


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"),reason="TEST_DATABASE_URL required")
def test_attention_resolution_forward_and_rollback():
    url=os.environ["TEST_DATABASE_URL"]
    with connect(url,autocommit=True) as connection:
        for table in reversed(TABLES):
            connection.execute(f"DROP TABLE IF EXISTS public.{table} CASCADE")
        try:
            connection.execute(FORWARD.read_text(encoding="utf-8"))
            connection.execute(RELIABILITY_FORWARD.read_text(encoding="utf-8"))
            for table in TABLES:
                assert connection.execute("SELECT to_regclass(%s)",(f"public.{table}",)).fetchone()[0]
            with pytest.raises(Exception):
                connection.execute("""INSERT INTO conversation_resolution_plans(
                  plan_id,inspection_id,creator_profile_id,fanvue_account_id,relationship_key,
                  telegram_user_id,attention_occurrence_id,state_fingerprint,root_cause_scope,
                  action_type,provider_generation_possible,customer_visible_send_possible,
                  risk_level,signature,idempotency_key,expires_at)
                  VALUES(gen_random_uuid(),gen_random_uuid(),2,2,'x',1,'o',repeat('f',64),
                    'GLOBAL_SYSTEM','ARBITRARY_SQL',false,false,'LOW','s','i',NOW())""")
            connection.rollback()
            connection.execute(RELIABILITY_ROLLBACK.read_text(encoding="utf-8"))
            connection.execute(ROLLBACK.read_text(encoding="utf-8"))
            for table in TABLES:
                assert connection.execute("SELECT to_regclass(%s)",(f"public.{table}",)).fetchone()[0] is None
        finally:
            for table in reversed(TABLES):
                connection.execute(f"DROP TABLE IF EXISTS public.{table} CASCADE")


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"),reason="TEST_DATABASE_URL required")
def test_signed_plan_stale_expiry_and_single_use_guards():
    url=os.environ["TEST_DATABASE_URL"]
    @contextmanager
    def factory():
        with connect(url,row_factory=dict_row) as connection: yield connection
    with connect(url,autocommit=True) as connection:
        for table in reversed(TABLES): connection.execute(f"DROP TABLE IF EXISTS public.{table} CASCADE")
        connection.execute(FORWARD.read_text(encoding="utf-8"))
        connection.execute(RELIABILITY_FORWARD.read_text(encoding="utf-8"))
    repository=ConversationAttentionResolutionRepository(connection_factory=factory)
    def plan(suffix):
        inspection_id=uuid4(); plan_id=uuid4()
        repository.create_inspection(inspection_id=inspection_id,creator_profile_id=2,
          fanvue_account_id=2,relationship_key=f"relationship-{suffix}",telegram_user_id=7001,
          attention_occurrence_id=f"occ-{suffix}",evidence_digest="e"*64,
          state_fingerprint="f"*64,failure_signature="REQUIRED_RESPONSE_QUALITY_FAILURE",
          root_cause_scope="CUSTOMER_ONLY",validated_result={},evidence_references=[])
        repository.create_plan(plan_id=plan_id,inspection_id=inspection_id,creator_profile_id=2,
          fanvue_account_id=2,relationship_key=f"relationship-{suffix}",telegram_user_id=7001,
          attention_occurrence_id=f"occ-{suffix}",state_fingerprint="f"*64,
          root_cause_scope="CUSTOMER_ONLY",target_operation_id=None,causal_operation_id=None,
          action_type="ACKNOWLEDGE_ONLY",parameters={},expected_mutation_entities=[],
          provider_generation_possible=False,customer_visible_send_possible=False,
          risk_level="LOW",signature=f"signature-{suffix}",idempotency_key=f"key-{suffix}")
        repository.approve(plan_id,creator_profile_id=2,fanvue_account_id=2,approved_by="operator")
        return plan_id
    try:
        stale=plan("stale")
        with pytest.raises(RuntimeError,match="OUT OF DATE"):
            repository.claim_execution(stale,creator_profile_id=2,fanvue_account_id=2,
              signature="signature-stale",current_fingerprint="x"*64,canonical_service="safe")
        assert repository.get_plan(stale,creator_profile_id=2,fanvue_account_id=2)["execution_state"]=="STALE_REJECTED"
        tampered=plan("tampered")
        with pytest.raises(PermissionError,match="signature"):
            repository.claim_execution(tampered,creator_profile_id=2,fanvue_account_id=2,
              signature="forged",current_fingerprint="f"*64,canonical_service="safe")
        expired=plan("expired")
        with connect(url,autocommit=True) as connection:
            connection.execute("UPDATE conversation_resolution_plans SET expires_at=NOW()-INTERVAL '1 second' WHERE plan_id=%s",(expired,))
        with pytest.raises(RuntimeError,match="expired"):
            repository.claim_execution(expired,creator_profile_id=2,fanvue_account_id=2,
              signature="signature-expired",current_fingerprint="f"*64,canonical_service="safe")
        assert repository.get_plan(expired,creator_profile_id=2,fanvue_account_id=2)["approval_state"]=="EXPIRED"
        once=plan("once")
        first,reused=repository.claim_execution(once,creator_profile_id=2,fanvue_account_id=2,
          signature="signature-once",current_fingerprint="f"*64,canonical_service="safe")
        second,reused_again=repository.claim_execution(once,creator_profile_id=2,fanvue_account_id=2,
          signature="signature-once",current_fingerprint="f"*64,canonical_service="safe")
        assert reused is False and reused_again is True
        assert first["execution_id"]==second["execution_id"]
    finally:
        with connect(url,autocommit=True) as connection:
            for table in reversed(TABLES): connection.execute(f"DROP TABLE IF EXISTS public.{table} CASCADE")
