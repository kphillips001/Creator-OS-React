"""Real PostgreSQL certification for ordinary Telegram reply idempotency."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.telegram.telethon_runtime import TelethonRuntime
from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundResult
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.telegram_sales_prospect_repository import TelegramSalesProspectRepository
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.telegram_delivery_executor import TelegramDeliveryExecutionResult
from app.test_private_chat_settlement_postgres import connection_factory, fixture
from app.repositories.relationships_repository import RelationshipsRepository
from app.services.ordinary_chat_delivery_reconciliation_service import (
    OrdinaryChatDeliveryReconciliationService,
)
from app.services.relationships_service import RelationshipsService


pytestmark = pytest.mark.skipif(not __import__("os").getenv("TEST_DATABASE_URL"),
                                reason="TEST_DATABASE_URL required")


class Transport:
    def set_inbound_handler(self, handler): self.handler = handler
    async def start(self): pass
    async def disconnect(self): pass
    async def run_until_disconnected(self): pass


class Adapter:
    def __init__(self, result, *, error=None): self.result=result; self.error=error; self.calls=0
    def execute(self, _payload):
        self.calls += 1
        if self.error: raise self.error
        return self.result


class Delivery:
    def __init__(self, outcomes): self.outcomes=list(outcomes); self.calls=0; self.contexts=[]
    async def execute_async(self, *_args, **_kwargs):
        self.calls += 1; self.contexts.append(dict(_kwargs.get("context") or {})); outcome=self.outcomes.pop(0)
        if isinstance(outcome, BaseException): raise outcome
        return outcome


def service(worker=None):
    return OrdinaryChatReplyService(
        repository=OrdinaryChatReplyRepository(connection_factory=connection_factory),
        worker_id=worker,
        generation_authorizer=lambda operation, diagnostics: None,
    )


def payload(message_id=None):
    return TelegramInboundPayload(telegram_user_id=800001,telegram_chat_id=800001,
        message_text="hello",message_id=message_id or 100000+(uuid4().int%800000))


def result(item, *, diagnostics=None):
    return TelegramInboundResult(correlation_id=f"telegram:{item.telegram_chat_id}:{item.message_id}",
        telegram_chat_id=item.telegram_chat_id,telegram_user_id=item.telegram_user_id,
        message_id=item.message_id,engine_user_id="synthetic",response_text="Hi there",
        offer_authorized=False,offer_link=None,blocked=False,error_code=None,
        delivery_payload={"message_text":"Hi there"},diagnostic_metadata=diagnostics or {})


def execution(message_id=9001):
    return TelegramDeliveryExecutionResult(status="SENT",executed=True,
        delivery_method="text",metadata={"telegram_message_id":message_id})


def nurture_result(item, *, legacy_projection=False):
    attention = {
        "timeWasterRisk": "HIGH",
        "attentionTier": "LOW",
        "effortMode": "MINIMAL",
        "lowCostNurtureActive": True,
        "nurtureResponsesUsed": 0,
        "nurtureResponseBudget": 1,
    }
    diagnostics = (
        {"commercial_summary": {"customerValueAttention": attention}}
        if legacy_projection else
        {"customer_value_attention": attention}
    )
    return result(item, diagnostics=diagnostics)


def runtime(adapter, delivery, replies, *, saver=None, purchases=None):
    return TelethonRuntime(transport=Transport(),inbound_adapter=adapter,
        delivery_executor=delivery,ordinary_reply_service=replies,
        conversation_message_saver=saver,purchase_intent_service=purchases,
        global_safety_service=SimpleNamespace(check_global_safety=lambda:{"allowed":True}))


@pytest.fixture(autouse=True)
def clean_operations():
    with connection_factory() as c:
        c.execute("DELETE FROM market_tier_confirmed_reply_events")
        c.execute("DELETE FROM operator_delivery_resolutions")
        c.execute("DELETE FROM ordinary_reply_generation_attempts")
        c.execute("UPDATE telegram_private_inbound_messages SET response_operation_id=NULL")
        c.execute("DELETE FROM telegram_private_inbound_messages WHERE telegram_user_id=800001")
        c.execute("DELETE FROM ordinary_generation_budgets")
        c.execute("DELETE FROM ordinary_chat_reply_operations")


def test_first_inbound_and_duplicate_create_one_operation_and_generation():
    item=payload(); generated=result(item); adapter=Adapter(generated); delivery=Delivery([execution()])
    asyncio.run(runtime(adapter,delivery,service("one")).handle_payload(item))
    asyncio.run(runtime(Adapter(generated),Delivery([]),service("two")).handle_payload(item))
    with connection_factory() as c:
        rows=c.execute("SELECT * FROM ordinary_chat_reply_operations").fetchall()
    assert len(rows)==1 and rows[0]["state"]=="SENT_CONFIRMED"
    assert rows[0]["generation_attempt_count"]==rows[0]["send_attempt_count"]==1
    assert adapter.calls==delivery.calls==1
    assert delivery.contexts[0]["correlation_id"] == (
        f"ordinary_reply:AVA_TELETHON_PRIVATE:{item.telegram_chat_id}:{item.message_id}"
    )


def test_two_workers_racing_claim_generation_once():
    item=payload(); first=service("a"); second=service("b")
    operation,_=first.begin(item)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims=list(pool.map(lambda svc:svc.claim_generation(operation),(first,second)))
    assert sum(value is not None for value in claims)==1
    with connection_factory() as c:
        row=c.execute("SELECT generation_attempt_count,state FROM ordinary_chat_reply_operations").fetchone()
    assert row=={"generation_attempt_count":1,"state":"GENERATING"}


def test_restart_before_and_after_generation_reuses_same_payload():
    item=payload(); first=service("first"); operation,_=first.begin(item)
    # Crash before generation: a new worker owns the only claim.
    second=service("second"); claimed=second.claim_generation(operation)
    stored=second.generated(claimed,result(item))
    adapter=Adapter(result(item)); delivery=Delivery([execution(9010)])
    asyncio.run(runtime(adapter,delivery,service("restart")).handle_payload(item))
    assert adapter.calls==0 and delivery.calls==1
    assert service("read").repository.get(stored.operation_id).state.value=="SENT_CONFIRMED"


def test_expired_generation_claim_recovers_without_duplicate_operation():
    item=payload(); first=service("dead"); operation,_=first.begin(item); first.claim_generation(operation)
    with connection_factory() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET lease_expires_at=NOW()-INTERVAL '1 second'")
    recovered=service("restart").claim_generation(operation)
    assert recovered is not None and recovered.generation_attempt_count==2
    with connection_factory() as c:
        assert c.execute("SELECT count(*) n FROM ordinary_chat_reply_operations").fetchone()["n"]==1


@pytest.mark.parametrize("ambiguous_error",(
    TimeoutError("timeout"), ConnectionError("socket disconnected"),
    ConnectionResetError("connection reset"), OSError("transport error"),
))
def test_ambiguous_network_result_becomes_uncertain_and_never_resends(ambiguous_error):
    item=payload(); adapter=Adapter(result(item)); delivery=Delivery([ambiguous_error])
    asyncio.run(runtime(adapter,delivery,service("one")).handle_payload(item))
    replay=Delivery([])
    asyncio.run(runtime(Adapter(result(item)),replay,service("two")).handle_payload(item))
    with connection_factory() as c: row=c.execute("SELECT state,next_retry_at FROM ordinary_chat_reply_operations").fetchone()
    assert row=={"state":"SEND_UNCERTAIN","next_retry_at":None}
    assert delivery.calls==1 and replay.calls==0


def test_missing_telegram_message_id_becomes_uncertain():
    item=payload(); delivery=Delivery([TelegramDeliveryExecutionResult(
        status="SENT",executed=True,delivery_method="text",metadata={})])
    asyncio.run(runtime(Adapter(result(item)),delivery,service("missing-id")).handle_payload(item))
    with connection_factory() as c: row=c.execute("SELECT state,outbound_telegram_message_id FROM ordinary_chat_reply_operations").fetchone()
    assert row=={"state":"SEND_UNCERTAIN","outbound_telegram_message_id":None}


def test_crash_after_network_acceptance_recovers_as_uncertain_without_resend():
    item=payload(); replies=service("crash")
    original=replies.confirmed
    replies.confirmed=lambda *_args,**_kwargs: (_ for _ in ()).throw(RuntimeError("crash before commit"))
    delivery=Delivery([execution(9020)])
    asyncio.run(runtime(Adapter(result(item)),delivery,replies).handle_payload(item))
    with connection_factory() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET lease_expires_at=NOW()-INTERVAL '1 second'")
    restart=service("restart"); assert len(restart.recover_startup())==1
    replay=Delivery([])
    asyncio.run(runtime(Adapter(result(item)),replay,restart).handle_payload(item))
    assert delivery.calls==1 and replay.calls==0
    with connection_factory() as c: assert c.execute("SELECT state FROM ordinary_chat_reply_operations").fetchone()["state"]=="SEND_UNCERTAIN"
    replies.confirmed=original


def test_definitely_not_sent_retries_same_generated_reply_once():
    item=payload(); first=Delivery([TelegramDeliveryExecutionResult(status="FAILED",executed=False)])
    adapter=Adapter(result(item)); asyncio.run(runtime(adapter,first,service("one")).handle_payload(item))
    with connection_factory() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW()-INTERVAL '1 second'")
    retry=Delivery([execution(9030)])
    asyncio.run(runtime(Adapter(result(item)),retry,service("two")).handle_payload(item))
    with connection_factory() as c: row=c.execute("SELECT state,generation_attempt_count,send_attempt_count FROM ordinary_chat_reply_operations").fetchone()
    assert row=={"state":"SENT_CONFIRMED","generation_attempt_count":1,"send_attempt_count":2}
    assert adapter.calls==1 and first.calls==retry.calls==1


def test_generation_exception_is_bounded_without_customer_visible_fallback():
    item=payload(); deliveries=[]
    for attempt in range(5):
        replies=service(f"generation-{attempt}")
        delivery=Delivery([]); deliveries.append(delivery)
        asyncio.run(runtime(Adapter(result(item),error=RuntimeError("provider unavailable")),
                            delivery,replies).handle_payload(item))
        with connection_factory() as c:
            c.execute("UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW()-INTERVAL '1 second'")
    with connection_factory() as c: row=c.execute("SELECT state,generation_attempt_count,send_attempt_count,response_payload,response_text FROM ordinary_chat_reply_operations").fetchone()
    assert row=={"state":"TERMINAL_FAILED","generation_attempt_count":1,
                 "send_attempt_count":0,"response_payload":None,"response_text":None}
    assert sum(delivery.calls for delivery in deliveries) == 0


def test_generation_exception_does_not_restart_full_pipeline():
    item=payload(); first=Delivery([])
    asyncio.run(runtime(Adapter(result(item),error=RuntimeError("temporary provider failure")),
                        first,service("generation-fail")).handle_payload(item))
    with connection_factory() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW()-INTERVAL '1 second'")
    recovered_adapter=Adapter(result(item)); delivery=Delivery([execution(9060)])
    asyncio.run(runtime(recovered_adapter,delivery,service("generation-recovered")).handle_payload(item))
    with connection_factory() as c: row=c.execute("SELECT state,generation_attempt_count,send_attempt_count FROM ordinary_chat_reply_operations").fetchone()
    assert row=={"state":"TERMINAL_FAILED","generation_attempt_count":1,"send_attempt_count":0}
    assert first.calls==0 and recovered_adapter.calls==0 and delivery.calls==0


def test_empty_unsent_generation_cannot_restart_full_pipeline():
    item=payload(); replies=service("empty-recovery"); operation,_=replies.begin(item)
    empty=replace(result(item), response_text="", delivery_payload={})
    stored=replies.generated(replies.claim_generation(operation),empty)
    assert stored is not None and stored.state.value=="TERMINAL_FAILED"
    assert stored.response_payload is None and stored.response_text is None
    assert stored.send_attempt_count == 0
    recovered=replies.requeue_empty_generation(
        stored, reason="generation_runtime_encoding_failure",
    )
    # Empty output is an internal generation failure. It never becomes a
    # customer-visible fallback and the legacy generated-row recovery is inert.
    assert recovered is None
    with connection_factory() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW()-INTERVAL '1 second'")
    delivery=Delivery([execution(9061)])
    asyncio.run(runtime(Adapter(result(item)),delivery,service("empty-retry")).handle_payload(item))
    with connection_factory() as c:
        row=c.execute("SELECT state,generation_attempt_count,send_attempt_count FROM ordinary_chat_reply_operations").fetchone()
    assert row=={"state":"TERMINAL_FAILED","generation_attempt_count":1,"send_attempt_count":0}


def test_empty_engine_exception_cannot_restart_full_pipeline():
    item=payload(); replies=service("engine-exception-recovery"); operation,_=replies.begin(item)
    blocked=replace(result(item), response_text="", delivery_payload={}, blocked=True,
                    error_code="decision_engine_exception")
    stored=replies.generated(replies.claim_generation(operation), blocked)
    assert stored.state.value=="TERMINAL_FAILED"
    assert stored.response_payload is None and stored.response_text is None
    assert stored.send_attempt_count == 0
    recovered=replies.requeue_suppressed_engine_exception(
        stored, reason="repaired_customer_value_durable_memory_boundary",
    )
    assert recovered is None
    retry_payload=replies.retry_payload(stored)
    assert replies.requeue_suppressed_engine_exception(
        stored, reason="duplicate_release",
    ) is None
    with connection_factory() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW()-INTERVAL '1 second'")
    delivery=Delivery([execution(9062)])
    asyncio.run(runtime(Adapter(result(item)),delivery,service("engine-exception-retry")).handle_payload(retry_payload))
    with connection_factory() as c:
        row=c.execute("SELECT state,generation_attempt_count,send_attempt_count FROM ordinary_chat_reply_operations").fetchone()
    assert row=={"state":"TERMINAL_FAILED","generation_attempt_count":1,"send_attempt_count":0}


def test_engine_failure_persists_only_bounded_semantic_and_progression_diagnostics():
    item = payload()
    replies = service("diagnostic-persistence")
    operation, _ = replies.begin(item)
    claimed = replies.claim_generation(operation)
    blocked = replace(
        result(item), response_text="", delivery_payload={}, blocked=True,
        error_code="decision_engine_exception",
        diagnostic_metadata={
            "currentTurnSemanticClassification": {
                "authority": "CurrentTurnSemanticClassificationService",
                "status": "AVAILABLE",
                "correlationId": f"telegram:{item.telegram_chat_id}:{item.message_id}",
                "result": {"sexual_engagement": True, "confidence": 0.95},
            },
            "conversationProgressionFailure": {
                "candidateDialogueFunction": "OBSERVATION",
                "rewriteAttempted": True,
                "finalBlockingReasons": [
                    "SEQUENTIAL_LOW_NOVELTY_DIALOGUE_FUNCTION_LOOP"
                ],
            },
            "providerPrivatePayload": {"secret": "must-not-persist"},
        },
    )

    stored = replies.generated(claimed, blocked)

    evidence = stored.delivery_payload["generationFailureDiagnostics"]
    assert set(evidence) == {
        "currentTurnSemanticClassification", "conversationProgressionFailure",
    }
    assert evidence["currentTurnSemanticClassification"]["result"][
        "sexual_engagement"
    ] is True
    assert evidence["conversationProgressionFailure"]["rewriteAttempted"] is True
    assert "providerPrivatePayload" not in str(stored.delivery_payload)
    assert stored.generation_attempt_count == 1
    assert stored.send_attempt_count == 0


def test_blocked_empty_generation_is_terminal_suppressed_and_never_replayed():
    item = payload()
    blocked = replace(
        result(item), response_text="", delivery_payload={}, blocked=True,
        error_code="PAID_PRESENTATION_UNMAPPED_EXPLICIT_PRICE",
        diagnostic_metadata={
            "status": "blocked",
            "paid_presentation_block_reason": (
                "PAID_PRESENTATION_UNMAPPED_EXPLICIT_PRICE"
            ),
        },
    )
    purchases = SimpleNamespace(
        calls=0,
        create_before_delivery=lambda *_args: setattr(
            purchases, "calls", purchases.calls + 1,
        ),
    )
    first_adapter = Adapter(blocked)
    first_delivery = Delivery([])
    asyncio.run(runtime(
        first_adapter, first_delivery, service("blocked-first"),
        purchases=purchases,
    ).handle_payload(item))

    replay_adapter = Adapter(blocked)
    replay_delivery = Delivery([])
    asyncio.run(runtime(
        replay_adapter, replay_delivery, service("blocked-replay"),
        purchases=purchases,
    ).handle_payload(item))

    with connection_factory() as connection:
        row = connection.execute("""SELECT state,response_text,send_attempt_count,
            outbound_telegram_message_id,last_error,response_payload
            FROM ordinary_chat_reply_operations""").fetchone()
    assert row["state"] == "SUPPRESSED"
    assert row["response_text"] == ""
    assert row["send_attempt_count"] == 0
    assert row["outbound_telegram_message_id"] is None
    assert row["last_error"] == (
        "intentional_suppression:PAID_PRESENTATION_UNMAPPED_EXPLICIT_PRICE"
    )
    assert row["response_payload"]["diagnostic_metadata"][
        "paid_presentation_block_reason"
    ] == "PAID_PRESENTATION_UNMAPPED_EXPLICIT_PRICE"
    assert first_adapter.calls == 1
    assert replay_adapter.calls == 0
    assert first_delivery.calls == replay_delivery.calls == 0
    assert purchases.calls == 0
    assert service("restart").recover_startup() == []


def _terminal_generated_recovery_fixture(*, newer=False, delivered=False):
    values = fixture()
    repository = OrdinaryChatReplyRepository(connection_factory=connection_factory)
    inbound = TelegramInboundPayload(
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        message_text="current customer message", message_id=71001,
        received_at=datetime.now(timezone.utc),
    )
    operation, _ = OrdinaryChatReplyService(repository=repository).begin(inbound)
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
            state='TERMINAL_FAILED',response_payload='{"response_text":"ready"}'::jsonb,
            response_text='ready',generation_attempt_count=1,send_attempt_count=5,
            max_send_attempts=5,failed_at=NOW(),last_error='prior deterministic block'
            WHERE operation_id=%s""", (operation.operation_id,))
        if newer:
            connection.execute("""INSERT INTO ordinary_chat_reply_operations(
                operation_id,telegram_account_scope,telegram_chat_id,
                inbound_telegram_message_id,inbound_sender_telegram_user_id,
                correlation_id,state,inbound_message_text,inbound_received_at)
                VALUES(%s,'AVA_TELETHON_PRIVATE',%s,71002,%s,%s,
                       'PENDING_GENERATION','newer',NOW())""", (
                uuid4(),values["telegram"],values["telegram"],str(uuid4())))
        if delivered:
            connection.execute("""INSERT INTO ordinary_chat_reply_operations(
                operation_id,telegram_account_scope,telegram_chat_id,
                inbound_telegram_message_id,inbound_sender_telegram_user_id,
                correlation_id,state,response_payload,response_text,
                outbound_telegram_message_id,sent_confirmed_at,inbound_received_at)
                VALUES(%s,'AVA_TELETHON_PRIVATE',%s,71000,%s,%s,
                       'SENT_CONFIRMED','{}'::jsonb,'already answered',99001,NOW(),NOW())""", (
                uuid4(),values["telegram"],values["telegram"],str(uuid4())))
    return values, repository, operation


