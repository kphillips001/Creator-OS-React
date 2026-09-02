"""Deterministic, prompt-safe sales context for one prepared Photoshoot Bundle."""

from __future__ import annotations

import json
from pathlib import Path

from app.repositories.asset_repository import AssetRepository
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.services.photoshoot_bundle_ownership_service import PhotoshootBundleOwnershipService
from app.services.photoshoot_bundle_sale_preparation_service import PhotoshootBundleSalePreparationService
from app.services.photoshoot_bundle_teaser_service import PhotoshootBundleTeaserService
from app.services.runtime_media_resolver import RuntimeMediaResolver
from app.services.photoshoot_commercial_intelligence_service import PhotoshootCommercialIntelligenceService


class PhotoshootBundleSalesContextService:
    SCHEMA_VERSION = "photoshoot_bundle_conversation_v1"

    def __init__(self, *, photoshoots=None, preparation=None, teasers=None,
                 ownership=None, assets=None, media=None) -> None:
        self.photoshoots = photoshoots or PhotoshootCommerceRepository()
        self.preparation = preparation or PhotoshootBundleSalePreparationService()
        self.teasers = teasers or PhotoshootBundleTeaserService()
        self.ownership = ownership or PhotoshootBundleOwnershipService()
        self.assets = assets or AssetRepository()
        self.media = media or RuntimeMediaResolver()

    def resolve_mode(self, photoshoot_session_id: str) -> str | None:
        row = self.photoshoots.get_by_session(str(photoshoot_session_id))
        return str(row.get("selling_mode") or "SESSION") if row else None

    def build(self, photoshoot_session_id: str, *, identity,
              lifecycle_id=None, teaser_presented=False,
              offer_presented=False) -> dict:
        row = self.photoshoots.get_by_session(str(photoshoot_session_id))
        if row is None:
            raise KeyError("Photoshoot not found.")
        if str(row.get("selling_mode") or "SESSION") != "BUNDLE":
            raise ValueError("Bundle sales context requires BUNDLE selling mode.")
        deliverable_id = str(row["deliverable_id"])
        paid = self.preparation.inspect(
            deliverable_id, creator_profile_id=identity.creator_profile_id,
        )
        teaser = self.teasers.inspect(
            deliverable_id, creator_profile_id=identity.creator_profile_id,
        )
        owned = self.ownership.inspect(deliverable_id, identity=identity)
        reasons = []
        channel = str(row.get("bundle_sales_channel") or "CHAT")
        if channel != "CHAT":
            reasons.append("BUNDLE_CHANNEL_CONTENT_WALL")
        if offer_presented:
            reasons.append("BUNDLE_ALREADY_PRESENTED")
        if paid.get("status") != "READY":
            reasons.append("BUNDLE_MEDIA_NOT_READY")
        if not all((paid.get("offeringId"), paid.get("publicationId"),
                    paid.get("deliveryUrl"))):
            reasons.append("BUNDLE_MEDIA_NOT_READY")
        if teaser.get("status") != "READY" or not teaser.get("teaserAssetId"):
            reasons.append("BUNDLE_TEASER_NOT_READY")
        teaser_path = None
        if teaser.get("teaserAssetId"):
            try:
                asset = self.assets.get_by_id(int(teaser["teaserAssetId"]))
                resolved = self.media.resolve_original(asset, require_exists=True)
                teaser_path = str(resolved.path) if resolved.path else None
            except Exception:
                teaser_path = None
        if teaser_path is None:
            reasons.append("BUNDLE_TEASER_NOT_READY")
        if owned.get("purchased"):
            reasons.append("BUNDLE_ALREADY_PURCHASED")
        paid_ids = tuple(int(value) for value in owned.get("paidAssetIds") or ())
        owned_count = int(owned.get("ownedPaidAssetCount") or 0)
        if not owned.get("purchased") and owned_count:
            reasons.append(
                "BUNDLE_FULLY_OWNED"
                if owned_count == len(paid_ids) else "BUNDLE_PARTIALLY_OWNED"
            )
        if owned.get("ownershipState") in {"INSUFFICIENT", "CONFLICTING"}:
            reasons.append("BUNDLE_OWNERSHIP_UNRESOLVED")
        if teaser.get("sourceAssetId") not in paid_ids:
            reasons.append("BUNDLE_TEASER_SOURCE_INVALID")
        if str(paid.get("offeringId") or "") != str(owned.get("bundleOfferingId") or ""):
            reasons.append("BUNDLE_OFFERING_CONFLICT")
        intelligence = dict(row.get("intelligence_profile") or {})
        if (row.get("commercial_intelligence_status") != "READY"
                or row.get("commercial_intelligence_stage") != "COMPLETE"
                or not PhotoshootCommercialIntelligenceService.has_complete_commercial_contract(intelligence)):
            reasons.append("COMMERCIAL_INTELLIGENCE_INCOMPLETE")
        title = self._first(
            paid.get("title"), row.get("commercial_title"),
            intelligence.get("commercial_title"), row.get("display_name"),
            "Photoshoot Bundle",
        )
        intelligence_reader = getattr(
            self.photoshoots, "latest_shot_intelligence", None,
        )
        member_rows = tuple(
            intelligence_reader(str(row["photoshoot_session_id"])) or ()
        ) if callable(intelligence_reader) else ()
        member_profiles = [
            dict(member.get("profile_data") or {})
            for member in member_rows
            if int(member.get("asset_id") or 0) in paid_ids
        ]
        aggregate_fields = (
            "scene_environment", "emotional_tone", "sequence_role",
            "wardrobe_state", "visual_focus",
        )
        aggregate = {
            field: self._distinct(
                profile.get(field) for profile in member_profiles
            )
            for field in aggregate_fields
        }
        aggregate = {key: value for key, value in aggregate.items() if value}
        representative_profile = next((
            dict(member.get("profile_data") or {})
            for member in member_rows
            if int(member.get("asset_id") or 0) == int(teaser.get("sourceAssetId") or 0)
        ), {})
        context = {
            "schemaVersion": self.SCHEMA_VERSION,
            "sellingMode": "BUNDLE",
            "bundleSalesChannel": channel,
            "eligible": not reasons,
            "ineligibilityReasons": list(dict.fromkeys(reasons)),
            "presentationPhase": (
                "TERMINAL" if owned.get("purchased")
                else "ALREADY_PRESENTED" if offer_presented
                else "PAID_OFFER_ONLY" if teaser_presented
                else "COMPLETE_PRESENTATION"
            ),
            "lifecycleId": str(lifecycle_id) if lifecycle_id else None,
            "photoshoot": {
                "deliverableId": deliverable_id,
                "photoshootSessionId": str(row["photoshoot_session_id"]),
                "title": title,
                "subtitle": self._first(intelligence.get("subtitle")),
                "commercialSummary": self._first(
                    intelligence.get("commercial_summary"),
                    intelligence.get("summary"),
                ),
                "story": self._first(intelligence.get("story")),
                "theme": self._first(intelligence.get("theme")),
                "experience": intelligence.get("experience"),
                "emotionalJourney": intelligence.get("emotional_journey"),
                "buyerProfile": intelligence.get("buyer_profile"),
                "salesStrategy": intelligence.get("sales_strategy"),
                "salesBrainBrief": intelligence.get("sales_brain_brief"),
                "approvedOriginalCount": len(paid_ids),
            },
            "promotionalTeaser": {
                "assetId": teaser.get("teaserAssetId"),
                "sourceAssetId": teaser.get("sourceAssetId"),
                "mediaReference": teaser.get("previewUrl"),
                "role": "BUNDLE_PROMOTIONAL_TEASER",
                "presented": bool(teaser_presented),
                "scope": (
                    "This preview represents one source member only. Its specific visual "
                    "details must not be attributed to every paid Bundle member."
                ),
            },
            "bundlePresentationIntelligence": {
                "scope": "WHOLE_BUNDLE",
                "overallMood": self._first(
                    intelligence.get("mood"),
                    intelligence.get("emotional_journey"),
                ),
                "aggregateMemberSignals": aggregate,
                "representativeSource": {
                    "scope": "ONE_REPRESENTATIVE_MEMBER_ONLY",
                    "summary": {
                        key: representative_profile[key]
                        for key in aggregate_fields
                        if representative_profile.get(key) not in (None, "", [], {})
                    },
                },
                "languageRules": [
                    "Entice toward the Photoshoot experience as a whole, not one image.",
                    "Use representative details only as preview evidence, never as facts about every member.",
                    "Do not enumerate or invent members, counts, scenes, outfits, or future reveals.",
                ],
            },
            "bundleOffer": {
                "offeringId": paid.get("offeringId"),
                "offeringType": "BUNDLE",
                "priceMinor": paid.get("priceMinor"),
                "currency": paid.get("currency"),
                "publicationId": paid.get("publicationId"),
                "provider": "FANVUE",
                "providerResourceId": paid.get("mediaLinkUuid"),
                "mediaLink": paid.get("deliveryUrl"),
                "paidMemberCount": len(paid_ids),
            },
            "ownership": {
                "purchased": bool(owned.get("purchased")),
                "purchasedAt": owned.get("purchasedAt"),
            },
            "presentation": {
                "teaserPresented": bool(teaser_presented),
                "offerPresented": bool(offer_presented),
            },
            "salesRules": [
                "The entire Photoshoot is one purchase.",
                "The selective-blur teaser is promotional only.",
                "The teaser source original remains paid Bundle content.",
                "Never offer individual Bundle members.",
                "Never use sequential Photoshoot progression.",
                "One attributed purchase completes the Photoshoot commercially.",
            ],
            "_delivery": {"teaserAssetPath": teaser_path},
        }
        context["promptBlock"] = self.render_prompt_block(context)
        return context

    @staticmethod
    def render_prompt_block(context) -> str:
        safe = {
            key: value for key, value in context.items()
            if key not in {"_delivery", "promptBlock"}
        }
        return (
            "BUNDLE PHOTOSHOOT CONVERSATION CONTEXT\n"
            "These commercial facts are authoritative. Choose natural language only; "
            "do not choose or alter the product, price, media, ownership, or fulfillment.\n"
            + json.dumps(safe, indent=2, ensure_ascii=False, default=str)
        )

    @staticmethod
    def _first(*values):
        return next((str(value).strip() for value in values
                     if value is not None and str(value).strip()), None)

    @staticmethod
    def _distinct(values, limit=6):
        result = []
        for value in values:
            if value in (None, "", [], {}):
                continue
            candidates = value if isinstance(value, (list, tuple)) else (value,)
            for candidate in candidates:
                text = str(candidate).strip()
                if text and text not in result:
                    result.append(text)
                if len(result) >= limit:
                    return result
        return result
