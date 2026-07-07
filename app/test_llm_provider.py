from __future__ import annotations

import unittest

from app.models.llm_provider import (
    LLMConversation,
    LLMMessage,
    LLMProviderConfig,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolResult,
)
from app.providers.llm.base import BaseLLMProvider
from app.providers.llm.null_provider import NullLLMProvider
from app.providers.llm.openai_provider import OpenAIProvider


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.calls = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "OpenAIResponse",
            (),
            {
                "choices": (
                    type(
                        "Choice",
                        (),
                        {
                            "message": type(
                                "Message",
                                (),
                                {"content": "Mocked OpenAI answer."},
                            )()
                        },
                    )(),
                ),
                "usage": type(
                    "Usage",
                    (),
                    {
                        "prompt_tokens": 10,
                        "completion_tokens": 4,
                        "total_tokens": 14,
                    },
                )(),
            },
        )()


def test_llm_provider_models_can_be_created() -> None:
    request = LLMRequest(
        messages=(
            LLMMessage(role="system", content="Answer from context."),
            LLMMessage(role="user", content="What should I do today?"),
        ),
        structured_context={"intent": "DAILY_PRIORITIES"},
        provider_name="test",
        model_name="test-model",
        conversation=LLMConversation(
            messages=(LLMMessage(role="assistant", content="Earlier answer."),),
        ),
        tool_calls=(
            LLMToolCall(
                tool_call_id="tool-1",
                name="business_optimization_snapshot",
                arguments={"read_only": True},
            ),
        ),
        tool_results=(
            LLMToolResult(
                tool_call_id="tool-1",
                name="business_optimization_snapshot",
                result={"health": "HEALTHY"},
            ),
        ),
    )

    assert request.messages[0].role == "system"
    assert request.conversation.messages[0].content == "Earlier answer."
    assert request.structured_context["intent"] == "DAILY_PRIORITIES"
    assert request.tool_calls[0].name == "business_optimization_snapshot"
    assert request.tool_results[0].result == {"health": "HEALTHY"}


def test_base_provider_interface_exists() -> None:
    assert hasattr(BaseLLMProvider, "generate_response")


def test_openai_provider_implements_base_provider_and_uses_client() -> None:
    client = FakeOpenAIClient()
    provider = OpenAIProvider(
        LLMProviderConfig(provider_name="openai", model_name="gpt-test"),
        client=client,
    )
    request = LLMRequest(
        messages=(LLMMessage(role="user", content="Summarize priorities."),),
        structured_context={"intent": "DAILY_PRIORITIES"},
        conversation=LLMConversation(
            messages=(LLMMessage(role="assistant", content="Earlier context."),),
        ),
    )

    response = provider.generate_response(request)

    assert isinstance(provider, BaseLLMProvider)
    assert response.response_text == "Mocked OpenAI answer."
    assert response.provider_name == "openai"
    assert response.model_name == "gpt-test"
    assert response.usage.total_tokens == 14
    assert response.metadata["external_api_called"] is True
    assert len(client.calls) == 1
    assert client.calls[0]["messages"][0]["content"] == "Earlier context."


def test_null_provider_returns_deterministic_output_without_external_api() -> None:
    provider = NullLLMProvider(
        LLMProviderConfig(provider_name="null-test", model_name="null-model-test")
    )
    request = LLMRequest(
        messages=(LLMMessage(role="user", content="What should I do today?"),),
        structured_context={
            "intent": "DAILY_PRIORITIES",
            "sources": ("BusinessOptimizationService",),
            "recommended_actions": ("Publish Products awaiting Media Links",),
        },
    )

    first = provider.generate_response(request)
    second = provider.generate_response(request)

    assert isinstance(first, LLMResponse)
    assert first.response_text == second.response_text
    assert first.provider_name == "null-test"
    assert first.model_name == "null-model-test"
    assert first.metadata["external_api_called"] is False
    assert first.raw_provider_metadata["external_api_called"] is False
    assert first.raw_provider_metadata["request_context"]["intent"] == "DAILY_PRIORITIES"
    assert first.usage.total_tokens > 0


class LLMProviderTest(unittest.TestCase):
    def test_llm_provider_models_can_be_created(self) -> None:
        test_llm_provider_models_can_be_created()

    def test_base_provider_interface_exists(self) -> None:
        test_base_provider_interface_exists()

    def test_openai_provider_implements_base_provider_and_uses_client(self) -> None:
        test_openai_provider_implements_base_provider_and_uses_client()

    def test_null_provider_returns_deterministic_output_without_external_api(self) -> None:
        test_null_provider_returns_deterministic_output_without_external_api()