def test_terminal_generated_reply_can_be_authorized_once_without_regeneration():
    values, repository, operation = _terminal_generated_recovery_fixture()

    recovered = repository.recover_terminal_generated_for_delivery(
        operation_id=operation.operation_id,
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        inbound_message_id=71001, approved_by="operator",
        idempotency_key="recovery-1",
    )
    duplicate = repository.recover_terminal_generated_for_delivery(
        operation_id=operation.operation_id,
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        inbound_message_id=71001, approved_by="operator",
        idempotency_key="recovery-1",
    )

    assert recovered.state.value == "RETRYABLE"
    assert recovered.response_text == "ready"
    assert recovered.generation_attempt_count == 1
    assert recovered.send_attempt_count == 0
    assert recovered.max_send_attempts == 1
    assert duplicate is None


@pytest.mark.parametrize("newer,delivered", [(True, False), (False, True)])
def test_terminal_generated_recovery_fails_closed_when_stale_or_already_answered(
        newer, delivered):
    values, repository, operation = _terminal_generated_recovery_fixture(
        newer=newer, delivered=delivered)

    assert repository.recover_terminal_generated_for_delivery(
        operation_id=operation.operation_id,
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        inbound_message_id=71001, approved_by="operator",
        idempotency_key="recovery-blocked",
    ) is None


