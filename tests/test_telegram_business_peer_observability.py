import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.integrations.telegram.business_connection_capture import (
    TelegramBusinessConnectionCapture,
)
from app.services.telegram_business_peer_observation_service import (
    TelegramBusinessPeerObservationService,
)


NOW = datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc)


class Repository:
    def __init__(self, value=None):
        self.value = value
        self.events = []

    def capture(self, event):
        self.events.append(event)
        return self.value

    def evidence(self, **_scope):
        return self.value


def evidence(last_inbound):
    return {
        "business_connection_id": "bc-1", "is_enabled": True,
        "can_reply": True, "last_business_inbound_at": last_inbound,
        "last_observed_at": last_inbound, "observation_count": 1,
    }


def test_recent_and_stale_evidence_are_reported_as_evidence_not_permission():
    recent = TelegramBusinessPeerObservationService(
        repository=Repository(evidence(NOW - timedelta(hours=2))), now=lambda: NOW,
    ).evidence(business_connection_id="bc-1", telegram_peer_user_id=7)
    stale = TelegramBusinessPeerObservationService(
        repository=Repository(evidence(NOW - timedelta(hours=25))), now=lambda: NOW,
    ).evidence(business_connection_id="bc-1", telegram_peer_user_id=7)
    assert recent["recent_peer_evidence"] is True
    assert recent["evidence_age_seconds"] == 7200
    assert stale["recent_peer_evidence"] is False
    assert stale["evidence_only_not_provider_guarantee"] is True


def test_observer_has_no_conversation_sales_generation_or_send_dependencies():
    paths = [
        Path("app/integrations/telegram/business_connection_capture.py"),
        Path("app/repositories/telegram_business_peer_observation_repository.py"),
        Path("app/services/telegram_business_peer_observation_service.py"),
    ]
    imported = {
        alias.name
        for path in paths
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    for forbidden in (
        "ConversationGateway", "SalesBrain", "OrdinaryChatReply",
        "PurchaseIntent", "Ava", "sendMessage",
    ):
        assert all(forbidden not in name for name in imported)


def test_unknown_connection_can_be_ignored_by_repository_contract():
    repository = Repository(None)
    service = TelegramBusinessPeerObservationService(repository=repository)
    event = TelegramBusinessConnectionCapture.parse({
        "update_id": 1,
        "business_message": {
            "business_connection_id": "unknown", "message_id": 2,
            "date": 3, "from": {"id": 4},
            "chat": {"id": 4, "type": "private"},
        },
    })[0]
    assert service.capture(event) is None
    assert repository.events == [event]


def test_schema_enforces_replay_and_message_idempotency_and_known_connection():
    migration = Path(
        "migrations/forward/20260909_106_telegram_business_peer_observations.sql"
    ).read_text(encoding="utf-8")
    repository = Path(
        "app/repositories/telegram_business_peer_observation_repository.py"
    ).read_text(encoding="utf-8")
    assert "UNIQUE (bot_api_update_id,event_type,telegram_message_id)" in migration
    assert "telegram_business_peer_inbound_message_unique" in migration
    assert "telegram_business_peer_connection_fkey" in migration
    assert "ON CONFLICT DO NOTHING" in repository
    assert "telegram_business_connections" in repository


def test_restart_repoll_uses_stable_provider_identity_not_message_text():
    first = TelegramBusinessConnectionCapture.parse({
        "update_id": 44,
        "business_message": {
            "business_connection_id": "bc-1", "message_id": 55,
            "date": 66, "from": {"id": 77},
            "chat": {"id": 77, "type": "private"}, "text": "first",
        },
    })[0]
    replay = TelegramBusinessConnectionCapture.parse({
        "update_id": 44,
        "business_message": {
            "business_connection_id": "bc-1", "message_id": 55,
            "date": 66, "from": {"id": 77},
            "chat": {"id": 77, "type": "private"}, "text": "changed",
        },
    })[0]
    assert first == replay
    assert not hasattr(first, "text")
