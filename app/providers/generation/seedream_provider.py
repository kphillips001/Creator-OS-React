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


class Seedream50ProProvider(WaveSpeedProviderBase):
    provider_id = "seedream_5_0_pro"
    display_name = "ByteDance Seedream 5.0 Pro Edit"
    endpoint = "https://api.wavespeed.ai/api/v3/bytedance/seedream-v5.0-pro/edit"
    capabilities = ProviderCapabilities(
        supported_generation_types=(GenerationType.IMAGE_TO_IMAGE.value,),
        supports_images=True,
        supports_video=False,
        supports_cancel=False,
        max_images=1,
        max_reference_images=10,
        metadata={"model": "seedream-v5.0-pro/edit"},
    )

    PHOTOSHOOT_REFERENCE_ROLE_GUIDANCE = """
REFERENCE GUIDANCE FOR THIS PHOTOSHOOT:
Image 1 is the canonical creator identity reference. Treat Image 1 as the authoritative source for the creator's exact identity and overall appearance, including facial identity, face shape, eyes, eyebrows, nose, lips, jawline, cheek structure, hairline, and skin tone. Preserve that creator exactly; do not reinterpret or replace her identity.

Image 2 is the latest approved Photoshoot image. Use Image 2 for the continuing pose, body position, wardrobe, location, lighting, composition, framing, camera angle, expression evolution, and the visual continuity of this Photoshoot. Do not use Image 2 to redefine the creator's facial identity.

Image 1 controls identity. Image 2 controls Photoshoot continuity.
""".strip()

    def _render_prompt_text(self, request):
        prompt = super()._render_prompt_text(request)
        metadata = request.metadata or {}
        workflow = str(metadata.get("workflow_type") or "").strip().lower()
        canonical = str(
            metadata.get("canonical_reference_image_url")
            or request.reference_asset_path
            or ""
        ).strip()
        continuity = str(
            metadata.get("photoshoot_continuity_reference_image_url") or ""
        ).strip()
        if workflow == "photoshoot" and canonical and continuity and canonical != continuity:
            return f"{prompt}\n\n{self.PHOTOSHOOT_REFERENCE_ROLE_GUIDANCE}"
        return prompt
