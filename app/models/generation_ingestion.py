"""Generation result ingestion models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.models.generation_engine import utc_now


GENERATION_ASSET_METADATA_KEY = "content_studio_generation"


@dataclass(frozen=True)
class GenerationAssetIngestionRecord:
    ingestion_id: str
    generation_job_id: str
    generation_request_id: str
    generation_result_id: str
    output_reference: str
    status: str
    asset_id: int | None = None
    local_file_path: str | None = None
    message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str | None = None


@dataclass(frozen=True)
class GenerationResultIngestionResult:
    success: bool
    generation_job_id: str
    imported_asset_ids: tuple[int, ...] = ()
    records: tuple[GenerationAssetIngestionRecord, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def imported_count(self) -> int:
        return len(self.imported_asset_ids)
