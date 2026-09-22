"""Versioned textual identity authority for migrated creator generation paths."""

from __future__ import annotations

from dataclasses import dataclass


CANONICAL_IDENTITY_POLICY_ID = "canonical_ava_identity"
CANONICAL_IDENTITY_POLICY_VERSION = "v1"


@dataclass(frozen=True)
class CanonicalCreatorIdentityPolicy:
    creator_profile_id: int
    policy_id: str
    policy_version: str
    reference_authority: str
    appearance_continuity: str
    hair_continuity: str
    bust_continuity: str
    body_continuity: str
    skin_continuity: str
    facial_continuity: str
    facial_naturalism_continuity: str

    @property
    def premium_render_identity_opening(self) -> str:
        return "\n".join((
            self.reference_authority,
            self.appearance_continuity,
            self.hair_continuity,
        ))

    @property
    def premium_render_body_identity(self) -> str:
        return "\n".join((self.bust_continuity, self.body_continuity, self.skin_continuity))

    @property
    def planner_identity_summary(self) -> str:
        return (
            "same face, hair, body, bust size, same waist-to-hip proportions, "
            "same natural sun-kissed skin tone"
        )


_AVA_POLICY = CanonicalCreatorIdentityPolicy(
    creator_profile_id=2,
    policy_id=CANONICAL_IDENTITY_POLICY_ID,
    policy_version=CANONICAL_IDENTITY_POLICY_VERSION,
    reference_authority=(
        "Use the reference image as the identity, face, hair, skin-tone, body-size, "
        "body-shape, and bust-size source of truth only."
    ),
    appearance_continuity=(
        "Preserve the exact same woman, face, long dark loose hair, same natural sun-kissed "
        "skin tone as the reference image, body size, body weight, and recognizable silhouette "
        "from the reference image."
    ),
    hair_continuity="\n".join((
        "Hair must be worn down: soft center part or natural side part, smooth flat natural top, loose flowing dark hair lying over her shoulders or down her back.",
        "Keep the scalp area natural and low-profile, with no lifted tied hairstyle and no tall hair shape.",
        "Do not create a bun, hairbun, topknot, ponytail, updo, tied-up hair, piled hair, messy crown, lifted hair knot, or any clump of hair above the scalp.",
        "The top of her hair must remain smooth, flat, natural, and low-profile, with no raised tied silhouette.",
    )),
    bust_continuity="\n".join((
        "Her breasts must remain visibly large natural D-cup breasts in the generated image, with full D-cup breast volume, full upper and lower breast fullness, rounded natural breast shape, visible bust projection, and natural cleavage when clothing or framing allows it.",
        "Do not reduce breast size. Do not make her smaller-busted. Do not flatten her chest. Do not make her appear B-cup or small-chested.",
    )),
    body_continuity=(
        "Preserve her feminine hourglass body, same waist-to-hip proportions, hip width, thigh "
        "proportions, shoulder width, and bust-to-waist ratio."
    ),
    skin_continuity=(
        "Preserve the reference skin tone exactly across face, chest, arms, waist, hips, and legs "
        "when visible. Keep it natural, even, sun-kissed, and photorealistic without making her "
        "darker, changing undertone, changing ethnicity, or making her look like a different person."
    ),
    facial_continuity=(
        "Preserve her exact facial identity, facial structure, eyes, nose, lips, jawline, cheekbones, "
        "and natural facial proportions from the reference image."
    ),
    facial_naturalism_continuity=(
        "Preserve Ava's exact facial identity, facial anatomy, proportions, and recognizable features "
        "from the canonical reference image."
    ),
)


def canonical_creator_identity_policy(creator_profile_id: int) -> CanonicalCreatorIdentityPolicy:
    """Return the registered policy; never silently substitute another creator."""
    if int(creator_profile_id) != _AVA_POLICY.creator_profile_id:
        raise ValueError(f"No canonical textual identity policy is registered for creator profile {creator_profile_id}.")
    return _AVA_POLICY
