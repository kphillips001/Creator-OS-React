"""Resumable official Fanvue Media Link execution for AI Chat offerings."""
from __future__ import annotations
import hashlib
import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from requests.exceptions import Timeout as RequestsTimeout

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

logger = logging.getLogger(__name__)

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
        except Exception as error:
            # Validation, eligibility, provider setup, and upload execution are
            # all terminal attempts once a publication claim has been acquired.
            # Never strand an executable publication in PUBLISHING merely
            # because failure occurred before the inner upload boundary.
            try:
                current = self.publication_service.get_publication(
                    publication.publication_id, creator_profile_id=creator_profile_id,
                )
                if current and current.status != CommercialPublicationStatus.FAILED:
                    self.publication_service.mark_failed(
                        publication.publication_id,
                        creator_profile_id=creator_profile_id,
                        error=str(error),
                    )
            except Exception:
                logger.exception(
                    "Failed to persist terminal Fanvue publication error for %s",
                    publication.publication_id,
                )
            raise
        finally:
            self.publications.release_execution(publication.publication_id, claim)

    def replace_live_media_link(self, publication_id, *, creator_profile_id: int,
                                fanvue_account_id: int):
        """Replace one claimed LIVE media link without re-uploading offering media."""
        publication = self.publication_service.get_publication(
            publication_id, creator_profile_id=creator_profile_id)
        if publication is None:
            raise ValueError("Commercial Publication not found.")
        claim = self.publications.claim_execution(
            publication.publication_id, creator_profile_id=creator_profile_id)
        if claim is None:
            raise ValueError("Commercial Publication execution is already in progress.")
        try:
            return self._replace_claimed(
                publication, creator_profile_id, fanvue_account_id)
        except Exception as error:
            current = self.publication_service.get_publication(
                publication.publication_id, creator_profile_id=creator_profile_id)
            current_metadata = dict(current.publication_metadata if current else {})
            replacement = dict(current_metadata.get("media_link_replacement") or {})
            if (current and current.status == CommercialPublicationStatus.LIVE
                    and replacement.get("state") not in {
                        "OLD_LINK_DELETED", "REPLACEMENT_FAILED",
                    }):
                replacement.update({
                    "state": "PREFLIGHT_FAILED", "last_error": str(error),
                    "last_attempt_at": self._now(),
                })
                current_metadata["media_link_replacement"] = replacement
                self.publications.update_metadata(
                    current.publication_id, creator_profile_id=creator_profile_id,
                    metadata=current_metadata)
            raise
        finally:
            self.publications.release_execution(publication.publication_id, claim)

    def _replace_claimed(self, publication, creator_profile_id, account_id):
        offering = self.offerings.get(
            publication.commercial_offering_id, creator_profile_id=creator_profile_id)
        metadata = dict(publication.publication_metadata)
        replacement = dict(metadata.get("media_link_replacement") or {})
        target_price = int(replacement.get("target_price_minor") or 0)
        if not 300 <= target_price <= 50000:
            raise ValueError("A valid replacement price is required.")
        if offering is None or not offering.assets:
            raise ValueError("Commercial Offering is unavailable.")
        expected_assets = [member.asset_id for member in offering.assets]
        if replacement.get("asset_ids") != expected_assets:
            raise ValueError("Bundle membership changed during Media Link replacement.")
        client = self.client_factory(account_id)
        client.require_media_link_scopes()
        client.get_current_user()
        old_link = dict(metadata.get("media_link") or {})
        old_uuid = str(replacement.get("old_uuid") or publication.external_product_id or "").strip()
        deleted = replacement.get("state") in {"OLD_LINK_DELETED", "REPLACEMENT_FAILED"}
        if not deleted:
            matches = [item for item in client.list_media_links().get("data", [])
                       if str(item.get("uuid") or "") == old_uuid]
            if not matches and replacement.get("state") == "DELETING_OLD_LINK":
                # Recovery after an ambiguous/crashed DELETE: absence at the
                # provider proves the old resource is already gone.
                deleted = True
            elif len(matches) != 1:
                raise ValueError("The existing canonical Fanvue Media Link could not be verified.")
            if not deleted:
                provider_link = matches[0]
                if (tuple(sorted(provider_link.get("mediaUuids") or ()))
                        != tuple(sorted(old_link.get("media_uuids") or old_link.get("mediaUuids") or ()))
                        or int(provider_link.get("price", -1)) != int(offering.price_minor)):
                    raise ValueError("The existing Fanvue Media Link does not match canonical Bundle state.")
                replacement.update({"state": "DELETING_OLD_LINK", "last_attempt_at": self._now()})
                metadata["media_link_replacement"] = replacement
                self.publications.update_metadata(
                    publication.publication_id, creator_profile_id=creator_profile_id, metadata=metadata)
                client.delete_media_link(old_uuid)
            replacement["state"] = "OLD_LINK_DELETED"
            metadata["media_link_replacement"] = replacement
            metadata.pop("media_link", None)
            publication = self.publications.mark_media_link_replacement_deleted(
                publication.publication_id, creator_profile_id=creator_profile_id,
                metadata=metadata)
        try:
            media_uuids = [self._upload_asset(
                client, publication.publication_id, member.asset_id,
                creator_profile_id, account_id) for member in offering.assets]
            matches = client.find_equivalent_media_link(media_uuids, target_price)
            if len(matches) > 1:
                raise RuntimeError("Multiple equivalent Fanvue Media Links require reconciliation.")
            link = matches[0] if matches else client.create_media_link(media_uuids, target_price)
            metadata["media_link"] = {
                "uuid": link["uuid"], "url": link.get("url"),
                "price_minor": link["price"], "media_uuids": link["mediaUuids"],
                "created_at": link.get("createdAt"), "clicks": link.get("clicks"),
                "unlocks": link.get("unlocks"), "earnings": link.get("earnings"),
            }
            snapshot = dict(self._snapshot(offering))
            snapshot["price_minor"] = target_price
            snapshot_raw = json.dumps({
                "offering_id": str(offering.offering_id),
                "asset_ids": snapshot["asset_ids"],
                "price_minor": target_price,
            }, separators=(",", ":"), sort_keys=True)
            snapshot["composition_hash"] = hashlib.sha256(snapshot_raw.encode()).hexdigest()
            metadata.update({
                "price_minor": target_price, "currency": offering.currency,
                "offering_snapshot": snapshot,
                "composition_hash": snapshot["composition_hash"],
                "ordered_asset_ids": snapshot["asset_ids"],
            })
            metadata["media_link_replacement"] = {
                **replacement, "state": "COMPLETE", "completed_at": self._now(),
                "new_uuid": link["uuid"],
            }
            return self.publications.finalize_media_link_replacement(
                publication.publication_id, creator_profile_id=creator_profile_id,
                price_minor=target_price, currency=offering.currency,
                external_product_id=link["uuid"], metadata=metadata)
        except Exception as error:
            replacement.update({
                "state": "REPLACEMENT_FAILED", "last_error": str(error),
                "last_attempt_at": self._now(),
            })
            metadata["media_link_replacement"] = replacement
            metadata.pop("media_link", None)
            self.publications.mark_media_link_replacement_deleted(
                publication.publication_id, creator_profile_id=creator_profile_id,
                metadata=metadata, error=(
                    "The old Fanvue Media Link was deleted, but replacement creation failed. "
                    f"Retry the price update. {error}"
                ),
            )
            raise

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
        content_hash = digest.hexdigest()
        checkpoint = self.uploads.get(publication_id, asset_id)
        if checkpoint and (checkpoint.content_hash != content_hash or checkpoint.file_size_bytes != size):
            raise ValueError(f"Offering Asset changed after upload checkpoint: {asset_id}.")
        if checkpoint is None:
            find_reusable = getattr(self.uploads, "find_ready_reusable", None)
            reusable = find_reusable(
                asset_id=asset_id, fanvue_account_id=account_id,
                content_hash=content_hash, file_size_bytes=size,
            ) if callable(find_reusable) else None
            reusable_status = ""
            if reusable is not None:
                try:
                    provider_media = client.get_media(reusable.provider_media_uuid)
                    reusable_status = str(provider_media.get("status") or "").lower()
                except Exception:
                    # A stale/missing provider resource is not reusable; start a
                    # fresh upload checkpoint for this publication instead.
                    reusable_status = ""
            if reusable is not None and reusable_status == "ready":
                checkpoint = self.uploads.initialize_reused(
                    publication_id=publication_id, asset_id=asset_id,
                    fanvue_account_id=account_id, media_type=asset.media_type,
                    content_hash=content_hash, file_size_bytes=size,
                    provider_media_uuid=reusable.provider_media_uuid,
                )
        checkpoint = checkpoint or self.uploads.initialize(
            publication_id=publication_id, asset_id=asset_id, fanvue_account_id=account_id,
            media_type=asset.media_type, content_hash=content_hash, file_size_bytes=size)
        resume_completed_parts = bool(
            checkpoint.provider_media_uuid and checkpoint.total_parts
            and len(checkpoint.uploaded_parts) == int(checkpoint.total_parts)
        )
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
            provider_status = ""
            if resume_completed_parts:
                media = client.get_media(checkpoint.provider_media_uuid)
                provider_status = str(media.get("status") or "").lower()
            if provider_status not in {"processing", "ready"}:
                try:
                    result = client.complete_upload(checkpoint.provider_upload_id, completion)
                    provider_status = str(result.get("status") or "processing").lower()
                except RequestsTimeout:
                    # Completion is an ambiguous write: reconcile the persisted media UUID
                    # before allowing a later operator retry to submit it again.
                    media = client.get_media(checkpoint.provider_media_uuid)
                    provider_status = str(media.get("status") or "").lower()
                    if provider_status not in {"processing", "ready"}:
                        raise
            self.uploads.mark_uploaded(
                checkpoint.publication_upload_id,
                provider_status if provider_status in {"processing", "ready"} else "processing",
            )
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
        if offering.primary_sales_channel not in {
            PrimarySalesChannel.AI_CHAT,
            PrimarySalesChannel.TELEGRAM_WALL,
        }:
            raise ValueError("Fanvue Media Links are unavailable for this sales channel.")
        if offering.offering_type.value in {"STORY", "STORY_SET"}:
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
