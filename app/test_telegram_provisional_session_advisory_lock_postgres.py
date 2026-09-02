"""PostgreSQL lock-isolation regression without persistent fixture rows."""
from app.database import get_db_connection
from app.repositories.telegram_provisional_sales_session_repository import (
    provisional_session_advisory_lock_key,
)


def test_provisional_session_bigint_lock_serializes_same_scope_only():
    same = provisional_session_advisory_lock_key(
        fanvue_account_id=2, telegram_user_id=7_857_064_998,
    )
    other_customer = provisional_session_advisory_lock_key(
        fanvue_account_id=2, telegram_user_id=7_857_064_999,
    )
    other_account = provisional_session_advisory_lock_key(
        fanvue_account_id=3, telegram_user_id=7_857_064_998,
    )
    with get_db_connection() as first, get_db_connection() as second:
        try:
            with first.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s::bigint)", (same,))
            with second.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_try_advisory_xact_lock(%s::bigint) acquired",
                    (same,),
                )
                assert cursor.fetchone()["acquired"] is False
                cursor.execute(
                    "SELECT pg_try_advisory_xact_lock(%s::bigint) acquired",
                    (other_customer,),
                )
                assert cursor.fetchone()["acquired"] is True
                cursor.execute(
                    "SELECT pg_try_advisory_xact_lock(%s::bigint) acquired",
                    (other_account,),
                )
                assert cursor.fetchone()["acquired"] is True
        finally:
            first.rollback()
            second.rollback()
