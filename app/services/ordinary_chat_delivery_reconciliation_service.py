"""Governed reconciliation of externally proven ordinary Telegram delivery."""
from __future__ import annotations

from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository


class OrdinaryChatDeliveryReconciliationService:
    def __init__(self, *, repository=None):
        self.repository = repository or OrdinaryChatReplyRepository()

    @staticmethod
    def assess_history(*, operation, history):
        from app.services.telegram_transport_reconciliation import assess_telegram_history
        return assess_telegram_history(operation=operation, history=history)

    def reconcile(self, *, external_evidence, authorized_sender_id, **scope):
        evidence = dict(external_evidence or {})
        required = ("telegram_message_id", "telegram_chat_id", "telegram_sender_id",
                    "telegram_sent_at", "customer_visible_text", "outbound")
        if any(evidence.get(key) is None for key in required):
            return None
        if evidence["outbound"] is not True:
            return None
        if int(evidence["telegram_chat_id"]) != int(scope["telegram_chat_id"]):
            return None
        if int(evidence["telegram_sender_id"]) != int(authorized_sender_id):
            return None
        if str(evidence["customer_visible_text"]) != str(scope["expected_text"]):
            return None
        return self.repository.reconcile_send_uncertain_delivery(
            **scope,
            telegram_message_id=int(evidence["telegram_message_id"]),
            telegram_sent_at=evidence["telegram_sent_at"],
            telegram_sender_id=int(evidence["telegram_sender_id"]),
            authorized_sender_id=int(authorized_sender_id),
            evidence_source=str(evidence.get("evidence_source") or "UNKNOWN"),
        )
