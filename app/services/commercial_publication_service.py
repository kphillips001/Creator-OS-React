"""Lifecycle boundary for Commercial Publication records; no provider execution."""

from datetime import datetime, timezone
from uuid import UUID

from app.database import get_db_connection
from app.models.content_destination import ContentDestination
from app.models.commercial_offering import CommercialOfferingType
from app.models.commercial_offering import CommercialOfferingStatus
from app.models.commercial_publication import (
    CommercialPublicationProvider,
    CommercialPublicationStatus,
)
from app.repositories.commercial_offering_repository import CommercialOfferingRepository
from app.repositories.commercial_publication_repository import CommercialPublicationRepository
from app.services.content_destination_service import ContentDestinationService
from app.services.commercial_asset_eligibility_service import CommercialAssetEligibilityService


class CommercialPublicationService:
    TRANSITIONS = {
        CommercialPublicationStatus.DRAFT: {
            CommercialPublicationStatus.READY_TO_PUBLISH,
            CommercialPublicationStatus.ARCHIVED,
        },
        CommercialPublicationStatus.READY_TO_PUBLISH: {
            CommercialPublicationStatus.PUBLISHING,
            CommercialPublicationStatus.ARCHIVED,
        },
        CommercialPublicationStatus.PUBLISHING: {
            CommercialPublicationStatus.LIVE,
            CommercialPublicationStatus.FAILED,
        },
        CommercialPublicationStatus.FAILED: {
            CommercialPublicationStatus.READY_TO_PUBLISH,
            CommercialPublicationStatus.PUBLISHING,
            CommercialPublicationStatus.ARCHIVED,
        },
        CommercialPublicationStatus.LIVE: {CommercialPublicationStatus.ARCHIVED},
        CommercialPublicationStatus.ARCHIVED: set(),
    }

    def __init__(
        self, *, repository=None, offering_repository=None,
        content_destinations=None, commercial_eligibility=None,
        connection_factory=get_db_connection,
    ) -> None:
        self.repository = repository or CommercialPublicationRepository()
        self.offerings = offering_repository or CommercialOfferingRepository()
        self.content_destinations = content_destinations or ContentDestinationService()
        self.commercial_eligibility = commercial_eligibility or CommercialAssetEligibilityService(
            offering_repository=self.offerings
        )
        self.connection_factory = connection_factory

    def create_publication(
        self, *, creator_profile_id: int, commercial_offering_id,
        provider, publication_metadata=None,
    ):
        offering_id = UUID(str(commercial_offering_id))
        offering = self.offerings.get(offering_id, creator_profile_id=creator_profile_id)
        if offering is None:
            raise ValueError("Commercial Offering not found.")
        if offering.status == CommercialOfferingStatus.ARCHIVED:
            raise ValueError("Archived Commercial Offerings cannot be published.")
        if offering.primary_sales_channel is None:
            raise ValueError("Commercial Offering requires a Primary Sales Channel.")
        self.commercial_eligibility.require_offering(
            offering, creator_profile_id=creator_profile_id
        )
        normalized_provider = self._provider(provider)
        if self.repository.get_by_offering_provider(offering_id, normalized_provider):
            raise ValueError("A publication already exists for this provider.")
        return self.repository.create(
            commercial_offering_id=offering_id, provider=normalized_provider,
            status=CommercialPublicationStatus.READY_TO_PUBLISH,
            publication_metadata=publication_metadata,
        )

    def get_publication(self, publication_id, *, creator_profile_id: int):
        return self.repository.get(UUID(str(publication_id)), creator_profile_id=creator_profile_id)

    def list_publications(self, *, creator_profile_id: int, commercial_offering_id=None):
        return self.repository.list(
            creator_profile_id=creator_profile_id,
            commercial_offering_id=UUID(str(commercial_offering_id)) if commercial_offering_id else None,
        )

    def validate_transition(self, current, target) -> None:
        current_status = self._status(current)
        target_status = self._status(target)
        if target_status not in self.TRANSITIONS[current_status]:
            raise ValueError(
                f"Invalid publication transition: {current_status.value} -> {target_status.value}."
            )

    def update_status(
        self, publication_id, *, creator_profile_id: int, status,
        external_product_id=None, last_error=None, increment_retry=False,
    ):
        current = self.get_publication(publication_id, creator_profile_id=creator_profile_id)
        if current is None:
            return None
        target = self._status(status)
        self.validate_transition(current.status, target)
        return self.repository.update_status(
            current.publication_id, creator_profile_id=creator_profile_id,
            status=target,
            external_product_id=external_product_id or current.external_product_id,
            published_at=datetime.now(timezone.utc) if target == CommercialPublicationStatus.LIVE else current.published_at,
            last_error=last_error if target == CommercialPublicationStatus.FAILED else None,
            retry_count=current.retry_count + (1 if increment_retry else 0),
        )

    def mark_failed(self, publication_id, *, creator_profile_id: int, error: str):
        return self.update_status(
            publication_id, creator_profile_id=creator_profile_id,
            status=CommercialPublicationStatus.FAILED, last_error=error,
            increment_retry=True,
        )

    def mark_live(self, publication_id, *, creator_profile_id: int, external_product_id=None):
        return self.update_status(
            publication_id, creator_profile_id=creator_profile_id,
            status=CommercialPublicationStatus.LIVE,
            external_product_id=external_product_id,
        )

    def finalize_provider_live(
        self, publication_id, *, creator_profile_id: int,
        external_product_id: str, delivery_url: str, metadata,
    ):
        """Atomically commit eligible Assets and finalize provider-backed LIVE."""
        current = self.get_publication(
            publication_id, creator_profile_id=creator_profile_id
        )
        if current is None:
            raise ValueError("Commercial Publication not found.")
        if current.status == CommercialPublicationStatus.LIVE:
            if current.external_product_id != external_product_id:
                raise ValueError("LIVE publication provider identity conflicts.")
            return current
        if current.status != CommercialPublicationStatus.PUBLISHING:
            raise ValueError("Commercial Publication must be PUBLISHING before LIVE.")
        offering = self.offerings.get(
            current.commercial_offering_id, creator_profile_id=creator_profile_id
        )
        if offering is None:
            raise ValueError("Commercial Offering not found.")
        self.commercial_eligibility.require_offering(
            offering, creator_profile_id=creator_profile_id
        )
        if not external_product_id or not str(delivery_url or "").strip():
            raise ValueError("Provider UUID and delivery URL are required before LIVE.")
        with self.connection_factory() as connection:
            self._commit_offering_assets(
                offering, publication_id=current.publication_id,
                creator_profile_id=creator_profile_id, connection=connection,
            )
            finalized = self.repository.finalize_live(
                current.publication_id,
                creator_profile_id=creator_profile_id,
                external_product_id=external_product_id,
                metadata=metadata,
                connection=connection,
            )
            if finalized is None:
                raise ValueError("Commercial Publication LIVE finalization failed.")
            if metadata.get("source_workflow") in {
                "photoshoot_session_sale_preparation",
                "photoshoot_bundle_sale_preparation",
            }:
                self.offerings.update_status(
                    offering.offering_id,
                    creator_profile_id=creator_profile_id,
                    status=CommercialOfferingStatus.READY,
                    connection=connection,
                )
            return finalized

    def _commit_offering_assets(
        self, offering, *, publication_id, creator_profile_id: int, connection,
    ) -> None:
        asset_ids = [member.asset_id for member in offering.assets]
        self.commercial_eligibility.require_offering(
            offering, creator_profile_id=creator_profile_id, connection=connection
        )
        if offering.offering_type in {
            CommercialOfferingType.SINGLE_IMAGE, CommercialOfferingType.VIDEO
        }:
            if len(asset_ids) != 1:
                raise ValueError("Single-media offering must contain exactly one Asset.")
            self.content_destinations.commit_to_destination(
                asset_ids[0], ContentDestination.SINGLE_PPV,
                assigned_by_profile_id=creator_profile_id,
                source_workflow="commercial_publication_live",
                source_reference=f"commercial_publication:{publication_id}",
                reason="Provider-backed paid offering reached LIVE.",
                metadata={"offering_id": str(offering.offering_id)},
                connection=connection,
            )
            return
        if offering.offering_type == CommercialOfferingType.PHOTOSET:
            inconsistent = [
                asset_id for asset_id in asset_ids
                if self.content_destinations.get_destination(
                    asset_id, connection=connection
                ).destination != ContentDestination.PHOTOSET
            ]
            if inconsistent:
                raise ValueError(
                    "PHOTOSET membership is not committed consistently: "
                    + ", ".join(map(str, inconsistent))
                )
            return
        if offering.offering_type == CommercialOfferingType.BUNDLE:
            allowed = {
                ContentDestination.BUNDLE,
                ContentDestination.PHOTOSET,
                ContentDestination.SINGLE_PPV,
                ContentDestination.VIDEOSET,
            }
            inconsistent = [
                asset_id for asset_id in asset_ids
                if self.content_destinations.get_destination(
                    asset_id, connection=connection
                ).destination not in allowed
            ]
            if inconsistent:
                raise ValueError(
                    "BUNDLE membership is not commercially committed: "
                    + ", ".join(map(str, inconsistent))
                )
            return
        raise ValueError(
            f"No LIVE commitment rule exists for {offering.offering_type.value}."
        )

    @staticmethod
    def _provider(value):
        try:
            return value if isinstance(value, CommercialPublicationProvider) else CommercialPublicationProvider(str(value).upper())
        except ValueError as error:
            raise ValueError(f"Unsupported publication provider: {value}") from error

    @staticmethod
    def _status(value):
        try:
            return value if isinstance(value, CommercialPublicationStatus) else CommercialPublicationStatus(str(value).upper())
        except ValueError as error:
            raise ValueError(f"Unsupported publication status: {value}") from error
