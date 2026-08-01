"""Synchronize provider commerce outcomes into Creator OS learning."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.models.commerce_outcome import (
    CommerceOutcome,
    CommerceOutcomeRequest,
    CommerceOutcomeResult,
    CommerceOutcomeStatus,
    PurchaseOutcome,
    PurchaseStatus,
    RecommendationOutcome,
    RevenueAttribution,
    utc_now_iso,
)


class CommerceOutcomeSynchronizationService:
    """Bridge Fanvue purchases back to Creator OS business intelligence."""

    def __init__(
        self,
        *,
        repository: Any | None = None,
        delivery_repository: Any | None = None,
        commerce_registration_repository: Any | None = None,
        business_learning_service: Any | None = None,
        customer_intelligence_service: Any | None = None,
        customer_history_repository: Any | None = None,
        content_commerce_learning_service: Any | None = None,
        fanvue_api_factory: Any | None = None,
    ) -> None:
        if repository is None:
            from app.repositories.commerce_outcome_repository import (
                CommerceOutcomeRepository,
            )

            repository = CommerceOutcomeRepository()
        if delivery_repository is None:
            from app.repositories.chat_commerce_delivery_repository import (
                ChatCommerceDeliveryRepository,
            )

            delivery_repository = ChatCommerceDeliveryRepository()
        if commerce_registration_repository is None:
            from app.repositories.commerce_registration_repository import (
                CommerceRegistrationRepository,
            )

            commerce_registration_repository = CommerceRegistrationRepository()
        if business_learning_service is None:
            from app.services.business_learning_service import BusinessLearningService

            business_learning_service = BusinessLearningService()
        if customer_intelligence_service is None:
            from app.services.customer_intelligence_service import (
                CustomerIntelligenceCompatibilityAdapter as CustomerIntelligenceService,
            )

            customer_intelligence_service = CustomerIntelligenceService()
        if content_commerce_learning_service is None:
            from app.services.content_commerce_learning_service import (
                ContentCommerceLearningService,
            )

            content_commerce_learning_service = ContentCommerceLearningService(
                business_learning_service=business_learning_service,
            )

        self.repository = repository
        self.delivery_repository = delivery_repository
        self.commerce_registrations = commerce_registration_repository
        self.business_learning = business_learning_service
        self.customer_intelligence = customer_intelligence_service
        self.customer_history_repository = customer_history_repository
        self.content_commerce_learning = content_commerce_learning_service
        self.fanvue_api_factory = fanvue_api_factory

    def synchronize_provider_outcome(
        self,
        request: CommerceOutcomeRequest | Mapping[str, Any],
    ) -> CommerceOutcomeResult:
        resolved_request = (
            request
            if isinstance(request, CommerceOutcomeRequest)
            else CommerceOutcomeRequest(provider_payload=dict(request or {}))
        )
        payload = dict(resolved_request.provider_payload or {})
        purchase = self._purchase_from_payload(resolved_request, payload)
        provider = self._text(resolved_request.provider) or "fanvue"

        if not purchase.provider_transaction_id:
            self._record_failure(
                provider=provider,
                provider_transaction_id=None,
                reason="missing_provider_transaction_id",
                payload=payload,
            )
            return CommerceOutcomeResult(
                success=False,
                retryable=True,
                errors=("missing_provider_transaction_id",),
                metadata={"source": "CommerceOutcomeSynchronizationService"},
            )

        existing = self._existing(provider, purchase.provider_transaction_id)
        if existing is not None:
            self._record_duplicate(
                provider=provider,
                provider_transaction_id=purchase.provider_transaction_id,
                existing=existing,
                payload=payload,
            )
            return CommerceOutcomeResult(
                success=True,
                duplicate=True,
                warnings=("duplicate_purchase",),
                metadata={
                    "source": "CommerceOutcomeSynchronizationService",
                    "existing_outcome": existing,
                },
            )

        attribution = self._resolve_attribution(payload, purchase)
        recommendation = RecommendationOutcome(
            recommendation_id=attribution.recommendation_id,
            delivery_id=attribution.delivery_id,
            recommended=bool(attribution.recommendation_id),
            delivered=bool(attribution.delivery_id),
            purchased=purchase.purchase_status
            in {PurchaseStatus.PAID, PurchaseStatus.PURCHASED},
            revenue_cents=purchase.net_revenue_cents,
            success=bool(
                attribution.recommendation_id
                and attribution.delivery_id
                and purchase.net_revenue_cents >= 0
            ),
            metadata={
                "provider_transaction_id": purchase.provider_transaction_id,
                "matched_by": attribution.matched_by,
            },
        )
        status = self._outcome_status(purchase, attribution)
        outcome = CommerceOutcome(
            outcome_id=CommerceOutcome.deterministic_id(
                provider=provider,
                provider_transaction_id=purchase.provider_transaction_id,
            ),
            provider=provider,
            purchase=purchase,
            attribution=attribution,
            recommendation_outcome=recommendation,
            status=status,
            source=resolved_request.source,
            received_at=resolved_request.received_at or utc_now_iso(),
            synchronized_at=utc_now_iso(),
            failure_reason=(
                "unmatched_transaction"
                if status == CommerceOutcomeStatus.UNMATCHED
                else None
            ),
            raw_payload=payload,
        )
        self._record_outcome(outcome)
        recommendation_learning_result = self._record_recommendation_outcome(outcome)

        learning_result = self._feed_business_learning(outcome)
        customer_result = None
        if status != CommerceOutcomeStatus.UNMATCHED:
            customer_result = self._update_customer_history(outcome)
        else:
            self._record_failure(
                provider=provider,
                provider_transaction_id=purchase.provider_transaction_id,
                reason="unmatched_transaction",
                payload=outcome.to_context(),
            )

        return CommerceOutcomeResult(
            success=status
            in {
                CommerceOutcomeStatus.SYNCHRONIZED,
                CommerceOutcomeStatus.REFUNDED,
            },
            outcome=outcome,
            retryable=status == CommerceOutcomeStatus.UNMATCHED,
            warnings=attribution.unresolved_fields,
            business_learning_result=learning_result,
            customer_history_result=customer_result,
            metadata={
                "source": "CommerceOutcomeSynchronizationService",
                "business_learning_fed": learning_result is not None,
                "recommendation_learning_recorded": recommendation_learning_result
                is not None,
                "customer_history_updated": customer_result is not None,
            },
        )

    def sync_fanvue_outcomes(
        self,
        *,
        fanvue_account_id: int,
        since: str | None = None,
        limit: int = 100,
    ) -> tuple[CommerceOutcomeResult, ...]:
        api = self._fanvue_api(fanvue_account_id)
        if api is None:
            return (
                CommerceOutcomeResult(
                    success=False,
                    retryable=True,
                    errors=("fanvue_api_unavailable",),
                ),
            )
        records = self._list_provider_outcomes(api, since=since, limit=limit)
        return tuple(
            self.synchronize_provider_outcome(
                CommerceOutcomeRequest(
                    provider_payload=record,
                    provider="fanvue",
                    source="fanvue_api",
                    provider_account_id=fanvue_account_id,
                )
            )
            for record in records
        )

    def _purchase_from_payload(
        self,
        request: CommerceOutcomeRequest,
        payload: Mapping[str, Any],
    ) -> PurchaseOutcome:
        provider_account_id = (
            request.provider_account_id
            or self._first_value(
                payload,
                "fanvue_account_id",
                "provider_account_id",
                "account_id",
                "creator_account_id",
            )
        )
        gross = self._cents(
            self._first_value(
                payload,
                "gross_revenue_cents",
                "revenue_cents",
                "amount_cents",
                "purchase_amount_cents",
            ),
            fallback_amount=self._first_value(
                payload,
                "amount",
                "purchase_amount",
                "price",
                "gross",
                "gross_amount",
            ),
        )
        tip = self._cents(
            self._first_value(payload, "tip_cents", "tip_amount_cents"),
            fallback_amount=self._first_value(payload, "tip_amount", "tip"),
        )
        refund = self._cents(
            self._first_value(payload, "refund_cents", "refund_amount_cents"),
            fallback_amount=self._first_value(payload, "refund_amount", "refund"),
        )
        fee = self._cents(
            self._first_value(payload, "fee_cents", "platform_fee_cents"),
            fallback_amount=self._first_value(payload, "fee", "platform_fee"),
        )
        net = self._cents(
            self._first_value(payload, "net_revenue_cents", "net_amount_cents"),
            fallback_amount=self._first_value(payload, "net_amount", "net_revenue"),
            default=gross + tip - refund - fee,
        )
        status = self._purchase_status(
            self._first_value(payload, "purchase_status", "status", "event_type")
        )
        return PurchaseOutcome(
            provider_transaction_id=self._text(
                request.idempotency_key
                or self._first_value(
                    payload,
                    "provider_transaction_id",
                    "transaction_id",
                    "external_event_id",
                    "event_id",
                    "order_id",
                    "purchase_id",
                    "id",
                )
            ),
            purchase_status=status,
            purchased_at=self._text(
                self._first_value(
                    payload,
                    "purchase_timestamp",
                    "purchased_at",
                    "created_at",
                    "timestamp",
                    "occurred_at",
                )
            ),
            currency=self._text(payload.get("currency")) or "USD",
            gross_revenue_cents=gross,
            tip_cents=tip,
            refund_cents=refund,
            fee_cents=fee,
            net_revenue_cents=net,
            provider_media_uuid=self._text(
                self._first_value(
                    payload,
                    "fanvue_media_uuid",
                    "provider_media_uuid",
                    "provider_media_id",
                    "media_uuid",
                    "mediaUuid",
                )
            ),
            provider_customer_id=self._text(
                self._first_value(
                    payload,
                    "fanvue_user_id",
                    "fanvue_user_uuid",
                    "provider_customer_id",
                    "customer_id",
                    "user_id",
                )
            ),
            provider_account_id=self._text(provider_account_id),
            provider_raw_status=self._text(
                self._first_value(payload, "status", "event_type")
            ),
            metadata=dict(payload.get("metadata") or {})
            if isinstance(payload.get("metadata"), Mapping)
            else {},
        )

    def _resolve_attribution(
        self,
        payload: Mapping[str, Any],
        purchase: PurchaseOutcome,
    ) -> RevenueAttribution:
        direct = self._direct_attribution(payload)
        delivery = self._resolve_delivery(payload, purchase, direct)
        merged = {**delivery, **{k: v for k, v in direct.items() if v is not None}}
        asset_id = self._int(merged.get("asset_id"))
        business_asset_id = self._int(merged.get("business_asset_id")) or asset_id
        if business_asset_id is None and asset_id is not None:
            business_asset_id = self._business_asset_id(asset_id)

        unresolved = tuple(
            field
            for field, value in (
                ("recommendation_id", merged.get("recommendation_id")),
                ("delivery_id", merged.get("delivery_id")),
                ("asset_id", asset_id),
                ("customer_id", merged.get("customer_id") or purchase.provider_customer_id),
            )
            if value in {None, ""}
        )
        matched_by = (
            "direct_payload"
            if direct.get("delivery_id") or direct.get("recommendation_id")
            else delivery.get("matched_by")
        )
        confidence = 1.0 if not unresolved else 0.7 if delivery else 0.25
        return RevenueAttribution(
            recommendation_id=self._text(merged.get("recommendation_id")),
            delivery_id=self._text(merged.get("delivery_id")),
            asset_id=asset_id,
            business_asset_id=business_asset_id,
            product_id=self._text(merged.get("product_id")),
            experience_id=self._text(merged.get("experience_id")),
            customer_id=self._text(merged.get("customer_id") or purchase.provider_customer_id),
            conversation_id=self._text(merged.get("conversation_id")),
            provider_media_uuid=self._text(
                merged.get("provider_media_uuid") or purchase.provider_media_uuid
            ),
            matched_by=matched_by or "unmatched",
            confidence=confidence,
            unresolved_fields=unresolved,
            metadata={
                "delivery_resolution": delivery,
                "direct_payload": direct,
            },
        )

    def _direct_attribution(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        metadata = payload.get("metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        compatibility = payload.get("chat_delivery_metadata")
        compatibility = compatibility if isinstance(compatibility, Mapping) else {}
        merged = {**metadata, **compatibility, **dict(payload)}
        product_ids = self._tuple_value(merged.get("product_ids"))
        experience_ids = self._tuple_value(merged.get("experience_ids"))
        return {
            "recommendation_id": self._first_value(
                merged, "recommendation_id", "content_recommendation_id"
            ),
            "delivery_id": self._first_value(merged, "delivery_id"),
            "asset_id": self._first_value(
                merged, "asset_id", "canonical_asset_id", "content_item_id"
            ),
            "business_asset_id": self._first_value(merged, "business_asset_id"),
            "product_id": self._first_value(merged, "product_id")
            or (product_ids[0] if product_ids else None),
            "experience_id": self._first_value(merged, "experience_id")
            or (experience_ids[0] if experience_ids else None),
            "customer_id": self._first_value(merged, "customer_id", "local_user_id"),
            "conversation_id": self._first_value(merged, "conversation_id"),
            "provider_media_uuid": self._first_value(
                merged,
                "provider_media_uuid",
                "provider_media_id",
                "fanvue_media_uuid",
                "media_uuid",
            ),
        }

    def _resolve_delivery(
        self,
        payload: Mapping[str, Any],
        purchase: PurchaseOutcome,
        direct: Mapping[str, Any],
    ) -> dict[str, Any]:
        events_getter = getattr(self.delivery_repository, "list_events", None)
        if not callable(events_getter):
            return {}
        try:
            events = tuple(events_getter())
        except Exception:
            return {}
        needles = {
            "delivery_id": self._text(direct.get("delivery_id")),
            "recommendation_id": self._text(direct.get("recommendation_id")),
            "provider_media_uuid": self._text(
                direct.get("provider_media_uuid") or purchase.provider_media_uuid
            ),
            "customer_id": self._text(
                direct.get("customer_id") or purchase.provider_customer_id
            ),
        }
        for event in reversed(events):
            flat = self._flatten_mapping(event)
            if not self._delivery_event_matches(flat, needles):
                continue
            product_ids = self._tuple_value(flat.get("product_ids"))
            experience_ids = self._tuple_value(flat.get("experience_ids"))
            return {
                "matched_by": "delivery_history",
                "delivery_id": flat.get("delivery_id"),
                "recommendation_id": flat.get("recommendation_id"),
                "asset_id": flat.get("asset_id"),
                "product_id": flat.get("product_id")
                or (product_ids[0] if product_ids else None),
                "experience_id": flat.get("experience_id")
                or (experience_ids[0] if experience_ids else None),
                "customer_id": flat.get("customer_id"),
                "conversation_id": flat.get("conversation_id"),
                "provider_media_uuid": flat.get("provider_media_uuid")
                or flat.get("provider_media_id"),
            }
        return {}

    def _delivery_event_matches(
        self,
        flat: Mapping[str, Any],
        needles: Mapping[str, str | None],
    ) -> bool:
        if needles.get("delivery_id") and str(flat.get("delivery_id")) == needles["delivery_id"]:
            return True
        if needles.get("recommendation_id") and str(flat.get("recommendation_id")) == needles["recommendation_id"]:
            return True
        media = needles.get("provider_media_uuid")
        if media and media in {
            self._text(flat.get("provider_media_uuid")),
            self._text(flat.get("provider_media_id")),
            self._text(flat.get("fanvue_media_uuid")),
        }:
            customer = needles.get("customer_id")
            return not customer or customer in {
                self._text(flat.get("customer_id")),
                self._text(flat.get("provider_customer_id")),
            }
        return False

    def _outcome_status(
        self,
        purchase: PurchaseOutcome,
        attribution: RevenueAttribution,
    ) -> CommerceOutcomeStatus:
        if purchase.purchase_status in {
            PurchaseStatus.REFUNDED,
            PurchaseStatus.PARTIALLY_REFUNDED,
        } or purchase.refund_cents > 0:
            return CommerceOutcomeStatus.REFUNDED
        if purchase.purchase_status in {PurchaseStatus.FAILED, PurchaseStatus.CANCELLED}:
            return CommerceOutcomeStatus.FAILED
        if attribution.unresolved_fields:
            return CommerceOutcomeStatus.UNMATCHED
        return CommerceOutcomeStatus.SYNCHRONIZED

    def _feed_business_learning(self, outcome: CommerceOutcome) -> Any | None:
        business_outcome = outcome.to_business_outcome()
        for method_name in ("record_business_outcome", "record_outcome"):
            method = getattr(self.business_learning, method_name, None)
            if callable(method):
                try:
                    return method(business_outcome)
                except Exception:
                    return None
        builder = getattr(self.business_learning, "build_learning_snapshot", None)
        if callable(builder):
            try:
                snapshot = builder(
                    outcomes=(business_outcome,),
                    metadata={"source": "commerce_outcome_synchronization"},
                )
                return {
                    "success": True,
                    "snapshot_outcome_count": len(getattr(snapshot, "outcomes", ()) or ()),
                }
            except Exception:
                return None
        return None

    def _record_recommendation_outcome(self, outcome: CommerceOutcome) -> Any | None:
        recorder = getattr(self.content_commerce_learning, "record_commerce_outcome", None)
        if not callable(recorder):
            return None
        try:
            return recorder(outcome)
        except Exception:
            return None

    def _update_customer_history(self, outcome: CommerceOutcome) -> Any | None:
        recorder = getattr(self.customer_intelligence, "record_purchase", None)
        if not callable(recorder):
            return None
        history = {}
        customer_id = outcome.attribution.customer_id
        getter = getattr(self.customer_history_repository, "get", None)
        if callable(getter) and customer_id:
            try:
                history = getter(customer_id) or {}
            except Exception:
                history = {}
        try:
            updated = recorder(
                history,
                product_id=outcome.attribution.product_id,
                purchase_id=outcome.purchase.provider_transaction_id,
                purchased_at=outcome.purchase.purchased_at,
                metadata=outcome.to_context(),
            )
        except Exception:
            return None
        saver = getattr(self.customer_history_repository, "save", None)
        if callable(saver) and customer_id:
            try:
                saver(customer_id, updated)
            except Exception:
                pass
        return updated.to_context() if hasattr(updated, "to_context") else updated

    def _business_asset_id(self, asset_id: int) -> int | None:
        getter = getattr(self.commerce_registrations, "get_by_asset_id", None)
        if not callable(getter):
            return asset_id
        try:
            record = getter(asset_id)
        except Exception:
            return asset_id
        return self._int(getattr(record, "asset_id", None)) or asset_id

    def _existing(
        self,
        provider: str,
        provider_transaction_id: str,
    ) -> Mapping[str, Any] | None:
        getter = getattr(self.repository, "get_by_provider_transaction", None)
        if not callable(getter):
            return None
        try:
            return getter(
                provider=provider,
                provider_transaction_id=provider_transaction_id,
            )
        except Exception:
            return None

    def _record_outcome(self, outcome: CommerceOutcome) -> None:
        recorder = getattr(self.repository, "record_outcome", None)
        if callable(recorder):
            recorder(outcome.to_context())

    def _record_failure(
        self,
        *,
        provider: str,
        provider_transaction_id: str | None,
        reason: str,
        payload: Mapping[str, Any],
    ) -> None:
        recorder = getattr(self.repository, "record_failure", None)
        if callable(recorder):
            recorder(
                provider=provider,
                provider_transaction_id=provider_transaction_id,
                reason=reason,
                payload=payload,
            )

    def _record_duplicate(
        self,
        *,
        provider: str,
        provider_transaction_id: str,
        existing: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> None:
        recorder = getattr(self.repository, "record_duplicate", None)
        if callable(recorder):
            recorder(
                provider=provider,
                provider_transaction_id=provider_transaction_id,
                existing_outcome=existing,
                payload=payload,
            )

    def _fanvue_api(self, fanvue_account_id: int) -> Any | None:
        if self.fanvue_api_factory is not None:
            return self.fanvue_api_factory(fanvue_account_id)
        try:
            from app.services.fanvue_api_service import FanvueAPIService

            return FanvueAPIService(fanvue_account_id=fanvue_account_id)
        except Exception:
            return None

    def _list_provider_outcomes(
        self,
        api: Any,
        *,
        since: str | None,
        limit: int,
    ) -> tuple[Mapping[str, Any], ...]:
        for method_name in (
            "list_commerce_outcomes",
            "list_purchases",
            "list_transactions",
            "list_monetization_events",
        ):
            method = getattr(api, method_name, None)
            if not callable(method):
                continue
            try:
                result = method(since=since, limit=limit)
            except TypeError:
                result = method()
            except Exception:
                continue
            return self._records_from_provider_result(result)
        return ()

    def _records_from_provider_result(self, result: Any) -> tuple[Mapping[str, Any], ...]:
        if isinstance(result, Mapping):
            if result.get("success") is False:
                return ()
            for key in ("data", "purchases", "transactions", "events", "items"):
                value = result.get(key)
                if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
                    return tuple(item for item in value if isinstance(item, Mapping))
            return (result,)
        if isinstance(result, Iterable) and not isinstance(result, (str, bytes)):
            return tuple(item for item in result if isinstance(item, Mapping))
        return ()

    @staticmethod
    def _flatten_mapping(value: Any) -> dict[str, Any]:
        flat: dict[str, Any] = {}

        def visit(item: Any) -> None:
            if isinstance(item, Mapping):
                for key, nested in item.items():
                    if key not in flat and not isinstance(nested, (Mapping, list, tuple)):
                        flat[str(key)] = nested
                    visit(nested)
            elif isinstance(item, (list, tuple)):
                for nested in item:
                    visit(nested)

        visit(value)
        return flat

    @staticmethod
    def _first_value(mapping: Mapping[str, Any], *keys: str) -> Any:
        for key in keys:
            value = mapping.get(key)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _purchase_status(value: Any) -> PurchaseStatus:
        normalized = str(value or "").strip().upper()
        if normalized in {"PURCHASE_RECEIVED", "PURCHASE_CREATED", "UNLOCK_CONFIRMATION"}:
            return PurchaseStatus.PURCHASED
        if normalized in {"PAID", "SUCCEEDED", "SUCCESS", "COMPLETE", "COMPLETED"}:
            return PurchaseStatus.PAID
        if normalized in {"REFUNDED", "REFUND"}:
            return PurchaseStatus.REFUNDED
        if normalized in {"PARTIALLY_REFUNDED", "PARTIAL_REFUND"}:
            return PurchaseStatus.PARTIALLY_REFUNDED
        if normalized in {"FAILED", "ERROR"}:
            return PurchaseStatus.FAILED
        if normalized in {"CANCELLED", "CANCELED"}:
            return PurchaseStatus.CANCELLED
        if normalized in {"PENDING", "PROCESSING"}:
            return PurchaseStatus.PENDING
        return PurchaseStatus.UNKNOWN

    @classmethod
    def _cents(
        cls,
        value: Any,
        *,
        fallback_amount: Any = None,
        default: int = 0,
    ) -> int:
        if value not in (None, ""):
            return cls._int(value)
        if fallback_amount not in (None, ""):
            try:
                return int(round(float(fallback_amount) * 100))
            except (TypeError, ValueError):
                return default
        return default

    @staticmethod
    def _tuple_value(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, Iterable):
            return tuple(str(item) for item in value if str(item).strip())
        return (str(value),)

    @staticmethod
    def _int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text else None
