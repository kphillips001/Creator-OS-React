"""Grok-powered concepts for the dedicated Explicit Content lane."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.creative_diversity_guidance import creative_diversity_guidance
from app.services.grok_anything_service import ask_grok_anything


@dataclass(frozen=True)
class ExplicitInspirationResult:
    hardcore: tuple[str, ...]
    softcore: tuple[str, ...]


class ExplicitInspirationService:
    def __init__(
        self,
        *,
        profile_loader: Callable[[str], dict] | None = None,
        text_generator: Callable[[str], str] | None = None,
    ) -> None:
        self.profile_loader = profile_loader or get_active_creator_profile
        self.text_generator = text_generator or ask_grok_anything

    def create_concepts(
        self,
        *,
        fanvue_account_id: int | str,
        count_per_tier: int = 5,
    ) -> ExplicitInspirationResult:
        count = max(1, min(int(count_per_tier or 5), 12))
        profile = self.profile_loader(str(fanvue_account_id))
        if not profile:
            raise LookupError("An active creator profile is required.")
        hardcore = self._generate_tier(
            tier="hardcore",
            count=count,
        )
        softcore = self._generate_tier(
            tier="softcore",
            count=count,
            avoid_overlap=hardcore,
        )
        return ExplicitInspirationResult(hardcore=hardcore, softcore=softcore)

    def _generate_tier(
        self,
        *,
        tier: str,
        count: int,
        avoid_overlap: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        prompt = self._build_prompt(
            tier=tier,
            count=count,
            avoid_overlap=avoid_overlap,
        )
        concepts = self._parse(self.text_generator(prompt))
        if len(concepts) < count:
            raise ValueError(f"Explicit inspiration returned too few usable {tier} concepts.")
        return concepts[:count]

    def _build_prompt(
        self,
        *,
        tier: str,
        count: int,
        avoid_overlap: tuple[str, ...] = (),
    ) -> str:
        diversity_section = creative_diversity_guidance(concept_count=count)
        output_contract = f"""OUTPUT CONTRACT
Exactly {count} lines. No numbering, bullets, headings, markdown, labels, or explanation.
Each line is one complete concept ready for the explicit tag enhancer.
Start directly with the scene or action. Do not include a creator name or identity description.
Do not invent biographical facts, relationships, possessions, properties, or history.
No disconnected keywords, captions, hashtags, or technical provider syntax.
Identity, reference-image continuity, body locks, and hair locks are added later by the canonical explicit prompt planner.
"""

        overlap_block = ""
        if avoid_overlap:
            listed = "\n".join(f"- {item}" for item in avoid_overlap)
            overlap_block = f"""
Do not repeat or lightly rephrase any of these already-generated concepts:
{listed}
"""

        if tier == "hardcore":
            return f"""You are the Explicit Content hardcore inspiration editor for Creator_OS.
This lane sells paid NSFW PPV content (Fanvue / OnlyFans style).

Create exactly {count} distinct HARDCORE visual concepts.
These will become image prompts for hardcore creator porn the buyer pays to unlock.

HARDCORE REQUIREMENTS (mandatory for every concept):
- Write direct sexual language. Use anatomical words when relevant: pussy, clit, labia, nipples,
  breasts, ass, asshole, cock-tease framing toward camera, fingers, etc.
- Full or near-full nudity is the default. If any clothing remains, it must be actively pulled aside,
  around ankles, bunched at hips, or otherwise failing to cover genitals and/or breasts.
- Every concept must include a clear sexual act or explicit sexual display, not just a sexy pose.
  Rotate across the set among acts such as:
  * legs spread / pussy fully visible and presented to camera
  * fingers spreading labia or rubbing clit
  * fingering / masturbation (one or two fingers, grinding, circling clit)
  * ass up / doggy presentation with pussy and/or asshole visible
  * kneeling open-mouth oral tease toward camera
  * riding / grinding a pillow, edge of bed, chair, or (only if natural) a realistic toy
  * oil / lube / wet arousal on breasts, stomach, inner thighs, or pussy
  * close-up genital-forward framing with face still readable when possible
- Describe arousal concretely when it fits: hard nipples, flushed skin, wet pussy, swollen clit,
  glistening juices, parted lips, heavy breathing body language.
- Keep photorealistic private-creator PPV energy: intimate, filthy, paid-for the viewer —
  not soft romance novel prose and not cartoon gonzo exaggeration.
- Each concept is one complete scene sentence (or two short sentences max) covering:
  environment, nudity/wardrobe failure state, exact sexual act or genital display, pose,
  camera/framing intent, lighting, and erotic intent toward the buyer.

VARIATION:
Vary location, sexual act, pose, lighting, and framing across the {count} concepts.
Do not make every concept the same "recline and tease" softcore beat.
At least half the concepts must show pussy clearly (spread, presented, or being touched).
At least two concepts should emphasize ass/pussy from behind or three-quarter rear.

HARD BANS FOR THIS HARDCORE LIST:
- No soft "blouse slipping off one shoulder" / "towel almost falling" as the peak of the concept
- No pure clothed or lingerie-only teaser concepts
- No softcore-only ideas in this list

{diversity_section}

{output_contract}
{overlap_block}""".strip()

        return f"""You are the Explicit Content softcore inspiration editor for Creator_OS.
This lane sells paid NSFW / suggestive premium content (Fanvue / OnlyFans style).

Create exactly {count} distinct SOFTCORE visual concepts.
These are sexy, erotic, and commercial — but NOT hardcore genital-sex acts.

SOFTCORE REQUIREMENTS (mandatory for every concept):
- Suggestive, erotic, premium creator energy the buyer wants to unlock.
- Nudity or near-nudity is allowed and often preferred: topless, sheer, panties pulled aside
  just enough to tease, robe open, towel slipping, lingerie half-off, wet shirt cling, etc.
- Focus on seduction, body language, wardrobe failure, teasing hands, arched back, hip tilt,
  cleavage, bare breasts with visible nipples, ass presentation, legs parted without explicit
  genital sex acts, bedroom eyes, and intimate camera distance.
- Use sensual but clear adult language. You may say bare breasts, nipples, ass, inner thighs,
  panties, thong, topless, nude — but do NOT describe fingering, spreading labia, wet pussy
  close-ups, asshole presentation, masturbation insertion, or oral sex acts.
- Softcore still sells: make each concept hot and specific, not vague "beautiful woman posing".
- Each concept is one complete scene sentence (or two short sentences max) covering:
  environment, wardrobe/undress state, teasing pose, lighting, framing, and erotic mood.

VARIATION:
Vary location, wardrobe state, pose, lighting, and framing across the {count} concepts.
Include a mix of topless, almost-nude, lingerie tease, and full-nude soft presentation without
hardcore sexual acts.

HARD BANS FOR THIS SOFTCORE LIST:
- No hardcore sexual acts (fingering, masturbation insertion, labia spreading, pussy close-up sex display)
- No disconnected keywords, captions, hashtags, or technical provider syntax
- Do not invent biographical facts, relationships, possessions, properties, or history

{diversity_section}

{output_contract}
{overlap_block}""".strip()

    @staticmethod
    def _parse(value: str) -> tuple[str, ...]:
        cleaned = []
        for line in str(value or "").splitlines():
            item = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
            if not item:
                continue
            # Drop accidental section labels if the model echoes them.
            if re.fullmatch(r"(?i)(?:hardcore|softcore)\s*:?", item):
                continue
            if item not in cleaned:
                cleaned.append(item)
        return tuple(cleaned)
