"""Content commerce learning bridge.

This service connects recommendation, delivery, and commerce outcome records to
durable Business Learning evidence. It does not rank assets or ingest provider
commerce directly.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.models.business_learning import BusinessOutcome
from app.models.content_commerce_learning import (
    AssetLearningProfile,
    RecommendationEvent,
    RecommendationEventState,
    RuntimeLearningContext,
)


class ContentCommerceLearningService:
    """Durable feedback bridge for autonomous content commerce."""

    def __init__(
        self,
        *,
        repository: Any | None = None,
        business_learning_service: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        if repository is None:
            from app.repositories.content_commerce_learning_repository import (
                ContentCommerceLearningRepository,
            )

            repository = ContentCommerceLearningRepository()
        self.repository = repository
        self.business_learning_service = business_learning_service
        self.logger = logger

    def recommendation_id_for(
        self,
        *,
        asset_id: int | str | None,
        request_context: Mapping[str, Any] | None = None,
        explicit: str | None = None,
    ) -> str:
        if explicit:
            return str(explicit)
        request_context = dict(request_context or {})
        metadata = request_context.get("metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        key = metadata.get("idempotency_key") or "|".join(
            (
                str(asset_id or ""),
                str(request_context.get("creator_profile_id") or ""),
                str((request_context.get("customer_context") or {}).get("customer_id") or ""),
                str((request_context.get("conversation_context") or {}).get("conversation_id") or ""),
                str(request_context.get("offer_type") or ""),
            )
        )
        return str(uuid5(NAMESPACE_URL, f"creator-os:content-commerce-rec:{key}"))

    def record_recommendation_result(self, result: Any) -> dict[str, Any]:
        context = self._context(result)
        request = context.get("request") if isinstance(context.get("request"), Mapping) else {}
        ranked = tuple(context.get("ranked_assets") or ())
        rejected = tuple(context.get("rejected_candidates") or ())
        selected_asset_id = self._first_value(ranked[0], "asset_id") if ranked else None
        recorded = 0
        failures = []

        for index, candidate in enumerate(ranked):
            try:
                recommendation_id = self._recommendation_id(candidate, request)
                base = self._event_from_candidate(
                    candidate,
                    request=request,
                    recommendation_id=recommendation_id,
                    state=RecommendationEventState.GENERATED,
                )
                self._record_event(base)
                recorded += 1
                if str(candidate.get("asset_id")) == str(selected_asset_id):
                    self._record_event(
                        self._event_from_candidate(
                            candidate,
                            request=request,
                            recommendation_id=recommendation_id,
                            state=RecommendationEventState.SELECTED,
                        )
                    )
                    recorded += 1
            except Exception as error:
                failures.append(str(error))

        for candidate in rejected:
            try:
                recommendation_id = self._recommendation_id(candidate, request)
                state = (
                    RecommendationEventState.SUPPRESSED
                    if candidate.get("suppressed")
                    or candidate.get("suppression_reasons")
                    else RecommendationEventState.REJECTED
                )
                self._record_event(
                    self._event_from_candidate(
                        candidate,
                        request=request,
                        recommendation_id=recommendation_id,
                        state=state,
                    )
                )
                recorded += 1
            except Exception as error:
                failures.append(str(error))

        if failures:
            self._record_failure(
                "recommendation_recording_failed",
                {"errors": failures, "request": request},
            )
        return {
            "success": not failures,
            "recorded_event_count": recorded,
            "errors": tuple(failures),
        }

    def record_delivery_result(self, result: Any) -> dict[str, Any]:
        context = self._context(result)
        payload = context.get("payload")
        payload = payload if isinstance(payload, Mapping) else {}
        request = context.get("request")
        request = request if isinstance(request, Mapping) else {}
        validation = context.get("validation")
        validation = validation if isinstance(validation, Mapping) else {}
        recommendation_id = (
            payload.get("recommendation_id")
            or request.get("recommendation_id")
            or self._read_nested(request, "metadata", "recommendation_id")
        )
        asset_id = payload.get("asset_id") or request.get("asset_id")
        state = (
            RecommendationEventState.DELIVERY_PREPARED
            if context.get("success")
            else RecommendationEventState.DELIVERY_BLOCKED
        )
        event = RecommendationEvent(
            event_id=RecommendationEvent.deterministic_id(
                recommendation_id=str(recommendation_id) if recommendation_id else None,
                event_state=state.value,
                asset_id=asset_id,
                delivery_id=context.get("delivery_id") or payload.get("delivery_id"),
            ),
            recommendation_id=str(recommendation_id) if recommendation_id else None,
            event_state=state.value,
            event_timestamp=context.get("created_at") or self._now(),
            asset_id=self._int(asset_id),
            chat_registration_id=self._text(payload.get("chat_registration_id")),
            fulfillment_registration_id=self._text(payload.get("fulfillment_id")),
            delivery_id=self._text(context.get("delivery_id") or payload.get("delivery_id")),
            product_id=self._text(payload.get("product_id")),
            experience_id=self._text(payload.get("experience_id")),
            customer_id=self._text(payload.get("customer_id") or request.get("customer_id")),
            conversation_id=self._text(
                payload.get("conversation_id") or request.get("conversation_id")
            ),
            provider=self._text(payload.get("provider") or request.get("provider")),
            outcome_metadata={
                "failure_reason": context.get("failure_reason"),
                "validation": validation,
                "retryable": context.get("retryable"),
                "retry_of_delivery_id": request.get("retry_of_delivery_id"),
            },
        )
        self._record_event(event)
        if request.get("retry_of_delivery_id"):
            retry_event = RecommendationEvent(
                event_id=RecommendationEvent.deterministic_id(
                    recommendation_id=event.recommendation_id,
                    event_state=RecommendationEventState.RETRIED.value,
                    asset_id=asset_id,
                    delivery_id=event.delivery_id,
                ),
                recommendation_id=event.recommendation_id,
                event_state=RecommendationEventState.RETRIED.value,
                event_timestamp=event.event_timestamp,
                asset_id=event.asset_id,
                delivery_id=event.delivery_id,
                customer_id=event.customer_id,
                conversation_id=event.conversation_id,
                outcome_metadata={
                    "retry_of_delivery_id": request.get("retry_of_delivery_id")
                },
            )
            self._record_event(retry_event)
        return {"success": True, "event_id": event.event_id}

    def record_delivery_execution(
        self,
        *,
        delivery_id: str,
        payload: Mapping[str, Any] | None = None,
        success: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        payload = dict(payload or {})
        state = (
            RecommendationEventState.DELIVERED
            if success
            else RecommendationEventState.DELIVERY_FAILED
        )
        event = RecommendationEvent(
            event_id=RecommendationEvent.deterministic_id(
                recommendation_id=self._text(payload.get("recommendation_id")),
                event_state=state.value,
                asset_id=payload.get("asset_id"),
                delivery_id=delivery_id,
            ),
            recommendation_id=self._text(payload.get("recommendation_id")),
            event_state=state.value,
            event_timestamp=self._now(),
            asset_id=self._int(payload.get("asset_id")),
            delivery_id=str(delivery_id),
            product_id=self._text(payload.get("product_id")),
            experience_id=self._text(payload.get("experience_id")),
            customer_id=self._text(payload.get("customer_id")),
            conversation_id=self._text(payload.get("conversation_id")),
            provider=self._text(payload.get("provider")),
            outcome_metadata={"reason": reason, "payload": payload},
        )
        self._record_event(event)
        return {"success": True, "event_id": event.event_id}

    def record_commerce_outcome(self, outcome: Any) -> dict[str, Any]:
        context = self._context(outcome)
        attribution = context.get("attribution")
        attribution = attribution if isinstance(attribution, Mapping) else {}
        purchase = context.get("purchase")
        purchase = purchase if isinstance(purchase, Mapping) else {}
        status = str(context.get("status") or "").upper()
        if status == "REFUNDED" or self._int(purchase.get("refund_cents")) > 0:
            state = RecommendationEventState.REFUNDED
        elif status == "UNMATCHED":
            state = RecommendationEventState.UNMATCHED
        else:
            state = RecommendationEventState.PURCHASED
        event = RecommendationEvent(
            event_id=RecommendationEvent.deterministic_id(
                recommendation_id=self._text(attribution.get("recommendation_id")),
                event_state=state.value,
                asset_id=attribution.get("asset_id"),
                delivery_id=self._text(attribution.get("delivery_id")),
                provider_transaction_id=self._text(
                    purchase.get("provider_transaction_id")
                ),
            ),
            recommendation_id=self._text(attribution.get("recommendation_id")),
            event_state=state.value,
            event_timestamp=context.get("synchronized_at") or self._now(),
            asset_id=self._int(attribution.get("asset_id")),
            business_registration_id=self._text(
                attribution.get("business_asset_id")
            ),
            delivery_id=self._text(attribution.get("delivery_id")),
            product_id=self._text(attribution.get("product_id")),
            experience_id=self._text(attribution.get("experience_id")),
            customer_id=self._text(attribution.get("customer_id")),
            conversation_id=self._text(attribution.get("conversation_id")),
            provider=self._text(context.get("provider")),
            outcome_metadata={
                "commerce_outcome_id": context.get("outcome_id"),
                "provider_transaction_id": purchase.get("provider_transaction_id"),
                "gross_revenue_cents": purchase.get("gross_revenue_cents"),
                "tip_cents": purchase.get("tip_cents"),
                "refund_cents": purchase.get("refund_cents"),
                "net_revenue_cents": purchase.get("net_revenue_cents"),
                "unresolved_fields": attribution.get("unresolved_fields"),
                "matched_by": attribution.get("matched_by"),
            },
        )
        self._record_event(event)
        return {"success": True, "event_id": event.event_id}

    def record_business_outcome(self, outcome: BusinessOutcome | Mapping[str, Any]) -> dict[str, Any]:
        payload = self._business_outcome_payload(outcome)
        recorder = getattr(self.repository, "record_business_outcome", None)
        if not callable(recorder):
            return {"success": False, "reason": "repository_unavailable"}
        return recorder(payload)

    def build_runtime_learning_context(
        self,
        *,
        request: Any | None = None,
        creator_profile_id: int | None = None,
        customer_context: Mapping[str, Any] | None = None,
        conversation_context: Mapping[str, Any] | None = None,
    ) -> RuntimeLearningContext:
        request_context = self._context(request)
        creator_profile_id = creator_profile_id or self._int(
            request_context.get("creator_profile_id")
        )
        customer_context = dict(
            customer_context
            or request_context.get("customer_context")
            or {}
        )
        conversation_context = dict(
            conversation_context
            or request_context.get("conversation_context")
            or {}
        )
        profiles = {
            str(profile.asset_id): profile
            for profile in self.list_asset_learning_profiles()
        }
        asset_scores = {
            asset_id: profile.score for asset_id, profile in profiles.items()
        }
        top = tuple(
            asset_id
            for asset_id, profile in sorted(
                profiles.items(),
                key=lambda item: item[1].score,
                reverse=True,
            )
            if profile.score > 0
        )[:10]
        under = tuple(
            asset_id
            for asset_id, profile in sorted(
                profiles.items(),
                key=lambda item: item[1].score,
            )
            if profile.score < 0
        )[:10]
        context_id = str(
            uuid5(
                NAMESPACE_URL,
                "creator-os:runtime-learning:"
                + "|".join(
                    (
                        str(creator_profile_id or ""),
                        str(customer_context.get("customer_id") or ""),
                        str(conversation_context.get("conversation_id") or ""),
                        str(len(profiles)),
                    )
                ),
            )
        )
        return RuntimeLearningContext(
            context_id=context_id,
            asset_scores=asset_scores,
            asset_profiles={
                key: profile.to_context() for key, profile in profiles.items()
            },
            customer_evidence=self._customer_evidence(customer_context),
            cohort_evidence=self._cohort_evidence(customer_context),
            business_priorities=tuple(
                str(value)
                for value in self._as_iterable(
                    request_context.get("business_priorities")
                    or customer_context.get("business_priorities")
                )
            ),
            top_performers=top,
            underperformers=under,
            suppression_evidence={
                key: {
                    "suppression_rate": (
                        profile.suppressed_count / profile.recommendation_count
                        if profile.recommendation_count
                        else None
                    ),
                    "failure_rate": (
                        profile.delivery_failure_count / profile.delivery_count
                        if profile.delivery_count
                        else None
                    ),
                }
                for key, profile in profiles.items()
            },
            metadata={
                "source": "ContentCommerceLearningService",
                "creator_profile_id": creator_profile_id,
                "profile_count": len(profiles),
                "learning_context_available": True,
            },
        )

    def get_asset_learning_profile(self, asset_id: int | str) -> AssetLearningProfile:
        profiles = {
            str(profile.asset_id): profile
            for profile in self.list_asset_learning_profiles()
        }
        return profiles.get(str(asset_id)) or AssetLearningProfile(
            asset_id=int(asset_id),
            metadata={"source": "ContentCommerceLearningService", "sample_size": 0},
        )

    def list_asset_learning_profiles(self) -> tuple[AssetLearningProfile, ...]:
        events_getter = getattr(self.repository, "list_recommendation_events", None)
        outcomes_getter = getattr(self.repository, "list_business_outcomes", None)
        events = tuple(events_getter()) if callable(events_getter) else ()
        outcomes = tuple(outcomes_getter()) if callable(outcomes_getter) else ()
        asset_ids = {
            str(item.get("asset_id"))
            for item in events
            if item.get("asset_id") is not None
        }
        asset_ids.update(
            str(item.get("subject_id"))
            for item in outcomes
            if item.get("subject_type") == "asset" and item.get("subject_id") is not None
        )
        return tuple(
            self._asset_profile(asset_id, events=events, outcomes=outcomes)
            for asset_id in sorted(asset_ids, key=str)
        )

    def list_top_performers(self, *, limit: int = 10) -> tuple[AssetLearningProfile, ...]:
        return tuple(
            sorted(
                self.list_asset_learning_profiles(),
                key=lambda item: item.score,
                reverse=True,
            )[:limit]
        )

    def list_underperformers(self, *, limit: int = 10) -> tuple[AssetLearningProfile, ...]:
        return tuple(
            sorted(self.list_asset_learning_profiles(), key=lambda item: item.score)[
                :limit
            ]
        )

    def get_recommendation_outcome(
        self,
        recommendation_id: str,
    ) -> tuple[dict[str, Any], ...]:
        getter = getattr(self.repository, "list_recommendation_events", None)
        if not callable(getter):
            return ()
        return tuple(getter(recommendation_id=recommendation_id))

    def list_unmatched_outcomes(self) -> tuple[dict[str, Any], ...]:
        getter = getattr(self.repository, "list_unmatched_outcomes", None)
        return tuple(getter()) if callable(getter) else ()

    def list_failed_learning_events(self) -> tuple[dict[str, Any], ...]:
        getter = getattr(self.repository, "list_failed_learning_events", None)
        return tuple(getter()) if callable(getter) else ()

    def backfill_from_records(
        self,
        *,
        recommendation_results: Iterable[Any] = (),
        delivery_events: Iterable[Mapping[str, Any]] = (),
        commerce_outcomes: Iterable[Any] = (),
        business_outcomes: Iterable[Any] = (),
    ) -> dict[str, Any]:
        counts = {
            "recommendation_results": 0,
            "delivery_events": 0,
            "commerce_outcomes": 0,
            "business_outcomes": 0,
        }
        for result in recommendation_results or ():
            self.record_recommendation_result(result)
            counts["recommendation_results"] += 1
        for event in delivery_events or ():
            payload = event.get("payload") if isinstance(event, Mapping) else None
            payload = payload if isinstance(payload, Mapping) else event
            event_type = str(event.get("event_type") or "") if isinstance(event, Mapping) else ""
            if event_type in {"delivery_success", "delivery_failure"}:
                self.record_delivery_execution(
                    delivery_id=str(payload.get("delivery_id") or ""),
                    payload=payload.get("payload")
                    if isinstance(payload.get("payload"), Mapping)
                    else payload,
                    success=event_type == "delivery_success",
                    reason=payload.get("reason"),
                )
                counts["delivery_events"] += 1
        for outcome in commerce_outcomes or ():
            self.record_commerce_outcome(outcome)
            counts["commerce_outcomes"] += 1
        for outcome in business_outcomes or ():
            self.record_business_outcome(outcome)
            counts["business_outcomes"] += 1
        return {"success": True, "counts": counts, "automatic": False}

    def _event_from_candidate(
        self,
        candidate: Mapping[str, Any],
        *,
        request: Mapping[str, Any],
        recommendation_id: str,
        state: RecommendationEventState,
    ) -> RecommendationEvent:
        score = candidate.get("score")
        score = score if isinstance(score, Mapping) else {}
        metadata = candidate.get("metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        customer_context = request.get("customer_context")
        customer_context = customer_context if isinstance(customer_context, Mapping) else {}
        conversation_context = request.get("conversation_context")
        conversation_context = (
            conversation_context if isinstance(conversation_context, Mapping) else {}
        )
        asset_id = self._int(candidate.get("asset_id"))
        return RecommendationEvent(
            event_id=RecommendationEvent.deterministic_id(
                recommendation_id=recommendation_id,
                event_state=state.value,
                asset_id=asset_id,
            ),
            recommendation_id=recommendation_id,
            event_state=state.value,
            event_timestamp=self._now(),
            asset_id=asset_id,
            chat_registration_id=self._text(metadata.get("chat_registration_id")),
            product_id=self._first_text(candidate.get("product_ids")),
            experience_id=self._first_text(candidate.get("experience_ids")),
            customer_id=self._text(
                customer_context.get("customer_id")
                or customer_context.get("user_id")
                or customer_context.get("fanvue_user_id")
            ),
            conversation_id=self._text(
                conversation_context.get("conversation_id")
                or customer_context.get("conversation_id")
            ),
            recommendation_score=self._float(score.get("total")),
            recommendation_confidence=self._float(candidate.get("confidence")),
            recommendation_rationale=tuple(
                str(reason.get("rationale"))
                for reason in candidate.get("reasons", ())
                if isinstance(reason, Mapping) and reason.get("rationale")
            ),
            score_breakdown=score,
            supporting_evidence=tuple(
                dict(item)
                for item in candidate.get("evidence", ())
                if isinstance(item, Mapping)
            ),
            suppression_reasons=tuple(
                str(item) for item in candidate.get("suppression_reasons", ())
            ),
            rejected_candidate_reasons=tuple(
                str(item) for item in candidate.get("suppression_reasons", ())
            ),
            business_learning_context_reference=self._text(
                self._read_nested(request, "learning_context", "context_id")
                or self._read_nested(request, "learning_context", "metadata", "context_id")
            ),
            outcome_metadata={
                "selected": state == RecommendationEventState.SELECTED,
                "engine": metadata.get("source") or "ContentRecommendationService",
            },
        )

    def _asset_profile(
        self,
        asset_id: str,
        *,
        events: tuple[Mapping[str, Any], ...],
        outcomes: tuple[Mapping[str, Any], ...],
    ) -> AssetLearningProfile:
        asset_events = tuple(
            event for event in events if str(event.get("asset_id")) == str(asset_id)
        )
        asset_outcomes = tuple(
            outcome
            for outcome in outcomes
            if str(outcome.get("subject_id")) == str(asset_id)
        )
        states = tuple(str(event.get("event_state") or "") for event in asset_events)
        recommendation_count = states.count(RecommendationEventState.GENERATED.value)
        offer_count = states.count(RecommendationEventState.OFFERED.value)
        delivery_count = states.count(RecommendationEventState.DELIVERY_PREPARED.value) + states.count(
            RecommendationEventState.DELIVERED.value
        )
        purchase_events = states.count(RecommendationEventState.PURCHASED.value)
        refund_events = states.count(RecommendationEventState.REFUNDED.value)
        purchase_outcomes = tuple(
            item
            for item in asset_outcomes
            if str(item.get("outcome_type")) == "PRODUCT_PURCHASED"
        )
        refund_outcomes = tuple(
            item
            for item in asset_outcomes
            if str(item.get("outcome_type")) == "PRODUCT_REFUNDED"
        )
        purchase_count = max(purchase_events, len(purchase_outcomes))
        refund_count = max(refund_events, len(refund_outcomes))
        gross = 0
        tips = 0
        refunds = 0
        net = 0
        for item in asset_outcomes:
            provider_metadata = item.get("provider_metadata")
            provider_metadata = (
                provider_metadata if isinstance(provider_metadata, Mapping) else {}
            )
            gross += self._int(provider_metadata.get("gross_revenue_cents")) or 0
            tips += self._int(provider_metadata.get("tip_cents")) or 0
            refunds += self._int(provider_metadata.get("refund_cents")) or 0
            net += self._int(item.get("value_cents")) or 0
        conversion = (
            purchase_count / recommendation_count if recommendation_count else None
        )
        delivery_conversion = purchase_count / delivery_count if delivery_count else None
        sample_size = recommendation_count + purchase_count + delivery_count
        confidence = min(1.0, sample_size / 10.0) if sample_size else 0.0
        base = 0.0
        if conversion is not None:
            base += conversion * 16.0
        if delivery_conversion is not None:
            base += delivery_conversion * 8.0
        base += min(8.0, net / 1000.0)
        base -= refund_count * 5.0
        base -= states.count(RecommendationEventState.DELIVERY_FAILED.value) * 4.0
        if recommendation_count:
            base -= (
                states.count(RecommendationEventState.SUPPRESSED.value)
                / recommendation_count
            ) * 8.0
        score = max(-20.0, min(20.0, base * max(0.25, confidence)))
        latest = self._latest_timestamp(asset_events, asset_outcomes)
        return AssetLearningProfile(
            asset_id=int(asset_id),
            recommendation_count=recommendation_count,
            offer_count=offer_count,
            delivery_count=delivery_count,
            purchase_count=purchase_count,
            refund_count=refund_count,
            suppressed_count=states.count(RecommendationEventState.SUPPRESSED.value),
            rejected_count=states.count(RecommendationEventState.REJECTED.value),
            delivery_failure_count=states.count(
                RecommendationEventState.DELIVERY_FAILED.value
            )
            + states.count(RecommendationEventState.DELIVERY_BLOCKED.value),
            retry_count=states.count(RecommendationEventState.RETRIED.value),
            gross_revenue_cents=gross,
            tip_cents=tips,
            refund_cents=refunds,
            net_revenue_cents=net,
            conversion_rate=conversion,
            delivery_to_purchase_conversion=delivery_conversion,
            average_revenue_per_recommendation_cents=(
                net / recommendation_count if recommendation_count else None
            ),
            average_revenue_per_delivery_cents=(
                net / delivery_count if delivery_count else None
            ),
            confidence=confidence,
            sample_size=sample_size,
            score=score,
            evidence_freshness=latest,
            metadata={
                "source": "ContentCommerceLearningService",
                "unknown_values_omitted": True,
            },
        )

    def _customer_evidence(self, customer_context: Mapping[str, Any]) -> dict[str, Any]:
        customer_id = self._text(
            customer_context.get("customer_id")
            or customer_context.get("user_id")
            or customer_context.get("fanvue_user_id")
        )
        if not customer_id:
            return {"available": False}
        getter = getattr(self.repository, "list_business_outcomes", None)
        outcomes = (
            tuple(getter(customer_id=customer_id)) if callable(getter) else ()
        )
        purchases = tuple(
            item for item in outcomes if item.get("outcome_type") == "PRODUCT_PURCHASED"
        )
        return {
            "available": True,
            "customer_id": customer_id,
            "purchase_count": len(purchases),
            "net_revenue_cents": sum(self._int(item.get("value_cents")) or 0 for item in outcomes),
        }

    def _cohort_evidence(self, customer_context: Mapping[str, Any]) -> dict[str, Any]:
        cohorts = tuple(
            str(value)
            for value in self._as_iterable(
                customer_context.get("customer_segments")
                or customer_context.get("cohorts")
                or customer_context.get("cohort")
            )
            if str(value).strip()
        )
        return {"available": bool(cohorts), "cohorts": cohorts}

    def _record_event(self, event: RecommendationEvent) -> dict[str, Any]:
        recorder = getattr(self.repository, "record_recommendation_event", None)
        if not callable(recorder):
            return {"success": False, "reason": "repository_unavailable"}
        return recorder(event.to_context())

    def _record_failure(self, reason: str, payload: Mapping[str, Any]) -> None:
        recorder = getattr(self.repository, "record_learning_failure", None)
        if callable(recorder):
            recorder(reason=reason, payload=payload)

    def _recommendation_id(
        self,
        candidate: Mapping[str, Any],
        request: Mapping[str, Any],
    ) -> str:
        metadata = candidate.get("metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        explicit = metadata.get("recommendation_id") or candidate.get("recommendation_id")
        return self.recommendation_id_for(
            asset_id=candidate.get("asset_id"),
            request_context=request,
            explicit=str(explicit) if explicit else None,
        )

    def _business_outcome_payload(self, outcome: BusinessOutcome | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(outcome, Mapping):
            return dict(outcome)
        if is_dataclass(outcome):
            return asdict(outcome)
        context = getattr(outcome, "to_context", None)
        if callable(context):
            return dict(context())
        return dict(getattr(outcome, "__dict__", {}) or {})

    @staticmethod
    def _context(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return dict(value)
        context = getattr(value, "to_context", None)
        if callable(context):
            return dict(context())
        if is_dataclass(value):
            return asdict(value)
        return dict(getattr(value, "__dict__", {}) or {})

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text else None

    @staticmethod
    def _first_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value if value else None
        try:
            for item in value:
                if item not in (None, ""):
                    return str(item)
        except TypeError:
            return str(value)
        return None

    @staticmethod
    def _first_value(value: Any, *names: str) -> Any:
        if not isinstance(value, Mapping):
            return None
        for name in names:
            if value.get(name) is not None:
                return value.get(name)
        return None

    @staticmethod
    def _read_nested(value: Mapping[str, Any], *path: str) -> Any:
        current: Any = value
        for name in path:
            if not isinstance(current, Mapping):
                return None
            current = current.get(name)
        return current

    @staticmethod
    def _as_iterable(value: Any) -> tuple[Any, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        try:
            return tuple(value)
        except TypeError:
            return (value,)

    @staticmethod
    def _latest_timestamp(
        events: tuple[Mapping[str, Any], ...],
        outcomes: tuple[Mapping[str, Any], ...],
    ) -> str | None:
        values = [
            str(item.get("event_timestamp"))
            for item in events
            if item.get("event_timestamp")
        ]
        values.extend(
            str(item.get("occurred_at") or item.get("timestamp"))
            for item in outcomes
            if item.get("occurred_at") or item.get("timestamp")
        )
        return max(values) if values else None
