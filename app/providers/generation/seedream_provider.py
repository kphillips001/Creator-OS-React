"""Seedream generation provider adapters."""

from __future__ import annotations

from app.models.generation_engine import GenerationType
from app.models.render_policy import RenderPolicy
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

Image 2 is the immutable original Photoshoot seed. Use it as the foundational environment, styling, lighting, and visual-world anchor. Do not let later images override this foundation.

Image 3, when present, is only the latest valid approved shot. Use it for local pose, action, framing, and expression progression; it must not override Image 1 identity or Image 2's shoot foundation.

Image 1 controls identity. Image 2 anchors the shoot. Image 3 controls only local progression.
""".strip()

    def _render_prompt_text(self, request):
        if self._is_trusted_final_prompt(request):
            return str(request.prompt_text or "")
        prompt = super()._render_prompt_text(request)
        metadata = request.metadata or {}
        policy = self._render_policy(request)
        canonical = str(
            metadata.get("canonical_reference_image_url")
            or request.reference_asset_path
            or ""
        ).strip()
        continuity = str(
            metadata.get("photoshoot_continuity_reference_image_url") or ""
        ).strip()
        original_seed = str(
            metadata.get("original_photoshoot_seed_reference_image_url") or continuity
        ).strip()
        if (
            policy in {
                RenderPolicy.PHOTOSHOOT_SAFE,
                RenderPolicy.PHOTOSHOOT_PREMIUM,
                RenderPolicy.PHOTOSHOOT_EXPLICIT,
            }
            and canonical
            and continuity
            and original_seed
            and canonical != continuity
        ):
            return f"{prompt}\n\n{self.PHOTOSHOOT_REFERENCE_ROLE_GUIDANCE}"
        return prompt
