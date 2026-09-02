from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.repositories.telegram_provisional_sales_session_repository import (
    TelegramProvisionalSalesSessionRepository,
)


OLD_SESSION = UUID("d67bd8fa-7cf1-4605-bad0-7229f831ecc3")
OLD_INTENT = UUID("8bb9270a-f682-4953-992b-95ec05a1bbf3")


class Cursor:
    def __init__(self):
        self.calls = []
        self.row = None

    def __enter__(self): return self
    def __exit__(self, *_): return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        self.row = None
        if "LEFT JOIN public.purchase_intents" in normalized:
            self.row = {
                "provisional_session_id": OLD_SESSION,
                "first_purchase_intent_id": OLD_INTENT,
                "state": "AWAITING_PAYMENT",
                "bound_intent_status": "ADMIN_CLOSED",
            }
        elif "INSERT INTO public.telegram_provisional_sales_sessions" in normalized:
            self.row = {
                "provisional_session_id": params[0],
                "first_purchase_intent_id": None,
                "state": "ACTIVE",
            }

    def fetchone(self): return self.row


class Connection:
    def __init__(self): self.current = Cursor()
    def cursor(self): return self.current


def test_admin_closed_binding_is_retired_before_fresh_session_creation(monkeypatch):
    connection = Connection()

    @contextmanager
    def factory(): yield connection

    repository = TelegramProvisionalSalesSessionRepository(connection_factory=factory)
    monkeypatch.setattr(repository, "_model", lambda row: row)
    prospect = SimpleNamespace(
        telegram_sales_prospect_id=uuid4(), creator_profile_id=2,
        fanvue_account_id=2, telegram_user_id=7857064998,
        telegram_chat_id=7857064998,
    )
    fresh = repository.create_or_get(
        prospect=prospect, photoshoot_reference="photoshoot",
        session_strategy="CANONICAL_SESSION",
        configured_base_price_minor=300, commercial_context={},
    )
    statements = [sql for sql, _ in connection.current.calls]
    retirement = next(i for i, sql in enumerate(statements)
                      if "SET state='ADMIN_CLOSED'" in sql)
    insertion = next(i for i, sql in enumerate(statements)
                     if "INSERT INTO public.telegram_provisional_sales_sessions" in sql)
    assert retirement < insertion
    assert fresh["provisional_session_id"] != OLD_SESSION
    assert fresh["first_purchase_intent_id"] is None


def test_migration_preserves_linkage_and_separates_active_ownership():
    forward = Path(
        "migrations/forward/20260827_098_provisional_session_administrative_close.sql"
    ).read_text()
    rollback = Path(
        "migrations/rollback/20260827_098_provisional_session_administrative_close.sql"
    ).read_text()
    assert "'ADMIN_CLOSED'" in forward
    assert "administratively_closed_at" in forward
    assert "administrative_close_reason" in forward
    assert "intent.purchase_intent_id=session.first_purchase_intent_id" in forward
    assert "DELETE" not in forward.upper()
    assert "Rollback blocked" in rollback


def test_purchase_intent_admin_close_retires_provisional_session_atomically():
    source = Path("app/repositories/purchase_intent_repository.py").read_text()
    method = source[source.index("def close_administratively"):
                    source.index("def get_active_for_buyer")]
    assert "telegram_provisional_sales_sessions" in method
    assert "first_purchase_intent_id=%s" in method
    assert "state='ADMIN_CLOSED'" in method
    assert "DELETE" not in method


def test_historical_binding_is_never_reassociated_in_place():
    source = Path(
        "app/repositories/telegram_provisional_sales_session_repository.py"
    ).read_text()
    associate = source[source.index("def associate_intent"):
                       source.index("def graduate")]
    assert "COALESCE(first_purchase_intent_id,%s)" in associate
    assert "first_purchase_intent_id=%s" in associate
    assert "first_purchase_intent_id=NULL" not in source
