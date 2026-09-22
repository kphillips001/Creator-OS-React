from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from app.models.telegram_inbound import TelegramInboundPayload
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.test_private_chat_settlement_postgres import connection_factory


pytestmark = pytest.mark.skipif(
    not __import__("os").getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL required")


def _service(worker):
    return OrdinaryChatReplyService(
        repository=OrdinaryChatReplyRepository(connection_factory=connection_factory),
        worker_id=worker, creator_profile_id=1, fanvue_account_id=1)


def _payload(chat, message, text):
    return TelegramInboundPayload(telegram_user_id=chat, telegram_chat_id=chat,
        message_text=text, message_id=message)


@pytest.fixture(autouse=True)
def clean_policy_operations():
    with connection_factory() as connection:
        if connection.execute("SELECT to_regclass('public.market_tier_confirmed_reply_events') present").fetchone()["present"]:
            connection.execute("""DELETE FROM market_tier_confirmed_reply_events WHERE operation_id IN
                (SELECT operation_id FROM ordinary_chat_reply_operations WHERE correlation_id LIKE 'ordinary_reply:AVA_TELETHON_PRIVATE:9917%')""")
        connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE correlation_id LIKE 'ordinary_reply:AVA_TELETHON_PRIVATE:9917%'")
    yield
    with connection_factory() as connection:
        if connection.execute("SELECT to_regclass('public.market_tier_confirmed_reply_events') present").fetchone()["present"]:
            connection.execute("""DELETE FROM market_tier_confirmed_reply_events WHERE operation_id IN
                (SELECT operation_id FROM ordinary_chat_reply_operations WHERE correlation_id LIKE 'ordinary_reply:AVA_TELETHON_PRIVATE:9917%')""")
        connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE correlation_id LIKE 'ordinary_reply:AVA_TELETHON_PRIVATE:9917%'")


def _materialize_and_confirm(service, operation, payload, telegram_message_id):
    result = service.english_only_notice_result(operation, payload)
    stored = service.store_english_only_notice(operation, result)
    sending = service.claim_send(stored)
    # The policy authority is the canonical operation's confirmed state. Keep
    # this focused test independent of optional Market Tier accounting schema;
    # confirm_sent itself is covered by the ordinary lifecycle suite.
    with connection_factory() as connection:
        row = connection.execute("""UPDATE ordinary_chat_reply_operations SET
            state='SENT_CONFIRMED',outbound_telegram_message_id=%s,
            sent_confirmed_at=NOW(),claim_owner=NULL,claimed_at=NULL,
            lease_expires_at=NULL,next_retry_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='SENDING' RETURNING *""",
            (telegram_message_id, sending.operation_id)).fetchone()
    return service.repository._item(row)


def test_confirmed_notice_is_restart_durable_and_suppresses_ten_without_generation():
    chat = 991700001; service = _service("first")
    first_payload = _payload(chat, 1,
        "Hola, me gustaría saber cuánto cuesta este contenido y cómo comprarlo")
    first, _ = service.begin(first_payload)
    decision = service.apply_english_only_policy(first)
    assert decision.action == "FIRST_NOTICE"
    confirmed = _materialize_and_confirm(service, decision.operation, first_payload, 88001)
    assert confirmed.state.value == "SENT_CONFIRMED"
    restarted = _service("restart")
    decisions = []
    for number in range(2, 12):
        item, _ = restarted.begin(_payload(chat, number,
            "Hola, quiero hablar contigo porque tengo muchas preguntas para ti"))
        decisions.append(restarted.apply_english_only_policy(item))
    assert {item.action for item in decisions} == {"SUPPRESSED_AFTER_NOTICE"}
    with connection_factory() as connection:
        rows = connection.execute("""SELECT state,last_error,generation_attempt_count,
            send_attempt_count,response_payload,outbound_telegram_message_id
            FROM ordinary_chat_reply_operations WHERE telegram_chat_id=%s ORDER BY inbound_telegram_message_id""",
            (chat,)).fetchall()
    assert rows[0]["state"] == "SENT_CONFIRMED"
    assert all(row["state"] == "SUPPRESSED" for row in rows[1:])
    assert all(row["last_error"] == "NON_ENGLISH_AFTER_ENGLISH_ONLY_NOTICE" for row in rows[1:])
    assert sum(row["generation_attempt_count"] for row in rows[1:]) == 0
    assert sum(row["send_attempt_count"] for row in rows[1:]) == 0
    assert sum(row["response_payload"] is not None for row in rows[1:]) == 0
    assert sum(row["outbound_telegram_message_id"] is not None for row in rows[1:]) == 0


def test_concurrent_first_non_english_inbounds_reserve_at_most_one_notice():
    chat = 991700002
    services = [_service("worker-a"), _service("worker-b")]
    operations = []
    for number, service in enumerate(services, 1):
        operation, _ = service.begin(_payload(chat, number,
            "Hola, quiero saber cuánto cuesta y cómo puedo comprar este contenido"))
        operations.append(operation)
    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(lambda pair: pair[0].apply_english_only_policy(pair[1]),
                                  zip(services, operations)))
    assert sum(item.action == "FIRST_NOTICE" for item in decisions) == 1
    assert sum(item.action == "SUPPRESSED_NOTICE_PENDING" for item in decisions) == 1
    with connection_factory() as connection:
        reserved = connection.execute("""SELECT count(*) n FROM ordinary_chat_reply_operations
            WHERE telegram_chat_id=%s AND state<>'SUPPRESSED'
              AND COALESCE(delivery_payload#>>'{englishOnlyConversationPolicy,noticeReserved}','false')='true'""",
            (chat,)).fetchone()["n"]
    assert reserved == 1


def test_english_resumes_normal_processing_without_erasing_notice_authority():
    chat = 991700003; service = _service("resume")
    first_payload = _payload(chat, 1,
        "Hola, quiero saber cuánto cuesta este contenido y cómo comprarlo")
    first, _ = service.begin(first_payload)
    decision = service.apply_english_only_policy(first)
    _materialize_and_confirm(service, decision.operation, first_payload, 88003)
    english, _ = service.begin(_payload(chat, 2, "Okay, how much is the photo set?"))
    resumed = service.apply_english_only_policy(english)
    assert resumed.action == "NORMAL_PROCESSING"
    assert resumed.operation.state.value == "PENDING_GENERATION"
    with connection_factory() as connection:
        authority = connection.execute("""SELECT count(*) n FROM ordinary_chat_reply_operations
            WHERE telegram_chat_id=%s AND state='SENT_CONFIRMED'
              AND COALESCE(delivery_payload#>>'{englishOnlyConversationPolicy,noticeReserved}','false')='true'""",
            (chat,)).fetchone()["n"]
    assert authority == 1
