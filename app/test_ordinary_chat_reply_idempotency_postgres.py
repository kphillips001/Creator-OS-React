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


def runtime(adapter, delivery, replies, *, saver=None, purchases=None):
    return TelethonRuntime(transport=Transport(),inbound_adapter=adapter,
        delivery_executor=delivery,ordinary_reply_service=replies,
        conversation_message_saver=saver,purchase_intent_service=purchases,
        global_safety_service=SimpleNamespace(check_global_safety=lambda:{"allowed":True}))


@pytest.fixture(autouse=True)
def clean_operations():
    with connection_factory() as c: c.execute("DELETE FROM ordinary_chat_reply_operations")


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


def test_generation_failure_is_bounded_and_never_sends():
    item=payload(); sends=0
    for attempt in range(5):
        replies=service(f"generation-{attempt}")
        asyncio.run(runtime(Adapter(result(item),error=RuntimeError("provider unavailable")),
                            Delivery([]),replies).handle_payload(item))
        with connection_factory() as c:
            c.execute("UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW()-INTERVAL '1 second'")
    with connection_factory() as c: row=c.execute("SELECT state,generation_attempt_count,send_attempt_count FROM ordinary_chat_reply_operations").fetchone()
    assert row=={"state":"TERMINAL_FAILED","generation_attempt_count":5,"send_attempt_count":0}


def test_generation_provider_recovers_before_max_with_one_eventual_reply():
    item=payload(); first=Delivery([])
    asyncio.run(runtime(Adapter(result(item),error=RuntimeError("temporary provider failure")),
                        first,service("generation-fail")).handle_payload(item))
    with connection_factory() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW()-INTERVAL '1 second'")
    recovered_adapter=Adapter(result(item)); delivery=Delivery([execution(9060)])
    asyncio.run(runtime(recovered_adapter,delivery,service("generation-recovered")).handle_payload(item))
    with connection_factory() as c: row=c.execute("SELECT state,generation_attempt_count,send_attempt_count FROM ordinary_chat_reply_operations").fetchone()
    assert row=={"state":"SENT_CONFIRMED","generation_attempt_count":2,"send_attempt_count":1}
    assert recovered_adapter.calls==delivery.calls==1


def test_empty_unsent_generation_can_be_safely_requeued_once():
    item=payload(); replies=service("empty-recovery"); operation,_=replies.begin(item)
    empty=replace(result(item), response_text="", delivery_payload={})
    stored=replies.generated(replies.claim_generation(operation),empty)
    recovered=replies.requeue_empty_generation(
        stored, reason="generation_runtime_encoding_failure",
    )
    assert recovered is not None and recovered.state.value=="RETRYABLE"
    delivery=Delivery([execution(9061)])
    asyncio.run(runtime(Adapter(result(item)),delivery,service("empty-retry")).handle_payload(item))
    with connection_factory() as c:
        row=c.execute("SELECT state,generation_attempt_count,send_attempt_count FROM ordinary_chat_reply_operations").fetchone()
    assert row=={"state":"SENT_CONFIRMED","generation_attempt_count":2,"send_attempt_count":1}


def test_empty_engine_exception_suppression_can_be_guardedly_retried_once():
    item=payload(); replies=service("engine-exception-recovery"); operation,_=replies.begin(item)
    blocked=replace(result(item), response_text="", delivery_payload={}, blocked=True,
                    error_code="decision_engine_exception")
    stored=replies.generated(replies.claim_generation(operation), blocked)
    assert stored.state.value=="SUPPRESSED"
    recovered=replies.requeue_suppressed_engine_exception(
        stored, reason="repaired_customer_value_durable_memory_boundary",
    )
    assert recovered is not None and recovered.state.value=="RETRYABLE"
    retry_payload=replies.retry_payload(recovered)
    assert retry_payload.message_id==item.message_id
    assert retry_payload.message_text==item.message_text
    assert replies.requeue_suppressed_engine_exception(
        recovered, reason="duplicate_release",
    ) is None
    delivery=Delivery([execution(9062)])
    asyncio.run(runtime(Adapter(result(item)),delivery,service("engine-exception-retry")).handle_payload(retry_payload))
    with connection_factory() as c:
        row=c.execute("SELECT state,generation_attempt_count,send_attempt_count FROM ordinary_chat_reply_operations").fetchone()
    assert row=={"state":"SENT_CONFIRMED","generation_attempt_count":2,"send_attempt_count":1}


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


def test_commercial_namespace_is_suppressed_without_collision():
    item=payload(); generated=result(item)
    purchases=SimpleNamespace(create_before_delivery=lambda *_:SimpleNamespace(
            purchase_intent_id=uuid4()),
        confirm_delivery=lambda *_args,**_kwargs:None)
    asyncio.run(runtime(Adapter(generated),Delivery([execution(9050)]),service("ordinary"),purchases=purchases).handle_payload(item))
    with connection_factory() as c:
        row=c.execute("""SELECT state,correlation_id,response_payload,
            send_attempt_count FROM ordinary_chat_reply_operations""").fetchone()
        count=c.execute(
            "SELECT count(*) n FROM ordinary_chat_reply_operations"
        ).fetchone()["n"]
    assert row["state"]=="SENT_CONFIRMED"
    assert row["correlation_id"].startswith("ordinary_reply:")
    assert row["response_payload"]["diagnostic_metadata"][
        "commercial_payload_composed"
    ] is True
    assert row["send_attempt_count"] == 1 and count == 1


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
    for _ in range(3):
        item=payload(); operation,_=replies.begin(item)
        operations.append(replies.generated(replies.claim_generation(operation),result(item)))
    sending=replies.claim_send(operations[0])
    confirmed_claim=replies.claim_send(operations[1]); replies.confirmed(confirmed_claim,9070)
    retry_claim=replies.claim_send(operations[2]); replies.failed(
        retry_claim,RuntimeError("definitely unsent"),definitive=True)
    recovered=replies.recover_startup()
    assert [item.operation_id for item in recovered]==[sending.operation_id]
    states=[replies.repository.get(item.operation_id).state.value for item in operations]
    assert states==["SEND_UNCERTAIN","SENT_CONFIRMED","RETRYABLE"]
