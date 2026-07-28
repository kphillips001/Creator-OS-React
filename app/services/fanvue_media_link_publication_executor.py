"""Resumable official Fanvue Media Link execution for AI Chat offerings."""
from __future__ import annotations
import hashlib
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from app.models.commercial_offering import CommercialOfferingStatus, PrimarySalesChannel
from app.models.commercial_publication import CommercialPublicationProvider, CommercialPublicationStatus
from app.repositories.asset_repository import AssetRepository
from app.repositories.commercial_offering_repository import CommercialOfferingRepository
from app.repositories.commercial_publication_repository import CommercialPublicationRepository
from app.repositories.commercial_publication_upload_repository import CommercialPublicationUploadRepository
from app.services.commercial_publication_service import CommercialPublicationService
from app.services.commercial_asset_eligibility_service import CommercialAssetEligibilityService
from app.services.fanvue_official_client import FanvueOfficialClient
from app.services.fanvue_oauth_service import FanvueReauthorizationRequired

class PublicationPending(RuntimeError):
    pass

class FanvueMediaLinkPublicationExecutor:
    def __init__(self, *, publications=None, offerings=None, assets=None, uploads=None,
                 publication_service=None, client_factory=None, sleep=time.sleep):
        self.publications = publications or CommercialPublicationRepository()
        self.offerings = offerings or CommercialOfferingRepository()
        self.assets = assets or AssetRepository()
        self.uploads = uploads or CommercialPublicationUploadRepository()
        self.publication_service = publication_service or CommercialPublicationService(
            repository=self.publications, offering_repository=self.offerings)
        self.commercial_eligibility = CommercialAssetEligibilityService(
            asset_repository=self.assets, offering_repository=self.offerings
        )
        self.client_factory = client_factory or (lambda account_id: FanvueOfficialClient(account_id))
        self.sleep = sleep

    def execute(self, publication_id, *, creator_profile_id: int, fanvue_account_id: int):
        publication = self.publication_service.get_publication(
            publication_id, creator_profile_id=creator_profile_id)
        if publication is None:
            raise ValueError("Commercial Publication not found.")
        claim = self.publications.claim_execution(
            publication.publication_id, creator_profile_id=creator_profile_id)
        if claim is None:
            raise ValueError("Commercial Publication execution is already in progress.")
        try:
            return self._execute_claimed(publication, creator_profile_id, fanvue_account_id)
        finally:
            self.publications.release_execution(publication.publication_id, claim)

    def _execute_claimed(self, publication, creator_profile_id, account_id):
        offering = self.offerings.get(
            publication.commercial_offering_id, creator_profile_id=creator_profile_id)
        self._validate(publication, offering)
        self.commercial_eligibility.require_offering(
            offering, creator_profile_id=creator_profile_id
        )
        client = self.client_factory(account_id)
        client.require_media_link_scopes()
        identity = client.get_current_user()
        if publication.status != CommercialPublicationStatus.PUBLISHING:
            publication = self.publication_service.update_status(
                publication.publication_id, creator_profile_id=creator_profile_id,
                status=CommercialPublicationStatus.PUBLISHING)
        snapshot = self._snapshot(offering)
        metadata = dict(publication.publication_metadata)
        metadata.update({
            "schema_version": 1, "fanvue_account_id": account_id,
            "creator_user_uuid": identity.get("uuid") or identity.get("userUuid"),
            "publication_kind": "MEDIA_LINK", "api_version": client.API_VERSION,
            "offering_snapshot": snapshot, "composition_hash": snapshot["composition_hash"],
            "ordered_asset_ids": snapshot["asset_ids"],
            "execution": {"current_stage": "uploading", "last_attempt_at": self._now()},
        })
        self.publications.update_metadata(
            publication.publication_id, creator_profile_id=creator_profile_id, metadata=metadata)
        media_uuids = []
        try:
            for member in offering.assets:
                media_uuids.append(self._upload_asset(
                    client, publication.publication_id, member.asset_id, creator_profile_id, account_id))
            metadata["execution"]["current_stage"] = "reconciling_media_link"
            matches = client.find_equivalent_media_link(media_uuids, offering.price_minor)
            if len(matches) > 1:
                raise RuntimeError("Multiple equivalent Fanvue Media Links require reconciliation.")
            link = matches[0] if matches else client.create_media_link(media_uuids, offering.price_minor)
            metadata["media_link"] = {
                "uuid": link["uuid"], "url": link.get("url"),
                "price_minor": link["price"], "media_uuids": link["mediaUuids"],
                "created_at": link.get("createdAt"), "clicks": link.get("clicks"),
                "unlocks": link.get("unlocks"), "earnings": link.get("earnings"),
            }
            metadata["upload_summary"] = {"total": len(media_uuids), "ready": len(media_uuids)}
            metadata["execution"]["current_stage"] = "complete"
            return self.publication_service.finalize_provider_live(
                publication.publication_id, creator_profile_id=creator_profile_id,
                external_product_id=link["uuid"], delivery_url=link.get("url"),
                metadata=metadata)
        except Exception as error:
            metadata["execution"].update({"current_stage": "failed", "last_error_code": type(error).__name__})
            self.publications.update_metadata(
                publication.publication_id, creator_profile_id=creator_profile_id, metadata=metadata)
            self.publication_service.mark_failed(
                publication.publication_id, creator_profile_id=creator_profile_id, error=str(error))
            raise

    def _upload_asset(self, client, publication_id, asset_id, creator_profile_id, account_id):
        asset = self.assets.get_by_id(asset_id)
        if asset is None or int(asset.creator_profile_id or 0) != int(creator_profile_id):
            raise ValueError(f"Offering Asset is unavailable: {asset_id}.")
        if asset.media_type not in {"image", "video"}:
            raise ValueError(f"Unsupported Fanvue media type: {asset.media_type}.")
        path = Path(asset.local_vault_path or asset.file_path)
        if not path.is_file():
            raise ValueError(f"Offering Asset file is missing: {asset_id}.")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        size = path.stat().st_size
        checkpoint = self.uploads.get(publication_id, asset_id)
        if checkpoint and (checkpoint.content_hash != digest.hexdigest() or checkpoint.file_size_bytes != size):
            raise ValueError(f"Offering Asset changed after upload checkpoint: {asset_id}.")
        checkpoint = checkpoint or self.uploads.initialize(
            publication_id=publication_id, asset_id=asset_id, fanvue_account_id=account_id,
            media_type=asset.media_type, content_hash=digest.hexdigest(), file_size_bytes=size)
        if checkpoint.processing_status == "ready":
            return checkpoint.provider_media_uuid
        if not checkpoint.provider_media_uuid:
            session = client.create_upload_session(
                name=path.name, filename=path.name, media_type=asset.media_type, size_bytes=size)
            checkpoint = self.uploads.save_session(
                checkpoint.publication_upload_id, media_uuid=session["mediaUuid"],
                upload_id=session["uploadId"], part_size=session["partSize"],
                total_parts=session.get("totalParts") or ((size + session["partSize"] - 1)//session["partSize"]))
        if checkpoint.upload_status != "uploaded":
            parts = dict(checkpoint.uploaded_parts)
            with path.open("rb") as source:
                for number in range(1, int(checkpoint.total_parts) + 1):
                    chunk = source.read(int(checkpoint.part_size_bytes))
                    if str(number) in parts:
                        continue
                    url = client.get_upload_part_url(checkpoint.provider_upload_id, number)
                    etag = client.put_part(url, chunk)
                    self.uploads.save_part(checkpoint.publication_upload_id, part_number=number, etag=etag)
                    parts[str(number)] = etag
            completion = [{"PartNumber": number, "ETag": parts[str(number)]}
                          for number in range(1, int(checkpoint.total_parts)+1)]
            result = client.complete_upload(checkpoint.provider_upload_id, completion)
            self.uploads.mark_uploaded(checkpoint.publication_upload_id, result.get("status", "processing"))
        delays = (1, 2, 4, 8)
        for delay in delays:
            media = client.get_media(checkpoint.provider_media_uuid)
            status = str(media.get("status") or "").lower()
            if status == "ready":
                self.uploads.mark_processing(checkpoint.publication_upload_id, "ready")
                return checkpoint.provider_media_uuid
            if status == "error":
                self.uploads.mark_processing(checkpoint.publication_upload_id, "error", "Fanvue media processing failed.")
                raise RuntimeError("Fanvue media processing failed.")
            self.uploads.mark_processing(checkpoint.publication_upload_id, "processing")
            self.sleep(delay + random.random())
        raise PublicationPending("Fanvue media is still processing; retry will resume polling.")

    @staticmethod
    def _validate(publication, offering):
        if publication.provider != CommercialPublicationProvider.FANVUE:
            raise ValueError("Only FANVUE publications are supported.")
        if publication.status not in {CommercialPublicationStatus.READY_TO_PUBLISH,
                                      CommercialPublicationStatus.FAILED,
                                      CommercialPublicationStatus.PUBLISHING}:
            raise ValueError("Commercial Publication is not executable.")
        if offering is None or offering.status == CommercialOfferingStatus.ARCHIVED:
            raise ValueError("Commercial Offering is unavailable or archived.")
        if offering.primary_sales_channel != PrimarySalesChannel.AI_CHAT:
            raise ValueError("Fanvue Media Links are only available for AI_CHAT offerings.")
        if offering.offering_type.value in {"STORY", "STORY_SET", "BUNDLE"}:
            raise ValueError("This offering type is not supported by Fanvue Media Link execution.")
        if offering.price_minor is None or not 300 <= offering.price_minor <= 50000:
            raise ValueError("A valid price is required before publication.")
        if not offering.assets:
            raise ValueError("Commercial Offering has no assets.")

    @staticmethod
    def _snapshot(offering):
        asset_ids = [member.asset_id for member in offering.assets]
        raw = json.dumps({"offering_id": str(offering.offering_id), "asset_ids": asset_ids,
                          "price_minor": offering.price_minor}, separators=(",", ":"), sort_keys=True)
        return {"offering_id": str(offering.offering_id), "title": offering.title,
                "offering_type": offering.offering_type.value,
                "primary_sales_channel": offering.primary_sales_channel.value,
                "price_minor": offering.price_minor, "currency": offering.currency,
                "asset_ids": asset_ids, "hero_asset_id": offering.hero_asset_id,
                "composition_hash": hashlib.sha256(raw.encode()).hexdigest()}

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()
