"""Canonical Commerce Execution orchestration boundary for Creator OS.

CommerceExecutionService owns provider-neutral execution orchestration only. It
does not decide what should happen, generate strategy, create Products, mutate
Publishing, call provider APIs directly, or replace provider runtime executors.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from app.models.commerce_execution import (
    CommerceExecutionPlan,
    CommerceExecutionRequest,
    CommerceExecutionResult,
    CommerceExecutionReview,
    CommerceExecutionReviewSummary,
    ExecutionDecision,
    ExecutionEvidence,
    ExecutionRecommendation,
    ExecutionRuntimeContext,
    PublishingExecutionOutputs,
    RuntimeExecutionAction,
    RuntimeExecutionIntent,
    RuntimeExecutionPayload,
    RuntimeExecutionResult,
)


class CommerceExecutionService:
    """Coordinate execution handoff without owning runtime behavior."""

    def execute(
        self,
        request: CommerceExecutionRequest | Mapping[str, Any],
        *,
        runtime_executor: Any | None = None,
    ) -> CommerceExecutionResult:
        normalized = self._normalize_request(request)
        evidence = self._evidence(normalized)
        execution_plan = self._execution_plan(normalized, evidence)
        runtime_intent = self.prepare_runtime_intent(
            execution_plan,
            request=normalized,
        )
        recommendations = self._recommendations(
            normalized,
            evidence,
            execution_plan,
        )

        if runtime_executor is None:
            runtime_result = self._runtime_result(
                runtime_intent,
                status="deferred",
                executed=False,
                execution_state="deferred_until_runtime_executor_available",
            )
            return CommerceExecutionResult(
                status="deferred",
                executed=False,
                provider=normalized.provider,
                execution_state="deferred_until_runtime_executor_available",
                execution_plan=execution_plan,
                runtime_intent=runtime_intent,
                runtime_result=runtime_result,
                recommendations=recommendations,
                evidence=evidence,
                metadata=self._metadata(
                    normalized,
                    execution_plan=execution_plan,
                    runtime_intent=runtime_intent,
                ),
            )

        execution_result = self._delegate_runtime_execution(
            runtime_executor,
            runtime_intent,
        )
        runtime_result = self._runtime_result(
            runtime_intent,
            status=self._execution_status(execution_result),
            executed=self._executed(execution_result),
            execution_state=self._execution_state(execution_result),
            runtime_result=execution_result,
        )
        return CommerceExecutionResult(
            status=runtime_result.status,
            executed=runtime_result.executed,
            provider=normalized.provider,
            execution_state=runtime_result.execution_state,
            execution_result=execution_result,
            execution_plan=execution_plan,
            runtime_intent=runtime_intent,
            runtime_result=runtime_result,
            recommendations=recommendations,
            evidence=evidence,
            metadata=self._metadata(
                normalized,
                execution_plan=execution_plan,
                runtime_intent=runtime_intent,
                delegated=True,
                runtime_executor=runtime_executor,
            ),
        )

    def build_execution_review(
        self,
        result: CommerceExecutionResult,
        *,
        reviewed_at: str | None = None,
    ) -> CommerceExecutionReview:
        """Build a read-only diagnostic view of an execution result."""
        metadata = dict(result.metadata or {})
        runtime_actions = tuple(
            action.value for action in (result.runtime_intent.actions or ())
        ) if result.runtime_intent else ()

        return CommerceExecutionReview(
            status=result.status,
            executed=result.executed,
            provider=result.provider,
            execution_state=result.execution_state,
            execution_type=(
                result.execution_plan.execution_type
                if result.execution_plan
                else None
            ),
            business_intent=(
                result.execution_plan.business_intent
                if result.execution_plan
                else None
            ),
            delivery_type=(
                result.execution_plan.delivery_type
                if result.execution_plan
                else None
            ),
            product_type=(
                result.execution_plan.product_type
                if result.execution_plan
                else None
            ),
            runtime_actions=runtime_actions,
            runtime_executor=metadata.get("runtime_executor"),
            reviewed_at=reviewed_at or self._timestamp(),
            execution_started_at=metadata.get("execution_started_at"),
            execution_completed_at=metadata.get("execution_completed_at"),
            plan=self._plan_review(result.execution_plan),
            runtime_intent=self._runtime_intent_review(result.runtime_intent),
            runtime_result=self._runtime_result_review(result.runtime_result),
            diagnostics=self._review_diagnostics(result),
            errors=self._review_errors(result),
            compatibility=self._review_compatibility(result),
        )

    def build_execution_review_summary(
        self,
        results: tuple[CommerceExecutionResult, ...] | list[CommerceExecutionResult],
        *,
        reviewed_at: str | None = None,
    ) -> CommerceExecutionReviewSummary:
        reviews = tuple(
            self.build_execution_review(result, reviewed_at=reviewed_at)
            for result in results
        )
        providers = tuple(
            dict.fromkeys(review.provider for review in reviews if review.provider)
        )
        runtime_actions = tuple(
            dict.fromkeys(
                action
                for review in reviews
                for action in review.runtime_actions
            )
        )
        return CommerceExecutionReviewSummary(
            total_executions=len(reviews),
            executed_count=sum(1 for review in reviews if review.executed),
            deferred_count=sum(
                1
                for review in reviews
                if self._normalize_key(review.status) == "deferred"
            ),
            failed_count=sum(
                1
                for review in reviews
                if self._normalize_key(review.status)
                in {"failed", "failure", "error"}
            ),
            providers=providers,
            runtime_actions=runtime_actions,
            items=reviews,
        )

    def prepare_runtime_intent(
        self,
        execution_plan: CommerceExecutionPlan,
        *,
        request: CommerceExecutionRequest | Mapping[str, Any] | None = None,
    ) -> RuntimeExecutionIntent:
        normalized = self._normalize_request(request or {})
        payload = (
            normalized.execution_payload
            if normalized.execution_payload is not None
            else self._payload_from_plan(execution_plan)
        )
        return RuntimeExecutionIntent(
            actions=self._runtime_actions(execution_plan),
            provider=execution_plan.provider or normalized.provider,
            execution_type=execution_plan.execution_type,
            business_intent=execution_plan.business_intent,
            payload=payload,
            context=normalized.runtime_context.to_context(),
            metadata={
                "source": "commerce_execution",
                "owner": "CommerceExecutionService",
                "provider_neutral": True,
                "runtime_specific": False,
                "telegram_specific": False,
                "calls_provider_apis_directly": False,
                "execution_plan_type": execution_plan.execution_type,
            },
        )

    @staticmethod
    def _normalize_request(
        request: CommerceExecutionRequest | Mapping[str, Any],
    ) -> CommerceExecutionRequest:
        if isinstance(request, CommerceExecutionRequest):
            return CommerceExecutionRequest(
                execution_decision=CommerceExecutionService._execution_decision(
                    request.execution_decision
                ),
                execution_payload=CommerceExecutionService._runtime_payload(
                    request.execution_payload
                ),
                provider=request.provider,
                delivery_type=request.delivery_type,
                product_type=request.product_type,
                product_reference=request.product_reference,
                product_strategy_context=request.product_strategy_context,
                commerce_strategy_context=request.commerce_strategy_context,
                customer_context=request.customer_context,
                publishing_outputs=(
                    CommerceExecutionService._publishing_outputs(
                        request.publishing_outputs
                    )
                ),
                runtime_context=CommerceExecutionService._runtime_context(
                    request.runtime_context,
                    customer_context=request.customer_context,
                ),
                metadata=dict(request.metadata or {}),
            )
        return CommerceExecutionRequest(
            execution_decision=CommerceExecutionService._execution_decision(
                request.get("execution_decision")
            ),
            execution_payload=CommerceExecutionService._runtime_payload(
                request.get("execution_payload")
            ),
            provider=request.get("provider"),
            delivery_type=request.get("delivery_type"),
            product_type=request.get("product_type"),
            product_reference=request.get("product_reference"),
            product_strategy_context=request.get("product_strategy_context"),
            commerce_strategy_context=request.get("commerce_strategy_context"),
            customer_context=request.get("customer_context"),
            publishing_outputs=CommerceExecutionService._publishing_outputs(
                request.get("publishing_outputs")
            ),
            runtime_context=CommerceExecutionService._runtime_context(
                request.get("runtime_context"),
                customer_context=request.get("customer_context"),
            ),
            metadata=dict(request.get("metadata") or {}),
        )

    @staticmethod
    def _delegate_runtime_execution(
        runtime_executor: Any,
        runtime_intent: RuntimeExecutionIntent,
    ) -> Any:
        try:
            return runtime_executor.execute(
                runtime_intent,
                context=runtime_intent.context,
            )
        except TypeError:
            try:
                return runtime_executor.execute(runtime_intent)
            except TypeError:
                return runtime_executor.execute(runtime_intent.payload)

    @staticmethod
    def _execution_decision(value: Any) -> ExecutionDecision | None:
        if value is None:
            return None
        if isinstance(value, ExecutionDecision):
            return value
        return ExecutionDecision(
            action=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(
                    value,
                    "action",
                    "delivery_action",
                    "next_suggested_action",
                )
            ),
            delivery_type=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(
                    value,
                    "delivery_type",
                    "current_delivery_type",
                )
            ),
            product_type=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(
                    value,
                    "product_type",
                    "product_kind",
                    "recommendation_type",
                )
            ),
            product_reference=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(
                    value,
                    "product_reference",
                    "current_product_id",
                    "product_id",
                )
            ),
            delivery_method=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(value, "delivery_method")
            ),
            blocked=bool(
                CommerceExecutionService._first_value(value, "blocked") is True
            ),
            metadata=CommerceExecutionService._metadata_from_value(value),
        )

    @staticmethod
    def _runtime_payload(value: Any) -> RuntimeExecutionPayload | None:
        if value is None:
            return None
        if isinstance(value, RuntimeExecutionPayload):
            return value
        return RuntimeExecutionPayload(
            delivery_type=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(
                    value,
                    "delivery_type",
                    "current_delivery_type",
                )
            ),
            message_text=str(
                CommerceExecutionService._first_value(
                    value,
                    "message_text",
                    "response_text",
                )
                or ""
            ),
            asset_path=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(value, "asset_path")
            ),
            media_link=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(
                    value,
                    "media_link",
                    "paid_media_link",
                    "provider_output_url",
                )
            ),
            product_reference=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(
                    value,
                    "product_reference",
                    "current_product_id",
                    "product_id",
                )
            ),
            experience_reference=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(
                    value,
                    "experience_reference",
                    "current_experience_id",
                    "experience_id",
                )
            ),
            delivery_reason=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(value, "delivery_reason")
            ),
            blocking_reason=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(value, "blocking_reason")
            ),
            next_suggested_action=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(
                    value,
                    "next_suggested_action",
                )
            ),
            delivery_method=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(value, "delivery_method")
            ),
            execution_type=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(value, "execution_type")
            ),
            business_intent=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(value, "business_intent")
            ),
            metadata=CommerceExecutionService._metadata_from_value(value),
        )

    @staticmethod
    def _publishing_outputs(value: Any) -> PublishingExecutionOutputs | None:
        if value is None:
            return None
        if isinstance(value, PublishingExecutionOutputs):
            return value
        return PublishingExecutionOutputs(
            media_link=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(value, "media_link")
            ),
            provider_output_url=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(
                    value,
                    "provider_output_url",
                )
            ),
            output_url=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(value, "output_url")
            ),
            source=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(value, "source")
            ),
            metadata=CommerceExecutionService._metadata_from_value(value),
        )

    @staticmethod
    def _runtime_context(
        value: Any,
        *,
        customer_context: Any | None = None,
    ) -> ExecutionRuntimeContext:
        if isinstance(value, ExecutionRuntimeContext):
            return value
        return ExecutionRuntimeContext(
            correlation_id=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(value, "correlation_id")
            ),
            engine_user_id=CommerceExecutionService._normalize_optional_text(
                CommerceExecutionService._first_value(value, "engine_user_id")
            ),
            customer_context=customer_context
            or CommerceExecutionService._first_value(value, "customer_context"),
            metadata=CommerceExecutionService._metadata_from_value(value),
        )

    def _recommendations(
        self,
        request: CommerceExecutionRequest,
        evidence: tuple[ExecutionEvidence, ...],
        execution_plan: CommerceExecutionPlan,
    ) -> tuple[ExecutionRecommendation, ...]:
        if not evidence:
            return ()
        return (
            ExecutionRecommendation(
                recommendation_type=execution_plan.execution_type,
                objective=execution_plan.objective,
                provider=request.provider,
                confidence=self._confidence(evidence),
                rationale=tuple(item.detail for item in evidence if item.detail),
                evidence=evidence,
                metadata={
                    "source": "commerce_execution",
                    "owner": "CommerceExecutionService",
                    "business_intent": execution_plan.business_intent,
                    "delivery_type": execution_plan.delivery_type,
                    "product_type": execution_plan.product_type,
                    "generates_runtime_decisions": False,
                    "calls_provider_apis_directly": False,
                    "runtime_specific": False,
                },
            ),
        )

    def _execution_plan(
        self,
        request: CommerceExecutionRequest,
        evidence: tuple[ExecutionEvidence, ...],
    ) -> CommerceExecutionPlan:
        delivery_type = self._delivery_type(request)
        product_type = self._product_type(request)
        execution_type = self._execution_type(
            delivery_type=delivery_type,
            product_type=product_type,
        )
        requires_media_link = execution_type in {
            "execute_paid_product",
            "execute_bundle_product",
            "execute_album_product",
            "execute_story_product",
        }
        return CommerceExecutionPlan(
            execution_type=execution_type,
            delivery_type=delivery_type,
            product_type=product_type,
            business_intent=self._business_intent(execution_type),
            objective=self._objective(execution_type),
            provider=request.provider,
            requires_media_link=requires_media_link,
            provider_neutral_steps=self._provider_neutral_steps(
                execution_type,
                requires_media_link=requires_media_link,
            ),
            evidence=evidence,
            metadata={
                "source": "commerce_execution",
                "owner": "CommerceExecutionService",
                "runtime_specific": False,
                "telegram_action": False,
                "calls_provider_apis_directly": False,
                "modifies_publishing": False,
                "product_reference": request.product_reference
                or self._first_value(
                    request.execution_decision,
                    "product_reference",
                    "current_product_id",
                    "product_id",
                )
                or self._first_value(
                    request.execution_payload,
                    "product_reference",
                    "current_product_id",
                    "product_id",
                ),
            },
        )

    @classmethod
    def _delivery_type(cls, request: CommerceExecutionRequest) -> str | None:
        return cls._normalize_text(
            request.delivery_type
            or cls._first_value(
                request.execution_decision,
                "delivery_type",
                "current_delivery_type",
            )
            or cls._first_value(
                request.execution_payload,
                "delivery_type",
                "current_delivery_type",
            )
        )

    @classmethod
    def _product_type(cls, request: CommerceExecutionRequest) -> str | None:
        return cls._normalize_text(
            request.product_type
            or cls._first_value(
                request.execution_decision,
                "product_type",
                "product_kind",
                "recommendation_type",
            )
            or cls._first_value(
                request.execution_payload,
                "product_type",
                "product_kind",
                "recommendation_type",
            )
            or cls._first_value(
                request.product_strategy_context,
                "recommendation_type",
                "product_type",
                "composition_type",
            )
        )

    @classmethod
    def _execution_type(
        cls,
        *,
        delivery_type: str | None,
        product_type: str | None,
    ) -> str:
        normalized_product = cls._normalize_key(product_type)
        if normalized_product in {"story", "story_product"}:
            return "execute_story_product"
        if normalized_product in {"album", "photo_set", "video_set", "photoshoot_product"}:
            return "execute_album_product"
        if normalized_product in {"bundle", "collection", "vip_collection"}:
            return "execute_bundle_product"
        if cls._normalize_key(delivery_type) == "free":
            return "execute_free_product"
        if cls._normalize_key(delivery_type) == "paid":
            return "execute_paid_product"
        return "prepare_delivery_execution"

    @staticmethod
    def _business_intent(execution_type: str) -> str:
        mapping = {
            "execute_free_product": "Execute FREE Product",
            "execute_paid_product": "Execute PAID Product",
            "execute_bundle_product": "Execute Bundle Product",
            "execute_album_product": "Execute Album Product",
            "execute_story_product": "Execute Story Product",
            "prepare_delivery_execution": "Prepare Delivery Execution",
        }
        return mapping.get(execution_type, "Prepare Delivery Execution")

    @staticmethod
    def _objective(execution_type: str) -> str:
        mapping = {
            "execute_free_product": "Prepare a provider-neutral plan for FREE Product delivery.",
            "execute_paid_product": "Prepare a provider-neutral plan for PAID Product delivery.",
            "execute_bundle_product": "Prepare a provider-neutral plan for Bundle delivery.",
            "execute_album_product": "Prepare a provider-neutral plan for Album delivery.",
            "execute_story_product": "Prepare a provider-neutral plan for Story Product delivery.",
            "prepare_delivery_execution": "Prepare a provider-neutral execution plan from available context.",
        }
        return mapping.get(
            execution_type,
            "Prepare a provider-neutral execution plan from available context.",
        )

    @staticmethod
    def _provider_neutral_steps(
        execution_type: str,
        *,
        requires_media_link: bool,
    ) -> tuple[str, ...]:
        steps = [
            "validate_execution_decision",
            "prepare_business_delivery_context",
        ]
        if requires_media_link:
            steps.append("require_publishing_output")
        if execution_type == "execute_bundle_product":
            steps.append("prepare_bundle_delivery_context")
        elif execution_type == "execute_album_product":
            steps.append("prepare_album_delivery_context")
        elif execution_type == "execute_story_product":
            steps.append("prepare_story_delivery_context")
        steps.append("delegate_to_provider_runtime_boundary")
        return tuple(steps)

    @staticmethod
    def _runtime_actions(
        execution_plan: CommerceExecutionPlan,
    ) -> tuple[RuntimeExecutionAction, ...]:
        mapping = {
            "execute_free_product": (
                RuntimeExecutionAction.DELIVER_MEDIA,
                RuntimeExecutionAction.CONTINUE_CONVERSATION,
            ),
            "execute_paid_product": (
                RuntimeExecutionAction.DELIVER_MEDIA_LINK,
                RuntimeExecutionAction.PRESENT_CALL_TO_ACTION,
                RuntimeExecutionAction.FOLLOW_UP_REQUIRED,
            ),
            "execute_bundle_product": (
                RuntimeExecutionAction.DELIVER_BUNDLE,
                RuntimeExecutionAction.PRESENT_CALL_TO_ACTION,
                RuntimeExecutionAction.FOLLOW_UP_REQUIRED,
            ),
            "execute_album_product": (
                RuntimeExecutionAction.DELIVER_ALBUM,
                RuntimeExecutionAction.PRESENT_CALL_TO_ACTION,
                RuntimeExecutionAction.FOLLOW_UP_REQUIRED,
            ),
            "execute_story_product": (
                RuntimeExecutionAction.DELIVER_STORY_STEP,
                RuntimeExecutionAction.PRESENT_CALL_TO_ACTION,
                RuntimeExecutionAction.FOLLOW_UP_REQUIRED,
            ),
        }
        return mapping.get(
            execution_plan.execution_type,
            (
                RuntimeExecutionAction.CONTINUE_CONVERSATION,
                RuntimeExecutionAction.FOLLOW_UP_REQUIRED,
            ),
        )

    @staticmethod
    def _payload_from_plan(
        execution_plan: CommerceExecutionPlan,
    ) -> RuntimeExecutionPayload:
        return RuntimeExecutionPayload(
            execution_type=execution_plan.execution_type,
            delivery_type=execution_plan.delivery_type,
            business_intent=execution_plan.business_intent,
            product_reference=execution_plan.metadata.get("product_reference"),
            metadata={
                "source": "commerce_execution_plan",
                "product_type": execution_plan.product_type,
            },
        )

    @staticmethod
    def _runtime_result(
        runtime_intent: RuntimeExecutionIntent,
        *,
        status: str,
        executed: bool,
        execution_state: str | None,
        runtime_result: Any | None = None,
    ) -> RuntimeExecutionResult:
        return RuntimeExecutionResult(
            status=status,
            executed=executed,
            actions=runtime_intent.actions,
            provider=runtime_intent.provider,
            execution_state=execution_state,
            runtime_result=runtime_result,
            metadata={
                "source": "commerce_execution",
                "owner": "CommerceExecutionService",
                "provider_neutral": True,
                "runtime_specific": False,
                "telegram_specific": False,
            },
        )

    @classmethod
    def _evidence(
        cls,
        request: CommerceExecutionRequest,
    ) -> tuple[ExecutionEvidence, ...]:
        evidence = []
        if request.execution_decision is not None:
            evidence.append(
                ExecutionEvidence(
                    reason="execution_decision",
                    detail="Execution decision supplied by an upstream intelligence boundary.",
                    weight=30,
                )
            )
        if request.product_strategy_context is not None:
            evidence.append(
                ExecutionEvidence(
                    reason="product_strategy_context",
                    detail="Product Strategy context is available for execution traceability.",
                    weight=10,
                )
            )
        if request.commerce_strategy_context is not None:
            evidence.append(
                ExecutionEvidence(
                    reason="commerce_strategy_context",
                    detail="Commerce Strategy context is available for execution traceability.",
                    weight=10,
                )
            )
        if request.publishing_outputs is not None:
            evidence.append(
                ExecutionEvidence(
                    reason="publishing_outputs",
                    detail="Publishing output context is available for execution traceability.",
                    weight=15,
                )
            )
        if request.execution_payload is not None:
            evidence.append(
                ExecutionEvidence(
                    reason="execution_payload",
                    detail="Provider-neutral execution payload is available.",
                    weight=25,
                )
            )
        delivery_type = cls._delivery_type(request)
        if delivery_type is not None:
            evidence.append(
                ExecutionEvidence(
                    reason="delivery_type",
                    detail=f"Delivery Type {delivery_type} is available for execution planning.",
                    weight=10,
                )
            )
        product_type = cls._product_type(request)
        if product_type is not None:
            evidence.append(
                ExecutionEvidence(
                    reason="product_type",
                    detail=f"Product Type {product_type} is available for execution planning.",
                    weight=10,
                )
            )
        return tuple(evidence)

    @staticmethod
    def _confidence(evidence: tuple[ExecutionEvidence, ...]) -> float:
        if not evidence:
            return 0.0
        return round(min(0.95, sum(item.weight for item in evidence) / 100), 2)

    @staticmethod
    def _execution_status(execution_result: Any) -> str:
        value = getattr(execution_result, "status", None)
        if value is not None:
            return str(value)
        if isinstance(execution_result, Mapping):
            return str(execution_result.get("status") or "delegated")
        return "delegated"

    @staticmethod
    def _executed(execution_result: Any) -> bool:
        value = getattr(execution_result, "executed", None)
        if value is not None:
            return bool(value)
        if isinstance(execution_result, Mapping):
            return bool(execution_result.get("executed", False))
        return False

    @staticmethod
    def _execution_state(execution_result: Any) -> str | None:
        metadata = getattr(execution_result, "metadata", None)
        if isinstance(metadata, Mapping):
            return metadata.get("execution_state")
        if isinstance(execution_result, Mapping):
            result_metadata = execution_result.get("metadata")
            if isinstance(result_metadata, Mapping):
                return result_metadata.get("execution_state")
        return None

    @staticmethod
    def _metadata(
        request: CommerceExecutionRequest,
        *,
        execution_plan: CommerceExecutionPlan | None = None,
        runtime_intent: RuntimeExecutionIntent | None = None,
        delegated: bool = False,
        runtime_executor: Any | None = None,
    ) -> dict[str, Any]:
        metadata = {
            "source": "commerce_execution",
            "owner": "CommerceExecutionService",
            "delegated_to_runtime": delegated,
            "runtime_executor": type(runtime_executor).__name__
            if runtime_executor is not None
            else None,
            "provider": request.provider,
            "execution_plan_type": (
                execution_plan.execution_type if execution_plan else None
            ),
            "business_intent": (
                execution_plan.business_intent if execution_plan else None
            ),
            "runtime_actions": tuple(
                action.value for action in runtime_intent.actions
            )
            if runtime_intent
            else (),
            "creates_products": False,
            "creates_product_drafts": False,
            "generates_product_strategy": False,
            "generates_commerce_strategy": False,
            "generates_runtime_decisions": False,
            "calls_provider_apis_directly": False,
            "modifies_publishing": False,
            "new_ai_analysis": False,
            "telegram_specific": False,
        }
        metadata.update(dict(request.metadata or {}))
        return metadata

    @classmethod
    def _first_value(cls, source: Any, *names: str) -> Any | None:
        if source is None:
            return None
        for name in names:
            if isinstance(source, Mapping):
                value = source.get(name)
            else:
                value = getattr(source, name, None)
            if value is not None:
                return value
        return None

    @staticmethod
    def _plan_review(
        execution_plan: CommerceExecutionPlan | None,
    ) -> dict[str, Any]:
        if execution_plan is None:
            return {}
        return {
            "execution_type": execution_plan.execution_type,
            "delivery_type": execution_plan.delivery_type,
            "product_type": execution_plan.product_type,
            "business_intent": execution_plan.business_intent,
            "objective": execution_plan.objective,
            "provider": execution_plan.provider,
            "requires_media_link": execution_plan.requires_media_link,
            "provider_neutral_steps": execution_plan.provider_neutral_steps,
            "evidence": tuple(
                {
                    "reason": item.reason,
                    "detail": item.detail,
                    "weight": item.weight,
                }
                for item in execution_plan.evidence
            ),
            "metadata": dict(execution_plan.metadata or {}),
        }

    @staticmethod
    def _runtime_intent_review(
        runtime_intent: RuntimeExecutionIntent | None,
    ) -> dict[str, Any]:
        if runtime_intent is None:
            return {}
        return {
            "actions": tuple(action.value for action in runtime_intent.actions),
            "provider": runtime_intent.provider,
            "execution_type": runtime_intent.execution_type,
            "business_intent": runtime_intent.business_intent,
            "has_payload": runtime_intent.payload is not None,
            "context": dict(runtime_intent.context or {}),
            "metadata": dict(runtime_intent.metadata or {}),
        }

    @classmethod
    def _runtime_result_review(
        cls,
        runtime_result: RuntimeExecutionResult | None,
    ) -> dict[str, Any]:
        if runtime_result is None:
            return {}
        provider_result = runtime_result.runtime_result
        provider_metadata = cls._metadata_from(provider_result)
        return {
            "status": runtime_result.status,
            "executed": runtime_result.executed,
            "actions": tuple(action.value for action in runtime_result.actions),
            "provider": runtime_result.provider,
            "execution_state": runtime_result.execution_state,
            "metadata": dict(runtime_result.metadata or {}),
            "provider_status": cls._first_value(provider_result, "status"),
            "provider_executed": cls._first_value(provider_result, "executed"),
            "provider_metadata": provider_metadata,
        }

    @classmethod
    def _review_diagnostics(
        cls,
        result: CommerceExecutionResult,
    ) -> dict[str, Any]:
        metadata = dict(result.metadata or {})
        return {
            "execution_owner": "CommerceExecutionService",
            "review_owner": "Execution Review",
            "read_only": True,
            "delegated_to_runtime": metadata.get("delegated_to_runtime"),
            "runtime_executor": metadata.get("runtime_executor"),
            "execution_plan_type": metadata.get("execution_plan_type"),
            "business_intent": metadata.get("business_intent"),
            "runtime_actions": metadata.get("runtime_actions", ()),
            "status": result.status,
            "execution_state": result.execution_state,
            "runtime_result_status": (
                result.runtime_result.status if result.runtime_result else None
            ),
        }

    @classmethod
    def _review_errors(cls, result: CommerceExecutionResult) -> tuple[str, ...]:
        errors = []
        status = cls._normalize_key(result.status)
        if status in {"failed", "failure", "error"}:
            errors.append(f"execution_status:{result.status}")
        for source in (
            result,
            result.runtime_result,
            result.execution_result,
            result.runtime_result.runtime_result if result.runtime_result else None,
        ):
            metadata = cls._metadata_from(source)
            for key in ("error", "error_type", "failure_reason", "diagnostic"):
                value = metadata.get(key)
                if value:
                    errors.append(f"{key}:{value}")
        return tuple(dict.fromkeys(errors))

    @staticmethod
    def _review_compatibility(result: CommerceExecutionResult) -> dict[str, Any]:
        metadata = dict(result.metadata or {})
        return {
            "read_only": True,
            "presentation_only": True,
            "runtime_behavior_changed": False,
            "calls_telegram": False,
            "calls_publishing": False,
            "modifies_decision_engine": False,
            "modifies_products": False,
            "preserves_runtime_executor": True,
            "delegated_to_runtime": metadata.get("delegated_to_runtime"),
            "provider_neutral": True,
        }

    @staticmethod
    def _metadata_from(source: Any) -> dict[str, Any]:
        if source is None:
            return {}
        metadata = getattr(source, "metadata", None)
        if isinstance(metadata, Mapping):
            return dict(metadata)
        if isinstance(source, Mapping):
            metadata = source.get("metadata")
            if isinstance(metadata, Mapping):
                return dict(metadata)
        return {}

    @staticmethod
    def _metadata_from_value(source: Any) -> dict[str, Any]:
        if source is None:
            return {}
        metadata = getattr(source, "metadata", None)
        if isinstance(metadata, Mapping):
            return dict(metadata)
        if isinstance(source, Mapping):
            explicit = source.get("metadata")
            if isinstance(explicit, Mapping):
                return dict(explicit)
            return dict(source)
        return {}

    @staticmethod
    def _normalize_optional_text(value: Any) -> str | None:
        raw = getattr(value, "value", value)
        if raw is None:
            return None
        text = str(raw).strip()
        return text or None

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_text(value: Any) -> str | None:
        raw = getattr(value, "value", value)
        if raw is None:
            return None
        text = str(raw).strip()
        return text.upper() if text else None

    @staticmethod
    def _normalize_key(value: Any) -> str:
        raw = getattr(value, "value", value)
        return str(raw or "").strip().lower()
