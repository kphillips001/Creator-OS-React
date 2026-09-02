"""Narrow Bot API lifecycle poller; never processes Business chat messages."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping

import requests

from app.integrations.telegram.business_connection_capture import (
    BOT_API_ALLOWED_UPDATES,
    TelegramBusinessConnectionCapture,
)


class TelegramBusinessConnectionWorker:
    def __init__(self, *, bot_token, lifecycle_service, session=None,
                 timeout_seconds=20):
        self.endpoint = f"https://api.telegram.org/bot{str(bot_token).strip()}/getUpdates"
        self.lifecycle_service = lifecycle_service
        self.session = session or requests.Session()
        self.timeout_seconds = int(timeout_seconds)
        self.offset = None

    def poll_once(self):
        params = {
            "timeout": self.timeout_seconds,
            "limit": 100,
            "allowed_updates": json.dumps(BOT_API_ALLOWED_UPDATES),
        }
        if self.offset is not None:
            params["offset"] = self.offset
        response = self.session.get(
            self.endpoint, params=params, timeout=self.timeout_seconds + 5,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping) or payload.get("ok") is not True:
            raise RuntimeError("Telegram Business lifecycle polling failed.")
        updates = payload.get("result") or []
        captured = []
        for update in updates:
            if not isinstance(update, Mapping):
                continue
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                self.offset = max(self.offset or 0, update_id + 1)
            event = TelegramBusinessConnectionCapture._parse(update)
            if event is not None:
                captured.append(self.lifecycle_service.capture(event))
        return tuple(captured)

    def run_forever(self, *, stop_requested=lambda: False):
        while not stop_requested():
            try:
                self.poll_once()
            except Exception:
                time.sleep(5)