def test_deterministic_delivery_block_stops_after_one_claim_and_keeps_reason():
    item = payload()
    replies = service("deterministic-block")
    blocked_delivery = Delivery([TelegramDeliveryExecutionResult(
        status="blocked", executed=False, delivery_method="text",
        blocking_reason="GLOBAL_AVA_BOT_ATTENTION",
        metadata={"execution_state": "blocked"},
    )])

    asyncio.run(runtime(
        Adapter(result(item)), blocked_delivery, replies,
    ).handle_payload(item))

    with connection_factory() as connection:
        row = connection.execute("""SELECT state,send_attempt_count,next_retry_at,
            last_error,delivery_payload FROM ordinary_chat_reply_operations""").fetchone()
    assert row["state"] == "RETRYABLE"
    assert row["send_attempt_count"] == 1
    assert row["next_retry_at"] is None
    assert row["last_error"] == (
        "deterministic_delivery_block:GLOBAL_AVA_BOT_ATTENTION")
    assert row["delivery_payload"]["deterministicDeliveryBlock"][
        "transportAttempted"] is False


def test_mapping_only_scheduling_and_uncertain_reconciliation_are_canonical():
    values = fixture()
    sent_at = datetime.now(timezone.utc)
    operation_id = uuid4()
    delivered_text = "Existing Telegram delivery"
    with connection_factory() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS telegram_operator_message_operations(
            operation_id UUID PRIMARY KEY,creator_profile_id BIGINT,
            fanvue_account_id BIGINT,telegram_user_id BIGINT,telegram_chat_id BIGINT,
            state TEXT,message_text TEXT,confirmed_at TIMESTAMPTZ,
            outbound_telegram_message_id BIGINT)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS conversation_attention_acknowledgements(
            acknowledgement_id UUID PRIMARY KEY,occurrence_id TEXT,
            creator_profile_id BIGINT,fanvue_account_id BIGINT,
            telegram_user_id BIGINT,telegram_chat_id BIGINT,
            triggering_inbound_message_id BIGINT,acknowledged_at TIMESTAMPTZ,
            acknowledged_by TEXT,revoked_at TIMESTAMPTZ)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS telegram_relationship_market_tiers(
            market_tier_id UUID PRIMARY KEY,creator_profile_id BIGINT,
            fanvue_account_id BIGINT,telegram_user_id BIGINT,telegram_chat_id BIGINT,
            market_tier TEXT,removed_at TIMESTAMPTZ)""")
        connection.execute(
            "DELETE FROM telegram_sales_prospects WHERE telegram_user_id=%s",
            (values["telegram"],),
        )
        connection.execute("""INSERT INTO telegram_identity_map(
            telegram_user_id,telegram_chat_id,fanvue_account_id,
            local_fanvue_user_id,external_fanvue_user_uuid,is_active,
            verification_status,verification_method,verified_at,verified_by)
            VALUES(%s,%s,%s,%s,%s,TRUE,'VERIFIED','TEST',NOW(),'TEST')""", (
            values["telegram"], values["telegram"], values["account"],
            values["user"], values["buyer_uuid"],
        ))
        connection.execute("""INSERT INTO ordinary_chat_reply_operations(
            operation_id,telegram_account_scope,telegram_chat_id,
            inbound_telegram_message_id,inbound_sender_telegram_user_id,
            correlation_id,state,inbound_message_text,inbound_received_at,
            next_retry_at,last_error)
            VALUES(%s,'AVA_TELETHON_PRIVATE',%s,72001,%s,%s,'RETRYABLE',
                   'hello',NOW(),NOW()+INTERVAL '10 minutes','availability_deferred')""", (
            operation_id, values["telegram"], values["telegram"], str(uuid4()),
        ))
    repository = RelationshipsRepository(connection_factory=connection_factory)
    inbox = repository.inbox_state(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"])
    projected = RelationshipsService._operational_projection(inbox[values["telegram"]])
    assert projected["operationalStatus"] == "REPLY_SCHEDULED"
    assert len([key for key in inbox if key == values["telegram"]]) == 1

    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
            state='SEND_UNCERTAIN',response_payload=%s::jsonb,response_text='stale',
            delivery_payload=%s::jsonb,generation_attempt_count=1,send_attempt_count=1,
            next_retry_at=NULL,sending_at=%s-INTERVAL '2 seconds',uncertain_at=%s+INTERVAL '2 seconds',
            last_error='worker_restarted_during_provider_send'
            WHERE operation_id=%s""", (
            __import__('json').dumps({"response_text": "stale", "delivery_payload": {
                "message_text": delivered_text}}),
            __import__('json').dumps({"message_text": delivered_text,
                "provider_delivery_evidence": {"telegram_message_id": 99001}}),
            sent_at, sent_at, operation_id,
        ))
    service = OrdinaryChatDeliveryReconciliationService(repository=
        OrdinaryChatReplyRepository(connection_factory=connection_factory))
    scope = dict(
        operation_id=operation_id, creator_profile_id=values["creator"],
        fanvue_account_id=values["account"], telegram_user_id=values["telegram"],
        telegram_chat_id=values["telegram"], inbound_message_id=72001,
        expected_text=delivered_text, idempotency_key="mapping-only-reconcile",
    )
    evidence = dict(telegram_message_id=99001, telegram_chat_id=values["telegram"],
        telegram_sender_id=777, telegram_sent_at=sent_at,
        customer_visible_text=delivered_text, outbound=True,
        evidence_source="ISOLATED_TELEGRAM_HISTORY")
    assert service.reconcile(external_evidence={**evidence,
        "telegram_chat_id": values["telegram"] + 1},
        authorized_sender_id=777, **scope) is None
    assert service.reconcile(external_evidence={**evidence,
        "telegram_sender_id": 778}, authorized_sender_id=777, **scope) is None
    assert service.reconcile(external_evidence={**evidence,
        "telegram_message_id": 99002}, authorized_sender_id=777, **scope) is None
    assert service.reconcile(external_evidence=evidence, authorized_sender_id=777,
        **{**scope, "fanvue_account_id": values["account"] + 1}) is None
    first = service.reconcile(external_evidence=evidence, authorized_sender_id=777, **scope)
    second = service.reconcile(external_evidence=evidence, authorized_sender_id=777, **scope)
    assert first.state.value == second.state.value == "SENT_CONFIRMED"
    assert first.outbound_telegram_message_id == 99001
    assert first.response_text == delivered_text
    assert first.uncertain_at is None and first.next_retry_at is None
    assert service.reconcile(external_evidence={**evidence,
        "customer_visible_text": "mismatch"}, authorized_sender_id=777, **scope) is None
    messages = repository.messages(creator_profile_id=values["creator"],
        fanvue_account_id=values["account"], telegram_user_id=values["telegram"])
    assert any(item["direction"] == "AVA" and item["content"] == delivered_text
               and item["telegram_message_id"] == 99001 for item in messages)
    final_inbox = repository.inbox_state(creator_profile_id=values["creator"],
        fanvue_account_id=values["account"])[values["telegram"]]
    assert RelationshipsService._operational_projection(final_inbox)[
        "operationalStatus"] == "NONE"
    with connection_factory() as connection:
        assert connection.execute("""SELECT count(*) n FROM telegram_sales_prospects
            WHERE telegram_user_id=%s""", (values["telegram"],)).fetchone()["n"] == 0
        marker = connection.execute("""SELECT delivery_payload#>>
            '{optionalPersistence,activeOfferFollowThrough}' status
            FROM ordinary_chat_reply_operations WHERE operation_id=%s""",
            (operation_id,)).fetchone()["status"]
        assert marker in {"UNAVAILABLE", "NOT_APPLICABLE", "RECORDED"}


