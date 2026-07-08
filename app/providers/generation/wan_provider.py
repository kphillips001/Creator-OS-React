"""WAN generation provider adapters."""

from __future__ import annotations

from app.models.generation_engine import GenerationType
from app.providers.generation.base import ProviderCapabilities, WaveSpeedProviderBase


class WanImageEditProvider(WaveSpeedProviderBase):
    provider_id = "wan_2_7_image_edit"
    display_name = "WAN 2.7 Image Edit"
    endpoint = "https://api.wavespeed.ai/api/v3/alibaba/wan-2.7/image-edit"
    capabilities = ProviderCapabilities(
        supported_generation_types=(GenerationType.IMAGE_TO_IMAGE.value,),
        supports_images=True,
        supports_video=False,
        supports_cancel=False,
        max_images=1,
        metadata={"model": "wan-2.7/image-edit"},
    )
