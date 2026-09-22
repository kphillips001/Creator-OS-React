"""Explicit neutral transport evidence for injected regression-test adapters."""
from datetime import datetime, timezone
from app.models.telegram_transport_contract import TelegramReachability


class ReachableTestSender:
    def prepare_delivery(self, *, chat_id, requirements):
        evidence = TelegramReachability("BOT_API", "isolated-test-bot", chat_id,
            "BOT_INBOUND", datetime.now(timezone.utc), sender_id=42)
        evidence.validate(requirements)
        return evidence


class InvocationTestRepository:
    def recover_expired_invocations(self): return []
    def begin_invocation(self, operation_id, *, owner, evidence):
        return {"operation_id": operation_id, "owner": owner, **evidence}
    def record_transport_evidence(self, operation_id, *, owner, evidence):
        return {"operation_id": operation_id, "owner": owner, **evidence}
