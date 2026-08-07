"""Provider-neutral Video Studio domain contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class VideoProviderCapability:
    provider_id: str
    display_name: str
    model_family: str
    generation_types: tuple[str, ...]
    input_media_types: tuple[str, ...]
    min_native_duration: int
    max_native_duration: int
    supported_resolutions: tuple[str, ...]
    supported_aspect_ratios: tuple[str, ...]
    native_audio: bool
    audio_on_extension: bool
    video_extension: bool
    video_edit: bool
    text_to_video: bool
    native_cancellation: bool
    web_search: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)


SEEDANCE_20_CAPABILITY = VideoProviderCapability(
    provider_id="wavespeed_seedance_2_0",
    display_name="Seedance 2.0 (WaveSpeed)",
    model_family="seedance-2.0",
    generation_types=("image_to_video", "video_extend"),
    input_media_types=("image", "video"),
    min_native_duration=4,
    max_native_duration=15,
    supported_resolutions=("480p", "720p", "1080p", "4k"),
    supported_aspect_ratios=("adaptive", "16:9", "9:16", "4:3", "3:4", "1:1", "21:9"),
    native_audio=True,
    audio_on_extension=True,
    video_extension=True,
    video_edit=False,
    text_to_video=False,
    native_cancellation=False,
    web_search=True,
    metadata={
        "image_to_video_endpoint": "bytedance/seedance-2.0/image-to-video",
        "video_extend_endpoint": "bytedance/seedance-2.0/video-extend",
        "extension_output": "cumulative",
        "seed_supported": False,
    },
)


class VideoProviderCapabilityService:
    def __init__(self, capabilities=None):
        values = capabilities or (SEEDANCE_20_CAPABILITY,)
        self._values = {value.provider_id: value for value in values}

    def require(self, provider_id: str) -> VideoProviderCapability:
        try:
            return self._values[provider_id]
        except KeyError as error:
            raise ValueError(f"Unsupported video provider: {provider_id}") from error

    def list(self) -> tuple[VideoProviderCapability, ...]:
        return tuple(self._values.values())
