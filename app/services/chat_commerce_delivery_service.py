"""Chat Commerce Delivery preparation boundary."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from app.models.chat_commerce_delivery import (
    ChatDeliveryRequest,
    ChatDeliveryResult,
    ChatDeliveryStatus,
    DeliveryEvidence,
    DeliveryPayload,
    DeliveryValidation,
)
from app.models.fulfillment_registration import (
    FulfillmentLifecycleState,
    FulfillmentRoute,
    MediaLinkVerificationState,
)


class ChatCommerceDeliveryService:
    """Prepare one provider-neutral delivery payload for a Chat Ready Asset."""

    def __init__(
        self,
        *,
        chat_commerce_registration_service: Any | None = None,
        fulfillment_repository: Any | None = None,
        content_usage_service: Any | None = None,
        content_ownership_service: Any | None = None,
        repository: Any | None = None,
        content_commerce_learning_service: Any | None = None,
    ) -> None:
        # Retained as a no-op constructor argument for older composition roots.
        # Delivery does not interpret ownership.
        del content_ownership_service
        if chat_commerce_registration_service is None:
            from app.services.chat_commerce_registration_service import (
                ChatCommerceRegistrationService,
            )

            chat_commerce_registration_service = ChatCommerceRegistrationService()
        if fulfillment_repository is None:
            from app.repositories.fulfillment_registration_repository import (
                FulfillmentRegistrationRepository,
            )

            fulfillment_repository = FulfillmentRegistrationRepository()
        if content_usage_service is None:
            from app.services.content_usage_service import ContentUsageService

            content_usage_service = ContentUsageService()
        if repository is None:
            from app.repositories.chat_commerce_delivery_repository import (
                ChatCommerceDeliveryRepository,
            )

            repository = ChatCommerceDeliveryRepository()
        if content_commerce_learning_service is None:
            from app.services.content_commerce_learning_service import (
                ContentCommerceLearningService,
            )

            content_commerce_learning_service = ContentCommerceLearningService()

        self.chat_commerce_registration_service = chat_commerce_registration_service
        self.fulfillment_repository = fulfillment_repository
        self.content_usage_service = content_usage_service
        self.repository = repository
        self.content_commerce_learning_service = content_commerce_learning_service

    def prepare_delivery(
        self,
        request: ChatDeliveryRequest | Mapping[str, Any],
    ) -> ChatDeliveryResult:
        request = (
            request
            if isinstance(request, ChatDeliveryRequest)
            else ChatDeliveryRequest(**dict(request or {}))
        )
        self._persist("record_request", request.to_context())

        record = self._chat_record(request.asset_id)
        fulfillment = self._fulfillment_record(request.asset_id)
        evidence: list[DeliveryEvidence] = []
        failures: list[str] = []
        warnings: list[str] = []

        self._validate_chat_ready(record, failures, evidence)
        self._validate_fulfillment_ready(record, fulfillment, failures, evidence)
        self._validate_media_link(record, fulfillment, request, failures, evidence)
        self._validate_recommendation(record, request, failures, evidence)
        self._validate_customer_eligibility(record, request, failures, warnings, evidence)
        self._validate_product_eligibility(record, request, failures, evidence)
        self._validate_runtime_suppression(request, failures, evidence)

        failures = list(dict.fromkeys(reason for reason in failures if reason))
        warnings = list(dict.fromkeys(reason for reason in warnings if reason))
        valid = not failures
        validation = DeliveryValidation(
            valid=valid,
            failures=tuple(failures),
            warnings=tuple(warnings),
            retryable=self._retryable(failures),
            metadata={
                "owner": "ChatCommerceDeliveryService",
                "validates_chat_ready": True,
                "validates_fulfillment_ready": True,
                "validates_media_link": True,
            },
        )
        payload = (
            self._payload(request, record=record, fulfillment=fulfillment)
            if valid and record is not None
            else None
        )
        result = ChatDeliveryResult(
            success=valid,
            status=ChatDeliveryStatus.READY if valid else ChatDeliveryStatus.BLOCKED,
            request=request,
            payload=payload,
            validation=validation,
            evidence=tuple(evidence),
            failure_reason=failures[0] if failures else None,
            retryable=validation.retryable,
            created_at=datetime.now(timezone.utc),
            metadata={
                "source": "ChatCommerceDeliveryService",
                "sends_messages": False,
                "prepares_payload_only": True,
            },
        )
        self._persist("record_result", result.to_context())
        self._record_learning_delivery_result(result)
        return result

    def record_execution_result(
        self,
        delivery_result: ChatDeliveryResult | Mapping[str, Any] | None,
        execution_result: Any,
    ) -> None:
        context = (
            delivery_result.to_context()
            if isinstance(delivery_result, ChatDeliveryResult)
            else dict(delivery_result or {})
        )
        delivery_id = str(
            context.get("delivery_id")
            or (context.get("payload") or {}).get("delivery_id")
            or ""
        )
        if not delivery_id:
            return
        executed = bool(getattr(execution_result, "executed", False))
        status = getattr(execution_result, "status", None)
        payload = {
            "status": status,
            "executed": executed,
            "execution_state": getattr(execution_result, "execution_state", None),
            "delivery_method": getattr(execution_result, "delivery_method", None),
            "blocking_reason": getattr(execution_result, "blocking_reason", None),
        }
        if executed:
            self._persist("record_success", delivery_id, payload)
        else:
            self._persist(
                "record_failure",
                delivery_id,
                str(status or payload.get("blocking_reason") or "not_executed"),
                payload,
            )
        self._record_learning_delivery_execution(
            delivery_id=delivery_id,
            payload=self._execution_learning_payload(context, payload),
            success=executed,
            reason=str(status or payload.get("blocking_reason") or "not_executed")
            if not executed
            else None,
        )

    def _chat_record(self, asset_id: int) -> Any | None:
        getter = getattr(self.chat_commerce_registration_service, "get_by_asset_id", None)
        if not callable(getter):
            return None
        try:
            return getter(int(asset_id))
        except Exception:
            return None

    def _fulfillment_record(self, asset_id: int) -> Any | None:
        getter = getattr(self.fulfillment_repository, "get_by_asset_and_route", None)
        if not callable(getter):
            return None
        try:
            return getter(int(asset_id), FulfillmentRoute.CUSTOMER_CONVERSATIONS)
        except Exception:
            return None

    def _validate_chat_ready(
        self,
        record: Any | None,
        failures: list[str],
        evidence: list[DeliveryEvidence],
    ) -> None:
        if record is None:
            failures.append("chat_registration_not_found")
            return
        chat_ready = bool(getattr(record, "chat_ready", False))
        active = bool(getattr(record, "active", True))
        if not chat_ready:
            failures.append("asset_not_chat_ready")
        if not active:
            failures.append("asset_not_active")
        if getattr(record, "temporarily_unavailable", False):
            failures.append("asset_temporarily_unavailable")
        if getattr(record, "retired", False):
            failures.append("asset_retired")
        block_reasons = tuple(getattr(record, "block_reasons", ()) or ())
        failures.extend(block_reasons)
        evidence.append(
            DeliveryEvidence(
                category="chat_readiness",
                signal="chat_registration",
                value=chat_ready,
                metadata={"asset_id": getattr(record, "asset_id", None)},
            )
        )

    def _validate_fulfillment_ready(
        self,
        record: Any | None,
        fulfillment: Any | None,
        failures: list[str],
        evidence: list[DeliveryEvidence],
    ) -> None:
        record_ready = bool(getattr(record, "fulfillment_ready", False))
        fulfillment_ready = record_ready
        lifecycle = getattr(fulfillment, "lifecycle_state", None)
        if fulfillment is not None:
            fulfillment_ready = lifecycle == FulfillmentLifecycleState.FULFILLMENT_READY
        if not fulfillment_ready:
            failures.append("fulfillment_not_ready")
        evidence.append(
            DeliveryEvidence(
                category="fulfillment",
                signal="fulfillment_ready",
                value=fulfillment_ready,
                metadata={"lifecycle_state": getattr(lifecycle, "value", lifecycle)},
            )
        )

    def _validate_media_link(
        self,
        record: Any | None,
        fulfillment: Any | None,
        request: ChatDeliveryRequest,
        failures: list[str],
        evidence: list[DeliveryEvidence],
    ) -> None:
        media_link = self._first_text(
            getattr(fulfillment, "media_link", None),
            getattr(record, "media_link", None),
            self._recommendation_value(request, "media_link", "fanvue_link", "checkout_url"),
        )
        provider_media_id = self._first_text(
            getattr(fulfillment, "provider_media_id", None),
            getattr(fulfillment, "provider_full_media_id", None),
            getattr(fulfillment, "provider_preview_media_id", None),
            getattr(record, "provider_media_id", None),
            self._recommendation_value(request, "provider_media_id", "provider_media_uuid"),
        )
        verification = getattr(fulfillment, "media_link_verification_state", None)
        verified = (
            verification == MediaLinkVerificationState.VERIFIED
            if fulfillment is not None
            else bool(media_link)
        )
        if not media_link:
            failures.append("media_link_missing")
        elif not str(media_link).startswith(("http://", "https://")):
            failures.append("invalid_media_link")
        if not verified:
            failures.append("media_link_not_verified")
        if not provider_media_id:
            failures.append("provider_media_uuid_missing")
        evidence.append(
            DeliveryEvidence(
                category="fulfillment",
                signal="media_link_verified",
                value=verified,
                metadata={"provider_media_id": provider_media_id},
            )
        )

    def _validate_recommendation(
        self,
        record: Any | None,
        request: ChatDeliveryRequest,
        failures: list[str],
        evidence: list[DeliveryEvidence],
    ) -> None:
        recommendation_asset_id = self._recommendation_value(
            request,
            "asset_id",
            "content_item_id",
            "canonical_asset_id",
        )
        if recommendation_asset_id is not None and str(recommendation_asset_id) != str(request.asset_id):
            failures.append("recommendation_asset_mismatch")
        if self._recommendation_value(request, "recommendation_suppressed") is True:
            failures.append("recommendation_suppressed")
        if record is not None and not bool(getattr(record, "recommendation_eligible", False)):
            failures.append("recommendation_not_eligible")
        evidence.append(
            DeliveryEvidence(
                category="recommendation",
                signal="recommendation_valid",
                value="recommendation_suppressed" not in failures,
                metadata={"recommendation_id": self._recommendation_id(request)},
            )
        )

    def _validate_customer_eligibility(
        self,
        record: Any | None,
        request: ChatDeliveryRequest,
        failures: list[str],
        warnings: list[str],
        evidence: list[DeliveryEvidence],
    ) -> None:
        checker = getattr(
            self.chat_commerce_registration_service,
            "eligibility_for_asset",
            None,
        )
        eligibility = None
        if callable(checker):
            try:
                eligibility = checker(
                    request.asset_id,
                    customer_context=request.customer_context,
                )
            except Exception:
                warnings.append("customer_eligibility_unavailable")
        if eligibility is not None:
            if not bool(getattr(eligibility, "delivery_eligible", False)):
                failures.extend(tuple(getattr(eligibility, "block_reasons", ()) or ()))
            warnings.extend(tuple(getattr(eligibility, "warnings", ()) or ()))

        tag = f"chat_asset_{request.asset_id}"
        if self._contains(request.customer_context, request.asset_id, "seen_asset_ids", "delivered_asset_ids"):
            failures.append("customer_already_seen_asset")
        if self._contains(request.customer_context, tag, "owned_content_tags", "owned_asset_tags"):
            failures.append("customer_already_owns_asset")
        evidence.append(
            DeliveryEvidence(
                category="customer",
                signal="customer_eligible",
                value="customer_already_seen_asset" not in failures
                and "customer_already_owns_asset" not in failures,
            )
        )

    def _validate_product_eligibility(
        self,
        record: Any | None,
        request: ChatDeliveryRequest,
        failures: list[str],
        evidence: list[DeliveryEvidence],
    ) -> None:
        status = self._first_text(
            request.decision_context.get("product_status"),
            request.customer_context.get("product_status"),
        )
        if status and status.upper() not in {"ACTIVE", "APPROVED", "AVAILABLE", "PUBLISHED"}:
            failures.append("product_not_eligible")
        product_ids = tuple(str(value) for value in getattr(record, "product_ids", ()) or ())
        evidence.append(
            DeliveryEvidence(
                category="product",
                signal="product_eligible",
                value="product_not_eligible" not in failures,
                metadata={"product_ids": product_ids},
            )
        )

    def _validate_runtime_suppression(
        self,
        request: ChatDeliveryRequest,
        failures: list[str],
        evidence: list[DeliveryEvidence],
    ) -> None:
        if self._contains(
            request.customer_context,
            request.asset_id,
            "recently_delivered_asset_ids",
        ):
            failures.append("recently_delivered_asset")
        if self._contains(
            request.customer_context,
            request.asset_id,
            "recently_recommended_asset_ids",
        ):
            failures.append("recommendation_expired")
        evidence.append(
            DeliveryEvidence(
                category="runtime_suppression",
                signal="cooldowns_clear",
                value=not any(
                    reason in failures
                    for reason in ("recently_delivered_asset", "recommendation_expired")
                ),
            )
        )

    def _payload(
        self,
        request: ChatDeliveryRequest,
        *,
        record: Any,
        fulfillment: Any | None,
    ) -> DeliveryPayload:
        product_ids = tuple(str(value) for value in getattr(record, "product_ids", ()) or ())
        experience_ids = tuple(
            str(value) for value in getattr(record, "experience_ids", ()) or ()
        )
        media_link = self._first_text(
            getattr(fulfillment, "media_link", None),
            getattr(record, "media_link", None),
            self._recommendation_value(request, "media_link", "fanvue_link", "checkout_url"),
        )
        provider_media_id = self._first_text(
            getattr(fulfillment, "provider_media_id", None),
            getattr(fulfillment, "provider_full_media_id", None),
            getattr(fulfillment, "provider_preview_media_id", None),
            getattr(record, "provider_media_id", None),
            self._recommendation_value(request, "provider_media_id", "provider_media_uuid"),
        )
        recommendation_id = self._recommendation_id(request)
        return DeliveryPayload(
            delivery_id=request.delivery_id,
            asset_id=int(request.asset_id),
            chat_registration_id=getattr(record, "chat_registration_id", None),
            fulfillment_id=(
                getattr(fulfillment, "fulfillment_id", None)
                or getattr(record, "fulfillment_id", None)
            ),
            product_id=product_ids[0] if product_ids else None,
            experience_id=experience_ids[0] if experience_ids else None,
            product_ids=product_ids,
            experience_ids=experience_ids,
            fanvue_media_link=media_link,
            provider_media_uuid=provider_media_id,
            provider=(
                self._first_text(
                    getattr(fulfillment, "provider", None),
                    getattr(record, "provider", None),
                    request.provider,
                )
            ),
            customer_id=(
                request.customer_id
                or self._first_text(
                    request.customer_context.get("customer_id"),
                    request.customer_context.get("user_id"),
                    request.customer_context.get("fanvue_user_id"),
                )
            ),
            conversation_id=(
                request.conversation_id
                or self._first_text(
                    request.conversation_context.get("conversation_id"),
                    request.customer_context.get("conversation_id"),
                )
            ),
            recommendation_id=recommendation_id,
            delivery_type="PAID" if media_link else "FREE",
            delivery_method="paid_media_link" if media_link else "free_asset",
            delivery_ready=True,
            readiness={
                "chat_ready": True,
                "fulfillment_ready": True,
                "media_link_verified": bool(media_link),
                "recommendation_valid": True,
                "customer_eligible": True,
            },
            metadata={
                "source": "ChatCommerceDeliveryService",
                "recommendation_owner": "ContentRecommendationService",
                "delivery_owner": "ChatCommerceDeliveryService",
                "sends_messages": False,
            },
        )

    @staticmethod
    def _retryable(failures: list[str]) -> bool:
        return any(
            reason
            in {
                "media_link_missing",
                "invalid_media_link",
                "media_link_not_verified",
                "provider_media_uuid_missing",
                "asset_temporarily_unavailable",
                "fulfillment_not_ready",
                "provider_unavailable",
            }
            for reason in failures
        )

    @staticmethod
    def _first_text(*values: Any) -> str | None:
        for value in values:
            if value is not None and value != "":
                return str(value)
        return None

    @staticmethod
    def _contains(context: Mapping[str, Any], needle: Any, *keys: str) -> bool:
        needle_text = str(needle)
        for key in keys:
            value = context.get(key)
            if isinstance(value, str) and value == needle_text:
                return True
            try:
                if any(str(item) == needle_text for item in value or ()):
                    return True
            except TypeError:
                continue
        return False

    @staticmethod
    def _recommendation_value(request: ChatDeliveryRequest, *names: str) -> Any:
        recommendation = request.recommendation
        if hasattr(recommendation, "to_context"):
            recommendation = recommendation.to_context()
        if not isinstance(recommendation, Mapping):
            return None
        sources = [recommendation]
        metadata = recommendation.get("metadata")
        if isinstance(metadata, Mapping):
            sources.append(metadata)
        rec_metadata = recommendation.get("recommendation_metadata")
        if isinstance(rec_metadata, Mapping):
            sources.append(rec_metadata)
        for source in sources:
            for name in names:
                if source.get(name) is not None:
                    return source.get(name)
        return None

    def _recommendation_id(self, request: ChatDeliveryRequest) -> str:
        explicit = request.recommendation_id or self._recommendation_value(
            request,
            "recommendation_id",
        )
        if explicit:
            return str(explicit)
        key = f"{request.asset_id}:{request.customer_id or ''}:{request.conversation_id or ''}"
        return str(uuid5(NAMESPACE_URL, f"creator-os:content-recommendation:{key}"))

    def _persist(self, method_name: str, *args: Any) -> None:
        method = getattr(self.repository, method_name, None)
        if not callable(method):
            return
        try:
            method(*args)
        except Exception:
            return

    def _record_learning_delivery_result(self, result: ChatDeliveryResult) -> None:
        recorder = getattr(
            self.content_commerce_learning_service,
            "record_delivery_result",
            None,
        )
        if not callable(recorder):
            return
        try:
            recorder(result)
        except Exception:
            return

    def _record_learning_delivery_execution(
        self,
        *,
        delivery_id: str,
        payload: Mapping[str, Any],
        success: bool,
        reason: str | None,
    ) -> None:
        recorder = getattr(
            self.content_commerce_learning_service,
            "record_delivery_execution",
            None,
        )
        if not callable(recorder):
            return
        try:
            recorder(
                delivery_id=delivery_id,
                payload=payload,
                success=success,
                reason=reason,
            )
        except Exception:
            return

    @staticmethod
    def _execution_learning_payload(
        delivery_context: Mapping[str, Any],
        execution_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = delivery_context.get("payload")
        payload = payload if isinstance(payload, Mapping) else {}
        request = delivery_context.get("request")
        request = request if isinstance(request, Mapping) else {}
        return {
            **dict(payload or {}),
            **dict(execution_payload or {}),
            "recommendation_id": payload.get("recommendation_id")
            or request.get("recommendation_id"),
            "asset_id": payload.get("asset_id") or request.get("asset_id"),
            "delivery_id": delivery_context.get("delivery_id")
            or payload.get("delivery_id"),
        }
