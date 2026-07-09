"""Canonical Wavespeed premium render-lock helpers."""

from __future__ import annotations

import hashlib


PREMIUM_RENDER_BODY_LOCK = """
FINAL REFERENCE BODY LOCK - NON-NEGOTIABLE:
Use the reference image as the identity, face, hair, skin-tone, body-size, body-shape, and bust-size source of truth only.
Preserve the exact same woman, face, long dark loose hair, same natural sun-kissed skin tone as the reference image, body size, body weight, and recognizable silhouette from the reference image.
Hair must be worn down: soft center part or natural side part, smooth flat natural top, loose flowing dark hair lying over her shoulders or down her back.
Keep the scalp area natural and low-profile, with no lifted tied hairstyle and no tall hair shape.
Do not create a bun, hairbun, topknot, ponytail, updo, tied-up hair, piled hair, messy crown, lifted hair knot, or any clump of hair above the scalp.
The top of her hair must remain smooth, flat, natural, and low-profile, with no raised tied silhouette.
Do NOT copy the reference image's setting, location, background, water, boat, dock, railings, trees, cabin, rocks, room, furniture, props, lighting, outfit, pose, or camera angle unless the written prompt explicitly asks for those exact elements.
The written prompt is the source of truth for the generated scene, wardrobe, nudity state, shower/pool/bedroom/hotel/indoor/outdoor setting, pose, lighting, and background.
If the written prompt asks for a shower, bathroom, bedroom, hotel, couch, pool, or any non-boat scene, do not include a boat, lake, dock, marina, railing, cabin, natural-water background, or outdoor boat-deck elements from the reference image.
If the written prompt asks for nude/topless/shower content, do not preserve clothing from the reference image.
Her breasts must remain visibly large natural D-cup breasts in the generated image, with full D-cup breast volume, full upper and lower breast fullness, rounded natural breast shape, visible bust projection, and natural cleavage when clothing or framing allows it.
Do not reduce breast size. Do not make her smaller-busted. Do not flatten her chest. Do not make her appear B-cup or small-chested.
Preserve her feminine hourglass body, same waist-to-hip proportions, hip width, thigh proportions, shoulder width, and bust-to-waist ratio.
Preserve the reference skin tone exactly across face, chest, arms, waist, hips, and legs when visible. Keep it natural, even, sun-kissed, and photorealistic without making her darker, changing undertone, changing ethnicity, or making her look like a different person.
MANDATORY FRAMING LOCK FOR WAN 2.7:
Use medium-close creator framing. The subject must be large in frame without being pressed against the image edges.
Use close-medium, waist-up, head-to-hips, head-to-upper-thigh, upper-thigh, or intimate seated portrait framing.
Make her face, upper body, torso, bust, waist, and hip angle visually dominant in the composition.
Keep her full face and full head inside the frame, with her smooth natural hair top visible and a little clean background space above her hair.
Leave visible empty background space above her hair. Keep her hair and forehead away from the top image edge.
If the composition cannot fit her face, smooth hair top, bust, waist, and hips at the requested crop distance, pull the camera back slightly.
Keep the camera close enough that her full natural D-cup bust, hourglass waist, and reference skin tone are obvious.
Keep the background secondary. The environment may be visible, but it must not become the main subject.
Reject wide bed shots, wide room shots, distant mattress compositions, distant full-body shots, scenery-dominant lake/pool/landscape shots, or any framing where the bed, furniture, room, water, or landscape is more visually important than her body.
Unless the prompt explicitly asks for a wide shot, do not create a wide shot.
Reject cropped-off forehead, missing top of head, face pressed against the top edge, hair touching the top border, or any composition that slices through her hair.
Reject tall hair shapes, lifted tied hair, piled hair, knot-like hair silhouettes, or large hair clumps above the scalp.
Do not crop out the body cues needed to preserve her D-cup bust, hourglass shape, reference skin tone, and recognizable facial identity.
Do not use side/rear all-fours angles that hide or minimize the bust; if using side/rear body orientation, keep the chest, bust, face, and upper torso still visible and prominent.
Preserve her exact facial identity, facial structure, eyes, nose, lips, jawline, cheekbones, smile shape, and natural facial proportions from the reference image.
Keep the face photorealistic, natural, anatomically correct, and consistent with the selected expression variation.
Avoid goofy, silly, cartoonish, distorted, uncanny, melted, asymmetrical, cross-eyed, or over-exaggerated facial expressions.
Avoid distorted mouth shape, strange teeth, warped lips, oversized tongue, misplaced tongue, or unnatural tongue anatomy.
If the prompt asks for a tongue-out expression, keep it subtle, teasing, natural, and flattering, with normal mouth proportions and the same recognizable face.
""".strip()

EXPLICIT_RENDER_TERMS = [
    "explicit",
    "nude",
    "naked",
    "topless",
    "bare breasts",
    "visible nipples",
    "masturbation",
    "touching her vagina",
    "vulva",
    "clit",
    "pussy",
    "dildo",
    "toy",
    "insertion",
]

NUDE_LOWER_RENDER_TERMS = [
    "nude",
    "naked",
    "fully nude",
    "completely nude",
    "bare body",
    "pubic area",
    "vulva",
    "clit",
    "pussy",
    "touching her vagina",
]

EXPLICIT_EXPRESSION_PROFILES = [
    (20, "relaxed natural smile, authentic creator smile, subtle warmth, relaxed cheeks, natural eye contact"),
    (15, "neutral relaxed face, calm expression, direct eye contact, candid portrait energy"),
    (15, "playful expression, teasing grin, amused smile, casual creator-photo energy"),
    (10, "laughing naturally, caught mid-laugh, genuine happiness, spontaneous camera-roll moment"),
    (10, "looking away thoughtfully, soft smile while looking off-camera, candid private moment"),
    (10, "confident expression, confident eye contact, slight smile, relaxed self-assured presence"),
    (10, "intimate bedroom eyes, soft seductive look, subtle intimacy, restrained private mood"),
    (5, "parted lips, intimate expression, quiet close-camera connection"),
    (5, "playful lower-lip bite, amused eyes, casual teasing energy"),
]


