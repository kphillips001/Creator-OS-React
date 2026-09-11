"""X-to-Telegram CTA ingestion and Overview reporting."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from app.models.performance_snapshot import ReportingPeriodService
from app.repositories.x_link_performance_repository import XLinkPerformanceRepository
from app.services.content_archive_service import ContentArchiveService
from app.services.social_publishing_service import SocialPublishingService


class XLinkIngestionAuthenticationError(ValueError):
    pass


class XLinkPerformanceService:
    EVENT_TYPE = "X_TELEGRAM_CTA_HANDOFF"
    CLASSIFICATION = "LIKELY_BROWSER"
    SCHEMA_VERSION = 1
    SIGNATURE_WINDOW_SECONDS = 300

    def __init__(self, *, repository=None, periods=None, archive=None, social=None,
                 secret: str | None = None, clock=None):
        self.repository = repository or XLinkPerformanceRepository()
        self.periods = periods or ReportingPeriodService()
        self.archive = archive or ContentArchiveService()
        self.social = social or SocialPublishingService()
        self.secret = secret if secret is not None else os.getenv(
            "X_LINK_ANALYTICS_INGESTION_SECRET", ""
        )
        self.clock = clock or time.time

    def authenticate(self, *, raw_body: bytes, timestamp: str, event_id: str,
                     signature: str) -> None:
        if len(self.secret.encode("utf-8")) < 32:
            raise XLinkIngestionAuthenticationError("X Link ingestion secret is not configured.")
        try:
            request_time = int(timestamp)
        except (TypeError, ValueError) as error:
            raise XLinkIngestionAuthenticationError("Invalid ingestion timestamp.") from error
        if abs(int(self.clock()) - request_time) > self.SIGNATURE_WINDOW_SECONDS:
            raise XLinkIngestionAuthenticationError("Stale ingestion timestamp.")
        signed = timestamp.encode() + b"." + event_id.encode() + b"." + raw_body
        expected = hmac.new(self.secret.encode(), signed, hashlib.sha256).hexdigest()
        supplied = str(signature or "").removeprefix("sha256=")
        if not hmac.compare_digest(expected, supplied):
            raise XLinkIngestionAuthenticationError("Invalid ingestion signature.")

    def ingest(self, event: Mapping[str, Any]) -> dict[str, Any]:
        return self.repository.ingest_event(
            event_id=str(event["eventId"]),
            attribution_token=str(event["attributionToken"]),
            occurred_at=self._datetime(event["occurredAt"]),
            event_type=str(event["eventType"]),
            classification=str(event["classification"]),
            classification_reason=str(event["classificationReason"]),
            schema_version=int(event["schemaVersion"]),
        )

    def report(self, *, creator_profile_id: int, fanvue_account_id: int,
               period: str) -> dict[str, Any]:
        resolved = self.periods.resolve(period)
        attributed = self.repository.attributed_posts(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            start=resolved.start, end=resolved.end,
        )
        by_primary = {str(row["primary_x_post_id"]): row for row in attributed}
        publish_items = self.social.list_publish_items()
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for archived in self.archive.list_records():
            if archived.archive_type != "published_x":
                continue
            archive_metadata = dict(archived.metadata or {})
            queue_id = str(archive_metadata.get("social_queue_item_id") or "")
            candidates = [item for item in publish_items
                          if item.queue_item_id == queue_id and item.platform == "x"]
            for publish_item in candidates:
                metadata = dict(publish_item.metadata or {})
                primary_id = str(
                    metadata.get("primary_x_post_id")
                    or metadata.get("provider_post_id") or ""
                )
                if not primary_id or primary_id in seen:
                    continue
                published_at = self._datetime(
                    metadata.get("primary_published_at")
                    or archive_metadata.get("publish_datetime")
                    or archived.created_at
                )
                if not resolved.contains(published_at):
                    continue
                seen.add(primary_id)
                attribution = by_primary.get(primary_id)
                requested = bool(metadata.get("x_thread_cta_requested"))
                cta_status = str(metadata.get("x_thread_cta_status") or "")
                if not requested:
                    tracking_state = "NO_CTA"
                elif cta_status != "posted":
                    tracking_state = "FAILED_CTA"
                elif attribution:
                    tracking_state = "TRACKED"
                else:
                    tracking_state = "TRACKING_UNAVAILABLE"
                items.append({
                    "primaryPostId": primary_id,
                    "ctaPostId": str(metadata.get("cta_x_post_id") or "") or None,
                    "accountName": str(metadata.get("account_name") or ""),
                    "caption": str((attribution or {}).get("primary_caption") or archived.caption or ""),
                    "thumbnailUrl": f"/api/v1/posted-content/{archived.archive_id}/media",
                    "publishedAt": published_at.isoformat(),
                    "trackingState": tracking_state,
                    "linkClicks": int(attribution.get("link_clicks") or 0) if attribution else None,
                })
        items.sort(key=lambda item: (item["publishedAt"], item["primaryPostId"]), reverse=True)
        return {"period": resolved.as_dict(), "items": items,
                "historicalBoundary": "Tracking begins with attributed Creator-OS X publications."}

    @staticmethod
    def _datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            result = value
        else:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
