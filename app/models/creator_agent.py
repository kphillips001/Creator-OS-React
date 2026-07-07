"""Provider-neutral Creator Agent read models.

Creator Agent is a natural-language presentation and orchestration boundary. It
does not own business logic and does not execute provider/runtime mutations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class CreatorAgentIntent(str, Enum):
    UNKNOWN = "UNKNOWN"
    DAILY_PRIORITIES = "DAILY_PRIORITIES"
    BUSINESS_HEALTH = "BUSINESS_HEALTH"
    PRODUCT_ATTENTION = "PRODUCT_ATTENTION"
    PUBLISHING_READINESS = "PUBLISHING_READINESS"
    CUSTOMER_ATTENTION = "CUSTOMER_ATTENTION"
    TELEGRAM_FOLLOW_UP = "TELEGRAM_FOLLOW_UP"
    BUSINESS_OPTIMIZATION_SUMMARY = "BUSINESS_OPTIMIZATION_SUMMARY"
    BUSINESS_LEARNING = "BUSINESS_LEARNING"
    PRODUCT_RECOMMENDATION = "PRODUCT_RECOMMENDATION"
    COMMERCE_RECOMMENDATION = "COMMERCE_RECOMMENDATION"
    WORKSPACE_OVERVIEW = "WORKSPACE_OVERVIEW"
    CONTENT_OPPORTUNITY = "CONTENT_OPPORTUNITY"
    EXPLAIN_RECOMMENDATION = "EXPLAIN_RECOMMENDATION"
    COMPARE_BUSINESS_OPTIONS = "COMPARE_BUSINESS_OPTIONS"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class CreatorAgentRequest:
    """Natural-language request plus optional context identifiers."""

    question: str
    creator_profile_id: str | int | None = None
    account_id: str | int | None = None
    customer_id: str | int | None = None
    product_id: str | int | None = None
    provider: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class CreatorAgentSource:
    """A read-model or service used to answer a Creator Agent request."""

    source_type: str
    name: str
    summary: str
    confidence: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorAgentRecommendedAction:
    """Advisory next action surfaced from existing Creator OS domains."""

    title: str
    detail: str = ""
    priority: str = "NORMAL"
    source: str = "CreatorAgentService"
    target: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorAgentEvidence:
    """Source-backed evidence used in a Creator Agent explanation."""

    source: str
    summary: str
    evidence_type: str = "read_model"
    confidence: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorAgentActionProposal:
    """Non-executing proposal for a future confirmed action workflow."""

    action_type: str
    title: str
    detail: str = ""
    requires_confirmation: bool = True
    executable_by: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorAgentTool:
    """Read-only service capability available to Creator Agent orchestration."""

    name: str
    service_name: str
    method_name: str
    context_field: str
    intents: tuple[CreatorAgentIntent, ...]
    read_only: bool = True
    allows_runtime_execution: bool = False
    allows_mutations: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorAgentToolRequest:
    """A single read-only tool invocation selected for a Creator Agent request."""

    tool: CreatorAgentTool
    request: CreatorAgentRequest
    intent: CreatorAgentIntent
    parameters: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorAgentToolResult:
    """Structured result from a read-only Creator Agent tool invocation."""

    tool: CreatorAgentTool
    success: bool
    result: Any | None = None
    warning: str | None = None
    source: CreatorAgentSource | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorAgentToolRegistry:
    """Provider-neutral map from Creator Agent intents to existing services."""

    tools: tuple[CreatorAgentTool, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)

    def tools_for_intent(
        self, intent: CreatorAgentIntent
    ) -> tuple[CreatorAgentTool, ...]:
        return tuple(tool for tool in self.tools if intent in tool.intents)


@dataclass(frozen=True)
class CreatorAgentToolContext:
    """Selected tool requests and results for one Creator Agent response."""

    intent: CreatorAgentIntent
    requests: tuple[CreatorAgentToolRequest, ...] = ()
    results: tuple[CreatorAgentToolResult, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorAgentContext:
    """Resolved read-only context gathered for a Creator Agent response."""

    intent: CreatorAgentIntent = CreatorAgentIntent.UNKNOWN
    business_optimization_snapshot: Any | None = None
    workspace_dashboard: Any | None = None
    product_business_snapshot: Any | None = None
    telegram_business_snapshot: Any | None = None
    customer_business_snapshot: Any | None = None
    business_learning_snapshot: Any | None = None
    publishing_summary: Any | None = None
    product_strategy_result: Any | None = None
    commerce_strategy_result: Any | None = None
    content_opportunity_snapshot: Any | None = None
    tool_context: CreatorAgentToolContext | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorAgentResponse:
    """Structured answer returned by the Creator Agent boundary."""

    request: CreatorAgentRequest
    intent: CreatorAgentIntent
    answer_text: str
    context: CreatorAgentContext = field(default_factory=CreatorAgentContext)
    sources: tuple[CreatorAgentSource, ...] = ()
    confidence: float = 0.0
    recommended_actions: tuple[CreatorAgentRecommendedAction, ...] = ()
    action_proposals: tuple[CreatorAgentActionProposal, ...] = ()
    business_reasoning: tuple[str, ...] = ()
    supporting_evidence: tuple[CreatorAgentEvidence, ...] = ()
    confidence_explanation: str = ""
    recommendation_rationale: tuple[str, ...] = ()
    suggested_follow_up_questions: tuple[str, ...] = ()
    related_business_areas: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
