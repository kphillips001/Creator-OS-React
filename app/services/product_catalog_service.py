"""Application service for Product Catalog management."""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg.errors import UniqueViolation

from app.database import get_db_connection
from app.models.asset import Asset
from app.models.experience import Experience
from app.models.experience import ExperiencePublishingReadiness
from app.models.product import (
    Product,
    ProductApprovalStatus,
    ProductDeliveryType,
    ProductStatus,
    ProductType,
    normalize_product_delivery_type,
)
from app.models.product_asset import ProductAsset
from app.repositories.experience_repository import ExperienceRepository
from app.repositories.asset_repository import AssetRepository
from app.repositories.customer_entitlement_repository import (
    CustomerEntitlementRepository,
)
from app.repositories.product_asset_repository import ProductAssetRepository
from app.repositories.product_repository import ProductRepository
from app.services.publishing_state_service import (
    has_fanvue_media,
    product_has_provider_url,
)
from app.services.ai_product_drafting_service import AIProductDraftingService
from app.services.experience_service import ExperienceService
from app.services.media_processing_service import MediaProcessingService
from app.services.publishing_service import PublishingService
from app.services.runtime_media_resolver import RuntimeMediaResolver


class ProductCatalogError(Exception):
    """Base catalog application error."""


class ProductCatalogValidationError(ProductCatalogError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class ProductCatalogNotFoundError(ProductCatalogError):
    pass


@dataclass(frozen=True)
class ProductCatalogCommand:
    creator_profile_id: int
    internal_name: str
    display_name: str
    description: str | None
    product_type: ProductType
    price_cents: int | None
    currency: str = "USD"
    media_link: str | None = None
    delivery_type: ProductDeliveryType | str | None = None
    tags: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    asset_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ProductEditorData:
    product: Product
    product_assets: tuple[ProductAsset, ...]
    assets: tuple[Asset, ...]
    experience: Experience | None
    entitlement_count: int


@dataclass(frozen=True)
class ProductCatalogPublishingSummary:
    status: str
    detail: str


@dataclass(frozen=True)
class ProductCatalogAssetDisplay:
    asset: Asset
    thumbnail_path: str | None
    publishing: ProductCatalogPublishingSummary
    upload_visible: bool
    upload_enabled: bool
    upload_note: str
    original_media_path: str | None


@dataclass(frozen=True)
class ProductCatalogExperiencePresentation:
    experience_id: str | None
    experience_type: str | None
    title: str | None
    summary: str | None
    cover_asset_id: int | None
    asset_ids: tuple[int, ...]
    themes: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    mood: str | None = None
    story_progression: str | None = None
    technical_continuity: str | None = None
    relationship_source: str | None = None
    compatibility: bool = False
    publishing_readiness: ExperiencePublishingReadiness | None = None


@dataclass(frozen=True)
class ProductCatalogDisplayModel:
    product: Product
    product_assets: tuple[ProductAsset, ...]
    experience: Experience | None
    ordered_assets: tuple[Asset, ...]
    cover_asset: Asset | None
    preview_asset: Asset | None
    thumbnail_path: str | None
    publishing: ProductCatalogPublishingSummary
    asset_displays: tuple[ProductCatalogAssetDisplay, ...]
    classification_label: str
    experience_presentation: ProductCatalogExperiencePresentation | None = None


@dataclass(frozen=True)
class ProductDeleteResult:
    product: Product
    product_asset_links_deleted: int
    assets_archived: int
    fanvue_cleanup_required: bool


class ProductCatalogService:
    TRANSITIONS = {
        ProductStatus.DRAFT: {ProductStatus.ACTIVE, ProductStatus.ARCHIVED},
        ProductStatus.ACTIVE: {ProductStatus.DISABLED},
        ProductStatus.DISABLED: {
            ProductStatus.ACTIVE,
            ProductStatus.ARCHIVED,
        },
        ProductStatus.ARCHIVED: set(),
    }

    def __init__(
        self,
        product_repository: ProductRepository | None = None,
        product_asset_repository: ProductAssetRepository | None = None,
        asset_repository: AssetRepository | None = None,
        entitlement_repository: CustomerEntitlementRepository | None = None,
        experience_service: ExperienceService | None = None,
        media_processing_service: MediaProcessingService | None = None,
        runtime_media_resolver: RuntimeMediaResolver | None = None,
        publishing_service: PublishingService | None = None,
        content_opportunity_service=None,
        connection_factory=get_db_connection,
    ):
        self.products = product_repository or ProductRepository()
        # Compatibility storage only: ProductAssetRepository is injected into
        # ExperienceService so Catalog callers use Experience composition APIs.
        self.product_assets = product_asset_repository or ProductAssetRepository()
        self.assets = asset_repository or AssetRepository()
        self.entitlements = (
            entitlement_repository or CustomerEntitlementRepository()
        )
        self.experiences = experience_service or ExperienceService(
            ExperienceRepository(
                product_repository=self.products,
                product_asset_repository=self.product_assets,
            )
        )
        self.media_processing = media_processing_service or MediaProcessingService()
        self.runtime_media_resolver = (
            runtime_media_resolver or RuntimeMediaResolver()
        )
        self.publishing = publishing_service or PublishingService()
        self.content_opportunity_service = content_opportunity_service
        self._connection_factory = connection_factory

    @staticmethod
    def _dedupe(values, *, lower: bool) -> tuple[str, ...]:
        normalized = []
        seen = set()
        for value in values or ():
            clean = str(value).strip()
            if not clean:
                continue
            clean = clean.lower() if lower else clean
            key = clean.lower()
            if key not in seen:
                seen.add(key)
                normalized.append(clean)
        return tuple(normalized)

    def normalize_command(self, command: ProductCatalogCommand):
        return replace(
            command,
            internal_name=command.internal_name.strip(),
            display_name=command.display_name.strip(),
            description=(command.description or "").strip() or None,
            currency=(command.currency or "USD").strip().upper(),
            media_link=(command.media_link or "").strip() or None,
            delivery_type=normalize_product_delivery_type(
                command.delivery_type
            ),
            tags=self._dedupe(command.tags, lower=True),
            themes=self._dedupe(command.themes, lower=False),
            asset_ids=tuple(int(asset_id) for asset_id in command.asset_ids),
        )

    def validate_command(
        self,
        command: ProductCatalogCommand,
        *,
        activation: bool,
        existing_product_id: UUID | None = None,
        connection=None,
    ) -> tuple[ProductCatalogCommand, list[Asset]]:
        command = self.normalize_command(command)
        errors = []
        if not command.creator_profile_id:
            errors.append("Creator profile is required.")
        if not command.internal_name:
            errors.append("Internal name is required.")
        if not command.display_name:
            errors.append("Display name is required.")
        if len(command.currency) != 3 or not command.currency.isalpha():
            errors.append("Currency must contain exactly three letters.")
        if command.price_cents is not None and command.price_cents < 0:
            errors.append("Price cannot be negative.")
        if len(set(command.asset_ids)) != len(command.asset_ids):
            errors.append("The same asset cannot be assigned more than once.")

        # A.2 compatibility boundary: Product validation needs media type and
        # Product composition context. Keep the broad Asset model here until
        # Product owns its required Asset contract separately.
        assets = self.assets.list_by_ids(
            command.asset_ids,
            connection=connection,
        )
        if len(assets) != len(command.asset_ids):
            errors.append("One or more selected assets no longer exist.")

        if self.products.internal_name_exists(
            command.internal_name,
            excluding_product_id=existing_product_id,
        ):
            errors.append("Internal name is already in use.")

        if activation:
            if command.price_cents is None:
                errors.append("Active products require a price.")
            errors.extend(self._validate_asset_cardinality(command, assets))

        if errors:
            raise ProductCatalogValidationError(errors)
        return command, assets

    @staticmethod
    def _validate_asset_cardinality(
        command: ProductCatalogCommand,
        assets: list[Asset],
    ) -> list[str]:
        asset_types = [asset.media_type for asset in assets]
        product_type = command.product_type
        if product_type == ProductType.SINGLE_IMAGE:
            return [] if asset_types == ["image"] else [
                "SINGLE_IMAGE requires exactly one image asset."
            ]
        if product_type == ProductType.SINGLE_VIDEO:
            return [] if asset_types == ["video"] else [
                "SINGLE_VIDEO requires exactly one video asset."
            ]
        if product_type == ProductType.PHOTO_SET:
            return [] if len(assets) >= 2 and set(asset_types) == {"image"} else [
                "PHOTO_SET requires at least two image assets."
            ]
        if product_type == ProductType.VIDEO_SET:
            return [] if len(assets) >= 2 and set(asset_types) == {"video"} else [
                "VIDEO_SET requires at least two video assets."
            ]
        return [] if assets else [f"{product_type.value} requires at least one asset."]

    def create_product(
        self,
        command: ProductCatalogCommand,
        *,
        activate: bool = False,
    ) -> ProductEditorData:
        status = ProductStatus.ACTIVE if activate else ProductStatus.DRAFT
        try:
            with self._connection_factory() as conn:
                command, assets = self.validate_command(
                    command,
                    activation=activate,
                    connection=conn,
                )
                product = self.products.create_product(
                    creator_profile_id=command.creator_profile_id,
                    internal_name=command.internal_name,
                    display_name=command.display_name,
                    description=command.description,
                    product_type=command.product_type,
                    status=status,
                    price_cents=command.price_cents,
                    currency=command.currency,
                    media_link=command.media_link,
                    delivery_type=command.delivery_type,
                    tags=command.tags,
                    themes=command.themes,
                    connection=conn,
                )
                links = self.experiences.replace_product_experience_assets(
                    product.id,
                    command.asset_ids,
                    connection=conn,
                )
        except UniqueViolation as error:
            raise ProductCatalogValidationError(
                ["Internal name is already in use."]
            ) from error
        editor = self._editor_data(product, links, assets, 0)
        if status == ProductStatus.ACTIVE:
            self._notify_content_opportunity_product_available(editor)
        return editor

    def update_product(
        self,
        product_id: UUID,
        command: ProductCatalogCommand,
        *,
        activate: bool = False,
    ) -> ProductEditorData:
        existing = self.products.get_by_id(
            product_id,
            creator_profile_id=command.creator_profile_id,
        )
        if not existing:
            raise ProductCatalogNotFoundError("Product was not found.")
        if existing.status == ProductStatus.ARCHIVED:
            raise ProductCatalogValidationError(
                ["Archived products are read-only."]
            )
        target_status = ProductStatus.ACTIVE if activate else existing.status
        if activate and target_status not in self.TRANSITIONS[existing.status]:
            raise ProductCatalogValidationError(
                [f"{existing.status.value} cannot transition to ACTIVE."]
            )
        current_links = self.experiences.list_product_experience_assets(
            product_id
        )
        entitlement_count = self.entitlements.count_for_product(product_id)
        if entitlement_count:
            immutable_errors = []
            if command.internal_name.strip() != existing.internal_name:
                immutable_errors.append(
                    "Internal name cannot change after an entitlement exists."
                )
            if command.product_type != existing.product_type:
                immutable_errors.append(
                    "Product type cannot change after an entitlement exists."
                )
            current_experience = self.project_product_experience(
                existing,
                current_links,
            )
            if tuple(command.asset_ids) != self.experiences.get_ordered_asset_ids(
                current_experience
            ):
                immutable_errors.append(
                    "Asset composition cannot change after an entitlement exists."
                )
            if immutable_errors:
                raise ProductCatalogValidationError(immutable_errors)

        try:
            with self._connection_factory() as conn:
                command, assets = self.validate_command(
                    command,
                    activation=target_status == ProductStatus.ACTIVE,
                    existing_product_id=product_id,
                    connection=conn,
                )
                product = self.products.update_product(
                    product_id=product_id,
                    creator_profile_id=command.creator_profile_id,
                    internal_name=command.internal_name,
                    display_name=command.display_name,
                    description=command.description,
                    product_type=command.product_type,
                    status=target_status,
                    price_cents=command.price_cents,
                    currency=command.currency,
                    media_link=command.media_link,
                    delivery_type=command.delivery_type,
                    tags=command.tags,
                    themes=command.themes,
                    connection=conn,
                )
                links = self.experiences.replace_product_experience_assets(
                    product_id,
                    command.asset_ids,
                    connection=conn,
                )
        except UniqueViolation as error:
            raise ProductCatalogValidationError(
                ["Internal name is already in use."]
            ) from error
        if not product:
            raise ProductCatalogNotFoundError("Product was not found.")
        editor = self._editor_data(product, links, assets, entitlement_count)
        if target_status == ProductStatus.ACTIVE:
            self._notify_content_opportunity_product_available(editor)
        return editor

    def reset_product_commerce_to_ai(
        self,
        product_id: UUID,
        creator_profile_id: int,
        *,
        fields: tuple[str, ...] = ("price", "delivery_type", "product_type"),
    ) -> ProductEditorData:
        """Reset supported Product commerce fields to stored AI recommendations."""

        editor = self.load_editor(product_id, creator_profile_id)
        product = editor.product
        commerce = self._commerce_intelligence_metadata(product)
        if not commerce:
            raise ProductCatalogValidationError(
                ["No AI Commerce Intelligence recommendation is available."]
            )

        requested_fields = tuple(dict.fromkeys(fields))
        unsupported = [
            field
            for field in requested_fields
            if field not in {"price", "delivery_type", "product_type"}
        ]
        if unsupported:
            raise ProductCatalogValidationError(
                [
                    "Unsupported commerce reset field(s): "
                    + ", ".join(sorted(unsupported))
                ]
            )

        price = commerce.get("price") or {}
        price_cents = product.price_cents
        delivery_type = product.delivery_type
        product_type = product.product_type
        if "price" in requested_fields:
            price_cents = price.get("suggested_price_cents")
        if "delivery_type" in requested_fields and commerce.get("delivery_type"):
            delivery_type = ProductDeliveryType(
                str(commerce["delivery_type"]).upper()
            )
        if "product_type" in requested_fields and commerce.get("product_type"):
            product_type = ProductType(str(commerce["product_type"]).upper())

        command = ProductCatalogCommand(
            creator_profile_id=creator_profile_id,
            internal_name=product.internal_name,
            display_name=product.display_name,
            description=product.description,
            product_type=product_type,
            price_cents=price_cents,
            currency=product.currency,
            media_link=product.media_link,
            delivery_type=delivery_type,
            tags=product.tags,
            themes=product.themes,
            asset_ids=self.experiences.get_ordered_asset_ids(editor.experience),
        )
        return self.update_product(product_id, command)

    def approve_product(
        self,
        product_id: UUID,
        creator_profile_id: int,
        *,
        reviewed_by: str | None = None,
        notes: str | None = None,
    ) -> ProductEditorData:
        """Persist creator approval without executing publishing."""

        editor = self.load_editor(product_id, creator_profile_id)
        status = (
            ProductApprovalStatus.READY_TO_PUBLISH
            if self._editor_ready_to_publish(editor)
            else ProductApprovalStatus.APPROVED
        )
        product = self.products.update_approval_metadata(
            product_id=product_id,
            creator_profile_id=creator_profile_id,
            approval_status=status,
            reviewed_by=reviewed_by,
            notes=notes,
        )
        if not product:
            raise ProductCatalogNotFoundError("Product was not found.")
        self._ensure_publishing_job_for_approved_product(
            product,
            editor.assets,
            approval_status=status,
        )
        return self.load_editor(product.id, creator_profile_id)

    def _ensure_publishing_job_for_approved_product(
        self,
        product: Product,
        assets,
        *,
        approval_status: ProductApprovalStatus,
    ) -> None:
        """Queue approved Products for provider execution via PublishingService."""

        ensure_job = getattr(self.publishing, "ensure_product_publishing_job", None)
        if not callable(ensure_job):
            return
        asset = assets[0] if assets else None
        asset_id = getattr(asset, "id", None) or product.legacy_content_item_id
        provider_account_id = getattr(asset, "fanvue_account_id", None)
        ensure_job(
            product_id=product.id,
            asset_id=asset_id,
            provider_account_id=provider_account_id,
            media_link_required=True,
            provider_metadata={
                "source": "ProductCatalogService.approve_product",
                "approval_status": approval_status.value,
            },
        )

    def mark_product_needs_review(
        self,
        product_id: UUID,
        creator_profile_id: int,
        *,
        reviewed_by: str | None = None,
        notes: str | None = None,
    ) -> ProductEditorData:
        """Persist that a Product remains in creator review."""

        product = self.products.update_approval_metadata(
            product_id=product_id,
            creator_profile_id=creator_profile_id,
            approval_status=ProductApprovalStatus.NEEDS_REVIEW,
            reviewed_by=reviewed_by,
            notes=notes,
        )
        if not product:
            raise ProductCatalogNotFoundError("Product was not found.")
        return self.load_editor(product.id, creator_profile_id)

    def reject_product(
        self,
        product_id: UUID,
        creator_profile_id: int,
        *,
        reviewed_by: str | None = None,
        notes: str | None = None,
    ) -> ProductEditorData:
        """Persist that a Product is not approved for publishing."""

        product = self.products.update_approval_metadata(
            product_id=product_id,
            creator_profile_id=creator_profile_id,
            approval_status=ProductApprovalStatus.REJECTED,
            reviewed_by=reviewed_by,
            notes=notes,
        )
        if not product:
            raise ProductCatalogNotFoundError("Product was not found.")
        return self.load_editor(product.id, creator_profile_id)

    def save_media_link(
        self,
        product_id: UUID,
        creator_profile_id: int,
        media_link: str | None,
    ) -> Product:
        product = self.products.get_by_id(
            product_id,
            creator_profile_id=creator_profile_id,
        )
        if not product:
            raise ProductCatalogNotFoundError("Product was not found.")
        if product.status == ProductStatus.ARCHIVED:
            raise ProductCatalogValidationError(
                ["Archived products are read-only."]
            )

        normalized_link = (media_link or "").strip() or None
        updated = self.products.update_media_link(
            product_id=product_id,
            creator_profile_id=creator_profile_id,
            media_link=normalized_link,
        )
        if not updated:
            raise ProductCatalogNotFoundError("Product was not found.")
        return updated

    def find_product_by_media_link(
        self,
        media_link: str,
        *,
        creator_profile_id: int | None = None,
    ) -> Product | None:
        normalized_link = (media_link or "").strip()
        if not normalized_link:
            return None
        return self.products.get_by_media_link(
            normalized_link,
            creator_profile_id=creator_profile_id,
        )

    def validate_media_link_ownership(
        self,
        *,
        product_id: UUID,
        creator_profile_id: int,
        media_link: str,
    ) -> Product:
        product = self.products.get_by_id(
            product_id,
            creator_profile_id=creator_profile_id,
        )
        if not product:
            raise ProductCatalogNotFoundError("Product was not found.")
        existing = self.find_product_by_media_link(
            media_link,
            creator_profile_id=creator_profile_id,
        )
        if existing and existing.id != product_id:
            raise ProductCatalogValidationError(
                ["Media link already belongs to another Product."]
            )
        return product

    def complete_publishing_media_link(
        self,
        *,
        product_id: UUID,
        creator_profile_id: int,
        media_link: str,
    ) -> Product:
        self.validate_media_link_ownership(
            product_id=product_id,
            creator_profile_id=creator_profile_id,
            media_link=media_link,
        )
        updated = self.save_media_link(
            product_id,
            creator_profile_id,
            media_link,
        )
        if updated.status == ProductStatus.ACTIVE:
            return updated
        return self.transition_status(
            product_id,
            creator_profile_id,
            ProductStatus.ACTIVE,
        )

    def transition_status(
        self,
        product_id: UUID,
        creator_profile_id: int,
        target: ProductStatus,
    ) -> Product:
        editor = self.load_editor(product_id, creator_profile_id)
        product = editor.product
        if target not in self.TRANSITIONS[product.status]:
            raise ProductCatalogValidationError(
                [f"{product.status.value} cannot transition to {target.value}."]
            )
        command = ProductCatalogCommand(
            creator_profile_id=creator_profile_id,
            internal_name=product.internal_name,
            display_name=product.display_name,
            description=product.description,
            product_type=product.product_type,
            price_cents=product.price_cents,
            currency=product.currency,
            media_link=product.media_link,
            delivery_type=product.delivery_type,
            tags=product.tags,
            themes=product.themes,
            asset_ids=self.experiences.get_ordered_asset_ids(editor.experience),
        )
        with self._connection_factory() as conn:
            command, _ = self.validate_command(
                command,
                activation=target == ProductStatus.ACTIVE,
                existing_product_id=product_id,
                connection=conn,
            )
            updated = self.products.update_product(
                product_id=product_id,
                creator_profile_id=creator_profile_id,
                internal_name=command.internal_name,
                display_name=command.display_name,
                description=command.description,
                product_type=command.product_type,
                status=target,
                price_cents=command.price_cents,
                currency=command.currency,
                media_link=command.media_link,
                delivery_type=command.delivery_type,
                tags=command.tags,
                themes=command.themes,
                connection=conn,
            )
        if not updated:
            raise ProductCatalogNotFoundError("Product was not found.")
        return updated

    def delete_product(
        self,
        product_id: UUID,
        creator_profile_id: int,
    ) -> ProductDeleteResult:
        editor = self.load_editor(product_id, creator_profile_id)
        if editor.product.status == ProductStatus.ARCHIVED:
            raise ProductCatalogValidationError(
                ["Product is already archived."]
            )

        asset_ids = self.experiences.get_ordered_asset_ids(editor.experience)
        # Phase 1 behavior archives attached Assets with the Product. Future
        # lifecycle cleanup should let Products retire without owning Assets.
        fanvue_cleanup_required = any(
            has_fanvue_media(asset)
            for asset in editor.assets
        ) or product_has_provider_url(editor.product)

        with self._connection_factory() as conn:
            archived_product = self.products.archive_product(
                product_id=product_id,
                creator_profile_id=creator_profile_id,
                connection=conn,
            )
            if not archived_product:
                raise ProductCatalogNotFoundError("Product was not found.")
            links_deleted = self.experiences.delete_product_experience_assets(
                product_id,
                connection=conn,
            )
            assets_archived = self.assets.archive_assets(
                asset_ids,
                connection=conn,
            )

        return ProductDeleteResult(
            product=archived_product,
            product_asset_links_deleted=links_deleted,
            assets_archived=assets_archived,
            fanvue_cleanup_required=fanvue_cleanup_required,
        )

    def load_editor(
        self,
        product_id: UUID,
        creator_profile_id: int,
    ) -> ProductEditorData:
        product = self.products.get_by_id(
            product_id,
            creator_profile_id=creator_profile_id,
        )
        if not product:
            raise ProductCatalogNotFoundError("Product was not found.")
        links = self.experiences.list_product_experience_assets(product_id)
        experience = self.project_product_experience(product, links)
        # A.4 compatibility boundary: editor data still displays Product and
        # Publishing readiness from attached Assets, but Experience now owns
        # read-side grouping and ordering interpretation.
        assets = self.assets.list_by_ids(
            self.experiences.get_ordered_asset_ids(experience)
        )
        return ProductEditorData(
            product=product,
            product_assets=tuple(links),
            assets=tuple(self.order_assets_for_experience(experience, assets)),
            experience=experience,
            entitlement_count=self.entitlements.count_for_product(product_id),
        )

    def project_product_experience(
        self,
        product: Product,
        product_assets,
    ) -> Experience:
        return self.experiences.build_product_experience(
            product,
            product_assets,
        )

    def order_assets_for_experience(
        self,
        experience: Experience | None,
        assets,
    ) -> tuple[Asset, ...]:
        return self.experiences.order_assets_for_experience(
            experience,
            assets,
        )

    def cover_asset_for_experience(
        self,
        experience: Experience | None,
        assets,
    ) -> Asset | None:
        return self.experiences.cover_asset_for_experience(
            experience,
            assets,
        )

    def resolve_existing_media_path(self, value: str | Path | None) -> Path | None:
        if not value:
            return None
        path = Path(value)
        candidates = [
            path,
            Path.cwd() / path,
            Path("data/uploads") / path.name,
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def resolve_runtime_original_asset_path(self, asset: Asset | Any) -> Path | None:
        if not asset:
            return None
        resolved = self.runtime_media_resolver.resolve_original(
            asset,
            require_exists=True,
        )
        if resolved.path:
            return resolved.path
        for _, candidate in resolved.candidates:
            compatible_path = self.resolve_existing_media_path(candidate)
            if compatible_path:
                return compatible_path
        return None

    def asset_preview_path(self, asset: Asset | Any) -> str | None:
        if not asset:
            return None
        blurred_preview = self.media_processing.resolve_derivative(
            asset,
            "blurred_preview",
        )
        if blurred_preview:
            return blurred_preview
        if getattr(asset, "media_type", None) == "image":
            original = self.resolve_runtime_original_asset_path(asset)
            if original:
                return str(original)
        return None

    def asset_publishing_summary(
        self,
        asset: Asset | Any,
        *,
        provider_name: str = "Fanvue",
    ) -> ProductCatalogPublishingSummary:
        status, detail = self.publishing.get_provider_status_display(
            self.publishing.project_legacy_asset_record(asset),
            provider_name=provider_name,
        )
        return ProductCatalogPublishingSummary(status=status, detail=detail)

    def product_publishing_summary(
        self,
        product: Product,
        assets,
        *,
        provider_name: str = "Fanvue",
    ) -> ProductCatalogPublishingSummary:
        status, detail = self.publishing.get_product_provider_status_display(
            self.publishing.project_legacy_product_record(product),
            tuple(
                self.publishing.project_legacy_asset_record(asset)
                for asset in assets
            ),
            provider_name=provider_name,
        )
        return ProductCatalogPublishingSummary(status=status, detail=detail)

    def asset_upload_action_state(
        self,
        asset: Asset | Any,
        *,
        provider_name: str = "Fanvue",
    ) -> tuple[bool, bool, str]:
        status = self.asset_publishing_summary(
            asset,
            provider_name=provider_name,
        ).status
        if status == f"Uploaded to {provider_name}":
            return False, False, f"Asset is already uploaded to {provider_name}."
        if not asset:
            return False, False, "No asset is attached."
        if not self.resolve_runtime_original_asset_path(asset):
            return True, False, "Local file could not be found on disk."
        return True, True, f"Upload this local asset to {provider_name} Vault."

    def build_asset_upload_item(self, asset: Asset | Any) -> dict | None:
        local_path = self.resolve_runtime_original_asset_path(asset)
        if not local_path:
            return None
        return {
            "id": asset.id,
            "file_path": str(local_path),
            "classification": asset.classification,
        }

    def build_asset_library_service(self):
        from app.services.asset_library_service import AssetLibraryService

        return AssetLibraryService(
            asset_repository=self.assets,
            runtime_media_resolver=self.runtime_media_resolver,
            media_processing_service=self.media_processing,
            experience_service=self.experiences,
            product_repository=self.products,
            product_asset_repository=self.product_assets,
            publishing_service=self.publishing,
        )

    def load_assets_by_ids(
        self,
        asset_ids: tuple[int, ...] | list[int],
    ) -> tuple[Asset, ...]:
        return tuple(self.assets.list_by_ids(asset_ids))

    def load_asset_by_id(self, asset_id: int) -> Asset | None:
        assets = self.load_assets_by_ids((int(asset_id),))
        return assets[0] if assets else None

    def load_asset_library_items(
        self,
        asset_ids: tuple[int, ...] | list[int],
    ):
        return self.build_asset_library_service().get_asset_items(asset_ids)

    def build_upload_success_payload(
        self,
        upload_result,
        *,
        default_status: str = "uploaded",
    ) -> dict:
        return self.publishing.build_upload_success_payload(
            upload_result,
            default_status=default_status,
        )

    def build_upload_failure_payload(
        self,
        upload_result=None,
        *,
        error=None,
    ) -> dict:
        return self.publishing.build_upload_failure_payload(
            upload_result,
            error=error,
        )

    def classification_label(self, product: Product, assets) -> str:
        metadata = product.metadata or {}
        classification = metadata.get("classification")
        if classification:
            return classification
        classifications = [
            asset.classification for asset in assets if asset.classification
        ]
        if classifications:
            return classifications[0]
        return "—"

    def build_asset_display(self, asset: Asset | Any) -> ProductCatalogAssetDisplay:
        visible, enabled, note = self.asset_upload_action_state(asset)
        original = self.resolve_runtime_original_asset_path(asset)
        return ProductCatalogAssetDisplay(
            asset=asset,
            thumbnail_path=self.asset_preview_path(asset),
            publishing=self.asset_publishing_summary(asset),
            upload_visible=visible,
            upload_enabled=enabled,
            upload_note=note,
            original_media_path=str(original) if original else None,
        )

    def build_experience_presentation(
        self,
        product: Product,
        experience: Experience | None,
        ordered_assets,
    ) -> ProductCatalogExperiencePresentation | None:
        if experience is None:
            return None
        metadata = dict(getattr(experience, "metadata", None) or {})
        product_relationships = self._safe_product_experience_relationships(
            product.id
        )
        relationship = product_relationships[0] if product_relationships else None
        relationship_metadata = dict(getattr(relationship, "metadata", None) or {})
        merged_metadata = {**metadata, **relationship_metadata}
        asset_records = tuple(
            self.publishing.project_legacy_asset_record(asset)
            for asset in ordered_assets
        )
        readiness = self.publishing.project_experience_readiness(
            experience,
            asset_records=asset_records,
        )
        return ProductCatalogExperiencePresentation(
            experience_id=(
                str(experience.experience_id)
                if experience.experience_id is not None
                else None
            ),
            experience_type=getattr(experience.experience_type, "value", None)
            or str(experience.experience_type),
            title=experience.title,
            summary=experience.description,
            cover_asset_id=experience.cover_asset_id,
            asset_ids=tuple(experience.ordered_asset_ids),
            themes=self._metadata_tuple(
                merged_metadata,
                "suggested_themes",
                "themes",
                "experience_themes",
            ),
            keywords=self._metadata_tuple(
                merged_metadata,
                "suggested_keywords",
                "keywords",
                "experience_keywords",
            ),
            mood=self._first_metadata_value(merged_metadata, "mood"),
            story_progression=self._first_metadata_value(
                merged_metadata,
                "story_progression",
            ),
            technical_continuity=self._first_metadata_value(
                merged_metadata,
                "technical_continuity",
            ),
            relationship_source=(
                str(getattr(relationship, "source", "") or "")
                if relationship
                else str(metadata.get("source") or "")
            ),
            compatibility=bool(
                getattr(relationship, "compatibility", False)
                if relationship
                else metadata.get("compatibility", False)
            ),
            publishing_readiness=readiness,
        )

    def _safe_product_experience_relationships(
        self,
        product_id: UUID,
    ) -> tuple[Any, ...]:
        list_relationships = getattr(
            self.experiences,
            "list_product_relationships",
            None,
        )
        if callable(list_relationships):
            try:
                return tuple(list_relationships(product_id))
            except Exception:
                return ()
        return ()

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

    def build_display_model(
        self,
        product: Product,
        links,
        assets,
        experience: Experience | None = None,
    ) -> ProductCatalogDisplayModel:
        experience = experience or self.project_product_experience(
            product,
            links,
        )
        ordered_assets = self.order_assets_for_experience(experience, assets)
        cover_asset = self.cover_asset_for_experience(
            experience,
            ordered_assets,
        )
        preview_asset = cover_asset or (ordered_assets[0] if ordered_assets else None)
        experience_presentation = self.build_experience_presentation(
            product,
            experience,
            ordered_assets,
        )
        return ProductCatalogDisplayModel(
            product=product,
            product_assets=tuple(links),
            experience=experience,
            ordered_assets=ordered_assets,
            cover_asset=cover_asset,
            preview_asset=preview_asset,
            thumbnail_path=self.asset_preview_path(preview_asset),
            publishing=self.product_publishing_summary(product, ordered_assets),
            asset_displays=tuple(
                self.build_asset_display(asset) for asset in ordered_assets
            ),
            classification_label=self.classification_label(
                product,
                ordered_assets,
            ),
            experience_presentation=experience_presentation,
        )

    def load_display_model(self, product: Product) -> ProductCatalogDisplayModel:
        links = self.experiences.list_product_experience_assets(product.id)
        experience = self.project_product_experience(product, links)
        assets = self.assets.list_by_ids(
            self.experiences.get_ordered_asset_ids(experience)
        )
        return self.build_display_model(
            product,
            links,
            assets,
            experience,
        )

    def count_workspace_products(self, creator_profile_id: int) -> dict[str, int]:
        """Return Product status counts for presentation dashboards."""

        return self.products.count_by_status(creator_profile_id)

    def list_workspace_products(
        self,
        *,
        creator_profile_id: int,
        include_archived: bool = True,
        limit: int = 500,
    ) -> tuple[Product, ...]:
        """Return Products for read-only presentation surfaces."""

        return tuple(
            self.products.list_products(
                creator_profile_id=creator_profile_id,
                include_archived=include_archived,
                limit=limit,
            )
        )

    def list_workspace_display_models(
        self,
        *,
        creator_profile_id: int,
        include_archived: bool = True,
        limit: int = 100,
    ) -> tuple[ProductCatalogDisplayModel, ...]:
        """Return Product Catalog presentation models for Workspace cards."""

        return tuple(
            self.load_display_model(product)
            for product in self.list_workspace_products(
                creator_profile_id=creator_profile_id,
                include_archived=include_archived,
                limit=limit,
            )
        )

    def count_product_experience_assets(self, product_id: UUID) -> int:
        return self.experiences.count_product_experience_assets(product_id)

    def build_editor_display_model(
        self,
        editor: ProductEditorData,
    ) -> ProductCatalogDisplayModel:
        return self.build_display_model(
            editor.product,
            editor.product_assets,
            editor.assets,
            editor.experience,
        )

    def _editor_data(
        self,
        product: Product,
        links,
        assets,
        entitlement_count: int,
    ) -> ProductEditorData:
        experience = self.project_product_experience(product, links)
        ordered_assets = self.order_assets_for_experience(experience, assets)
        return ProductEditorData(
            product=product,
            product_assets=tuple(links),
            assets=ordered_assets,
            experience=experience,
            entitlement_count=entitlement_count,
        )

    @staticmethod
    def _commerce_intelligence_metadata(product: Product) -> dict[str, Any]:
        metadata = dict(product.metadata or {})
        commerce = metadata.get("commerce_intelligence") or {}
        return dict(commerce) if isinstance(commerce, dict) else {}

    @staticmethod
    def _editor_ready_to_publish(editor: ProductEditorData) -> bool:
        product = editor.product
        fulfillment_status = getattr(
            getattr(product, "fulfillment_status", None),
            "value",
            getattr(product, "fulfillment_status", None),
        )
        if product.status == ProductStatus.ARCHIVED:
            return False
        if fulfillment_status != "READY":
            return False
        if not editor.assets:
            return False
        delivery_type = getattr(
            getattr(product, "delivery_type", None),
            "value",
            getattr(product, "delivery_type", None),
        )
        if delivery_type == ProductDeliveryType.PAID.value and product.price_cents is None:
            return False
        return True

    def assign_legacy_draft(
        self,
        product_id: UUID,
        creator_profile_id: int,
    ) -> Product:
        product = self.products.assign_to_creator(
            product_id,
            creator_profile_id,
        )
        if not product:
            raise ProductCatalogValidationError(
                ["Legacy draft is no longer available for assignment."]
            )
        return product

    def _notify_content_opportunity_product_available(
        self,
        editor: ProductEditorData,
    ) -> None:
        service = self.content_opportunity_service
        notify = getattr(service, "record_new_product_available", None)
        if not callable(notify):
            return
        try:
            notify(
                {
                    "product": editor.product,
                    "assets": tuple(editor.assets or ()),
                    "publishing": editor.publishing,
                    "source": "ProductCatalogService",
                }
            )
        except Exception:
            return

    def refresh_ai_draft_from_asset(
        self,
        product_id: UUID,
        creator_profile_id: int,
    ) -> ProductEditorData:
        editor = self.load_editor(product_id, creator_profile_id)
        if editor.product.status != ProductStatus.DRAFT:
            raise ProductCatalogValidationError(
                ["Only draft products can be refreshed from CMS asset intelligence."]
            )
        result = AIProductDraftingService(
            product_repository=self.products,
            product_asset_repository=self.product_assets,
            asset_repository=self.assets,
        ).refresh_existing_product_from_asset(
            editor.product,
            creator_profile_id=creator_profile_id,
        )
        return self.load_editor(result.product.id, creator_profile_id)

    def retry_ai_draft_for_asset(
        self,
        asset_id: int,
        creator_profile_id: int,
    ) -> ProductEditorData:
        result = AIProductDraftingService(
            product_repository=self.products,
            product_asset_repository=self.product_assets,
            asset_repository=self.assets,
        ).create_or_refresh_draft_for_asset(
            asset_id,
            creator_profile_id=creator_profile_id,
        )
        return self.load_editor(result.product.id, creator_profile_id)
