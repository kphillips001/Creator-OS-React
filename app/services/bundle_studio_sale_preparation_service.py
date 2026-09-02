"""Bundle Studio source adapter for the canonical offering/publication pipeline."""
from hashlib import sha256
from uuid import UUID

from app.database import get_db_connection
from app.models.commercial_offering import CommercialOfferingStatus, CommercialOfferingType, PrimarySalesChannel
from app.models.commercial_publication import CommercialPublicationProvider, CommercialPublicationStatus
from app.repositories.asset_repository import AssetRepository
from app.repositories.commercial_offering_repository import CommercialOfferingRepository
from app.repositories.commercial_publication_repository import CommercialPublicationRepository
from app.repositories.commercial_publication_upload_repository import CommercialPublicationUploadRepository
from app.repositories.generation_library_projection_repository import GenerationLibraryProjectionRepository
from app.services.asset_registration_service import AssetRegistrationService
from app.services.commercial_offering_service import CommercialOfferingService
from app.services.commercial_publication_service import CommercialPublicationService
from app.services.fanvue_media_link_publication_executor import FanvueMediaLinkPublicationExecutor


class BundleStudioSalePreparationService:
    WORKFLOW = "bundle_studio_sale_preparation"

    def __init__(self, *, connection_factory=get_db_connection, generations=None, assets=None,
                 offerings=None, publications=None, uploads=None, registration=None,
                 offering_service=None, publication_service=None, executor=None):
        self.connection_factory = connection_factory
        self.generations = generations or GenerationLibraryProjectionRepository()
        self.assets = assets or AssetRepository()
        self.offerings = offerings or CommercialOfferingRepository()
        self.publications = publications or CommercialPublicationRepository()
        self.uploads = uploads or CommercialPublicationUploadRepository()
        self.registration = registration or AssetRegistrationService(
            asset_repository=self.assets, analyze_on_registration=False)
        self.offering_service = offering_service or CommercialOfferingService(
            repository=self.offerings, asset_repository=self.assets,
            publication_repository=self.publications)
        self.publication_service = publication_service or CommercialPublicationService(
            repository=self.publications, offering_repository=self.offerings)
        self.executor = executor or FanvueMediaLinkPublicationExecutor(
            publications=self.publications, offerings=self.offerings, assets=self.assets,
            uploads=self.uploads, publication_service=self.publication_service)
        from app.services.bundle_studio_teaser_service import BundleStudioTeaserService
        self.teasers = BundleStudioTeaserService(assets=self.assets)

    def inspect(self, bundle_id, *, creator_profile_id: int):
        bundle, members = self._context(bundle_id, creator_profile_id)
        offering = self._offering(bundle)
        publication = self.publications.get_by_offering_provider(
            offering.offering_id, CommercialPublicationProvider.FANVUE) if offering else None
        metadata = dict(publication.publication_metadata if publication else {})
        link = dict(metadata.get("media_link") or {})
        ready = bool(publication and publication.status == CommercialPublicationStatus.LIVE and link.get("url"))
        status = "READY" if ready else "NEEDS_ATTENTION" if publication and publication.status == CommercialPublicationStatus.FAILED else "PREPARING" if offering else "NOT_CONFIGURED"
        result = {
            "bundleId": str(bundle["bundle_id"]), "workspaceStatus": bundle["status"],
            "destination": bundle.get("sales_destination"), "status": status,
            "statusLabel": {"READY":"Paid Bundle Ready","NEEDS_ATTENTION":"Paid Bundle Needs Attention","PREPARING":"Preparing Paid Bundle","NOT_CONFIGURED":"Paid Bundle Not Configured"}[status],
            "memberCount": len(members), "priceMinor": offering.price_minor if offering else None,
            "currency": offering.currency if offering else "USD",
            "offeringId": str(offering.offering_id) if offering else None,
            "publicationId": str(publication.publication_id) if publication else None,
            "publicationStatus": publication.status.value if publication else None,
            "mediaLinkUuid": publication.external_product_id if publication else None,
            "deliveryUrl": link.get("url"), "error": publication.last_error if publication else None,
            "members": [{"imageId": item["image_id"], "position": int(item["position"]),
                         "assetId": self._asset_id(item["image_id"])} for item in members],
        }
        draft = metadata.get("content_vault_caption_draft")
        result["contentVaultCaption"] = dict(draft) if isinstance(draft, dict) else None
        try:
            from app.services.bundle_studio_teaser_service import BundleStudioTeaserService
            result["promotionalTeaser"] = BundleStudioTeaserService().inspect(bundle_id, creator_profile_id=creator_profile_id)
        except (KeyError, ValueError) as error:
            result["promotionalTeaser"] = {"status":"NOT_CONFIGURED", "statusLabel":"Teaser Not Configured", "error":str(error), "candidates":[]}
        if bundle.get("sales_destination") == "CONTENT_WALL" and offering:
            from app.services.commerce_telegram_vault_service import CommerceTelegramVaultService
            result["contentVaultPublication"] = CommerceTelegramVaultService().status(offering.offering_id, creator_profile_id=creator_profile_id)
        result["readyForChat"] = bool(ready and bundle.get("sales_destination") == "CHAT" and result["promotionalTeaser"].get("status") == "READY")
        return result

    def content_vault_context(self, bundle_id, *, creator_profile_id: int):
        bundle, members = self._context(bundle_id, creator_profile_id)
        if bundle.get("sales_destination") != "CONTENT_WALL": raise ValueError("Content Vault captions are available only for WALL Bundles.")
        offering = self._offering(bundle)
        if offering is None or offering.status != CommercialOfferingStatus.READY: raise ValueError("Bundle sale preparation must be READY before authoring captions.")
        asset_ids = tuple(self._asset_id(item["image_id"]) for item in members)
        if any(value is None for value in asset_ids) or tuple(item.asset_id for item in offering.assets) != asset_ids:
            raise ValueError("Canonical paid Bundle membership is invalid.")
        publication = self.publications.get_by_offering_provider(offering.offering_id, CommercialPublicationProvider.FANVUE)
        if publication is None: raise ValueError("The prepared Bundle publication could not be found.")
        return bundle, tuple({"asset_id": value, "shot_order": index} for index, value in enumerate(asset_ids, 1)), offering, publication

    def stage(self, bundle_id, *, creator_profile_id: int, destination: str,
              fanvue_account_id: int, price_minor: int):
        bundle, members = self._context(bundle_id, creator_profile_id)
        if len(members) < 2: raise ValueError("A Bundle requires at least two images.")
        normalized = str(destination).upper()
        if normalized not in {"CHAT", "CONTENT_WALL"}: raise ValueError("Choose CHAT or CONTENT_WALL.")
        price = int(price_minor)
        if not 300 <= price <= 50000: raise ValueError("Bundle price must be between 300 and 50,000 minor units.")
        if bundle.get("sales_destination") and bundle["sales_destination"] != normalized:
            raise ValueError("Bundle selling destination is locked after preparation begins.")
        asset_ids = tuple(self._register(item["image_id"], creator_profile_id) for item in members)
        offering = self._offering(bundle)
        if offering is None:
            offering = self.offering_service.create(
                creator_profile_id=creator_profile_id, offering_type=CommercialOfferingType.BUNDLE,
                title=bundle["name"], description=f"{len(asset_ids)}-image bundle",
                hero_asset_id=asset_ids[0], primary_sales_channel=(PrimarySalesChannel.AI_CHAT if normalized == "CHAT" else PrimarySalesChannel.TELEGRAM_WALL),
                asset_ids=asset_ids, price_minor=price, currency="USD",
                source_bundle_studio_bundle_id=UUID(str(bundle["bundle_id"])),
                idempotency_key=self._key(bundle["bundle_id"]),
            )
            with self.connection_factory() as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE public.bundle_studio_bundles SET status='PREPARING',sales_destination=%s,commercial_offering_id=%s,updated_at=NOW() WHERE bundle_id=%s",
                               (normalized, offering.offering_id, bundle["bundle_id"]))
        elif tuple(item.asset_id for item in offering.assets) != asset_ids:
            raise ValueError("Canonical Bundle offering membership differs from Bundle Studio membership.")
        elif offering.price_minor != price:
            offering = self.offering_service.update_pricing(offering.offering_id, creator_profile_id=creator_profile_id, price_minor=price, currency="USD")
        publication = self.publications.get_by_offering_provider(offering.offering_id, CommercialPublicationProvider.FANVUE)
        metadata = {**dict(publication.publication_metadata if publication else {}),
                    "source_workflow": self.WORKFLOW, "bundle_studio_bundle_id": str(bundle["bundle_id"]),
                    "fanvue_account_id": int(fanvue_account_id), "asset_ids": list(asset_ids),
                    "image_count": len(asset_ids), "price_minor": price, "currency": "USD"}
        if publication is None:
            publication = self.publication_service.create_publication(creator_profile_id=creator_profile_id,
                commercial_offering_id=offering.offering_id, provider="FANVUE", publication_metadata=metadata)
        else:
            self.publications.update_metadata(publication.publication_id, creator_profile_id=creator_profile_id, metadata=metadata)
        if publication.status in {CommercialPublicationStatus.READY_TO_PUBLISH, CommercialPublicationStatus.FAILED}:
            publication = self.publication_service.update_status(publication.publication_id, creator_profile_id=creator_profile_id, status="PUBLISHING")
        elif publication.status == CommercialPublicationStatus.LIVE:
            return ()
        return (publication.publication_id,)

    def execute_staged(self, publication_ids, *, creator_profile_id: int, fanvue_account_id: int):
        for publication_id in tuple(publication_ids):
            self.executor.execute(UUID(str(publication_id)), creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id)
            publication = self.publications.get(UUID(str(publication_id)), creator_profile_id=creator_profile_id)
            offering = self.offerings.get(publication.commercial_offering_id, creator_profile_id=creator_profile_id)
            if offering and offering.source_bundle_studio_bundle_id:
                with self.connection_factory() as connection, connection.cursor() as cursor:
                    cursor.execute("UPDATE public.bundle_studio_bundles SET status='COMPLETED',updated_at=NOW() WHERE bundle_id=%s", (offering.source_bundle_studio_bundle_id,))

    def _register(self, image_id, creator_profile_id):
        record = self.generations.get(str(image_id))
        if record is None: raise KeyError(f"Generation Library image not found: {image_id}")
        result = self.registration.register_generated_image(record, creator_profile_id=creator_profile_id)
        if not result.success or result.asset_id is None: raise ValueError(result.message or "Asset registration failed.")
        return int(result.asset_id)

    def _asset_id(self, image_id):
        asset = self.assets.get_by_generation_image_id(str(image_id)); return int(asset.id) if asset else None

    def _context(self, bundle_id, creator_profile_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.bundle_studio_bundles WHERE bundle_id=%s AND creator_profile_id=%s", (bundle_id, int(creator_profile_id)))
            bundle = cursor.fetchone()
            if bundle is None: raise KeyError("Bundle Studio workspace not found.")
            cursor.execute("SELECT image_id,position FROM public.bundle_studio_members WHERE bundle_id=%s ORDER BY position", (bundle_id,))
            members = tuple(cursor.fetchall())
        return dict(bundle), tuple(dict(item) for item in members)

    def _offering(self, bundle):
        if bundle.get("commercial_offering_id"):
            return self.offerings.get(UUID(str(bundle["commercial_offering_id"])), creator_profile_id=int(bundle["creator_profile_id"]))
        return self.offerings.get_by_idempotency_key(creator_profile_id=int(bundle["creator_profile_id"]), idempotency_key=self._key(bundle["bundle_id"]))

    def _key(self, bundle_id): return sha256(f"{self.WORKFLOW}:{bundle_id}".encode()).hexdigest()
