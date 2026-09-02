from app.services.conversation_quality_watch_service import ConversationQualityWatchService
from app.services.operator_telegram_alert_service import OperatorTelegramAlertService


class Repo:
    def __init__(self): self.created = []
    def create_notification(self, **values):
        self.created.append(values)
        return {"notification_operation_id": "op-1", "state": "AUTHORIZED"}
    def claim_notification(self, **values): return {"notification_operation_id": "op-1"}
    def confirm_notification(self, **values): return {"notification_operation_id": "op-1", "state": "SENT_CONFIRMED"}
    def fail_notification(self, **values): return {"notification_operation_id": "op-1", "state": "FAILED"}


class Response:
    ok = True
    status_code = 200
    def json(self): return {"ok": True, "result": {"message_id": 77}}


class Http:
    def __init__(self): self.calls = []
    def post(self, url, **kwargs): self.calls.append((url, kwargs)); return Response()


def test_monitor_service_never_falls_back_to_ava_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_AVA", "ava-token")
    monkeypatch.delenv("TELEGRAM_OPERATOR_ALERT_BOT_TOKEN", raising=False)
    repo = Repo()
    result = OperatorTelegramAlertService(
        repository=repo, destination_chat_id="1", http_client=Http(),
    ).authorize_and_attempt(text="test", notification_type="AVA_CONVERSATION_REVIEW")
    assert result["state"] == "FAILED"


def test_quality_watch_deduplicates_by_customer_reason_and_window():
    repo, http = Repo(), Http()
    alerts = OperatorTelegramAlertService(
        repository=repo, bot_token="monitor-token", destination_chat_id="1", http_client=http,
    )
    watch = ConversationQualityWatchService(repository=repo, alert_service=alerts)
    diagnostics = {"conversationStyle": {
        "customerCommercialStateOverstatementReasons": ["CUSTOMER_READY_OR_COMMITTED"]
    }}
    first = watch.observe(response_text="you're ready", customer_message="tell me more",
                          diagnostics=diagnostics, creator_profile_id=1,
                          telegram_user_id=2, correlation_id="one")
    second = watch.observe(response_text="you're ready", customer_message="tell me more",
                           diagnostics=diagnostics, creator_profile_id=1,
                           telegram_user_id=2, correlation_id="two")
    assert first["conversationQualitySeverity"] == "HIGH"
    assert first["conversationQualityAlertConfirmed"] is True
    assert repo.created[0]["correlation_id"] == repo.created[1]["correlation_id"]


def test_successfully_repaired_candidate_does_not_alert():
    result = ConversationQualityWatchService.material_reasons(
        "maybe I'll give you a hint", {"conversationStyle": {
            "turnObligationsSatisfied": True,
            "finalResponseRepetitionSatisfied": True,
            "manufacturedQuestionRisk": False,
        }})
    assert result == []
