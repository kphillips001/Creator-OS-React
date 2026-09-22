from contextlib import contextmanager
from unittest.mock import Mock
from uuid import uuid4

from app.services.historical_survivor_reconciliation_service import HistoricalSurvivorReconciliationService


class Cursor:
    def __init__(self, rows): self.rows=list(rows); self.current=[]
    def execute(self, sql, _params): self.current=self.rows.pop(0)
    def fetchone(self): return self.current[0] if self.current else None
    def fetchall(self): return self.current
    def __enter__(self): return self
    def __exit__(self, *_): return False


class Connection:
    def __init__(self, rows): self.cursor_value=Cursor(rows); self.committed=False
    def cursor(self): return self.cursor_value
    def commit(self): self.committed=True


def factory(rows):
    connection=Connection(rows)
    @contextmanager
    def value(): yield connection
    return value


def operation(**changes):
    base={"operation_id":uuid4(),"state":"SUPPRESSED",
          "last_error":"SUPERSEDED_PENDING_GENERATION","send_attempt_count":0,
          "outbound_telegram_message_id":None,"claim_owner":None,"lease_expires_at":None,
          "telegram_account_scope":"AVA","telegram_chat_id":7,
          "inbound_telegram_message_id":10,"inbound_received_at":"2026-01-01T00:00:00Z",
          "delivery_payload":{"conversationBurst":{"obligations":["ANSWER_DIRECT_QUESTION"]}},
          "burst_obligations":["ANSWER_DIRECT_QUESTION"]}
    base.update(changes); return base


def test_question_followup_retains_one_current_survivor():
    service=HistoricalSurvivorReconciliationService(connection_factory=factory([
        [operation()], [{"telegram_message_id":10,"customer_text":"question"},
                        {"telegram_message_id":11,"customer_text":"clarification"}], [], [],
    ]))
    result=service.inspect(operation()["operation_id"])
    assert result["disposition"]=="CURRENT_OBLIGATION_SURVIVES"
    assert result["freshnessMessageId"]==11


def test_later_answer_makes_obligation_obsolete():
    service=HistoricalSurvivorReconciliationService(connection_factory=factory([
        [operation()], [{"telegram_message_id":10,"customer_text":"question"}], [{"?column?":1}], [],
    ]))
    assert service.inspect(uuid4())["disposition"]=="OBLIGATION_OBSOLETE"


def test_missing_archive_is_ambiguous_and_never_mutates():
    service=HistoricalSurvivorReconciliationService(connection_factory=factory([
        [operation()], [], [], [],
    ]))
    assert service.reconcile(uuid4())["disposition"]=="AMBIGUOUS_OPERATOR_REVIEW"


def test_no_meaningful_obligation_is_obsolete():
    row=operation(burst_obligations=[],delivery_payload={"conversationBurst":{"obligations":[]}})
    service=HistoricalSurvivorReconciliationService(connection_factory=factory([
        [row], [{"telegram_message_id":10,"customer_text":"ok"}], [], [],
    ]))
    assert service.inspect(uuid4())["reason"]=="NO_MEANINGFUL_OBLIGATION"
