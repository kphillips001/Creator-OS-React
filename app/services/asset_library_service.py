"""Read-only Asset Library service.

B.5.2 introduces the Asset Library read-model boundary only. The service
constructs UI-friendly asset models from existing repositories and domain
services without mutating assets, publishing media, or creating Products.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.models.asset import Asset
from app.models.product import ProductType
from app.models.asset_library import (
    AssetDerivativeSummary,
    AssetExperiencePresentation,
    AssetLibraryActionResult,
    AssetLibraryDetails,
    AssetLibraryFilter,
    AssetLibraryItem,
    AssetLibraryResult,
    AssetPublishingSummary,
    AssetRelationshipSummary,
    AssetStorageSummary,
)
from app.repositories.asset_repository import AssetRepository
from app.repositories.experience_repository import ExperienceRepository
from app.repositories.product_asset_repository import ProductAssetRepository
from app.repositories.product_repository import ProductRepository
from app.services.asset_lifecycle_service import AssetLifecycleService
from app.services.asset_understanding_service import AssetUnderstandingService
from app.services.asset_intelligence_service import AssetIntelligenceService
from app.services.content_destination_service import ContentDestinationService
from app.services.experience_service import ExperienceService
from app.services.local_vault_service import LocalVaultService
from app.services.media_processing_service import MediaProcessingService
from app.services.publishing_service import PublishingService
from app.services.runtime_media_resolver import RuntimeMediaResolver
from app.services.reference_asset_protection import is_reference_asset


class AssetLibraryService:
    """Builds read-only Asset Library presentation models."""

    def __init__(
        self,
        *,
        asset_repository: AssetRepository | None = None,
        runtime_media_resolver: RuntimeMediaResolver | None = None,
        media_processing_service: MediaProcessingService | None = None,
        experience_service: ExperienceService | None = None,
        product_repository: ProductRepository | None = None,
        product_asset_repository: ProductAssetRepository | None = None,
        publishing_service: PublishingService | None = None,
        local_vault_service: LocalVaultService | None = None,
        asset_lifecycle_service: AssetLifecycleService | None = None,
        asset_understanding_service: AssetUnderstandingService | None = None,
        content_opportunity_service=None,
        asset_intelligence_service: AssetIntelligenceService | None = None,
        content_destination_service: ContentDestinationService | None = None,
    ):
        self.assets = asset_repository or AssetRepository()
        self.runtime_media_resolver = runtime_media_resolver or RuntimeMediaResolver()
        self.media_processing = media_processing_service or MediaProcessingService()
        self.products = product_repository or ProductRepository()
        self.product_assets = product_asset_repository or ProductAssetRepository()
        self.experiences = experience_service or ExperienceService(
            ExperienceRepository(
                product_repository=self.products,
                product_asset_repository=self.product_assets,
            )
        )
        self.publishing = publishing_service or PublishingService()
        self.local_vault = local_vault_service or LocalVaultService()
        self.asset_lifecycle = asset_lifecycle_service or AssetLifecycleService()
        self.asset_understanding = (
            asset_understanding_service
            or AssetUnderstandingService(
                asset_repository=self.assets,
                runtime_media_resolver=self.runtime_media_resolver,
            )
        )
        self.content_opportunity_service = content_opportunity_service
        self.asset_intelligence = asset_intelligence_service or AssetIntelligenceService()
        self.content_destinations = (
            content_destination_service
            or ContentDestinationService(asset_repository=self.assets)
        )

    def search_assets(
        self,
        filters: AssetLibraryFilter | None = None,
    ) -> AssetLibraryResult:
        filters = filters or AssetLibraryFilter()
        assets = self.assets.search_assets(
            search=filters.search,
            media_type=filters.media_type,
            classification=filters.classification,
            eligible_only=filters.eligible_only,
            limit=filters.limit,
            tags=filters.tags,
            themes=filters.themes,
            status=filters.status,
            created_after=filters.created_after,
            created_before=filters.created_before,
            creator_profile_id=filters.creator_profile_id,
            product_id=filters.product_id,
            experience_id=filters.experience_id,
            publishing_status=filters.publishing_status,
            has_local_vault_original=filters.has_local_vault_original,
            has_derivative_preview=filters.has_derivative_preview,
            is_reference_image=filters.is_reference_image,
            legacy_content_id=filters.legacy_content_id,
            availability_predicate=(
                self.content_destinations.available_inventory_predicate(
                    "content_items.id"
                )
                if filters.eligible_only
                else None
            ),
        )
        items = tuple(self.build_item(asset) for asset in assets)
        return AssetLibraryResult(
            items=items,
            filters=filters,
            total=len(items),
        )

    def asset_library_grid_summary(
        self,
        filters: AssetLibraryFilter,
        *,
        candidate_limit: int,
    ) -> tuple[tuple[dict, ...], int, tuple[str, ...]]:
        # Registered Images are independently managed commercial units.
        # Photoshoot members and supporting derivatives remain accessible
        # through their owning Photoshoot instead of this grid.
        classification = (
            ProductType.SINGLE_IMAGE.value
            if filters.media_type == "image"
            else filters.classification
        )
        return self.assets.asset_library_grid_summary(
            search=filters.search,
            media_type=filters.media_type,
            classification=classification,
            sale_destination=filters.sale_destination if filters.media_type == "image" else None,
            asset_purpose=filters.asset_purpose,
            creator_profile_id=int(filters.creator_profile_id or 0),
            limit=candidate_limit,
            # Canonical library membership is independent of commercial
            # destination. A SINGLE_IMAGE remains library-visible after it is
            # committed to SINGLE_PPV or another legitimate sales destination.
            availability_predicate=None,
        )

    def build_items_by_ids(self, asset_ids: tuple[int, ...]) -> tuple[AssetLibraryItem, ...]:
        assets = self.assets.list_by_ids(asset_ids)
        by_id = {asset.id: asset for asset in assets}
        return tuple(
            self.build_item(by_id[asset_id])
            for asset_id in asset_ids
            if asset_id in by_id
        )

    def get_asset_details(self, asset_id: int) -> AssetLibraryDetails | None:
        asset = self.assets.get_by_id(asset_id)
        if not asset:
            return None
        item = self.build_item(asset)
        storage = self.build_storage_summary(asset)
        derivative = self.build_derivative_summary(asset)
        relationship = item.relationship
        publishing = item.publishing
        understanding = self._safe_asset_understanding(asset)
        return AssetLibraryDetails(
            item=item,
            creator_profile_id=asset.creator_profile_id,
            confidence=self._understanding_confidence(understanding, asset),
            summary=self._understanding_summary(understanding, asset),
            reasoning=self._understanding_reasoning(understanding, asset),
            risk_flags=self._understanding_risk_flags(understanding, asset),
            is_explicit=self._understanding_is_explicit(understanding, asset),
            nudity_labels=self._understanding_nudity_labels(understanding, asset),
            nudity_level=self._understanding_nudity_level(understanding, asset),
            sexual_intensity=self._understanding_sexual_intensity(
                understanding,
                asset,
            ),
            storage=storage,
            derivative=derivative,
            relationship=relationship,
            publishing=publishing,
            analysis_provenance=asset.analysis_provenance,
            gpt_vision_result=asset.gpt_vision_result,
            nudenet_result=asset.nudenet_result,
            classification_result=asset.classification_result,
            media_metadata=asset.media_metadata,
            asset_understanding=understanding,
            intelligence_profile=self._safe_intelligence_profile(asset.id),
        )

    def _safe_intelligence_profile(self, asset_id: int):
        try:
            return self.asset_intelligence.get_profile(asset_id)
        except Exception:
            return None

    def get_asset_items(self, asset_ids: tuple[int, ...] | list[int]) -> tuple[AssetLibraryItem, ...]:
        assets = self.assets.list_by_ids(asset_ids)
        by_id = {asset.id: asset for asset in assets}
        return tuple(
            self.build_item(by_id[asset_id])
            for asset_id in asset_ids
            if asset_id in by_id
        )

    def regenerate_derivative_preview(
        self,
        asset_id: int,
    ) -> AssetLibraryActionResult:
        asset = self.assets.get_by_id(asset_id)
        if not asset:
            return AssetLibraryActionResult(
                success=False,
                message="Asset was not found.",
                asset_id=asset_id,
            )
        results = self.media_processing.regenerate_derivatives(
            asset,
            ("blurred_preview",),
        )
        return AssetLibraryActionResult(
            success=True,
            message="Derivative preview regenerated.",
            asset_id=asset_id,
            data=results,
        )

    def refresh_derivative_summary(
        self,
        asset_id: int,
    ) -> AssetLibraryActionResult:
        asset = self.assets.get_by_id(asset_id)
        if not asset:
            return AssetLibraryActionResult(
                success=False,
                message="Asset was not found.",
                asset_id=asset_id,
            )
        summary = self.build_derivative_summary(asset)
        return AssetLibraryActionResult(
            success=True,
            message="Derivative metadata refreshed.",
            asset_id=asset_id,
            data={
                "preview_path": summary.preview_path,
                "type": summary.derivative_type,
                "storage": summary.storage,
                "generated_at": summary.generated_at,
                "source": summary.source,
            },
        )

    def update_asset_metadata(
        self,
        asset_id: int,
        *,
        classification: str,
        tags: tuple[str, ...],
        themes: tuple[str, ...],
    ) -> AssetLibraryActionResult:
        asset = self.assets.get_by_id(asset_id)
        if not asset:
            return AssetLibraryActionResult(
                success=False,
                message="Asset was not found.",
                asset_id=asset_id,
            )
        self.asset_lifecycle.save_review_edits(
            asset_id=asset_id,
            suggested_tags=list(tags),
            detected_themes=list(themes),
            classification=classification,
        )
        self._notify_content_opportunity_asset_available(asset)
        return AssetLibraryActionResult(
            success=True,
            message="Asset metadata updated.",
            asset_id=asset_id,
        )

    def _notify_content_opportunity_asset_available(self, asset: Asset) -> None:
        service = self.content_opportunity_service
        notify = getattr(service, "record_new_asset_available", None)
        if not callable(notify):
            return
        try:
            notify(asset)
        except Exception:
            return

    def build_item(self, asset: Asset) -> AssetLibraryItem:
        original = self.runtime_media_resolver.resolve_original(
            asset,
            require_exists=True,
        )
        preview_path = self.media_processing.resolve_derivative(
            asset,
            "blurred_preview",
        )
        if not preview_path and original.path:
            preview_path = str(original.path)
        relationship = self.build_relationship_summary(asset)
        publishing = self.build_publishing_summary(asset)
        return AssetLibraryItem(
            asset_id=asset.id,
            file_name=asset.file_name,
            media_type=asset.media_type,
            classification=asset.classification,
            status=asset.status,
            is_active=asset.is_active,
            created_at=asset.created_at,
            preview_path=preview_path,
            original_path=str(original.path) if original.path else None,
            tags=asset.suggested_tags,
            themes=asset.detected_themes,
            ready_for_rotation=bool(getattr(asset, "ready_for_rotation", False)),
            relationship=relationship,
            publishing=publishing,
            is_reference_image=self._is_reference_image(asset),
            media_metadata=asset.media_metadata,
        )

    def _safe_asset_understanding(self, asset: Asset) -> Any | None:
        try:
            return self.asset_understanding.build_from_asset(asset)
        except Exception:
            return None

    @staticmethod
    def _understanding_confidence(understanding: Any | None, asset: Asset) -> float | None:
        classification = getattr(understanding, "classification", None)
        value = getattr(classification, "confidence", None)
        return value if value is not None else asset.confidence

    @staticmethod
    def _understanding_summary(understanding: Any | None, asset: Asset) -> str | None:
        visual = getattr(understanding, "visual", None)
        return getattr(visual, "summary", None) or asset.summary

    @staticmethod
    def _understanding_reasoning(understanding: Any | None, asset: Asset) -> str | None:
        provenance = getattr(understanding, "provenance", None)
        return getattr(provenance, "reasoning", None) or asset.reasoning

    @staticmethod
    def _understanding_risk_flags(understanding: Any | None, asset: Asset) -> tuple[str, ...]:
        safety = getattr(understanding, "safety", None)
        return tuple(getattr(safety, "risk_flags", ()) or asset.risk_flags or ())

    @staticmethod
    def _understanding_is_explicit(understanding: Any | None, asset: Asset) -> bool:
        safety = getattr(understanding, "safety", None)
        value = getattr(safety, "is_explicit", None)
        return bool(asset.is_explicit if value is None else value)

    @staticmethod
    def _understanding_nudity_labels(understanding: Any | None, asset: Asset) -> tuple[str, ...]:
        safety = getattr(understanding, "safety", None)
        return tuple(getattr(safety, "nudity_labels", ()) or asset.nudity_labels or ())

    @staticmethod
    def _understanding_nudity_level(understanding: Any | None, asset: Asset) -> str | None:
        safety = getattr(understanding, "safety", None)
        return getattr(safety, "nudity_level", None) or asset.nudity_level

    @staticmethod
    def _understanding_sexual_intensity(
        understanding: Any | None,
        asset: Asset,
    ) -> str | None:
        safety = getattr(understanding, "safety", None)
        return getattr(safety, "sexual_intensity", None) or asset.sexual_intensity

    def build_storage_summary(self, asset: Asset) -> AssetStorageSummary:
        original = self.runtime_media_resolver.resolve_original(
            asset,
            require_exists=True,
        )
        media_metadata = self._coerce_mapping(asset.media_metadata)
        local_vault_path = (
            media_metadata.get("local_vault_path")
            or getattr(asset, "local_vault_path", None)
        )
        return AssetStorageSummary(
            original_path=str(original.path) if original.path else None,
            original_source=original.source,
            original_exists=original.exists,
            local_vault_path=str(local_vault_path) if local_vault_path else None,
            legacy_file_path=asset.file_path,
            media_metadata=media_metadata,
        )

    def build_derivative_summary(self, asset: Asset) -> AssetDerivativeSummary:
        preview_path = self.media_processing.resolve_derivative(
            asset,
            "blurred_preview",
        )
        metadata = self._derivative_metadata(asset)
        return AssetDerivativeSummary(
            preview_path=preview_path,
            derivative_type=str(metadata.get("type") or "blur"),
            storage=metadata.get("storage"),
            generated_at=metadata.get("generated_at"),
            source=metadata.get("source"),
            metadata=metadata,
        )

    def build_relationship_summary(
        self,
        asset: Asset,
    ) -> AssetRelationshipSummary:
        product_ids = set()
        products = []
        experience_relationships = self._safe_experience_relationships(
            asset.id
        )
        for relationship in experience_relationships:
            source_product_id = self._coerce_mapping(
                getattr(relationship, "metadata", None)
            ).get("source_product_id")
            if not source_product_id:
                continue
            product_ids.add(str(source_product_id))
            product = self._safe_product_by_id(source_product_id)
            if product is not None:
                products.append(product)

        if not product_ids:
            # Compatibility-only fallback for older injected test doubles or
            # deployments that have not exposed Experience relationships yet.
            for product_id in self._safe_product_asset_ids(asset.id):
                product_ids.add(str(product_id))
                product = self._safe_product_by_id(product_id)
                if product is not None:
                    products.append(product)

        legacy_product = self._safe_legacy_product(asset.id)
        legacy_product_id = None
        if legacy_product:
            legacy_product_id = str(getattr(legacy_product, "id", ""))
            if legacy_product_id:
                product_ids.add(legacy_product_id)
                products.append(legacy_product)

        sorted_product_ids = tuple(sorted(product_ids))
        delivery_types = tuple(
            sorted(
                {
                    str(getattr(getattr(product, "delivery_type", None), "value", None)
                    or getattr(product, "delivery_type", None))
                    for product in products
                    if getattr(product, "delivery_type", None)
                }
            )
        )
        experience_ids = tuple(
            getattr(relationship, "experience_id")
            for relationship in experience_relationships
        ) or self._safe_asset_experience_ids(asset.id)
        experience_summaries = (
            tuple(
                self._experience_presentation_from_relationship(relationship)
                for relationship in experience_relationships
            )
            or tuple(
                AssetExperiencePresentation(
                    experience_id=str(experience_id),
                    relationship_source="compatibility_id",
                    compatibility=True,
                )
                for experience_id in experience_ids
            )
        )
        return AssetRelationshipSummary(
            product_count=len(sorted_product_ids),
            experience_count=len(experience_ids),
            legacy_product_id=legacy_product_id,
            product_ids=sorted_product_ids,
            product_delivery_types=delivery_types,
            experience_ids=experience_ids,
            experience_summaries=experience_summaries,
        )

    def _experience_presentation_from_relationship(
        self,
        relationship: Any,
    ) -> AssetExperiencePresentation:
        metadata = self._coerce_mapping(getattr(relationship, "metadata", None))
        return AssetExperiencePresentation(
            experience_id=str(getattr(relationship, "experience_id", "")),
            title=self._first_metadata_value(
                metadata,
                "experience_title",
                "title",
                "name",
            ),
            experience_type=self._first_metadata_value(
                metadata,
                "experience_type",
                "type",
            ),
            summary=self._first_metadata_value(
                metadata,
                "experience_summary",
                "summary",
                "description",
            ),
            cover_asset_id=self._coerce_optional_int(
                self._first_metadata_value(metadata, "cover_asset_id")
            ),
            themes=self._metadata_tuple(metadata, "suggested_themes", "themes"),
            keywords=self._metadata_tuple(
                metadata,
                "suggested_keywords",
                "keywords",
            ),
            mood=self._first_metadata_value(metadata, "mood"),
            story_progression=self._first_metadata_value(
                metadata,
                "story_progression",
            ),
            publishing_readiness=self._first_metadata_value(
                metadata,
                "publishing_readiness",
                "readiness",
            ),
            relationship_source=str(getattr(relationship, "source", "") or ""),
            compatibility=bool(getattr(relationship, "compatibility", False)),
        )

    @staticmethod
    def _first_metadata_value(
        metadata: dict,
        *keys: str,
    ) -> Any | None:
        for key in keys:
            value = metadata.get(key)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _metadata_tuple(metadata: dict, *keys: str) -> tuple[str, ...]:
        for key in keys:
            value = metadata.get(key)
            if not value:
                continue
            if isinstance(value, str):
                return (value,)
            return tuple(str(item) for item in value if str(item).strip())
        return ()

    @staticmethod
    def _coerce_optional_int(value: Any | None) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _safe_experience_relationships(self, asset_id: int) -> tuple[Any, ...]:
        list_relationships = getattr(
            self.experiences,
            "list_asset_relationships",
            None,
        )
        if callable(list_relationships):
            try:
                return tuple(list_relationships(asset_id))
            except Exception:
                return ()
        return ()

    def _safe_asset_experience_ids(self, asset_id: int) -> tuple[str, ...]:
        list_ids = getattr(
            self.experiences,
            "list_asset_experience_ids",
            None,
        )
        if callable(list_ids):
            try:
                return tuple(str(value) for value in list_ids(asset_id))
            except Exception:
                return ()
        return ()

    def build_publishing_summary(self, asset: Asset) -> AssetPublishingSummary:
        record = self.publishing.project_legacy_asset_record(asset)
        status, detail = self.publishing.get_provider_status_display(
            record,
            provider_name="Fanvue",
            missing_detail="No local asset is attached.",
            local_detail="Local asset only",
        )
        record = record or {}
        return AssetPublishingSummary(
            status=status,
            detail=detail,
            provider_media_id=record.get("provider_media_id"),
            provider_preview_media_id=record.get("provider_preview_media_id"),
            provider_full_media_id=record.get("provider_full_media_id"),
            provider_error=record.get("provider_error"),
        )

    def _safe_product_asset_ids(self, asset_id: int) -> tuple[Any, ...]:
        list_for_asset = getattr(
            self.product_assets,
            "list_product_ids_for_asset",
            None,
        )
        if callable(list_for_asset):
            try:
                return tuple(list_for_asset(asset_id))
            except Exception:
                return ()
        return ()

    def _safe_legacy_product(self, asset_id: int) -> Any | None:
        get_by_legacy = getattr(
            self.products,
            "get_by_legacy_content_item_id",
            None,
        )
        if callable(get_by_legacy):
            try:
                return get_by_legacy(asset_id)
            except Exception:
                return None
        return None

    def _safe_product_by_id(self, product_id: Any) -> Any | None:
        get_by_id = getattr(self.products, "get_by_id", None)
        if callable(get_by_id):
            try:
                return get_by_id(product_id)
            except Exception:
                return None
        return None

    def _derivative_metadata(self, asset: Asset) -> Mapping[str, Any]:
        media_metadata = self._coerce_mapping(asset.media_metadata)
        derivatives = self._coerce_mapping(media_metadata.get("derivatives"))
        metadata = derivatives.get("blurred_preview") or derivatives.get("blur")
        if not metadata:
            return {}
        try:
            return self.media_processing.normalize_derivative_metadata(
                metadata,
                derivative_type="blurred_preview",
            )
        except ValueError:
            return {}

    @staticmethod
    def _coerce_mapping(value: Any) -> Mapping[str, Any]:
        return value if isinstance(value, Mapping) else {}

    @classmethod
    def _is_reference_image(cls, asset: Asset) -> bool:
        return is_reference_asset(asset)
