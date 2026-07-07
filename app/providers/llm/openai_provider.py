"""OpenAI-backed implementation of the provider-neutral LLM interface."""

from __future__ import annotations

import os
from typing import Any

from app.config import settings
from app.models.llm_provider import (
    LLMProviderConfig,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)
from app.providers.llm.base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    """Provider-neutral adapter over the existing OpenAI SDK configuration."""

    def __init__(
        self,
        config: LLMProviderConfig | None = None,
        *,
        client: Any | None = None,
        api_key: str | None = None,
    ) -> None:
        resolved_config = config or LLMProviderConfig(
            provider_name="openai",
            model_name=os.getenv(
                "OPENAI_CHAT_MODEL",
                os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            ),
            temperature=0.2,
            max_output_tokens=500,
        )
        super().__init__(resolved_config)
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.client = client

    @property
    def is_configured(self) -> bool:
        return bool(self.client or self.api_key)

    def generate_response(self, request: LLMRequest) -> LLMResponse:
        if not self.is_configured:
            return LLMResponse(
                response_text="",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
                errors=("OpenAIProvider is not configured.",),
                raw_provider_metadata={"external_api_called": False},
                metadata={
                    "provider_neutral": True,
                    "external_api_called": False,
                    "configured": False,
                },
            )

        try:
            client = self.client or self._build_client()
            response = client.chat.completions.create(
                model=request.model_name or self.config.model_name,
                messages=self._messages(request),
                temperature=self.config.temperature,
                max_tokens=self.config.max_output_tokens,
            )
            text = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            return LLMResponse(
                response_text=text.strip(),
                provider_name=self.config.provider_name,
                model_name=request.model_name or self.config.model_name,
                usage=LLMUsage(
                    input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                    output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                    total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
                    metadata={"source": "openai_usage"},
                ),
                raw_provider_metadata={
                    "external_api_called": True,
                    "provider": "openai",
                    "model": request.model_name or self.config.model_name,
                },
                metadata={
                    "provider_neutral": True,
                    "external_api_called": True,
                    "configured": True,
                },
            )
        except Exception as exc:
            return LLMResponse(
                response_text="",
                provider_name=self.config.provider_name,
                model_name=request.model_name or self.config.model_name,
                errors=(f"OpenAIProvider failed safely: {exc}",),
                raw_provider_metadata={"external_api_called": True},
                metadata={
                    "provider_neutral": True,
                    "external_api_called": True,
                    "configured": True,
                },
            )

    def _build_client(self) -> Any:
        from openai import OpenAI

        self.client = OpenAI(api_key=self.api_key)
        return self.client

    def _messages(self, request: LLMRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if request.conversation is not None:
            messages.extend(
                {"role": message.role, "content": message.content}
                for message in request.conversation.messages
            )
        messages.extend(
            {"role": message.role, "content": message.content}
            for message in request.messages
        )
        return messages

