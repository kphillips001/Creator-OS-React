from __future__ import annotations

import os
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundResult
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.operator_delivery_resolution_repository import OperatorDeliveryResolutionRepository
from app.repositories.telegram_sales_prospect_repository import TelegramSalesProspectRepository
from app.repositories.telegram_private_inbound_repository import TelegramPrivateInboundRepository
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.historical_corrective_eligibility_service import HistoricalCorrectiveEligibilityService
from app.testing.postgres_safety import require_isolated_test_database_url


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


@contextmanager
def connection_factory():
    url = require_isolated_test_database_url(
        TEST_DATABASE_URL, os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"),
    )
    with connect(url, row_factory=dict_row) as connection:
        yield connection


def result(payload, candidate, reasons, *, outcome):
    question_unanswered = "CUSTOMER_QUESTION_UNANSWERED" in reasons
    obligations_unsatisfied = "TURN_OBLIGATIONS_UNSATISFIED" in reasons
    return TelegramInboundResult(
        correlation_id=f"fixture:{payload.message_id}",
        telegram_chat_id=payload.telegram_chat_id,
        telegram_user_id=payload.telegram_user_id,
        message_id=payload.message_id,
        engine_user_id="fixture",
        response_text=candidate,
        offer_authorized=False,
        offer_link=None,
        blocked=False,
        error_code=None,
        delivery_payload={"type": "MESSAGE_TEXT", "message_text": candidate},
        diagnostic_metadata={
            "selected_provider": "OPENAI_FIXTURE",
            "conversationStyle": {
                "turnObligations": ["ANSWER_DIRECT_QUESTION"],
                "satisfiedTurnObligations": ([] if obligations_unsatisfied else ["ANSWER_DIRECT_QUESTION"]),
                "unsatisfiedTurnObligations": (["ANSWER_DIRECT_QUESTION"] if obligations_unsatisfied else []),
                "customerQuestionAnswered": not question_unanswered,
                "turnObligationsSatisfied": not obligations_unsatisfied,
                "combinedObligationRepairOutcome": outcome,
                "styleRewriteReasons": list(reasons),
            },
        },
    )


