"""Prepare one complete Photoshoot Bundle for one Fanvue Media Link."""

from __future__ import annotations

from hashlib import sha256
from uuid import UUID

from app.models.commercial_offering import (
    CommercialOfferingStatus, CommercialOfferingType, PrimarySalesChannel,
)
from app.models.commercial_publication import (
    CommercialPublicationProvider, CommercialPublicationStatus,
)
from app.repositories.asset_repository import AssetRepository
from app.repositories.commercial_offering_repository import CommercialOfferingRepository
from app.repositories.commercial_publication_repository import CommercialPublicationRepository
from app.repositories.commercial_publication_upload_repository import CommercialPublicationUploadRepository
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.services.commercial_offering_service import CommercialOfferingService
from app.services.commercial_publication_service import CommercialPublicationService
from app.services.fanvue_media_link_publication_executor import FanvueMediaLinkPublicationExecutor
from app.services.photoshoot_commercial_intelligence_service import PhotoshootCommercialIntelligenceService


class PhotoshootBundleSalePreparationService:
    WORKFLOW = "photoshoot_bundle_sale_preparation"

    def __init__(self, *, photoshoots=None, assets=None, offerings=None,
                 publications=None, uploads=None, offering_service=None,
                 publication_service=None, executor=None, teasers=None):
        self.photoshoots = photoshoots or PhotoshootCommerceRepository()
        self.assets = assets or AssetRepository()
        self.offerings = offerings or CommercialOfferingRepository()
        self.publications = publications or CommercialPublicationRepository()
        self.uploads = uploads or CommercialPublicationUploadRepository()
        self.offering_service = offering_service or CommercialOfferingService(
            repository=self.offerings, asset_repository=self.assets,
            publication_repository=self.publications,
            photoshoot_repository=self.photoshoots,
        )
        self.publication_service = publication_service or CommercialPublicationService(
            repository=self.publications, offering_repository=self.offerings,
        )
        self.executor = executor or FanvueMediaLinkPublicationExecutor(
            publications=self.publications, offerings=self.offerings,
            assets=self.assets, uploads=self.uploads,
            publication_service=self.publication_service,
        )
        if teasers is None:
            from app.services.photoshoot_bundle_teaser_service import PhotoshootBundleTeaserService
            teasers = PhotoshootBundleTeaserService(
                photoshoots=self.photoshoots, assets=self.assets,
            )
        self.teasers = teasers

    def inspect(self, deliverable_id, *, creator_profile_id: int):
        row, members = self._context(deliverable_id, creator_profile_id)
        asset_ids = tuple(int(item["asset_id"]) for item in members)
        offering = self._bundle_offering(row, asset_ids)
        publication = (self.publications.get_by_offering_provider(
            offering.offering_id, CommercialPublicationProvider.FANVUE,
        ) if offering else None)
        error = self._shape_error(row, offering, asset_ids) if offering else None
        metadata = dict(publication.publication_metadata if publication else {})
        link = dict(metadata.get("media_link") or {})
        url = str(link.get("url") or "").strip() or None
        ready = bool(
            not error and offering and publication
            and publication.status == CommercialPublicationStatus.LIVE
            and publication.provider_resource_status.value == "PRESENT"
            and url
        )
        preparing = bool(
            publication and publication.status in {
                CommercialPublicationStatus.READY_TO_PUBLISH,
                CommercialPublicationStatus.PUBLISHING,
            }
        )
        needs_attention = bool(
            error or (publication and publication.status == CommercialPublicationStatus.FAILED)
            or (offering and publication is None)
            or (offering and not ready and not preparing and publication is not None)
        )
        status = (
            "READY" if ready else "NEEDS_ATTENTION" if needs_attention
            else "PREPARING" if preparing else "NOT_CONFIGURED"
        )
        result = {
            "deliverableId": str(row["deliverable_id"]),
            "photoshootSessionId": str(row["photoshoot_session_id"]),
            "sellingMode": "BUNDLE",
            "bundleSalesChannel": row.get("bundle_sales_channel") or "CHAT",
            "status": status,
            "statusLabel": {
                "READY": "Paid Bundle Ready",
                "NEEDS_ATTENTION": "Paid Bundle Needs Attention",
                "PREPARING": "Preparing Paid Bundle",
                "NOT_CONFIGURED": "Paid Bundle Not Configured",
            }[status],
            "imageCount": len(asset_ids),
            "priceMinor": offering.price_minor if offering else None,
            "currency": offering.currency if offering else "USD",
            "offeringId": str(offering.offering_id) if offering else None,
            "publicationId": str(publication.publication_id) if publication else None,
            "publicationStatus": publication.status.value if publication else None,
            "providerResourceStatus": publication.provider_resource_status.value if publication else None,
            "mediaLinkUuid": publication.external_product_id if publication else None,
            "deliveryUrl": url,
            "publishedAt": publication.published_at.isoformat() if publication and publication.published_at else None,
            "updatedAt": publication.updated_at.isoformat() if publication else None,
            "error": error or (publication.last_error if publication else None),
        }
        try:
            result["promotionalTeaser"] = self.teasers.inspect(
                deliverable_id, creator_profile_id=creator_profile_id,
            )
        except Exception as teaser_error:
            result["promotionalTeaser"] = {
                "status": "NEEDS_ATTENTION", "statusLabel": "Teaser Needs Attention",
                "error": str(teaser_error), "candidates": [],
            }
        result["autonomousSales"] = self._autonomous_sales_readiness(
            paid_status=status,
            teaser_status=result["promotionalTeaser"].get("status"),
            channel=result["bundleSalesChannel"],
            intelligence_ready=(
                row.get("commercial_intelligence_status") == "READY"
                and row.get("commercial_intelligence_stage") == "COMPLETE"
                and PhotoshootCommercialIntelligenceService.has_complete_commercial_contract(
                    row.get("intelligence_profile")
                )
            ),
        )
        return result

    @staticmethod
    def _autonomous_sales_readiness(*, paid_status, teaser_status, channel,
                                    intelligence_ready=True):
        if str(channel or "CHAT") != "CHAT":
            return {
                "status": "DISABLED", "statusLabel": "Chat Sales Disabled",
                "reason": "Designated for Ava's Content Wall",
            }
        if not intelligence_ready:
            return {
                "status": "NEEDS_SETUP",
                "statusLabel": "Commercial Intelligence Incomplete",
                "reason": "Commercial intelligence needs attention",
            }
        if paid_status == "READY" and teaser_status == "READY":
            return {
                "status": "READY", "statusLabel": "Ready to Sell",
                "reason": None,
            }
        if paid_status == "NEEDS_ATTENTION":
            reason = "Bundle publication needs attention"
        elif teaser_status == "NEEDS_ATTENTION":
            reason = "Promotional teaser needs attention"
        elif paid_status == "PREPARING":
            reason = "Bundle media still preparing"
        elif paid_status != "READY":
            reason = "Needs Bundle media"
        else:
            reason = "Needs promotional teaser"
        return {
            "status": "NEEDS_SETUP", "statusLabel": "Needs Setup",
            "reason": reason,
        }

    def stage(self, deliverable_id, *, creator_profile_id: int,
              fanvue_account_id: int, price_minor: int):
        row, members = self._context(deliverable_id, creator_profile_id)
        price = self._price(price_minor)
        asset_ids = tuple(int(item["asset_id"]) for item in members)
        if len(asset_ids) < 2:
            raise ValueError("A Photoshoot Bundle requires at least two approved images.")
        offering = self._bundle_offering(row, asset_ids)
        if offering is None:
            prepared = self.offering_service.prepare_photoshoot(
                str(row["deliverable_id"]), creator_profile_id=creator_profile_id,
            )
            offering = self.offering_service.create(
                creator_profile_id=creator_profile_id,
                offering_type=CommercialOfferingType.BUNDLE,
                title=prepared["title"], description=prepared["description"],
                hero_asset_id=prepared["hero_asset_id"],
                primary_sales_channel=PrimarySalesChannel.AI_CHAT,
                asset_ids=asset_ids, price_minor=price, currency="USD",
                source_photoshoot_deliverable_id=UUID(str(row["deliverable_id"])),
                idempotency_key=self._idempotency_key(row),
            )
        error = self._shape_error(row, offering, asset_ids)
        if error:
            raise ValueError(error)
        publication = self.publications.get_by_offering_provider(
            offering.offering_id, CommercialPublicationProvider.FANVUE,
        )
        if publication and publication.status == CommercialPublicationStatus.LIVE:
            if offering.price_minor != price:
                raise ValueError("The live Bundle Media Link price is locked.")
            return (publication.publication_id,)
        if offering.price_minor != price:
            offering = self.offering_service.update_pricing(
                offering.offering_id, creator_profile_id=creator_profile_id,
                price_minor=price, currency="USD",
            )
        metadata = {
            **dict(publication.publication_metadata if publication else {}),
            "source_workflow": self.WORKFLOW,
            "fanvue_account_id": int(fanvue_account_id),
            "photoshoot_session_id": str(row["photoshoot_session_id"]),
            "photoshoot_deliverable_id": str(row["deliverable_id"]),
            "asset_ids": list(asset_ids), "image_count": len(asset_ids),
            "price_minor": price, "currency": "USD",
        }
        if publication is None:
            publication = self.publication_service.create_publication(
                creator_profile_id=creator_profile_id,
                commercial_offering_id=offering.offering_id,
                provider="FANVUE", publication_metadata=metadata,
            )
        else:
            self.publications.update_metadata(
                publication.publication_id, creator_profile_id=creator_profile_id,
                metadata=metadata,
            )
            publication = self.publication_service.get_publication(
                publication.publication_id, creator_profile_id=creator_profile_id,
            )
        if publication.status in {
            CommercialPublicationStatus.READY_TO_PUBLISH,
            CommercialPublicationStatus.FAILED,
        }:
            publication = self.publication_service.update_status(
                publication.publication_id, creator_profile_id=creator_profile_id,
                status="PUBLISHING",
            )
        elif publication.status != CommercialPublicationStatus.PUBLISHING:
            raise ValueError("Bundle publication cannot be prepared from its current state.")
        return (publication.publication_id,)

    def execute_staged(self, publication_ids, *, creator_profile_id: int,
                       fanvue_account_id: int):
        for publication_id in tuple(publication_ids):
            self.executor.execute(
                UUID(str(publication_id)), creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
            )

    def _context(self, deliverable_id, creator_profile_id):
        row = self.photoshoots.get(str(deliverable_id))
        if row is None or int(row["creator_profile_id"]) != int(creator_profile_id):
            raise KeyError("Photoshoot not found.")
        if row["registration_state"] not in {"IN_ASSET_LIBRARY", "REGISTERED"}:
            raise ValueError("Photoshoot must be in the Asset Library.")
        if str(row.get("selling_mode") or "SESSION") != "BUNDLE":
            raise ValueError("Bundle preparation requires BUNDLE selling mode.")
        members = tuple(self.photoshoots.members(str(row["photoshoot_session_id"])))
        if not members:
            raise ValueError("Photoshoot has no approved images.")
        return row, tuple(sorted(members, key=lambda item: (int(item["shot_order"]), int(item["asset_id"]))))

    def _bundle_offering(self, row, asset_ids):
        offering = self.offerings.get_by_idempotency_key(
            creator_profile_id=int(row["creator_profile_id"]),
            idempotency_key=self._idempotency_key(row),
        )
        return offering

    @staticmethod
    def _shape_error(row, offering, asset_ids):
        if offering is None:
            return None
        if offering.offering_type != CommercialOfferingType.BUNDLE:
            return "Canonical Bundle preparation key is occupied by a non-BUNDLE offering."
        if str(offering.source_photoshoot_deliverable_id) != str(row["deliverable_id"]):
            return "Canonical Bundle offering has conflicting Photoshoot attribution."
        if tuple(item.asset_id for item in offering.assets) != tuple(asset_ids):
            return "Canonical Bundle offering membership differs from approved Photoshoot membership."
        return None

    @staticmethod
    def _price(value):
        if isinstance(value, bool) or not isinstance(value, int) or not 300 <= value <= 50000:
            raise ValueError("Bundle price must be between 300 and 50,000 minor units.")
        return value

    def _idempotency_key(self, row):
        return sha256(f"{self.WORKFLOW}:{row['deliverable_id']}".encode()).hexdigest()
