"""Base interface for provider-neutral LLM integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.llm_provider import LLMProviderConfig, LLMRequest, LLMResponse


class BaseLLMProvider(ABC):
    """Replaceable LLM provider boundary.

    Implementations must not mutate Creator OS business state through this
    interface. Provider-specific execution belongs behind concrete providers.
    """

    def __init__(self, config: LLMProviderConfig | None = None) -> None:
        self.config = config or LLMProviderConfig()

    @abstractmethod
    def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Generate a natural-language response for structured context."""

