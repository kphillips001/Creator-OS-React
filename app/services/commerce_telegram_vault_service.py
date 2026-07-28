"""Commerce-authoritative publishing to Ava's Telegram Content Vault."""

from __future__ import annotations

from html import escape
from pathlib import Path
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


class CommerceTelegramVaultError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CommerceTelegramVaultService:
    """Validates Commerce state and delegates delivery to Social Publishing."""

    def __init__(
        self,
        *,
        offerings=None,
        publications=None,
        assets=None,
        social=None,
    ) -> None:
        self.offerings = offerings or CommercialOfferingService()
        self.publications = publications or CommercialPublicationService(
            offering_repository=self.offerings.repository
        )
        self.assets = assets or AssetRepository()
        self.social = social or SocialPublishingService()

    def publish(
        self,
        offering_id,
        *,
        creator_profile_id: int,
        marketing_text: str | None = None,
    ):
        offering = self._offering(offering_id, creator_profile_id)
        if offering.status == CommercialOfferingStatus.ARCHIVED:
            raise CommerceTelegramVaultError(
                "OFFERING_ARCHIVED",
                "Archived Commercial Offerings cannot be published.",
            )
        if offering.status != CommercialOfferingStatus.READY:
            raise CommerceTelegramVaultError(
                "OFFERING_NOT_PUBLISHABLE",
                "Commercial Offering must be READY before publishing.",
            )
        delivery_url = self._delivery_url(offering, creator_profile_id)
        preview = self._preview(offering, creator_profile_id)
        self._validate_telegram()

        source_id = f"commercial-offering:{offering.offering_id}"
        existing = self.social.find_queue_item(source_id, platform="telegram")
        if existing and existing.status == SocialPublishStatus.POSTED.value:
            raise CommerceTelegramVaultError(
                "ALREADY_PUBLISHED",
                "Commercial Offering is already published to Telegram Content Vault.",
            )
        item = self.social.create_commerce_queue_item(
            commercial_offering_id=str(offering.offering_id),
            creator_profile_id=creator_profile_id,
            hero_asset_id=offering.hero_asset_id,
            image_reference=preview,
            title=offering.title,
        )
        caption = self._caption(
            offering.title, offering.description, marketing_text
        )
        result = self.social.publish_now(
            item.queue_item_id,
            caption_text=caption,
            telegram_post_to="vault",
            telegram_cta_enabled=True,
            telegram_cta_label="Unlock Now",
            telegram_cta_url=delivery_url,
        )
        if result.status == SocialPublishStatus.FAILED.value:
            history = [
                entry for entry in self.social.list_history()
                if entry.queue_item_id == item.queue_item_id
            ]
            message = history[0].message if history else "Telegram publishing failed."
            raise CommerceTelegramVaultError(
                "TELEGRAM_PUBLISH_FAILED", message or "Telegram publishing failed."
            )
        return result

    def status(self, offering_id, *, creator_profile_id: int) -> dict:
        offering = self.offerings.get(
            UUID(str(offering_id)), creator_profile_id=creator_profile_id
        )
        if offering is None:
            return {"status": None, "publishedAt": None, "lastError": None}
        source_id = f"commercial-offering:{offering.offering_id}"
        item = self.social.find_queue_item(source_id, platform="telegram")
        if item is None:
            return {"status": None, "publishedAt": None, "lastError": None}
        history = [
            entry for entry in self.social.list_history()
            if entry.queue_item_id == item.queue_item_id
        ]
        failed = next(
            (entry.message for entry in history if entry.status == "failed"), None
        )
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
        }

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
        publications = self.publications.list_publications(
            creator_profile_id=creator_profile_id,
            commercial_offering_id=offering.offering_id,
        )
        publication = next(
            (
                item for item in publications
                if item.provider == CommercialPublicationProvider.FANVUE
                and item.status == CommercialPublicationStatus.LIVE
                and item.provider_resource_status == ProviderResourceStatus.PRESENT
            ),
            None,
        )
        metadata = publication.publication_metadata if publication else {}
        media_link = metadata.get("media_link") if isinstance(metadata, dict) else None
        url = media_link.get("url") if isinstance(media_link, dict) else None
        if not str(url or "").strip().startswith(("http://", "https://")):
            raise CommerceTelegramVaultError(
                "ACTIVE_MEDIA_LINK_REQUIRED",
                "An active provider-backed Fanvue Media Link is required.",
            )
        return str(url).strip()

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
