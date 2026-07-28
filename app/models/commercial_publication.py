"""Provider-neutral publication intent for a Commercial Offering."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


class CommercialPublicationProvider(str, Enum):
    FANVUE = "FANVUE"


class CommercialPublicationStatus(str, Enum):
    DRAFT = "DRAFT"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISHING = "PUBLISHING"
    LIVE = "LIVE"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class ProviderResourceStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    MISMATCH = "MISMATCH"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class CommercialPublication:
    publication_id: UUID
    commercial_offering_id: UUID
    provider: CommercialPublicationProvider
    status: CommercialPublicationStatus
    external_product_id: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    last_error: str | None
    retry_count: int
    publication_metadata: Mapping[str, Any] = field(default_factory=dict)
    provider_resource_status: ProviderResourceStatus = ProviderResourceStatus.UNVERIFIED
    last_reconciled_at: datetime | None = None
    reconciliation_result: str | None = None