def test_missing_optional_follow_through_table_cannot_rollback_confirmation():
    values = fixture()
    operation_id = uuid4()
    with connection_factory() as connection:
        optional_present = connection.execute(
            "SELECT to_regclass('public.active_offer_follow_through_events') present"
        ).fetchone()["present"]
        connection.execute("""INSERT INTO ordinary_chat_reply_operations(
            operation_id,telegram_account_scope,telegram_chat_id,
            inbound_telegram_message_id,inbound_sender_telegram_user_id,
            correlation_id,state,response_payload,response_text,delivery_payload,
            generation_attempt_count,send_attempt_count,claim_owner,claimed_at,
            lease_expires_at,inbound_message_text,inbound_received_at,sending_at)
            VALUES(%s,'AVA_TELETHON_PRIVATE',%s,73001,%s,%s,'SENDING',
                   '{"response_text":"confirmed"}','confirmed',
                   '{"message_text":"confirmed"}',1,1,'optional-test',NOW(),
                   NOW()+INTERVAL '1 minute','hello',NOW(),NOW())""", (
            operation_id, values["telegram"], values["telegram"], str(uuid4()),
        ))
    confirmed = OrdinaryChatReplyRepository(
        connection_factory=connection_factory).confirm_sent(
            operation_id, owner="optional-test", telegram_message_id=99101,
        )
    assert confirmed.state.value == "SENT_CONFIRMED"
    assert confirmed.outbound_telegram_message_id == 99101
    with connection_factory() as connection:
        row = connection.execute("""SELECT state,outbound_telegram_message_id,
            delivery_payload#>>'{optionalPersistence,activeOfferFollowThrough}' status
            FROM ordinary_chat_reply_operations WHERE operation_id=%s""",
            (operation_id,)).fetchone()
    assert row["state"] == "SENT_CONFIRMED"
    assert row["outbound_telegram_message_id"] == 99101
    assert row["status"] == ("UNAVAILABLE" if optional_present is None
                              else "NOT_APPLICABLE")


