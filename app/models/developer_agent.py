"""Provider-neutral Developer Agent read models.

Developer Agent is an advisory software architecture assistant. It does not
execute commands, modify files, mutate business state, or call runtime services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class DeveloperAgentIntent(str, Enum):
    UNKNOWN = "UNKNOWN"
    ARCHITECTURE_AUDIT = "ARCHITECTURE_AUDIT"
    ROADMAP_GUIDANCE = "ROADMAP_GUIDANCE"
    COMPATIBILITY_VALIDATION = "COMPATIBILITY_VALIDATION"
    IMPLEMENTATION_PLANNING = "IMPLEMENTATION_PLANNING"
    TEST_STRATEGY = "TEST_STRATEGY"
    RISK_ANALYSIS = "RISK_ANALYSIS"
    CODEBASE_EXPLANATION = "CODEBASE_EXPLANATION"
    RELEASE_READINESS = "RELEASE_READINESS"
    CREATOR_OS_CERTIFICATION = "CREATOR_OS_CERTIFICATION"
    RUNTIME_CONTROL = "RUNTIME_CONTROL"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class DeveloperAgentRequest:
    """Natural-language developer request plus optional architecture context."""

    question: str
    topic: str | None = None
    phase: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class DeveloperAgentSource:
    """Read-only architecture/development source used by Developer Agent."""

    source_type: str
    name: str
    summary: str
    confidence: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeveloperAgentEvidence:
    """Traceable evidence supporting an advisory Developer Agent response."""

    source: str
    summary: str
    evidence_type: str = "architecture_metadata"
    confidence: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeveloperAgentRecommendation:
    """Advisory development recommendation. It is never executable directly."""

    title: str
    detail: str = ""
    priority: str = "NORMAL"
    source: str = "DeveloperAgentService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeveloperAgentTool:
    """Read-only architecture capability available to Developer Agent."""

    name: str
    source_name: str
    context_field: str
    intents: tuple[DeveloperAgentIntent, ...]
    read_only: bool = True
    allows_command_execution: bool = False
    allows_file_mutation: bool = False
    allows_runtime_mutation: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeveloperAgentToolRequest:
    """Selected read-only tool invocation for one Developer Agent request."""

    tool: DeveloperAgentTool
    request: DeveloperAgentRequest
    intent: DeveloperAgentIntent
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeveloperAgentToolResult:
    """Structured read-only architecture tool result."""

    tool: DeveloperAgentTool
    success: bool
    result: Any | None = None
    warning: str | None = None
    source: DeveloperAgentSource | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeveloperAgentToolRegistry:
    """Provider-neutral map from Developer Agent intents to read-only sources."""

    tools: tuple[DeveloperAgentTool, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)

    def tools_for_intent(
        self,
        intent: DeveloperAgentIntent,
    ) -> tuple[DeveloperAgentTool, ...]:
        return tuple(tool for tool in self.tools if intent in tool.intents)


@dataclass(frozen=True)
class DeveloperAgentContext:
    """Aggregated read-only architecture/development context."""

    intent: DeveloperAgentIntent = DeveloperAgentIntent.UNKNOWN
    architecture_context: Mapping[str, Any] = field(default_factory=dict)
    roadmap_context: Mapping[str, Any] = field(default_factory=dict)
    compatibility_context: Mapping[str, Any] = field(default_factory=dict)
    test_context: Mapping[str, Any] = field(default_factory=dict)
    release_context: Mapping[str, Any] = field(default_factory=dict)
    tool_results: tuple[DeveloperAgentToolResult, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeveloperAgentResponse:
    """Structured advisory response returned by Developer Agent."""

    request: DeveloperAgentRequest
    intent: DeveloperAgentIntent
    answer_text: str
    context: DeveloperAgentContext = field(default_factory=DeveloperAgentContext)
    sources: tuple[DeveloperAgentSource, ...] = ()
    evidence: tuple[DeveloperAgentEvidence, ...] = ()
    recommendations: tuple[DeveloperAgentRecommendation, ...] = ()
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    confidence: float = 0.0
    suggested_follow_up_questions: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
