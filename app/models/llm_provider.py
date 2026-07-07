"""Provider-neutral LLM request and response models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True)
class LLMMessage:
    """Provider-neutral chat message."""

    role: str
    content: str
    name: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMToolCall:
    """Future-compatible provider-neutral LLM tool call request."""

    tool_call_id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMToolResult:
    """Future-compatible provider-neutral LLM tool result."""

    tool_call_id: str
    name: str
    result: Any | None = None
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMUsage:
    """Provider-neutral token/usage metadata."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMProviderConfig:
    """Provider-neutral LLM provider configuration."""

    provider_name: str = "null"
    model_name: str = "null-model"
    temperature: float = 0.0
    max_output_tokens: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMConversation:
    """Provider-neutral conversation history for LLM prompt construction."""

    messages: tuple[LLMMessage, ...] = ()
    conversation_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMRequest:
    """Provider-neutral LLM generation request."""

    messages: tuple[LLMMessage, ...]
    structured_context: Mapping[str, Any] = field(default_factory=dict)
    provider_name: str | None = None
    model_name: str | None = None
    conversation: LLMConversation | None = None
    tool_calls: tuple[LLMToolCall, ...] = ()
    tool_results: tuple[LLMToolResult, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class LLMResponse:
    """Provider-neutral LLM generation response."""

    response_text: str
    provider_name: str = "unknown"
    model_name: str = "unknown"
    usage: LLMUsage = field(default_factory=LLMUsage)
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    tool_calls: tuple[LLMToolCall, ...] = ()
    tool_results: tuple[LLMToolResult, ...] = ()
    raw_provider_metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMProviderResult:
    """Wrapper for provider execution metadata and response."""

    request: LLMRequest
    response: LLMResponse | None = None
    success: bool = True
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    provider_name: str = "unknown"
    model_name: str = "unknown"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)
