"""Commerce-authoritative publishing to Ava's Telegram Content Vault."""

from __future__ import annotations

from html import escape
from pathlib import Path
from threading import Lock
from uuid import UUID

from app.models.commercial_offering import CommercialOfferingStatus
from app.models.commercial_publication import (
    CommercialPublicationProvider,
    CommercialPublicationStatus,
    ProviderResourceStatus,
)
from app.models.social_publishing import SocialPublishStatus
from app.repositories.asset_repository import AssetRepository
from app.services.commercial_offering_service import CommercialOfferingService
from app.services.commercial_publication_service import CommercialPublicationService
from app.services.social_publishing_service import SocialPublishingService
from app.repositories.commercial_teaser_repository import CommercialTeaserRepository


class CommerceTelegramVaultError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CommerceTelegramVaultService:
    """Validates Commerce state and delegates delivery to Social Publishing."""

    _claims_guard = Lock()
    _claims: set[str] = set()
    TELEGRAM_PHOTO_CAPTION_LIMIT = 1024

    def __init__(
        self,
        *,
        offerings=None,
        publications=None,
        assets=None,
        social=None,
        teasers=None,
        bundle_preparation=None,
    ) -> None:
        self.offerings = offerings or CommercialOfferingService()
        self.publications = publications or CommercialPublicationService(
            offering_repository=self.offerings.repository
        )
        self.assets = assets or AssetRepository()
        self.social = social or SocialPublishingService()
        self.teasers = teasers or CommercialTeaserRepository()
        self.bundle_preparation = bundle_preparation

    def publish(
        self,
        offering_id,
        *,
        creator_profile_id: int,
        marketing_text: str | None = None,
    ):
        offering = self._offering(offering_id, creator_profile_id)
        claim = str(offering.offering_id)
        if not self._acquire_claim(claim):
            raise CommerceTelegramVaultError("PUBLISH_IN_PROGRESS", "This offering is already publishing.")
        try:
            self._validate_offering(offering)
            self._validate_telegram()
            source_id = f"commercial-offering:{offering.offering_id}"
            existing = self.social.find_queue_item(source_id, platform="telegram")
            if existing and existing.status == SocialPublishStatus.POSTED.value:
                raise CommerceTelegramVaultError(
                    "ALREADY_PUBLISHED", "Commercial Offering is already published to Telegram Content Vault.")
            if existing and existing.status in {
                SocialPublishStatus.QUEUED.value, SocialPublishStatus.SCHEDULED.value,
            }:
                raise CommerceTelegramVaultError("PUBLISH_IN_PROGRESS", "This offering is already publishing.")

            if self._offering_type(offering) in {"SINGLE_IMAGE", "BUNDLE"}:
                package = self._content_vault_package(offering, creator_profile_id)
                # Telegram's canonical provider uses HTML parse mode. Escape only
                # at the transport boundary so the customer sees the persisted
                # caption verbatim while the audit snapshot retains its exact text.
                caption = escape(package["caption"])
                preview = package["teaser_path"]
                delivery_url = package["delivery_url"]
                cta_label = f"🔓 Unlock · {self._money(package['price_minor'], package['currency'])}"
                audit = {key: value for key, value in package.items()
                         if key not in {"teaser_path", "delivery_url"}}
            else:
                delivery_url = self._delivery_url(offering, creator_profile_id)
                preview = self._preview(offering, creator_profile_id)
                caption = self._caption(offering.title, offering.description, marketing_text)
                cta_label = "Unlock Now"
                audit = {"offering_id": str(offering.offering_id),
                         "asset_id": int(offering.hero_asset_id),
                         "telegram_destination": "vault"}

            item = self.social.create_commerce_queue_item(
                commercial_offering_id=str(offering.offering_id), creator_profile_id=creator_profile_id,
                hero_asset_id=offering.hero_asset_id, image_reference=preview, title=offering.title)
            result = self.social.publish_now(
                item.queue_item_id, caption_text=caption, telegram_post_to="vault",
                telegram_cta_enabled=True, telegram_cta_label=cta_label,
                telegram_cta_url=delivery_url, audit_metadata=audit)
            if result.status == SocialPublishStatus.FAILED.value:
                history = [entry for entry in self.social.list_history()
                           if entry.queue_item_id == item.queue_item_id]
                message = history[0].message if history else "Telegram publishing failed."
                raise CommerceTelegramVaultError(
                    "TELEGRAM_PUBLISH_FAILED", message or "Telegram publishing failed.")
            return result
        finally:
            self._release_claim(claim)

    def status(self, offering_id, *, creator_profile_id: int) -> dict:
        offering = self.offerings.get(
            UUID(str(offering_id)), creator_profile_id=creator_profile_id
        )
        if offering is None:
            return {"status": None, "publishedAt": None, "lastError": None,
                    "providerMessageId": None, "canPublish": False, "configured": False}
        configured = self._telegram_configured()
        readiness_error = None
        ready = configured
        if self._offering_type(offering) in {"SINGLE_IMAGE", "BUNDLE"}:
            try:
                self._validate_offering(offering)
                self._content_vault_package(offering, creator_profile_id)
            except CommerceTelegramVaultError as error:
                ready, readiness_error = False, str(error)
        source_id = f"commercial-offering:{offering.offering_id}"
        item = self.social.find_queue_item(source_id, platform="telegram")
        if item is None:
            return {"status": "NOT_PUBLISHED", "publishedAt": None, "lastError": None,
                    "providerMessageId": None, "canPublish": ready,
                    "configured": configured, "readinessError": readiness_error}
        history = [
            entry for entry in self.social.list_history()
            if entry.queue_item_id == item.queue_item_id
        ]
        failed = next(
            (entry.message for entry in history if entry.status == "failed"), None
        )
        posted = next((entry for entry in history if entry.status == "posted"), None)
        return {
            "status": {
                "queued": "PUBLISHING",
                "scheduled": "PUBLISHING",
                "posted": "PUBLISHED",
                "failed": "FAILED",
                "archived": "ARCHIVED",
            }.get(item.status, item.status.upper()),
            "publishedAt": item.updated_at if item.status == "posted" else None,
            "lastError": failed if item.status == "failed" else None,
            "providerMessageId": ((posted.metadata or {}).get("provider_post_id") if posted else None),
            "canPublish": ready and item.status == SocialPublishStatus.FAILED.value,
            "configured": configured, "readinessError": readiness_error,
        }

    @classmethod
    def _acquire_claim(cls, key: str) -> bool:
        with cls._claims_guard:
            if key in cls._claims: return False
            cls._claims.add(key); return True

    @classmethod
    def _release_claim(cls, key: str) -> None:
        with cls._claims_guard: cls._claims.discard(key)

    @staticmethod
    def _offering_type(offering) -> str:
        return str(getattr(getattr(offering, "offering_type", None), "value",
                           getattr(offering, "offering_type", "")))

    @staticmethod
    def _validate_offering(offering) -> None:
        if offering.status == CommercialOfferingStatus.ARCHIVED:
            raise CommerceTelegramVaultError("OFFERING_ARCHIVED", "Archived Commercial Offerings cannot be published.")
        if offering.status != CommercialOfferingStatus.READY:
            raise CommerceTelegramVaultError("OFFERING_NOT_PUBLISHABLE", "Commercial Offering must be READY before publishing.")

    def _single_image_package(self, offering, creator_profile_id: int) -> dict:
        if self._offering_type(offering) != "SINGLE_IMAGE":
            raise CommerceTelegramVaultError("INVALID_OFFERING_TYPE", "Prepared Content Vault publishing requires a Single Image offering.")
        asset = self.assets.get_by_id(offering.hero_asset_id)
        if asset is None or int(asset.creator_profile_id or 0) != int(creator_profile_id):
            raise CommerceTelegramVaultError("PREVIEW_NOT_FOUND", "Offering preview Asset was not found.")
        configuration = dict((asset.media_metadata or {}).get("standalone_sale_preparation") or {})
        if list(configuration.get("destinations") or []) != ["CONTENT_VAULT"]:
            raise CommerceTelegramVaultError("INVALID_DESTINATION", "Single Image is not prepared for Content Vault.")

        publication, delivery_url = self._fanvue_delivery(offering, creator_profile_id)
        metadata = dict(publication.publication_metadata or {})
        draft = metadata.get("content_vault_caption_draft")
        caption = str((draft or {}).get("text") or "").strip() if isinstance(draft, dict) else ""
        if not caption:
            raise CommerceTelegramVaultError("CAPTION_REQUIRED", "Select and save a Content Vault caption before publishing.")
        if len(caption) > self.TELEGRAM_PHOTO_CAPTION_LIMIT:
            raise CommerceTelegramVaultError(
                "CAPTION_TOO_LONG", f"Content Vault caption exceeds Telegram's {self.TELEGRAM_PHOTO_CAPTION_LIMIT}-character photo caption limit.")

        teaser = self.teasers.get(asset.id, "CONTENT_VAULT") if self.teasers else None
        if (not teaser or int(teaser.get("source_asset_id") or 0) != int(asset.id)
                or teaser.get("distribution_use") != "CONTENT_VAULT"
                or teaser.get("status") != "READY"):
            raise CommerceTelegramVaultError("PREVIEW_NOT_FOUND", "Authoritative Content Vault teaser is not READY.")
        teaser_path = str(teaser.get("derivative_path") or "").strip()
        if not teaser_path or not Path(teaser_path).is_file():
            raise CommerceTelegramVaultError("PREVIEW_NOT_FOUND", "Authoritative Content Vault teaser file is unavailable.")
        price_minor = getattr(offering, "price_minor", None)
        currency = str(getattr(offering, "currency", None) or "").strip().upper()
        if price_minor is None or int(price_minor) <= 0 or not currency:
            raise CommerceTelegramVaultError("PRICE_REQUIRED", "A valid canonical sale price is required.")
        return {
            "caption": caption, "caption_source": draft.get("source"),
            "caption_updated_at": draft.get("updatedAt"), "asset_id": int(asset.id),
            "offering_id": str(offering.offering_id), "teaser_id": str(teaser.get("teaser_id")),
            "derived_teaser_asset_id": teaser.get("derived_asset_id"), "teaser_path": teaser_path,
            "price_minor": int(price_minor), "currency": currency,
            "fanvue_publication_id": str(publication.publication_id),
            "delivery_url": delivery_url, "telegram_destination": "vault",
        }

    def _content_vault_package(self, offering, creator_profile_id: int) -> dict:
        if self._offering_type(offering) == "SINGLE_IMAGE":
            return self._single_image_package(offering, creator_profile_id)
        if self._offering_type(offering) == "BUNDLE":
            return self._bundle_package(offering, creator_profile_id)
        raise CommerceTelegramVaultError(
            "INVALID_OFFERING_TYPE", "Content Vault publishing does not support this offering type."
        )

    def _bundle_package(self, offering, creator_profile_id: int) -> dict:
        deliverable_id = getattr(offering, "source_photoshoot_deliverable_id", None)
        if not deliverable_id:
            raise CommerceTelegramVaultError("INVALID_BUNDLE", "Bundle Photoshoot attribution is required.")
        if self.bundle_preparation is None:
            from app.services.photoshoot_bundle_sale_preparation_service import PhotoshootBundleSalePreparationService
            self.bundle_preparation = PhotoshootBundleSalePreparationService()
        try:
            row, members, canonical, publication = self.bundle_preparation.content_vault_context(
                deliverable_id, creator_profile_id=creator_profile_id,
            )
        except (KeyError, ValueError) as error:
            raise CommerceTelegramVaultError("INVALID_DESTINATION", str(error)) from error
        if str(canonical.offering_id) != str(offering.offering_id):
            raise CommerceTelegramVaultError("INVALID_BUNDLE", "Bundle offering attribution is inconsistent.")
        paid_ids = tuple(int(item["asset_id"]) for item in members)
        if tuple(item.asset_id for item in offering.assets) != paid_ids or len(paid_ids) < 2:
            raise CommerceTelegramVaultError("INVALID_BUNDLE", "Canonical paid Bundle membership is invalid.")
        publication, delivery_url = self._fanvue_delivery(offering, creator_profile_id)
        metadata = dict(publication.publication_metadata or {})
        draft = metadata.get("content_vault_caption_draft")
        caption = str((draft or {}).get("text") or "").strip() if isinstance(draft, dict) else ""
        if not caption:
            raise CommerceTelegramVaultError("CAPTION_REQUIRED", "Select and save a Content Vault caption before publishing.")
        try:
            from app.services.grok_caption_service import GrokCaptionService
            if str(draft.get("source") or "").upper() == "GROK":
                caption = GrokCaptionService.validate_bundle_caption(caption, len(paid_ids))
            else:
                caption = GrokCaptionService.validate_operator_bundle_caption(caption)
        except ValueError as error:
            raise CommerceTelegramVaultError("INVALID_CAPTION", str(error)) from error
        if len(caption) > self.TELEGRAM_PHOTO_CAPTION_LIMIT:
            raise CommerceTelegramVaultError("CAPTION_TOO_LONG", f"Content Vault caption exceeds Telegram's {self.TELEGRAM_PHOTO_CAPTION_LIMIT}-character photo caption limit.")
        teaser = self.bundle_preparation.teasers.inspect(
            deliverable_id, creator_profile_id=creator_profile_id,
        )
        if teaser.get("status") != "READY" or not teaser.get("teaserAssetId"):
            raise CommerceTelegramVaultError("PREVIEW_NOT_FOUND", "Authoritative Bundle promotional teaser is not READY.")
        teaser_asset = self.assets.get_by_id(int(teaser["teaserAssetId"]))
        teaser_path = str(getattr(teaser_asset, "local_vault_path", None) or getattr(teaser_asset, "file_path", None) or "").strip()
        if teaser_asset is None or int(teaser_asset.creator_profile_id or 0) != int(creator_profile_id) or not teaser_path or not Path(teaser_path).is_file():
            raise CommerceTelegramVaultError("PREVIEW_NOT_FOUND", "Authoritative Bundle promotional teaser file is unavailable.")
        if offering.price_minor is None or int(offering.price_minor) <= 0 or not str(offering.currency or "").strip():
            raise CommerceTelegramVaultError("PRICE_REQUIRED", "A valid canonical Bundle price is required.")
        return {
            "caption": caption, "caption_source": draft.get("source"),
            "caption_updated_at": draft.get("updatedAt"),
            "offering_id": str(offering.offering_id),
            "photoshoot_deliverable_id": str(row["deliverable_id"]),
            "paid_asset_ids": list(paid_ids), "paid_image_count": len(paid_ids),
            "teaser_asset_id": int(teaser["teaserAssetId"]), "teaser_path": teaser_path,
            "price_minor": int(offering.price_minor), "currency": str(offering.currency).upper(),
            "fanvue_publication_id": str(publication.publication_id),
            "delivery_url": delivery_url, "telegram_destination": "vault",
        }

    def _fanvue_delivery(self, offering, creator_profile_id: int):
        publications = self.publications.list_publications(
            creator_profile_id=creator_profile_id, commercial_offering_id=offering.offering_id)
        publication = next((item for item in publications
            if item.provider == CommercialPublicationProvider.FANVUE
            and item.status == CommercialPublicationStatus.LIVE
            and item.provider_resource_status == ProviderResourceStatus.PRESENT), None)
        metadata = publication.publication_metadata if publication else {}
        media_link = metadata.get("media_link") if isinstance(metadata, dict) else None
        url = media_link.get("url") if isinstance(media_link, dict) else None
        if not str(url or "").strip().startswith(("http://", "https://")):
            raise CommerceTelegramVaultError("ACTIVE_MEDIA_LINK_REQUIRED", "An active provider-backed Fanvue Media Link is required.")
        return publication, str(url).strip()

    @staticmethod
    def _money(price_minor: int, currency: str) -> str:
        symbols = {"USD": "$", "EUR": "€", "GBP": "£"}
        amount = f"{int(price_minor) / 100:.2f}"
        return f"{symbols.get(currency, currency + ' ')}{amount}"

    def _telegram_configured(self) -> bool:
        config = self.social.telegram_provider.load_telegram_env()
        return all(str(config.get(name) or "").strip() for name in ("bot_token", "vault_chat_id"))

    def _offering(self, offering_id, creator_profile_id: int):
        offering = self.offerings.get(
            UUID(str(offering_id)), creator_profile_id=creator_profile_id
        )
        if offering is None:
            raise CommerceTelegramVaultError(
                "OFFERING_NOT_FOUND", "Commercial Offering not found."
            )
        return offering

    def _delivery_url(self, offering, creator_profile_id: int) -> str:
        return self._fanvue_delivery(offering, creator_profile_id)[1]

    def _preview(self, offering, creator_profile_id: int) -> str:
        asset = self.assets.get_by_id(offering.hero_asset_id)
        if asset is None or asset.creator_profile_id != int(creator_profile_id):
            raise CommerceTelegramVaultError(
                "PREVIEW_NOT_FOUND", "Offering preview Asset was not found."
            )
        candidate = str(asset.local_vault_path or asset.file_path or "").strip()
        if not candidate or not Path(candidate).is_file():
            raise CommerceTelegramVaultError(
                "PREVIEW_NOT_FOUND", "Offering preview image is unavailable."
            )
        if asset.media_type != "image":
            raise CommerceTelegramVaultError(
                "INVALID_PREVIEW", "Telegram Content Vault requires an image preview."
            )
        return candidate

    def _validate_telegram(self) -> None:
        config = self.social.telegram_provider.load_telegram_env()
        missing = [
            name for name in ("bot_token", "vault_chat_id")
            if not str(config.get(name) or "").strip()
        ]
        if missing:
            raise CommerceTelegramVaultError(
                "TELEGRAM_NOT_CONFIGURED",
                "Telegram Content Vault configuration is incomplete: "
                + ", ".join(missing),
            )

    @staticmethod
    def _caption(title: str, description: str | None, marketing_text: str | None):
        parts = [f"<b>{escape(str(title).strip())}</b>"]
        if description and str(description).strip():
            parts.append(escape(str(description).strip()))
        if marketing_text and str(marketing_text).strip():
            parts.append(escape(str(marketing_text).strip()))
        return "\n\n".join(parts)
