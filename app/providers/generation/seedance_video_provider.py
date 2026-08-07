"""WaveSpeed Seedance 2.0 video adapter using the canonical WaveSpeed transport."""
from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from app.models.generation_engine import GenerationRequest, GenerationResult
from app.providers.generation.base import (
    GenerationProviderError, ProviderCapabilities, WaveSpeedProviderBase,
)


class Seedance20VideoProvider(WaveSpeedProviderBase):
    provider_id = "wavespeed_seedance_2_0"
    display_name = "Seedance 2.0 (WaveSpeed)"
    image_to_video_endpoint = "https://api.wavespeed.ai/api/v3/bytedance/seedance-2.0/image-to-video"
    video_extend_endpoint = "https://api.wavespeed.ai/api/v3/bytedance/seedance-2.0/video-extend"
    endpoint = image_to_video_endpoint
    capabilities = ProviderCapabilities(
        supported_generation_types=("image_to_video", "video_extend"),
        supports_images=False, supports_video=True, supports_cancel=False,
        max_images=1, max_reference_images=1,
        metadata={"min_duration": 4, "max_duration": 15, "native_audio": True},
    )

    def validate_request(self, request: GenerationRequest) -> None:
        if request.generation_type not in self.capabilities.supported_generation_types:
            raise GenerationProviderError(f"Unsupported Seedance generation type: {request.generation_type}")
        if not str(request.prompt_text or "").strip():
            raise GenerationProviderError("Seedance prompt is required.")
        duration = int(request.metadata.get("duration") or 0)
        if duration < 4 or duration > 15:
            raise GenerationProviderError("Seedance duration must be between 4 and 15 seconds.")
        source = self._source(request)
        if not source:
            raise GenerationProviderError("Seedance requires an authoritative image or video source.")
        resolution = str(request.metadata.get("resolution") or "720p")
        if resolution not in {"480p", "720p", "1080p", "4k"}:
            raise GenerationProviderError(f"Unsupported Seedance resolution: {resolution}")
        if request.generation_type == "image_to_video":
            aspect = str(request.metadata.get("aspect_ratio") or "adaptive")
            if aspect not in {"adaptive", "16:9", "9:16", "4:3", "3:4", "1:1", "21:9"}:
                raise GenerationProviderError(f"Unsupported Seedance aspect ratio: {aspect}")
        self._api_key()

    def submit_generation(self, request: GenerationRequest):
        endpoint = self.video_extend_endpoint if request.generation_type == "video_extend" else self.image_to_video_endpoint
        previous = self.endpoint
        try:
            self.endpoint = endpoint
            return super().submit_generation(request)
        finally:
            self.endpoint = previous

    def build_payload(self, request: GenerationRequest) -> Mapping[str, object]:
        metadata = request.metadata
        payload: dict[str, object] = {
            "prompt": request.prompt_text.strip(),
            "duration": int(metadata["duration"]),
            "resolution": str(metadata.get("resolution") or "720p"),
            "generate_audio": bool(metadata.get("generate_audio", True)),
            "enable_web_search": bool(metadata.get("enable_web_search", False)),
        }
        if metadata.get("last_image"):
            payload["last_image"] = str(metadata["last_image"])
        if request.generation_type == "video_extend":
            payload["video"] = self._source(request)
        else:
            payload["image"] = self._provider_reference_value(self._source(request))
            aspect = str(metadata.get("aspect_ratio") or "adaptive")
            if aspect != "adaptive":
                payload["aspect_ratio"] = aspect
        return payload

    def retrieve_result(self, request, submission, poll_result) -> GenerationResult:
        result = super().retrieve_result(request, submission, poll_result)
        return replace(result, duration_seconds=float(request.metadata.get("duration") or 0),
                       image_metadata={}, generation_metadata={**result.generation_metadata,
                       "media_type": "video", "generation_type": request.generation_type})

    @staticmethod
    def _source(request: GenerationRequest) -> str:
        metadata = request.metadata or {}
        value = (metadata.get("input_video_url") if request.generation_type == "video_extend" else None) or metadata.get("reference_image_url") or metadata.get("provider_reference_url") or request.reference_asset_path
        return str(value or "").strip()
