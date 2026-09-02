"""PostgreSQL certification for durable purchase acknowledgement ordering."""
from datetime import datetime, timezone
from uuid import uuid4

from app.models.telegram_sales_delivery_operation import TelegramSalesDeliveryState
from app.repositories.telegram_sales_delivery_repository import TelegramSalesDeliveryRepository
from app.services.telegram_sales_delivery_service import TelegramSalesDeliveryService
from app.test_private_chat_settlement_postgres import connection_factory, fixture


def acknowledgement_operation(*, state="TELEGRAM_ACCEPTED"):
    values = fixture()
    with connection_factory() as connection:
        connection.execute(
            """UPDATE purchase_intents SET status='PURCHASED',purchased_at=NOW(),
               attribution_result='ATTRIBUTED' WHERE purchase_intent_id=%s""",
            (values["intent_id"],),
        )
        thread_id = connection.execute(
            """INSERT INTO chat_threads(fanvue_user_id,fanvue_account_id)
               VALUES (%s,%s) RETURNING id""",
            (values["user"], values["account"]),
        ).fetchone()["id"]
        operation_id = uuid4()
        confirmed_at = datetime.now(timezone.utc) if state == "CONFIRMED" else None
        connection.execute(
            """INSERT INTO telegram_sales_delivery_operations(
               operation_id,correlation_id,creator_profile_id,fanvue_account_id,
               conversation_thread_id,fanvue_user_id,telegram_chat_id,
               inbound_telegram_message_id,outbound_telegram_message_id,
               purchase_intent_id,commercial_offering_id,commercial_publication_id,
               response_text,delivery_payload,state,telegram_accepted_at,confirmed_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,9001,%s,%s,%s,'Got it',
               '{"message_text":"Got it","metadata":{"message_purpose":
               "PURCHASE_ACKNOWLEDGEMENT"}}'::jsonb,%s,NOW(),%s)""",
            (operation_id, f"ack:{uuid4()}", values["creator"], values["account"],
             thread_id, values["user"], values["telegram"],
             8_000_000 + uuid4().int % 900_000, values["intent_id"],
             values["offering_id"], values["publication_id"], state, confirmed_at),
        )
    return values, operation_id


def test_confirm_and_acknowledgement_commit_with_one_canonical_timestamp():
    values, operation_id = acknowledgement_operation()
    repository = TelegramSalesDeliveryRepository(connection_factory=connection_factory)
    operation = repository.get_by_correlation(
        repository._one(
            "SELECT * FROM telegram_sales_delivery_operations WHERE operation_id=%s",
            (operation_id,),
        ).correlation_id
    )
    confirmed = TelegramSalesDeliveryService(repository=repository).confirm(operation)
    with connection_factory() as connection:
        row = connection.execute(
            """SELECT operation.state,operation.confirmed_at,
                      intent.purchase_acknowledged_at
               FROM telegram_sales_delivery_operations operation
               JOIN purchase_intents intent USING(purchase_intent_id)
               WHERE operation.operation_id=%s""",
            (operation_id,),
        ).fetchone()
    assert confirmed.state is TelegramSalesDeliveryState.CONFIRMED
    assert row["state"] == "CONFIRMED"
    assert row["purchase_acknowledged_at"] == row["confirmed_at"]


def test_startup_repairs_confirmed_ack_gap_without_new_delivery():
    values, operation_id = acknowledgement_operation(state="CONFIRMED")
    repository = TelegramSalesDeliveryRepository(connection_factory=connection_factory)
    before = repository._one(
        "SELECT * FROM telegram_sales_delivery_operations WHERE operation_id=%s",
        (operation_id,),
    )
    recovered = TelegramSalesDeliveryService(repository=repository).recover_startup()
    with connection_factory() as connection:
        row = connection.execute(
            """SELECT operation.state,operation.confirmed_at,
                      intent.purchase_acknowledged_at,
                      operation.outbound_telegram_message_id
               FROM telegram_sales_delivery_operations operation
               JOIN purchase_intents intent USING(purchase_intent_id)
               WHERE operation.operation_id=%s""",
            (operation_id,),
        ).fetchone()
    assert len(recovered) == 1
    assert before.state is TelegramSalesDeliveryState.CONFIRMED
    assert row["state"] == "CONFIRMED" and row["outbound_telegram_message_id"] == 9001
    assert row["purchase_acknowledged_at"] == row["confirmed_at"]


def test_duplicate_confirm_preserves_confirmation_and_acknowledgement_timestamp():
    values, operation_id = acknowledgement_operation()
    repository = TelegramSalesDeliveryRepository(connection_factory=connection_factory)
    operation = repository._one(
        "SELECT * FROM telegram_sales_delivery_operations WHERE operation_id=%s",
        (operation_id,),
    )
    service = TelegramSalesDeliveryService(repository=repository)
    first = service.confirm(operation)
    second = service.confirm(first)
    with connection_factory() as connection:
        row = connection.execute(
            """SELECT operation.confirmed_at,intent.purchase_acknowledged_at
               FROM telegram_sales_delivery_operations operation
               JOIN purchase_intents intent USING(purchase_intent_id)
               WHERE operation.operation_id=%s""",
            (operation_id,),
        ).fetchone()
    assert second.state is TelegramSalesDeliveryState.CONFIRMED
    assert row["purchase_acknowledged_at"] == row["confirmed_at"] == first.confirmed_at
