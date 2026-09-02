from contextlib import contextmanager

from app.repositories.purchase_intent_repository import (
    PurchaseIntentRepository,
    purchase_intent_advisory_lock_key,
)


class RecordingCursor:
    def __init__(self):
        self.calls = []
        self._result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))
        if "SELECT purchase_intent_id" in sql:
            self._result = []
        elif "INSERT INTO public.purchase_intents" in sql:
            self._result = [{
                "purchase_intent_id": params[0],
                "creator_profile_id": params[1],
                "fanvue_account_id": params[2],
                "telegram_identity_mapping_id": params[3],
                "telegram_user_id": params[4],
                "telegram_chat_id": params[5],
                "external_fanvue_user_uuid": params[6],
                "commercial_offering_id": params[7],
                "commercial_publication_id": params[8],
                "provider": params[9],
                "provider_resource_id": params[10],
                "delivery_url": params[11],
                "telegram_message_id": params[12],
                "conversation_id": params[13],
                "correlation_id": params[14],
                "expected_price_minor": params[15],
                "expected_currency": params[16],
                "status": "CREATED",
                "created_at": params[18],
                "presented_at": None,
                "clicked_at": None,
                "expires_at": params[17],
                "abandoned_at": None,
                "purchased_at": None,
                "provider_transaction_order_id": None,
                "provider_payment_id": None,
                "provider_event_id": None,
                "attribution_result": "PENDING",
                "attribution_reason": None,
                "created_metadata": {},
                "updated_at": params[18],
                "purchase_acknowledged_at": None,
                "configured_base_price_minor": None,
                "actual_charged_price_minor": None,
                "identity_bootstrap_mode": None,
            }]
        return self

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0]


class RecordingConnection:
    def __init__(self):
        self.recording_cursor = RecordingCursor()

    def cursor(self):
        return self.recording_cursor


def test_lock_key_is_stable_isolated_and_supports_64_bit_telegram_ids():
    large = purchase_intent_advisory_lock_key(
        fanvue_account_id=2, telegram_user_id=7_857_064_998,
    )
    assert large == purchase_intent_advisory_lock_key(
        fanvue_account_id=2, telegram_user_id=7_857_064_998,
    )
    assert large != purchase_intent_advisory_lock_key(
        fanvue_account_id=2, telegram_user_id=7_857_064_999,
    )
    assert large != purchase_intent_advisory_lock_key(
        fanvue_account_id=3, telegram_user_id=7_857_064_998,
    )
    assert large != purchase_intent_advisory_lock_key(
        fanvue_account_id=2, telegram_user_id=42,
    )
    assert -(2**63) <= large <= (2**63 - 1)


def test_replace_active_uses_transaction_scoped_bigint_lock(monkeypatch):
    connection = RecordingConnection()

    @contextmanager
    def connection_factory():
        yield connection

    repository = PurchaseIntentRepository(connection_factory=connection_factory)
    monkeypatch.setattr(repository, "_insert", lambda cursor, values: values)
    values = {
        "creator_profile_id": 2,
        "fanvue_account_id": 2,
        "telegram_user_id": 7_857_064_998,
    }
    assert repository.replace_active(**values) == values

    lock_sql, lock_params = connection.recording_cursor.calls[0]
    assert lock_sql == "SELECT pg_advisory_xact_lock(%s::bigint)"
    assert lock_params == (purchase_intent_advisory_lock_key(
        fanvue_account_id=2, telegram_user_id=7_857_064_998,
    ),)
    assert len(lock_params) == 1