def test_retry_exhausted_zero_candidate_creates_exactly_one_current_policy_child():
    repository=OrdinaryChatReplyRepository(connection_factory=connection_factory)
    prospects=TelegramSalesProspectRepository(connection_factory=connection_factory)
    inbounds=TelegramPrivateInboundRepository(connection_factory=connection_factory)
    user_id=930000+int(str(uuid4().int)[-5:]); now=datetime.now(timezone.utc)
    prospects.observe(creator_profile_id=2,fanvue_account_id=2,
        telegram_user_id=user_id,telegram_chat_id=user_id)
    inbounds.capture(account_scope="AVA_TELETHON_PRIVATE",user_id=user_id,
        chat_id=user_id,message_id=1,received_at=now,
        customer_text="I want you right now",creator_profile_id=2,
        fanvue_account_id=2,automation_state="ON")
    root,_=repository.get_or_create(account_scope="AVA_TELETHON_PRIVATE",
        chat_id=user_id,inbound_message_id=1,sender_user_id=user_id,
        correlation_id=f"retry-exhausted:{uuid4()}",
        inbound_message_text="I want you right now",inbound_received_at=now,
        turn_obligations=("ACKNOWLEDGE_SEXUAL_ENERGY",))
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          state='TERMINAL_FAILED',generation_attempt_count=5,max_generation_attempts=5,
          send_attempt_count=0,response_text=NULL,response_payload=NULL,
          outbound_telegram_message_id=NULL,sent_confirmed_at=NULL,
          claim_owner=NULL,lease_expires_at=NULL,
          conversation_burst_id=operation_id,burst_role='SURVIVOR',
          burst_member_obligations='["ACKNOWLEDGE_SEXUAL_ENERGY"]'::jsonb,
          last_error='DECISION_ENGINE_EXCEPTION:UNKNOWN: Automatic reply could not be completed.'
          WHERE operation_id=%s""",(root.operation_id,))
    before=repository.get(root.operation_id); key=str(uuid4()); plan=uuid4()
    eligibility=HistoricalCorrectiveEligibilityService(
        connection_factory=connection_factory).evaluate(
          root=before,parent=before,creator_profile_id=2,fanvue_account_id=2,
          telegram_user_id=user_id,telegram_chat_id=user_id,chat_allowed=True)
    assert eligibility["eligible"] is True, eligibility
    def create():
        return OrdinaryChatReplyRepository(
            connection_factory=connection_factory).requeue_historical_corrective(
              target_operation_id=root.operation_id,
              causal_operation_id=root.operation_id,
              creator_profile_id=2,fanvue_account_id=2,
              telegram_user_id=user_id,occurrence_id="retry-exhausted-current",
              resolution_plan_id=plan,approved_by="fixture",
              idempotency_key=key)
    with ThreadPoolExecutor(max_workers=2) as executor:
        children=list(executor.map(lambda _:create(),range(2)))
    assert all(child is not None for child in children)
    assert len({child.operation_id for child in children})==1
    child=children[0]
    assert child.operation_kind=="HISTORICAL_CORRECTIVE"
    assert child.max_generation_attempts==1
    assert child.generation_attempt_count==0 and child.send_attempt_count==0
    assert child.response_text is None and child.response_payload is None
    policy=child.delivery_payload["retryExhaustedCurrentPolicyReevaluation"]
    assert policy["commercialEvaluationRequiredBeforeConversation"] is True
    assert "recoveryExecutionConstraint" not in child.delivery_payload
    after=repository.get(root.operation_id)
    for name in ("state","last_error","generation_attempt_count","send_attempt_count",
                 "response_text","response_payload","outbound_telegram_message_id"):
        assert getattr(after,name)==getattr(before,name)
    assert repository.requeue_historical_corrective(
        target_operation_id=root.operation_id,causal_operation_id=root.operation_id,
        creator_profile_id=2,fanvue_account_id=2,telegram_user_id=user_id,
        occurrence_id="duplicate",resolution_plan_id=uuid4(),
        approved_by="fixture",idempotency_key=str(uuid4())) is None
    with connection_factory() as connection:
        connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE operation_id=%s",
                           (child.operation_id,))
        connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE operation_id=%s",
                           (root.operation_id,))
        connection.execute("DELETE FROM telegram_private_inbound_messages WHERE telegram_chat_id=%s",
                           (user_id,))
        connection.execute("DELETE FROM telegram_sales_prospects WHERE creator_profile_id=2 AND fanvue_account_id=2 AND telegram_user_id=%s",
                           (user_id,))


def test_historical_repetition_child_persists_clay_shaped_exclusion_contract():
    repository = OrdinaryChatReplyRepository(connection_factory=connection_factory)
    prospects = TelegramSalesProspectRepository(connection_factory=connection_factory)
    user_id = 930000 + int(str(uuid4().int)[-5:])
    prospects.observe(
        creator_profile_id=2, fanvue_account_id=2,
        telegram_user_id=user_id, telegram_chat_id=user_id,
    )
    prior, _ = repository.get_or_create(
        account_scope="AVA_TELETHON_PRIVATE", chat_id=user_id,
        inbound_message_id=1, sender_user_id=user_id,
        correlation_id=f"historical-prior:{uuid4()}", inbound_message_text="Tempted",
        inbound_received_at=datetime.now(timezone.utc),
    )
    original, _ = repository.get_or_create(
        account_scope="AVA_TELETHON_PRIVATE", chat_id=user_id,
        inbound_message_id=2, sender_user_id=user_id,
        correlation_id=f"historical-clay:{uuid4()}",
        inbound_message_text="How's my tease today",
        inbound_received_at=datetime.now(timezone.utc),
    )
    rejected = "then don't make it too easy for me"
    diagnostics = {
        "conversationStyle": {
            "turnObligations": ["ANSWER_DIRECT_QUESTION"],
            "finalResponseRepetitionSatisfied": False,
        },
        "conversationCoherence": {
            "resolvedCustomerMeaning": "How effective is my teasing today?",
            "resolvedPersonaDomain": "ordinary",
        },
        "provider": "OPENAI_FIXTURE",
    }
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          state='SENT_CONFIRMED',response_text=%s,response_payload=%s::jsonb,
          outbound_telegram_message_id=10001,sent_confirmed_at=NOW()-INTERVAL '1 day',
          generation_attempt_count=1,send_attempt_count=1
          WHERE operation_id=%s""", (
            rejected, json.dumps({"response_text": rejected}), prior.operation_id,
        ))
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          state='SUPPRESSED',response_text=%s,response_payload=%s::jsonb,
          generation_attempt_count=1,send_attempt_count=0,
          last_error='quality_blocked_before_delivery:FINAL_REPETITION_FAILURE'
          WHERE operation_id=%s""", (
            rejected, json.dumps({"response_text": rejected,
                                  "diagnostic_metadata": diagnostics}),
            original.operation_id,
        ))
    child = repository.requeue_historical_corrective(
        target_operation_id=original.operation_id,
        causal_operation_id=original.operation_id,
        creator_profile_id=2, fanvue_account_id=2, telegram_user_id=user_id,
        occurrence_id="clay-shaped-occurrence", approved_by="fixture-operator",
        resolution_plan_id=uuid4(), idempotency_key=str(uuid4()),
    )
    assert child is not None
    assert child.operation_kind == "HISTORICAL_CORRECTIVE"
    assert child.causal_operation_id == original.operation_id
    assert child.recovery_parent_operation_id == original.operation_id
    assert child.max_generation_attempts == 1
    correction = child.delivery_payload["qualityCorrectiveRetry"]
    assert correction["blockingReasons"] == ["FINAL_REPETITION_FAILURE"]
    assert correction["previousCandidateFailure"] == "FINAL_REPETITION_FAILURE"
    assert correction["previousCandidateText"] == rejected
    assert correction["previousCandidateDiagnostics"] == diagnostics
    assert correction["excludedExactResponses"][0] == rejected
    assert correction["exclusionAuthority"] == "FINAL_RESPONSE_EXACT_NOVELTY"
    assert correction["turnObligations"] == ["ANSWER_DIRECT_QUESTION"]
    assert correction["originalOperationId"] == str(original.operation_id)
    assert correction["originalInboundMessageId"] == 2
    preserved = repository.get(original.operation_id)
    assert preserved.state.value == "SUPPRESSED"
    assert preserved.generation_attempt_count == 1
    assert preserved.send_attempt_count == 0
    with connection_factory() as connection:
        connection.execute(
            "UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW() "
            "WHERE operation_id=%s", (child.operation_id,),
        )
    service = OrdinaryChatReplyService(
        repository=repository, worker_id=f"historical-worker-{uuid4()}",
        creator_profile_id=2, fanvue_account_id=2,
    )
    claimed = service.claim_generation(repository.get(child.operation_id))
    assert claimed is not None
    recovery_payload = service.retry_payload(claimed)
    repeated = result(
        recovery_payload, "Then, don't make it too easy for me!",
        ["FINAL_REPETITION_FAILURE"], outcome="REPEATED_HISTORICAL_CORRECTIVE",
    )
    terminal = service.generated(claimed, repeated)
    assert terminal.state.value == "SUPPRESSED"
    assert terminal.generation_attempt_count == 1
    assert terminal.max_generation_attempts == 1
    assert terminal.send_attempt_count == 0
    assert terminal.outbound_telegram_message_id is None
    assert service.claim_generation(terminal) is None


def test_two_blocked_attempts_survive_terminal_suppression_and_restart():
    scope = f"ATTEMPT_AUDIT_{uuid4()}"
    repository = OrdinaryChatReplyRepository(connection_factory=connection_factory)
    service = OrdinaryChatReplyService(
        repository=repository, worker_id=f"worker-{uuid4()}",
        creator_profile_id=900001, fanvue_account_id=900002,
    )
    service.ACCOUNT_SCOPE = scope
    payload = TelegramInboundPayload(
        telegram_user_id=910001, telegram_chat_id=910001,
        message_text="Where does your name come from?", message_id=1,
        received_at=datetime.now(timezone.utc),
    )
    operation, _ = service.begin(payload)
    first = service.claim_generation(operation)
    scheduled = service.generated(first, result(
        payload, "candidate A", ["CUSTOMER_QUESTION_UNANSWERED"],
        outcome="FIRST_BLOCKED",
    ))
    assert scheduled.state.value == "RETRYABLE"
    with connection_factory() as connection:
        connection.execute(
            "UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW() WHERE operation_id=%s",
            (operation.operation_id,),
        )
    second = service.claim_generation(repository.get(operation.operation_id))
    terminal = service.generated(second, result(
        payload, "candidate B", ["TURN_OBLIGATIONS_UNSATISFIED"],
        outcome="SECOND_BLOCKED",
    ))
    assert terminal.state.value == "SUPPRESSED"
    assert terminal.send_attempt_count == 0

    restarted = OrdinaryChatReplyRepository(connection_factory=connection_factory)
    attempts = restarted.generation_attempts(operation.operation_id)
    assert [item["attempt_number"] for item in attempts] == [1, 2]
    assert [item["candidate_text"] for item in attempts] == ["candidate A", "candidate B"]
    assert attempts[0]["quality_reasons"] == ["CUSTOMER_QUESTION_UNANSWERED"]
    assert attempts[1]["quality_reasons"] == ["TURN_OBLIGATIONS_UNSATISFIED"]
    assert all(item["quality_disposition"] == "BLOCKED_BEFORE_DELIVERY" for item in attempts)
    assert all(item["sent_confirmed"] is False for item in attempts)
    assert all(item["creator_profile_id"] == 900001 for item in attempts)
    assert all(item["fanvue_account_id"] == 900002 for item in attempts)
    assert all(item["telegram_user_id"] == 910001 for item in attempts)
    assert restarted.get(operation.operation_id).state.value == "SUPPRESSED"

    with connection_factory() as connection:
        connection.execute("DELETE FROM ordinary_reply_generation_attempts WHERE operation_id=%s", (operation.operation_id,))
        connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE operation_id=%s", (operation.operation_id,))


def test_operator_corrective_requeue_carries_bounded_failure_context_and_is_stale_safe():
    repository = OrdinaryChatReplyRepository(connection_factory=connection_factory)
    prospects = TelegramSalesProspectRepository(connection_factory=connection_factory)
    user_id = 920000 + int(str(uuid4().int)[-5:])
    prospects.observe(
        creator_profile_id=2, fanvue_account_id=2,
        telegram_user_id=user_id, telegram_chat_id=user_id,
    )
    operation, _ = repository.get_or_create(
        account_scope="AVA_TELETHON_PRIVATE", chat_id=user_id,
        inbound_message_id=1, sender_user_id=user_id,
        correlation_id=f"corrective-fixture:{uuid4()}",
        inbound_message_text="You have a beautiful name; where does it come from?",
        inbound_received_at=datetime.now(timezone.utc),
    )
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          state='SUPPRESSED',generation_attempt_count=2,max_generation_attempts=2,
          last_error='quality_corrective_retry_exhausted:CUSTOMER_QUESTION_UNANSWERED,TURN_OBLIGATIONS_UNSATISFIED'
          WHERE operation_id=%s""", (operation.operation_id,))
    resolution_plan_id = uuid4()
    recovery_idempotency_key = str(uuid4())
    def create_recovery():
        return OrdinaryChatReplyRepository(
            connection_factory=connection_factory,
        ).requeue_historical_corrective(
            target_operation_id=operation.operation_id,
            causal_operation_id=operation.operation_id,
            creator_profile_id=2, fanvue_account_id=2,
            telegram_user_id=user_id,
            occurrence_id="fixture-occurrence", approved_by="fixture-operator",
            resolution_plan_id=resolution_plan_id,
            idempotency_key=recovery_idempotency_key,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        concurrent = list(executor.map(lambda _index: create_recovery(), range(2)))
    assert all(item is not None for item in concurrent)
    assert len({item.operation_id for item in concurrent}) == 1
    requeued = concurrent[0]
    assert requeued is not None
    assert requeued.state.value == "RETRYABLE"
    assert requeued.generation_attempt_count == 0
    assert requeued.send_attempt_count == 0
    assert requeued.outbound_telegram_message_id is None
    assert requeued.operation_id != operation.operation_id
    assert requeued.operation_kind == "HISTORICAL_CORRECTIVE"
    assert requeued.causal_operation_id == operation.operation_id
    assert requeued.recovery_parent_operation_id == operation.operation_id
    repeated = repository.requeue_historical_corrective(
        target_operation_id=operation.operation_id,
        causal_operation_id=operation.operation_id,
        creator_profile_id=2, fanvue_account_id=2, telegram_user_id=user_id,
        occurrence_id="fixture-occurrence", approved_by="fixture-operator",
        resolution_plan_id=resolution_plan_id,
        idempotency_key=recovery_idempotency_key,
    )
    assert repeated.operation_id == requeued.operation_id
    original = repository.get(operation.operation_id)
    assert original.state.value == "SUPPRESSED"
    assert original.generation_attempt_count == 2
    assert original.send_attempt_count == 0
    assert original.last_error == (
        "quality_corrective_retry_exhausted:"
        "CUSTOMER_QUESTION_UNANSWERED,TURN_OBLIGATIONS_UNSATISFIED"
    )
    context = OrdinaryChatReplyService(
        repository=repository, worker_id="fixture",
    ).retry_payload(requeued).quality_correction_context
    assert context["required"] is True
    assert context["source"] == "OPERATOR_APPROVED_HISTORICAL_CORRECTION"
    assert context["blockingReasons"] == [
        "CUSTOMER_QUESTION_UNANSWERED", "TURN_OBLIGATIONS_UNSATISFIED",
    ]
    assert context["turnObligations"] == ["ANSWER_DIRECT_QUESTION"]
    assert context["semanticReferent"] == "AUTOBIOGRAPHICAL_NAME_ORIGIN"
    assert context["previousCandidateFailure"] == (
        "CUSTOMER_QUESTION_UNANSWERED,TURN_OBLIGATIONS_UNSATISFIED"
    )
    assert context["unknownBiographyInstructionRequired"] is True
    assert context["historicalRecoveryGenerationLimit"] == 1
    assert requeued.max_generation_attempts == 1

    # A terminal, durably attested non-delivery may parent exactly one later
    # corrective while the original quality failure remains the immutable root.
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          state='TERMINAL_FAILED',next_retry_at=NULL,
          last_error='RECOVERY_ABORTED_TELEGRAM_PEER_ID_INVALID',
          failed_at=NOW() WHERE operation_id=%s""", (requeued.operation_id,))
    followup_key = str(uuid4())
    followup_plan = uuid4()
    followup = repository.requeue_historical_corrective(
        target_operation_id=requeued.operation_id,
        causal_operation_id=operation.operation_id,
        creator_profile_id=2, fanvue_account_id=2, telegram_user_id=user_id,
        occurrence_id="fixture-followup-occurrence", approved_by="fixture-operator",
        resolution_plan_id=followup_plan, idempotency_key=followup_key,
    )
    assert followup is not None
    assert followup.operation_kind == "HISTORICAL_CORRECTIVE"
    assert followup.causal_operation_id == operation.operation_id
    assert followup.recovery_parent_operation_id == requeued.operation_id
    assert repository.requeue_historical_corrective(
        target_operation_id=requeued.operation_id,
        causal_operation_id=operation.operation_id,
        creator_profile_id=2, fanvue_account_id=2, telegram_user_id=user_id,
        occurrence_id="fixture-followup-occurrence", approved_by="fixture-operator",
        resolution_plan_id=followup_plan, idempotency_key=followup_key,
    ).operation_id == followup.operation_id
    # A distinct plan cannot branch around the already-created active follow-up.
    assert repository.requeue_historical_corrective(
        target_operation_id=requeued.operation_id,
        causal_operation_id=operation.operation_id,
        creator_profile_id=2, fanvue_account_id=2, telegram_user_id=user_id,
        occurrence_id="fixture-followup-duplicate", approved_by="fixture-operator",
        resolution_plan_id=uuid4(), idempotency_key=str(uuid4()),
    ) is None

    newer, _ = repository.get_or_create(
        account_scope="AVA_TELETHON_PRIVATE", chat_id=user_id,
        inbound_message_id=2, sender_user_id=user_id,
        correlation_id=f"corrective-fixture-newer:{uuid4()}",
        inbound_message_text="Never mind", inbound_received_at=datetime.now(timezone.utc),
    )
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          state='SUPPRESSED',generation_attempt_count=2,max_generation_attempts=2,
          last_error='quality_corrective_retry_exhausted:CUSTOMER_QUESTION_UNANSWERED'
          WHERE operation_id=%s""", (operation.operation_id,))
    assert repository.requeue_historical_corrective(
        target_operation_id=operation.operation_id,
        causal_operation_id=operation.operation_id,
        creator_profile_id=2, fanvue_account_id=2, telegram_user_id=user_id,
        occurrence_id="stale", approved_by="fixture-operator",
        resolution_plan_id=uuid4(),
        idempotency_key=str(uuid4()),
    ) is None
    with connection_factory() as connection:
        connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE telegram_chat_id=%s", (user_id,))
        connection.execute("DELETE FROM telegram_sales_prospects WHERE creator_profile_id=2 AND fanvue_account_id=2 AND telegram_user_id=%s", (user_id,))


