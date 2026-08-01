"""Chat Commerce Registration boundary for canonical Business Assets."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, Mapping

from app.models.chat_commerce_registration import (
    ChatAvailabilityState,
    ChatCommerceAssetRecord,
    ChatCommerceRegistrationRequest,
    ChatCommerceRegistrationResult,
    ChatEligibility,
    ChatInventoryCandidate,
)
from app.models.commerce_destination import CommerceDestination
from app.models.commerce_registration import (
    BusinessAssetLifecycleState,
    BusinessAssetRecord,
    CommerceRegistrationStatus,
)
from app.models.fulfillment_registration import (
    BusinessAssetFulfillmentRecord,
    FulfillmentLifecycleState,
    FulfillmentRoute,
    MediaLinkVerificationState,
)
from app.models.generation_engine import utc_now

if TYPE_CHECKING:
    from app.repositories.asset_repository import AssetRepository
    from app.repositories.chat_commerce_registration_repository import (
        ChatCommerceRegistrationRepository,
    )
    from app.repositories.commerce_registration_repository import (
        CommerceRegistrationRepository,
    )
    from app.repositories.fulfillment_registration_repository import (
        FulfillmentRegistrationRepository,
    )
    from app.services.ownership_decision_projection import OwnershipDecisionProjection
    from app.services.content_usage_service import ContentUsageService


CHAT_DESTINATIONS = {
    CommerceDestination.CUSTOMER_CONVERSATIONS.value,
    CommerceDestination.BOTH.value,
}


class ChatCommerceRegistrationService:
    """Registers fulfilled Business Assets into canonical chat inventory."""

    def __init__(
        self,
        *,
        chat_repository: "ChatCommerceRegistrationRepository | None" = None,
        registration_repository: "CommerceRegistrationRepository | None" = None,
        fulfillment_repository: "FulfillmentRegistrationRepository | None" = None,
        asset_repository: "AssetRepository | None" = None,
        content_usage_service: "ContentUsageService | None" = None,
        ownership_decisions: "OwnershipDecisionProjection | None" = None,
        content_ownership_service: Any | None = None,
        entry_policy: Any | None = None,
    ) -> None:
        if chat_repository is None:
            from app.repositories.chat_commerce_registration_repository import (
                ChatCommerceRegistrationRepository,
            )

            chat_repository = ChatCommerceRegistrationRepository()
        if registration_repository is None:
            from app.repositories.commerce_registration_repository import (
                CommerceRegistrationRepository,
            )

            registration_repository = CommerceRegistrationRepository()
        if fulfillment_repository is None:
            from app.repositories.fulfillment_registration_repository import (
                FulfillmentRegistrationRepository,
            )

            fulfillment_repository = FulfillmentRegistrationRepository()
        if asset_repository is None:
            from app.repositories.asset_repository import AssetRepository

            asset_repository = AssetRepository()
        if content_usage_service is None:
            from app.services.content_usage_service import ContentUsageService

            content_usage_service = ContentUsageService()
        if ownership_decisions is None:
            from app.services.ownership_decision_projection import (
                OwnershipDecisionProjection,
            )
            ownership_decisions = OwnershipDecisionProjection()
        self.chat_repository = chat_repository
        self.registration_repository = registration_repository
        self.fulfillment_repository = fulfillment_repository
        self.asset_repository = asset_repository
        self.content_usage_service = content_usage_service
        self.ownership_decisions = ownership_decisions
        if entry_policy is None:
            from app.services.autonomous_commerce_entry_policy import (
                AutonomousCommerceEntryPolicy,
            )

            entry_policy = AutonomousCommerceEntryPolicy(asset_repository=asset_repository)
        self.entry_policy = entry_policy

    def register_fulfilled_asset(
        self,
        asset_id: int,
        *,
        idempotency_key: str | None = None,
        creator_note: str | None = None,
        additional_block_reasons: tuple[str, ...] = (),
    ) -> ChatCommerceRegistrationResult:
        business_asset = self.registration_repository.get_by_asset_id(int(asset_id))
        fulfillment = self.fulfillment_repository.get_by_asset_and_route(
            int(asset_id),
            FulfillmentRoute.CUSTOMER_CONVERSATIONS,
        )
        if business_asset is None or fulfillment is None:
            request = ChatCommerceRegistrationRequest(
                asset_id=int(asset_id),
                registration_id=(
                    business_asset.registration_id
                    if business_asset
                    else ChatCommerceAssetRecord.deterministic_id(asset_id)
                ),
                fulfillment_id=(
                    fulfillment.fulfillment_id
                    if fulfillment
                    else ChatCommerceAssetRecord.deterministic_id(asset_id)
                ),
                commerce_destination=(
                    business_asset.selected_commerce_destination
                    if business_asset
                    else None
                ),
                creator_profile_id=(
                    business_asset.creator_profile_id if business_asset else None
                ),
                creator_note=creator_note,
                idempotency_key=idempotency_key,
            )
            return self.register(request, additional_block_reasons=additional_block_reasons)
        return self.register(
            self._request_from_records(
                business_asset,
                fulfillment,
                idempotency_key=idempotency_key,
                creator_note=creator_note,
            ),
            additional_block_reasons=additional_block_reasons,
        )

    def register(
        self,
        request: ChatCommerceRegistrationRequest,
        *,
        additional_block_reasons: tuple[str, ...] = (),
    ) -> ChatCommerceRegistrationResult:
        business_asset = self.registration_repository.get_by_asset_id(
            int(request.asset_id)
        )
        fulfillment = self.fulfillment_repository.get_by_asset_and_route(
            int(request.asset_id),
            FulfillmentRoute.CUSTOMER_CONVERSATIONS,
        )
        asset = self.asset_repository.get_by_id(int(request.asset_id))
        existing = self.chat_repository.get_by_asset_id(int(request.asset_id))

        now = utc_now()
        block_reasons = self._block_reasons(
            request=request,
            business_asset=business_asset,
            fulfillment=fulfillment,
            asset=asset,
            additional_block_reasons=additional_block_reasons,
        )
        warnings = self._warnings(
            business_asset=business_asset,
            fulfillment=fulfillment,
            asset=asset,
        )
        state = self._availability_state(existing, block_reasons)
        chat_ready = state == ChatAvailabilityState.CHAT_READY
        record = ChatCommerceAssetRecord(
            chat_registration_id=(
                existing.chat_registration_id
                if existing
                else ChatCommerceAssetRecord.deterministic_id(request.asset_id)
            ),
            asset_id=int(request.asset_id),
            registration_id=(
                business_asset.registration_id
                if business_asset
                else self._coerce_uuid(request.registration_id)
            ),
            fulfillment_id=(
                fulfillment.fulfillment_id
                if fulfillment
                else self._coerce_uuid(request.fulfillment_id)
            ),
            creator_profile_id=(
                request.creator_profile_id
                if request.creator_profile_id is not None
                else (business_asset.creator_profile_id if business_asset else None)
            ),
            commerce_destination=(
                business_asset.selected_commerce_destination
                if business_asset
                else request.commerce_destination
            ),
            availability_state=state,
            chat_ready=chat_ready,
            fulfillment_ready=self._fulfillment_ready(fulfillment),
            recommendation_eligible=chat_ready,
            delivery_eligible=chat_ready and bool(getattr(fulfillment, "media_link", None)),
            active=chat_ready,
            temporarily_unavailable=(
                existing.temporarily_unavailable
                if existing
                and existing.availability_state
                == ChatAvailabilityState.TEMPORARILY_UNAVAILABLE
                else False
            ),
            retired=existing.retired if existing else False,
            product_ids=self._relationship_ids(
                request.product_ids,
                getattr(business_asset, "product_ids", ()),
            ),
            experience_ids=self._relationship_ids(
                request.experience_ids,
                getattr(business_asset, "experience_ids", ()),
            ),
            source_workflow=(
                request.source_workflow
                or getattr(fulfillment, "provenance", {}).get("source_workflow")
                if fulfillment
                else request.source_workflow
            ),
            media_link=getattr(fulfillment, "media_link", None),
            provider_media_id=(
                getattr(fulfillment, "provider_media_id", None)
                or getattr(fulfillment, "provider_full_media_id", None)
                or getattr(fulfillment, "provider_preview_media_id", None)
            ),
            provider=getattr(fulfillment, "provider", None),
            registered_at=existing.registered_at if existing else now,
            chat_ready_at=(
                existing.chat_ready_at
                if existing and existing.chat_ready_at
                else (now if chat_ready else None)
            ),
            temporarily_unavailable_at=(
                existing.temporarily_unavailable_at if existing else None
            ),
            retired_at=existing.retired_at if existing else None,
            last_refreshed_at=now,
            registration_provenance={
                "source": "ChatCommerceRegistrationService",
                "idempotency_key": request.idempotency_key,
                "creator_note": request.creator_note,
                "business_lifecycle_state": (
                    business_asset.business_lifecycle_state.value
                    if business_asset
                    else None
                ),
                "fulfillment_lifecycle_state": (
                    fulfillment.lifecycle_state.value if fulfillment else None
                ),
            },
            block_reasons=block_reasons,
            warnings=warnings,
            error_code=None if chat_ready else (block_reasons[0] if block_reasons else None),
            error_message=None if chat_ready else ", ".join(block_reasons),
            retry_count=(
                int(existing.retry_count or 0) + (0 if chat_ready else 1)
                if existing
                else (0 if chat_ready else 1)
            ),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        if existing is not None and self._registration_projection(existing) == self._registration_projection(record):
            return ChatCommerceRegistrationResult.from_record(
                existing,
                success=existing.chat_ready,
                errors=tuple(existing.block_reasons) if not existing.chat_ready else (),
            )
        stored = self.chat_repository.upsert_record(record)
        self._project_business_lifecycle(stored, business_asset)
        return ChatCommerceRegistrationResult.from_record(
            stored,
            success=stored.chat_ready,
            errors=tuple(stored.block_reasons) if not stored.chat_ready else (),
        )

    @staticmethod
    def _registration_projection(record: ChatCommerceAssetRecord) -> tuple[Any, ...]:
        """Fields whose change represents a durable chat-registration transition."""
        return (
            record.asset_id, record.registration_id, record.fulfillment_id,
            record.creator_profile_id, record.commerce_destination,
            record.availability_state, record.chat_ready, record.fulfillment_ready,
            record.recommendation_eligible, record.delivery_eligible, record.active,
            record.temporarily_unavailable, record.retired, record.product_ids,
            record.experience_ids, record.media_link, record.provider_media_id,
            record.provider, record.block_reasons, record.warnings,
        )

    def refresh_asset(self, asset_id: int) -> ChatCommerceRegistrationResult:
        return self.register_fulfilled_asset(int(asset_id))

    def temporarily_disable(
        self,
        asset_id: int,
        *,
        reason: str | None = None,
    ) -> ChatCommerceRegistrationResult:
        record = self.chat_repository.get_by_asset_id(int(asset_id))
        if record is None:
            return ChatCommerceRegistrationResult(
                success=False,
                asset_id=int(asset_id),
                errors=("chat_registration_not_found",),
            )
        now = utc_now()
        stored = self.chat_repository.upsert_record(
            replace(
                record,
                availability_state=ChatAvailabilityState.TEMPORARILY_UNAVAILABLE,
                chat_ready=False,
                recommendation_eligible=False,
                delivery_eligible=False,
                active=False,
                temporarily_unavailable=True,
                temporarily_unavailable_at=now,
                last_refreshed_at=now,
                block_reasons=tuple(
                    dict.fromkeys((*record.block_reasons, "temporarily_unavailable"))
                ),
                registration_provenance={
                    **dict(record.registration_provenance or {}),
                    "temporary_disable_reason": reason,
                },
                updated_at=now,
            )
        )
        return ChatCommerceRegistrationResult.from_record(stored, success=False)

    def re_enable(self, asset_id: int) -> ChatCommerceRegistrationResult:
        record = self.chat_repository.get_by_asset_id(int(asset_id))
        if record is None:
            return ChatCommerceRegistrationResult(
                success=False,
                asset_id=int(asset_id),
                errors=("chat_registration_not_found",),
            )
        cleared = self.chat_repository.upsert_record(
            replace(
                record,
                temporarily_unavailable=False,
                temporarily_unavailable_at=None,
                block_reasons=tuple(
                    reason
                    for reason in record.block_reasons
                    if reason != "temporarily_unavailable"
                ),
                updated_at=utc_now(),
            )
        )
        return self.refresh_asset(cleared.asset_id)

    def retire_asset(
        self,
        asset_id: int,
        *,
        reason: str | None = None,
    ) -> ChatCommerceRegistrationResult:
        record = self.chat_repository.get_by_asset_id(int(asset_id))
        if record is None:
            return ChatCommerceRegistrationResult(
                success=False,
                asset_id=int(asset_id),
                errors=("chat_registration_not_found",),
            )
        now = utc_now()
        stored = self.chat_repository.upsert_record(
            replace(
                record,
                availability_state=ChatAvailabilityState.RETIRED,
                chat_ready=False,
                recommendation_eligible=False,
                delivery_eligible=False,
                active=False,
                retired=True,
                retired_at=now,
                last_refreshed_at=now,
                block_reasons=tuple(
                    dict.fromkeys((*record.block_reasons, "retired"))
                ),
                registration_provenance={
                    **dict(record.registration_provenance or {}),
                    "retirement_reason": reason,
                },
                updated_at=now,
            )
        )
        return ChatCommerceRegistrationResult.from_record(stored, success=False)

    def restore_retired(self, asset_id: int) -> ChatCommerceRegistrationResult:
        record = self.chat_repository.get_by_asset_id(int(asset_id))
        if record is None:
            return ChatCommerceRegistrationResult(
                success=False,
                asset_id=int(asset_id),
                errors=("chat_registration_not_found",),
            )
        self.chat_repository.upsert_record(
            replace(
                record,
                retired=False,
                retired_at=None,
                block_reasons=tuple(
                    reason for reason in record.block_reasons if reason != "retired"
                ),
                updated_at=utc_now(),
            )
        )
        return self.refresh_asset(int(asset_id))

    def get_by_asset_id(self, asset_id: int) -> ChatCommerceAssetRecord | None:
        return self.chat_repository.get_by_asset_id(int(asset_id))

    def list_chat_ready_assets(
        self,
        *,
        creator_profile_id: int | None = None,
        limit: int = 100,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        return self.chat_repository.list_chat_ready(
            creator_profile_id=creator_profile_id,
            limit=limit,
        )

    def list_blocked_assets(
        self,
        *,
        limit: int = 100,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        return self.chat_repository.list_by_state(
            ChatAvailabilityState.BLOCKED,
            limit=limit,
        )

    def list_temporarily_unavailable_assets(
        self,
        *,
        limit: int = 100,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        return self.chat_repository.list_by_state(
            ChatAvailabilityState.TEMPORARILY_UNAVAILABLE,
            limit=limit,
        )

    def list_retired_assets(
        self,
        *,
        limit: int = 100,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        return self.chat_repository.list_by_state(
            ChatAvailabilityState.RETIRED,
            limit=limit,
        )

    def list_by_product(
        self,
        product_id: str,
        *,
        limit: int = 100,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        return self.chat_repository.list_by_product(product_id, limit=limit)

    def list_by_experience(
        self,
        experience_id: str,
        *,
        limit: int = 100,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        return self.chat_repository.list_by_experience(experience_id, limit=limit)

    def get_recommendation_candidates(
        self,
        *,
        creator_profile_id: int | None = None,
        limit: int = 100,
    ) -> tuple[ChatInventoryCandidate, ...]:
        standalone = tuple(
            ChatInventoryCandidate.from_record(record)
            for record in self.chat_repository.list_recommendation_eligible(
                creator_profile_id=creator_profile_id,
                limit=limit,
            )
        )
        if creator_profile_id is None:
            return standalone
        from uuid import UUID
        from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
        photoshoots = tuple(
            ChatInventoryCandidate(
                asset_id=int(row["hero_asset_id"]),
                chat_registration_id=UUID(str(row["deliverable_id"])),
                creator_profile_id=int(row["creator_profile_id"]),
                media_link=None,
                provider_media_id=None,
                recommendation_eligible=True,
                delivery_eligible=False,
                metadata={
                    "source": "PhotoshootCommerceDeliverable",
                    "item_kind": "photoshoot",
                    "deliverable_id": str(row["deliverable_id"]),
                    "display_name": row.get("display_title") or row["display_name"],
                    "description": row.get("display_description"),
                    "shot_count": int(row["shot_count"]),
                    "member_asset_ids": list(row["ordered_member_asset_ids"] or ()),
                    "gallery_path": row["gallery_path"],
                },
            )
            for row in PhotoshootCommerceRepository().list_active(int(creator_profile_id))
            if row.get("hero_asset_id") and row.get("workflow_stage") == "READY"
        )
        return standalone + photoshoots

    def get_delivery_candidates(
        self,
        *,
        creator_profile_id: int | None = None,
        limit: int = 100,
    ) -> tuple[ChatInventoryCandidate, ...]:
        return tuple(
            ChatInventoryCandidate.from_record(record)
            for record in self.chat_repository.list_delivery_eligible(
                creator_profile_id=creator_profile_id,
                limit=limit,
            )
        )

    def eligibility_for_asset(
        self,
        asset_id: int,
        *,
        customer_context: Mapping[str, Any] | None = None,
    ) -> ChatEligibility:
        record = self.chat_repository.get_by_asset_id(int(asset_id))
        if record is None:
            return ChatEligibility(
                chat_ready=False,
                fulfillment_ready=False,
                recommendation_eligible=False,
                delivery_eligible=False,
                destination_valid=False,
                block_reasons=("chat_registration_not_found",),
            )
        block_reasons = list(record.block_reasons)
        if customer_context and self.customer_has_seen_asset(
            asset_id,
            customer_context=customer_context,
        ):
            block_reasons.append("customer_already_seen_asset")
        if customer_context and self.customer_owns_asset(
            asset_id,
            customer_context=customer_context,
        ):
            block_reasons.append("customer_already_owns_asset")
        return ChatEligibility(
            chat_ready=record.chat_ready and not block_reasons,
            fulfillment_ready=record.fulfillment_ready,
            recommendation_eligible=record.recommendation_eligible
            and not block_reasons,
            delivery_eligible=record.delivery_eligible and not block_reasons,
            destination_valid=record.commerce_destination in CHAT_DESTINATIONS,
            temporarily_unavailable=record.temporarily_unavailable,
            retired=record.retired,
            block_reasons=tuple(dict.fromkeys(block_reasons)),
            warnings=record.warnings,
            metadata=record.eligibility.metadata,
        )

    def customer_has_seen_asset(
        self,
        asset_id: int,
        *,
        customer_context: Mapping[str, Any],
    ) -> bool:
        fanvue_account_id = customer_context.get("fanvue_account_id")
        fanvue_user_id = customer_context.get("fanvue_user_id")
        if not fanvue_account_id or not fanvue_user_id:
            return False
        return bool(
            self.content_usage_service.has_seen_content(
                int(fanvue_account_id),
                fanvue_user_id,
                int(asset_id),
            )
        )

    def customer_owns_asset(
        self,
        asset_id: int,
        *,
        customer_context: Mapping[str, Any],
    ) -> bool:
        fanvue_account_id = customer_context.get("fanvue_account_id")
        fanvue_user_id = customer_context.get("fanvue_user_id")
        if not fanvue_account_id or not fanvue_user_id:
            return False
        return self.ownership_decisions.asset(
            fanvue_account_id=int(fanvue_account_id),
            fanvue_user_id=fanvue_user_id,
            asset_id=int(asset_id),
            creator_profile_id=customer_context.get("creator_profile_id"),
        ).blocks_offer

    def backfill_from_fulfillment_ready(
        self,
        *,
        limit: int = 100,
    ) -> tuple[ChatCommerceRegistrationResult, ...]:
        records = self.fulfillment_repository.list_by_state(
            FulfillmentLifecycleState.FULFILLMENT_READY,
            limit=limit,
        )
        return tuple(
            self.register_fulfilled_asset(
                record.asset_id,
                idempotency_key=f"chat-commerce-backfill:{record.asset_id}",
            )
            for record in records
        )

    def _request_from_records(
        self,
        business_asset: BusinessAssetRecord,
        fulfillment: BusinessAssetFulfillmentRecord,
        *,
        idempotency_key: str | None,
        creator_note: str | None,
    ) -> ChatCommerceRegistrationRequest:
        return ChatCommerceRegistrationRequest(
            asset_id=business_asset.asset_id,
            registration_id=business_asset.registration_id,
            fulfillment_id=fulfillment.fulfillment_id,
            commerce_destination=business_asset.selected_commerce_destination,
            creator_profile_id=business_asset.creator_profile_id,
            source_workflow=fulfillment.provenance.get("source_workflow"),
            product_ids=business_asset.product_ids,
            experience_ids=business_asset.experience_ids,
            creator_note=creator_note,
            idempotency_key=idempotency_key,
        )

    def _block_reasons(
        self,
        *,
        request: ChatCommerceRegistrationRequest,
        business_asset: BusinessAssetRecord | None,
        fulfillment: BusinessAssetFulfillmentRecord | None,
        asset: Any | None,
        additional_block_reasons: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if asset is None:
            reasons.append("canonical_asset_not_found")
        else:
            if str(getattr(asset, "status", "") or "").lower() != "approved":
                reasons.append("asset_not_approved")
            if not bool(getattr(asset, "is_active", True)):
                reasons.append("asset_inactive")
        if business_asset is None:
            reasons.append("business_asset_not_found")
        else:
            if str(business_asset.registration_id) != str(request.registration_id):
                reasons.append("business_registration_mismatch")
            if business_asset.commerce_registration_status != CommerceRegistrationStatus.REGISTERED:
                reasons.append("business_asset_not_registered")
            if str(business_asset.approval_status).lower() != "approved":
                reasons.append("asset_not_approved")
            if not business_asset.content_intelligence_ready:
                reasons.append("content_intelligence_not_ready")
            if business_asset.selected_commerce_destination not in CHAT_DESTINATIONS:
                reasons.append("invalid_destination")
            policy = self.entry_policy.can_register_chat(business_asset)
            reasons.extend(policy.reasons)
            if business_asset.business_lifecycle_state == BusinessAssetLifecycleState.RETIRED:
                reasons.append("business_asset_retired")
        if fulfillment is None:
            reasons.append("fulfillment_record_not_found")
        else:
            if str(fulfillment.fulfillment_id) != str(request.fulfillment_id):
                reasons.append("fulfillment_registration_mismatch")
            if fulfillment.lifecycle_state != FulfillmentLifecycleState.FULFILLMENT_READY:
                reasons.append("fulfillment_not_ready")
            if (
                fulfillment.media_link_verification_state
                != MediaLinkVerificationState.VERIFIED
            ):
                reasons.append("media_link_not_verified")
            if not fulfillment.media_link:
                reasons.append("verified_media_link_missing")
            if not (
                fulfillment.provider_media_id
                or fulfillment.provider_full_media_id
                or fulfillment.provider_preview_media_id
            ):
                reasons.append("provider_media_missing")
        reasons.extend(additional_block_reasons)
        return tuple(dict.fromkeys(reasons))

    def _warnings(
        self,
        *,
        business_asset: BusinessAssetRecord | None,
        fulfillment: BusinessAssetFulfillmentRecord | None,
        asset: Any | None,
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if business_asset and not business_asset.product_ids:
            warnings.append("product_relationship_deferred")
        if fulfillment and fulfillment.provider != "fanvue":
            warnings.append("non_fanvue_provider")
        if asset and not getattr(asset, "creator_profile_id", None):
            warnings.append("asset_creator_profile_missing")
        return tuple(dict.fromkeys(warnings))

    @staticmethod
    def _availability_state(
        existing: ChatCommerceAssetRecord | None,
        block_reasons: tuple[str, ...],
    ) -> ChatAvailabilityState:
        if existing and existing.retired:
            return ChatAvailabilityState.RETIRED
        if existing and existing.temporarily_unavailable:
            return ChatAvailabilityState.TEMPORARILY_UNAVAILABLE
        if block_reasons:
            return ChatAvailabilityState.BLOCKED
        return ChatAvailabilityState.CHAT_READY

    @staticmethod
    def _fulfillment_ready(
        fulfillment: BusinessAssetFulfillmentRecord | None,
    ) -> bool:
        return bool(
            fulfillment
            and fulfillment.lifecycle_state == FulfillmentLifecycleState.FULFILLMENT_READY
            and fulfillment.media_link_verification_state
            == MediaLinkVerificationState.VERIFIED
            and fulfillment.media_link
        )

    def _project_business_lifecycle(
        self,
        chat_record: ChatCommerceAssetRecord,
        business_asset: BusinessAssetRecord | None,
    ) -> None:
        if business_asset is None:
            return
        lifecycle = (
            BusinessAssetLifecycleState.CHAT_READY
            if chat_record.chat_ready
            else business_asset.business_lifecycle_state
        )
        if (
            not chat_record.chat_ready
            and business_asset.business_lifecycle_state
            == BusinessAssetLifecycleState.CHAT_READY
        ):
            lifecycle = BusinessAssetLifecycleState.FULFILLMENT_READY
        self.registration_repository.upsert_record(
            replace(
                business_asset,
                business_lifecycle_state=lifecycle,
                last_refreshed_at=utc_now(),
                registration_provenance={
                    **dict(business_asset.registration_provenance or {}),
                    "chat_commerce_registration": {
                        "chat_registration_id": str(
                            chat_record.chat_registration_id
                        ),
                        "availability_state": chat_record.availability_state.value,
                        "chat_ready": chat_record.chat_ready,
                    },
                },
            )
        )

    @staticmethod
    def _relationship_ids(
        primary: tuple[str, ...],
        fallback: tuple[str, ...],
    ) -> tuple[str, ...]:
        return tuple(dict.fromkeys(str(item) for item in (*primary, *fallback) if item))

    @staticmethod
    def _coerce_uuid(value: Any):
        from uuid import UUID

        if isinstance(value, UUID):
            return value
        return UUID(str(value))
