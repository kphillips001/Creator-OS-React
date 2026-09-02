from contextlib import contextmanager
from types import SimpleNamespace

from app.repositories.purchase_intent_repository import purchase_intent_advisory_lock_key
from app.repositories.telegram_provisional_sales_session_repository import (
    TelegramProvisionalSalesSessionRepository,
    provisional_session_advisory_lock_key,
)


class RecordingCursor:
    def __init__(self):
        self.calls = []
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        if "FROM public.telegram_provisional_sales_sessions" in normalized:
            self.rows = []
        elif "INSERT INTO public.telegram_provisional_sales_sessions" in normalized:
            self.rows = [{"provisional_session_id": params[0]}]

    def fetchone(self):
        return self.rows[0] if self.rows else None


class RecordingConnection:
    def __init__(self):
        self.cursor_instance = RecordingCursor()

    def cursor(self):
        return self.cursor_instance


def test_provisional_lock_key_supports_64_bit_scope_and_isolation():
    key = provisional_session_advisory_lock_key(
        fanvue_account_id=2, telegram_user_id=7_857_064_998,
    )
    assert key == provisional_session_advisory_lock_key(
        fanvue_account_id=2, telegram_user_id=7_857_064_998,
    )
    assert key != provisional_session_advisory_lock_key(
        fanvue_account_id=2, telegram_user_id=7_857_064_999,
    )
    assert key != provisional_session_advisory_lock_key(
        fanvue_account_id=3, telegram_user_id=7_857_064_998,
    )
    assert key != purchase_intent_advisory_lock_key(
        fanvue_account_id=2, telegram_user_id=7_857_064_998,
    )
    assert -(2**63) <= key <= 2**63 - 1


def test_create_or_get_uses_transaction_scoped_bigint_signature(monkeypatch):
    connection = RecordingConnection()

    @contextmanager
    def connection_factory():
        yield connection

    repository = TelegramProvisionalSalesSessionRepository(
        connection_factory=connection_factory,
    )
    monkeypatch.setattr(repository, "_model", lambda row: row)
    prospect = SimpleNamespace(
        telegram_sales_prospect_id="prospect",
        creator_profile_id=2,
        fanvue_account_id=2,
        telegram_user_id=7_857_064_998,
        telegram_chat_id=7_857_064_998,
    )
    created = repository.create_or_get(
        prospect=prospect,
        photoshoot_reference="fixture",
        session_strategy="CANONICAL_SESSION",
        configured_base_price_minor=300,
        commercial_context={},
    )
    assert created["provisional_session_id"] is not None
    lock_sql, lock_params = connection.cursor_instance.calls[0]
    assert lock_sql == "SELECT pg_advisory_xact_lock(%s::bigint)"
    assert lock_params == (provisional_session_advisory_lock_key(
        fanvue_account_id=2, telegram_user_id=7_857_064_998,
    ),)
