"""Customer Conversations fulfillment registration for Business Assets."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, Mapping
from uuid import UUID

from app.models.commerce_destination import (
    DestinationRoutingIntent,
    DestinationRoutingOwner,
    DestinationRoutingStatus,
)
from app.models.commerce_registration import BusinessAssetLifecycleState
from app.models.fulfillment_registration import (
    BusinessAssetFulfillmentRecord,
    FulfillmentLifecycleState,
    FulfillmentRegistrationRequest,
    FulfillmentRegistrationResult,
    FulfillmentRoute,
    MediaLinkSubmission,
    MediaLinkVerificationResult,
    MediaLinkVerificationState,
)
from app.models.generation_engine import utc_now
from app.services.runtime_media_resolver import RuntimeMediaResolver

if TYPE_CHECKING:
    from app.repositories.asset_repository import AssetRepository
    from app.repositories.commerce_destination_repository import (
        CommerceDestinationRepository,
    )
    from app.repositories.commerce_registration_repository import (
        CommerceRegistrationRepository,
    )
    from app.repositories.fulfillment_registration_repository import (
        FulfillmentRegistrationRepository,
    )
    from app.services.chat_commerce_registration_service import (
        ChatCommerceRegistrationService,
    )
    from app.services.publishing_service import PublishingService


CUSTOMER_CONVERSATIONS_FANVUE_FOLDER = "Chat"


class FulfillmentRegistrationService:
    """Consumes Customer Conversations routing intents by canonical asset_id."""

    def __init__(
        self,
        *,
        fulfillment_repository: "FulfillmentRegistrationRepository | None" = None,
        registration_repository: "CommerceRegistrationRepository | None" = None,
        destination_repository: "CommerceDestinationRepository | None" = None,
        publishing_service: "PublishingService | None" = None,
        asset_repository: "AssetRepository | None" = None,
        runtime_media_resolver: RuntimeMediaResolver | None = None,
        chat_commerce_registration_service: "ChatCommerceRegistrationService | None" = None,
        entry_policy: Any | None = None,
    ) -> None:
        if fulfillment_repository is None:
            from app.repositories.fulfillment_registration_repository import (
                FulfillmentRegistrationRepository,
            )

            fulfillment_repository = FulfillmentRegistrationRepository()
        if registration_repository is None:
            from app.repositories.commerce_registration_repository import (
                CommerceRegistrationRepository,
            )

            registration_repository = CommerceRegistrationRepository()
        if destination_repository is None:
            from app.repositories.commerce_destination_repository import (
                CommerceDestinationRepository,
            )

            destination_repository = CommerceDestinationRepository()
        if publishing_service is None:
            from app.services.publishing_service import PublishingService

            publishing_service = PublishingService()
        if asset_repository is None:
            from app.repositories.asset_repository import AssetRepository

            asset_repository = AssetRepository()
        self.fulfillment_repository = fulfillment_repository
        self.registration_repository = registration_repository
        self.destination_repository = destination_repository
        self.publishing_service = publishing_service
        self.asset_repository = asset_repository
        self.runtime_media_resolver = runtime_media_resolver or RuntimeMediaResolver()
        self.chat_commerce_registration_service = (
            chat_commerce_registration_service
        )
        if entry_policy is None:
            from app.services.autonomous_commerce_entry_policy import (
                AutonomousCommerceEntryPolicy,
            )

            entry_policy = AutonomousCommerceEntryPolicy(asset_repository=asset_repository)
        self.entry_policy = entry_policy

    def consume_pending_customer_conversation_intents(
        self,
        *,
        limit: int = 100,
        provider_account_id: int | None = None,
    ) -> tuple[FulfillmentRegistrationResult, ...]:
        results: list[FulfillmentRegistrationResult] = []
        for intent in self.destination_repository.list_pending_routing_intents(
            limit=limit
        ):
            if intent.routing_owner != DestinationRoutingOwner.CUSTOMER_CONVERSATIONS:
                continue
            results.append(
                self.create_or_start_fulfillment(
                    self._request_from_intent(
                        intent,
                        provider_account_id=provider_account_id,
                    )
                )
            )
        return tuple(results)

    def create_or_start_fulfillment(
        self,
        request: FulfillmentRegistrationRequest,
    ) -> FulfillmentRegistrationResult:
        validation_error = self._validate_request(request)
        if validation_error:
            return FulfillmentRegistrationResult(
                success=False,
                asset_id=int(request.asset_id),
                errors=(validation_error,),
            )

        record = self.fulfillment_repository.get_by_asset_and_route(
            request.asset_id,
            request.route,
        )
        now = utc_now()
        if record is None:
            record = BusinessAssetFulfillmentRecord(
                fulfillment_id=BusinessAssetFulfillmentRecord.deterministic_id(
                    request.asset_id,
                    request.route,
                ),
                asset_id=int(request.asset_id),
                registration_id=request.registration_id,
                routing_intent_id=request.routing_intent_id,
                route=request.route,
                route_owner=DestinationRoutingOwner.CUSTOMER_CONVERSATIONS,
                provider=request.provider,
                provider_account_id=request.provider_account_id,
                lifecycle_state=FulfillmentLifecycleState.READY_FOR_UPLOAD,
                provider_metadata={},
                provenance={
                    "source_workflow": request.source_workflow,
                    "source_session_id": request.source_session_id,
                    "idempotency_key": request.idempotency_key,
                    **dict(request.metadata or {}),
                },
                created_at=now,
                updated_at=now,
            )

        job = self.publishing_service.ensure_asset_publishing_job(
            asset_id=request.asset_id,
            provider=request.provider,
            provider_account_id=request.provider_account_id,
            media_link_required=True,
            provider_metadata={
                "routing_intent_id": str(request.routing_intent_id),
                "fulfillment_route": request.route.value,
                "route_owner": DestinationRoutingOwner.CUSTOMER_CONVERSATIONS.value,
                "business_registration_id": str(request.registration_id),
            },
            route_owner=DestinationRoutingOwner.CUSTOMER_CONVERSATIONS.value,
        )
        state = self._state_from_job(job, default=record.lifecycle_state)
        record = replace(
            record,
            publishing_job_id=job.id,
            provider_account_id=request.provider_account_id
            or record.provider_account_id,
            lifecycle_state=state,
            updated_at=now,
        )
        stored = self.fulfillment_repository.upsert_record(record)
        self._update_business_asset_projection(stored)
        self._update_routing_intent(stored)
        return FulfillmentRegistrationResult(
            success=True,
            asset_id=stored.asset_id,
            record=stored,
            publishing_job=job,
        )

    def upload_customer_conversations_asset(
        self,
        *,
        asset_id: int,
        fanvue_account_id: int,
    ) -> FulfillmentRegistrationResult:
        record = self.get_fulfillment_by_asset_id(asset_id)
        if record is None:
            return FulfillmentRegistrationResult(
                success=False,
                asset_id=int(asset_id),
                errors=("fulfillment_record_not_found",),
            )
        if record.lifecycle_state == FulfillmentLifecycleState.FULFILLMENT_READY:
            return FulfillmentRegistrationResult(
                success=True,
                asset_id=record.asset_id,
                record=record,
                warnings=("fulfillment_already_ready",),
            )
        if record.provider_media_id:
            return self.refresh_publishing_job_projection(asset_id=record.asset_id)

        asset = self.asset_repository.get_by_id(record.asset_id)
        media_path = self.runtime_media_resolver.resolve_original_path(
            asset,
            require_exists=True,
        )
        if asset is None or media_path is None:
            failed = self._fail_record(
                record,
                code="local_media_missing",
                message="Canonical Asset local media is missing.",
            )
            return FulfillmentRegistrationResult(
                success=False,
                asset_id=record.asset_id,
                record=failed,
                errors=("local_media_missing",),
            )

        if not record.publishing_job_id:
            return FulfillmentRegistrationResult(
                success=False,
                asset_id=record.asset_id,
                record=record,
                errors=("publishing_job_missing",),
            )

        uploading = self.fulfillment_repository.upsert_record(
            replace(
                record,
                lifecycle_state=FulfillmentLifecycleState.UPLOADING,
                provider_account_id=int(fanvue_account_id),
                updated_at=utc_now(),
            )
        )
        self._update_routing_intent(uploading)
        upload_item = {
            "id": uploading.asset_id,
            "file_path": str(media_path),
            "classification": getattr(asset, "classification", None) or "VIP_IMAGE",
            "folder_name": CUSTOMER_CONVERSATIONS_FANVUE_FOLDER,
            "_fulfillment_trace": {
                "asset_id": uploading.asset_id,
                "routing_intent_id": str(uploading.routing_intent_id),
                "route_owner": uploading.route_owner.value,
            },
        }
        result = self.publishing_service.upload_asset_media_item_for_job(
            job_id=uploading.publishing_job_id,
            fanvue_account_id=int(fanvue_account_id),
            item=upload_item,
            media_link_required=True,
            persist_legacy_asset_state=True,
        )
        upload_result = dict(result.get("upload_result") or {})
        job = result.get("job")
        if not upload_result.get("success"):
            failed = self._fail_record(
                uploading,
                code="provider_upload_failed",
                message=str(upload_result.get("error") or upload_result),
                provider_metadata=upload_result,
            )
            return FulfillmentRegistrationResult(
                success=False,
                asset_id=failed.asset_id,
                record=failed,
                publishing_job=job,
                upload_result=upload_result,
                errors=("provider_upload_failed",),
            )
        media_id = (
            upload_result.get("media_uuid")
            or upload_result.get("full_uuid")
            or upload_result.get("preview_uuid")
        )
        stored = self.fulfillment_repository.upsert_record(
            replace(
                uploading,
                provider_media_id=media_id,
                provider_preview_media_id=upload_result.get("preview_uuid") or media_id,
                provider_full_media_id=upload_result.get("full_uuid") or media_id,
                provider_processing_status=str(
                    upload_result.get("status") or "uploaded"
                ),
                lifecycle_state=FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK,
                media_link_verification_state=MediaLinkVerificationState.MISSING,
                provider_metadata={
                    **dict(uploading.provider_metadata or {}),
                    "upload_result": upload_result,
                    "publishing_job_id": str(uploading.publishing_job_id),
                },
                failure_code=None,
                failure_message=None,
                retry_required=False,
                updated_at=utc_now(),
            )
        )
        self._update_business_asset_projection(stored)
        self._update_routing_intent(stored)
        return FulfillmentRegistrationResult(
            success=True,
            asset_id=stored.asset_id,
            record=stored,
            publishing_job=job,
            upload_result=upload_result,
        )

    def submit_media_link(
        self,
        submission: MediaLinkSubmission,
    ) -> MediaLinkVerificationResult:
        record = self.get_fulfillment_by_asset_id(submission.asset_id)
        if record is None:
            return MediaLinkVerificationResult(
                success=False,
                asset_id=int(submission.asset_id),
                errors=("fulfillment_record_not_found",),
            )
        validation = self.publishing_service.validate_publishing_media_link(
            submission.media_link,
            creator_profile_id=submission.creator_profile_id,
        )
        if not validation["valid"]:
            failed = self._fail_record(
                record,
                code="invalid_media_link",
                message=";".join(validation["errors"]),
                verification_state=MediaLinkVerificationState.FAILED,
            )
            return MediaLinkVerificationResult(
                success=False,
                asset_id=record.asset_id,
                media_link=validation["media_link"],
                verification_state=failed.media_link_verification_state,
                record=failed,
                errors=tuple(validation["errors"]),
            )

        media_link = validation["media_link"]
        duplicate = self.fulfillment_repository.get_by_media_link(media_link)
        if (
            duplicate
            and duplicate.asset_id != record.asset_id
            and not submission.replace_existing
        ):
            failed = self._fail_record(
                record,
                code="duplicate_media_link",
                message="Media Link is already registered to another Asset.",
                verification_state=MediaLinkVerificationState.FAILED,
            )
            return MediaLinkVerificationResult(
                success=False,
                asset_id=record.asset_id,
                media_link=media_link,
                verification_state=failed.media_link_verification_state,
                record=failed,
                errors=("duplicate_media_link",),
            )
        if not record.publishing_job_id:
            return MediaLinkVerificationResult(
                success=False,
                asset_id=record.asset_id,
                media_link=media_link,
                record=record,
                errors=("publishing_job_missing",),
            )

        submitted_at = utc_now()
        submitted = self.fulfillment_repository.upsert_record(
            replace(
                record,
                media_link=media_link,
                media_link_verification_state=MediaLinkVerificationState.SUBMITTED,
                media_link_submitted_at=submitted_at,
                lifecycle_state=FulfillmentLifecycleState.MEDIA_LINK_SUBMITTED,
                provenance={
                    **dict(record.provenance or {}),
                    "media_link_submitted_by": dict(submission.submitted_by or {}),
                    "media_link_idempotency_key": submission.idempotency_key,
                },
                updated_at=submitted_at,
            )
        )
        completed = self.publishing_service.complete_publishing_media_link_workflow(
            submitted.publishing_job_id,
            creator_profile_id=submission.creator_profile_id,
            media_link=media_link,
        )
        if not completed.get("success"):
            failed = self._fail_record(
                submitted,
                code=str(completed.get("reason") or "media_link_verification_failed"),
                message=";".join(completed.get("errors") or ()),
                verification_state=MediaLinkVerificationState.FAILED,
            )
            return MediaLinkVerificationResult(
                success=False,
                asset_id=record.asset_id,
                media_link=media_link,
                verification_state=failed.media_link_verification_state,
                record=failed,
                errors=tuple(completed.get("errors") or (completed.get("reason"),)),
            )

        verified_at = utc_now()
        verified = self.fulfillment_repository.upsert_record(
            replace(
                submitted,
                lifecycle_state=FulfillmentLifecycleState.FULFILLMENT_READY,
                media_link_verification_state=MediaLinkVerificationState.VERIFIED,
                media_link_verified_at=verified_at,
                fulfillment_ready_at=verified_at,
                failure_code=None,
                failure_message=None,
                retry_required=False,
                provider_metadata={
                    **dict(submitted.provider_metadata or {}),
                    "media_link_workflow": {
                        "creator_profile_id": submission.creator_profile_id,
                        "publishing_job_id": str(submitted.publishing_job_id),
                        "asset_only": True,
                        "verified": True,
                    },
                },
                updated_at=verified_at,
            )
        )
        self._update_business_asset_projection(verified)
        self._update_routing_intent(verified)
        self._register_chat_if_fulfilled(verified)
        return MediaLinkVerificationResult(
            success=True,
            asset_id=verified.asset_id,
            media_link=verified.media_link,
            verification_state=verified.media_link_verification_state,
            record=verified,
            warnings=tuple(validation["warnings"]),
        )

    def register_legacy_upload(
        self,
        *,
        asset_id: int,
        provider_media_id: str,
        routing_intent_id: UUID,
        registration_id: UUID,
        provider: str = "fanvue",
        metadata: Mapping[str, Any] | None = None,
    ) -> FulfillmentRegistrationResult:
        """Backfill an unambiguous existing upload without re-uploading."""

        if not provider_media_id:
            return FulfillmentRegistrationResult(
                success=False,
                asset_id=int(asset_id),
                errors=("ambiguous_legacy_upload",),
            )
        record = BusinessAssetFulfillmentRecord(
            fulfillment_id=BusinessAssetFulfillmentRecord.deterministic_id(
                asset_id,
                FulfillmentRoute.CUSTOMER_CONVERSATIONS,
            ),
            asset_id=int(asset_id),
            registration_id=registration_id,
            routing_intent_id=routing_intent_id,
            route=FulfillmentRoute.CUSTOMER_CONVERSATIONS,
            route_owner=DestinationRoutingOwner.CUSTOMER_CONVERSATIONS,
            provider=provider,
            provider_media_id=provider_media_id,
            provider_preview_media_id=provider_media_id,
            provider_full_media_id=provider_media_id,
            provider_processing_status="ready",
            lifecycle_state=FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK,
            media_link_verification_state=MediaLinkVerificationState.MISSING,
            provider_metadata=dict(metadata or {}),
            provenance={"source": "legacy_fulfillment_backfill"},
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        stored = self.fulfillment_repository.upsert_record(record)
        self._update_business_asset_projection(stored)
        self._update_routing_intent(stored)
        return FulfillmentRegistrationResult(
            success=True,
            asset_id=stored.asset_id,
            record=stored,
        )

    def refresh_publishing_job_projection(
        self,
        *,
        asset_id: int,
    ) -> FulfillmentRegistrationResult:
        record = self.get_fulfillment_by_asset_id(asset_id)
        if record is None:
            return FulfillmentRegistrationResult(
                success=False,
                asset_id=int(asset_id),
                errors=("fulfillment_record_not_found",),
            )
        if not record.publishing_job_id:
            return FulfillmentRegistrationResult(
                success=True,
                asset_id=record.asset_id,
                record=record,
                warnings=("publishing_job_missing",),
            )
        job = self.publishing_service.get_publishing_job(record.publishing_job_id)
        if not job:
            return FulfillmentRegistrationResult(
                success=True,
                asset_id=record.asset_id,
                record=record,
                warnings=("publishing_job_not_found",),
            )
        state = self._state_from_job(job, default=record.lifecycle_state)
        updated = self.fulfillment_repository.upsert_record(
            replace(
                record,
                lifecycle_state=state,
                provider_media_id=job.provider_media_id or record.provider_media_id,
                provider_preview_media_id=job.provider_preview_media_id
                or record.provider_preview_media_id,
                provider_full_media_id=job.provider_full_media_id
                or record.provider_full_media_id,
                provider_processing_status=job.provider_status,
                updated_at=utc_now(),
            )
        )
        self._update_business_asset_projection(updated)
        self._update_routing_intent(updated)
        self._register_chat_if_fulfilled(updated)
        return FulfillmentRegistrationResult(
            success=True,
            asset_id=updated.asset_id,
            record=updated,
            publishing_job=job,
        )

    def retry_fulfillment(
        self,
        *,
        asset_id: int,
        fanvue_account_id: int,
    ) -> FulfillmentRegistrationResult:
        record = self.get_fulfillment_by_asset_id(asset_id)
        if record is None:
            return FulfillmentRegistrationResult(
                success=False,
                asset_id=int(asset_id),
                errors=("fulfillment_record_not_found",),
            )
        if record.provider_media_id:
            waiting = self.fulfillment_repository.upsert_record(
                replace(
                    record,
                    lifecycle_state=FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK,
                    retry_required=False,
                    updated_at=utc_now(),
                )
            )
            self._update_business_asset_projection(waiting)
            self._update_routing_intent(waiting)
            return FulfillmentRegistrationResult(
                success=True,
                asset_id=waiting.asset_id,
                record=waiting,
                warnings=("existing_provider_media_reused",),
            )
        return self.upload_customer_conversations_asset(
            asset_id=asset_id,
            fanvue_account_id=fanvue_account_id,
        )

    def get_fulfillment_by_asset_id(
        self,
        asset_id: int,
    ) -> BusinessAssetFulfillmentRecord | None:
        return self.fulfillment_repository.get_by_asset_and_route(
            int(asset_id),
            FulfillmentRoute.CUSTOMER_CONVERSATIONS,
        )

    def get_fulfillment_by_route_intent_id(
        self,
        routing_intent_id: UUID | str,
    ) -> BusinessAssetFulfillmentRecord | None:
        return self.fulfillment_repository.get_by_route_intent_id(routing_intent_id)

    def list_by_state(
        self,
        state: FulfillmentLifecycleState | str,
        *,
        limit: int = 100,
    ) -> tuple[BusinessAssetFulfillmentRecord, ...]:
        return self.fulfillment_repository.list_by_state(state, limit=limit)

    def list_ready_for_upload(
        self,
        *,
        limit: int = 100,
    ) -> tuple[BusinessAssetFulfillmentRecord, ...]:
        return self.list_by_state(FulfillmentLifecycleState.READY_FOR_UPLOAD, limit=limit)

    def list_waiting_for_media_link(
        self,
        *,
        limit: int = 100,
    ) -> tuple[BusinessAssetFulfillmentRecord, ...]:
        return self.list_by_state(
            FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK,
            limit=limit,
        )

    def list_fulfillment_ready(
        self,
        *,
        limit: int = 100,
    ) -> tuple[BusinessAssetFulfillmentRecord, ...]:
        return self.list_by_state(
            FulfillmentLifecycleState.FULFILLMENT_READY,
            limit=limit,
        )

    def list_failed_or_retry_required(
        self,
        *,
        limit: int = 100,
    ) -> tuple[BusinessAssetFulfillmentRecord, ...]:
        failed = self.list_by_state(FulfillmentLifecycleState.FAILED, limit=limit)
        retry = self.list_by_state(FulfillmentLifecycleState.RETRY_REQUIRED, limit=limit)
        return tuple((*failed, *retry))[:limit]

    def _request_from_intent(
        self,
        intent: DestinationRoutingIntent,
        *,
        provider_account_id: int | None,
    ) -> FulfillmentRegistrationRequest:
        return FulfillmentRegistrationRequest(
            asset_id=int(intent.asset_id),
            registration_id=intent.registration_id,
            routing_intent_id=intent.routing_intent_id,
            provider_account_id=provider_account_id,
            source_workflow=intent.source_workflow,
            metadata={"selected_destination": intent.selected_destination.value},
        )

    def _validate_request(
        self,
        request: FulfillmentRegistrationRequest,
    ) -> str | None:
        if request.route != FulfillmentRoute.CUSTOMER_CONVERSATIONS:
            return "unsupported_fulfillment_route"
        record = self.registration_repository.get_by_asset_id(request.asset_id)
        if record is None:
            return "business_asset_not_found"
        if str(record.registration_id) != str(request.registration_id):
            return "business_registration_mismatch"
        if str(record.approval_status).lower() != "approved":
            return "asset_not_approved"
        policy = self.entry_policy.can_start_fulfillment(
            record,
            selected_destination=record.selected_commerce_destination,
        )
        if not policy.allowed:
            return policy.reasons[0] if policy.reasons else "commerce_entry_not_allowed"
        return None

    def _fail_record(
        self,
        record: BusinessAssetFulfillmentRecord,
        *,
        code: str,
        message: str,
        provider_metadata: Mapping[str, Any] | None = None,
        verification_state: MediaLinkVerificationState | None = None,
    ) -> BusinessAssetFulfillmentRecord:
        failed = self.fulfillment_repository.upsert_record(
            replace(
                record,
                lifecycle_state=FulfillmentLifecycleState.RETRY_REQUIRED,
                media_link_verification_state=verification_state
                or record.media_link_verification_state,
                failure_code=code,
                failure_message=message,
                retry_count=int(record.retry_count or 0) + 1,
                retry_required=True,
                provider_metadata={
                    **dict(record.provider_metadata or {}),
                    "last_failure": dict(provider_metadata or {}),
                },
                updated_at=utc_now(),
            )
        )
        self._update_business_asset_projection(failed)
        self._update_routing_intent(failed)
        return failed

    def _update_business_asset_projection(
        self,
        record: BusinessAssetFulfillmentRecord,
    ) -> None:
        business_asset = self.registration_repository.get_by_asset_id(record.asset_id)
        if business_asset is None:
            return
        lifecycle = {
            FulfillmentLifecycleState.READY_FOR_UPLOAD: BusinessAssetLifecycleState.AWAITING_UPLOAD,
            FulfillmentLifecycleState.UPLOAD_QUEUED: BusinessAssetLifecycleState.AWAITING_UPLOAD,
            FulfillmentLifecycleState.UPLOADING: BusinessAssetLifecycleState.AWAITING_UPLOAD,
            FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK: BusinessAssetLifecycleState.WAITING_FOR_MEDIA_LINK,
            FulfillmentLifecycleState.MEDIA_LINK_SUBMITTED: BusinessAssetLifecycleState.WAITING_FOR_MEDIA_LINK,
            FulfillmentLifecycleState.FULFILLMENT_READY: BusinessAssetLifecycleState.FULFILLMENT_READY,
            FulfillmentLifecycleState.RETRY_REQUIRED: BusinessAssetLifecycleState.ROUTING_FAILED,
            FulfillmentLifecycleState.FAILED: BusinessAssetLifecycleState.ROUTING_FAILED,
        }.get(record.lifecycle_state, business_asset.business_lifecycle_state)
        self.registration_repository.upsert_record(
            replace(
                business_asset,
                business_lifecycle_state=lifecycle,
                fulfillment_readiness=record.readiness.to_context(),
                last_refreshed_at=utc_now(),
            )
        )

    def _update_routing_intent(
        self,
        record: BusinessAssetFulfillmentRecord,
    ) -> None:
        intent = None
        for candidate in self.destination_repository.list_routing_intents(
            record.asset_id,
            include_cancelled=True,
        ):
            if str(candidate.routing_intent_id) == str(record.routing_intent_id):
                intent = candidate
                break
        if intent is None:
            return
        status = {
            FulfillmentLifecycleState.READY_FOR_UPLOAD: DestinationRoutingStatus.ROUTING,
            FulfillmentLifecycleState.UPLOAD_QUEUED: DestinationRoutingStatus.ROUTING,
            FulfillmentLifecycleState.UPLOADING: DestinationRoutingStatus.UPLOAD_IN_PROGRESS,
            FulfillmentLifecycleState.UPLOADED: DestinationRoutingStatus.UPLOAD_IN_PROGRESS,
            FulfillmentLifecycleState.MEDIA_READY: DestinationRoutingStatus.WAITING_FOR_MEDIA_LINK,
            FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK: DestinationRoutingStatus.WAITING_FOR_MEDIA_LINK,
            FulfillmentLifecycleState.MEDIA_LINK_SUBMITTED: DestinationRoutingStatus.WAITING_FOR_MEDIA_LINK,
            FulfillmentLifecycleState.MEDIA_LINK_VERIFIED: DestinationRoutingStatus.FULFILLMENT_READY,
            FulfillmentLifecycleState.FULFILLMENT_READY: DestinationRoutingStatus.FULFILLMENT_READY,
            FulfillmentLifecycleState.RETRY_REQUIRED: DestinationRoutingStatus.ROUTING_FAILED,
            FulfillmentLifecycleState.FAILED: DestinationRoutingStatus.ROUTING_FAILED,
        }.get(record.lifecycle_state, intent.routing_status)
        self.destination_repository.upsert_routing_intent(
            replace(
                intent,
                routing_status=status,
                metadata={
                    **dict(intent.metadata or {}),
                    "fulfillment_id": str(record.fulfillment_id),
                    "fulfillment_lifecycle_state": record.lifecycle_state.value,
                    "provider": record.provider,
                    "provider_media_id": record.provider_media_id,
                    "media_link_verification_state": (
                        record.media_link_verification_state.value
                    ),
                },
                updated_at=utc_now(),
            )
        )

    def _state_from_job(
        self,
        job: Any,
        *,
        default: FulfillmentLifecycleState,
    ) -> FulfillmentLifecycleState:
        projection = self.publishing_service.project_publishing_status(job)
        publishing_status = projection.publishing_status
        if publishing_status == "QUEUED":
            return FulfillmentLifecycleState.UPLOAD_QUEUED
        if publishing_status == "UPLOADING":
            return FulfillmentLifecycleState.UPLOADING
        if publishing_status == "UPLOADED":
            return FulfillmentLifecycleState.MEDIA_READY
        if publishing_status == "WAITING_FOR_MEDIA_LINK":
            return FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK
        if publishing_status == "MEDIA_LINK_VERIFIED":
            return FulfillmentLifecycleState.MEDIA_LINK_VERIFIED
        if publishing_status == "PUBLISHING_COMPLETE":
            return FulfillmentLifecycleState.FULFILLMENT_READY
        if publishing_status == "RETRY_REQUIRED":
            return FulfillmentLifecycleState.RETRY_REQUIRED
        if publishing_status == "FAILED":
            return FulfillmentLifecycleState.FAILED
        return default

    def _register_chat_if_fulfilled(
        self,
        record: BusinessAssetFulfillmentRecord,
    ) -> None:
        if record.lifecycle_state != FulfillmentLifecycleState.FULFILLMENT_READY:
            return
        service = self.chat_commerce_registration_service
        if service is None:
            try:
                from app.services.chat_commerce_registration_service import (
                    ChatCommerceRegistrationService,
                )

                service = ChatCommerceRegistrationService(
                    registration_repository=self.registration_repository,
                    fulfillment_repository=self.fulfillment_repository,
                    asset_repository=self.asset_repository,
                )
            except Exception:
                return
        try:
            service.register_fulfilled_asset(
                record.asset_id,
                idempotency_key=f"fulfillment-ready:{record.fulfillment_id}",
            )
        except Exception:
            return
