"""Application boundary for Product Review presentation workflows."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING
from uuid import UUID

from app.models.product import (
    ProductApprovalStatus,
    ProductStatus,
    product_approval_metadata,
    product_approval_status_from_metadata,
)
from app.models.product_review import (
    ProductReview,
    ProductReviewSection,
    ProductReviewSummary,
)

if TYPE_CHECKING:
    from app.services.creator_review_service import CreatorReviewService
    from app.services.product_catalog_service import ProductCatalogService
    from app.services.publishing_service import PublishingService


class ProductReviewService:
    """Coordinate read-only Product Review models from existing services."""

    def __init__(
        self,
        *,
        product_catalog_service: "ProductCatalogService | None" = None,
        publishing_service: "PublishingService | None" = None,
        creator_review_service: "CreatorReviewService | None" = None,
    ):
        self._product_catalog = product_catalog_service
        self._publishing = publishing_service
        self._creator_review = creator_review_service

    @property
    def product_catalog(self) -> "ProductCatalogService":
        if self._product_catalog is None:
            from app.services.product_catalog_service import ProductCatalogService

            self._product_catalog = ProductCatalogService()
        return self._product_catalog

    @property
    def publishing(self) -> "PublishingService":
        if self._publishing is None:
            from app.services.publishing_service import PublishingService

            self._publishing = PublishingService()
        return self._publishing

    @property
    def creator_review(self) -> "CreatorReviewService":
        if self._creator_review is None:
            from app.services.creator_review_service import CreatorReviewService

            self._creator_review = CreatorReviewService()
        return self._creator_review

    def build_review(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int,
        manual_overrides: Mapping[str, Any] | None = None,
    ) -> ProductReview:
        """Build a read-only Product Review for one persisted Product."""

        editor = self.product_catalog.load_editor(
            product_id,
            creator_profile_id,
        )
        display = self.product_catalog.build_editor_display_model(editor)
        review = self.build_review_from_display(display)
        if manual_overrides:
            return review.with_manual_overrides(manual_overrides)
        return review

    def list_reviews(
        self,
        *,
        creator_profile_id: int,
        include_archived: bool = False,
        limit: int = 100,
    ) -> tuple[ProductReview, ...]:
        """Return read-only Product Reviews for creator-facing review queues."""

        displays = self.product_catalog.list_workspace_display_models(
            creator_profile_id=creator_profile_id,
            include_archived=include_archived,
            limit=limit,
        )
        return tuple(self.build_review_from_display(display) for display in displays)

    def build_summary(
        self,
        *,
        creator_profile_id: int,
        include_archived: bool = False,
        limit: int = 100,
    ) -> ProductReviewSummary:
        reviews = self.list_reviews(
            creator_profile_id=creator_profile_id,
            include_archived=include_archived,
            limit=limit,
        )
        draft_reviews = tuple(
            review for review in reviews if review.review_status == "Draft Review"
        )
        publishing_reviews = tuple(
            review
            for review in reviews
            if review.review_status in {"Publishing Review", "Needs Attention"}
        )
        high_priority_reviews = tuple(
            review for review in reviews if review.priority == "high"
        )
        ready_for_approval = tuple(
            review for review in reviews if review.review_status == "Ready for Approval"
        )
        needs_review = tuple(
            review
            for review in reviews
            if review.approval_status == ProductApprovalStatus.NEEDS_REVIEW.value
        )
        approved = tuple(
            review
            for review in reviews
            if review.approval_status == ProductApprovalStatus.APPROVED.value
        )
        rejected = tuple(
            review
            for review in reviews
            if review.approval_status == ProductApprovalStatus.REJECTED.value
        )
        ready_to_publish = tuple(
            review
            for review in reviews
            if review.approval_status == ProductApprovalStatus.READY_TO_PUBLISH.value
        )
        manual_products = tuple(
            review for review in reviews if review.product_origin == "Manual Product"
        )
        ai_product_drafts = tuple(
            review
            for review in reviews
            if review.product_origin == "AI Product Draft"
        )
        products_with_commerce_overrides = tuple(
            review
            for review in reviews
            if review.commerce_overrides.status == "overridden"
        )
        return ProductReviewSummary(
            total_reviews=len(reviews),
            needs_review=len(needs_review),
            approved=len(approved),
            rejected=len(rejected),
            ready_to_publish=len(ready_to_publish),
            manual_products=len(manual_products),
            ai_product_drafts=len(ai_product_drafts),
            products_with_commerce_overrides=len(products_with_commerce_overrides),
            draft_reviews=len(draft_reviews),
            publishing_reviews=len(publishing_reviews),
            high_priority_reviews=len(high_priority_reviews),
            ready_for_approval=len(ready_for_approval),
            reviews=reviews,
        )

    def build_from_workflow_result(
        self,
        workflow_result: Any,
        *,
        manual_overrides: Mapping[str, Any] | None = None,
    ):
        """Delegate import-result review projection to CreatorReviewService."""

        return self.creator_review.build_review(
            workflow_result,
            manual_overrides=manual_overrides,
        )

    def build_review_from_display(self, display: Any) -> ProductReview:
        """Project Product Catalog display data into a Product Review."""

        product = self._attribute(display, "product")
        if product is None:
            raise ValueError("Product Review requires a Product display model.")

        product_status = self._enum_value(self._attribute(product, "status"))
        approval = self._approval_metadata(product)
        approval_status = self._approval_status(product).value
        review_status = self._review_status(display)
        priority = self._priority(display, review_status)
        warnings = self._warnings(display, review_status)
        return ProductReview(
            product_id=str(self._attribute(product, "id")),
            creator_profile_id=self._attribute(product, "creator_profile_id"),
            product_name=str(
                self._attribute(product, "display_name")
                or self._attribute(product, "internal_name")
                or "Untitled Product"
            ),
            description=self._attribute(product, "description"),
            product_type=self._enum_value(self._attribute(product, "product_type")),
            delivery_type=self._enum_value(
                self._attribute(product, "delivery_type")
            ),
            product_origin=self._product_origin(product),
            product_status=product_status,
            approval_status=approval_status,
            approved_at=approval.get("approved_at"),
            last_reviewed_at=approval.get("last_reviewed_at"),
            review_notes=approval.get("review_notes"),
            price_cents=self._attribute(product, "price_cents"),
            currency=str(self._attribute(product, "currency") or "USD"),
            review_status=review_status,
            priority=priority,
            product=self._product_section(product, display),
            experience=self._experience_section(display),
            commerce=self._commerce_section(product),
            commerce_overrides=self._commerce_overrides_section(product, display),
            publishing=self._publishing_section(display),
            ai_rationale=self._ai_rationale_section(product),
            warnings=warnings,
        )

    def _product_section(self, product: Any, display: Any) -> ProductReviewSection:
        asset_count = len(tuple(self._attribute(display, "ordered_assets") or ()))
        data = {
            "product_id": str(self._attribute(product, "id")),
            "name": self._attribute(product, "display_name"),
            "description": self._attribute(product, "description"),
            "product_type": self._enum_value(
                self._attribute(product, "product_type")
            ),
            "delivery_type": self._enum_value(
                self._attribute(product, "delivery_type")
            ),
            "product_origin": self._product_origin(product),
            "status": self._enum_value(self._attribute(product, "status")),
            "approval_status": self._approval_status(product).value,
            "approval": self._approval_metadata(product),
            "price_cents": self._attribute(product, "price_cents"),
            "currency": self._attribute(product, "currency"),
            "asset_count": asset_count,
        }
        return ProductReviewSection(
            title="Product",
            status="available",
            summary=self._attribute(product, "display_name"),
            data=data,
            warnings=tuple(self._missing_product_fields(product, asset_count)),
        )

    def _experience_section(self, display: Any) -> ProductReviewSection:
        experience = self._attribute(display, "experience_presentation")
        if experience is None:
            return ProductReviewSection(
                title="Experience",
                status="missing",
                summary="No Experience relationship is available.",
                warnings=("missing_experience",),
            )
        data = {
            "experience_id": self._attribute(experience, "experience_id"),
            "experience_type": self._attribute(experience, "experience_type"),
            "name": self._attribute(experience, "title"),
            "summary": self._attribute(experience, "summary"),
            "cover_asset_id": self._attribute(experience, "cover_asset_id"),
            "asset_ids": tuple(self._attribute(experience, "asset_ids") or ()),
            "themes": tuple(self._attribute(experience, "themes") or ()),
            "keywords": tuple(self._attribute(experience, "keywords") or ()),
            "mood": self._attribute(experience, "mood"),
            "story_progression": self._attribute(
                experience,
                "story_progression",
            ),
            "technical_continuity": self._attribute(
                experience,
                "technical_continuity",
            ),
            "relationship_source": self._attribute(
                experience,
                "relationship_source",
            ),
            "compatibility": bool(self._attribute(experience, "compatibility")),
        }
        warnings = ()
        if data["compatibility"]:
            warnings = ("compatibility_experience_projection",)
        return ProductReviewSection(
            title="Experience",
            status="available",
            summary=data["name"] or data["summary"],
            data=data,
            warnings=warnings,
        )

    def _commerce_section(self, product: Any) -> ProductReviewSection:
        commerce = self._commerce_metadata(product)
        if not commerce:
            return ProductReviewSection(
                title="Commerce Recommendation",
                status="missing",
                summary="No Commerce Intelligence metadata is available.",
                warnings=("missing_commerce_recommendation",),
            )
        price = commerce.get("price") or {}
        data = {
            "source_type": commerce.get("source_type"),
            "source_id": commerce.get("source_id"),
            "product_type": commerce.get("product_type"),
            "delivery_type": commerce.get("delivery_type"),
            "suggested_keywords": tuple(commerce.get("suggested_keywords") or ()),
            "confidence": commerce.get("confidence"),
            "suggested_price_cents": price.get("suggested_price_cents"),
            "min_price_cents": price.get("min_price_cents"),
            "max_price_cents": price.get("max_price_cents"),
            "pricing_rule": price.get("pricing_rule"),
            "publishing": commerce.get("publishing"),
        }
        return ProductReviewSection(
            title="Commerce Recommendation",
            status="available",
            summary=self._commerce_summary(data),
            data=data,
            evidence=tuple(self._commerce_evidence(product)),
        )

    def _publishing_section(self, display: Any) -> ProductReviewSection:
        publishing = self._attribute(display, "publishing")
        if publishing is None:
            product = self._attribute(display, "product")
            assets = tuple(self._attribute(display, "ordered_assets") or ())
            product_record = self.publishing.project_legacy_product_record(product)
            status, detail = self.publishing.get_product_provider_status_display(
                product_record,
                assets,
            )
            publishing = {"status": status, "detail": detail}
        status = self._attribute(publishing, "status") or "Unavailable"
        detail = self._attribute(publishing, "detail")
        return ProductReviewSection(
            title="Publishing Readiness",
            status=str(status),
            summary=detail,
            data={
                "status": status,
                "detail": detail,
                "projection_owner": "PublishingService",
            },
            warnings=()
            if self._is_ready_status(status)
            else ("publishing_not_ready",),
        )

    def _commerce_overrides_section(
        self,
        product: Any,
        display: Any,
    ) -> ProductReviewSection:
        fields = self._commerce_override_fields(product, display)
        overridden = tuple(
            name for name, values in fields.items() if values["overridden"]
        )
        if not fields:
            return ProductReviewSection(
                title="Commerce Overrides",
                status="missing",
                summary="No AI commerce recommendation is available.",
                warnings=("missing_commerce_recommendation",),
            )
        summary = (
            "No commerce overrides"
            if not overridden
            else f"{len(overridden)} commerce override(s)"
        )
        return ProductReviewSection(
            title="Commerce Overrides",
            status="overridden" if overridden else "aligned",
            summary=summary,
            data={
                "fields": fields,
                "overridden_fields": overridden,
                "reset_supported_fields": tuple(
                    name
                    for name in ("price", "delivery_type", "product_type")
                    if name in fields
                ),
            },
            warnings=tuple(f"commerce_override_{name}" for name in overridden),
        )

    def _ai_rationale_section(self, product: Any) -> ProductReviewSection:
        metadata = dict(self._attribute(product, "metadata") or {})
        commerce = dict(metadata.get("commerce_intelligence") or {})
        evidence = tuple(self._commerce_evidence(product))
        rationale = (
            commerce.get("delivery_type_rationale")
            or metadata.get("activation_reason")
            or self._attribute(product, "activation_reason")
        )
        return ProductReviewSection(
            title="AI Rationale",
            status="available" if rationale or evidence else "missing",
            summary=rationale,
            data={
                "activation_source": self._attribute(product, "activation_source"),
                "activation_reason": self._attribute(product, "activation_reason"),
                "ai_product_draft": metadata.get("ai_product_draft"),
                "draft_source": metadata.get("draft_source"),
                "creation_source": metadata.get("creation_source"),
                "manual_product": metadata.get("manual_product"),
            },
            evidence=evidence,
        )

    def _review_status(self, display: Any) -> str:
        product = self._attribute(display, "product")
        status = self._enum_value(self._attribute(product, "status"))
        product_section_warnings = self._missing_product_fields(
            product,
            len(tuple(self._attribute(display, "ordered_assets") or ())),
        )
        if status == ProductStatus.ARCHIVED.value:
            return "Archived"
        approval_status = self._approval_status(product)
        if approval_status == ProductApprovalStatus.REJECTED:
            return "Rejected"
        if approval_status == ProductApprovalStatus.READY_TO_PUBLISH:
            return "Ready To Publish"
        if approval_status == ProductApprovalStatus.APPROVED:
            return "Approved"
        if product_section_warnings:
            return "Needs Attention"
        if self._commerce_override_field_names(product, display):
            return "Commerce Override Review"
        if status == ProductStatus.DRAFT.value:
            return "Draft Review"
        publishing = self._attribute(display, "publishing")
        if self._is_ready_status(self._attribute(publishing, "status")):
            return "Ready for Approval"
        return "Publishing Review"

    def _priority(self, display: Any, review_status: str) -> str:
        if review_status == "Needs Attention":
            return "high"
        if review_status in {"Ready To Publish", "Approved"}:
            return "normal"
        if review_status in {
            "Draft Review",
            "Publishing Review",
            "Commerce Override Review",
        }:
            return "medium"
        return "normal"

    def _warnings(self, display: Any, review_status: str) -> tuple[str, ...]:
        warnings: list[str] = []
        for section in (
            self._product_section(
                self._attribute(display, "product"),
                display,
            ),
            self._experience_section(display),
            self._commerce_section(self._attribute(display, "product")),
            self._commerce_overrides_section(
                self._attribute(display, "product"),
                display,
            ),
            self._publishing_section(display),
        ):
            warnings.extend(section.warnings)
        if review_status == "Archived":
            warnings.append("archived_product")
        if review_status == "Rejected":
            warnings.append("product_not_approved")
        return tuple(dict.fromkeys(warnings))

    def _approval_status(self, product: Any) -> ProductApprovalStatus:
        return product_approval_status_from_metadata(
            self._attribute(product, "metadata") or {}
        )

    def _approval_metadata(self, product: Any) -> dict[str, Any]:
        return product_approval_metadata(self._attribute(product, "metadata") or {})

    def _product_origin(self, product: Any) -> str:
        metadata = self._attribute(product, "metadata") or {}
        if not isinstance(metadata, Mapping):
            return "Unknown"
        if metadata.get("manual_product") or metadata.get("creation_source") == "manual":
            return "Manual Product"
        if metadata.get("ai_product_draft") or metadata.get("draft_source"):
            return "AI Product Draft"
        return "Product"

    def _missing_product_fields(self, product: Any, asset_count: int) -> tuple[str, ...]:
        warnings: list[str] = []
        if not self._attribute(product, "display_name"):
            warnings.append("missing_product_name")
        if not self._attribute(product, "description"):
            warnings.append("missing_description")
        delivery_type = self._attribute(product, "delivery_type")
        if not delivery_type:
            warnings.append("missing_delivery_type")
        price = self._attribute(product, "price_cents")
        delivery_value = self._enum_value(delivery_type)
        if delivery_value == "PAID" and price is None:
            warnings.append("missing_price")
        if asset_count <= 0:
            warnings.append("missing_assets")
        return tuple(warnings)

    def _commerce_override_field_names(
        self,
        product: Any,
        display: Any,
    ) -> tuple[str, ...]:
        fields = self._commerce_override_fields(product, display)
        return tuple(name for name, values in fields.items() if values["overridden"])

    def _commerce_override_fields(
        self,
        product: Any,
        display: Any,
    ) -> dict[str, dict[str, Any]]:
        commerce = self._commerce_metadata(product)
        if not commerce:
            return {}
        price = commerce.get("price") or {}
        publishing = commerce.get("publishing") or {}
        current_publishing = self._publishing_section(display)
        comparisons = {
            "price": {
                "label": "Suggested Price",
                "ai": price.get("suggested_price_cents"),
                "current": self._attribute(product, "price_cents"),
            },
            "delivery_type": {
                "label": "Delivery Type",
                "ai": commerce.get("delivery_type"),
                "current": self._enum_value(
                    self._attribute(product, "delivery_type")
                ),
            },
            "product_type": {
                "label": "Product Type",
                "ai": commerce.get("product_type"),
                "current": self._enum_value(self._attribute(product, "product_type")),
            },
        }
        if publishing:
            comparisons["publishing_readiness"] = {
                "label": "Publishing Readiness",
                "ai": publishing.get("status"),
                "current": current_publishing.status,
                "presentation_only": True,
            }
        normalized = {}
        for name, values in comparisons.items():
            ai_value = values["ai"]
            current_value = values["current"]
            if ai_value in (None, "") and current_value in (None, ""):
                continue
            normalized[name] = {
                **values,
                "overridden": (
                    False
                    if values.get("presentation_only")
                    else self._normalize_commerce_value(ai_value)
                    != self._normalize_commerce_value(current_value)
                ),
            }
        return normalized

    def _commerce_metadata(self, product: Any) -> Mapping[str, Any]:
        metadata = self._attribute(product, "metadata") or {}
        if not isinstance(metadata, Mapping):
            return {}
        commerce = metadata.get("commerce_intelligence") or {}
        return commerce if isinstance(commerce, Mapping) else {}

    def _commerce_evidence(self, product: Any) -> Iterable[Mapping[str, Any]]:
        commerce = self._commerce_metadata(product)
        evidence = commerce.get("evidence") or ()
        for item in evidence:
            if isinstance(item, Mapping):
                yield dict(item)
            else:
                yield {
                    "reason": self._attribute(item, "reason"),
                    "detail": self._attribute(item, "detail"),
                    "weight": self._attribute(item, "weight"),
                }
        rationale = commerce.get("delivery_type_rationale")
        if rationale:
            yield {
                "reason": "delivery_type_rationale",
                "detail": rationale,
            }

    @staticmethod
    def _commerce_summary(data: Mapping[str, Any]) -> str:
        delivery = data.get("delivery_type") or "Unknown"
        product_type = data.get("product_type") or "Unknown"
        price = data.get("suggested_price_cents")
        if price is None:
            return f"{delivery} {product_type}"
        return f"{delivery} {product_type} at {price} cents"

    @staticmethod
    def _normalize_commerce_value(value: Any) -> Any:
        if value is None:
            return None
        enum_value = getattr(value, "value", value)
        if isinstance(enum_value, str):
            clean = enum_value.strip()
            return clean.upper() if clean else None
        return enum_value

    @staticmethod
    def _is_ready_status(status: Any) -> bool:
        value = str(status or "").strip().lower()
        return value in {"ready", "ready to publish", "ready_for_approval"}

    @staticmethod
    def _attribute(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, Mapping):
            return value.get(name, default)
        return getattr(value, name, default)

    @staticmethod
    def _enum_value(value: Any) -> str:
        if value is None:
            return ""
        return str(getattr(value, "value", value))
