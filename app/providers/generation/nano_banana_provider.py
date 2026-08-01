"""Nano Banana generation provider adapters."""

from __future__ import annotations

from app.models.generation_engine import GenerationType
from app.providers.generation.base import ProviderCapabilities, WaveSpeedProviderBase


class NanoBananaProvider(WaveSpeedProviderBase):
    lifecycle = "COMPATIBILITY"
    provider_id = "nano_banana"
    display_name = "Google Nano Banana 2 Edit"
    endpoint = "https://api.wavespeed.ai/api/v3/google/nano-banana-2/edit"
    capabilities = ProviderCapabilities(
        supported_generation_types=(GenerationType.IMAGE_TO_IMAGE.value,),
        supports_images=True,
        supports_video=False,
        supports_cancel=False,
        max_images=1,
        metadata={"model": "nano-banana-2/edit"},
    )


class NanoBananaProProvider(WaveSpeedProviderBase):
    provider_id = "nano_banana_pro"
    display_name = "Google Nano Banana Pro Edit"
    endpoint = "https://api.wavespeed.ai/api/v3/google/nano-banana-pro/edit"
    capabilities = ProviderCapabilities(
        supported_generation_types=(GenerationType.IMAGE_TO_IMAGE.value,),
        supports_images=True,
        supports_video=False,
        supports_cancel=False,
        max_images=1,
        metadata={"model": "nano-banana-pro/edit"},
    )