def test_prospect_inbound_count_uses_durable_unique_inbound_operations():
    values=fixture(); item=TelegramInboundPayload(
        telegram_user_id=values["telegram"],telegram_chat_id=values["telegram"],
        message_text="hello",message_id=700000+(uuid4().int%100000),
    )
    service("prospect-count").begin(item)
    prospects=TelegramSalesProspectRepository(connection_factory=connection_factory)
    for _ in range(2):
        prospect=prospects.observe(
            creator_profile_id=values["creator"],fanvue_account_id=values["account"],
            telegram_user_id=values["telegram"],telegram_chat_id=values["telegram"],
        )
    assert prospect.inbound_message_count==1


def test_confirmed_reply_transcript_is_idempotent_across_replay():
    values=fixture()
    with connection_factory() as c:
        thread=c.execute("""INSERT INTO chat_threads(fanvue_account_id,fanvue_user_id,thread_status)
            VALUES (%s,%s,'active') RETURNING *""",(values["account"],values["user"])).fetchone()
    def saver(**values_to_save):
        with connection_factory() as c:
            c.execute("""INSERT INTO chat_messages(fanvue_account_id,thread_id,fanvue_user_id,
                fanvue_message_uuid,direction,sender_type,text,has_media,media_uuids,is_paid_message,
                sent_at,raw_payload) VALUES (%s,%s,%s,%s,%s,%s,%s,FALSE,'{}',FALSE,NOW(),%s::jsonb)
                ON CONFLICT(fanvue_message_uuid) DO NOTHING""",(values_to_save["fanvue_account_id"],
                values_to_save["thread_id"],values_to_save["fanvue_user_id"],
                values_to_save["fanvue_message_uuid"],values_to_save["direction"],
                values_to_save["sender_type"],values_to_save["text"],
                __import__("json").dumps(values_to_save["raw_payload"])))
    item=TelegramInboundPayload(telegram_user_id=values["telegram"],telegram_chat_id=values["telegram"],message_text="hello",message_id=700000+(uuid4().int%100000))
    diagnostics={"conversation_thread_id":thread["id"],"conversation_fanvue_account_id":values["account"],"conversation_fanvue_user_id":values["user"]}
    generated=result(item,diagnostics=diagnostics)
    asyncio.run(runtime(Adapter(generated),Delivery([execution(9040)]),service("one"),saver=saver).handle_payload(item))
    asyncio.run(runtime(Adapter(generated),Delivery([]),service("two"),saver=saver).handle_payload(item))
    with connection_factory() as c:
        count=c.execute("""SELECT count(*) n FROM chat_messages WHERE thread_id=%s AND direction='outbound'
            AND raw_payload->>'telegram_message_id'='9040'""",(thread["id"],)).fetchone()["n"]
    assert count==1


