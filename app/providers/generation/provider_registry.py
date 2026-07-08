"""Generation provider registry."""

from __future__ import annotations

from typing import Mapping

from app.models.generation_engine import GenerationRequest, GenerationResult
from app.providers.generation.base import GenerationProvider, ProviderMetadata
from app.providers.generation.flux_provider import FluxProvider
from app.providers.generation.nano_banana_provider import NanoBananaProProvider, NanoBananaProvider
from app.providers.generation.seedream_provider import Seedream45Provider, Seedream50LiteProvider
from app.providers.generation.wan_provider import WanImageEditProvider


class ProviderRegistry:
    """Provider lookup boundary for the Generation Engine."""

    def __init__(self, providers: Mapping[str, GenerationProvider] | None = None):
        self._providers: dict[str, GenerationProvider] = {}
        for provider in (providers or {}).values():
            self.register(provider)

    def register(self, provider: GenerationProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> GenerationProvider | None:
        return self._providers.get(str(provider_id))

    def require(self, provider_id: str) -> GenerationProvider:
        provider = self.get(provider_id)
        if provider is None:
            raise KeyError(f"Generation Provider not registered: {provider_id}")
        return provider

    def metadata(self) -> tuple[ProviderMetadata, ...]:
        return tuple(provider.metadata() for provider in self._providers.values())

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(self._providers)

    def dispatch(self, request: GenerationRequest) -> GenerationResult:
        provider = self.require(request.provider_id)
        if hasattr(provider, "execute"):
            return provider.execute(request)
        return provider.dispatch(request)


def create_default_registry(**provider_kwargs) -> ProviderRegistry:
    providers = (
        NanoBananaProvider(**provider_kwargs),
        NanoBananaProProvider(**provider_kwargs),
        WanImageEditProvider(**provider_kwargs),
        Seedream45Provider(**provider_kwargs),
        Seedream50LiteProvider(**provider_kwargs),
        FluxProvider(),
    )
    return ProviderRegistry({provider.provider_id: provider for provider in providers})
