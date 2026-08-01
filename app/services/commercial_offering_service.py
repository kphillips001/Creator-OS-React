"""Validated application boundary for Commercial Offerings."""

from contextlib import nullcontext
from uuid import UUID

from app.models.content_destination import ContentDestination
from app.models.commercial_offering import (
    CommercialOfferingType,
    CommercialOfferingStatus,
    PrimarySalesChannel,
)
from app.repositories.asset_repository import AssetRepository
from app.repositories.commercial_offering_repository import CommercialOfferingRepository
from app.repositories.commercial_publication_repository import CommercialPublicationRepository
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.models.commercial_publication import CommercialPublicationStatus
from app.services.content_destination_service import ContentDestinationService
from app.services.reference_asset_protection import require_commercially_eligible_asset


class CommercialOfferingBusinessError(ValueError):
    def __init__(
        self, code: str, message: str, *, required_action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.required_action = required_action


class CommercialOfferingService:
    def __init__(
        self, *, repository=None, asset_repository=None, content_destinations=None,
        publication_repository=None,
        photoshoot_repository=None,
    ) -> None:
        self.repository = repository or CommercialOfferingRepository()
        self.assets = asset_repository or AssetRepository()
        self.content_destinations = content_destinations or ContentDestinationService(
            asset_repository=self.assets
        )
        self.publications = publication_repository or CommercialPublicationRepository()
        self.photoshoots = (
            photoshoot_repository or PhotoshootCommerceRepository()
        )

    def create(
        self, *, creator_profile_id: int, offering_type, title: str,
        description: str | None, hero_asset_id: int | None,
        primary_sales_channel, asset_ids, price_minor: int | None = None,
        currency: str = "USD",
        initial_status: CommercialOfferingStatus = CommercialOfferingStatus.DRAFT,
    ):
        normalized_type = self._type(offering_type)
        channel = self._channel(primary_sales_channel)
        ordered = tuple(int(value) for value in asset_ids)
        if not ordered:
            raise ValueError("At least one canonical Asset is required.")
        if len(set(ordered)) != len(ordered):
            raise ValueError("Duplicate Asset membership is not allowed.")
        hero = int(hero_asset_id or ordered[0])
        if hero not in ordered:
            raise ValueError("Hero Asset must be a member of the Commercial Offering.")
        clean_title = str(title or "").strip()
        if not clean_title:
            raise ValueError("Commercial Offering title is required.")
        transaction = getattr(self.repository, "transaction", None)
        with transaction() if callable(transaction) else nullcontext(None) as connection:
            assets = []
            for asset_id in ordered:
                asset = self._asset(asset_id, connection)
                if asset is None or int(asset.creator_profile_id or 0) != int(creator_profile_id):
                    raise ValueError(f"Canonical Asset is unavailable: {asset_id}.")
                require_commercially_eligible_asset(asset, asset_id=asset_id)
                if (
                    normalized_type != CommercialOfferingType.BUNDLE
                    and not self._is_available(asset_id, connection)
                ):
                    raise ValueError(f"Asset {asset_id} is already commercially committed.")
                assets.append(asset)
            self._validate_shape(
                normalized_type, tuple(asset.media_type for asset in assets)
            )
            if (
                normalized_type == CommercialOfferingType.BUNDLE
                and self.photoshoots.common_approved_photoshoot(ordered) is None
            ):
                raise ValueError(
                    "BUNDLE Assets must share one approved Photoshoot lineage."
                )
            values = dict(
                creator_profile_id=creator_profile_id, offering_type=normalized_type,
                title=clean_title, description=str(description or "").strip() or None,
                hero_asset_id=hero, primary_sales_channel=channel, asset_ids=ordered,
                price_minor=price_minor, currency=currency, status=initial_status,
            )
            if connection is not None:
                values["connection"] = connection
            offering = self.repository.create(**values)
            if normalized_type in {
                CommercialOfferingType.PHOTOSET,
                CommercialOfferingType.BUNDLE,
            }:
                for asset_id in ordered:
                    if (
                        normalized_type == CommercialOfferingType.BUNDLE
                        and not self._is_available(asset_id, connection)
                    ):
                        continue
                    context = dict(
                        assigned_by_profile_id=creator_profile_id,
                        source_workflow="commercial_offering_creation",
                        source_reference=f"commercial_offering:{offering.offering_id}",
                        reason=(
                            "Asset became an immutable grouped offering member."
                        ),
                        metadata={"offering_id": str(offering.offering_id)},
                    )
                    if connection is not None:
                        context["connection"] = connection
                    self.content_destinations.commit_to_destination(
                        asset_id,
                        (
                            ContentDestination.PHOTOSET
                            if normalized_type == CommercialOfferingType.PHOTOSET
                            else ContentDestination.BUNDLE
                        ),
                        **context,
                    )
            return offering

    def get(self, offering_id: UUID | str, *, creator_profile_id: int):
        return self.repository.get(UUID(str(offering_id)), creator_profile_id=creator_profile_id)

    def list(self, *, creator_profile_id: int, search: str | None, page: int, page_size: int):
        return self.repository.list_page(
            creator_profile_id=creator_profile_id, search=search,
            page=page, page_size=page_size,
        )

    def update_metadata(
        self, offering_id: UUID | str, *, creator_profile_id: int,
        title: str, description: str | None, hero_asset_id: int,
    ):
        current = self.get(offering_id, creator_profile_id=creator_profile_id)
        if current is None:
            return None
        if hero_asset_id not in {member.asset_id for member in current.assets}:
            raise ValueError("Hero Asset must be a member of the Commercial Offering.")
        clean_title = str(title or "").strip()
        if not clean_title:
            raise ValueError("Commercial Offering title is required.")
        return self.repository.update_metadata(
            UUID(str(offering_id)), creator_profile_id=creator_profile_id,
            title=clean_title, description=str(description or "").strip() or None,
            hero_asset_id=int(hero_asset_id),
        )

    def update_pricing(
        self, offering_id: UUID | str, *, creator_profile_id: int,
        price_minor: int, currency: str = "USD",
    ):
        price = int(price_minor)
        normalized_currency = str(currency or "").strip().upper()
        if price < 300 or price > 50000:
            raise ValueError("Fanvue price must be between 300 and 50000 minor units.")
        if normalized_currency != "USD":
            raise ValueError("Commercial Offering currency must currently be USD.")
        offering_uuid = UUID(str(offering_id))
        self.validate_pricing_update(
            offering_uuid, creator_profile_id=creator_profile_id
        )
        return self.repository.update_pricing(
            offering_uuid, creator_profile_id=creator_profile_id,
            price_minor=price, currency=normalized_currency,
        )

    def validate_pricing_update(
        self, offering_id: UUID | str, *, creator_profile_id: int,
    ) -> None:
        """Enforce the single publication-aware pricing policy for all callers."""
        offering_uuid = UUID(str(offering_id))
        publications = self.publications.list(
            creator_profile_id=creator_profile_id,
            commercial_offering_id=offering_uuid,
        )
        live = next(
            (
                publication
                for publication in publications
                if publication.status == CommercialPublicationStatus.LIVE
            ),
            None,
        )
        if live is not None:
            raise CommercialOfferingBusinessError(
                "LIVE_PRICE_LOCKED",
                "Price cannot change while the provider publication is LIVE.",
                required_action="Use the provider-backed publication replacement workflow.",
            )
        if any(
            publication.status == CommercialPublicationStatus.PUBLISHING
            for publication in publications
        ):
            raise CommercialOfferingBusinessError(
                "PUBLICATION_PRICE_LOCKED",
                "Price cannot change while provider publication is in progress.",
                required_action="Wait for publication execution to finish.",
            )

    def _asset(self, asset_id: int, connection):
        if connection is None:
            return self.assets.get_by_id(asset_id)
        return self.assets.get_by_id(asset_id, connection=connection)

    def _is_available(self, asset_id: int, connection) -> bool:
        if connection is None:
            return self.content_destinations.is_available_inventory(asset_id)
        return (
            self.content_destinations.get_destination(
                asset_id, connection=connection, for_update=True
            ).destination
            == ContentDestination.AVAILABLE_INVENTORY
        )

    @staticmethod
    def _type(value) -> CommercialOfferingType:
        try:
            return value if isinstance(value, CommercialOfferingType) else CommercialOfferingType(str(value).upper())
        except ValueError as error:
            raise ValueError(f"Unsupported Commercial Offering type: {value}") from error

    @staticmethod
    def _channel(value) -> PrimarySalesChannel:
        try:
            return value if isinstance(value, PrimarySalesChannel) else PrimarySalesChannel(str(value).upper())
        except ValueError as error:
            raise ValueError(f"Unsupported Primary Sales Channel: {value}") from error

    @staticmethod
    def _validate_shape(offering_type: CommercialOfferingType, media_types: tuple[str, ...]) -> None:
        count = len(media_types)
        rules = {
            CommercialOfferingType.SINGLE_IMAGE: (count == 1 and media_types == ("image",), "exactly one image Asset"),
            CommercialOfferingType.PHOTOSET: (count >= 2 and set(media_types) == {"image"}, "two or more image Assets"),
            CommercialOfferingType.VIDEO: (count == 1 and media_types == ("video",), "exactly one video Asset"),
            CommercialOfferingType.STORY: (count == 1 and media_types == ("story",), "exactly one story Asset"),
            CommercialOfferingType.STORY_SET: (count >= 2 and set(media_types) == {"story"}, "two or more story Assets"),
            CommercialOfferingType.BUNDLE: (
                count >= 2 and set(media_types).issubset({"image", "video"}),
                "two or more image or video Assets",
            ),
        }
        valid, requirement = rules[offering_type]
        if not valid:
            raise ValueError(f"{offering_type.value} requires {requirement}.")