def test_confirmed_low_cost_nurture_response_consumes_rolling_budget():
    item = payload()
    diagnostics = {
        "customer_value_attention": {
            "lowCostNurtureActive": True,
            "nurtureResponseBudget": 1,
        },
    }
    asyncio.run(runtime(
        Adapter(result(item, diagnostics=diagnostics)),
        Delivery([execution(9041)]), service("nurture-budget"),
    ).handle_payload(item))

    evidence = service("nurture-read").repository.customer_behavior_evidence(
        account_scope="AVA_TELETHON_PRIVATE",
        chat_id=item.telegram_chat_id,
        sender_user_id=item.telegram_user_id,
    )
    assert evidence["nurture_response_count_rolling_day"] == 1
    assert evidence["last_nurture_response_at"] is not None


def test_suppressed_low_cost_nurture_response_does_not_consume_budget():
    item = payload()
    blocked = replace(
        result(item, diagnostics={
            "customer_value_attention": {
                "lowCostNurtureActive": True,
                "nurtureResponseBudget": 1,
            },
        }),
        response_text="",
        delivery_payload={},
        blocked=True,
        error_code="LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED",
    )
    asyncio.run(runtime(
        Adapter(blocked), Delivery([]), service("nurture-suppressed"),
    ).handle_payload(item))

    evidence = service(
        "nurture-suppressed-read"
    ).repository.customer_behavior_evidence(
        account_scope="AVA_TELETHON_PRIVATE",
        chat_id=item.telegram_chat_id,
        sender_user_id=item.telegram_user_id,
    )
    assert evidence["nurture_response_count_rolling_day"] == 0
    assert evidence["last_nurture_response_at"] is None


