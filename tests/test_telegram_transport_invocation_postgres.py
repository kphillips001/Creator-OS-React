"""Neutral manual dispatch crash/concurrency certification on disposable PostgreSQL."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
import pytest

from app.repositories.telegram_operator_message_repository import TelegramOperatorMessageRepository
from app.services.schema_manager_service import SchemaManagerService

MIGRATION = "20260920_147_telegram_transport_invocations.sql"


@contextmanager
def connection_factory():
    from app.testing.postgres_safety import require_isolated_test_database_url
    url = require_isolated_test_database_url(os.environ['TEST_DATABASE_URL'], os.environ['DATABASE_URL'])
    with psycopg.connect(url, row_factory=dict_row) as connection:
        yield connection


def test_00_migration_forward_rollback_reforward():
    manager = SchemaManagerService(connection_factory=connection_factory)
    manager.reconcile_one(MIGRATION)
    with connection_factory() as c:
        # Only this suite's synthetic rows, in the verified disposable database.
        c.execute("DELETE FROM telegram_operator_message_operations WHERE fanvue_account_id IN (SELECT id FROM fanvue_accounts WHERE account_name LIKE 'Neutral transport %')")
        assert c.execute("SELECT data_type FROM information_schema.columns WHERE table_name='telegram_operator_message_operations' AND column_name='transport_evidence'").fetchone()["data_type"] == "jsonb"
        assert c.execute("SELECT to_regclass('telegram_operator_invocation_recovery_idx') value").fetchone()["value"]
        assert c.execute("SELECT 1 FROM pg_constraint WHERE conname='telegram_operator_transport_evidence_object'").fetchone()
        c.execute((Path("migrations/rollback")/MIGRATION).read_text())
        c.execute("DELETE FROM schema_migrations WHERE migration_name=%s", (MIGRATION,))
    manager.reconcile_one(MIGRATION)
    with connection_factory() as c:
        assert c.execute("SELECT count(*) n FROM schema_migrations WHERE migration_name=%s", (MIGRATION,)).fetchone()["n"] == 1


@pytest.fixture
def queued():
    repository = TelegramOperatorMessageRepository(connection_factory)
    peer = 100000 + uuid4().int % 1000000
    with connection_factory() as c:
        account = c.execute("INSERT INTO fanvue_accounts(account_name) VALUES(%s) RETURNING id", (f"Neutral transport {uuid4()}",)).fetchone()["id"]
        creator = c.execute("""INSERT INTO creator_profiles(fanvue_account_id,persona_name,display_name,age,gender,location)
            VALUES(%s,'Transport Test','Transport Test',25,'unspecified','test') RETURNING id""", (str(account),)).fetchone()["id"]
        c.execute("""INSERT INTO telegram_relationship_controls(relationship_control_id,creator_profile_id,fanvue_account_id,
            telegram_user_id,telegram_chat_id,mode,control_version,changed_by)
            VALUES(%s,%s,%s,%s,%s,'HUMAN_OPERATOR',1,'isolated-test')""", (uuid4(),creator,account,peer,peer))
    operation = repository.reserve(creator_profile_id=creator,fanvue_account_id=account,
        telegram_user_id=peer,telegram_chat_id=peer,telegram_identity_mapping_id=None,
        local_fanvue_user_id=None,conversation_thread_id=None,idempotency_key=str(uuid4()),
        message_text="Creator-OS transport test",relationship_control_version=1,changed_by="isolated-test")
    operation = repository.claim(operation["operation_id"],expected_version=1,route="AVA_TELETHON_PRIVATE")
    return repository, operation


def evidence():
    return {"transport_route": {"transport": "TELETHON", "provider_attempt_id": str(uuid4())}, "certainty": "UNKNOWN"}


def test_concurrent_invocation_has_one_winner(queued):
    repo, op = queued
    def invoke(_): return repo.begin_invocation(op["operation_id"],owner=str(uuid4()),evidence=evidence())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(invoke, range(4)))
    assert sum(x is not None for x in results) == 1
    assert op["operation_id"] not in {x["operation_id"] for x in repo.pending_private_dispatches(1000)}


@pytest.mark.parametrize("ack_persisted", [False, True])
def test_crash_after_invocation_never_requeues(queued, ack_persisted):
    repo, op = queued; owner = str(uuid4())
    repo.begin_invocation(op["operation_id"],owner=owner,evidence=evidence())
    if ack_persisted:
        repo.record_transport_evidence(op["operation_id"],owner=owner,evidence={"telegram_message_id": 99, "certainty": "ACCEPTED"})
    with connection_factory() as c:
        c.execute("""UPDATE telegram_operator_message_operations SET transport_evidence=jsonb_set(
            transport_evidence,'{lease_expires_at}',to_jsonb((NOW()-INTERVAL '1 second')::text)) WHERE operation_id=%s""", (op["operation_id"],))
    restarted = TelegramOperatorMessageRepository(connection_factory)
    restarted.recover_expired_invocations()
    assert restarted.get(op["operation_id"])["state"] == "AMBIGUOUS"
    assert restarted.claim(op["operation_id"],expected_version=1,route="AVA_TELETHON_PRIVATE") is None
    assert restarted.confirmed(op["operation_id"],99,owner=owner) is None


def test_crash_before_invocation_remains_queued(queued):
    repo, op = queued
    repo.recover_expired_invocations()
    assert op["operation_id"] in {x["operation_id"] for x in repo.pending_private_dispatches(1000)}


def test_stale_owner_cannot_write_or_confirm(queued):
    repo, op = queued; owner = str(uuid4())
    repo.begin_invocation(op["operation_id"],owner=owner,evidence=evidence())
    assert repo.record_transport_evidence(op["operation_id"],owner="stale",evidence={"telegram_message_id":99}) is None
    assert repo.confirmed(op["operation_id"],99,owner=owner) is None
    assert repo.record_transport_evidence(op["operation_id"],owner=owner,evidence={"telegram_message_id":99})
    assert repo.record_transport_evidence(op["operation_id"],owner=owner,evidence={"telegram_message_id":100}) is None
    assert repo.failed(op["operation_id"],ValueError("accepted cannot be rejected"),owner=owner) is None
    assert repo.confirmed(op["operation_id"],99,owner="stale") is None
    assert repo.confirmed(op["operation_id"],99,owner=owner)["state"] == "CONFIRMED"
    assert repo.failed(op["operation_id"],ValueError("late failure"),owner=owner) is None


def test_failed_confirmation_leaves_non_dispatchable_claim(queued):
    repo, op = queued; owner = str(uuid4())
    repo.begin_invocation(op["operation_id"],owner=owner,evidence=evidence())
    repo.record_transport_evidence(op["operation_id"],owner=owner,evidence={"telegram_message_id":99})
    # Simulate final transaction abort after the UPDATE, before its commit.
    @contextmanager
    def aborting():
        with connection_factory() as c:
            yield c
            raise RuntimeError("injected commit failure")
    with pytest.raises(RuntimeError):
        TelegramOperatorMessageRepository(aborting).confirmed(op["operation_id"],99,owner=owner)
    assert repo.get(op["operation_id"])["state"] == "SENDING"
    assert op["operation_id"] not in {x["operation_id"] for x in repo.pending_private_dispatches(1000)}


def test_rollback_refuses_to_destroy_attempt_evidence(queued):
    repo, op = queued
    repo.begin_invocation(op["operation_id"],owner=str(uuid4()),evidence=evidence())
    with pytest.raises(psycopg.errors.RaiseException):
        with connection_factory() as c:
            c.execute((Path("migrations/rollback")/MIGRATION).read_text())


def test_transport_evidence_requires_object(queued):
    _, operation = queued
    with pytest.raises(psycopg.errors.CheckViolation):
        with connection_factory() as c:
            c.execute("UPDATE telegram_operator_message_operations SET transport_evidence='[]' WHERE operation_id=%s", (operation["operation_id"],))


def test_ordinary_route_claim_ack_confirmation_is_single_invocation():
    from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
    from app.services.telegram_transport_boundary import RoutedTelegramSender, TelegramInvocationUnknown
    from app.integrations.telegram.bot_api_sender import TelegramBotApiSender
    from app.models.telegram_transport_contract import TelegramReachability
    from datetime import datetime, timezone
    identifier = uuid4(); peer = 123000 + uuid4().int % 100000
    with connection_factory() as c:
        c.execute("""INSERT INTO ordinary_chat_reply_operations(operation_id,telegram_account_scope,
          telegram_chat_id,inbound_telegram_message_id,inbound_sender_telegram_user_id,correlation_id,
          state,claim_owner,sending_at,send_attempt_count,response_text,delivery_payload)
          VALUES(%s,'TRANSPORT_TEST',%s,1,%s,%s,'SENDING','test-owner',NOW(),1,'test','{}')""",
          (identifier,peer,peer,str(identifier)))
    repo = OrdinaryChatReplyRepository(connection_factory)
    calls = []
    class Http:
        def post(self, *a, **k):
            calls.append(k)
            return type("Response", (), {"json": lambda self: {"ok":True,"result":{"message_id":99}}})()
    sender = TelegramBotApiSender(bot_token="test",session=Http(),sender_scope="test-bot",
        peer_evidence=lambda _: TelegramReachability("BOT_API","test-bot",peer,"BOT_INBOUND",datetime.now(timezone.utc)))
    routed = RoutedTelegramSender(sender,context={"operation_id":str(identifier),
        "record_transport_evidence":lambda e:repo.record_provider_evidence(identifier,owner="test-owner",evidence=e)},metadata={})
    assert routed.send_text(chat_id=peer,message_text="test") == 99
    with pytest.raises(TelegramInvocationUnknown): routed.send_text(chat_id=peer,message_text="test")
    assert len(calls) == 1
    confirmed = repo.confirm_sent(identifier,owner="test-owner",telegram_message_id=99)
    assert confirmed.state.value == "SENT_CONFIRMED"
    assert confirmed.delivery_payload["provider_delivery_evidence"]["transport_route"]["transport"] == "BOT_API"
