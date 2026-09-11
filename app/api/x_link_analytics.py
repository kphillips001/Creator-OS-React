"""Authenticated public ingestion for Cloudflare X CTA handoff events."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.x_link_performance_service import (
    XLinkIngestionAuthenticationError,
    XLinkPerformanceService,
)


router = APIRouter(prefix="/api/v1/analytics/x-link-clicks", tags=["x-link-analytics"])


class XLinkClickEvent(BaseModel):
    eventId: UUID
    attributionToken: str = Field(min_length=24, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    occurredAt: datetime
    eventType: Literal["X_TELEGRAM_CTA_HANDOFF"]
    classification: Literal["LIKELY_BROWSER"]
    classificationReason: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9_]+$")
    schemaVersion: Literal[1]


@router.post("/events")
async def ingest_x_link_click(
    request: Request,
    timestamp: str = Header(alias="X-X-Link-Timestamp"),
    event_id: str = Header(alias="X-X-Link-Event-Id"),
    signature: str = Header(alias="X-X-Link-Signature"),
):
    raw_body = await request.body()
    service = XLinkPerformanceService()
    try:
        service.authenticate(
            raw_body=raw_body, timestamp=timestamp,
            event_id=event_id, signature=signature,
        )
    except XLinkIngestionAuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    try:
        event = XLinkClickEvent.model_validate_json(raw_body)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid X Link event payload.") from error
    if str(event.eventId) != event_id:
        raise HTTPException(status_code=400, detail="Event ID header does not match payload.")
    result = service.ingest(event.model_dump(mode="json"))
    if not result["accepted"]:
        raise HTTPException(status_code=404, detail="Unknown or revoked attribution token.")
    return {"success": True, "duplicate": bool(result["duplicate"]),
            "eventId": str(event.eventId)}