def test_behavior_evidence_counts_semantic_nonpayment_and_browsing():
    base = payload()
    messages = (
        "I'm just browsing",
        "I don't feel like paying",
        "maybe later, I'm not paying now",
    )
    repository = service("semantic-nonpayment").repository
    for offset, message in enumerate(messages):
        repository.get_or_create(
            account_scope="AVA_TELETHON_PRIVATE",
            chat_id=base.telegram_chat_id,
            inbound_message_id=base.message_id + offset,
            sender_user_id=base.telegram_user_id,
            correlation_id=f"semantic-nonpayment:{offset}",
            inbound_message_text=message,
            inbound_received_at=datetime.now(timezone.utc),
        )
    evidence = repository.customer_behavior_evidence(
        account_scope="AVA_TELETHON_PRIVATE",
        chat_id=base.telegram_chat_id,
        sender_user_id=base.telegram_user_id,
    )
    assert evidence["rejection_count"] == 2
    assert evidence["idle_browsing_signal_count"] == 1


def test_commercial_payload_without_current_authority_is_not_delivered():
    item=payload(); generated=result(item)
    purchases=SimpleNamespace(create_before_delivery=lambda *_:SimpleNamespace(
            purchase_intent_id=uuid4()),
        confirm_delivery=lambda *_args,**_kwargs:None)
    delivery=Delivery([execution(9050)])
    asyncio.run(runtime(Adapter(generated),delivery,service("ordinary"),purchases=purchases).handle_payload(item))
    with connection_factory() as c:
        row=c.execute("""SELECT state,correlation_id,response_payload,
            send_attempt_count FROM ordinary_chat_reply_operations""").fetchone()
        count=c.execute(
            "SELECT count(*) n FROM ordinary_chat_reply_operations"
        ).fetchone()["n"]
    assert row["state"]=="RETRYABLE"
    assert row["correlation_id"].startswith("ordinary_reply:")
    assert row["response_payload"]["diagnostic_metadata"][
        "commercial_payload_composed"
    ] is True
    assert row["send_attempt_count"] == 0 and count == 1
    assert delivery.calls == 0


def test_stable_key_is_account_scope_chat_and_inbound_message():
    item=payload(); first,created=service("one").begin(item)
    duplicate,duplicate_created=service("two").begin(item)
    assert created is True and duplicate_created is False
    assert duplicate.operation_id==first.operation_id
    with pytest.raises(ValueError, match="reused with conflicting content"):
        service("three").begin(TelegramInboundPayload(
            telegram_user_id=item.telegram_user_id+1,
            telegram_chat_id=item.telegram_chat_id,
            message_text="different text",message_id=item.message_id))
    with connection_factory() as c:
        assert c.execute(
            "SELECT count(*) n FROM ordinary_chat_reply_operations"
        ).fetchone()["n"] == 1


def test_generated_payload_and_hash_are_durable():
    item=payload(); replies=service("hash"); operation,_=replies.begin(item)
    stored=replies.generated(replies.claim_generation(operation),result(item))
    assert stored.response_text=="Hi there" and len(stored.response_content_sha256)==64
    assert replies.result(stored).response_text=="Hi there"


@pytest.mark.parametrize("terminal_state",("SENT_CONFIRMED","SEND_UNCERTAIN","TERMINAL_FAILED","SUPPRESSED"))
def test_terminal_or_uncertain_states_cannot_be_reclaimed_for_send(terminal_state):
    item=payload(); replies=service("terminal"); operation,_=replies.begin(item)
    stored=replies.generated(replies.claim_generation(operation),result(item))
    with connection_factory() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET state=%s",(terminal_state,))
    assert replies.claim_send(replies.repository.get(stored.operation_id)) is None


