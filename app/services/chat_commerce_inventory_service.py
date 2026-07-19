"""Chat Commerce Inventory read-model aggregation service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from app.models.business_learning import BusinessOutcomeType
from app.models.chat_commerce_inventory import (
    ChatCommerceInventoryFilter,
    ChatCommerceInventoryItem,
    ChatCommerceInventoryMetrics,
    ChatCommerceInventoryResult,
    ChatCommerceInventorySummary,
)
from app.models.chat_commerce_registration import ChatAvailabilityState
from app.models.commerce_registration import CommerceDestinationStatus
from app.models.fulfillment_registration import FulfillmentLifecycleState


class ChatCommerceInventoryService:
    """Project Asset Library operational inventory from existing services."""

    def __init__(
        self,
        *,
        asset_library_service: Any | None = None,
        commerce_registration_repository: Any | None = None,
        chat_commerce_registration_service: Any | None = None,
        fulfillment_registration_service: Any | None = None,
        business_learning_service: Any | None = None,
    ) -> None:
        if asset_library_service is None:
            from app.services.asset_library_service import AssetLibraryService

            asset_library_service = AssetLibraryService()
        if commerce_registration_repository is None:
            from app.repositories.commerce_registration_repository import (
                CommerceRegistrationRepository,
            )

            commerce_registration_repository = CommerceRegistrationRepository()
        if chat_commerce_registration_service is None:
            from app.services.chat_commerce_registration_service import (
                ChatCommerceRegistrationService,
            )

            chat_commerce_registration_service = ChatCommerceRegistrationService()
        if fulfillment_registration_service is None:
            from app.services.fulfillment_registration_service import (
                FulfillmentRegistrationService,
            )

            fulfillment_registration_service = FulfillmentRegistrationService()
        if business_learning_service is None:
            from app.services.business_learning_service import BusinessLearningService

            business_learning_service = BusinessLearningService()

        self.asset_library = asset_library_service
        self.commerce_registrations = commerce_registration_repository
        self.chat_commerce = chat_commerce_registration_service
        self.fulfillment = fulfillment_registration_service
        self.business_learning = business_learning_service

    def build_inventory(
        self,
        *,
        filters: ChatCommerceInventoryFilter | None = None,
        business_outcomes: Any | None = None,
        limit: int = 500,
    ) -> ChatCommerceInventoryResult:
        filters = filters or ChatCommerceInventoryFilter()
        business_assets = self._business_assets(limit=limit)
        asset_ids = tuple(int(record.asset_id) for record in business_assets)
        asset_items = {
            item.asset_id: item
            for item in self.asset_library.get_asset_items(asset_ids)
        }
        metrics_by_asset = self._metrics_by_asset(business_outcomes)
        items = tuple(
            self._build_item(
                business_asset,
                asset_item=asset_items.get(int(business_asset.asset_id)),
                chat_record=self._chat_record(int(business_asset.asset_id)),
                fulfillment_record=self._fulfillment_record(int(business_asset.asset_id)),
                metrics=metrics_by_asset.get(
                    str(business_asset.asset_id),
                    ChatCommerceInventoryMetrics(),
                ),
            )
            for business_asset in business_assets
        )
        filtered = tuple(item for item in items if self._matches(item, filters))
        return ChatCommerceInventoryResult(
            items=filtered,
            summary=self._summary(filtered),
            filters=filters,
            generated_at=datetime.now(timezone.utc),
            metadata={
                "source": "ChatCommerceInventoryService",
                "owner": "Asset Library",
                "business_logic_owner": "Existing Business Asset services",
                "presentation_projection": True,
            },
        )

    def attention_chat_records(self, *, limit: int = 100) -> tuple[Any, ...]:
        try:
            blocked = self.chat_commerce.list_blocked_assets(limit=limit)
            unavailable = self.chat_commerce.list_temporarily_unavailable_assets(
                limit=limit
            )
            retired = self.chat_commerce.list_retired_assets(limit=limit)
        except Exception:
            return ()
        seen: set[int] = set()
        records: list[Any] = []
        for record in (*blocked, *unavailable, *retired):
            asset_id = int(getattr(record, "asset_id", 0))
            if asset_id in seen:
                continue
            seen.add(asset_id)
            records.append(record)
        return tuple(records[:limit])

    def summarize_items(
        self,
        items: Iterable[ChatCommerceInventoryItem],
    ) -> ChatCommerceInventorySummary:
        """Summarize an already-scoped inventory without changing lifecycle rules."""
        return self._summary(tuple(items))

    def _business_assets(self, *, limit: int) -> tuple[Any, ...]:
        records: list[Any] = []
        for getter_name in (
            "list_registered",
            "list_awaiting_destination",
            "list_blocked_by_incomplete_intelligence",
        ):
            getter = getattr(self.commerce_registrations, getter_name, None)
            if not callable(getter):
                continue
            try:
                records.extend(getter(limit=limit))
            except Exception:
                continue
        by_asset: dict[int, Any] = {}
        for record in records:
            by_asset[int(record.asset_id)] = record
        return tuple(by_asset.values())[:limit]

    def _chat_record(self, asset_id: int) -> Any | None:
        getter = getattr(self.chat_commerce, "get_by_asset_id", None)
        if not callable(getter):
            return None
        try:
            return getter(asset_id)
        except Exception:
            return None

    def _fulfillment_record(self, asset_id: int) -> Any | None:
        getter = getattr(self.fulfillment, "get_by_asset_id", None)
        if callable(getter):
            try:
                return getter(asset_id)
            except Exception:
                pass
        repository = getattr(self.fulfillment, "repository", None)
        getter = getattr(repository, "get_by_asset_and_route", None)
        if not callable(getter):
            return None
        try:
            from app.models.fulfillment_registration import FulfillmentRoute

            return getter(asset_id, FulfillmentRoute.CUSTOMER_CONVERSATIONS)
        except Exception:
            return None

    def _build_item(
        self,
        business_asset: Any,
        *,
        asset_item: Any | None,
        chat_record: Any | None,
        fulfillment_record: Any | None,
        metrics: ChatCommerceInventoryMetrics,
    ) -> ChatCommerceInventoryItem:
        lifecycle = self._value(getattr(business_asset, "business_lifecycle_state", None))
        destination_status = getattr(business_asset, "commerce_destination_status", None)
        awaiting_destination = destination_status == CommerceDestinationStatus.AWAITING_DESTINATION
        fulfillment_state = getattr(fulfillment_record, "lifecycle_state", None)
        media_status = self._value(
            getattr(fulfillment_record, "media_link_verification_state", None)
        )
        waiting_media = fulfillment_state == FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK
        fulfillment_ready = (
            fulfillment_state == FulfillmentLifecycleState.FULFILLMENT_READY
            or bool(getattr(chat_record, "fulfillment_ready", False))
        )
        chat_ready = bool(getattr(chat_record, "chat_ready", False))
        recommendation_ready = bool(getattr(chat_record, "recommendation_eligible", False))
        availability = self._availability(chat_record, business_asset, fulfillment_record)
        product_ids = self._ids(
            getattr(chat_record, "product_ids", ())
            or getattr(business_asset, "product_ids", ())
            or getattr(getattr(asset_item, "relationship", None), "product_ids", ())
        )
        experience_ids = self._ids(
            getattr(chat_record, "experience_ids", ())
            or getattr(business_asset, "experience_ids", ())
            or getattr(getattr(asset_item, "relationship", None), "experience_ids", ())
        )
        block_reasons = self._ids(getattr(chat_record, "block_reasons", ()))
        quick_actions = self._quick_actions(
            chat_record=chat_record,
            fulfillment_record=fulfillment_record,
            awaiting_destination=awaiting_destination,
            waiting_media=waiting_media,
        )
        return ChatCommerceInventoryItem(
            asset_id=int(business_asset.asset_id),
            asset_name=getattr(asset_item, "file_name", None),
            thumbnail_path=getattr(asset_item, "preview_path", None),
            source_workflow=(
                getattr(business_asset, "destination_source_workflow", None)
                or getattr(chat_record, "source_workflow", None)
                or self._mapping(getattr(fulfillment_record, "provenance", None)).get(
                    "source_workflow"
                )
            ),
            commerce_destination=getattr(
                business_asset,
                "selected_commerce_destination",
                None,
            )
            or getattr(chat_record, "commerce_destination", None),
            current_lifecycle=lifecycle,
            chat_ready=chat_ready,
            fulfillment_ready=fulfillment_ready,
            recommendation_ready=recommendation_ready,
            fanvue_upload_status=self._fanvue_upload_status(
                fulfillment_record,
                getattr(asset_item, "publishing", None),
            ),
            fanvue_media_uuid=(
                getattr(fulfillment_record, "provider_media_id", None)
                or getattr(fulfillment_record, "provider_full_media_id", None)
                or getattr(fulfillment_record, "provider_preview_media_id", None)
                or getattr(chat_record, "provider_media_id", None)
                or getattr(getattr(asset_item, "publishing", None), "provider_media_id", None)
            ),
            media_link_status=media_status,
            media_link=(
                getattr(fulfillment_record, "media_link", None)
                or getattr(chat_record, "media_link", None)
            ),
            product_ids=product_ids,
            experience_ids=experience_ids,
            availability=availability,
            waiting_for_media_link=waiting_media,
            awaiting_destination=awaiting_destination,
            blocked=availability == "Blocked",
            temporarily_unavailable=bool(
                getattr(chat_record, "temporarily_unavailable", False)
            ),
            retired=bool(getattr(chat_record, "retired", False))
            or lifecycle == "RETIRED",
            block_reasons=block_reasons,
            warnings=self._ids(getattr(chat_record, "warnings", ())),
            metrics=metrics,
            lifecycle_steps=self._lifecycle_steps(
                business_asset,
                chat_record,
                fulfillment_record,
            ),
            quick_actions=quick_actions,
            metadata={
                "source": "ChatCommerceInventoryService",
                "chat_registration_id": self._text(
                    getattr(chat_record, "chat_registration_id", None)
                ),
                "fulfillment_id": self._text(
                    getattr(fulfillment_record, "fulfillment_id", None)
                    or getattr(chat_record, "fulfillment_id", None)
                ),
            },
        )

    def _metrics_by_asset(self, outcomes: Any | None) -> dict[str, ChatCommerceInventoryMetrics]:
        normalized = self._normalize_outcomes(outcomes)
        by_asset: dict[str, list[Any]] = {}
        for outcome in normalized:
            asset_id = self._outcome_asset_id(outcome)
            if not asset_id:
                continue
            by_asset.setdefault(asset_id, []).append(outcome)
        return {
            asset_id: self._metrics_for_outcomes(items)
            for asset_id, items in by_asset.items()
        }

    def _normalize_outcomes(self, outcomes: Any | None) -> tuple[Any, ...]:
        normalizer = getattr(self.business_learning, "normalize_business_outcomes", None)
        if callable(normalizer):
            try:
                return tuple(normalizer(outcomes))
            except Exception:
                return ()
        if outcomes is None:
            return ()
        return tuple(outcomes if isinstance(outcomes, Iterable) else (outcomes,))

    def _metrics_for_outcomes(self, outcomes: list[Any]) -> ChatCommerceInventoryMetrics:
        type_counts: dict[str, int] = {}
        revenue = 0
        last: dict[str, str] = {}
        for outcome in outcomes:
            outcome_type = str(getattr(outcome, "outcome_type", "") or "")
            type_counts[outcome_type] = type_counts.get(outcome_type, 0) + 1
            revenue += int(getattr(outcome, "value_cents", 0) or 0)
            occurred = (
                getattr(outcome, "occurred_at", None)
                or getattr(outcome, "timestamp", None)
            )
            if occurred:
                last[outcome_type] = str(occurred)
        offers = type_counts.get(BusinessOutcomeType.PRODUCT_OFFERED.value, 0)
        purchases = type_counts.get(BusinessOutcomeType.PRODUCT_PURCHASED.value, 0)
        deliveries = (
            type_counts.get(BusinessOutcomeType.PRODUCT_DELIVERED.value, 0)
            + type_counts.get(BusinessOutcomeType.FREE_ASSET_DELIVERED.value, 0)
        )
        recommendations = sum(
            count
            for name, count in type_counts.items()
            if "RECOMMEND" in name.upper()
        )
        conversion = purchases / offers if offers else 0.0
        trend = "Strong" if conversion >= 0.25 and purchases else "Needs Review" if offers else "Unknown"
        return ChatCommerceInventoryMetrics(
            recommendation_count=recommendations,
            offer_count=offers,
            delivery_count=deliveries,
            purchase_count=purchases,
            revenue_cents=revenue,
            conversion_rate=conversion,
            last_recommended=self._last_like(last, "RECOMMEND"),
            last_offered=last.get(BusinessOutcomeType.PRODUCT_OFFERED.value),
            last_delivered=(
                last.get(BusinessOutcomeType.PRODUCT_DELIVERED.value)
                or last.get(BusinessOutcomeType.FREE_ASSET_DELIVERED.value)
            ),
            last_purchased=last.get(BusinessOutcomeType.PRODUCT_PURCHASED.value),
            performance_trend=trend,
        )

    def _summary(
        self,
        items: tuple[ChatCommerceInventoryItem, ...],
    ) -> ChatCommerceInventorySummary:
        offers = sum(item.metrics.offer_count for item in items)
        purchases = sum(item.metrics.purchase_count for item in items)
        ranked = sorted(items, key=lambda item: item.metrics.revenue_cents, reverse=True)
        attention = tuple(
            item.asset_id
            for item in items
            if item.waiting_for_media_link or item.awaiting_destination or item.blocked
        )
        return ChatCommerceInventorySummary(
            total_business_assets=len(items),
            chat_ready=sum(1 for item in items if item.chat_ready),
            fulfillment_ready=sum(1 for item in items if item.fulfillment_ready),
            waiting_for_media_link=sum(1 for item in items if item.waiting_for_media_link),
            awaiting_destination=sum(1 for item in items if item.awaiting_destination),
            blocked=sum(1 for item in items if item.blocked),
            temporarily_unavailable=sum(1 for item in items if item.temporarily_unavailable),
            retired=sum(1 for item in items if item.retired),
            recommendation_ready=sum(1 for item in items if item.recommendation_ready),
            recommendation_pending=sum(1 for item in items if not item.recommendation_ready),
            total_revenue_cents=sum(item.metrics.revenue_cents for item in items),
            total_purchases=purchases,
            overall_conversion=purchases / offers if offers else 0.0,
            top_performing_asset_ids=tuple(item.asset_id for item in ranked[:5] if item.metrics.revenue_cents > 0),
            underperforming_asset_ids=tuple(item.asset_id for item in items if item.metrics.offer_count and not item.metrics.purchase_count),
            disabled_asset_ids=tuple(item.asset_id for item in items if item.temporarily_unavailable),
            retired_asset_ids=tuple(item.asset_id for item in items if item.retired),
            attention_asset_ids=attention,
        )

    def _matches(
        self,
        item: ChatCommerceInventoryItem,
        filters: ChatCommerceInventoryFilter,
    ) -> bool:
        checks = (
            (filters.chat_ready, item.chat_ready),
            (filters.fulfillment_ready, item.fulfillment_ready),
            (filters.waiting_for_media_link, item.waiting_for_media_link),
            (filters.awaiting_destination, item.awaiting_destination),
            (filters.blocked, item.blocked),
            (filters.temporarily_unavailable, item.temporarily_unavailable),
            (filters.retired, item.retired),
            (filters.recommendation_ready, item.recommendation_ready),
        )
        if any(expected is not None and expected != actual for expected, actual in checks):
            return False
        if filters.status and item.availability != filters.status:
            return False
        if filters.destination and item.commerce_destination != filters.destination:
            return False
        if filters.product_id and filters.product_id not in item.product_ids:
            return False
        if filters.experience_id and filters.experience_id not in item.experience_ids:
            return False
        if filters.source_workflow and item.source_workflow != filters.source_workflow:
            return False
        return True

    def _availability(self, chat_record: Any | None, business_asset: Any, fulfillment: Any | None) -> str:
        if chat_record is not None:
            state = getattr(chat_record, "availability_state", None)
            if state == ChatAvailabilityState.CHAT_READY:
                return "Chat Ready"
            if state == ChatAvailabilityState.TEMPORARILY_UNAVAILABLE:
                return "Temporarily Unavailable"
            if state == ChatAvailabilityState.RETIRED:
                return "Retired"
            if state in {ChatAvailabilityState.BLOCKED, ChatAvailabilityState.FAILED}:
                return "Blocked"
        if getattr(business_asset, "commerce_destination_status", None) == CommerceDestinationStatus.AWAITING_DESTINATION:
            return "Awaiting Destination"
        if getattr(fulfillment, "lifecycle_state", None) == FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK:
            return "Waiting For Media Link"
        return "Pending"

    def _quick_actions(
        self,
        *,
        chat_record: Any | None,
        fulfillment_record: Any | None,
        awaiting_destination: bool,
        waiting_media: bool,
    ) -> tuple[str, ...]:
        actions: list[str] = []
        if waiting_media:
            actions.extend(("Open Fanvue", "Paste Media Link", "Verify Media Link"))
        if getattr(fulfillment_record, "retry_required", False):
            actions.extend(("Retry Verification", "Retry Upload"))
        if awaiting_destination:
            actions.append("Change Destination")
        if chat_record is not None:
            if getattr(chat_record, "temporarily_unavailable", False):
                actions.append("Re-enable")
            elif not getattr(chat_record, "retired", False):
                actions.append("Temporarily Disable")
            if getattr(chat_record, "retired", False):
                actions.append("Re-enable")
            else:
                actions.append("Retire")
        return tuple(dict.fromkeys(actions))

    def _lifecycle_steps(self, business_asset: Any, chat_record: Any | None, fulfillment: Any | None) -> tuple[tuple[str, str], ...]:
        return (
            ("Approved", str(getattr(business_asset, "approval_status", "unknown"))),
            ("Canonical Asset", f"Asset #{business_asset.asset_id}"),
            ("Content Intelligence", str(getattr(business_asset, "content_intelligence_status", "UNKNOWN"))),
            ("Business Asset", self._value(getattr(business_asset, "commerce_registration_status", None))),
            ("Destination", str(getattr(business_asset, "selected_commerce_destination", None) or "Awaiting Destination")),
            ("Fulfillment", self._value(getattr(fulfillment, "lifecycle_state", None))),
            ("Chat Ready", "Yes" if getattr(chat_record, "chat_ready", False) else "No"),
            ("Recommendation Ready", "Yes" if getattr(chat_record, "recommendation_eligible", False) else "No"),
        )

    @staticmethod
    def _fanvue_upload_status(fulfillment: Any | None, publishing: Any | None) -> str | None:
        return (
            getattr(fulfillment, "provider_processing_status", None)
            or ChatCommerceInventoryService._value(getattr(fulfillment, "lifecycle_state", None))
            or getattr(publishing, "status", None)
        )

    @staticmethod
    def _outcome_asset_id(outcome: Any) -> str | None:
        for source in (
            getattr(outcome, "provider_metadata", None),
            getattr(outcome, "evidence_metadata", None),
            getattr(outcome, "metadata", None),
            getattr(outcome, "signals", None),
        ):
            if isinstance(source, Mapping):
                value = source.get("asset_id") or source.get("canonical_asset_id")
                if value is not None:
                    return str(value)
        subject_type = str(getattr(outcome, "subject_type", "") or "").lower()
        if subject_type == "asset" and getattr(outcome, "subject_id", None):
            return str(getattr(outcome, "subject_id"))
        return None

    @staticmethod
    def _last_like(values: Mapping[str, str], fragment: str) -> str | None:
        for name, value in values.items():
            if fragment in name.upper():
                return value
        return None

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _ids(values: Any) -> tuple[str, ...]:
        if not values:
            return ()
        if isinstance(values, str):
            return (values,)
        return tuple(str(value) for value in values if str(value).strip())

    @staticmethod
    def _text(value: Any) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _value(value: Any) -> str | None:
        if value is None:
            return None
        return str(getattr(value, "value", value))
