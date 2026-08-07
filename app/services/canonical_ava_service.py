"""Single provider-neutral definition of canonical Ava.

This service owns creator identity only. Creative workflows continue to own the
scene, activity, wardrobe, pose, location, lighting, expression, and editorial
variation surrounding Ava.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalAvaDefinition:
    """Immutable identity contract that workflows may add to creative intent."""

    canonical_identity: str
    facial_identity: str
    hair: str
    skin_tone: str
    body_proportions: str
    bust_size: str
    hourglass_definition: str
    visual_recipe: str
    framing_philosophy: str
    provider_identity_instructions: str
    render_identity_rules: str

    def as_prompt_context(self) -> str:
        fields = (
            ("Canonical identity", self.canonical_identity),
            ("Facial identity", self.facial_identity),
            ("Hair", self.hair),
            ("Skin tone", self.skin_tone),
            ("Body proportions", self.body_proportions),
            ("Bust size", self.bust_size),
            ("Hourglass definition", self.hourglass_definition),
            ("Visual recipe", self.visual_recipe),
            ("Framing philosophy", self.framing_philosophy),
            ("Provider identity instructions", self.provider_identity_instructions),
            ("Render identity rules", self.render_identity_rules),
        )
        return "\n".join(f"{label}: {value}" for label, value in fields)


class CanonicalAvaService:
    """Authoritative Ava identity definition, extracted from Inspire Me."""

    def definition(self) -> CanonicalAvaDefinition:
        return CanonicalAvaDefinition(
            canonical_identity=(
                "Use the active canonical reference image as the source of truth for "
                "Ava's identity and body only. Preserve the exact same woman and her "
                "recognizable creator aesthetic."
            ),
            facial_identity=(
                "Preserve Ava's exact face, facial structure, eyes, nose, lips, "
                "jawline, cheekbones, hairline, and natural facial proportions. Keep "
                "her face photorealistic, natural, anatomically correct, and recognizable."
            ),
            hair=(
                "Preserve long dark loose hair, worn down with a soft center or natural "
                "side part, a smooth flat natural top, and loose hair over her shoulders "
                "or down her back. Do not introduce a bun, ponytail, updo, topknot, tied, "
                "piled, or unnaturally tall hair silhouette."
            ),
            skin_tone=(
                "Preserve the same natural sun-kissed skin tone and undertone across all "
                "visible skin. Do not wash it out, over-tan it, alter ethnicity, or change "
                "the reference complexion."
            ),
            body_proportions=(
                "Preserve Ava's body size, body weight, recognizable silhouette, shoulder "
                "width, hip width, thigh proportions, and bust-to-waist ratio with realistic anatomy."
            ),
            bust_size=(
                "Preserve a visibly full natural D-cup bust with full upper and lower "
                "volume, rounded natural shape, projection, and natural cleavage when the "
                "creative intent and framing allow it. Never reduce, flatten, or minimize it."
            ),
            hourglass_definition=(
                "Preserve Ava's feminine hourglass body and the same waist-to-hip proportions."
            ),
            visual_recipe=(
                "Render Ava as a photorealistic creator with natural skin and hair texture, "
                "believable anatomy, realistic proportions, and an authentic non-uncanny appearance."
            ),
            framing_philosophy=(
                "Ava remains the unmistakable visual subject. Prefer creator-forward framing "
                "that keeps identity and defining body cues legible, keeps her full face and "
                "head intact with clean headroom, and makes the environment supportive rather "
                "than dominant. Creative intent may explicitly require a wider composition."
            ),
            provider_identity_instructions=(
                "For image-edit providers, send the canonical reference as the identity/body "
                "reference and express this contract as direct natural-language continuity "
                "instructions without model weighting syntax."
            ),
            render_identity_rules=(
                "The reference controls identity, face, hair, skin tone, body shape, body "
                "proportions, and bust size only. The creative direction controls scene, "
                "activity, wardrobe, pose, location, lighting, expression, and editorial "
                "variation. Never inherit those creative elements from the reference image."
            ),
        )

    def prompt_context(self) -> str:
        return self.definition().as_prompt_context()