def test_future_retry_is_not_claimable_until_due():
    item=payload(); replies=service("retry"); operation,_=replies.begin(item)
    stored=replies.generated(replies.claim_generation(operation),result(item))
    sending=replies.claim_send(stored); replies.failed(sending,RuntimeError("definitely failed"),definitive=True)
    current=replies.repository.get(operation.operation_id)
    assert current.state.value=="RETRYABLE" and replies.claim_send(current) is None


def test_startup_marks_orphaned_sending_claim_uncertain():
    item=payload(); replies=service("orphan"); operation,_=replies.begin(item)
    sending=replies.claim_send(replies.generated(replies.claim_generation(operation),result(item)))
    recovered=replies.recover_startup()
    assert len(recovered)==1 and recovered[0].state.value=="SEND_UNCERTAIN"


def test_definitive_send_failures_reach_terminal_bound():
    item=payload(); replies=service("bounded-send"); operation,_=replies.begin(item)
    current=replies.generated(replies.claim_generation(operation),result(item))
    for attempt in range(5):
        current=replies.claim_send(current)
        current=replies.failed(current,RuntimeError("rejected"),definitive=True)
        if current.state.value=="RETRYABLE":
            with connection_factory() as c:
                c.execute("UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW()-INTERVAL '1 second'")
            current=replies.repository.get(operation.operation_id)
    assert current.state.value=="TERMINAL_FAILED" and current.send_attempt_count==5


def test_explicit_terminal_telegram_error_is_never_retryable():
    item=payload(); replies=service("hard-failure"); operation,_=replies.begin(item)
    sending=replies.claim_send(replies.generated(replies.claim_generation(operation),result(item)))
    failed=replies.failed(sending,PermissionError("chat blocked"),definitive=True,terminal=True)
    assert failed.state.value=="TERMINAL_FAILED" and failed.next_retry_at is None


def test_startup_recovery_changes_only_inflight_sending():
    replies=service("startup")
    operations=[]
    for offset in range(3):
        item=replace(payload(message_id=700000+offset),
            telegram_user_id=800001+offset,telegram_chat_id=800001+offset)
        operation,_=replies.begin(item)
        operations.append(replies.generated(replies.claim_generation(operation),result(item)))
    sending=replies.claim_send(operations[0])
    confirmed_claim=replies.claim_send(operations[1]); replies.confirmed(confirmed_claim,9070)
    retry_claim=replies.claim_send(operations[2]); replies.failed(
        retry_claim,RuntimeError("definitely unsent"),definitive=True)
    recovered=replies.recover_startup()
    assert [item.operation_id for item in recovered]==[sending.operation_id]
    states=[replies.repository.get(item.operation_id).state.value for item in operations]
    assert states==["SEND_UNCERTAIN","SENT_CONFIRMED","RETRYABLE"]


@pytest.mark.parametrize("legacy_projection", (False, True))
def test_confirmed_nurture_reply_counts_once_from_canonical_or_legacy_projection(
    legacy_projection,
):
    item = payload()
    replies = service("nurture-confirmed")
    operation, _ = replies.begin(item)
    generated = replies.generated(
        replies.claim_generation(operation),
        nurture_result(item, legacy_projection=legacy_projection),
    )
    sending = replies.claim_send(generated)
    confirmed = replies.confirmed(sending, 9100)

    # Confirmation replay cannot transition the row a second time, and the
    # authoritative usage query counts the durable operation rather than calls.
    assert replies.confirmed(sending, 9100) is None
    evidence = replies.repository.customer_behavior_evidence(
        account_scope=replies.ACCOUNT_SCOPE,
        chat_id=item.telegram_chat_id,
        sender_user_id=item.telegram_user_id,
    )
    assert confirmed.state.value == "SENT_CONFIRMED"
    assert evidence["nurture_response_count_rolling_day"] == 1
    assert evidence["last_nurture_response_at"] is not None


def test_failed_nurture_send_does_not_consume_budget():
    item = payload()
    replies = service("nurture-failed")
    operation, _ = replies.begin(item)
    generated = replies.generated(
        replies.claim_generation(operation), nurture_result(item),
    )
    failed = replies.failed(
        replies.claim_send(generated), RuntimeError("definitively unsent"),
        definitive=True,
    )
    evidence = replies.repository.customer_behavior_evidence(
        account_scope=replies.ACCOUNT_SCOPE,
        chat_id=item.telegram_chat_id,
        sender_user_id=item.telegram_user_id,
    )
    assert failed.state.value == "RETRYABLE"
    assert evidence["nurture_response_count_rolling_day"] == 0
    assert evidence["last_nurture_response_at"] is None


def test_confirmed_nurture_reply_expires_from_rolling_window():
    item = payload()
    replies = service("nurture-expired")
    operation, _ = replies.begin(item)
    generated = replies.generated(
        replies.claim_generation(operation), nurture_result(item),
    )
    replies.confirmed(replies.claim_send(generated), 9101)
    with connection_factory() as connection:
        connection.execute(
            "UPDATE ordinary_chat_reply_operations "
            "SET sent_confirmed_at=NOW()-INTERVAL '25 hours'"
        )
    evidence = replies.repository.customer_behavior_evidence(
        account_scope=replies.ACCOUNT_SCOPE,
        chat_id=item.telegram_chat_id,
        sender_user_id=item.telegram_user_id,
    )
    assert evidence["nurture_response_count_rolling_day"] == 0
    assert evidence["last_nurture_response_at"] is not None
