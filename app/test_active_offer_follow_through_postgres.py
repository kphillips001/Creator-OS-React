"""Isolated PostgreSQL certification for one-nudge and settlement-send safety."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.repositories.active_offer_follow_through_repository import (
    ActiveOfferFollowThroughRepository,
)
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.services.post_nudge_conversation_policy_service import PostNudgeConversationPolicyService
from app.test_private_chat_settlement_postgres import connection_factory, fixture


pytestmark = pytest.mark.skipif(
    not __import__("os").getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL required",
)


def _presented_fixture():
    values = fixture()
    now = datetime.now(timezone.utc)
    PurchaseIntentRepository(connection_factory).mark_presented(
        values["intent_id"], at=now - timedelta(hours=25),
        telegram_message_id=700001,
    )
    return values, now


def _ordinary(values, *, state="GENERATED"):
    operation_id = uuid4()
    with connection_factory() as connection:
        connection.execute("""INSERT INTO ordinary_chat_reply_operations(
          operation_id,telegram_account_scope,telegram_chat_id,
          inbound_telegram_message_id,inbound_sender_telegram_user_id,
          correlation_id,inbound_message_text,inbound_received_at,state,
          response_payload,response_text,delivery_payload,generated_at)
          VALUES(%s,'AVA_TELETHON_PRIVATE',%s,%s,%s,%s,'still interested',NOW(),
          %s,'{}'::jsonb,'One follow-up','{}'::jsonb,NOW())""", (
            operation_id, values["telegram"], 100000 + uuid4().int % 800000,
            values["telegram"], str(uuid4()), state,
        ))
    return operation_id


def _scoped_ordinary(values, *, state="GENERATED"):
    operation_id = _ordinary(values, state=state)
    with connection_factory() as connection:
        row = connection.execute("""SELECT inbound_telegram_message_id
            FROM ordinary_chat_reply_operations WHERE operation_id=%s""",
            (operation_id,)).fetchone()
        connection.execute("""INSERT INTO telegram_private_inbound_messages(
          inbound_id,telegram_account_scope,telegram_user_id,telegram_chat_id,
          telegram_message_id,received_at,customer_text,creator_profile_id,
          fanvue_account_id,ingestion_provenance,automation_state_at_receipt,
          reconciliation_state,response_operation_id)
          VALUES(%s,'AVA_TELETHON_PRIVATE',%s,%s,%s,NOW(),'fixture',%s,%s,
          'ISOLATED_TEST','ENABLED','LIVE_HANDLED',%s)""", (
            uuid4(), values["telegram"], values["telegram"],
            row["inbound_telegram_message_id"], values["creator"],
            values["account"], operation_id))
    return operation_id


def test_one_confirmed_nudge_per_intent_survives_time_restart_and_race():
    values, now = _presented_fixture()
    ledger = ActiveOfferFollowThroughRepository(connection_factory)
    intent = PurchaseIntentRepository(connection_factory).get(values["intent_id"])
    first_operation = _ordinary(values)
    first = ledger.reserve(
        intent=intent, reason="TIMED", eligible_at=now,
        operation_id=first_operation, now=now,
    )
    assert first and first["nudge_sequence"] == 1
    ledger.confirm(
        operation_id=first_operation, outbound_id=700002, confirmed_at=now,
    )

    def later_reservation(_):
        reopened = ActiveOfferFollowThroughRepository(connection_factory)
        return reopened.reserve(
            intent=intent, reason="TIMED", eligible_at=now + timedelta(hours=3),
            operation_id=uuid4(), now=now + timedelta(hours=3),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(later_reservation, range(2))) == [None, None]
    assert ledger.confirmed_summary(values["intent_id"])["confirmed_count"] == 1


def test_two_workers_racing_for_first_nudge_produce_one_winner():
    values, now = _presented_fixture()
    intent = PurchaseIntentRepository(connection_factory).get(values["intent_id"])

    def reserve(_):
        return ActiveOfferFollowThroughRepository(connection_factory).reserve(
            intent=intent, reason="TIMED", eligible_at=now,
            operation_id=uuid4(), now=now,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, range(2)))
    winners = [row for row in results if row is not None]
    assert len(winners) == 1
    assert winners[0]["nudge_sequence"] == 1


def test_settlement_after_generation_is_suppressed_before_send_claim():
    values, now = _presented_fixture()
    ledger = ActiveOfferFollowThroughRepository(connection_factory)
    intent = PurchaseIntentRepository(connection_factory).get(values["intent_id"])
    operation_id = _ordinary(values)
    assert ledger.reserve(
        intent=intent, reason="TIMED", eligible_at=now,
        operation_id=operation_id, now=now,
    )
    PurchaseIntentRepository(connection_factory).update(
        values["intent_id"], status="PURCHASED", purchased_at=now,
        provider_transaction_order_id="settled-before-send",
    )
    replies = OrdinaryChatReplyRepository(connection_factory)
    blocked = replies.suppress_settled_follow_through_before_send(operation_id)
    assert blocked.state.value == "SUPPRESSED"
    assert blocked.send_attempt_count == 0
    assert replies.claim_send(operation_id, owner="worker") is None


def test_unsettled_first_nudge_can_claim_send_and_same_operation_retry_is_reused():
    values, now = _presented_fixture()
    ledger = ActiveOfferFollowThroughRepository(connection_factory)
    intent = PurchaseIntentRepository(connection_factory).get(values["intent_id"])
    operation_id = _ordinary(values)
    first = ledger.reserve(
        intent=intent, reason="TIMED", eligible_at=now,
        operation_id=operation_id, now=now,
    )
    assert ledger.reserve(
        intent=intent, reason="TIMED", eligible_at=now,
        operation_id=operation_id, now=now,
    )["event_id"] == first["event_id"]
    claimed = OrdinaryChatReplyRepository(connection_factory).claim_send(
        operation_id, owner="worker")
    assert claimed and claimed.state.value == "SENDING"


def test_post_nudge_nonconversion_remains_relationship_authority_after_expiry():
    values, now = _presented_fixture()
    ledger = ActiveOfferFollowThroughRepository(connection_factory)
    intents = PurchaseIntentRepository(connection_factory)
    intent = intents.get(values["intent_id"])
    operation_id = _ordinary(values)
    assert ledger.reserve(
        intent=intent, reason="TIMED", eligible_at=now,
        operation_id=operation_id, now=now,
    )
    assert ledger.confirm(
        operation_id=operation_id, outbound_id=700003, confirmed_at=now,
    )
    observed_at = now + timedelta(minutes=1)
    assert ledger.observe_customer_response(
        intent_id=values["intent_id"], observed_at=observed_at,
    )
    scope = dict(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
    )
    assert ledger.relationship_nonconversion(**scope)["nonconversion_count"] == 1
    intents.update(values["intent_id"], status="EXPIRED")
    reopened = ActiveOfferFollowThroughRepository(connection_factory)
    assert reopened.relationship_nonconversion(**scope)["nonconversion_count"] == 1
    intents.update(
        values["intent_id"], status="PURCHASED", purchased_at=observed_at,
        provider_transaction_order_id="settled-after-backoff",
    )
    assert reopened.relationship_nonconversion(**scope)["nonconversion_count"] == 0


def test_supporter_boundary_and_repeated_attempts_are_durable_without_new_schema():
    values, now = _presented_fixture()
    ledger = ActiveOfferFollowThroughRepository(connection_factory)
    intent = PurchaseIntentRepository(connection_factory).get(values["intent_id"])
    nudge = _ordinary(values)
    assert ledger.reserve(intent=intent, reason="TIMED", eligible_at=now,
                          operation_id=nudge, now=now)
    assert ledger.confirm(operation_id=nudge, outbound_id=700004, confirmed_at=now)
    assert ledger.observe_customer_response(intent_id=values["intent_id"],
                                             observed_at=now + timedelta(minutes=1))
    boundary = _scoped_ordinary(values)
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          state='SENT_CONFIRMED',
          sent_confirmed_at=%s,outbound_telegram_message_id=700005,
          response_payload=%s::jsonb WHERE operation_id=%s""", (
            now + timedelta(minutes=2),
            '{"diagnostic_metadata":{"post_nudge_conversation_policy":{"responsePurpose":"SUPPORTER_BOUNDARY"}}}',
            boundary))
    for offset in range(3):
        later = _scoped_ordinary(values)
        with connection_factory() as connection:
            connection.execute("""UPDATE ordinary_chat_reply_operations SET
              inbound_received_at=%s,delivery_payload=%s::jsonb
              WHERE operation_id=%s""", (
                now + timedelta(minutes=3 + offset),
                '{"postNudgeConversationPolicy":{"sexualInbound":true}}', later))
    scope = dict(creator_profile_id=values["creator"],
                 fanvue_account_id=values["account"],
                 telegram_user_id=values["telegram"],
                 telegram_chat_id=values["telegram"])
    replies = OrdinaryChatReplyRepository(connection_factory)
    assert replies.post_nudge_policy_history(**scope) == {
        "supporter_boundary_confirmed": True,
        "sexual_attempts_after_boundary": 3,
    }
    accounting = type("Accounting", (), {"today": lambda self, **scope: {
        "replies_used_today": 0, "next_reset_at": now + timedelta(days=1)}})()
    policy = PostNudgeConversationPolicyService(
        ledger=ActiveOfferFollowThroughRepository(connection_factory),
        operations=OrdinaryChatReplyRepository(connection_factory),
        accounting=accounting)
    operation = type("Operation", (), {"inbound_message_text": "hello",
        "inbound_sender_telegram_user_id": values["telegram"],
        "telegram_chat_id": values["telegram"]})()
    commercial = type("Commercial", (), {"commercial_bypass_eligible": False})()
    decision = policy.evaluate(operation=operation, commercial_decision=commercial,
                               verified_buyer=False,
                               creator_profile_id=values["creator"],
                               fanvue_account_id=values["account"])
    # Three post-boundary messages are not three failed presentations. One
    # distinct missed opportunity remains presentation-specific.
    assert decision.time_waster is False
    assert decision.evidence["failedPresentationCount"] == 1
    assert decision.evidence["investmentTreatment"] == "NORMAL_CULTIVATION"
    assert decision.response_purpose == "CASUAL_BACKOFF_CONVERSATION"
    assert decision.evidence["relationshipRemainsActive"] is True
    assert decision.evidence["ignoreChanged"] is False
