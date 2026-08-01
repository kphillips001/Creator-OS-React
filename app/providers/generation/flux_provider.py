"""Flux generation provider adapter placeholder."""

from __future__ import annotations

from app.models.generation_engine import GenerationRequest, GenerationResult, GenerationType
from app.providers.generation.base import (
    GenerationProvider,
    GenerationProviderError,
    ProviderCapabilities,
    ProviderMetadata,
    ProviderPollResult,
    ProviderSubmission,
)


class FluxProvider(GenerationProvider):
    provider_id = "flux"
    display_name = "Flux"
    capabilities = ProviderCapabilities(
        supported_generation_types=(
            GenerationType.TEXT_TO_IMAGE.value,
            GenerationType.IMAGE_TO_IMAGE.value,
        ),
        supports_images=True,
        supports_video=False,
        supports_cancel=False,
        max_images=1,
        metadata={"migration_status": "placeholder_no_wavespeed_implementation_found"},
    )

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id=self.provider_id,
            display_name=self.display_name,
            provider_family="unconfigured",
            endpoint=None,
            enabled=False,
            capabilities=self.capabilities,
            metadata={
                "lifecycle": "FUTURE",
                "reason": "No Flux provider implementation was present in Wavespeed_App.",
            },
        )

    def validate_request(self, request: GenerationRequest) -> None:
        raise GenerationProviderError("Flux provider is registered as a disabled placeholder.")

    def submit_generation(self, request: GenerationRequest) -> ProviderSubmission:
        self.validate_request(request)

    def poll_status(self, submission: ProviderSubmission) -> ProviderPollResult:
        raise GenerationProviderError("Flux provider is registered as a disabled placeholder.")

    def retrieve_result(
        self,
        request: GenerationRequest,
        submission: ProviderSubmission,
        poll_result: ProviderPollResult,
    ) -> GenerationResult:
        raise GenerationProviderError("Flux provider is registered as a disabled placeholder.")

    def cancel_job(self, provider_request_id: str):
        return {"provider_request_id": provider_request_id, "cancel_supported": False}
