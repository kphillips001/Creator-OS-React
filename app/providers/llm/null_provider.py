"""Deterministic local LLM provider for tests and safe fallback."""

from __future__ import annotations

from app.models.llm_provider import (
    LLMProviderConfig,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)
from app.providers.llm.base import BaseLLMProvider


class NullLLMProvider(BaseLLMProvider):
    """Local deterministic provider that never calls external APIs."""

    def __init__(self, config: LLMProviderConfig | None = None) -> None:
        super().__init__(
            config
            or LLMProviderConfig(
                provider_name="null",
                model_name="null-deterministic-v1",
                temperature=0.0,
            )
        )

    def generate_response(self, request: LLMRequest) -> LLMResponse:
        intent = str(request.structured_context.get("intent") or "UNKNOWN")
        question = self._user_question(request)
        source_names = tuple(request.structured_context.get("sources") or ())
        action_titles = tuple(request.structured_context.get("recommended_actions") or ())
        action_text = (
            f" Recommended next action: {action_titles[0]}."
            if action_titles
            else " No recommended action was available."
        )
        source_text = (
            f" Sources: {', '.join(str(source) for source in source_names)}."
            if source_names
            else " Sources: none."
        )
        response_text = (
            f"[null-llm] {intent}: {question}.{action_text}{source_text}"
        )
        input_tokens = sum(len(message.content.split()) for message in request.messages)
        output_tokens = len(response_text.split())
        return LLMResponse(
            response_text=response_text,
            provider_name=self.config.provider_name,
            model_name=self.config.model_name,
            usage=LLMUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                metadata={"deterministic": True},
            ),
            warnings=("NullLLMProvider used deterministic local output.",),
            raw_provider_metadata={
                "external_api_called": False,
                "request_context": dict(request.structured_context),
            },
            metadata={
                "provider_neutral": True,
                "deterministic": True,
                "external_api_called": False,
            },
        )

    def _user_question(self, request: LLMRequest) -> str:
        for message in reversed(request.messages):
            if message.role == "user":
                return message.content
        return ""

