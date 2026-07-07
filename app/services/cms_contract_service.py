"""Public CMS contract boundary for DecisionEngine-facing data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.contracts.cms import (
    AvailableExperience,
    AvailableProduct,
    CustomerIdentity,
    CustomerProgress,
    DeliveryMode,
    DeliveryPermission,
    DeliverySubjectType,
    ExperienceKind,
    OfferCandidate,
    OfferKind,
    ProductAvailability,
    ProductDeliveryType,
    PublishingState,
    PublishingStatus,
    RuntimeCustomerContext,
)
from app.models.experience import Experience, ExperienceType
from app.models.product import (
    Product,
    ProductFulfillmentStatus,
    ProductStatus,
    delivery_mode_value_for_delivery_type,
    product_delivery_type_from_metadata,
)
from app.models.product_offer import ProductOffer
from app.services.experience_service import ExperienceService


class CMSContractService:
    """Build stable CMS contracts from Creator OS domain objects."""

    def __init__(
        self,
        *,
        experience_service: ExperienceService | None = None,
        product_repository: Any | None = None,
        publishing_service: Any | None = None,
        recommendation_service: Any | None = None,
        delivery_guard_service: Any | None = None,
    ):
        self.experience_service = experience_service or ExperienceService()
        self.product_repository = product_repository
        self.publishing_service = publishing_service
        self.recommendation_service = recommendation_service
        self.delivery_guard_service = delivery_guard_service

    def get_available_product(self, product_id: Any) -> AvailableProduct | None:
        if not self.product_repository:
            return None

        getter = getattr(self.product_repository, "get_by_id", None)
        if getter is None:
            getter = getattr(self.product_repository, "get_product", None)
        if getter is None:
            return None

        product = getter(product_id)
        if not product:
            return None
        return self.build_available_product(product)

    def build_available_product(
        self,
        product: Product | Mapping[str, Any] | None,
        *,
        experience: Experience | AvailableExperience | None = None,
    ) -> AvailableProduct | None:
        if not product:
            return None

        product_id = self._read(product, "id", "product_id")
        product_type = self._read(product, "product_type") or "custom"
        status = self._read(product, "status")
        metadata = self._as_mapping(self._read(product, "metadata"))
        experience_id = self._read(metadata, "experience_id")
        if experience is not None:
            experience_id = self._read(experience, "experience_id")
        relationship_metadata = self._product_experience_relationship_metadata(
            product_id=product_id,
            experience_id=experience_id,
            experience=experience,
        )

        return AvailableProduct(
            product_id=str(product_id),
            title=str(
                self._read(product, "display_name", "title", "internal_name")
                or product_id
            ),
            product_type=self._enum_value(product_type).lower(),
            availability=self._map_product_availability(status),
            delivery_type=self._map_product_delivery_type(product),
            description=self._read(product, "description"),
            experience_id=str(experience_id) if experience_id else None,
            price_cents=self._read(product, "price_cents"),
            currency=self._read(product, "currency") or "USD",
            tags=self._read(product, "tags") or (),
            themes=self._read(product, "themes") or (),
            offer_metadata=self._stable_product_metadata(
                {
                    **metadata,
                    **relationship_metadata,
                }
            ),
        )

    def get_available_experience(
        self,
        product_id: Any,
        *,
        creator_profile_id: int | None = None,
    ) -> AvailableExperience | None:
        experience = self.experience_service.get_experience(
            product_id,
            creator_profile_id=creator_profile_id,
        )
        return self.build_available_experience(experience)

    def build_available_experience(
        self,
        experience: Experience | Mapping[str, Any] | None,
    ) -> AvailableExperience | None:
        if not experience:
            return None

        metadata = self._as_mapping(self._read(experience, "metadata"))
        experience_intelligence = self._experience_intelligence_projection(
            metadata
        )
        presentation_metadata = {
            **metadata,
            **experience_intelligence,
        }
        return AvailableExperience(
            experience_id=str(self._read(experience, "experience_id", "id")),
            experience_kind=self._map_experience_kind(
                self._read(experience, "experience_type", "experience_kind")
            ),
            title=str(self._read(experience, "title") or "Untitled"),
            description=self._read(experience, "description"),
            cover_media_ref=self._media_ref(
                self._read(experience, "cover_asset_id")
            ),
            ordered_media_refs=tuple(
                self._media_ref(asset_id)
                for asset_id in self._ordered_asset_ids(experience)
            ),
            tags=self._read(metadata, "tags") or (),
            themes=(
                self._read(metadata, "themes")
                or self._read(experience_intelligence, "suggested_themes")
                or ()
            ),
            classification=self._read(metadata, "classification"),
            presentation=self._stable_presentation_metadata(presentation_metadata),
        )

    def get_publishing_status(
        self,
        subject_id: Any,
        *,
        subject_type: DeliverySubjectType | str = DeliverySubjectType.PRODUCT,
    ) -> PublishingStatus | None:
        if not self.publishing_service:
            return None

        if DeliverySubjectType(subject_type) == DeliverySubjectType.EXPERIENCE:
            return PublishingStatus(
                subject_id=str(subject_id),
                subject_type=DeliverySubjectType.EXPERIENCE,
                state=PublishingState.UNKNOWN,
                is_deliverable=False,
                reason="Experience publishing state is not available yet.",
            )

        getter = getattr(self.publishing_service, "get_by_product_id", None)
        if getter is None:
            return None
        record = getter(subject_id)
        return self.build_publishing_status(
            record,
            subject_id=subject_id,
            subject_type=subject_type,
        )

    def build_publishing_status(
        self,
        publishing_record: Mapping[str, Any] | None,
        *,
        subject_id: Any,
        subject_type: DeliverySubjectType | str = DeliverySubjectType.PRODUCT,
    ) -> PublishingStatus:
        if not publishing_record:
            return PublishingStatus(
                subject_id=str(subject_id),
                subject_type=subject_type,
                state=PublishingState.NOT_PUBLISHED,
                is_deliverable=False,
                reason="No publishing record.",
            )

        status = self._read(publishing_record, "provider_status", "state")
        output = self._read(publishing_record, "provider_output_url")
        is_deliverable = self._is_published(status) or bool(output)
        modes = self._available_delivery_modes_for_publishing_record(
            publishing_record,
            is_deliverable=is_deliverable,
        )
        return PublishingStatus(
            subject_id=str(subject_id),
            subject_type=subject_type,
            state=self._map_publishing_state(status, has_output=bool(output)),
            is_deliverable=is_deliverable,
            available_delivery_modes=modes,
            reason=self._safe_reason(publishing_record),
            updated_at=self._read(publishing_record, "updated_at"),
        )

    def build_customer_identity(
        self,
        customer_id: Any,
        *,
        creator_id: Any | None = None,
        channel: str | None = None,
        display_name: str | None = None,
    ) -> CustomerIdentity:
        return CustomerIdentity(
            customer_id=str(customer_id),
            creator_id=str(creator_id) if creator_id is not None else None,
            channel=channel,
            display_name=display_name,
        )

    def build_runtime_customer_context(
        self,
        identity: CustomerIdentity | Any,
        *,
        traits: Mapping[str, Any] | None = None,
        conversation_state: Mapping[str, Any] | None = None,
    ) -> RuntimeCustomerContext:
        if not isinstance(identity, CustomerIdentity):
            identity = self.build_customer_identity(identity)
        return RuntimeCustomerContext(
            identity=identity,
            traits=self._stable_customer_mapping(traits),
            conversation_state=self._stable_customer_mapping(
                conversation_state
            ),
        )

    def build_customer_progress(
        self,
        customer_id: Any,
        *,
        user_memory: Mapping[str, Any] | None = None,
        owned_product_ids: Sequence[Any] | None = None,
        owned_experience_ids: Sequence[Any] | None = None,
    ) -> CustomerProgress:
        user_memory = user_memory or {}
        return CustomerProgress(
            customer_id=str(customer_id),
            seen_offer_ids=self._text_tuple(
                self._read(user_memory, "seen_offer_ids")
            ),
            seen_experience_ids=self._text_tuple(
                self._read(user_memory, "seen_experience_ids")
            ),
            owned_product_ids=self._text_tuple(owned_product_ids),
            owned_experience_ids=self._text_tuple(owned_experience_ids),
            preferred_tags=self._text_tuple(
                self._read(user_memory, "preferred_tags", "seen_content_tags")
            ),
            preferred_themes=self._text_tuple(
                self._read(user_memory, "preferred_themes")
                or self._read(user_memory, "preferred_content_theme")
            ),
            offer_count=self._int_value(
                self._read(user_memory, "offer_count"),
            ),
            purchase_count=self._int_value(
                self._read(user_memory, "purchase_count"),
            ),
            total_spend_cents=self._int_value(
                self._read(user_memory, "total_spend_cents"),
            ),
            last_offer_id=self._read(user_memory, "last_offer_id"),
            last_offer_kind=self._map_offer_kind(
                self._read(user_memory, "last_offer_kind", "last_offer_type")
            ),
            cooldown_until=self._read(user_memory, "cooldown_until"),
            signals=self._stable_customer_mapping(
                self._read(user_memory, "signals")
            ),
        )

    def build_delivery_permission(
        self,
        *,
        subject_id: Any,
        subject_type: DeliverySubjectType | str = DeliverySubjectType.PRODUCT,
        delivery_mode: DeliveryMode | str = DeliveryMode.PAID,
        allowed: bool | None = None,
        reason: str | None = None,
        product: Product | Mapping[str, Any] | None = None,
        publishing_status: PublishingStatus | None = None,
        price_cents: int | None = None,
        currency: str | None = None,
    ) -> DeliveryPermission:
        delivery_mode = self._delivery_mode_for_product(
            product,
            delivery_mode,
        )
        if allowed is None:
            allowed = self._delivery_allowed(product, publishing_status)
        if reason is None and not allowed:
            reason = "Content is not currently deliverable."

        product_price = self._read(product, "price_cents") if product else None
        product_currency = self._read(product, "currency") if product else None
        resolved_price = price_cents if price_cents is not None else product_price
        return DeliveryPermission(
            subject_id=str(subject_id),
            subject_type=subject_type,
            delivery_mode=delivery_mode,
            allowed=bool(allowed),
            reason=reason,
            requires_payment=DeliveryMode(delivery_mode) == DeliveryMode.PAID,
            price_cents=resolved_price,
            currency=currency or product_currency or "USD",
        )

    def build_offer_candidate(
        self,
        offer: ProductOffer | Mapping[str, Any] | None = None,
        *,
        offer_id: Any | None = None,
        offer_kind: OfferKind | str | None = None,
        title: str | None = None,
        product: Product | AvailableProduct | Mapping[str, Any] | None = None,
        experience: Experience | AvailableExperience | Mapping[str, Any] | None = None,
        delivery_permission: DeliveryPermission | None = None,
        publishing_status: PublishingStatus | None = None,
        description: str | None = None,
        price_cents: int | None = None,
        currency: str | None = None,
        score: int | None = None,
        reason: str | None = None,
        presentation: Mapping[str, Any] | None = None,
    ) -> OfferCandidate:
        if offer is not None:
            product = product or self._read(offer, "product")
            offer_kind = offer_kind or self._read(offer, "offer_type", "type")
            reason = reason or self._read(offer, "reason")
            score = score if score is not None else self._read(offer, "score")
            presentation = presentation or self._read(offer, "metadata")

        product_contract = self._ensure_product_contract(product)
        experience_contract = self._ensure_experience_contract(experience)
        resolved_price = price_cents
        resolved_currency = currency
        if product_contract:
            resolved_price = (
                resolved_price
                if resolved_price is not None
                else product_contract.price_cents
            )
            resolved_currency = resolved_currency or product_contract.currency

        resolved_id = offer_id or self._read(offer, "offer_id", "id")
        if not resolved_id and product_contract:
            resolved_id = f"offer:{product_contract.product_id}"

        return OfferCandidate(
            offer_id=str(resolved_id or "offer"),
            offer_kind=self._map_offer_kind(offer_kind),
            title=title or self._offer_title(product_contract, offer_kind),
            product=product_contract,
            experience=experience_contract,
            delivery_permission=delivery_permission,
            publishing_status=publishing_status,
            description=description,
            price_cents=resolved_price,
            currency=resolved_currency or "USD",
            score=self._int_value(score),
            reason=reason,
            presentation=self._stable_presentation_metadata(presentation),
        )

    def _ensure_product_contract(
        self,
        product: Product | AvailableProduct | Mapping[str, Any] | None,
    ) -> AvailableProduct | None:
        if product is None or isinstance(product, AvailableProduct):
            return product
        return self.build_available_product(product)

    def _ensure_experience_contract(
        self,
        experience: Experience | AvailableExperience | Mapping[str, Any] | None,
    ) -> AvailableExperience | None:
        if experience is None or isinstance(experience, AvailableExperience):
            return experience
        return self.build_available_experience(experience)

    def _ordered_asset_ids(
        self,
        experience: Experience | Mapping[str, Any],
    ) -> tuple[Any, ...]:
        ordered = self._read(experience, "ordered_asset_ids", "asset_order")
        if ordered:
            return tuple(ordered)
        asset_ids = self._read(experience, "asset_ids")
        return tuple(asset_ids or ())

    def _media_ref(self, asset_id: Any) -> str | None:
        if asset_id is None:
            return None
        return f"asset:{asset_id}"

    def _map_experience_kind(self, value: Any) -> ExperienceKind:
        normalized = self._enum_value(value).lower()
        if normalized == ExperienceType.PHOTOSHOOT.value.lower():
            return ExperienceKind.PHOTOSHOOT
        if normalized == ExperienceType.STORY.value.lower():
            return ExperienceKind.STORY
        return ExperienceKind.STANDALONE

    def _map_product_availability(self, value: Any) -> ProductAvailability:
        normalized = self._enum_value(value).lower()
        if normalized == ProductStatus.ACTIVE.value.lower():
            return ProductAvailability.AVAILABLE
        if normalized == ProductStatus.ARCHIVED.value.lower():
            return ProductAvailability.ARCHIVED
        if normalized == ProductStatus.DISABLED.value.lower():
            return ProductAvailability.PAUSED
        return ProductAvailability.DRAFT

    def _map_product_delivery_type(self, product: Any) -> ProductDeliveryType:
        delivery_type = self._read(product, "delivery_type")
        if delivery_type:
            return ProductDeliveryType(self._enum_value(delivery_type).upper())

        metadata = self._as_mapping(self._read(product, "metadata"))
        return ProductDeliveryType(
            product_delivery_type_from_metadata(metadata).value
        )

    def _delivery_mode_for_product(
        self,
        product: Product | Mapping[str, Any] | None,
        delivery_mode: DeliveryMode | str,
    ) -> DeliveryMode | str:
        try:
            normalized_mode = DeliveryMode(delivery_mode)
        except ValueError:
            return delivery_mode
        if product is None or normalized_mode != DeliveryMode.PAID:
            return delivery_mode
        return delivery_mode_value_for_delivery_type(
            self._map_product_delivery_type(product).value
        )

    def _available_delivery_modes_for_publishing_record(
        self,
        publishing_record: Mapping[str, Any],
        *,
        is_deliverable: bool,
    ) -> tuple[DeliveryMode, ...]:
        if not is_deliverable:
            return ()

        delivery_type = self._read(publishing_record, "delivery_type")
        if not delivery_type:
            return (DeliveryMode.PAID,)

        try:
            delivery_mode = delivery_mode_value_for_delivery_type(
                self._enum_value(delivery_type).upper()
            )
            return (DeliveryMode(delivery_mode),)
        except ValueError:
            return (DeliveryMode.PAID,)

    def _map_publishing_state(
        self,
        value: Any,
        *,
        has_output: bool = False,
    ) -> PublishingState:
        normalized = self._enum_value(value).lower()
        if normalized in {"ready", "published", "uploaded"} or has_output:
            return PublishingState.PUBLISHED
        if normalized in {"failed", "error"}:
            return PublishingState.FAILED
        if normalized in {"pending", "processing", "uploading"}:
            return PublishingState.PENDING
        if normalized in {"not_ready", "not_published", "missing", ""}:
            return PublishingState.NOT_PUBLISHED
        return PublishingState.UNKNOWN

    def _map_offer_kind(self, value: Any) -> OfferKind:
        normalized = self._enum_value(value).lower()
        if normalized.endswith("_offer"):
            normalized = normalized.replace("_offer", "")
        if normalized == "teaser":
            normalized = "tease"
        if normalized == OfferKind.VIP.value:
            return OfferKind.VIP
        if normalized == OfferKind.PREMIUM.value:
            return OfferKind.PREMIUM
        if normalized == OfferKind.CUSTOM.value:
            return OfferKind.CUSTOM
        return OfferKind.TEASE

    def _delivery_allowed(
        self,
        product: Product | Mapping[str, Any] | None,
        publishing_status: PublishingStatus | None,
    ) -> bool:
        if publishing_status is not None:
            return publishing_status.is_deliverable
        if not product:
            return False
        status = self._read(product, "fulfillment_status")
        if not status:
            return False
        return self._enum_value(status) == ProductFulfillmentStatus.READY.value

    def _stable_product_metadata(
        self,
        metadata: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return self._filter_stable_mapping(
            metadata,
            allowed_keys={
                "caption_style",
                "content_tier",
                "experience_id",
                "experience_relationship",
                "intensity",
                "sales_angle",
                "theme",
            },
        )

    def _product_experience_relationship_metadata(
        self,
        *,
        product_id: Any,
        experience_id: Any,
        experience: Experience | AvailableExperience | None,
    ) -> dict[str, Any]:
        if not experience_id:
            return {}
        experience_id_text = str(experience_id)
        relationship = {
            "product_id": str(product_id),
            "experience_id": experience_id_text,
            "role": "primary",
            "source": "cms_contract",
            "compatibility_experience_id": experience_id_text.startswith(
                "product:"
            ),
        }
        experience_kind = self._read(
            experience,
            "experience_type",
            "experience_kind",
        )
        if experience_kind:
            relationship["experience_kind"] = self._enum_value(experience_kind)
        return {"experience_relationship": relationship}

    def _stable_presentation_metadata(
        self,
        metadata: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return self._filter_stable_mapping(
            metadata,
            allowed_keys={
                "chapter",
                "chapters",
                "classification",
                "content_tier",
                "cover_title",
                "intensity",
                "intelligence_metadata",
                "intelligence_provenance",
                "setting",
                "mood",
                "sales_angle",
                "sequence_label",
                "story_progression",
                "suggested_keywords",
                "suggested_themes",
                "technical_continuity",
                "theme",
                "visual_continuity",
            },
        )

    def _experience_intelligence_projection(
        self,
        metadata: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        metadata = self._as_mapping(metadata)
        direct = self._as_mapping(metadata.get("experience_intelligence"))
        commerce = self._as_mapping(metadata.get("commerce_intelligence"))
        nested = self._as_mapping(commerce.get("experience_intelligence"))
        return {**nested, **direct}

    def _stable_customer_mapping(
        self,
        values: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return self._filter_stable_mapping(
            values,
            denied_markers={
                "account_id",
                "file_path",
                "link",
                "media_uuid",
                "provider",
                "url",
                "user_id",
            },
        )

    def _filter_stable_mapping(
        self,
        values: Mapping[str, Any] | None,
        *,
        allowed_keys: set[str] | None = None,
        denied_markers: set[str] | None = None,
    ) -> dict[str, Any]:
        values = self._as_mapping(values)
        stable = {}
        for key, value in values.items():
            key_text = str(key)
            lowered = key_text.lower()
            if allowed_keys is not None and lowered not in allowed_keys:
                continue
            if denied_markers and any(marker in lowered for marker in denied_markers):
                continue
            stable[key_text] = value
        return stable

    def _safe_reason(self, record: Mapping[str, Any]) -> str | None:
        error = self._read(record, "provider_error")
        if error:
            return str(error)
        return None

    def _is_published(self, status: Any) -> bool:
        return self._map_publishing_state(status) == PublishingState.PUBLISHED

    def _offer_title(
        self,
        product: AvailableProduct | None,
        offer_kind: Any,
    ) -> str:
        if product:
            return product.title
        kind = self._map_offer_kind(offer_kind)
        return f"{kind.value.title()} offer"

    def _enum_value(self, value: Any) -> str:
        if value is None:
            return ""
        return str(getattr(value, "value", value))

    def _as_mapping(self, value: Any) -> Mapping[str, Any]:
        return value if isinstance(value, Mapping) else {}

    def _text_tuple(self, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, (str, bytes)):
            values = (value,)
        else:
            values = tuple(value)
        return tuple(str(item) for item in values if item is not None)

    def _int_value(self, value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _read(self, source: Any, *names: str) -> Any:
        if source is None:
            return None
        for name in names:
            if isinstance(source, Mapping) and name in source:
                return source[name]
            if hasattr(source, name):
                value = getattr(source, name)
                return value() if callable(value) else value
        return None
