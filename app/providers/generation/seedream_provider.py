"""Seedream generation provider adapters."""

from __future__ import annotations

from app.models.generation_engine import GenerationType
from app.providers.generation.base import ProviderCapabilities, WaveSpeedProviderBase


class Seedream45Provider(WaveSpeedProviderBase):
    provider_id = "seedream_4_5"
    display_name = "ByteDance Seedream 4.5 Edit"
    endpoint = "https://api.wavespeed.ai/api/v3/bytedance/seedream-v4.5/edit"
    capabilities = ProviderCapabilities(
        supported_generation_types=(GenerationType.IMAGE_TO_IMAGE.value,),
        supports_images=True,
        supports_video=False,
        supports_cancel=False,
        max_images=1,
        metadata={"model": "seedream-v4.5/edit"},
    )


class Seedream50LiteProvider(WaveSpeedProviderBase):
    provider_id = "seedream_5_0_lite"
    display_name = "ByteDance Seedream 5.0 Lite Edit"
    endpoint = "https://api.wavespeed.ai/api/v3/bytedance/seedream-v5.0-lite/edit"
    capabilities = ProviderCapabilities(
        supported_generation_types=(GenerationType.IMAGE_TO_IMAGE.value,),
        supports_images=True,
        supports_video=False,
        supports_cancel=False,
        max_images=1,
        metadata={"model": "seedream-v5.0-lite/edit"},
    )
