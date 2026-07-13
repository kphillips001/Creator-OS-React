"""AI import workflow orchestration for Creator OS.

This service coordinates the existing import pipeline without owning the
classification, Local Vault, Product, Experience, or Publishing business rules.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

from app.models.asset_provenance import (
    ASSET_PROVENANCE_METADATA_KEY,
    AssetProvenanceClassification,
    administrative_import_context,
    provenance_context,
)
from app.models.creator_intent import CreatorIntent

if TYPE_CHECKING:
    from app.repositories.asset_repository import AssetRepository
    from app.services.ai_product_drafting_service import AIProductDraftingService
    from app.services.asset_understanding_service import AssetUnderstandingService
    from app.services.commerce_intelligence_service import CommerceIntelligenceService
    from app.services.commerce_strategy_service import CommerceStrategyService
    from app.services.content_intelligence_service import ContentIntelligenceService
    from app.services.experience_intelligence_service import ExperienceIntelligenceService
    from app.services.experience_service import ExperienceService
    from app.services.media_processing_service import MediaProcessingService
    from app.services.publishing_service import PublishingService
    from app.services.product_strategy_service import ProductStrategyService
    from app.services.runtime_media_resolver import RuntimeMediaResolver


@dataclass(frozen=True)
class AutomaticOrganizationResult:
    """Read-only organization projection for an imported workflow result."""

    asset_ids: tuple[int, ...]
    organization_type: str
    asset_library_visible: bool
    local_vault_owned: bool
    experience_recommendation: Any | None = None
    product_strategy_result: Any | None = None
    commerce_strategy_result: Any | None = None
    product_draft_result: Any | None = None
    delivery_type: str | None = None
    publishing_readiness: Mapping[str, Any] = field(default_factory=dict)
    relationship_chain: tuple[str, ...] = (
        "Asset",
        "AssetUnderstanding",
        "ExperienceRecommendation",
        "ProductStrategy",
        "CommerceStrategy",
        "Product Draft",
        "Publishing readiness",
    )
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AIImportAssetResult:
    """Presentation-safe result for one imported asset workflow."""

    success: bool
    media_path: str
    upload_intent: str
    legacy_result: Mapping[str, Any]
    content_id: int | None = None
    product_draft_result: Mapping[str, Any] = field(default_factory=dict)
    asset: Any | None = None
    content_intelligence: Any | None = None
    asset_understanding: Any | None = None
    experience_recommendation: Any | None = None
    commerce_recommendation: Any | None = None
    product_strategy_result: Any | None = None
    commerce_strategy_result: Any | None = None
    publishing_readiness: Mapping[str, Any] = field(default_factory=dict)
    organization_result: AutomaticOrganizationResult | None = None
    creator_intent: CreatorIntent | None = None

    @property
    def final_classification(self) -> str | None:
        return self.legacy_result.get("final_classification")

    def to_legacy_result(self) -> dict[str, Any]:
        """Return the existing result shape expected by legacy callers."""

        return dict(self.legacy_result)


@dataclass(frozen=True)
class AIImportBatchResult:
    """Presentation-safe result for a batch/photo-set import workflow."""

    success: bool
    asset_results: tuple[AIImportAssetResult, ...]
    content_ids: tuple[int, ...]
    product_draft_result: Any | None = None
    experience_recommendation: Any | None = None
    commerce_recommendation: Any | None = None
    product_strategy_result: Any | None = None
    commerce_strategy_result: Any | None = None
    publishing_readiness: Mapping[str, Any] = field(default_factory=dict)
    organization_result: AutomaticOrganizationResult | None = None
    errors: tuple[Mapping[str, Any], ...] = ()
    creator_intent: CreatorIntent | None = None

    @property
    def legacy_results(self) -> tuple[dict[str, Any], ...]:
        return tuple(result.to_legacy_result() for result in self.asset_results)


class AIImportWorkflowService:
    """Single orchestration boundary for imported Creator OS assets."""

    def __init__(
        self,
        *,
        classifier: Callable[..., dict[str, Any]] | None = None,
        asset_repository: "AssetRepository | None" = None,
        product_drafting_service: "AIProductDraftingService | None" = None,
        asset_understanding_service: "AssetUnderstandingService | None" = None,
        content_intelligence_service: "ContentIntelligenceService | None" = None,
        experience_intelligence_service: "ExperienceIntelligenceService | None" = None,
        commerce_intelligence_service: "CommerceIntelligenceService | None" = None,
        product_strategy_service: "ProductStrategyService | None" = None,
        commerce_strategy_service: "CommerceStrategyService | None" = None,
        runtime_media_resolver: "RuntimeMediaResolver | None" = None,
        media_processing_service: "MediaProcessingService | None" = None,
        experience_service: "ExperienceService | None" = None,
        publishing_service: "PublishingService | None" = None,
    ):
        self._classifier = classifier
        self._assets = asset_repository
        self._product_drafting = product_drafting_service
        self._asset_understanding = asset_understanding_service
        self._content_intelligence = content_intelligence_service
        self._experience_intelligence = experience_intelligence_service
        self._commerce_intelligence = commerce_intelligence_service
        self._product_strategy = product_strategy_service
        self._commerce_strategy = commerce_strategy_service
        self._runtime_media_resolver = runtime_media_resolver
        self._media_processing = media_processing_service
        self._experiences = experience_service
        self._publishing = publishing_service

    @property
    def classifier(self) -> Callable[..., dict[str, Any]]:
        if self._classifier is None:
            from app.services.content_classification_service import (
                classify_content_image,
            )

            self._classifier = classify_content_image
        return self._classifier

    @property
    def assets(self):
        if self._assets is None:
            from app.repositories.asset_repository import AssetRepository

            self._assets = AssetRepository()
        return self._assets

    @property
    def product_drafting(self):
        if self._product_drafting is None:
            from app.services.ai_product_drafting_service import (
                AIProductDraftingService,
            )

            self._product_drafting = AIProductDraftingService()
        return self._product_drafting

    @property
    def asset_understanding(self):
        if self._asset_understanding is None:
            from app.services.asset_understanding_service import (
                AssetUnderstandingService,
            )

            self._asset_understanding = AssetUnderstandingService(
                asset_repository=self.assets,
                runtime_media_resolver=self.runtime_media_resolver,
            )
        return self._asset_understanding

    @property
    def content_intelligence(self):
        if self._content_intelligence is None:
            from app.services.content_intelligence_service import (
                ContentIntelligenceService,
            )

            self._content_intelligence = ContentIntelligenceService(
                asset_understanding_service=self.asset_understanding,
            )
        return self._content_intelligence

    @property
    def experience_intelligence(self):
        if self._experience_intelligence is None:
            from app.services.experience_intelligence_service import (
                ExperienceIntelligenceService,
            )

            self._experience_intelligence = ExperienceIntelligenceService(
                asset_understanding_service=self.asset_understanding,
            )
        return self._experience_intelligence

    @property
    def commerce_intelligence(self):
        if self._commerce_intelligence is None:
            from app.services.commerce_intelligence_service import (
                CommerceIntelligenceService,
            )

            self._commerce_intelligence = CommerceIntelligenceService()
        return self._commerce_intelligence

    @property
    def product_strategy(self):
        if self._product_strategy is None:
            from app.services.product_strategy_service import (
                ProductStrategyService,
            )

            self._product_strategy = ProductStrategyService()
        return self._product_strategy

    @property
    def commerce_strategy(self):
        if self._commerce_strategy is None:
            from app.services.commerce_strategy_service import (
                CommerceStrategyService,
            )

            self._commerce_strategy = CommerceStrategyService()
        return self._commerce_strategy

    @property
    def runtime_media_resolver(self):
        if self._runtime_media_resolver is None:
            from app.services.runtime_media_resolver import RuntimeMediaResolver

            self._runtime_media_resolver = RuntimeMediaResolver()
        return self._runtime_media_resolver

    @property
    def media_processing(self):
        if self._media_processing is None:
            from app.services.media_processing_service import MediaProcessingService

            self._media_processing = MediaProcessingService()
        return self._media_processing

    @property
    def experiences(self):
        if self._experiences is None:
            from app.services.experience_service import ExperienceService

            self._experiences = ExperienceService()
        return self._experiences

    @property
    def publishing(self):
        if self._publishing is None:
            from app.services.publishing_service import PublishingService

            self._publishing = PublishingService()
        return self._publishing

    def import_asset(
        self,
        *,
        media_path: str | Path,
        upload_intent: str,
        creator_profile_id: int | None,
        creator_intent: CreatorIntent | Mapping[str, Any] | str | None = None,
        original_filename: str | None = None,
        fanvue_account_id: int | None = None,
        content_tier: str | None = None,
        distribution_type: str | None = None,
        mass_ppv_price: float | None = None,
        create_product_draft: bool = True,
        provider_upload_enabled: bool = False,
        is_test: bool = False,
        import_session_id: str | None = None,
        provenance_classification: AssetProvenanceClassification | str = (
            AssetProvenanceClassification.ADMINISTRATIVE_IMPORT
        ),
        provenance_source: str = "AIImportWorkflowService.import_asset",
    ) -> AIImportAssetResult:
        """Import one asset through the existing AI/CMS pipeline."""

        resolved_creator_intent = self._creator_intent(
            creator_intent,
            fallback_upload_intent=upload_intent,
        )
        resolved_upload_intent = resolved_creator_intent.to_legacy_upload_intent(
            upload_intent
        )
        result = self.classifier(
            image_path=media_path,
            save_to_db=True,
            is_test=is_test,
            upload_intent=resolved_upload_intent,
            fanvue_account_id=fanvue_account_id,
            creator_profile_id=creator_profile_id,
            content_tier=content_tier,
            distribution_type=distribution_type,
            mass_ppv_price=mass_ppv_price,
            fanvue_upload_enabled=provider_upload_enabled,
            create_product_draft=False,
            original_filename=original_filename,
        )

        content_id = self._content_id_from_result(result)
        self._stamp_import_provenance(
            content_id,
            classification=provenance_classification,
            source=provenance_source,
            source_workflow="ai_import_workflow",
            metadata={
                "import_session_id": import_session_id,
                "upload_intent": resolved_upload_intent,
                "creator_profile_id": creator_profile_id,
            },
        )
        legacy_product_draft_result = self._product_draft_from_result(result)
        product_draft_result = (
            {}
            if create_product_draft
            else legacy_product_draft_result
        )
        asset = self._load_asset(content_id)
        content_intelligence = self._build_content_intelligence(
            asset,
            content_id,
        )
        understanding = (
            content_intelligence.asset_understanding
            if content_intelligence is not None
            else None
        )
        resolved_import_session_id = self._resolve_import_session_id(
            import_session_id,
            result,
            asset_ids=(content_id,) if content_id is not None else (),
            prefix="asset",
        )
        experience_recommendation = self._recommend_experience(
            (self._preferred_intelligence(content_intelligence, understanding),),
            package_type="standalone",
            import_session_id=resolved_import_session_id,
        )
        commerce_recommendation = self._recommend_commerce(
            (self._preferred_intelligence(content_intelligence, understanding),),
            experience_recommendation=experience_recommendation,
        )
        product_strategy_result = self._recommend_product_strategy(
            creator_intent=resolved_creator_intent,
            content_intelligences=(content_intelligence,),
            experience_recommendation=experience_recommendation,
            commerce_recommendation=commerce_recommendation,
        )
        commerce_strategy_result = self._recommend_commerce_strategy(
            content_intelligences=(content_intelligence,),
            experience_recommendation=experience_recommendation,
            commerce_recommendation=commerce_recommendation,
            product_strategy_result=product_strategy_result,
        )
        product_draft_result = self._ensure_product_draft_for_asset(
            content_id=content_id,
            creator_profile_id=creator_profile_id,
            create_product_draft=create_product_draft,
            existing_product_draft_result=product_draft_result,
            commerce_recommendation=commerce_recommendation,
        )
        result = self._legacy_result_with_product_draft(
            result,
            product_draft_result,
        )
        publishing_readiness = self._publishing_readiness(asset)
        organization_result = self._organization_result(
            asset_ids=(content_id,) if content_id is not None else (),
            organization_type="standalone",
            asset_library_visible=asset is not None,
            understandings=(understanding,),
            experience_recommendation=experience_recommendation,
            commerce_recommendation=commerce_recommendation,
            product_strategy_result=product_strategy_result,
            commerce_strategy_result=commerce_strategy_result,
            product_draft_result=product_draft_result,
            publishing_readiness=publishing_readiness,
        )

        return AIImportAssetResult(
            success=bool(result.get("success")),
            media_path=str(media_path),
            upload_intent=resolved_upload_intent,
            creator_intent=resolved_creator_intent,
            legacy_result=result,
            content_id=content_id,
            product_draft_result=product_draft_result,
            asset=asset,
            content_intelligence=content_intelligence,
            asset_understanding=understanding,
            experience_recommendation=experience_recommendation,
            commerce_recommendation=commerce_recommendation,
            product_strategy_result=product_strategy_result,
            commerce_strategy_result=commerce_strategy_result,
            publishing_readiness=publishing_readiness,
            organization_result=organization_result,
        )

    def import_asset_batch(
        self,
        *,
        media_items: Iterable[Mapping[str, Any] | str | Path],
        upload_intent: str,
        creator_profile_id: int | None,
        creator_intent: CreatorIntent | Mapping[str, Any] | str | None = None,
        fanvue_account_id: int | None = None,
        content_tier: str | None = None,
        distribution_type: str | None = None,
        mass_ppv_price: float | None = None,
        package_type: str = "photo_set",
        create_product_draft: bool = True,
        provider_upload_enabled: bool = False,
        is_test: bool = False,
        import_session_id: str | None = None,
        provenance_classification: AssetProvenanceClassification | str = (
            AssetProvenanceClassification.ADMINISTRATIVE_IMPORT
        ),
        provenance_source: str = "AIImportWorkflowService.import_asset_batch",
    ) -> AIImportBatchResult:
        """Import a batch and optionally create one photo-set Product draft."""

        resolved_creator_intent = (
            self._creator_intent(
                creator_intent,
                fallback_upload_intent=upload_intent,
            )
            if creator_intent is not None
            else CreatorIntent.create(
                package_type,
                legacy_upload_intent=upload_intent,
                metadata={"source": "ai_import_workflow_batch"},
            )
        )
        resolved_upload_intent = resolved_creator_intent.to_legacy_upload_intent(
            upload_intent
        )
        resolved_package_type = (
            package_type
            if package_type != "photo_set" or creator_intent is None
            else resolved_creator_intent.package_type
        )
        asset_results: list[AIImportAssetResult] = []
        errors: list[Mapping[str, Any]] = []

        for item in media_items:
            media_path, original_filename, item_upload_intent = (
                self._normalize_media_item(item, resolved_upload_intent)
            )
            result = self.import_asset(
                media_path=media_path,
                upload_intent=item_upload_intent,
                creator_intent=resolved_creator_intent,
                creator_profile_id=creator_profile_id,
                original_filename=original_filename,
                fanvue_account_id=fanvue_account_id,
                content_tier=content_tier,
                distribution_type=distribution_type,
                mass_ppv_price=mass_ppv_price,
                create_product_draft=False,
                provider_upload_enabled=provider_upload_enabled,
                is_test=is_test,
                import_session_id=import_session_id,
                provenance_classification=provenance_classification,
                provenance_source=provenance_source,
            )
            asset_results.append(result)
            if not result.success:
                errors.append(
                    {
                        "media_path": str(media_path),
                        "error": result.legacy_result.get("error"),
                    }
                )

        content_ids = tuple(
            result.content_id
            for result in asset_results
            if result.content_id is not None
        )

        product_draft_result = None
        resolved_import_session_id = self._resolve_import_session_id(
            import_session_id,
            {},
            asset_ids=content_ids,
            prefix="batch",
        )
        experience_recommendation = self._recommend_experience(
            tuple(self._result_intelligence(result) for result in asset_results),
            package_type=resolved_package_type,
            import_session_id=resolved_import_session_id,
        )
        commerce_recommendation = self._recommend_commerce(
            tuple(self._result_intelligence(result) for result in asset_results),
            experience_recommendation=experience_recommendation,
        )
        product_strategy_result = self._recommend_product_strategy(
            creator_intent=resolved_creator_intent,
            content_intelligences=tuple(
                result.content_intelligence for result in asset_results
            ),
            experience_recommendation=experience_recommendation,
            commerce_recommendation=commerce_recommendation,
        )
        commerce_strategy_result = self._recommend_commerce_strategy(
            content_intelligences=tuple(
                result.content_intelligence for result in asset_results
            ),
            experience_recommendation=experience_recommendation,
            commerce_recommendation=commerce_recommendation,
            product_strategy_result=product_strategy_result,
        )
        normalized_package_type = (resolved_package_type or "").lower()
        if (
            create_product_draft
            and normalized_package_type in {"photo_set", "photoset"}
            and not errors
            and len(content_ids) == len(asset_results)
            and creator_profile_id
        ):
            product_draft_result = (
                self.product_drafting.create_photo_set_for_assets(
                    list(content_ids),
                    creator_profile_id=creator_profile_id,
                    commerce_recommendation=commerce_recommendation,
                )
            )
        publishing_readiness = self._batch_publishing_readiness(
            asset_results,
            commerce_recommendation=commerce_recommendation,
        )
        organization_result = self._organization_result(
            asset_ids=content_ids,
            organization_type=(
                "photo_set"
                if normalized_package_type in {"photo_set", "photoset"}
                else package_type
            ),
            asset_library_visible=(
                bool(content_ids)
                and len(content_ids) == len(asset_results)
                and all(result.asset is not None for result in asset_results)
            ),
            understandings=tuple(
                result.asset_understanding for result in asset_results
            ),
            experience_recommendation=experience_recommendation,
            commerce_recommendation=commerce_recommendation,
            product_strategy_result=product_strategy_result,
            commerce_strategy_result=commerce_strategy_result,
            product_draft_result=product_draft_result,
            publishing_readiness=publishing_readiness,
        )

        return AIImportBatchResult(
            success=not errors and len(content_ids) == len(asset_results),
            creator_intent=resolved_creator_intent,
            asset_results=tuple(asset_results),
            content_ids=content_ids,
            product_draft_result=product_draft_result,
            experience_recommendation=experience_recommendation,
            commerce_recommendation=commerce_recommendation,
            product_strategy_result=product_strategy_result,
            commerce_strategy_result=commerce_strategy_result,
            publishing_readiness=publishing_readiness,
            organization_result=organization_result,
            errors=tuple(errors),
        )

    def _stamp_import_provenance(
        self,
        content_id: int | None,
        *,
        classification: AssetProvenanceClassification | str,
        source: str,
        source_workflow: str | None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if content_id is None:
            return
        asset = self._load_asset(content_id)
        if asset is None:
            return
        current = dict(getattr(asset, "media_metadata", None) or {})
        if ASSET_PROVENANCE_METADATA_KEY in current:
            return
        try:
            context = provenance_context(
                classification,
                source=source,
                source_workflow=source_workflow,
                metadata=metadata,
            )
        except ValueError:
            context = administrative_import_context(
                source=source,
                source_workflow=source_workflow,
                metadata={
                    **dict(metadata or {}),
                    "invalid_requested_classification": str(classification),
                },
            )
        current[ASSET_PROVENANCE_METADATA_KEY] = context
        update = getattr(self.assets, "update_media_metadata", None)
        if callable(update):
            update(content_id, current)

    def _load_asset(self, content_id: int | None) -> Any | None:
        if not content_id:
            return None
        try:
            return self.assets.get_by_id(content_id)
        except Exception:
            return None

    def _build_asset_understanding(
        self,
        asset: Any | None,
        content_id: int | None,
    ) -> Any | None:
        record = self._build_content_intelligence(asset, content_id)
        return record.asset_understanding if record is not None else None

    def _build_content_intelligence(
        self,
        asset: Any | None,
        content_id: int | None,
    ) -> Any | None:
        try:
            if asset is not None:
                return self.content_intelligence.build_from_asset(asset)
            if content_id is not None:
                return self.content_intelligence.get_asset_intelligence(
                    content_id
                )
        except Exception:
            return None
        return None

    @staticmethod
    def _preferred_intelligence(
        content_intelligence: Any | None,
        asset_understanding: Any | None,
    ) -> Any | None:
        view = getattr(content_intelligence, "to_asset_understanding_view", None)
        if callable(view):
            return content_intelligence
        return asset_understanding

    @classmethod
    def _result_intelligence(cls, result: AIImportAssetResult) -> Any | None:
        return cls._preferred_intelligence(
            result.content_intelligence,
            result.asset_understanding,
        )

    def _recommend_experience(
        self,
        understandings: Iterable[Any | None],
        *,
        package_type: str | None,
        import_session_id: str | None = None,
    ) -> Any | None:
        candidates = tuple(
            understanding
            for understanding in understandings
            if understanding is not None
        )
        if not candidates:
            return None
        try:
            return self.experience_intelligence.recommend_for_understandings(
                candidates,
                package_type=package_type,
                import_session_id=import_session_id,
            )
        except Exception:
            return None

    def _recommend_commerce(
        self,
        understandings: Iterable[Any | None],
        *,
        experience_recommendation: Any | None,
    ) -> Any | None:
        candidates = tuple(
            understanding
            for understanding in understandings
            if understanding is not None
        )
        if not candidates:
            return None
        try:
            return self.commerce_intelligence.recommend(
                asset_understandings=candidates,
                experience_recommendation=experience_recommendation,
            )
        except Exception:
            return None

    def _recommend_product_strategy(
        self,
        *,
        creator_intent: CreatorIntent | None = None,
        content_intelligences: Iterable[Any | None],
        experience_recommendation: Any | None,
        commerce_recommendation: Any | None,
    ) -> Any | None:
        candidates = tuple(
            record
            for record in content_intelligences
            if record is not None
            and callable(getattr(record, "to_asset_understanding_view", None))
        )
        if not candidates and experience_recommendation is None:
            return None
        try:
            return self.product_strategy.recommend(
                creator_intent=(
                    creator_intent.to_context() if creator_intent else None
                ),
                content_intelligences=candidates,
                experience_context=experience_recommendation,
                commerce_recommendation=commerce_recommendation,
            )
        except Exception:
            return None

    def _recommend_commerce_strategy(
        self,
        *,
        content_intelligences: Iterable[Any | None],
        experience_recommendation: Any | None,
        commerce_recommendation: Any | None,
        product_strategy_result: Any | None,
    ) -> Any | None:
        candidates = tuple(record for record in content_intelligences if record)
        if (
            not candidates
            and experience_recommendation is None
            and commerce_recommendation is None
            and product_strategy_result is None
        ):
            return None
        try:
            return self.commerce_strategy.recommend(
                content_intelligences=candidates,
                experience_context=experience_recommendation,
                commerce_intelligence=commerce_recommendation,
                product_strategy_result=product_strategy_result,
            )
        except Exception:
            return None

    def _ensure_product_draft_for_asset(
        self,
        *,
        content_id: int | None,
        creator_profile_id: int | None,
        create_product_draft: bool,
        existing_product_draft_result: Mapping[str, Any],
        commerce_recommendation: Any | None,
    ) -> Mapping[str, Any]:
        if existing_product_draft_result:
            return existing_product_draft_result
        if not create_product_draft:
            return {
                "success": True,
                "created": False,
                "reason": "product_draft_deferred",
            }
        if not content_id or not creator_profile_id:
            return {
                "success": False,
                "created": False,
                "reason": "missing_content_or_creator_profile",
            }
        try:
            return self.product_drafting.create_draft_result_for_asset(
                content_id,
                creator_profile_id=creator_profile_id,
                commerce_recommendation=commerce_recommendation,
            )
        except TypeError:
            return self.product_drafting.create_draft_result_for_asset(
                content_id,
                creator_profile_id=creator_profile_id,
            )
        except Exception as error:
            return {
                "success": False,
                "created": False,
                "error": str(error),
            }

    def _organization_result(
        self,
        *,
        asset_ids: tuple[int, ...],
        organization_type: str,
        asset_library_visible: bool,
        understandings: Iterable[Any | None],
        experience_recommendation: Any | None,
        commerce_recommendation: Any | None,
        product_strategy_result: Any | None,
        commerce_strategy_result: Any | None,
        product_draft_result: Any | None,
        publishing_readiness: Mapping[str, Any],
    ) -> AutomaticOrganizationResult:
        understanding_values = tuple(
            understanding
            for understanding in understandings
            if understanding is not None
        )
        delivery_type = self._delivery_type(commerce_recommendation)
        notes: list[str] = []
        if not asset_library_visible:
            notes.append("Asset Library visibility pending asset projection.")
        if not understanding_values:
            notes.append("Asset Understanding unavailable.")
        if experience_recommendation is None:
            notes.append("Experience recommendation unavailable.")
        if not product_draft_result:
            notes.append("Product Draft unavailable or deferred.")
        if not publishing_readiness:
            notes.append("Publishing readiness unavailable.")

        return AutomaticOrganizationResult(
            asset_ids=tuple(asset_id for asset_id in asset_ids if asset_id),
            organization_type=organization_type or "unknown",
            asset_library_visible=asset_library_visible,
            local_vault_owned=self._all_local_vault_owned(understanding_values),
            experience_recommendation=experience_recommendation,
            product_strategy_result=product_strategy_result,
            commerce_strategy_result=commerce_strategy_result,
            product_draft_result=product_draft_result,
            delivery_type=delivery_type,
            publishing_readiness=dict(publishing_readiness),
            notes=tuple(notes),
        )

    @staticmethod
    def _delivery_type(commerce_recommendation: Any | None) -> str | None:
        delivery_type = getattr(commerce_recommendation, "delivery_type", None)
        return getattr(delivery_type, "value", delivery_type)

    @staticmethod
    def _all_local_vault_owned(understandings: Iterable[Any]) -> bool:
        values = tuple(understandings)
        if not values:
            return False
        for understanding in values:
            readiness = getattr(understanding, "readiness", None)
            media = getattr(understanding, "media", None)
            has_local_vault_media = getattr(
                readiness,
                "has_local_vault_media",
                None,
            )
            local_vault_path = getattr(media, "local_vault_path", None)
            if not (has_local_vault_media or local_vault_path):
                return False
        return True

    @staticmethod
    def _batch_publishing_readiness(
        asset_results: Iterable[AIImportAssetResult],
        *,
        commerce_recommendation: Any | None,
    ) -> dict[str, Any]:
        results = tuple(asset_results)
        asset_readiness = tuple(
            dict(result.publishing_readiness)
            for result in results
            if result.publishing_readiness
        )
        commerce_publishing = getattr(commerce_recommendation, "publishing", None)
        ready_count = sum(
            1
            for readiness in asset_readiness
            if readiness.get("status") not in {None, "missing"}
        )
        return {
            "status": "ready_for_review"
            if ready_count == len(results) and results
            else "partial",
            "asset_count": len(results),
            "ready_asset_count": ready_count,
            "asset_readiness": asset_readiness,
            "commerce": {
                "status": getattr(commerce_publishing, "status", None),
                "action": getattr(commerce_publishing, "action", None),
                "reason": getattr(commerce_publishing, "reason", None),
            }
            if commerce_publishing
            else None,
        }

    def _publishing_readiness(self, asset: Any | None) -> dict[str, Any]:
        if asset is None:
            return {}
        try:
            record = self.publishing.project_legacy_asset_record(asset)
            status, detail = self.publishing.get_provider_status_display(
                record,
                provider_name="Fanvue",
                missing_detail="No local asset is attached.",
                local_detail="Local asset only",
            )
            return {
                "status": status,
                "detail": detail,
                "record": record,
            }
        except Exception:
            return {}

    @staticmethod
    def _content_id_from_result(result: Mapping[str, Any]) -> int | None:
        db_save_result = result.get("db_save_result") or {}
        content_id = db_save_result.get("content_id")
        try:
            return int(content_id) if content_id is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _product_draft_from_result(
        result: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        db_save_result = result.get("db_save_result") or {}
        product_result = db_save_result.get("product_draft_result")
        return product_result if isinstance(product_result, Mapping) else {}

    @staticmethod
    def _legacy_result_with_product_draft(
        result: Mapping[str, Any],
        product_draft_result: Any,
    ) -> dict[str, Any]:
        legacy = dict(result)
        db_save_result = dict(legacy.get("db_save_result") or {})
        db_save_result["product_draft_result"] = product_draft_result
        legacy["db_save_result"] = db_save_result
        return legacy

    @staticmethod
    def _resolve_import_session_id(
        explicit: str | None,
        result: Mapping[str, Any],
        *,
        asset_ids: tuple[int, ...],
        prefix: str,
    ) -> str | None:
        if explicit:
            return str(explicit)
        db_save_result = result.get("db_save_result") or {}
        candidate = result.get("import_session_id") or db_save_result.get(
            "import_session_id"
        )
        if candidate:
            return str(candidate)
        clean_ids = tuple(asset_id for asset_id in asset_ids if asset_id)
        if not clean_ids:
            return None
        return f"{prefix}:{'-'.join(str(asset_id) for asset_id in clean_ids)}"

    @staticmethod
    def _creator_intent(
        value: CreatorIntent | Mapping[str, Any] | str | None,
        *,
        fallback_upload_intent: str | None,
    ) -> CreatorIntent:
        return CreatorIntent.from_value(
            value,
            fallback_upload_intent=fallback_upload_intent,
        )

    @staticmethod
    def _normalize_media_item(
        item: Mapping[str, Any] | str | Path,
        default_upload_intent: str,
    ) -> tuple[str | Path, str | None, str]:
        if isinstance(item, Mapping):
            media_path = item.get("media_path") or item.get("path")
            if not media_path:
                raise ValueError("Batch media item is missing media_path.")
            return (
                media_path,
                item.get("original_filename"),
                item.get("upload_intent") or default_upload_intent,
            )
        return item, None, default_upload_intent