def get_explicit_expression(prompt_text):
    prompt_key = (prompt_text or "").strip().encode("utf-8")
    digest = hashlib.sha256(prompt_key).digest()
    bucket = int.from_bytes(digest[:8], "big") % 100

    running_total = 0
    for weight, profile in EXPLICIT_EXPRESSION_PROFILES:
        running_total += weight
        if bucket < running_total:
            return profile

    return EXPLICIT_EXPRESSION_PROFILES[-1][1]


def build_explicit_expression_directive(prompt_text):
    selected_expression = get_explicit_expression(prompt_text)
    return f"""
EXPLICIT EXPRESSION VARIATION:
Use this single selected expression profile only: {selected_expression}.
Render it like a real creator camera-roll photo: candid, emotionally alive, slightly asymmetrical, natural muscle tension, believable human expression, and creator taking her own photos.
Avoid mannequin face, beauty pageant smile, frozen expression, identical smile repetition, exaggerated glamour posing, plastic symmetry, and overacted facial performance.

EXPLICIT HAIR SHAPE LOCK:
Her hair must be worn down naturally with a smooth flat natural top and loose dark hair flowing around her face, over her shoulders, or down her back.
No bun, hairbun, topknot, ponytail, updo, tied-up hair, piled hair, messy crown, lifted knot, tall hair shape, or large clump of hair above the scalp.
If wet hair is present, it must stay loose and worn down, not tied up.
""".strip()


NUDE_GROOMING_RENDER_LOCK = """
NUDE GROOMING LOCK - NON-NEGOTIABLE:
If the pubic area or lower nude body is visible, there must be no pubic hair under any circumstances.
The pubic area must be fully smooth, hairless, and clean-shaven.
Do not render a landing strip, stubble, trimmed pubic hair, shadow hair, peach fuzz, or any visible pubic hair texture.
Keep the lower nude anatomy photorealistic, natural, and fully groomed smooth.
""".strip()

TOPLESS_RENDER_TERMS = [
    "topless",
    "bare breasts",
    "bare breast",
    "no bra",
    "no bikini top",
    "no upper-body clothing",
    "upper body uncovered",
]

TOPLESS_RENDER_LOCK = """
TOPLESS RENDER LOCK - NON-NEGOTIABLE:
The requested image is topless. Do not add a bikini top, bra, lingerie top, swimsuit top, crop top, shirt, robe, towel, dress, or any upper-body clothing.
Bare breasts must be clearly visible and unobstructed.
Natural nipples must be perky, visible, and unobstructed.
Keep nipple size, placement, symmetry, and perkiness consistent with her full natural D-cup bust.
Nipples should look natural, centered on each breast, proportionate, and clearly visible whenever breasts are exposed.
Do not cover the breasts with hair, arms, hands, shadows, water surface, fabric, props, or camera crop.
Preserve visibly full natural D-cup breast volume with rounded upper and lower fullness, natural projection, visible cleavage, and consistent nipple placement in the medium-close creator portrait crop.
The viewer should immediately recognize that the subject is topless.
""".strip()

WAN_BUST_VISIBILITY_LOCK = """
WAN BUST VISIBILITY LOCK:
Preserve visibly full natural D-cup breast volume, not a petite or minimized bust.
Do not reduce, flatten, minimize, shrink, hide, or soften her bust size.
When wearing a bikini, lingerie, bra, crop top, fitted shirt, dress, bodysuit, swimwear, or any tight clothing, show realistic fabric tension from full D-cup volume.
Make cleavage, bust projection, rounded lower-breast fullness, upper-breast fullness, and cup fill clearly visible whenever framing and wardrobe allow it.
Use torso angle, chest-forward posture, side angle, three-quarter angle, seated lean, or close upper-body crop to make bust size obvious.
Avoid loose clothing, straight-on flat posture, hair coverage, arm coverage, shadows, or crops that hide or visually reduce bust volume.
If a bikini top or bra is present, the cups must look visibly filled and slightly tensioned by full natural D-cup volume.
""".strip()


def references_topless_render(prompt_text):
    prompt_lower = (prompt_text or "").lower()
    return any(term in prompt_lower for term in TOPLESS_RENDER_TERMS)


def references_explicit_render(prompt_text):
    prompt_lower = (prompt_text or "").lower()
    return any(term in prompt_lower for term in EXPLICIT_RENDER_TERMS)


def references_nude_lower_render(prompt_text):
    prompt_lower = (prompt_text or "").lower()
    return any(term in prompt_lower for term in NUDE_LOWER_RENDER_TERMS)


def enforce_premium_render_body_lock(prompt_text):
    cleaned_prompt = (prompt_text or "").strip()

    if not cleaned_prompt:
        return ""

    render_locks = [PREMIUM_RENDER_BODY_LOCK]

    if references_explicit_render(cleaned_prompt):
        render_locks.append(build_explicit_expression_directive(cleaned_prompt))

    if references_nude_lower_render(cleaned_prompt):
        render_locks.append(NUDE_GROOMING_RENDER_LOCK)

    if references_topless_render(cleaned_prompt):
        render_locks.append(TOPLESS_RENDER_LOCK)
    else:
        render_locks.append(WAN_BUST_VISIBILITY_LOCK)

    return f"{cleaned_prompt}\n\n" + "\n\n".join(render_locks)
