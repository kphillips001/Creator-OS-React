"""Canonical Business metadata poller; never invokes conversation or delivery."""
from __future__ import annotations
import json
import os
import time
from datetime import datetime, timezone
from collections.abc import Mapping
import requests
from app.integrations.telegram.business_connection_capture import (
    TelegramBusinessConnectionCapture, TelegramBusinessConnectionEvent,
    TelegramBusinessPeerEvent,
)

BUSINESS_UPDATE_TYPES = ("business_connection", "business_message",
                         "edited_business_message", "deleted_business_messages")

class BusinessIngestionError(RuntimeError):
    pass

class TelegramBusinessConnectionWorker:
    def __init__(self, *, bot_token, lifecycle_service, peer_observation_service=None,
                 session=None, timeout_seconds=20, business_owner_user_id=None):
        self.endpoint = f"https://api.telegram.org/bot{str(bot_token).strip()}/getUpdates"
        self.lifecycle_service = lifecycle_service
        self.peer_observation_service = peer_observation_service
        self.session = session or requests.Session()
        self.timeout_seconds = int(timeout_seconds)
        self.business_owner_user_id = business_owner_user_id
        # Restart intentionally re-polls unacknowledged updates. Durable observations
        # are idempotent; this consumer never replays conversational work.
        self.offset = None
        self.health = dict(mode="POLLING", owner_pid=os.getpid(), status="STARTING",
                           webhook_configured=None, conflict=False, errors=0,
                           conflicts=0, rejected_updates=0, last_poll_success=None,
                           last_bot_update_received=None, last_business_update_received=None,
                           last_observation_persisted=None, last_error=None)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _get(self, method, **kwargs):
        try:
            response = self.session.get(self.endpoint.rsplit("/", 1)[0]+"/"+method,
                                        timeout=self.timeout_seconds+5, **kwargs)
            code = getattr(response, "status_code", 200)
            if code == 409:
                raise BusinessIngestionError("BUSINESS_INGESTION_CONFLICT: Bot API consumer conflict")
            if code != 200:
                raise BusinessIngestionError(f"BUSINESS_INGESTION_HTTP_{code}")
            payload = response.json()
            if not isinstance(payload, Mapping) or payload.get("ok") is not True:
                raise BusinessIngestionError("BUSINESS_INGESTION_PROVIDER_REJECTED")
            return payload.get("result")
        except BusinessIngestionError:
            raise
        except Exception as error:
            # requests exceptions can embed the bot token; never persist their text.
            raise BusinessIngestionError("BUSINESS_INGESTION_REQUEST_FAILED") from None

    def record_error(self, error):
        code = str(error) if isinstance(error, BusinessIngestionError) else "BUSINESS_INGESTION_PERSISTENCE_FAILED"
        conflict = "CONFLICT" in code
        self.health.update(status="CONFLICT" if conflict else "ERROR", conflict=conflict,
                           last_error=code, last_error_at=self._now())
        self.health["errors"] += 1
        if conflict:
            self.health["conflicts"] += 1

    def poll_once(self):
        try:
            return self._poll_once()
        except Exception as error:
            self.record_error(error)
            raise

    def _poll_once(self):
        webhook = self._get("getWebhookInfo")
        if not isinstance(webhook, Mapping):
            raise BusinessIngestionError("BUSINESS_INGESTION_INVALID_WEBHOOK_STATE")
        configured = bool(webhook.get("url"))
        self.health.update(webhook_configured=configured, webhook_checked_at=self._now())
        if configured:
            raise BusinessIngestionError("BUSINESS_INGESTION_CONFLICT: Webhook configured while Business ingestion mode is polling.")
        params = dict(timeout=self.timeout_seconds, limit=100,
                      allowed_updates=json.dumps(BUSINESS_UPDATE_TYPES))
        if self.offset is not None:
            params["offset"] = self.offset
        updates = self._get("getUpdates", params=params)
        if not isinstance(updates, list):
            raise BusinessIngestionError("BUSINESS_INGESTION_INVALID_UPDATES")
        captured = []
        for update in updates:
            if not isinstance(update, Mapping) or type(update.get("update_id")) is not int:
                raise BusinessIngestionError("BUSINESS_INGESTION_INVALID_UPDATE_ID")
            self.health.update(last_bot_update_received=self._now(), last_update_id=update["update_id"])
            business = any(k in update for k in BUSINESS_UPDATE_TYPES)
            events = TelegramBusinessConnectionCapture.parse(update)
            if business:
                self.health["last_business_update_received"] = self._now()
                if not events:
                    raise BusinessIngestionError("BUSINESS_INGESTION_MALFORMED_BUSINESS_UPDATE")
            for event in events:
                result = None
                if isinstance(event, TelegramBusinessConnectionEvent):
                    if self.business_owner_user_id is not None and event.business_user_id != self.business_owner_user_id:
                        self.health["rejected_updates"] += 1
                        continue
                    result = self.lifecycle_service.capture(event)
                elif isinstance(event, TelegramBusinessPeerEvent):
                    if self.business_owner_user_id is not None:
                        current = self.lifecycle_service.current(business_owner_telegram_user_id=self.business_owner_user_id)
                        if not current or current.business_connection_id != event.business_connection_id:
                            self.health["rejected_updates"] += 1
                            self.health["last_rejection"] = "UNKNOWN_OR_STALE_BUSINESS_CONNECTION"
                            continue
                    if self.peer_observation_service is None:
                        raise BusinessIngestionError("BUSINESS_INGESTION_OBSERVER_MISSING")
                    result = self.peer_observation_service.capture(event)
                    if result is None:
                        raise BusinessIngestionError("BUSINESS_INGESTION_OBSERVATION_NOT_PERSISTED")
                    self.health["last_observation_persisted"] = self._now()
                    if event.provider_timestamp is not None:
                        self.health["update_lag_seconds"] = max(0, time.time()-event.provider_timestamp)
                if result is not None:
                    captured.append(result)
            # Never acknowledge a failed persistence. The next request confirms
            # only completely processed updates; restart duplicates are DB-idempotent.
            self.offset = max(self.offset or 0, update["update_id"]+1)
        self.health.update(status="HEALTHY", conflict=False, last_error=None,
                           last_poll_success=self._now(), next_offset=self.offset)
        return tuple(captured)

    def run_forever(self, *, stop_requested=lambda: False):
        while not stop_requested():
            try:
                self.poll_once()
            except Exception:
                time.sleep(5)
