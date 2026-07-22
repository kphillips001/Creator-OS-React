"""Durable public-host references for canonical Creator OS assets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HostedAssetReference:
    reference_id: str
    asset_id: int
    host_name: str
    hosted_url: str
    source_checksum: str
    source_path: str
    created_at: datetime
    verified_at: datetime | None
    last_used_at: datetime | None
    status: str
    is_current: bool
    last_error_code: str | None = None
    last_error_message: str | None = None
    updated_at: datetime | None = None
