"""Canonical relationship-aware routing for durable manual Telegram messages."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from app.database import get_db_connection

from app.repositories.telegram_business_peer_observation_repository import (
    TelegramBusinessPeerObservationRepository,
)
from app.services.telegram_business_connection_service import (
    TelegramBusinessConnectionService,
)


class ManualTelegramRouteUnavailable(RuntimeError):
    code = "MANUAL_TELEGRAM_ROUTE_UNAVAILABLE"


class ManualTelegramRuntimeUnavailable(ManualTelegramRouteUnavailable):
    code = "MANUAL_TELEGRAM_PRIVATE_RUNTIME_UNAVAILABLE"


@dataclass(frozen=True)
class ManualTelegramRoute:
    kind: str
    business_connection_id: str | None = None


class TelegramPrivateManualRouteReadiness:
    """Require a fresh singleton heartbeat advertising private dispatch support."""
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory=connection_factory

    def available(self):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT 1 FROM public.worker_heartbeats
                WHERE worker_name='Telegram' AND status IN ('RUNNING','IDLE')
                  AND last_heartbeat_at>=NOW()-INTERVAL '90 seconds'
                  AND metadata->>'lifecycle_state'='CONNECTED'
                  AND COALESCE((metadata->>'authorized')::boolean,FALSE)=TRUE
                  AND COALESCE(metadata->'ordinary_reply_scheduler_last_result','{}'::jsonb)
                      ? 'manualPrivateDispatches'
                ORDER BY last_heartbeat_at DESC LIMIT 1""")
            return cursor.fetchone() is not None


class TelegramManualTransportResolver:
    BUSINESS = "TELEGRAM_BUSINESS"
    PRIVATE = "AVA_TELETHON_PRIVATE"

    def __init__(self, *, owner_user_id=None, bot_id=None, connections=None,
                 peer_observations=None, private_readiness=None):
        self.owner_user_id = self._positive(owner_user_id if owner_user_id is not None
            else os.getenv("TELEGRAM_BUSINESS_OWNER_USER_ID"))
        self.bot_id = self._positive(bot_id if bot_id is not None
            else os.getenv("TELEGRAM_BUSINESS_BOT_ID"))
        self.connections = connections
        self.peers = peer_observations or TelegramBusinessPeerObservationRepository()
        self.private_readiness = private_readiness or TelegramPrivateManualRouteReadiness()

    def resolve(self, context):
        connection = self._active_connection()
        if connection is not None:
            evidence = self.peers.evidence(
                business_connection_id=connection.business_connection_id,
                telegram_peer_user_id=int(context["telegram_user_id"]),
                telegram_chat_id=int(context["telegram_chat_id"]),
            )
            if (evidence and evidence.get("is_enabled") is True
                    and evidence.get("can_reply") is True
                    and isinstance(evidence.get("last_business_inbound_at"), datetime)
                    and evidence["last_business_inbound_at"].tzinfo is not None
                    and timedelta(0) <= datetime.now(timezone.utc)-evidence["last_business_inbound_at"] < timedelta(hours=24)
                    and int(evidence.get("observation_count") or 0) > 0):
                return ManualTelegramRoute(
                    self.BUSINESS, connection.business_connection_id)
        if context.get("telegram_account_scope") == self.PRIVATE:
            if self.private_readiness.available():
                return ManualTelegramRoute(self.PRIVATE)
            raise ManualTelegramRuntimeUnavailable(
                "The authorized private Telegram runtime is not ready for manual sends.")
        raise ManualTelegramRouteUnavailable(
            "This customer is not reachable through an authorized Telegram route.")

    def _active_connection(self):
        if not self.owner_user_id or not self.bot_id:
            return None
        service = self.connections or TelegramBusinessConnectionService(
            bot_telegram_user_id=self.bot_id)
        return service.active(business_owner_telegram_user_id=self.owner_user_id)

    @staticmethod
    def _positive(value):
        try: parsed = int(str(value or "").strip())
        except (TypeError, ValueError): return None
        return parsed if parsed > 0 else None


class StaticBusinessManualTransportResolver:
    """Compatibility boundary for explicitly injected test transports."""
    def resolve(self, _context):
        return ManualTelegramRoute(TelegramManualTransportResolver.BUSINESS)
