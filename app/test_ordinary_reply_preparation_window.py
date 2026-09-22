from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.models.ordinary_chat_reply_operation import OrdinaryChatReplyState
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.relationships_service import RelationshipsService
from app.services.schema_manager_service import SchemaManagerService


DELIVERY_AT = datetime(2026, 9, 16, 21, 25, tzinfo=timezone.utc)
PREPARATION_AT = DELIVERY_AT - timedelta(minutes=5)


def prepared_operation(**changes):
    values = {
        "state": OrdinaryChatReplyState.RETRYABLE,
        "response_payload": {"response_text": "persisted reply"},
        "response_text": "persisted reply",
        "last_error": "prepared_for_scheduled_delivery",
        "scheduled_delivery_at": DELIVERY_AT,
        "preparation_eligible_at": PREPARATION_AT,
        "next_retry_at": DELIVERY_AT,
        "send_attempt_count": 0,
        "outbound_telegram_message_id": None,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def projection(**changes):
    source = {
        "last_customer_inbound_at": PREPARATION_AT - timedelta(minutes=10),
        "last_visible_outbound_at": PREPARATION_AT - timedelta(minutes=20),
        "database_now": PREPARATION_AT,
        "control_mode": "AVA_AUTO",
        "communication_disposition": "ACTIVE",
        "operation_state": "RETRYABLE",
        "operation_last_error": "availability_deferred",
        "next_retry_at": PREPARATION_AT,
        "scheduled_delivery_at": DELIVERY_AT,
        "preparation_eligible_at": PREPARATION_AT,
        "has_response_payload": False,
        "pending_reply_preview": None,
        "generation_attempt_count": 0,
        "max_generation_attempts": 3,
        "send_attempt_count": 0,
        "max_send_attempts": 3,
        "claim_owner": None,
        "lease_expires_at": None,
    }
    source.update(changes)
    return RelationshipsService._operational_projection(source)


def test_scheduled_projection_keeps_customer_visible_delivery_time():
    item = projection()
    assert item["operationalStatus"] == "REPLY_SCHEDULED"
    assert item["nextAutomaticAttemptAt"] == DELIVERY_AT
    assert item["pendingReplyPreview"] is None


def test_prepared_projection_is_ready_for_original_delivery_time():
    item = projection(
        operation_last_error="prepared_for_scheduled_delivery",
        next_retry_at=DELIVERY_AT,
        has_response_payload=True,
        pending_reply_preview="persisted reply",
        generation_attempt_count=1,
    )
    assert item["operationalStatus"] == "REPLY_READY"
    assert item["nextAutomaticAttemptAt"] == DELIVERY_AT
    assert item["pendingReplyPreview"] == "persisted reply"


def test_prepared_response_waits_until_delivery_and_never_waits_after_due():
    operation = prepared_operation()
    assert OrdinaryChatReplyService.awaiting_scheduled_delivery(
        operation, now=PREPARATION_AT,
    ) is True
    assert OrdinaryChatReplyService.awaiting_scheduled_delivery(
        operation, now=DELIVERY_AT,
    ) is False


def test_invalidated_or_claimed_response_is_not_waiting_for_delivery():
    assert OrdinaryChatReplyService.awaiting_scheduled_delivery(
        prepared_operation(state=OrdinaryChatReplyState.SUPPRESSED),
        now=PREPARATION_AT,
    ) is False
    assert OrdinaryChatReplyService.awaiting_scheduled_delivery(
        prepared_operation(send_attempt_count=1),
        now=PREPARATION_AT,
    ) is False
    assert OrdinaryChatReplyService.awaiting_scheduled_delivery(
        prepared_operation(response_payload=None),
        now=PREPARATION_AT,
    ) is False


def test_migration_defines_forward_and_rollback_preparation_authority():
    forward = Path(
        "migrations/forward/20260916_139_ordinary_reply_preparation_window.sql"
    ).read_text(encoding="utf-8")
    rollback = Path(
        "migrations/rollback/20260916_139_ordinary_reply_preparation_window.sql"
    ).read_text(encoding="utf-8")
    assert "scheduled_delivery_at TIMESTAMPTZ" in forward
    assert "preparation_eligible_at TIMESTAMPTZ" in forward
    assert "idx_ordinary_reply_preparation_due" in forward
    assert "DROP COLUMN IF EXISTS preparation_eligible_at" in rollback
    assert "DROP COLUMN IF EXISTS scheduled_delivery_at" in rollback


def test_runtime_schema_preflight_fails_closed_without_migration_139():
    class Cursor:
        def __init__(self):
            self.query = ""

        def __enter__(self): return self
        def __exit__(self, *_): return None
        def execute(self, query, _params): self.query = query
        def fetchone(self): return None
        def fetchall(self): return []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def cursor(self): return Cursor()

    manager = SchemaManagerService(connection_factory=lambda: Connection())
    try:
        manager.assert_migration_ready(
            "20260916_139_ordinary_reply_preparation_window.sql",
            table_name="ordinary_chat_reply_operations",
            required_columns=("scheduled_delivery_at", "preparation_eligible_at"),
            required_indexes=("idx_ordinary_reply_preparation_due",),
        )
    except RuntimeError as error:
        message = str(error)
    else:
        raise AssertionError("missing migration 139 must fail ordinary-reply startup")
    assert "migration_present=False" in message
    assert "Apply the named migration" in message
