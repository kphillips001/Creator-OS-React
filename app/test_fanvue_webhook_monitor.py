from app.services.fanvue_webhook_monitor_service import FanvueWebhookMonitorService
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.fanvue_webhook_monitor import router
from app.services.fanvue_webhook_monitor_service import fanvue_webhook_monitor


def test_monitor_is_newest_first_and_retains_details():
    clock = iter((1.0, 1.025, 2.0, 2.01)).__next__
    monitor = FanvueWebhookMonitorService(clock=clock)
    first = monitor.begin(
        raw_body=b'{"event_type":"message.received","sender":{"uuid":"fan-1"}}',
        headers={"x-fanvue-signature": "signature-1"},
        request_path="/webhooks/fanvue",
    )
    monitor.complete(first, http_status=200, signature_valid=True)
    second = monitor.begin(
        raw_body=b'{"event_type":"purchase.created","transactionOrderId":"tx-1"}',
        headers={"x-fanvue-event-id": "event-2"},
        request_path="/webhooks/fanvue",
    )
    monitor.complete(
        second,
        http_status=500,
        signature_valid=True,
        normalization_result={"event_type": "purchase_created"},
        persistence_result={"persisted": False},
        processing_result={"retry_count": 2},
        exception="repository failed",
    )

    items = monitor.list_items()
    assert [item["eventName"] for item in items] == [
        "purchase.created", "message.received"
    ]
    assert items[0]["eventId"] == "event-2"
    assert items[0]["retryCount"] == 2
    assert items[0]["durationMs"] == 10.0
    assert items[0]["payload"]["transactionOrderId"] == "tx-1"


def test_monitor_is_bounded_and_redacts_sensitive_values():
    monitor = FanvueWebhookMonitorService(limit=1, clock=lambda: 1.0)
    for event_id in ("first", "second"):
        trace = monitor.begin(
            raw_body=(
                f'{{"id":"{event_id}","access_token":"secret"}}'.encode()
            ),
            headers={"authorization": "Bearer secret"},
            request_path="/webhooks/fanvue",
        )
        monitor.complete(trace, http_status=200)

    items = monitor.list_items()
    assert len(items) == 1
    assert items[0]["eventId"] == "second"
    assert items[0]["payload"]["access_token"] == "[REDACTED]"
    assert items[0]["headers"]["authorization"] == "[REDACTED]"


def test_read_only_api_exposes_captured_webhook_and_empty_state():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    headers = {"X-Creator-OS-Developer": "true"}
    fanvue_webhook_monitor.clear_for_test()
    assert client.get(
        "/api/v1/developer/fanvue-webhook-monitor", headers=headers
    ).json() == {
        "items": [],
        "lastWebhookReceived": None,
        "storage": "process-memory",
        "limit": 100,
    }

    trace = fanvue_webhook_monitor.begin(
        raw_body=b'{"event_type":"subscription.new"}',
        headers={},
        request_path="/webhooks/fanvue",
    )
    fanvue_webhook_monitor.complete(trace, http_status=200)
    body = client.get(
        "/api/v1/developer/fanvue-webhook-monitor", headers=headers
    ).json()
    assert body["items"][0]["eventName"] == "subscription.new"
    assert body["lastWebhookReceived"] == body["items"][0]["timestamp"]
    fanvue_webhook_monitor.clear_for_test()
