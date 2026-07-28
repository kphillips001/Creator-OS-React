"""Durable Fanvue upload checkpoint records for Commercial Publications."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID

@dataclass(frozen=True)
class CommercialPublicationUpload:
    publication_upload_id: UUID
    publication_id: UUID
    asset_id: int
    provider: str
    fanvue_account_id: int
    provider_media_uuid: str | None
    provider_upload_id: str | None
    media_type: str
    content_hash: str
    file_size_bytes: int
    part_size_bytes: int | None
    total_parts: int | None
    uploaded_parts: Mapping[str, Any] = field(default_factory=dict)
    processing_status: str = "pending"
    upload_status: str = "pending"
    retry_count: int = 0
    last_error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
