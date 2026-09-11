from datetime import datetime, timezone

from app.repositories.telegram_business_peer_observation_repository import (
    TelegramBusinessPeerObservationRepository,
)


class TelegramBusinessPeerObservationService:
    REPLY_WINDOW_SECONDS = 24 * 60 * 60

    def __init__(self, repository=None, now=None):
        self.repository = repository or TelegramBusinessPeerObservationRepository()
        self.now = now or (lambda: datetime.now(timezone.utc))

    def capture(self, event):
        return self.repository.capture(event)

    def evidence(self, *, business_connection_id, telegram_peer_user_id):
        value = self.repository.evidence(
            business_connection_id=business_connection_id,
            telegram_peer_user_id=telegram_peer_user_id,
        )
        if value is None:
            return None
        last_inbound = value.get("last_business_inbound_at")
        age_seconds = None
        if last_inbound is not None:
            normalized = (
                last_inbound.replace(tzinfo=timezone.utc)
                if last_inbound.tzinfo is None else last_inbound
            )
            age_seconds = max(0, int((self.now() - normalized).total_seconds()))
        return {
            **value,
            "evidence_age_seconds": age_seconds,
            "recent_peer_evidence": (
                age_seconds is not None and age_seconds <= self.REPLY_WINDOW_SECONDS
            ),
            "reply_window_seconds": self.REPLY_WINDOW_SECONDS,
            "evidence_only_not_provider_guarantee": True,
        }
