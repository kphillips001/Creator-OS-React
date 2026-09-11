import hashlib
import hmac
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.performance_snapshot import ReportingPeriod, ReportingPeriodKey
from app.services.x_link_performance_service import (
    XLinkIngestionAuthenticationError,
    XLinkPerformanceService,
)


SECRET = "local-test-secret-that-is-at-least-32-bytes"


class FakeRepository:
    def __init__(self, rows=None, ingest_result=None):
        self.rows = rows or []
        self.ingest_result = ingest_result or {"accepted": True, "duplicate": False}
        self.ingested = []
        self.report_arguments = None

    def ingest_event(self, **values):
        self.ingested.append(values)
        return self.ingest_result

    def attributed_posts(self, **_values):
        self.report_arguments = _values
        return self.rows


class FakePeriods:
    def resolve(self, _period):
        return ReportingPeriod(
            key=ReportingPeriodKey.TODAY,
            timezone_name="America/New_York",
            start=datetime(2026, 9, 8, 4, tzinfo=timezone.utc),
            end=datetime(2026, 9, 9, 4, tzinfo=timezone.utc),
            generated_at=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
        )


def signature(body, timestamp="1000", event_id="event-1"):
    message = timestamp.encode() + b"." + event_id.encode() + b"." + body
    return hmac.new(SECRET.encode(), message, hashlib.sha256).hexdigest()


def test_ingestion_hmac_accepts_exact_body_and_rejects_invalid_or_stale_requests():
    body = b'{"eventId":"event-1"}'
    service = XLinkPerformanceService(repository=FakeRepository(), secret=SECRET, clock=lambda: 1000)
    service.authenticate(raw_body=body, timestamp="1000", event_id="event-1", signature=signature(body))
    with pytest.raises(XLinkIngestionAuthenticationError, match="Invalid"):
        service.authenticate(raw_body=body + b" ", timestamp="1000", event_id="event-1", signature=signature(body))
    with pytest.raises(XLinkIngestionAuthenticationError, match="Stale"):
        service.authenticate(raw_body=body, timestamp="1", event_id="event-1", signature=signature(body, "1"))


def test_ingestion_preserves_repository_duplicate_result():
    repository = FakeRepository(ingest_result={"accepted": True, "duplicate": True})
    service = XLinkPerformanceService(repository=repository, secret=SECRET)
    result = service.ingest({
        "eventId": "11111111-1111-4111-8111-111111111111",
        "attributionToken": "opaque_token_that_is_long_enough",
        "occurredAt": "2026-09-08T12:00:00Z",
        "eventType": "X_TELEGRAM_CTA_HANDOFF",
        "classification": "LIKELY_BROWSER",
        "classificationReason": "SIGNED_BROWSER_HANDOFF",
        "schemaVersion": 1,
    })
    assert result["duplicate"] is True
    assert repository.ingested[0]["occurred_at"].tzinfo is timezone.utc


def test_report_uses_local_archive_and_distinguishes_tracking_states():
    repository = FakeRepository(rows=[{
        "primary_x_post_id": "post-tracked", "primary_caption": "Tracked caption",
        "link_clicks": 3,
    }])
    archive = SimpleNamespace(list_records=lambda: [
        SimpleNamespace(archive_id="archive-1", archive_type="published_x", caption="Tracked caption", created_at="2026-09-08T12:00:00Z", metadata={"social_queue_item_id": "queue-1"}),
        SimpleNamespace(archive_id="archive-2", archive_type="published_x", caption="Old caption", created_at="2026-09-08T13:00:00Z", metadata={"social_queue_item_id": "queue-2"}),
        SimpleNamespace(archive_id="archive-3", archive_type="published_x", caption="Tomorrow", created_at="2026-09-09T05:00:00Z", metadata={"social_queue_item_id": "queue-3"}),
    ])
    social = SimpleNamespace(list_publish_items=lambda: [
        SimpleNamespace(queue_item_id="queue-1", platform="x", metadata={"primary_x_post_id": "post-tracked", "primary_published_at": "2026-09-08T12:00:00Z", "x_thread_cta_requested": True, "x_thread_cta_status": "posted", "cta_x_post_id": "cta-1"}),
        SimpleNamespace(queue_item_id="queue-2", platform="x", metadata={"primary_x_post_id": "post-old", "primary_published_at": "2026-09-08T13:00:00Z", "x_thread_cta_requested": True, "x_thread_cta_status": "posted"}),
        SimpleNamespace(queue_item_id="queue-3", platform="x", metadata={"primary_x_post_id": "post-tomorrow", "primary_published_at": "2026-09-09T05:00:00Z", "x_thread_cta_requested": False}),
    ])
    report = XLinkPerformanceService(
        repository=repository, periods=FakePeriods(), archive=archive, social=social,
    ).report(creator_profile_id=1, fanvue_account_id=2, period="TODAY")
    states = {item["primaryPostId"]: item for item in report["items"]}
    assert states["post-tracked"]["trackingState"] == "TRACKED"
    assert states["post-tracked"]["linkClicks"] == 3
    assert states["post-old"]["trackingState"] == "TRACKING_UNAVAILABLE"
    assert states["post-old"]["linkClicks"] is None
    assert states["post-tracked"]["thumbnailUrl"].endswith("/archive-1/media")
    assert "post-tomorrow" not in states
    assert repository.report_arguments["start"] == datetime(2026, 9, 8, 4, tzinfo=timezone.utc)
    assert repository.report_arguments["end"] == datetime(2026, 9, 9, 4, tzinfo=timezone.utc)


def test_migration_has_forward_rollback_uniqueness_and_reporting_indexes():
    from pathlib import Path

    forward = Path("migrations/forward/20260908_104_x_link_performance.sql").read_text()
    rollback = Path("migrations/rollback/20260908_104_x_link_performance.sql").read_text()
    repository = Path("app/repositories/x_link_performance_repository.py").read_text()
    assert "attribution_token TEXT NOT NULL UNIQUE" in forward
    assert "cta_x_post_id TEXT NULL UNIQUE" in forward
    assert "UNIQUE (creator_profile_id, fanvue_account_id, publish_operation_id, x_account_name)" in forward
    assert "event_id UUID PRIMARY KEY" in forward
    assert "ON CONFLICT (event_id) DO NOTHING" in repository
    assert "(x_link_attribution_id, occurred_at)" in forward
    assert "DROP TABLE IF EXISTS public.x_link_click_events" in rollback
    assert rollback.index("x_link_click_events") < rollback.index("x_link_attributions")
