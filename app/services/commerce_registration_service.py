"""Commerce Registration boundary for canonical Assets.

Commerce Registration creates the durable, provider-neutral Business Asset
identity for an already approved canonical Asset. It projects Product,
Experience, Delivery Type, and Publishing readiness, but does not own or mutate
those downstream domains.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, Iterable, Mapping
from uuid import UUID

from app.models.commerce_registration import (
    BusinessAssetLifecycleState,
    BusinessAssetRecord,
    COMMERCE_REGISTRATION_SCHEMA_VERSION,
    CommerceDestinationStatus,
    CommerceReadiness,
    CommerceRegistrationRequest,
    CommerceRegistrationResult,
    CommerceRegistrationStatus,
)
from app.models.asset_provenance import (
    ASSET_PROVENANCE_METADATA_KEY,
    AssetProvenanceClassification,
    provenance_context,
)
from app.models.generation_engine import utc_now
from app.models.product import ProductStatus, resolve_product_delivery_type
if TYPE_CHECKING:
    from app.repositories.asset_repository import AssetRepository
    from app.repositories.commerce_registration_repository import (
        CommerceRegistrationRepository,
    )
    from app.repositories.content_intelligence_repository import (
        ContentIntelligenceProfileRepository,
    )
    from app.repositories.product_asset_repository import ProductAssetRepository
    from app.repositories.product_repository import ProductRepository
    from app.services.experience_service import ExperienceService
    from app.services.publishing_service import PublishingService


class CommerceRegistrationService:
    """Registers creator-approved canonical Assets as reusable Business Assets."""

    def __init__(
        self,
        *,
        registration_repository: "CommerceRegistrationRepository | None" = None,
        asset_repository: "AssetRepository | None" = None,
        content_intelligence_repository: "ContentIntelligenceProfileRepository | None" = None,
        product_asset_repository: "ProductAssetRepository | None" = None,
        product_repository: "ProductRepository | None" = None,
        experience_service: "ExperienceService | None" = None,
        publishing_service: "PublishingService | None" = None,
        entry_policy: Any | None = None,
    ):
        if registration_repository is None:
            from app.repositories.commerce_registration_repository import (
                CommerceRegistrationRepository,
            )

            registration_repository = CommerceRegistrationRepository()
        if asset_repository is None:
            from app.repositories.asset_repository import AssetRepository

            asset_repository = AssetRepository()
        if content_intelligence_repository is None:
            from app.repositories.content_intelligence_repository import (
                ContentIntelligenceProfileRepository,
            )

            content_intelligence_repository = ContentIntelligenceProfileRepository()
        if product_asset_repository is None:
            from app.repositories.product_asset_repository import (
                ProductAssetRepository,
            )

            product_asset_repository = ProductAssetRepository()
        if product_repository is None:
            from app.repositories.product_repository import ProductRepository

            product_repository = ProductRepository()
        if experience_service is None:
            from app.services.experience_service import ExperienceService

            experience_service = ExperienceService()
        if publishing_service is None:
            from app.services.publishing_service import PublishingService

            publishing_service = PublishingService()
        self.registration_repository = (
            registration_repository
        )
        self.asset_repository = asset_repository
        self.content_intelligence_repository = (
            content_intelligence_repository
        )
        self.product_asset_repository = (
            product_asset_repository
        )
        self.product_repository = product_repository
        self.experience_service = experience_service
        self.publishing_service = publishing_service
        if entry_policy is None:
            from app.services.autonomous_commerce_entry_policy import (
                AutonomousCommerceEntryPolicy,
            )

            entry_policy = AutonomousCommerceEntryPolicy(
                asset_repository=self.asset_repository,
                content_intelligence_repository=self.content_intelligence_repository,
            )
        self.entry_policy = entry_policy

    def register_asset(
        self,
        asset_id: int,
        *,
        request: CommerceRegistrationRequest | None = None,
        content_intelligence_profile: Any | None = None,
        force_refresh: bool = False,
        **request_kwargs: Any,
    ) -> CommerceRegistrationResult:
        request = self._coerce_request(asset_id, request, request_kwargs)
        existing = self.registration_repository.get_by_asset_id(asset_id)
        if (
            existing
            and existing.commerce_registration_status
            == CommerceRegistrationStatus.REGISTERED
            and not force_refresh
        ):
            return CommerceRegistrationResult.from_record(existing)

        asset = self.asset_repository.get_by_id(asset_id)
        if asset is None:
            return CommerceRegistrationResult(
                success=False,
                asset_id=int(asset_id),
                errors=("asset_not_found",),
            )
        approval_status = str(getattr(asset, "status", "") or "").lower()
        if approval_status != "approved":
            return CommerceRegistrationResult(
                success=False,
                asset_id=int(asset_id),
                errors=("asset_not_approved",),
            )

        profile = content_intelligence_profile or self._content_intelligence_profile(asset_id)
        policy_decision = self.entry_policy.can_register_commerce(
            asset,
            approval_identity=request.approval_identity,
            content_intelligence_profile=profile,
        )
        if not policy_decision.allowed:
            return CommerceRegistrationResult(
                success=False,
                asset_id=int(asset_id),
                errors=policy_decision.reasons,
                warnings=(
                    f"provenance:{policy_decision.provenance_classification}"
                    if policy_decision.provenance_classification
                    else "provenance:missing"
                ),
            )
        intelligence_status = self._profile_status(profile)
        intelligence_ready = bool(getattr(profile, "ready", False))
        if not intelligence_ready:
            record = self._build_blocked_record(
                asset=asset,
                request=replace(
                    request,
                    content_intelligence_status=intelligence_status,
                    content_intelligence_ready=False,
                ),
                profile=profile,
            )
            record = self.registration_repository.upsert_record(record)
            return CommerceRegistrationResult.from_record(record)

        projection = self._project_business_relationships(asset, request)
        record = BusinessAssetRecord(
            registration_id=BusinessAssetRecord.deterministic_id(asset_id),
            asset_id=int(asset_id),
            creator_profile_id=request.creator_profile_id
            if request.creator_profile_id is not None
            else getattr(asset, "creator_profile_id", None),
            approval_status=approval_status,
            content_intelligence_status=intelligence_status,
            content_intelligence_ready=True,
            commerce_registration_status=CommerceRegistrationStatus.REGISTERED,
            business_lifecycle_state=(
                existing.business_lifecycle_state
                if existing and existing.selected_commerce_destination
                else BusinessAssetLifecycleState.AWAITING_DESTINATION
            ),
            commerce_destination_status=(
                existing.commerce_destination_status
                if existing and existing.selected_commerce_destination
                else CommerceDestinationStatus.AWAITING_DESTINATION
            ),
            selected_commerce_destination=(
                existing.selected_commerce_destination if existing else None
            ),
            destination_selected_at=(
                existing.destination_selected_at if existing else None
            ),
            destination_selected_by_profile_id=(
                existing.destination_selected_by_profile_id if existing else None
            ),
            destination_source_workflow=(
                existing.destination_source_workflow if existing else None
            ),
            destination_routing_state=(
                existing.destination_routing_state if existing else None
            ),
            destination_change_note=(
                existing.destination_change_note if existing else None
            ),
            destination_revision=existing.destination_revision if existing else 0,
            product_ids=projection["product_ids"],
            experience_ids=projection["experience_ids"],
            product_draft_ids=projection["product_draft_ids"],
            delivery_type=projection["delivery_type"],
            delivery_type_source=projection["delivery_type_source"],
            delivery_type_requires_review=projection["delivery_type_requires_review"],
            commerce_intelligence_refs=projection["commerce_intelligence_refs"],
            publishing_readiness=projection["publishing_readiness"],
            fulfillment_readiness=projection["fulfillment_readiness"],
            relationship_provenance=projection["relationship_provenance"],
            registration_provenance=self._registration_provenance(
                request,
                profile=profile,
                projection=projection,
            ),
            missing_requirements=(),
            warnings=projection["warnings"],
            registered_at=existing.registered_at if existing else utc_now(),
            last_refreshed_at=utc_now(),
            schema_version=COMMERCE_REGISTRATION_SCHEMA_VERSION,
        )
        record = self.registration_repository.upsert_record(record)
        return CommerceRegistrationResult.from_record(record)

    def get_business_asset(self, asset_id: int) -> BusinessAssetRecord | None:
        return self.registration_repository.get_by_asset_id(asset_id)

    def get_commerce_readiness(self, asset_id: int) -> CommerceReadiness | None:
        record = self.get_business_asset(asset_id)
        return record.commerce_readiness if record else None

    def refresh_registration_projections(
        self,
        asset_id: int,
    ) -> CommerceRegistrationResult:
        existing = self.registration_repository.get_by_asset_id(asset_id)
        if existing is None:
            return self.register_asset(asset_id, force_refresh=True)
        request = CommerceRegistrationRequest(
            asset_id=asset_id,
            creator_profile_id=existing.creator_profile_id,
            content_intelligence_status=existing.content_intelligence_status,
            content_intelligence_ready=existing.content_intelligence_ready,
            commerce_intelligence_refs=existing.commerce_intelligence_refs,
            source_workflow=str(
                existing.registration_provenance.get("source_workflow")
                or "commerce_registration_refresh"
            ),
            approval_identity=existing.registration_provenance.get("approval_identity")
            if isinstance(existing.registration_provenance.get("approval_identity"), Mapping)
            else {},
            creator_intent=existing.registration_provenance.get("creator_intent")
            if isinstance(existing.registration_provenance.get("creator_intent"), Mapping)
            else {},
            idempotency_key=str(
                existing.registration_provenance.get("idempotency_key")
                or f"commerce-registration:{asset_id}"
            ),
        )
        return self.register_asset(asset_id, request=request, force_refresh=True)

    def list_registered_assets(self, *, limit: int = 500) -> tuple[BusinessAssetRecord, ...]:
        return tuple(self.registration_repository.list_registered(limit=limit))

    def list_assets_awaiting_destination(
        self,
        *,
        limit: int = 500,
    ) -> tuple[BusinessAssetRecord, ...]:
        return tuple(self.registration_repository.list_awaiting_destination(limit=limit))

    def list_assets_blocked_by_incomplete_intelligence(
        self,
        *,
        limit: int = 500,
    ) -> tuple[BusinessAssetRecord, ...]:
        return tuple(
            self.registration_repository.list_blocked_by_incomplete_intelligence(
                limit=limit,
            )
        )

    def linked_product_ids(self, asset_id: int) -> tuple[str, ...]:
        record = self.get_business_asset(asset_id)
        return record.product_ids if record else ()

    def linked_experience_ids(self, asset_id: int) -> tuple[str, ...]:
        record = self.get_business_asset(asset_id)
        return record.experience_ids if record else ()

    def backfill_approved_assets(self, *, limit: int = 500) -> tuple[CommerceRegistrationResult, ...]:
        assets = self.asset_repository.search_assets(
            status="approved",
            eligible_only=False,
            limit=limit,
        )
        results: list[CommerceRegistrationResult] = []
        for asset in assets:
            results.append(self.register_asset(int(getattr(asset, "id"))))
        return tuple(results)

    def _build_blocked_record(
        self,
        *,
        asset: Any,
        request: CommerceRegistrationRequest,
        profile: Any | None,
    ) -> BusinessAssetRecord:
        missing = tuple(
            str(item)
            for item in (
                getattr(profile, "missing_components", None)
                or ("content_intelligence_complete",)
            )
            if str(item).strip()
        )
        return BusinessAssetRecord(
            registration_id=BusinessAssetRecord.deterministic_id(request.asset_id),
            asset_id=request.asset_id,
            creator_profile_id=request.creator_profile_id
            if request.creator_profile_id is not None
            else getattr(asset, "creator_profile_id", None),
            approval_status=str(getattr(asset, "status", "") or "").lower(),
            content_intelligence_status=request.content_intelligence_status,
            content_intelligence_ready=False,
            commerce_registration_status=CommerceRegistrationStatus.BLOCKED,
            business_lifecycle_state=BusinessAssetLifecycleState.INTELLIGENCE_PENDING,
            commerce_destination_status=CommerceDestinationStatus.NOT_READY,
            commerce_intelligence_refs=dict(request.commerce_intelligence_refs or {}),
            relationship_provenance={
                "source": "commerce_registration",
                "blocked_before_projection": True,
            },
            registration_provenance=self._registration_provenance(
                request,
                profile=profile,
                projection={},
            ),
            missing_requirements=missing,
            warnings=("content_intelligence_not_ready",),
            error_code="content_intelligence_incomplete",
            error_message=getattr(profile, "error_message", None),
            last_refreshed_at=utc_now(),
            schema_version=COMMERCE_REGISTRATION_SCHEMA_VERSION,
        )

    def _project_business_relationships(
        self,
        asset: Any,
        request: CommerceRegistrationRequest,
    ) -> dict[str, Any]:
        warnings: list[str] = []
        product_ids, products, product_provenance = self._project_products(
            asset,
            request,
            warnings=warnings,
        )
        experience_ids, experience_provenance = self._project_experiences(
            request.asset_id,
            product_ids,
            warnings=warnings,
        )
        delivery = self._resolve_delivery_type(
            products,
            request,
            warnings=warnings,
        )
        publishing_readiness = self._project_publishing_readiness(asset)
        return {
            "product_ids": product_ids,
            "experience_ids": experience_ids,
            "product_draft_ids": self._draft_product_ids(products),
            "delivery_type": delivery["delivery_type"],
            "delivery_type_source": delivery["source"],
            "delivery_type_requires_review": delivery["requires_review"],
            "commerce_intelligence_refs": dict(request.commerce_intelligence_refs or {}),
            "publishing_readiness": publishing_readiness,
            "fulfillment_readiness": {
                "status": "not_evaluated",
                "source": "CommerceRegistrationService",
                "owns_fulfillment": False,
            },
            "relationship_provenance": {
                "products": product_provenance,
                "experiences": experience_provenance,
                "delivery_type": {
                    "source": delivery["source"],
                    "owns_delivery_type": False,
                },
                "publishing": {
                    "source": "PublishingService",
                    "owns_publishing_state": False,
                    "execution": "not_run",
                },
            },
            "warnings": tuple(dict.fromkeys(warnings)),
        }

    def _project_products(
        self,
        asset: Any,
        request: CommerceRegistrationRequest,
        *,
        warnings: list[str],
    ) -> tuple[tuple[str, ...], tuple[Any, ...], dict[str, Any]]:
        ids: list[str] = [str(item) for item in request.existing_product_ids]
        provenance: dict[str, Any] = {
            "sources": [],
            "owns_product_membership": False,
        }
        list_ids = getattr(self.product_asset_repository, "list_product_ids_for_asset", None)
        if callable(list_ids):
            try:
                for product_id in list_ids(request.asset_id):
                    ids.append(str(product_id))
                provenance["sources"].append("ProductAssetRepository")
            except Exception as error:
                warnings.append(f"product_asset_projection_failed:{error}")
        get_legacy = getattr(self.product_repository, "get_by_legacy_content_item_id", None)
        legacy_product = None
        if callable(get_legacy):
            try:
                legacy_product = get_legacy(request.asset_id)
                if legacy_product is not None:
                    ids.append(str(getattr(legacy_product, "id")))
                    provenance["sources"].append("ProductRepository.legacy_content_item")
            except Exception as error:
                warnings.append(f"legacy_product_projection_failed:{error}")
        product_ids = self._dedupe(ids)
        products = [legacy_product] if legacy_product is not None else []
        get_by_id = getattr(self.product_repository, "get_by_id", None)
        if callable(get_by_id):
            for product_id in product_ids:
                if legacy_product is not None and str(getattr(legacy_product, "id", "")) == product_id:
                    continue
                try:
                    products.append(get_by_id(UUID(product_id)))
                except (ValueError, TypeError):
                    try:
                        products.append(get_by_id(product_id))
                    except Exception as error:
                        warnings.append(f"product_lookup_failed:{product_id}:{error}")
                except Exception as error:
                    warnings.append(f"product_lookup_failed:{product_id}:{error}")
        products = tuple(product for product in products if product is not None)
        provenance["product_count"] = len(product_ids)
        return product_ids, products, provenance

    def _project_experiences(
        self,
        asset_id: int,
        product_ids: Iterable[str],
        *,
        warnings: list[str],
    ) -> tuple[tuple[str, ...], dict[str, Any]]:
        ids: list[str] = []
        relationships: list[dict[str, Any]] = []
        list_relationships = getattr(self.experience_service, "list_asset_relationships", None)
        if callable(list_relationships):
            try:
                for relationship in list_relationships(asset_id):
                    experience_id = str(getattr(relationship, "experience_id"))
                    ids.append(experience_id)
                    relationships.append(
                        {
                            "experience_id": experience_id,
                            "source": str(getattr(relationship, "source", "experience")),
                            "compatibility": bool(getattr(relationship, "compatibility", False)),
                            "owns_experience_membership": False,
                        }
                    )
            except Exception as error:
                warnings.append(f"experience_projection_failed:{error}")
        if not ids:
            for product_id in product_ids:
                ids.append(f"product:{product_id}")
                relationships.append(
                    {
                        "experience_id": f"product:{product_id}",
                        "source": "products.product_assets",
                        "compatibility": True,
                        "owns_experience_membership": False,
                    }
                )
        return self._dedupe(ids), {
            "relationships": relationships,
            "owns_experience_membership": False,
        }

    def _resolve_delivery_type(
        self,
        products: Iterable[Any],
        request: CommerceRegistrationRequest,
        *,
        warnings: list[str],
    ) -> dict[str, Any]:
        for product in products:
            try:
                delivery_type = resolve_product_delivery_type(
                    getattr(product, "delivery_type", None),
                    getattr(product, "metadata", None),
                )
                return {
                    "delivery_type": delivery_type.value,
                    "source": f"product:{getattr(product, 'id', 'unknown')}",
                    "requires_review": False,
                }
            except Exception:
                continue
        if request.delivery_type_recommendation:
            return {
                "delivery_type": str(request.delivery_type_recommendation),
                "source": "commerce_intelligence_recommendation",
                "requires_review": True,
            }
        warnings.append("delivery_type_unresolved")
        return {
            "delivery_type": None,
            "source": None,
            "requires_review": True,
        }

    def _project_publishing_readiness(self, asset: Any) -> dict[str, Any]:
        try:
            record = self.publishing_service.project_legacy_asset_record(asset)
            status, detail = self.publishing_service.get_provider_status_display(
                record,
                provider_name="Provider",
                missing_detail="No local asset is attached.",
                local_detail="Local asset only",
            )
            return {
                "status": status,
                "detail": detail,
                "record": record,
                "source": "PublishingService",
                "execution": "not_run",
                "owns_publishing_state": False,
            }
        except Exception as error:
            return {
                "status": "unknown",
                "detail": str(error),
                "source": "PublishingService",
                "execution": "not_run",
                "owns_publishing_state": False,
            }

    @staticmethod
    def _draft_product_ids(products: Iterable[Any]) -> tuple[str, ...]:
        draft_ids: list[str] = []
        for product in products:
            status = getattr(product, "status", None)
            status_value = getattr(status, "value", status)
            metadata = getattr(product, "metadata", None) or {}
            if status_value == ProductStatus.DRAFT.value or metadata.get("product_draft"):
                draft_ids.append(str(getattr(product, "id")))
        return tuple(dict.fromkeys(draft_ids))

    def _content_intelligence_profile(self, asset_id: int) -> Any | None:
        get_by_asset = getattr(self.content_intelligence_repository, "get_by_asset_id", None)
        if not callable(get_by_asset):
            return None
        return get_by_asset(asset_id)

    @staticmethod
    def _profile_status(profile: Any | None) -> str:
        if profile is None:
            return "MISSING"
        status = getattr(profile, "status", None)
        return str(getattr(status, "value", status) or "UNKNOWN")

    @staticmethod
    def _coerce_request(
        asset_id: int,
        request: CommerceRegistrationRequest | None,
        values: Mapping[str, Any],
    ) -> CommerceRegistrationRequest:
        if request is not None:
            return request
        return CommerceRegistrationRequest(asset_id=int(asset_id), **dict(values))

    @staticmethod
    def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(str(value) for value in values if str(value).strip()))

    @staticmethod
    def _registration_provenance(
        request: CommerceRegistrationRequest,
        *,
        profile: Any | None,
        projection: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "source_workflow": request.source_workflow,
            "approval_identity": dict(request.approval_identity or {}),
            ASSET_PROVENANCE_METADATA_KEY: provenance_context(
                AssetProvenanceClassification.CREATOR_APPROVAL,
                source="CommerceRegistrationService",
                source_workflow=request.source_workflow,
                metadata={"idempotency_key": request.idempotency_key},
            ),
            "creator_intent": dict(request.creator_intent or {}),
            "idempotency_key": request.idempotency_key,
            "registration_boundary": "CommerceRegistrationService",
            "content_intelligence_profile_id": getattr(profile, "profile_id", None),
            "projection_sources": dict(projection.get("relationship_provenance") or {}),
            "schema_version": COMMERCE_REGISTRATION_SCHEMA_VERSION,
            "registered_at": utc_now(),
        }