def test_attested_send_uncertain_creates_one_fresh_policy_corrective_without_mutating_root():
    repository=OrdinaryChatReplyRepository(connection_factory=connection_factory)
    prospects=TelegramSalesProspectRepository(connection_factory=connection_factory)
    user_id=930000+int(str(uuid4().int)[-5:]);prospects.observe(
        creator_profile_id=2,fanvue_account_id=2,telegram_user_id=user_id,telegram_chat_id=user_id)
    root,_=repository.get_or_create(account_scope="AVA_TELETHON_PRIVATE",chat_id=user_id,
        inbound_message_id=1,sender_user_id=user_id,correlation_id=f"negative:{uuid4()}",
        inbound_message_text="I want to join you",inbound_received_at=datetime.now(timezone.utc))
    historical={"response_text":"historical caption","delivery_payload":{
        "asset_path":"historical.png","purchase_intent_id":"historical-intent"}}
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET state='SEND_UNCERTAIN',
          generation_attempt_count=1,send_attempt_count=1,response_text='historical caption',
          response_payload=%s::jsonb,last_error='legacy_sendPhoto_acceptance_unknown',
          sending_at=NOW()-INTERVAL '5 seconds',uncertain_at=NOW()
          WHERE operation_id=%s""",(json.dumps(historical),root.operation_id))
    OperatorDeliveryResolutionRepository(connection_factory).resolve(
        operation_id=root.operation_id,creator_profile_id=2,fanvue_account_id=2,
        relationship_key=f"telegram:2:2:{user_id}",telegram_user_id=user_id,
        telegram_chat_id=user_id,purchase_intent_id=None,outcome="NOT_DELIVERED",
        presentation_mode="VISIBLE_URL",provider_acceptance_evidence=False,
        provider_readback_evidence=True,resolved_by="fixture",evidence={
          "classification":"CONFIRMED_NOT_DELIVERED","complete":True,
          "matchingCandidateCount":0,"attestationMethod":
          "AUTHENTICATED_TELEGRAM_HISTORY_NEGATIVE_ATTESTATION"})
    before=repository.get(root.operation_id);key=str(uuid4());plan=uuid4()
    def create(): return OrdinaryChatReplyRepository(connection_factory=connection_factory).requeue_historical_corrective(
        target_operation_id=root.operation_id,causal_operation_id=root.operation_id,
        creator_profile_id=2,fanvue_account_id=2,telegram_user_id=user_id,
        occurrence_id="attested-occurrence",resolution_plan_id=plan,
        approved_by="fixture",idempotency_key=key,
        recovery_execution_constraint={
          "constraint":"CONVERSATION_ONLY_TEXT",
          "authority":"OPERATOR_APPROVED_RECOVERY_PLAN",
          "commercialActionAuthorization":"DENIED_BY_OPERATOR_RECOVERY_CONSTRAINT",
          "commercialProgressionAllowed":False,"purchaseIntentAllowed":False,
          "mediaAllowed":False,"textOnly":True,
          "reason":"OPERATOR_RECOVERY_CONVERSATION_ONLY"})
    with ThreadPoolExecutor(max_workers=2) as executor: children=list(executor.map(lambda _:create(),range(2)))
    assert len({child.operation_id for child in children})==1
    child=children[0];assert child.operation_kind=="HISTORICAL_CORRECTIVE"
    assert child.causal_operation_id==root.operation_id and child.recovery_parent_operation_id==root.operation_id
    assert child.generation_attempt_count==0 and child.send_attempt_count==0
    assert child.response_payload is None and child.response_text is None
    audit=child.delivery_payload["approvedHistoricalCorrection"]
    assert audit["rootEligibilityCategory"]=="CANONICALLY_CONFIRMED_NOT_DELIVERED"
    assert audit["historicalCandidateReused"] is False and audit["historicalMediaReused"] is False
    assert audit["historicalPurchaseIntentAuthoritative"] is False
    assert child.delivery_payload["canonicalNotDeliveredCorrection"]["freshGenerationRequired"] is True
    assert child.delivery_payload["recoveryExecutionConstraint"]["constraint"]=="CONVERSATION_ONLY_TEXT"
    after=repository.get(root.operation_id)
    for name in ("state","last_error","generation_attempt_count","send_attempt_count",
                 "response_text","response_payload","outbound_telegram_message_id"):
        assert getattr(after,name)==getattr(before,name)
    inspection=uuid4()
    constraint=child.delivery_payload["recoveryExecutionConstraint"]
    with connection_factory() as connection:
        connection.execute("""INSERT INTO conversation_attention_inspections(
          inspection_id,creator_profile_id,fanvue_account_id,relationship_key,
          telegram_user_id,attention_occurrence_id,evidence_digest,state_fingerprint,
          failure_signature,root_cause_scope,validated_result,evidence_references)
          VALUES(%s,2,2,%s,%s,'constraint-fixture',%s,%s,'SEND_UNCERTAIN',
          'CUSTOMER_ONLY','{}'::jsonb,'[]'::jsonb)""",(
          inspection,f"telegram:2:2:{user_id}",user_id,"a"*64,"b"*64))
        connection.execute("""INSERT INTO conversation_resolution_plans(
          plan_id,inspection_id,creator_profile_id,fanvue_account_id,relationship_key,
          telegram_user_id,attention_occurrence_id,state_fingerprint,root_cause_scope,
          target_operation_id,causal_operation_id,action_type,parameters,
          expected_mutation_entities,provider_generation_possible,
          customer_visible_send_possible,risk_level,signature,idempotency_key,expires_at)
          VALUES(%s,%s,2,2,%s,%s,'constraint-fixture',%s,'CUSTOMER_ONLY',%s,%s,
          'REQUEUE_CORRECTIVE_REPLY',%s::jsonb,'[]'::jsonb,TRUE,TRUE,'MEDIUM',%s,%s,
          NOW()+INTERVAL '1 hour')""",(plan,inspection,f"telegram:2:2:{user_id}",
          user_id,"b"*64,root.operation_id,root.operation_id,
          json.dumps({"recoveryExecutionConstraint":constraint}),"fixture-signature",str(uuid4())))
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          state='SUPPRESSED',generation_attempt_count=1,send_attempt_count=0,
          last_error='recovery_execution_constraint_violation:OPERATOR_RECOVERY_CONVERSATION_ONLY',
          next_retry_at=NULL WHERE operation_id=%s""",(child.operation_id,))
    followup_key=str(uuid4());followup_plan=uuid4()
    def create_followup():
        return OrdinaryChatReplyRepository(connection_factory=connection_factory).requeue_historical_corrective(
          target_operation_id=child.operation_id,causal_operation_id=root.operation_id,
          creator_profile_id=2,fanvue_account_id=2,telegram_user_id=user_id,
          occurrence_id="constraint-followup",resolution_plan_id=followup_plan,
          approved_by="fixture",idempotency_key=followup_key,
          recovery_execution_constraint=constraint)
    with ThreadPoolExecutor(max_workers=2) as executor:
        followups=list(executor.map(lambda _:create_followup(),range(2)))
    assert all(item is not None for item in followups)
    assert len({item.operation_id for item in followups})==1
    followup=followups[0]
    assert followup.recovery_parent_operation_id==child.operation_id
    assert followup.causal_operation_id==root.operation_id
    assert followup.generation_attempt_count==0 and followup.send_attempt_count==0
    assert followup.delivery_payload["recoveryExecutionConstraint"]==constraint
    # The first follow-up is a hard lineage boundary; it cannot itself parent another.
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          state='SUPPRESSED',last_error=
          'recovery_execution_constraint_violation:OPERATOR_RECOVERY_CONVERSATION_ONLY'
          WHERE operation_id=%s""",(followup.operation_id,))
    assert repository.requeue_historical_corrective(
      target_operation_id=followup.operation_id,causal_operation_id=root.operation_id,
      creator_profile_id=2,fanvue_account_id=2,telegram_user_id=user_id,
      occurrence_id="recursive-denied",resolution_plan_id=uuid4(),
      approved_by="fixture",idempotency_key=str(uuid4()),
      recovery_execution_constraint=constraint) is None
    with connection_factory() as connection:
        connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE operation_id=%s",(followup.operation_id,))
        connection.execute("DELETE FROM conversation_resolution_plans WHERE plan_id=%s",(plan,))
        connection.execute("DELETE FROM conversation_attention_inspections WHERE inspection_id=%s",(inspection,))
        connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE operation_id=%s",(child.operation_id,))
        connection.execute("DELETE FROM operator_delivery_resolutions WHERE ordinary_operation_id=%s",(root.operation_id,))
        connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE operation_id=%s",(root.operation_id,))
        connection.execute("DELETE FROM telegram_sales_prospects WHERE creator_profile_id=2 AND fanvue_account_id=2 AND telegram_user_id=%s",(user_id,))
