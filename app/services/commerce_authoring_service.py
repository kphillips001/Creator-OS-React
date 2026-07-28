"""Creator-facing orchestration over existing commerce domain services."""
from uuid import UUID

from app.models.commercial_publication import CommercialPublicationStatus
from app.models.commercial_offering import CommercialOfferingStatus
from app.repositories.commerce_authoring_repository import CommerceAuthoringRepository
from app.services.commercial_offering_service import CommercialOfferingService
from app.services.commercial_offering_service import CommercialOfferingBusinessError
from app.services.commercial_publication_service import CommercialPublicationService


class CommerceAuthoringError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CommerceAuthoringService:
    SUPPORTED_TYPES = {"SINGLE_IMAGE", "PHOTOSET", "VIDEO"}
    SUPPORTED_CHANNELS = {"AI_CHAT", "TELEGRAM_WALL"}

    def __init__(
        self, *, offerings=None, publications=None, read_repository=None,
    ) -> None:
        self.offerings = offerings or CommercialOfferingService()
        self.publications = publications or CommercialPublicationService(
            offering_repository=self.offerings.repository
        )
        self.reads = read_repository or CommerceAuthoringRepository()

    def create(self, *, creator_profile_id: int, offering_type, title,
               description, hero_asset_id, primary_sales_channel,
               asset_ids, price_minor, currency):
        normalized_type = str(offering_type or "").upper()
        if normalized_type not in self.SUPPORTED_TYPES:
            raise CommerceAuthoringError("INVALID_OFFERING_TYPE", "Only image, Photoset, and video offerings are supported.")
        normalized_channel = str(primary_sales_channel or "").upper()
        if normalized_channel not in self.SUPPORTED_CHANNELS:
            raise CommerceAuthoringError(
                "INVALID_SALES_CHANNEL", "Unsupported Primary Sales Channel."
            )
        self._validate_price(price_minor, currency)
        try:
            offering = self.offerings.create(
                creator_profile_id=creator_profile_id,
                offering_type=normalized_type, title=title,
                description=description, hero_asset_id=hero_asset_id,
                primary_sales_channel=normalized_channel, asset_ids=asset_ids,
                price_minor=int(price_minor), currency=str(currency).upper(),
                initial_status=CommercialOfferingStatus.READY,
            )
        except ValueError as error:
            raise self._translate(error) from error
        return offering

    def update(self, offering_id, *, creator_profile_id: int, title,
               description, price_minor, currency):
        current = self.offerings.get(offering_id, creator_profile_id=creator_profile_id)
        if current is None:
            raise CommerceAuthoringError("OFFERING_NOT_FOUND", "Commercial Offering not found.")
        publications = self.publications.list_publications(
            creator_profile_id=creator_profile_id,
            commercial_offering_id=current.offering_id,
        )
        if any(item.status == CommercialPublicationStatus.PUBLISHING for item in publications):
            raise CommerceAuthoringError("OFFERING_STATE_CONFLICT", "An actively publishing offering cannot be edited.")
        price_changed = int(price_minor) != current.price_minor or str(currency).upper() != current.currency
        self._validate_price(price_minor, currency)
        try:
            if price_changed:
                self.offerings.validate_pricing_update(
                    current.offering_id, creator_profile_id=creator_profile_id
                )
            updated = self.offerings.update_metadata(
                current.offering_id, creator_profile_id=creator_profile_id,
                title=title, description=description,
                hero_asset_id=current.hero_asset_id,
            )
            return self.offerings.update_pricing(
                updated.offering_id, creator_profile_id=creator_profile_id,
                price_minor=int(price_minor), currency=str(currency).upper(),
            )
        except CommercialOfferingBusinessError as error:
            raise CommerceAuthoringError(error.code, str(error)) from error
        except ValueError as error:
            raise self._translate(error) from error

    def archive(self, offering_id, *, creator_profile_id: int):
        current = self.offerings.get(offering_id, creator_profile_id=creator_profile_id)
        if current is None:
            raise CommerceAuthoringError("OFFERING_NOT_FOUND", "Commercial Offering not found.")
        publications = self.publications.list_publications(
            creator_profile_id=creator_profile_id,
            commercial_offering_id=current.offering_id,
        )
        if any(item.status == CommercialPublicationStatus.PUBLISHING for item in publications):
            raise CommerceAuthoringError("OFFERING_STATE_CONFLICT", "An actively publishing offering cannot be archived.")
        return self.offerings.repository.archive(
            UUID(str(offering_id)), creator_profile_id=creator_profile_id
        )

    def resolve_publication(self, offering_id, *, creator_profile_id: int):
        offering = self.offerings.get(offering_id, creator_profile_id=creator_profile_id)
        if offering is None:
            raise CommerceAuthoringError("OFFERING_NOT_FOUND", "Commercial Offering not found.")
        existing = self.publications.list_publications(
            creator_profile_id=creator_profile_id,
            commercial_offering_id=offering.offering_id,
        )
        if existing:
            publication = existing[0]
            if publication.status in {CommercialPublicationStatus.LIVE, CommercialPublicationStatus.ARCHIVED}:
                raise CommerceAuthoringError("OFFERING_STATE_CONFLICT", f"Publication is already {publication.status.value}.")
            return publication
        try:
            return self.publications.create_publication(
                creator_profile_id=creator_profile_id,
                commercial_offering_id=offering.offering_id,
                provider="FANVUE",
            )
        except ValueError as error:
            raise self._translate(error) from error

    def summary(self, *, creator_profile_id: int):
        return self.reads.summary(creator_profile_id=creator_profile_id)

    def list_page(self, **filters):
        return self.reads.list_page(**filters)

    @staticmethod
    def _validate_price(price_minor, currency):
        if str(currency or "").upper() != "USD":
            raise CommerceAuthoringError("INVALID_CURRENCY", "USD is the only supported currency.")
        if not isinstance(price_minor, int) or not 300 <= price_minor <= 50000:
            raise CommerceAuthoringError("INVALID_PRICE", "Price must be between $3.00 and $500.00.")

    @staticmethod
    def _translate(error):
        message = str(error)
        mappings = (
            ("Duplicate", "DUPLICATE_ASSET"), ("At least one", "INVALID_ASSET_COUNT"),
            ("requires", "INVALID_ASSET_COUNT"), ("committed", "ASSET_NOT_AVAILABLE"),
            ("unavailable", "ASSET_NOT_FOUND"), ("title", "INVALID_TITLE"),
            ("media", "INVALID_MEDIA_TYPE"),
        )
        code = next((value for marker, value in mappings if marker.lower() in message.lower()), "AUTHORING_VALIDATION_FAILED")
        return CommerceAuthoringError(code, message)
