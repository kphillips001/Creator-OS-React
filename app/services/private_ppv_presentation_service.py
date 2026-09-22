"""Resolve and validate the canonical private-chat PPV presentation."""

from __future__ import annotations

import re
from uuid import UUID

from app.models.commercial_offering import CommercialOfferingType
from app.models.private_ppv_presentation import PrivatePpvPresentation
from app.repositories.asset_repository import AssetRepository
from app.repositories.commercial_offering_repository import CommercialOfferingRepository
from app.repositories.commercial_teaser_repository import CommercialTeaserRepository
from app.services.private_ppv_readiness_service import PrivatePpvReadinessService


class PrivatePpvPresentationError(RuntimeError):
    code = "PRIVATE_PPV_PRESENTATION_INVALID"


class PrivatePpvPresentationService:
    """Build one media+caption+button contract from explicit sale authorities."""

    BUTTON_LABEL = "🔓 Unlock"
    _VISIBLE_URL = re.compile(r"https?://\S+", re.IGNORECASE)
    _UNLOCK_TEXT = re.compile(r"(?:🔓\s*)?unlock\s*:\s*https?://", re.IGNORECASE)

    def __init__(self, *, offerings=None, teasers=None, assets=None,
                 readiness=None):
        self.offerings = offerings or CommercialOfferingRepository()
        self.teasers = teasers or CommercialTeaserRepository()
        self.assets = assets or AssetRepository()
        self.readiness = readiness or PrivatePpvReadinessService()

    def build(self, *, creator_profile_id: int, offering_id, publication_id,
              purchase_intent_id, delivery_identity: str,
              attribution_identity: str, message_text: str,
              unlock_button_url: str) -> PrivatePpvPresentation:
        copy = str(message_text or "").strip()
        destination = str(unlock_button_url or "").strip()
        self.validate_customer_text(copy, configured_destination=destination)
        from app.models.telegram_offer_caption import telegram_offer_caption
        copy = telegram_offer_caption(copy)
        if not destination.startswith(("https://", "http://")):
            raise PrivatePpvPresentationError("Private PPV unlock destination is invalid.")

        offering = self.offerings.get(
            UUID(str(offering_id)), creator_profile_id=int(creator_profile_id))
        if offering is None or offering.offering_type is not CommercialOfferingType.SINGLE_IMAGE:
            raise PrivatePpvPresentationError("Canonical SINGLE_IMAGE offering was not found.")

        source_asset_id = int(offering.hero_asset_id)
        teaser = self.teasers.get(source_asset_id, "CHAT")
        teaser_asset_id = int((teaser or {}).get("derived_asset_id") or 0)
        teaser_asset = self.assets.get_by_id(teaser_asset_id) if teaser_asset_id else None
        teaser_metadata = dict(getattr(teaser_asset, "media_metadata", None) or {})
        readiness = self.readiness.evaluate({
            "creator_profile_id": creator_profile_id,
            "hero_asset_id": source_asset_id,
            "chat_teaser_id": (teaser or {}).get("teaser_id"),
            "chat_teaser_creator_profile_id": (teaser or {}).get("creator_profile_id"),
            "chat_teaser_source_asset_id": (teaser or {}).get("source_asset_id"),
            "chat_teaser_derived_asset_id": teaser_asset_id,
            "chat_teaser_derivative_path": (teaser or {}).get("derivative_path"),
            "chat_teaser_distribution_use": (teaser or {}).get("distribution_use"),
            "chat_teaser_status": (teaser or {}).get("status"),
            "chat_teaser_derived_creator_profile_id": getattr(
                teaser_asset, "creator_profile_id", None),
            "chat_teaser_derived_source_asset_id": teaser_metadata.get("source_asset_id"),
            "chat_teaser_derived_distribution_use": teaser_metadata.get("distribution_use"),
            "chat_teaser_derived_commercial_role": teaser_metadata.get("commercial_role"),
        })
        if not readiness.ready:
            raise PrivatePpvPresentationError(
                f"Canonical private PPV presentation is not ready: {readiness.reason}.")

        return PrivatePpvPresentation(
            offering_id=str(offering.offering_id), publication_id=str(publication_id),
            purchase_intent_id=str(purchase_intent_id),
            delivery_identity=str(delivery_identity), teaser_asset_id=teaser_asset_id,
            teaser_path=str(readiness.teaser_path), message_text=copy,
            unlock_button_label=self.BUTTON_LABEL, unlock_button_url=destination,
            attribution_identity=str(attribution_identity),
        )

    @classmethod
    def validate_customer_text(cls, message_text: str, *, configured_destination: str = "") -> None:
        text = str(message_text or "")
        destination = str(configured_destination or "").strip()
        lowered = text.lower()
        forbidden_host = any(host in lowered for host in (
            "unlock.avablackthorne.net", "fanvue.com", "fanvue.co",
        ))
        if (
            cls._UNLOCK_TEXT.search(text)
            or forbidden_host
            or (destination and destination in text)
            or cls._VISIBLE_URL.search(text)
        ):
            raise PrivatePpvPresentationError(
                "Customer-visible PPV text contains a commerce URL."
            )
