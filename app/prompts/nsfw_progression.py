from app.prompts.shot_types import SHOT_TYPES


def build_nsfw_progression_instruction(prompt_count: int = 10) -> str:
    return f"""
AUTOMATIC FULL NSFW EVOLUTION MODE (HIGHEST PRIORITY - OVERRIDES ALL OTHER RULES):

For Spicy/Premium mode when the reference is partially nude (topless + thong/panties), generate a clear, strong erotic progression story across all {prompt_count} prompts.

Progression sequence (spread gradually across the batch):
1. Very close to reference: seated topless in black thong on wooden floor, similar pose
2. More sensual: hands on breasts, squeezing, playing with nipples
3. Touching lower body: hand between legs, rubbing over panties, visible wet spot
4. Progressive removal: sliding panties down thighs, partial removal
5. Full removal: panties off, full nude, legs spreading/opening
6. Explicit self-pleasure: fingers rubbing clit, fingering, masturbation poses
7. Peak pleasure: arched back, eyes closed in ecstasy, biting lip, moaning expressions, etc.

MANDATORY RULES:
- Use the reference image for identity, face, hair, skin tone, body shape, and full natural D-cup breasts only unless the user explicitly asks for same-setting continuation.
- Do not copy the reference background, room, boat, dock, lake, railing, furniture, lighting, outfit, pose, or props unless explicitly requested.
- Never add clothing or go backwards in nudity level.
- Perfect identity, face, long dark hair, same natural sun-kissed skin tone as the reference image, full natural D-cup breasts with visible nipples in every prompt.
- Increase explicitness and intimacy steadily across the batch.
- Use natural, sensual, private creator-moment language.
"""


def build_premium_shot_type_context():
    formatted_shot_types = "\n".join(
        f"- {shot_type}" for shot_type in SHOT_TYPES
    )

    return f"""
SHOT INTELLIGENCE:
Use a natural mix of the following shot types and adapt them to the NSFW progression:

{formatted_shot_types}

Vary poses, framing (close-medium to upper-thigh), camera angles, and energy naturally.
"""


def build_nsfw_photoshoot_escalation(reference_context: str, prompt_count: int = 10) -> str:
    """Builds a high-priority NSFW escalation instruction for photoshoot sessions.
    It reads the provided reference_context (from vision analysis of the actual image)
    to determine the starting nudity/coverage/pose/environment state, then instructs
    gradual explicit progression while locking the environment.
    """
    ctx = (reference_context or "").strip() or "the uploaded reference image"

    return f"""
AUTOMATIC FULL NSFW EVOLUTION MODE (HIGHEST PRIORITY - OVERRIDES ALL OTHER RULES):

The source reference image context (analyzed from the actual passed-in image) is:

{ctx}

Use the above context to determine the woman's identity, body, bust size, coverage/nudity state, and pose at the start. Do not treat the reference environment as mandatory unless the user explicitly asks for same-setting continuation.

Generate a clear, strong, gradual erotic progression across all {prompt_count} prompts, beginning from precisely that starting state in the reference.

Progression sequence (adapt the starting step to match the reference's actual state, then escalate naturally):
1. Start close to the reference identity/body/coverage state: same woman, same body, same clothing/coverage level (or nudity level), while following the user's requested setting if one is provided.
2. Increase sensuality: hands on breasts / squeezing / playing with nipples (when reaching or past topless).
3. Touching lower body: hand between legs, rubbing over panties/thong, visible wet spot or arousal.
4. Progressive removal: sliding panties/thong down thighs, partial removal, increasing exposure.
5. Full removal: panties off, fully nude, legs opening/spreading.
6. Explicit intimate self-touch: fingers rubbing clit, fingering, masturbation poses.
7. Peak pleasure: arched back, eyes closed in ecstasy, biting lip, moaning expressions, intense body responses, various intimate angles.

MANDATORY RULES (apply to every prompt in the batch):
- Do not copy the reference environment, background, floor, walls, lighting, boat, dock, lake, railings, furniture, room, or props unless the user explicitly asks for same-setting continuation.
- If the user asks for shower, bathroom, bedroom, hotel, couch, pool, city, beach, or any non-boat scene, do not include boat, lake, dock, marina, railing, or outdoor natural-water elements from the reference image.
- Never revert to more clothing or lower the nudity/explicitness level compared to prior steps in the sequence.
- Perfect continuity of identity: same woman, same face, same hair, same natural sun-kissed skin tone as the reference image, same body, same full natural D-cup breasts (with visible nipples when exposed).
- Increase explicitness and intimacy **steadily and gradually** across the entire batch.
- Use natural, sensual, private-creator-moment language.
- The entire batch must read as one continuous private escalating moment captured in the same place.

If the reference context shows her already quite exposed or nude, begin the ladder at that point and continue escalating into self-pleasure and peak.
If less nude, still progress toward full explicit acts, but do so in believable gradual steps.

This NSFW evolution instruction has highest priority for the photoshoot.
"""
