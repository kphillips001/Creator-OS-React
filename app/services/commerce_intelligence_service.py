"""Recommend commerce treatment for imported Assets and Experiences."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.models.commerce_intelligence import (
    CommerceIntelligenceEvidence,
    CommercePriceRecommendation,
    CommerceRecommendation,
    PublishingReadinessRecommendation,
)
from app.models.experience import ExperienceType
from app.models.product import ProductDeliveryType, ProductType


class CommerceIntelligenceService:
    """Build commerce recommendations without creating Product records."""

    def recommend(
        self,
        *,
        asset_understanding: Any | None = None,
        asset_understandings: Iterable[Any] | None = None,
        experience_recommendation: Any | None = None,
    ) -> CommerceRecommendation | None:
        understandings = self._normalize_understandings(
            asset_understanding,
            asset_understandings,
        )
        if not understandings:
            return None

        product_type = self._product_type(
            understandings,
            experience_recommendation,
        )
        classification = self._highest_classification(understandings)
        intensity = self._highest_intensity(understandings)
        confidence = self._average_confidence(understandings)
        tags = self._dedupe(
            tag
            for item in understandings
            for tag in item.visual.suggested_tags
        )
        experience_themes = self._experience_tuple(
            experience_recommendation,
            "suggested_themes",
        )
        themes = experience_themes or self._dedupe(
            theme
            for item in understandings
            for theme in item.visual.detected_themes
        )
        experience_keywords = self._experience_tuple(
            experience_recommendation,
            "suggested_keywords",
        )
        keywords = experience_keywords or self._keywords(
            understandings,
            tags=tags,
            themes=themes,
            product_type=product_type,
        )
        delivery_type, delivery_context = self._delivery_type_recommendation(
            understandings=understandings,
            experience_recommendation=experience_recommendation,
            product_type=product_type,
            classification=classification,
            intensity=intensity,
            tags=tags,
            themes=themes,
        )
        price = self._price_recommendation_for_delivery_type(
            delivery_type=delivery_type,
            classification=classification,
            product_type=product_type,
            intensity=intensity,
            confidence=confidence,
        )
        evidence = self._evidence(
            understandings=understandings,
            experience_recommendation=experience_recommendation,
            product_type=product_type,
            classification=classification,
            intensity=intensity,
            confidence=confidence,
            delivery_type=delivery_type,
            delivery_context=delivery_context,
        )
        asset_ids = tuple(item.identity.asset_id for item in understandings)
        source_type = (
            "experience"
            if experience_recommendation
            and getattr(experience_recommendation, "is_collection", False)
            else "asset"
        )

        return CommerceRecommendation(
            source_type=source_type,
            source_id=self._source_id(asset_ids, source_type),
            asset_ids=asset_ids,
            product_type=product_type,
            delivery_type=delivery_type,
            suggested_name=self._suggested_name(
                understandings,
                experience_recommendation,
                product_type,
            ),
            suggested_description=self._suggested_description(
                understandings,
                experience_recommendation,
            ),
            suggested_tags=tags,
            suggested_themes=themes,
            suggested_keywords=keywords,
            price=price,
            publishing=self._publishing_readiness(understandings),
            confidence=round(min(0.95, max(0.2, confidence or 0.5)), 2),
            evidence=evidence,
            metadata={
                "source": "commerce_intelligence",
                "classification": classification,
                "sexual_intensity": intensity,
                "delivery_type": delivery_type.value,
                "delivery_type_rule": delivery_context["rule"],
                "delivery_type_rationale": delivery_context["rationale"],
                "delivery_type_scores": {
                    "free": delivery_context["free_score"],
                    "paid": delivery_context["paid_score"],
                },
                "delivery_type_factors": delivery_context["factors"],
                "experience_type": self._experience_type_value(
                    experience_recommendation
                ),
                "experience_intelligence": self._experience_intelligence_metadata(
                    experience_recommendation
                ),
            },
        )

    @classmethod
    def _normalize_understandings(
        cls,
        asset_understanding: Any | None,
        asset_understandings: Iterable[Any] | None,
    ) -> tuple[Any, ...]:
        values = []
        if asset_understanding is not None:
            values.append(cls._content_intelligence_view(asset_understanding))
        if asset_understandings is not None:
            values.extend(
                cls._content_intelligence_view(item)
                for item in asset_understandings
                if item is not None
            )
        return tuple(values)

    @staticmethod
    def _content_intelligence_view(item: Any) -> Any:
        view = getattr(item, "to_asset_understanding_view", None)
        if callable(view):
            return view()
        return item

    def _product_type(
        self,
        understandings: tuple[Any, ...],
        experience_recommendation: Any | None,
    ) -> ProductType:
        experience_type = self._experience_type_value(experience_recommendation)
        if experience_type == ExperienceType.STORY.value:
            return ProductType.STORY
        if experience_type == ExperienceType.PHOTOSHOOT.value:
            media_types = {item.media.media_type for item in understandings}
            if media_types == {"video"}:
                return ProductType.VIDEO_SET
            return ProductType.PHOTO_SET

        if len(understandings) > 1:
            media_types = {item.media.media_type for item in understandings}
            if media_types == {"video"}:
                return ProductType.VIDEO_SET
            return ProductType.PHOTO_SET

        media_type = understandings[0].media.media_type
        if media_type == "video":
            return ProductType.SINGLE_VIDEO
        if media_type == "image":
            return ProductType.SINGLE_IMAGE
        return ProductType.CUSTOM

    @staticmethod
    def _experience_type_value(experience_recommendation: Any | None) -> str | None:
        if not experience_recommendation:
            return None
        experience_type = getattr(experience_recommendation, "experience_type", None)
        return getattr(experience_type, "value", str(experience_type))

    @staticmethod
    def _highest_classification(understandings: tuple[Any, ...]) -> str | None:
        rank = {"EDGE_CASE": 0, "TEASE": 1, "VIP": 2, "PREMIUM": 3}
        values = [
            str(item.classification.final_classification or "").upper()
            for item in understandings
            if item.classification.final_classification
        ]
        if not values:
            return None
        return max(values, key=lambda value: rank.get(value, 0))

    @staticmethod
    def _highest_intensity(understandings: tuple[Any, ...]) -> str | None:
        rank = {None: 0, "low": 1, "medium": 2, "high": 3}
        values = [item.safety.sexual_intensity for item in understandings]
        return max(values, key=lambda value: rank.get(value, 0))

    @staticmethod
    def _average_confidence(understandings: tuple[Any, ...]) -> float | None:
        values = [
            float(item.classification.confidence)
            for item in understandings
            if item.classification.confidence is not None
        ]
        if not values:
            return None
        return sum(values) / len(values)

    @staticmethod
    def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
        seen = set()
        result = []
        for value in values:
            clean = str(value).strip()
            if not clean:
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(clean)
        return tuple(result)

    @classmethod
    def _experience_tuple(
        cls,
        experience_recommendation: Any | None,
        name: str,
    ) -> tuple[str, ...]:
        values = getattr(experience_recommendation, name, None)
        if not values:
            return ()
        return cls._dedupe(values)

    @staticmethod
    def _experience_intelligence_metadata(
        experience_recommendation: Any | None,
    ) -> dict[str, Any] | None:
        if not experience_recommendation:
            return None
        metadata = {
            "suggested_themes": tuple(
                getattr(experience_recommendation, "suggested_themes", ()) or ()
            ),
            "suggested_keywords": tuple(
                getattr(experience_recommendation, "suggested_keywords", ()) or ()
            ),
            "mood": getattr(experience_recommendation, "mood", None),
            "setting": getattr(experience_recommendation, "setting", None),
            "visual_continuity": dict(
                getattr(experience_recommendation, "visual_continuity", {}) or {}
            ),
            "story_progression": dict(
                getattr(experience_recommendation, "story_progression", {}) or {}
            ),
            "technical_continuity": dict(
                getattr(experience_recommendation, "technical_continuity", {}) or {}
            ),
            "intelligence_metadata": dict(
                getattr(experience_recommendation, "intelligence_metadata", {}) or {}
            ),
            "intelligence_provenance": dict(
                getattr(experience_recommendation, "intelligence_provenance", {})
                or {}
            ),
        }
        return {key: value for key, value in metadata.items() if value}

    def _keywords(
        self,
        understandings: tuple[Any, ...],
        *,
        tags: tuple[str, ...],
        themes: tuple[str, ...],
        product_type: ProductType,
    ) -> tuple[str, ...]:
        values = list(tags) + list(themes) + [product_type.value.lower()]
        for item in understandings:
            for value in (
                item.visual.setting,
                item.visual.outfit,
                item.visual.mood,
                item.visual.activity,
                item.classification.final_classification,
                item.safety.sexual_intensity,
            ):
                if value:
                    values.append(value)
        return self._dedupe(values)

    @staticmethod
    def _price_recommendation(
        *,
        classification: str | None,
        product_type: ProductType,
        intensity: str | None,
        confidence: float | None,
    ) -> CommercePriceRecommendation:
        classification = (classification or "").upper()
        base = {
            "TEASE": 999,
            "VIP": 2499,
            "PREMIUM": 4999,
        }.get(classification, 1999)
        if product_type == ProductType.SINGLE_VIDEO:
            base += 1000
        elif product_type in {ProductType.PHOTO_SET, ProductType.VIDEO_SET}:
            base += 1500
        elif product_type in {ProductType.STORY, ProductType.SESSION}:
            base += 2500
        elif product_type == ProductType.BUNDLE:
            base += 3500
        if intensity == "high":
            base += 1000
        elif intensity == "medium":
            base += 500
        if confidence is not None and confidence >= 0.95:
            base += 500
        min_price = max(499, int(round(base * 0.75 / 100)) * 100)
        max_price = max(base, int(round(base * 1.35 / 100)) * 100)
        return CommercePriceRecommendation(
            suggested_price_cents=base,
            min_price_cents=min_price,
            max_price_cents=max_price,
            pricing_rule=f"{classification or 'UNKNOWN'}_{product_type.value}",
        )

    def _price_recommendation_for_delivery_type(
        self,
        *,
        delivery_type: ProductDeliveryType,
        classification: str | None,
        product_type: ProductType,
        intensity: str | None,
        confidence: float | None,
    ) -> CommercePriceRecommendation:
        if delivery_type == ProductDeliveryType.FREE:
            return CommercePriceRecommendation(
                suggested_price_cents=0,
                min_price_cents=0,
                max_price_cents=0,
                pricing_rule=f"FREE_{product_type.value}",
            )
        return self._price_recommendation(
            classification=classification,
            product_type=product_type,
            intensity=intensity,
            confidence=confidence,
        )

    def _delivery_type_recommendation(
        self,
        *,
        understandings: tuple[Any, ...],
        experience_recommendation: Any | None,
        product_type: ProductType,
        classification: str | None,
        intensity: str | None,
        tags: tuple[str, ...],
        themes: tuple[str, ...],
    ) -> tuple[ProductDeliveryType, dict[str, Any]]:
        paid_score = 0
        free_score = 0
        factors: list[str] = []
        classification = (classification or "").upper()
        intensity = (intensity or "").lower()

        if classification == "PREMIUM":
            paid_score += 60
            factors.append("premium_classification")
        elif classification == "VIP":
            paid_score += 25
            factors.append("vip_classification")
        elif classification == "TEASE":
            free_score += 45
            factors.append("tease_classification")

        if intensity == "high":
            paid_score += 50
            factors.append("high_sexual_intensity")
        elif intensity == "medium":
            paid_score += 20
            factors.append("medium_sexual_intensity")
        elif intensity == "low":
            free_score += 20
            factors.append("low_sexual_intensity")

        if product_type in {
            ProductType.PHOTO_SET,
            ProductType.VIDEO_SET,
            ProductType.STORY,
            ProductType.SESSION,
            ProductType.BUNDLE,
        }:
            paid_score += 25
            factors.append("premium_product_shape")
        elif product_type in {ProductType.SINGLE_IMAGE, ProductType.SINGLE_VIDEO}:
            free_score += 10
            factors.append("single_asset_preview_shape")

        explicit_signal = self._has_explicit_signal(understandings)
        if explicit_signal:
            paid_score += 60
            factors.append(explicit_signal)

        free_terms = {
            "safe",
            "tease",
            "teaser",
            "preview",
            "starter",
            "conversation",
            "relationship",
            "gfe",
            "progression",
            "intro",
        }
        paid_terms = {
            "premium",
            "vip",
            "ppv",
            "bundle",
            "exclusive",
            "explicit",
            "unlock",
            "gallery",
            "full set",
        }
        text = self._delivery_signal_text(
            understandings=understandings,
            experience_recommendation=experience_recommendation,
            tags=tags,
            themes=themes,
        )
        free_matches = sorted(term for term in free_terms if term in text)
        paid_matches = sorted(term for term in paid_terms if term in text)
        if free_matches:
            free_score += 20
            factors.append(f"free_terms:{','.join(free_matches)}")
        if paid_matches:
            paid_score += 25
            factors.append(f"paid_terms:{','.join(paid_matches)}")

        if paid_score > free_score:
            delivery_type = ProductDeliveryType.PAID
            rule = "paid_score_exceeded_free_score"
        else:
            delivery_type = ProductDeliveryType.FREE
            rule = "free_score_met_or_exceeded_paid_score"

        rationale = (
            "Recommended PAID because premium, explicit, bundled, or high-intent "
            "signals outweighed preview/relationship-building signals."
            if delivery_type == ProductDeliveryType.PAID
            else "Recommended FREE because preview, safe, teaser, or "
            "relationship-building signals met or exceeded paid signals."
        )
        return delivery_type, {
            "rule": rule,
            "rationale": rationale,
            "free_score": free_score,
            "paid_score": paid_score,
            "factors": tuple(factors),
        }

    @staticmethod
    def _delivery_signal_text(
        *,
        understandings: tuple[Any, ...],
        experience_recommendation: Any | None,
        tags: tuple[str, ...],
        themes: tuple[str, ...],
    ) -> str:
        values: list[str] = list(tags) + list(themes)
        if experience_recommendation:
            values.extend(
                str(value)
                for value in (
                    getattr(experience_recommendation, "suggested_name", None),
                    getattr(experience_recommendation, "suggested_summary", None),
                    getattr(experience_recommendation, "mood", None),
                    getattr(experience_recommendation, "setting", None),
                )
                if value
            )
            values.extend(
                str(value)
                for value in (
                    getattr(experience_recommendation, "suggested_keywords", ())
                    or ()
                )
                if value
            )
        for item in understandings:
            visual = getattr(item, "visual", None)
            classification = getattr(item, "classification", None)
            safety = getattr(item, "safety", None)
            values.extend(
                str(value)
                for value in (
                    getattr(visual, "summary", None),
                    getattr(visual, "setting", None),
                    getattr(visual, "outfit", None),
                    getattr(visual, "mood", None),
                    getattr(visual, "activity", None),
                    getattr(classification, "final_classification", None),
                    getattr(safety, "sexual_intensity", None),
                    getattr(safety, "nudity_level", None),
                )
                if value
            )
            risk_flags = getattr(safety, "risk_flags", ()) or ()
            values.extend(str(flag) for flag in risk_flags if flag)
        return " ".join(values).lower()

    @staticmethod
    def _has_explicit_signal(understandings: tuple[Any, ...]) -> str | None:
        explicit_terms = {
            "explicit",
            "nude",
            "nudity",
            "sexual",
            "adult",
            "unsafe",
            "nsfw",
        }
        for item in understandings:
            safety = getattr(item, "safety", None)
            if getattr(safety, "is_explicit", False):
                return "explicit_safety_flag"
            nudity_level = str(getattr(safety, "nudity_level", "") or "").lower()
            if any(term in nudity_level for term in explicit_terms):
                return "explicit_nudity_level"
            risk_flags = getattr(safety, "risk_flags", ()) or ()
            if any(
                any(term in str(flag).lower() for term in explicit_terms)
                for flag in risk_flags
            ):
                return "explicit_risk_flag"
        return None

    def _suggested_name(
        self,
        understandings: tuple[Any, ...],
        experience_recommendation: Any | None,
        product_type: ProductType,
    ) -> str:
        if experience_recommendation and getattr(
            experience_recommendation,
            "suggested_name",
            None,
        ):
            return experience_recommendation.suggested_name
        if len(understandings) == 1:
            identity = understandings[0].identity
            source_name = identity.original_filename or identity.file_name
            if source_name:
                return Path(str(source_name)).stem.replace("_", " ").replace("-", " ").title()
        tags = self._dedupe(
            tag
            for item in understandings
            for tag in item.visual.suggested_tags
        )
        if tags:
            return f"{tags[0].title()} {product_type.value.replace('_', ' ').title()}"
        return product_type.value.replace("_", " ").title()

    @staticmethod
    def _suggested_description(
        understandings: tuple[Any, ...],
        experience_recommendation: Any | None,
    ) -> str | None:
        if experience_recommendation and getattr(
            experience_recommendation,
            "suggested_summary",
            None,
        ):
            return experience_recommendation.suggested_summary
        summaries = [
            item.visual.summary
            for item in understandings
            if item.visual.summary
        ]
        if summaries:
            return summaries[0]
        if len(understandings) > 1:
            return f"Curated set containing {len(understandings)} assets."
        return None

    @staticmethod
    def _publishing_readiness(
        understandings: tuple[Any, ...],
    ) -> PublishingReadinessRecommendation:
        missing_media = [
            item.identity.asset_id
            for item in understandings
            if not item.readiness.has_runtime_media
        ]
        needs_review = [
            item.identity.asset_id
            for item in understandings
            if item.readiness.needs_review
        ]
        if missing_media:
            return PublishingReadinessRecommendation(
                status="requires_attention",
                action="resolve_media",
                reason=f"Missing runtime media for assets: {missing_media}",
            )
        if needs_review:
            return PublishingReadinessRecommendation(
                status="requires_review",
                action="review_asset_intelligence",
                reason=f"Review recommended for assets: {needs_review}",
            )
        return PublishingReadinessRecommendation(
            status="ready_for_draft",
            action="generate_product_draft",
            reason="Asset intelligence is sufficient for Product Draft creation.",
        )

    def _evidence(
        self,
        *,
        understandings: tuple[Any, ...],
        experience_recommendation: Any | None,
        product_type: ProductType,
        classification: str | None,
        intensity: str | None,
        confidence: float | None,
        delivery_type: ProductDeliveryType,
        delivery_context: dict[str, Any],
    ) -> tuple[CommerceIntelligenceEvidence, ...]:
        evidence = [
            CommerceIntelligenceEvidence(
                reason="product_type_recommendation",
                detail=product_type.value,
                weight=25,
            )
        ]
        if experience_recommendation:
            evidence.append(
                CommerceIntelligenceEvidence(
                    reason="experience_recommendation",
                    detail=getattr(
                        getattr(experience_recommendation, "experience_type", None),
                        "value",
                        None,
                    ),
                    weight=25,
                )
            )
        if classification:
            evidence.append(
                CommerceIntelligenceEvidence(
                    reason="classification",
                    detail=classification,
                    weight=20,
                )
            )
        if intensity:
            evidence.append(
                CommerceIntelligenceEvidence(
                    reason="sexual_intensity",
                    detail=intensity,
                    weight=10,
                )
            )
        evidence.append(
            CommerceIntelligenceEvidence(
                reason="delivery_type_recommendation",
                detail=delivery_type.value,
                weight=abs(
                    int(delivery_context["paid_score"])
                    - int(delivery_context["free_score"])
                ),
            )
        )
        evidence.append(
            CommerceIntelligenceEvidence(
                reason="delivery_type_rationale",
                detail=delivery_context["rationale"],
                weight=10,
            )
        )
        if confidence is not None:
            evidence.append(
                CommerceIntelligenceEvidence(
                    reason="average_confidence",
                    detail=f"{confidence:.2f}",
                    weight=10,
                )
            )
        media_counts = Counter(item.media.media_type for item in understandings)
        evidence.append(
            CommerceIntelligenceEvidence(
                reason="media_mix",
                detail=", ".join(
                    f"{media_type}:{count}"
                    for media_type, count in sorted(media_counts.items())
                ),
                weight=10,
            )
        )
        return tuple(evidence)

    @staticmethod
    def _source_id(asset_ids: tuple[int, ...], source_type: str) -> str:
        if source_type == "asset" and len(asset_ids) == 1:
            return str(asset_ids[0])
        return "-".join(str(asset_id) for asset_id in asset_ids)
