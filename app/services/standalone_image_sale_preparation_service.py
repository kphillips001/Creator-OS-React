"""Thin, idempotent commercial preparation for one canonical image Asset."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from app.models.asset_intelligence import AssetIntelligenceStatus
from app.models.commercial_offering import (
    CommercialOfferingStatus,
    CommercialOfferingType,
    PrimarySalesChannel,
)
from app.models.commercial_publication import (
    CommercialPublicationProvider,
    CommercialPublicationStatus,
    ProviderResourceStatus,
)
from app.repositories.asset_intelligence_repository import AssetIntelligenceRepository
from app.repositories.asset_repository import AssetRepository
from app.repositories.commercial_offering_repository import CommercialOfferingRepository
from app.repositories.commercial_publication_upload_repository import CommercialPublicationUploadRepository
from app.services.commercial_offering_service import CommercialOfferingService
from app.services.commercial_publication_service import CommercialPublicationService
from app.services.fanvue_media_link_publication_executor import FanvueMediaLinkPublicationExecutor
from app.services.media_processing_service import MediaProcessingService
from app.services.commercial_teaser_service import CommercialTeaserService
from app.services.media_title_service import is_internal_fallback_title, safe_image_title


class StandaloneImageSalePreparationService:
    SOURCE_WORKFLOW = "standalone_image_sale_preparation"

    def __init__(self, *, assets=None, intelligence=None, offerings=None,
                 offering_service=None, publications=None, uploads=None,
                 media=None, executor=None, teasers=None):
        self.assets = assets or AssetRepository()
        self.intelligence = intelligence or AssetIntelligenceRepository()
        self.offering_repository = offerings or CommercialOfferingRepository()
        self.offering_service = offering_service or CommercialOfferingService(
            repository=self.offering_repository, asset_repository=self.assets)
        self.publication_service = publications or CommercialPublicationService(
            offering_repository=self.offering_repository)
        self.uploads = uploads or CommercialPublicationUploadRepository()
        self.media = media or MediaProcessingService()
        self.teasers = teasers or CommercialTeaserService(assets=self.assets, media=self.media)
        self.executor = executor or FanvueMediaLinkPublicationExecutor(
            assets=self.assets, offerings=self.offering_repository,
            uploads=self.uploads, publication_service=self.publication_service)

    @staticmethod
    def idempotency_key(asset_id: int) -> str:
        return sha256(f"standalone-image:{int(asset_id)}".encode()).hexdigest()

    def inspect(self, asset_id: int, *, creator_profile_id: int) -> dict:
        asset = self._asset(asset_id, creator_profile_id)
        profile = self.intelligence.get_profile(asset_id)
        offering = self.offering_repository.get_by_idempotency_key(
            creator_profile_id=creator_profile_id,
            idempotency_key=self.idempotency_key(asset_id),
        )
        publication = None
        checkpoint = None
        if offering is not None:
            publications = self.publication_service.list_publications(
                creator_profile_id=creator_profile_id,
                commercial_offering_id=offering.offering_id)
            publication = next((item for item in publications
                                if item.provider == CommercialPublicationProvider.FANVUE), None)
            if publication is not None:
                checkpoint = self.uploads.get(publication.publication_id, asset_id)
        teaser_rows = self.teasers.list(asset_id)
        teaser_by_use = {row["distribution_use"]: row for row in teaser_rows}
        configuration = dict((asset.media_metadata or {}).get("standalone_sale_preparation") or {})
        explicit_destinations = list(configuration.get("destinations") or [])
        metadata = publication.publication_metadata if publication else {}
        caption_draft = metadata.get("content_vault_caption_draft") if isinstance(metadata, dict) else None
        media_link = metadata.get("media_link") if isinstance(metadata, dict) else {}
        url = media_link.get("url") if isinstance(media_link, dict) else None
        intelligence_ready = bool(profile and profile.analysis_status == AssetIntelligenceStatus.READY)
        foundation_ready = bool(
            intelligence_ready
            and offering and offering.status == CommercialOfferingStatus.READY
            and checkpoint and checkpoint.upload_status == "uploaded"
            and checkpoint.processing_status == "ready"
            and publication and publication.status == CommercialPublicationStatus.LIVE
            and publication.provider_resource_status == ProviderResourceStatus.PRESENT
            and str(url or "").startswith(("http://", "https://"))
        )
        primary_channel = getattr(
            getattr(offering, "primary_sales_channel", None), "value",
            getattr(offering, "primary_sales_channel", None),
        )
        legacy_chat = bool(
            not explicit_destinations and foundation_ready and offering
            and offering.offering_type == CommercialOfferingType.SINGLE_IMAGE
            and primary_channel == PrimarySalesChannel.AI_CHAT.value
        )
        destinations = explicit_destinations or (["CHAT"] if legacy_chat else [])
        selected_use = destinations[0] if len(destinations) == 1 else None
        selected_teaser = teaser_by_use.get(selected_use) if selected_use else None
        teaser_style = (configuration.get("teaser_style")
                        or (selected_teaser or {}).get("teaser_style"))
        failed = bool(
            (publication and publication.status == CommercialPublicationStatus.FAILED)
            or (checkpoint and (checkpoint.upload_status == "failed"
                                or checkpoint.processing_status == "error"))
            or dict((asset.media_metadata or {}).get("standalone_sale_preparation") or {}).get("last_error")
        )
        chat_teaser_ready = self._teaser_ready(teaser_by_use.get("CHAT"))
        vault_teaser_ready = self._teaser_ready(teaser_by_use.get("CONTENT_VAULT"))
        chat_ready = foundation_ready and chat_teaser_ready
        vault_ready = foundation_ready and vault_teaser_ready
        legacy_blur = self.media.resolve_derivative(asset, "blurred_preview")
        legacy_ready = bool(legacy_chat and legacy_blur and Path(legacy_blur).is_file())
        ready = legacy_ready or bool(explicit_destinations and all(chat_ready if value == "CHAT" else vault_ready for value in explicit_destinations))
        started = bool(teaser_rows or offering or publication)
        partial = bool(explicit_destinations and foundation_ready and not ready)
        status = "READY" if ready else "NEEDS_ATTENTION" if failed or partial else "PREPARING" if started else "NOT_PREPARED"
        local_error = configuration.get("last_error")
        error = (publication.last_error if publication else None) or (checkpoint.last_error if checkpoint else None) or local_error
        return {
            "assetId": asset_id, "status": status,
            "statusLabel": {"NOT_PREPARED": "Prepare for Sale", "PREPARING": "Preparing...",
                            "READY": "Ready", "NEEDS_ATTENTION": "Needs Attention"}[status],
            "intelligenceReady": intelligence_ready,
            "blurredTeaserReady": vault_teaser_ready,
            "destinations": destinations,
            "teaserStyle": teaser_style,
            "foundationReady": foundation_ready,
            "chatReady": chat_ready, "vaultReady": vault_ready,
            "teasers": [self._teaser_payload(row) for row in teaser_rows],
            "priceMinor": int(offering.price_minor) if offering and getattr(offering, "price_minor", None) is not None else None,
            "currency": str(getattr(offering, "currency", None) or "USD") if offering else None,
            "offeringId": str(offering.offering_id) if offering else None,
            "publicationId": str(publication.publication_id) if publication else None,
            "deliveryUrl": url, "error": error,
            "contentVaultCaption": dict(caption_draft) if isinstance(caption_draft, dict) else None,
        }

    def stage(self, asset_id: int, *, creator_profile_id: int, price_minor: int,
              destinations=None, teaser_style=None):
        asset = self._asset(asset_id, creator_profile_id)
        try:
            return self._stage(asset, creator_profile_id=creator_profile_id,
                               price_minor=price_minor, destinations=destinations,
                               teaser_style=teaser_style)
        except Exception as error:
            current = self.assets.get_by_id(int(asset_id)) or asset
            metadata = dict(current.media_metadata or {})
            metadata["standalone_sale_preparation"] = {
                **dict(metadata.get("standalone_sale_preparation") or {}),
                "last_error": str(error),
            }
            self.assets.update_media_metadata(asset_id, metadata)
            raise

    def reassign_destination(self, asset_id: int, *, creator_profile_id: int,
                             price_minor: int, destination: str,
                             teaser_style: str | None = None):
        """Re-run canonical preparation while changing only a standalone sale destination."""
        asset = self._asset(asset_id, creator_profile_id)
        if str(getattr(asset, "classification", None) or "") != "SINGLE_IMAGE":
            raise ValueError("Sales destination reassignment supports standalone Single Images only.")
        metadata = dict(asset.media_metadata or {})
        prior = dict(metadata.get("standalone_sale_preparation") or {})
        current = list(prior.get("destinations") or [])
        requested = str(destination)
        if requested not in {"CHAT", "CONTENT_VAULT"}:
            raise ValueError("Select Chat or TG Wall as the sales destination.")
        if len(current) != 1 or current[0] not in {"CHAT", "CONTENT_VAULT"}:
            raise ValueError("Prepare this Single Image for sale before reassigning its destination.")
        if current[0] == requested:
            raise ValueError("Choose a different sales destination.")
        try:
            return self._stage(
                asset, creator_profile_id=creator_profile_id,
                price_minor=price_minor, destinations=[requested],
                teaser_style=teaser_style,
            )
        except Exception:
            # _stage owns the canonical transition. Restore its destination metadata if
            # a later preparation operation fails, so projections never expose a move
            # that did not complete.
            refreshed = self.assets.get_by_id(asset.id) or asset
            restored = dict(refreshed.media_metadata or {})
            restored["standalone_sale_preparation"] = prior
            self.assets.update_media_metadata(asset.id, restored)
            raise

    def _stage(self, asset, *, creator_profile_id: int, price_minor: int,
               destinations=None, teaser_style=None):
        profile = self.intelligence.get_profile(asset.id)
        if profile is None or profile.analysis_status != AssetIntelligenceStatus.READY:
            raise ValueError("Asset Intelligence must be READY before sale preparation can continue.")
        price = int(price_minor)
        if not 300 <= price <= 50000:
            raise ValueError("Price must be between $3.00 and $500.00.")
        if destinations is None:  # Compatibility for callers predating destination-aware preparation.
            blur = self.media.resolve_derivative(asset, "blurred_preview")
        else:
            selected = tuple(str(value) for value in destinations)
            if len(selected) != 1 or selected[0] not in {"CHAT", "CONTENT_VAULT"}:
                raise ValueError("Select exactly one selling mode: Chat Selling or Ava's Content Vault.")
            destination = selected[0]
            selected_style = str(teaser_style or ("SELECTIVE_BLUR" if destination == "CHAT" else "FULL_BLUR"))
            if destination == "CHAT" and selected_style != "SELECTIVE_BLUR":
                raise ValueError("Chat Selling requires a selective teaser.")
            if destination == "CHAT" and not self._teaser_ready(self.teasers.repository.get(asset.id, "CHAT")):
                raise ValueError("Save and accept a selective Chat teaser before preparing for sale.")
            if destination == "CONTENT_VAULT" and selected_style not in {"FULL_BLUR", "SELECTIVE_BLUR"}:
                raise ValueError("Ava's Content Vault requires Full Blur or Selective Blur.")
            if destination == "CONTENT_VAULT" and selected_style == "FULL_BLUR":
                self.teasers.ensure_vault(asset.id, creator_profile_id=creator_profile_id)
            if (destination == "CONTENT_VAULT" and selected_style == "SELECTIVE_BLUR"
                    and not self._teaser_ready_style(
                        self.teasers.repository.get(asset.id, "CONTENT_VAULT"), "SELECTIVE_BLUR")):
                raise ValueError("Save and accept a selective Content Vault teaser before preparing for sale.")
            refreshed = self.assets.get_by_id(asset.id) or asset
            metadata = dict(refreshed.media_metadata or {})
            prior = dict(metadata.get("standalone_sale_preparation") or {})
            metadata["standalone_sale_preparation"] = {
                **prior, "destinations": list(selected),
                "teaser_style": selected_style, "last_error": None,
            }
            self.assets.update_media_metadata(asset.id, metadata)
            blur = True
        if destinations is None and not blur:
            blur = self.media.generate_blurred_preview(asset)
            derivative = self.media.build_derivative_metadata(
                derivative_path=blur, derivative_type="blurred_preview",
                source=self.SOURCE_WORKFLOW)
            merged = self.media.merge_derivative_metadata(
                asset.media_metadata, derivative_type="blurred_preview",
                derivative_metadata=derivative)
            self.assets.update_blurred_preview(asset.id, path=str(blur), media_metadata=merged)
        title = safe_image_title(
            asset_id=asset.id, canonical_title=profile.title,
            file_name=asset.file_name,
        )
        description = str(profile.short_description or profile.content_summary or "").strip() or None
        offering = self.offering_service.create(
            creator_profile_id=creator_profile_id,
            offering_type=CommercialOfferingType.SINGLE_IMAGE,
            title=title, description=description, hero_asset_id=asset.id,
            primary_sales_channel=PrimarySalesChannel.AI_CHAT,
            asset_ids=(asset.id,), price_minor=price, currency="USD",
            initial_status=CommercialOfferingStatus.READY,
            idempotency_key=self.idempotency_key(asset.id),
        )
        publications = self.publication_service.list_publications(
            creator_profile_id=creator_profile_id,
            commercial_offering_id=offering.offering_id)
        publication = next((item for item in publications
                            if item.provider == CommercialPublicationProvider.FANVUE), None)
        if publication is None:
            publication = self.publication_service.create_publication(
                creator_profile_id=creator_profile_id,
                commercial_offering_id=offering.offering_id,
                provider=CommercialPublicationProvider.FANVUE,
                publication_metadata={"source_workflow": self.SOURCE_WORKFLOW,
                                      "asset_id": asset.id},
            )
        elif publication.status == CommercialPublicationStatus.FAILED:
            # A newly accepted retry supersedes the active failure state. Keep
            # retry_count as durable history, but clear last_error and expose a
            # queued/preparing lifecycle while the canonical executor resumes.
            publication = self.publication_service.update_status(
                publication.publication_id,
                creator_profile_id=creator_profile_id,
                status=CommercialPublicationStatus.READY_TO_PUBLISH,
            )
        self._repair_commercial_title(
            asset=asset, profile=profile, offering=offering,
            publications=(publication,),
        )
        return publication

    def repair_commercial_title(self, asset_id: int, *, creator_profile_id: int) -> bool:
        asset = self._asset(asset_id, creator_profile_id)
        profile = self.intelligence.get_profile(asset_id)
        if profile is None or not str(profile.title or "").strip():
            return False
        offering = self.offering_repository.get_by_idempotency_key(
            creator_profile_id=creator_profile_id,
            idempotency_key=self.idempotency_key(asset_id),
        )
        if offering is None:
            return False
        publications = self.publication_service.list_publications(
            creator_profile_id=creator_profile_id,
            commercial_offering_id=offering.offering_id,
        )
        return self._repair_commercial_title(
            asset=asset, profile=profile, offering=offering,
            publications=publications,
        )

    def _repair_commercial_title(self, *, asset, profile, offering, publications) -> bool:
        canonical_title = str(profile.title or "").strip()
        if not canonical_title or not is_internal_fallback_title(getattr(offering, "title", None)):
            return False
        old_title = str(getattr(offering, "title", None) or "").strip()
        updated = self.offering_repository.update_metadata(
            offering.offering_id, creator_profile_id=asset.creator_profile_id,
            title=canonical_title, description=offering.description,
            hero_asset_id=offering.hero_asset_id,
        )
        if updated is None:
            return False
        for publication in publications:
            metadata = dict(publication.publication_metadata or {})
            snapshot = dict(metadata.get("offering_snapshot") or {})
            snapshot_title = str(snapshot.get("title") or "").strip()
            if snapshot and (snapshot_title == old_title or is_internal_fallback_title(snapshot_title)):
                metadata["offering_snapshot"] = {**snapshot, "title": canonical_title}
                self.publication_service.repository.update_metadata(
                    publication.publication_id,
                    creator_profile_id=asset.creator_profile_id,
                    metadata=metadata,
                )
        return True

    @staticmethod
    def _teaser_ready(row):
        return bool(row and row.get("status") == "READY" and Path(str(row.get("derivative_path") or "")).is_file())

    @classmethod
    def _teaser_ready_style(cls, row, style):
        return cls._teaser_ready(row) and row.get("teaser_style") == style

    @staticmethod
    def _teaser_payload(row):
        use = row["distribution_use"]
        return {"id": str(row["teaser_id"]), "distributionUse": use,
                "teaserStyle": row["teaser_style"], "status": row["status"],
                "derivedAssetId": row.get("derived_asset_id"),
                "previewUrl": (f'/api/v1/assets/{row["derived_asset_id"]}/media'
                               if row.get("derived_asset_id") else
                               f'/api/v1/assets/{row["source_asset_id"]}/commercial-teasers/{use.lower()}/media'),
                "maskUrl": (f'/api/v1/assets/{row["source_asset_id"]}/commercial-teasers/{use.lower()}/mask'
                            if row.get("mask_path") else None),
                "maskWidth": row.get("mask_width"), "maskHeight": row.get("mask_height"),
                "maskVersion": row.get("mask_version"), "blurStrength": row.get("blur_strength")}

    def execute(self, publication_id, *, creator_profile_id: int,
                fanvue_account_id: int):
        return self.executor.execute(
            publication_id, creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id)

    def _asset(self, asset_id: int, creator_profile_id: int):
        asset = self.assets.get_by_id(int(asset_id))
        if asset is None or int(asset.creator_profile_id or 0) != int(creator_profile_id):
            raise KeyError("Canonical Asset not found.")
        if asset.media_type != "image":
            raise ValueError("Prepare for Sale supports canonical image Assets only.")
        reference_metadata = dict((asset.media_metadata or {}).get("reference_library") or {})
        if bool(reference_metadata.get("is_reference")):
            raise ValueError("Reference Assets cannot be prepared for sale.")
        return asset
