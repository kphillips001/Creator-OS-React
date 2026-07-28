"""Read-only provider reconciliation for official Fanvue Media Links."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.models.commercial_publication import (
    CommercialPublicationProvider,
    ProviderResourceStatus,
)
from app.repositories.commercial_publication_repository import (
    CommercialPublicationRepository,
)
from app.services.commercial_publication_service import CommercialPublicationService
from app.services.fanvue_official_client import FanvueOfficialClient


@dataclass(frozen=True)
class FanvueReconciliationResult:
    publication_id: UUID
    provider_resource_status: ProviderResourceStatus
    result: str
    publication_status: str
    last_reconciled_at: datetime | None


class FanvueCommercialPublicationReconciliationService:
    def __init__(
        self, *, repository=None, publication_service=None, client_factory=None,
    ) -> None:
        self.repository = repository or CommercialPublicationRepository()
        self.publications = publication_service or CommercialPublicationService(
            repository=self.repository
        )
        self.client_factory = client_factory or (
            lambda account_id: FanvueOfficialClient(account_id)
        )

    def reconcile(
        self, publication_id, *, creator_profile_id: int, fanvue_account_id: int,
    ) -> FanvueReconciliationResult:
        publication = self.publications.get_publication(
            publication_id, creator_profile_id=creator_profile_id
        )
        if publication is None:
            raise ValueError("Commercial Publication not found.")
        if publication.provider != CommercialPublicationProvider.FANVUE:
            raise ValueError("Only FANVUE publications can use this reconciler.")
        provider_id = publication.external_product_id or str(
            publication.publication_metadata.get("media_link", {}).get("uuid") or ""
        )
        if not provider_id:
            updated = self.repository.record_reconciliation(
                publication.publication_id,
                creator_profile_id=creator_profile_id,
                resource_status=ProviderResourceStatus.UNVERIFIED,
                result="PROVIDER_RESOURCE_ID_MISSING",
            )
            return self._result(updated)

        response = self.client_factory(fanvue_account_id).list_media_links()
        records = tuple(response.get("data") or ())
        matches = [item for item in records if str(item.get("uuid")) == provider_id]
        if not matches:
            updated = self.repository.record_reconciliation(
                publication.publication_id,
                creator_profile_id=creator_profile_id,
                resource_status=ProviderResourceStatus.MISSING,
                result="PROVIDER_RESOURCE_MISSING",
                archive_live=True,
            )
            return self._result(updated)
        if len(matches) != 1:
            updated = self.repository.record_reconciliation(
                publication.publication_id,
                creator_profile_id=creator_profile_id,
                resource_status=ProviderResourceStatus.AMBIGUOUS,
                result="MULTIPLE_PROVIDER_RECORDS",
            )
            return self._result(updated)

        expected = publication.publication_metadata.get("media_link", {})
        expected_price = expected.get("price_minor")
        expected_media = tuple(sorted(expected.get("media_uuids") or ()))
        actual = matches[0]
        actual_price = actual.get("price")
        actual_media = tuple(sorted(actual.get("mediaUuids") or ()))
        if (
            expected_price is None
            or int(actual_price or -1) != int(expected_price)
            or actual_media != expected_media
        ):
            updated = self.repository.record_reconciliation(
                publication.publication_id,
                creator_profile_id=creator_profile_id,
                resource_status=ProviderResourceStatus.MISMATCH,
                result="PROVIDER_COMPOSITION_OR_PRICE_MISMATCH",
            )
            return self._result(updated)
        updated = self.repository.record_reconciliation(
            publication.publication_id,
            creator_profile_id=creator_profile_id,
            resource_status=ProviderResourceStatus.PRESENT,
            result="PROVIDER_RESOURCE_CONFIRMED",
        )
        return self._result(updated)

    @staticmethod
    def _result(publication) -> FanvueReconciliationResult:
        return FanvueReconciliationResult(
            publication_id=publication.publication_id,
            provider_resource_status=publication.provider_resource_status,
            result=publication.reconciliation_result or "",
            publication_status=publication.status.value,
            last_reconciled_at=publication.last_reconciled_at,
        )
