from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.testing.postgres_safety import require_isolated_test_database_url


URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL required")


@contextmanager
def connection_factory():
    guarded = require_isolated_test_database_url(
        URL, os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"))
    with connect(guarded, row_factory=dict_row) as connection:
        yield connection


def test_suppressed_unresolved_semantics_survive_repository_restart_without_reviving():
    repository = OrdinaryChatReplyRepository(connection_factory=connection_factory)
    scope = f"COHERENCE_{uuid4()}"
    chat_id = 8_000_000_000 + (uuid4().int % 100_000_000)
    first, _ = repository.get_or_create(
        account_scope=scope, chat_id=chat_id, inbound_message_id=1,
        sender_user_id=chat_id, correlation_id=str(uuid4()),
        inbound_message_text="Do you do anything besides content?")
    second, _ = repository.get_or_create(
        account_scope=scope, chat_id=chat_id, inbound_message_id=2,
        sender_user_id=chat_id, correlation_id=str(uuid4()),
        inbound_message_text="For work, that is.")
    try:
        with connection_factory() as connection:
            connection.execute("""UPDATE ordinary_chat_reply_operations SET
                state='SUPPRESSED',last_error=%s,response_payload=%s::jsonb
                WHERE operation_id=%s""", (
                "quality_corrective_retry_exhausted:CUSTOMER_QUESTION_UNANSWERED,TURN_OBLIGATIONS_UNSATISFIED",
                '{"diagnostic_metadata":{"conversationStyle":{"unsatisfiedTurnObligations":["ANSWER_DIRECT_QUESTION"]}}}',
                first.operation_id,
            ))
        restarted = OrdinaryChatReplyRepository(connection_factory=connection_factory)
        evidence = restarted.immediately_preceding_unresolved_semantics(second)
        assert str(evidence["operation_id"]) == str(first.operation_id)
        assert evidence["unsatisfied_obligations"] == ["ANSWER_DIRECT_QUESTION"]
        assert restarted.get(first.operation_id).state.value == "SUPPRESSED"
    finally:
        with connection_factory() as connection:
            connection.execute(
                "DELETE FROM ordinary_chat_reply_operations WHERE telegram_account_scope=%s",
                (scope,),
            )
