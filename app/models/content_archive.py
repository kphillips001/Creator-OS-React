"""Content Studio archive models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.models.generation_engine import utc_now


@dataclass(frozen=True)
class ContentArchiveRecord:
    archive_id: str
    image_id: str
    archive_type: str
    destination: str
    current_file_path: str
    original_output_reference: str
    provider_id: str
    workflow: str | None = None
    platform: str | None = None
    caption: str | None = None
    prompt_text: str | None = None
    imported_asset_id: int | None = None
    generation_record: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str | None = None
