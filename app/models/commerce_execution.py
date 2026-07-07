"""Provider-neutral Commerce Execution orchestration models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.models.commerce_strategy import (
    CommerceStrategyRecommendation,
    CommerceStrategyResult,
)
from app.models.customer_intelligence import CustomerIntelligenceSnapshot
from app.models.product_strategy import (
    ProductStrategyRecommendation,
    ProductStrategyResult,
)


@dataclass(frozen=True)
class ExecutionEvidence:
    reason: str
    detail: str | None = None
    weight: int = 0


@dataclass(frozen=True)
class ExecutionRecommendation:
    recommendation_type: str
    objective: str | None = None
    provider: str | None = None
    confidence: float = 0.0
    rationale: tuple[str, ...] = ()
    evidence: tuple[ExecutionEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommerceExecutionPlan:
    execution_type: str
    delivery_type: str | None = None
    product_type: str | None = None
    business_intent: str | None = None
    objective: str | None = None
    provider: str | None = None
    requires_media_link: bool = False
    provider_neutral_steps: tuple[str, ...] = ()
    evidence: tuple[ExecutionEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionDecision:
    """Provider-neutral execution decision supplied by upstream domains."""

    action: str | None = None
    delivery_type: str | None = None
    product_type: str | None = None
    product_reference: str | None = None
    delivery_method: str | None = None
    blocked: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PublishingExecutionOutputs:
    """Provider-neutral publishing outputs available to execution."""

    media_link: str | None = None
    provider_output_url: str | None = None
    output_url: str | None = None
    source: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionRuntimeContext:
    """Provider-neutral runtime context for execution delegation."""

    correlation_id: str | None = None
    engine_user_id: str | None = None
    customer_context: CustomerIntelligenceSnapshot | Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        context = dict(self.metadata or {})
        if self.correlation_id is not None:
            context["correlation_id"] = self.correlation_id
        if self.engine_user_id is not None:
            context["engine_user_id"] = self.engine_user_id
        if self.customer_context is not None:
            context["customer_context"] = self.customer_context
        return context


@dataclass(frozen=True)
class RuntimeExecutionPayload:
    """Provider-neutral runtime payload carried by RuntimeExecutionIntent."""

    delivery_type: str | None = None
    message_text: str = ""
    asset_path: str | None = None
    media_link: str | None = None
    product_reference: str | None = None
    experience_reference: str | None = None
    delivery_reason: str | None = None
    blocking_reason: str | None = None
    next_suggested_action: str | None = None
    delivery_method: str | None = None
    execution_type: str | None = None
    business_intent: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class RuntimeExecutionAction(str, Enum):
    DELIVER_MEDIA = "DELIVER_MEDIA"
    DELIVER_MEDIA_LINK = "DELIVER_MEDIA_LINK"
    DELIVER_BUNDLE = "DELIVER_BUNDLE"
    DELIVER_ALBUM = "DELIVER_ALBUM"
    DELIVER_STORY_STEP = "DELIVER_STORY_STEP"
    PRESENT_CALL_TO_ACTION = "PRESENT_CALL_TO_ACTION"
    CONTINUE_CONVERSATION = "CONTINUE_CONVERSATION"
    FOLLOW_UP_REQUIRED = "FOLLOW_UP_REQUIRED"


@dataclass(frozen=True)
class RuntimeExecutionIntent:
    actions: tuple[RuntimeExecutionAction, ...] = ()
    provider: str | None = None
    execution_type: str | None = None
    business_intent: str | None = None
    payload: RuntimeExecutionPayload | None = None
    context: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeExecutionResult:
    status: str
    executed: bool
    actions: tuple[RuntimeExecutionAction, ...] = ()
    provider: str | None = None
    execution_state: str | None = None
    runtime_result: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommerceExecutionReview:
    status: str
    executed: bool
    provider: str | None = None
    execution_state: str | None = None
    execution_type: str | None = None
    business_intent: str | None = None
    delivery_type: str | None = None
    product_type: str | None = None
    runtime_actions: tuple[str, ...] = ()
    runtime_executor: str | None = None
    reviewed_at: str | None = None
    execution_started_at: str | None = None
    execution_completed_at: str | None = None
    plan: Mapping[str, Any] = field(default_factory=dict)
    runtime_intent: Mapping[str, Any] = field(default_factory=dict)
    runtime_result: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommerceExecutionReviewSummary:
    total_executions: int = 0
    executed_count: int = 0
    deferred_count: int = 0
    failed_count: int = 0
    providers: tuple[str, ...] = ()
    runtime_actions: tuple[str, ...] = ()
    items: tuple[CommerceExecutionReview, ...] = ()


@dataclass(frozen=True)
class CommerceExecutionRequest:
    execution_decision: ExecutionDecision | Mapping[str, Any] | None = None
    execution_payload: RuntimeExecutionPayload | Mapping[str, Any] | None = None
    provider: str | None = None
    delivery_type: str | None = None
    product_type: str | None = None
    product_reference: str | None = None
    product_strategy_context: (
        ProductStrategyResult
        | ProductStrategyRecommendation
        | Mapping[str, Any]
        | None
    ) = None
    commerce_strategy_context: (
        CommerceStrategyResult
        | CommerceStrategyRecommendation
        | Mapping[str, Any]
        | None
    ) = None
    customer_context: CustomerIntelligenceSnapshot | Mapping[str, Any] | None = None
    publishing_outputs: PublishingExecutionOutputs | Mapping[str, Any] | None = None
    runtime_context: ExecutionRuntimeContext | Mapping[str, Any] = field(
        default_factory=dict
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommerceExecutionResult:
    status: str
    executed: bool
    provider: str | None = None
    execution_state: str | None = None
    execution_result: Any | None = None
    execution_plan: CommerceExecutionPlan | None = None
    runtime_intent: RuntimeExecutionIntent | None = None
    runtime_result: RuntimeExecutionResult | None = None
    recommendations: tuple[ExecutionRecommendation, ...] = ()
    evidence: tuple[ExecutionEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
