"""Single-attempt, durable private operator Telegram alerts."""
from __future__ import annotations

import os
from uuid import uuid4

import requests


class OperatorTelegramAlertService:
    def __init__(self, *, repository, bot_token=None, destination_chat_id=None,
                 http_client=requests, worker_id=None):
        self.repository = repository
        self.bot_token = str(bot_token if bot_token is not None else
                             os.getenv("TELEGRAM_OPERATOR_ALERT_BOT_TOKEN", "")).strip()
        self.destination_chat_id = str(
            destination_chat_id if destination_chat_id is not None else
            os.getenv("TELEGRAM_OPERATOR_ALERT_CHAT_ID", "")
        ).strip()
        self.http = http_client
        self.worker_id = worker_id or f"operator-alert-{uuid4()}"

    def authorize_and_attempt(self, *, incident=None, text, notification_type=None,
                              correlation_id=None, context=None):
        incident = dict(incident or {})
        operation = self.repository.create_notification(
            incident_id=incident.get("incident_id"),
            destination_chat_id=self.destination_chat_id or None,
            payload={"text": text},
            notification_type=notification_type or "ABUSIVE_CUSTOMER_REVIEW",
            correlation_id=correlation_id,
            context=context,
        )
        if operation["state"] != "AUTHORIZED":
            return operation
        claimed = self.repository.claim_notification(
            operation_id=operation["notification_operation_id"], owner=self.worker_id
        )
        if claimed is None:
            return operation
        if not self.bot_token:
            return self.repository.fail_notification(
                operation_id=claimed["notification_operation_id"],
                reason="OPERATOR_ALERT_BOT_TOKEN_NOT_CONFIGURED",
            )
        try:
            response = self.http.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": self.destination_chat_id, "text": text}, timeout=15,
            )
            body = response.json() if hasattr(response, "json") else {}
            if not response.ok or not body.get("ok"):
                raise RuntimeError(f"TELEGRAM_OPERATOR_ALERT_REJECTED_HTTP_{response.status_code}")
            message_id = str((body.get("result") or {}).get("message_id") or "")
            if not message_id:
                raise RuntimeError("TELEGRAM_OPERATOR_ALERT_MISSING_MESSAGE_ID")
            return self.repository.confirm_notification(
                operation_id=claimed["notification_operation_id"],
                provider_message_id=message_id,
            )
        except Exception as error:
            return self.repository.fail_notification(
                operation_id=claimed["notification_operation_id"],
                reason=str(error)[:500],
            )
