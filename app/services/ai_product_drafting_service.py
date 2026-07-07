"""Create Product Catalog drafts from approved CMS assets."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.models.asset import Asset
from app.models.product import Product, ProductStatus, ProductType
from app.models.product_draft_source import ProductDraftSource
from app.services.experience_service import ExperienceService
from app.services.runtime_media_resolver import (
    RuntimeMediaPath,
    RuntimeMediaResolver,
)

if TYPE_CHECKING:
    from app.repositories.asset_repository import AssetRepository
    from app.repositories.product_asset_repository import ProductAssetRepository
    from app.repositories.product_repository import ProductRepository


class AIProductDraftingError(Exception):
    """Base error for AI product drafting failures."""


class AIProductDraftingNotEligibleError(AIProductDraftingError):
    """Raised when an asset should not produce a product draft."""


@dataclass(frozen=True)
class AIProductDraftResult:
    product: Product
    created: bool
    updated: bool
    product_asset_created: bool
    activated: bool = False
    skipped_reason: str | None = None


class AIProductDraftingService:
    CONFIDENCE_THRESHOLD = 0.80
    _CLASSIFICATION_RANK = {
        "TEASE": 1,
        "VIP": 2,
        "PREMIUM": 3,
        "EDGE_CASE": 0,
    }
    _INTENSITY_RANK = {
        None: 0,
        "low": 1,
        "medium": 2,
        "high": 3,
    }

    def __init__(
        self,
        asset_repository: "AssetRepository | None" = None,
        product_repository: "ProductRepository | None" = None,
        product_asset_repository: "ProductAssetRepository | None" = None,
        runtime_media_resolver: RuntimeMediaResolver | None = None,
        experience_service: ExperienceService | None = None,
    ):
        if asset_repository is None:
            from app.repositories.asset_repository import AssetRepository

            asset_repository = AssetRepository()
        if product_repository is None:
            from app.repositories.product_repository import ProductRepository

            product_repository = ProductRepository()
        if product_asset_repository is None:
            from app.repositories.product_asset_repository import (
                ProductAssetRepository,
            )

            product_asset_repository = ProductAssetRepository()

        self.assets = asset_repository
        self.products = product_repository
        # Compatibility storage only. ExperienceService owns Product/Asset
        # composition calls while ProductAsset remains the persisted bridge.
        self.product_assets = product_asset_repository
        self.runtime_media_resolver = (
            runtime_media_resolver or RuntimeMediaResolver()
        )
        self.experiences = experience_service or ExperienceService(
            self._default_experience_repository()
        )

    def _default_experience_repository(self):
        from app.repositories.experience_repository import ExperienceRepository

        return (
            ExperienceRepository(
                product_repository=self.products,
                product_asset_repository=self.product_assets,
            )
        )

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return slug or "asset"

    @staticmethod
    def _humanize_filename(asset: Asset) -> str:
        stem = Path(asset.file_name or asset.file_path).stem
        stem = re.sub(r"^\d{8}_\d{6}_\d+_", "", stem)
        stem = re.sub(r"[_-]+", " ", stem).strip()
        return stem.title() if stem else f"Asset {asset.id}"

    @staticmethod
    def _infer_product_type(asset: Asset) -> ProductType:
        if asset.media_type == "image":
            return ProductType.SINGLE_IMAGE
        if asset.media_type == "video":
            return ProductType.SINGLE_VIDEO
        return ProductType.CUSTOM

    def _runtime_original_media(self, asset: Asset) -> RuntimeMediaPath:
        return self.runtime_media_resolver.resolve_original(
            asset,
            require_exists=True,
        )

    def _metadata(self, asset: Asset) -> dict:
        runtime_original = self._runtime_original_media(asset)
        return {
            "draft_source": "ai_cms_asset",
            "ai_product_draft": True,
            "legacy_content_item_id": asset.id,
            "source_asset_id": asset.id,
            "classification": asset.classification,
            "confidence": asset.confidence,
            "risk_flags": list(asset.risk_flags),
            "nudity": {
                "labels": list(asset.nudity_labels),
                "level": asset.nudity_level,
                "sexual_intensity": asset.sexual_intensity,
                "is_explicit": asset.is_explicit,
            },
            "analysis": {
                "summary": asset.summary,
                "reasoning": asset.reasoning,
                "provenance": dict(asset.analysis_provenance or {}),
                "media_metadata": dict(asset.media_metadata or {}),
                "runtime_original_media": {
                    "path": runtime_original.path_string,
                    "source": runtime_original.source,
                    "exists": runtime_original.exists,
                },
            },
        }

    @staticmethod
    def _dedupe_ordered(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        normalized = []
        seen = set()
        for value in values or ():
            clean = str(value).strip()
            if not clean:
                continue
            key = clean.lower()
            if key not in seen:
                seen.add(key)
                normalized.append(clean)
        return tuple(normalized)

    @classmethod
    def _highest_classification(cls, assets: list[Asset]) -> str | None:
        classifications = [
            (asset.classification or "").upper()
            for asset in assets
            if asset.classification
        ]
        if not classifications:
            return None
        return max(
            classifications,
            key=lambda value: cls._CLASSIFICATION_RANK.get(value, 0),
        )

    @classmethod
    def _highest_intensity(cls, assets: list[Asset]) -> str | None:
        intensities = [asset.sexual_intensity for asset in assets]
        return max(
            intensities,
            key=lambda value: cls._INTENSITY_RANK.get(value, 0),
        )

    @staticmethod
    def _average_confidence(assets: list[Asset]) -> float | None:
        values = []
        for asset in assets:
            try:
                values.append(float(asset.confidence))
            except (TypeError, ValueError):
                pass
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    def _aggregate_photo_set_asset(self, assets: list[Asset]) -> Asset:
        primary = assets[0]
        tags = self._dedupe_ordered(
            [
                tag
                for asset in assets
                for tag in asset.suggested_tags
            ]
        )
        themes = self._dedupe_ordered(
            [
                theme
                for asset in assets
                for theme in asset.detected_themes
            ]
        )
        summaries = [
            asset.summary
            for asset in assets
            if asset.summary
        ]
        risk_flags = self._dedupe_ordered(
            [
                flag
                for asset in assets
                for flag in asset.risk_flags
            ]
        )
        nudity_labels = self._dedupe_ordered(
            [
                label
                for asset in assets
                for label in asset.nudity_labels
            ]
        )
        classification = self._highest_classification(assets)
        confidence = self._average_confidence(assets)
        sexual_intensity = self._highest_intensity(assets)

        return Asset(
            id=primary.id,
            file_path=primary.file_path,
            file_name=f"photo_set_{primary.id}_{len(assets)}_assets",
            classification=classification,
            confidence=confidence,
            status="approved",
            is_active=True,
            is_test=all(asset.is_test for asset in assets),
            ready_for_rotation=True,
            upload_intent="photo_set",
            content_tier=primary.content_tier,
            distribution_type=primary.distribution_type,
            blurred_preview_path=primary.blurred_preview_path,
            suggested_tags=tags,
            detected_themes=themes,
            is_explicit=any(asset.is_explicit for asset in assets),
            fanvue_media_preview_uuid=None,
            fanvue_media_full_uuid=None,
            created_at=primary.created_at,
            summary=(
                "Photo set containing "
                f"{len(assets)} images. "
                + " ".join(summaries[:3])
            ).strip(),
            risk_flags=risk_flags,
            reasoning=(
                "Aggregated PHOTO_SET product generated from ordered CMS assets."
            ),
            analysis_provenance={
                "source": "photo_set_upload",
                "asset_ids": [asset.id for asset in assets],
                "asset_count": len(assets),
            },
            media_metadata={
                "asset_count": len(assets),
                "asset_ids": [asset.id for asset in assets],
            },
            creator_profile_id=primary.creator_profile_id,
            nudity_labels=nudity_labels,
            nudity_level=primary.nudity_level,
            sexual_intensity=sexual_intensity,
            gpt_vision_result={},
            nudenet_result=None,
            classification_result={
                "final_classification": classification,
                "rule_applied": "photo_set_aggregate",
            },
        )

    @staticmethod
    def pricing_decision_for_asset(asset: Asset, product_type: ProductType) -> dict:
        """
        Return the read-only AI pricing decision used for product activation.

        Pricing is Product lifecycle state; this remains asset-derived for
        Phase 1 compatibility with automatic AI Product Draft creation.
        """

        classification = (asset.classification or "").upper()
        base_by_classification = {
            "TEASE": 999,
            "VIP": 2499,
            "PREMIUM": 4999,
        }
        base = base_by_classification.get(classification, 1999)
        factors = [
            {
                "factor": "classification",
                "value": classification or "UNKNOWN",
                "price_delta_cents": base,
            }
        ]

        if product_type == ProductType.SINGLE_VIDEO:
            base += 1000
            factors.append({
                "factor": "product_type",
                "value": product_type.value,
                "price_delta_cents": 1000,
            })
        elif product_type in {ProductType.PHOTO_SET, ProductType.VIDEO_SET}:
            base += 1500
            factors.append({
                "factor": "product_type",
                "value": product_type.value,
                "price_delta_cents": 1500,
            })
        elif product_type in {ProductType.STORY, ProductType.SESSION}:
            base += 2500
            factors.append({
                "factor": "product_type",
                "value": product_type.value,
                "price_delta_cents": 2500,
            })
        elif product_type == ProductType.BUNDLE:
            base += 3500
            factors.append({
                "factor": "product_type",
                "value": product_type.value,
                "price_delta_cents": 3500,
            })
        else:
            factors.append({
                "factor": "product_type",
                "value": product_type.value,
                "price_delta_cents": 0,
            })

        if asset.sexual_intensity == "high":
            base += 1000
            factors.append({
                "factor": "sexual_intensity",
                "value": "high",
                "price_delta_cents": 1000,
            })
        elif asset.sexual_intensity == "medium":
            base += 500
            factors.append({
                "factor": "sexual_intensity",
                "value": "medium",
                "price_delta_cents": 500,
            })
        else:
            factors.append({
                "factor": "sexual_intensity",
                "value": asset.sexual_intensity or "none",
                "price_delta_cents": 0,
            })

        try:
            confidence = float(asset.confidence or 0)
        except (TypeError, ValueError):
            confidence = 0
        if confidence >= 0.95:
            base += 500
            factors.append({
                "factor": "confidence",
                "value": confidence,
                "price_delta_cents": 500,
            })
        else:
            factors.append({
                "factor": "confidence",
                "value": confidence,
                "price_delta_cents": 0,
            })

        min_price = max(499, int(round(base * 0.75 / 100)) * 100)
        max_price = max(base, int(round(base * 1.35 / 100)) * 100)
        return {
            "pricing_rule": f"{classification or 'UNKNOWN'}_{product_type.value}",
            "base_price_cents": base,
            "min_price_cents": min_price,
            "max_price_cents": max_price,
            "classification": classification or None,
            "product_type": product_type.value,
            "confidence": confidence,
            "tags": list(asset.suggested_tags),
            "themes": list(asset.detected_themes),
            "sexual_intensity": asset.sexual_intensity,
            "factors": factors,
            "explanation": (
                f"{classification or 'UNKNOWN'} {product_type.value} pricing "
                f"with {asset.sexual_intensity or 'no'} sexual-intensity adjustment "
                f"and confidence {confidence:.2f}."
            ),
        }

    @staticmethod
    def _price_band_for_asset(asset: Asset, product_type: ProductType) -> dict:
        decision = AIProductDraftingService.pricing_decision_for_asset(
            asset,
            product_type,
        )
        return {
            "base_price_cents": decision["base_price_cents"],
            "min_price_cents": decision["min_price_cents"],
            "max_price_cents": decision["max_price_cents"],
        }

    @staticmethod
    def pricing_decision_for_source(source: ProductDraftSource) -> dict:
        """
        Return the Product-facing pricing decision for a draft source.

        This mirrors pricing_decision_for_asset while keeping Product creation
        on a narrow, provider-neutral input contract.
        """

        classification = (source.classification or "").upper()
        base_by_classification = {
            "TEASE": 999,
            "VIP": 2499,
            "PREMIUM": 4999,
        }
        base = base_by_classification.get(classification, 1999)
        factors = [
            {
                "factor": "classification",
                "value": classification or "UNKNOWN",
                "price_delta_cents": base,
            }
        ]

        if source.product_type == ProductType.SINGLE_VIDEO:
            base += 1000
            factors.append({
                "factor": "product_type",
                "value": source.product_type.value,
                "price_delta_cents": 1000,
            })
        elif source.product_type in {ProductType.PHOTO_SET, ProductType.VIDEO_SET}:
            base += 1500
            factors.append({
                "factor": "product_type",
                "value": source.product_type.value,
                "price_delta_cents": 1500,
            })
        elif source.product_type in {ProductType.STORY, ProductType.SESSION}:
            base += 2500
            factors.append({
                "factor": "product_type",
                "value": source.product_type.value,
                "price_delta_cents": 2500,
            })
        elif source.product_type == ProductType.BUNDLE:
            base += 3500
            factors.append({
                "factor": "product_type",
                "value": source.product_type.value,
                "price_delta_cents": 3500,
            })
        else:
            factors.append({
                "factor": "product_type",
                "value": source.product_type.value,
                "price_delta_cents": 0,
            })

        if source.intensity == "high":
            base += 1000
            factors.append({
                "factor": "sexual_intensity",
                "value": "high",
                "price_delta_cents": 1000,
            })
        elif source.intensity == "medium":
            base += 500
            factors.append({
                "factor": "sexual_intensity",
                "value": "medium",
                "price_delta_cents": 500,
            })
        else:
            factors.append({
                "factor": "sexual_intensity",
                "value": source.intensity or "none",
                "price_delta_cents": 0,
            })

        confidence = float(source.confidence or 0)
        if confidence >= 0.95:
            base += 500
            factors.append({
                "factor": "confidence",
                "value": confidence,
                "price_delta_cents": 500,
            })
        else:
            factors.append({
                "factor": "confidence",
                "value": confidence,
                "price_delta_cents": 0,
            })

        min_price = max(499, int(round(base * 0.75 / 100)) * 100)
        max_price = max(base, int(round(base * 1.35 / 100)) * 100)
        return {
            "pricing_rule": f"{classification or 'UNKNOWN'}_{source.product_type.value}",
            "base_price_cents": base,
            "min_price_cents": min_price,
            "max_price_cents": max_price,
            "classification": classification or None,
            "product_type": source.product_type.value,
            "confidence": confidence,
            "tags": list(source.tags),
            "themes": list(source.themes),
            "sexual_intensity": source.intensity,
            "factors": factors,
            "explanation": (
                f"{classification or 'UNKNOWN'} {source.product_type.value} pricing "
                f"with {source.intensity or 'no'} sexual-intensity adjustment "
                f"and confidence {confidence:.2f}."
            ),
        }

    @staticmethod
    def _price_band_for_source(source: ProductDraftSource) -> dict:
        if (
            source.base_price_cents is not None
            and source.min_price_cents is not None
            and source.max_price_cents is not None
        ):
            return {
                "base_price_cents": source.base_price_cents,
                "min_price_cents": source.min_price_cents,
                "max_price_cents": source.max_price_cents,
            }

        decision = AIProductDraftingService.pricing_decision_for_source(source)
        return {
            "base_price_cents": decision["base_price_cents"],
            "min_price_cents": decision["min_price_cents"],
            "max_price_cents": decision["max_price_cents"],
        }

    @staticmethod
    def _commerce_price_band(commerce_recommendation: Any | None) -> dict | None:
        price = getattr(commerce_recommendation, "price", None)
        if not price:
            return None
        required = (
            "suggested_price_cents",
            "min_price_cents",
            "max_price_cents",
        )
        if any(getattr(price, field, None) is None for field in required):
            return None
        return {
            "base_price_cents": int(price.suggested_price_cents),
            "min_price_cents": int(price.min_price_cents),
            "max_price_cents": int(price.max_price_cents),
        }

    @staticmethod
    def _commerce_metadata(commerce_recommendation: Any | None) -> dict:
        if commerce_recommendation is None:
            return {}
        price = getattr(commerce_recommendation, "price", None)
        publishing = getattr(commerce_recommendation, "publishing", None)
        recommendation_metadata = getattr(commerce_recommendation, "metadata", {}) or {}
        experience_intelligence = recommendation_metadata.get(
            "experience_intelligence"
        )
        return {
            "commerce_intelligence": {
                "source_type": getattr(commerce_recommendation, "source_type", None),
                "source_id": getattr(commerce_recommendation, "source_id", None),
                "product_type": getattr(
                    getattr(commerce_recommendation, "product_type", None),
                    "value",
                    getattr(commerce_recommendation, "product_type", None),
                ),
                "delivery_type": getattr(
                    getattr(commerce_recommendation, "delivery_type", None),
                    "value",
                    getattr(commerce_recommendation, "delivery_type", None),
                ),
                "suggested_keywords": list(
                    getattr(commerce_recommendation, "suggested_keywords", ())
                    or ()
                ),
                "confidence": getattr(commerce_recommendation, "confidence", None),
                "price": {
                    "suggested_price_cents": getattr(
                        price,
                        "suggested_price_cents",
                        None,
                    ),
                    "min_price_cents": getattr(price, "min_price_cents", None),
                    "max_price_cents": getattr(price, "max_price_cents", None),
                    "pricing_rule": getattr(price, "pricing_rule", None),
                }
                if price
                else None,
                "publishing": {
                    "status": getattr(publishing, "status", None),
                    "action": getattr(publishing, "action", None),
                    "reason": getattr(publishing, "reason", None),
                }
                if publishing
                else None,
                "experience_intelligence": experience_intelligence,
            }
        }

    @staticmethod
    def _experience_intelligence_from_commerce(
        commerce_recommendation: Any | None,
    ) -> dict:
        metadata = getattr(commerce_recommendation, "metadata", {}) or {}
        intelligence = metadata.get("experience_intelligence")
        return dict(intelligence or {})

    @classmethod
    def _experience_projection_metadata(
        cls,
        experience: Any | None,
        *,
        commerce_recommendation: Any | None = None,
    ) -> dict:
        if experience is None:
            return {}
        experience_metadata = dict(getattr(experience, "metadata", {}) or {})
        commerce_intelligence = cls._experience_intelligence_from_commerce(
            commerce_recommendation
        )
        nested_commerce = experience_metadata.get("commerce_intelligence") or {}
        metadata_intelligence = (
            experience_metadata.get("experience_intelligence")
            or (nested_commerce or {}).get("experience_intelligence")
            or {}
        )
        experience_intelligence = {
            **dict(metadata_intelligence or {}),
            **commerce_intelligence,
        }
        experience_type = getattr(experience, "experience_type", None)
        experience_id = getattr(experience, "experience_id", None)
        projection = {
            "experience_id": str(experience_id) if experience_id else None,
            "experience_type": getattr(
                experience_type,
                "value",
                experience_type,
            ),
            "experience_name": getattr(experience, "title", None),
            "experience_summary": getattr(experience, "description", None),
            "experience_cover_asset_id": getattr(
                experience,
                "cover_asset_id",
                None,
            ),
            "experience_metadata": experience_metadata,
            "experience_intelligence": experience_intelligence,
        }
        if experience_intelligence:
            projection.update(
                {
                    "experience_themes": tuple(
                        experience_intelligence.get("suggested_themes") or ()
                    ),
                    "experience_keywords": tuple(
                        experience_intelligence.get("suggested_keywords") or ()
                    ),
                    "experience_mood": experience_intelligence.get("mood"),
                    "experience_story_progression": dict(
                        experience_intelligence.get("story_progression") or {}
                    ),
                    "experience_technical_continuity": dict(
                        experience_intelligence.get("technical_continuity") or {}
                    ),
                    "experience_provenance": dict(
                        experience_intelligence.get("intelligence_provenance")
                        or {}
                    ),
                }
            )
        return {
            key: value
            for key, value in projection.items()
            if value is not None
        }

    @classmethod
    def _activation_errors(cls, product: Product, asset: Asset) -> list[str]:
        errors = []
        try:
            confidence = float(asset.confidence or 0)
        except (TypeError, ValueError):
            confidence = 0
        if confidence < cls.CONFIDENCE_THRESHOLD:
            errors.append(
                f"confidence {confidence:.2f} below threshold {cls.CONFIDENCE_THRESHOLD:.2f}"
            )
        if not asset.classification:
            errors.append("classification missing")
        if not product.tags:
            errors.append("tags missing")
        if not product.themes:
            errors.append("themes missing")
        if not product.product_type:
            errors.append("product type missing")
        return errors

    @classmethod
    def _activation_errors_for_source(
        cls,
        product: Product,
        source: ProductDraftSource,
    ) -> list[str]:
        errors = []
        confidence = float(source.confidence or 0)
        if confidence < cls.CONFIDENCE_THRESHOLD:
            errors.append(
                f"confidence {confidence:.2f} below threshold {cls.CONFIDENCE_THRESHOLD:.2f}"
            )
        if not source.classification:
            errors.append("classification missing")
        if not product.tags:
            errors.append("tags missing")
        if not product.themes:
            errors.append("themes missing")
        if not product.product_type:
            errors.append("product type missing")
        return errors

    @staticmethod
    def _activation_blocker_metadata(
        product: Product,
        errors: list[str],
        *,
        source_metadata: dict | None = None,
    ) -> dict:
        return {
            **dict(product.metadata or {}),
            **dict(source_metadata or {}),
            "activation_source": "ai_auto_activation",
            "activation_eligible": False,
            "activation_blockers": errors,
        }

    @staticmethod
    def _activation_success_metadata(
        product: Product,
        *,
        reason: str,
        prices: dict,
        source_metadata: dict | None = None,
    ) -> dict:
        return {
            **dict(product.metadata or {}),
            **dict(source_metadata or {}),
            "activation_source": "ai_auto_activation",
            "activation_eligible": True,
            "activation_reason": reason,
            "pricing": {
                "source": "ai_rule_based_pricing",
                **prices,
            },
        }

    def _activate_product_with_prices(
        self,
        *,
        product: Product,
        creator_profile_id: int,
        prices: dict,
        media_link: str,
        reason: str,
        metadata: dict,
    ) -> Product | None:
        return self.products.activate_ai_product(
            product_id=product.id,
            creator_profile_id=creator_profile_id,
            base_price_cents=prices["base_price_cents"],
            min_price_cents=prices["min_price_cents"],
            max_price_cents=prices["max_price_cents"],
            media_link=media_link,
            activation_source="ai_auto_activation",
            activation_reason=reason,
            metadata=metadata,
            delivery_type=product.delivery_type,
        )

    def _auto_activate_if_eligible(
        self,
        *,
        product: Product,
        asset: Asset,
        source: ProductDraftSource,
        creator_profile_id: int,
    ) -> tuple[Product, bool, str | None]:
        if product.status != ProductStatus.DRAFT:
            return product, False, "not_draft"
        metadata = product.metadata or {}
        if not (
            metadata.get("ai_product_draft") is True
            and metadata.get("draft_source") == "ai_cms_asset"
        ):
            return product, False, "creator_edits_preserved"

        errors = self._activation_errors_for_source(product, source)
        if errors:
            metadata = self._activation_blocker_metadata(product, errors)
            updated = self.products.apply_ai_draft_fields(
                product_id=product.id,
                creator_profile_id=creator_profile_id,
                display_name=product.display_name,
                description=product.description,
                product_type=product.product_type,
                tags=product.tags,
                themes=product.themes,
                metadata=metadata,
            )
            return updated or product, False, "; ".join(errors)

        prices = self._price_band_for_source(source)
        reason = (
            "AI auto-activated: confidence threshold met; classification, "
            "tags, themes, and product type are present."
        )
        metadata = self._activation_success_metadata(
            product,
            reason=reason,
            prices=prices,
        )
        activated = self._activate_product_with_prices(
            product=product,
            creator_profile_id=creator_profile_id,
            prices=prices,
            media_link=f"local://content_items/{asset.id}",
            reason=reason,
            metadata=metadata,
        )
        return activated or product, activated is not None, None

    def _mapped_values(self, asset: Asset) -> dict:
        return self._mapped_values_from_source(
            self._draft_source_for_asset(asset),
            metadata=self._metadata(asset),
        )

    def _draft_source_for_asset(
        self,
        asset: Asset,
        commerce_recommendation: Any | None = None,
    ) -> ProductDraftSource:
        product_type = (
            getattr(commerce_recommendation, "product_type", None)
            or self._infer_product_type(asset)
        )
        prices = (
            self._commerce_price_band(commerce_recommendation)
            or self._price_band_for_asset(asset, product_type)
        )
        return ProductDraftSource(
            source_id=str(asset.id),
            source_type="asset",
            product_type=product_type,
            delivery_type=getattr(commerce_recommendation, "delivery_type", None),
            suggested_title=(
                getattr(commerce_recommendation, "suggested_name", None)
                or self._humanize_filename(asset)
            ),
            suggested_description=(
                getattr(commerce_recommendation, "suggested_description", None)
                or (asset.summary or "").strip()
                or None
            ),
            suggested_price_cents=prices["base_price_cents"],
            base_price_cents=prices["base_price_cents"],
            min_price_cents=prices["min_price_cents"],
            max_price_cents=prices["max_price_cents"],
            tags=(
                getattr(commerce_recommendation, "suggested_tags", None)
                or asset.suggested_tags
            ),
            themes=(
                getattr(commerce_recommendation, "suggested_themes", None)
                or asset.detected_themes
            ),
            asset_ids=(asset.id,),
            classification=(
                (getattr(commerce_recommendation, "metadata", {}) or {}).get(
                    "classification"
                )
                if commerce_recommendation
                else None
            )
            or asset.classification,
            confidence=(
                getattr(commerce_recommendation, "confidence", None)
                if commerce_recommendation
                else None
            )
            or asset.confidence,
            intensity=asset.sexual_intensity,
            metadata={
                "legacy_content_item_id": asset.id,
                "source_asset_id": asset.id,
                "delivery_type_explicit": (
                    commerce_recommendation is not None
                    and getattr(commerce_recommendation, "delivery_type", None)
                    is not None
                ),
            },
        )

    def _draft_source_for_photo_set(
        self,
        aggregate: Asset,
        ordered_asset_ids: list[int],
        *,
        display_name: str,
        commerce_recommendation: Any | None = None,
    ) -> ProductDraftSource:
        product_type = (
            getattr(commerce_recommendation, "product_type", None)
            or ProductType.PHOTO_SET
        )
        prices = (
            self._commerce_price_band(commerce_recommendation)
            or self._price_band_for_asset(aggregate, product_type)
        )
        return ProductDraftSource(
            source_id=str(ordered_asset_ids[0]),
            source_type="photoshoot",
            product_type=product_type,
            delivery_type=getattr(commerce_recommendation, "delivery_type", None),
            suggested_title=(
                getattr(commerce_recommendation, "suggested_name", None)
                or display_name
            ),
            suggested_description=(
                getattr(commerce_recommendation, "suggested_description", None)
                or aggregate.summary
            ),
            suggested_price_cents=prices["base_price_cents"],
            base_price_cents=prices["base_price_cents"],
            min_price_cents=prices["min_price_cents"],
            max_price_cents=prices["max_price_cents"],
            tags=(
                getattr(commerce_recommendation, "suggested_tags", None)
                or aggregate.suggested_tags
            ),
            themes=(
                getattr(commerce_recommendation, "suggested_themes", None)
                or aggregate.detected_themes
            ),
            asset_ids=tuple(ordered_asset_ids),
            classification=(
                (getattr(commerce_recommendation, "metadata", {}) or {}).get(
                    "classification"
                )
                if commerce_recommendation
                else None
            )
            or aggregate.classification,
            confidence=(
                getattr(commerce_recommendation, "confidence", None)
                if commerce_recommendation
                else None
            )
            or aggregate.confidence,
            intensity=aggregate.sexual_intensity,
            metadata={
                "legacy_content_item_id": ordered_asset_ids[0],
                "source_asset_ids": list(ordered_asset_ids),
                "asset_count": len(ordered_asset_ids),
                "delivery_type_explicit": (
                    commerce_recommendation is not None
                    and getattr(commerce_recommendation, "delivery_type", None)
                    is not None
                ),
            },
        )

    def _mapped_values_from_source(
        self,
        source: ProductDraftSource,
        *,
        metadata: dict,
    ) -> dict:
        prefix = "photo-set" if source.source_type == "photoshoot" else "asset"
        if source.source_type == "photoshoot":
            internal_name = (
                f"photo-set-{source.asset_ids[0]}-"
                f"{len(source.asset_ids)}-assets"
            )
        else:
            internal_name = (
                f"{prefix}-{source.source_id}-"
                f"{self._slug(source.suggested_title)}"
            )
        return {
            "internal_name": internal_name,
            "display_name": source.suggested_title,
            "description": source.suggested_description,
            "product_type": source.product_type,
            "delivery_type": source.delivery_type,
            "delivery_type_explicit": bool(
                (source.metadata or {}).get("delivery_type_explicit")
            ),
            "tags": source.tags,
            "themes": source.themes,
            "metadata": metadata,
        }

    @staticmethod
    def _should_ai_refresh(product: Product) -> bool:
        metadata = product.metadata or {}
        return (
            product.status == ProductStatus.DRAFT
            and (
                metadata.get("ai_product_draft") is True
                or metadata.get("draft_source") == "ai_cms_asset"
                or metadata.get("backfill_source") == "content_items"
            )
        )

    @staticmethod
    def _preserve_creator_edits(product: Product, mapped: dict) -> dict:
        if not AIProductDraftingService._should_ai_refresh(product):
            return {
                "display_name": product.display_name,
                "description": product.description,
                "product_type": product.product_type,
                "delivery_type": product.delivery_type,
                "tags": product.tags,
                "themes": product.themes,
                "metadata": {
                    **dict(product.metadata or {}),
                    **mapped["metadata"],
                    "ai_product_draft": bool(
                        (product.metadata or {}).get("ai_product_draft")
                    ),
                    "last_ai_refresh_skipped": "creator_edits_preserved",
                },
            }

        return {
            "display_name": product.display_name or mapped["display_name"],
            "description": mapped["description"] if not product.description else product.description,
            "product_type": (
                mapped["product_type"]
                if product.product_type == ProductType.CUSTOM
                or (product.metadata or {}).get("backfill_source") == "content_items"
                else product.product_type
            ),
            "delivery_type": (
                mapped["delivery_type"]
                if mapped.get("delivery_type_explicit")
                else product.delivery_type
            ),
            "tags": mapped["tags"] if not product.tags else product.tags,
            "themes": mapped["themes"] if not product.themes else product.themes,
            "metadata": {
                **dict(product.metadata or {}),
                **mapped["metadata"],
                "ai_product_draft": True,
            },
        }

    @staticmethod
    def _assert_eligible(asset: Asset) -> None:
        if asset.status != "approved":
            raise AIProductDraftingNotEligibleError(
                f"Asset {asset.id} is not approved."
            )

    def create_or_refresh_draft_for_asset(
        self,
        asset_id: int,
        *,
        creator_profile_id: int,
        commerce_recommendation: Any | None = None,
    ) -> AIProductDraftResult:
        # A.2 compatibility boundary: AI Product Drafting is Product lifecycle
        # work, so it still needs the broad Asset model for analysis metadata,
        # product-type inference, pricing inputs, and source composition.
        # Do not switch this to get_asset_owned_row until Product Draft inputs
        # are represented by an explicit Product/Experience contract.
        asset = self.assets.get_by_id(asset_id)
        if not asset:
            raise AIProductDraftingError(f"Asset {asset_id} was not found.")
        self._assert_eligible(asset)

        source = self._draft_source_for_asset(
            asset,
            commerce_recommendation=commerce_recommendation,
        )
        mapped = self._mapped_values_from_source(
            source,
            metadata={
                **self._metadata(asset),
                **self._commerce_metadata(commerce_recommendation),
            },
        )
        experience = self.experiences.build_standalone_experience(
            asset,
            title=mapped["display_name"],
            description=mapped["description"],
            metadata=mapped["metadata"],
        )
        mapped["metadata"] = {
            **mapped["metadata"],
            **self._experience_projection_metadata(
                experience,
                commerce_recommendation=commerce_recommendation,
            ),
        }
        product, created = self.products.create_ai_draft_product(
            asset=asset,
            creator_profile_id=creator_profile_id,
            internal_name=mapped["internal_name"],
            display_name=mapped["display_name"],
            description=mapped["description"],
            product_type=mapped["product_type"],
            delivery_type=mapped["delivery_type"],
            tags=mapped["tags"],
            themes=mapped["themes"],
            metadata=mapped["metadata"],
        )

        updated = False
        if not created:
            if product.creator_profile_id is None:
                assigned = self.products.assign_to_creator(
                    product.id,
                    creator_profile_id,
                )
                if assigned:
                    product = assigned
            if product.creator_profile_id != creator_profile_id:
                raise AIProductDraftingError(
                    "Source asset is already linked to a product for a "
                    "different creator profile."
                )
            if product.creator_profile_id == creator_profile_id:
                refreshed = self._preserve_creator_edits(product, mapped)
                updated_product = self.products.apply_ai_draft_fields(
                    product_id=product.id,
                    creator_profile_id=creator_profile_id,
                    display_name=refreshed["display_name"],
                    description=refreshed["description"],
                    product_type=refreshed["product_type"],
                    delivery_type=refreshed["delivery_type"],
                    tags=refreshed["tags"],
                    themes=refreshed["themes"],
                    metadata=refreshed["metadata"],
                )
                if updated_product:
                    updated = updated_product != product
                    product = updated_product

        _, link_created = self.experiences.attach_primary_product_experience_asset(
            product.id,
            asset.id,
        )
        product, activated, skipped_reason = self._auto_activate_if_eligible(
            product=product,
            asset=asset,
            source=source,
            creator_profile_id=creator_profile_id,
        )
        return AIProductDraftResult(
            product=product,
            created=created,
            updated=updated,
            product_asset_created=link_created,
            activated=activated,
            skipped_reason=skipped_reason,
        )

    def create_draft_result_for_asset(
        self,
        asset_id: int | None,
        *,
        creator_profile_id: int | None,
        commerce_recommendation: Any | None = None,
    ) -> dict:
        if not asset_id or not creator_profile_id:
            return {
                "success": False,
                "created": False,
                "reason": "missing_content_or_creator_profile",
            }

        try:
            try:
                result = self.create_or_refresh_draft_for_asset(
                    asset_id,
                    creator_profile_id=creator_profile_id,
                    commerce_recommendation=commerce_recommendation,
                )
            except TypeError:
                result = self.create_or_refresh_draft_for_asset(
                    asset_id,
                    creator_profile_id=creator_profile_id,
                )
            return {
                "success": True,
                "created": result.created,
                "updated": result.updated,
                "product_id": str(result.product.id),
                "product_type": result.product.product_type.value,
                "delivery_type": result.product.delivery_type.value,
                "status": result.product.status.value,
                "price_cents": result.product.price_cents,
                "base_price_cents": result.product.base_price_cents,
                "min_price_cents": result.product.min_price_cents,
                "max_price_cents": result.product.max_price_cents,
                "activated": result.activated,
            }
        except Exception as error:
            return {
                "success": False,
                "created": False,
                "error": str(error),
            }

    def refresh_existing_product_from_asset(
        self,
        product: Product,
        *,
        creator_profile_id: int,
        commerce_recommendation: Any | None = None,
    ) -> AIProductDraftResult:
        if product.legacy_content_item_id is None:
            raise AIProductDraftingError("Product has no source CMS asset.")
        return self.create_or_refresh_draft_for_asset(
            product.legacy_content_item_id,
            creator_profile_id=creator_profile_id,
            commerce_recommendation=commerce_recommendation,
        )

    def create_photo_set_for_assets(
        self,
        asset_ids: list[int],
        *,
        creator_profile_id: int,
        commerce_recommendation: Any | None = None,
    ) -> AIProductDraftResult:
        # A.4 compatibility: construct the Experience contract first, while
        # preserving existing Product/ProductAsset persistence behavior.
        ordered_asset_ids = [int(asset_id) for asset_id in asset_ids]
        if len(ordered_asset_ids) < 2:
            raise AIProductDraftingError(
                "PHOTO_SET requires at least two assets."
            )

        assets = []
        for asset_id in ordered_asset_ids:
            # A.2 compatibility boundary: Photo Set creation is Product/
            # Experience composition, not a pure Asset read. Keep the broad
            # Asset compatibility model until Experiences own grouping.
            asset = self.assets.get_by_id(asset_id)
            if not asset:
                raise AIProductDraftingError(f"Asset {asset_id} was not found.")
            self._assert_eligible(asset)
            if asset.media_type != "image":
                raise AIProductDraftingError(
                    f"PHOTO_SET asset {asset_id} is not an image."
                )
            assets.append(asset)

        aggregate = self._aggregate_photo_set_asset(assets)
        display_name = f"Photo Set - {self._humanize_filename(assets[0])}"
        source = self._draft_source_for_photo_set(
            aggregate,
            ordered_asset_ids,
            display_name=display_name,
            commerce_recommendation=commerce_recommendation,
        )
        metadata = {
            **self._metadata(aggregate),
            **self._commerce_metadata(commerce_recommendation),
            "draft_source": "ai_cms_photo_set",
            "ai_product_draft": True,
            "product_structure": "photo_set",
            "source_asset_ids": ordered_asset_ids,
            "legacy_content_item_id": ordered_asset_ids[0],
            "asset_count": len(ordered_asset_ids),
        }
        experience = self.experiences.build_photoshoot_experience(
            assets,
            title=source.suggested_title,
            description=source.suggested_description,
            metadata=metadata,
            cover_asset_id=ordered_asset_ids[0],
            asset_order=ordered_asset_ids,
        )
        metadata = {
            **metadata,
            **self._experience_projection_metadata(
                experience,
                commerce_recommendation=commerce_recommendation,
            ),
        }

        mapped = self._mapped_values_from_source(
            source,
            metadata=metadata,
        )
        product, created = self.products.create_ai_draft_product(
            asset=aggregate,
            creator_profile_id=creator_profile_id,
            internal_name=mapped["internal_name"],
            display_name=mapped["display_name"],
            description=mapped["description"],
            product_type=mapped["product_type"],
            delivery_type=mapped["delivery_type"],
            tags=mapped["tags"],
            themes=mapped["themes"],
            metadata=metadata,
        )

        links = self.experiences.replace_product_experience_assets(
            product.id,
            ordered_asset_ids,
        )

        errors = self._activation_errors_for_source(product, source)
        if errors:
            metadata = self._activation_blocker_metadata(
                product,
                errors,
                source_metadata=metadata,
            )
            updated = self.products.apply_ai_draft_fields(
                product_id=product.id,
                creator_profile_id=creator_profile_id,
                display_name=product.display_name,
                description=product.description,
                product_type=source.product_type,
                delivery_type=product.delivery_type,
                tags=product.tags,
                themes=product.themes,
                metadata=metadata,
            )
            return AIProductDraftResult(
                product=updated or product,
                created=created,
                updated=updated is not None,
                product_asset_created=bool(links),
                activated=False,
                skipped_reason="; ".join(errors),
            )

        prices = self._price_band_for_source(source)
        reason = (
            "AI auto-activated PHOTO_SET: confidence threshold met; "
            "classification, tags, themes, product type, and ordered assets "
            "are present."
        )
        activation_metadata = self._activation_success_metadata(
            product,
            reason=reason,
            prices=prices,
            source_metadata=metadata,
        )
        activated_product = self._activate_product_with_prices(
            product=product,
            creator_profile_id=creator_profile_id,
            prices=prices,
            media_link=f"local://products/{product.id}",
            reason=reason,
            metadata=activation_metadata,
        )

        return AIProductDraftResult(
            product=activated_product or product,
            created=created,
            updated=False,
            product_asset_created=bool(links),
            activated=activated_product is not None,
            skipped_reason=None if activated_product else "activation_failed",
        )
