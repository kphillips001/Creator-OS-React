import os

from app.services.wavespeed_grok_service import generate_prompts_with_grok

from app.services.ava_personality_service import (
    AVA_PERSONALITY_PROFILE,
    AVA_PREMIUM_CONTENT_FEEL,
    AVA_REFERENCE_USAGE_RULES,
)


def _generate_lucky_tags(prompt):
    api_key = os.getenv("GROK_API_KEY")

    result = generate_prompts_with_grok(
        prompt,
        api_key,
    )

    if isinstance(result, list):
        return "\n".join(
            str(item).strip()
            for item in result
            if str(item).strip()
        )

    return str(result).strip()


def generate_lucky_premium_tags(prompt_count: int = 10):
    prompt = f"""
You are the Premium Creative Director for Ava Blackthorne.

Generate {prompt_count} distinct premium creator-content tag concepts for Ava.

{AVA_PERSONALITY_PROFILE}

{AVA_PREMIUM_CONTENT_FEEL}

{AVA_REFERENCE_USAGE_RULES}

Create very sexy Premium Wall-content tags that are sensual, teasing, risqué, fantasy-leaning, lifestyle-driven, and paid-content-ready, but not nude/explicit by default.

Premium Wall content is the sexy public-facing/paywall-teaser lane:
- much hotter than Social Content Studio
- more body-aware and flirty than Social
- more alluring, seductive, cleavage-forward, and fantasy-coded than Social
- still outfit, setting, personality, and lifestyle driven
- often cute, casual, around-the-house, and girlfriend-coded while still clearly premium and sexy
- not the nude NSFW Paid Content lane unless the user explicitly asks for nudity
- the "one step before Explicit" lane: anything sexy, teasing, alluring, suggestive, and fantasy-charged that stops before explicit nudity, sex toys, masturbation, penetration, fluids, or graphic genital focus

Premium Lucky should NOT generate clean social-style lifestyle posts.
Every line should feel like a subscriber teaser someone would pay to unlock:
- obvious sex appeal
- alluring wardrobe
- cleavage, legs, hips, waist, or lingerie styling as a visual hook
- private eye contact or teasing expression
- fantasy tension without explicit sex acts
- fantasy tension without explicit nudity, sex toys, or explicit sex acts

Do not treat Premium as only lingerie or only at-home content.
Premium may be ANY non-explicit sexy teaser concept:
- lingerie, heels, stockings, fishnets, robe, miniskirt, micro shorts, barely-there but clothed styling
- bikini, wet shirt, towel styling, outdoor shower, pool, beach, balcony, hotel, cabin, couch, kitchen, hallway, bedroom doorway, bathroom vanity
- playful strap adjustment, robe slipping, skirt hem tease, towel held loosely, wet fabric clinging, low neckline, underboob while clothed, legs emphasized, hip curve, waist curve
- Ava's playful, warm, hot-girl-next-door personality must still be present

Each line must be its own separate photo concept. Do not make every concept a bedroom or bed concept.

Include risqué premium teaser concepts across the batch, such as:
- black lace lingerie with thigh-high stockings and spiked heels
- barely-there miniskirt with a fitted crop top and visible cleavage
- sheer robe slipping off one shoulder over matching lingerie
- fishnet stockings with an oversized tee lifted just enough to tease
- tiny sleep shorts with a cropped bralette in morning window light
- tight tank top with high-waisted micro shorts near a hallway mirror
- wet white shirt over bikini bottoms by an outdoor shower
- satin robe loosely tied at the waist on a balcony or bathroom vanity
- body-hugging bodysuit with heels in a bedroom doorway
- tiny bikini, low neckline, or underboob styling at the beach or pool

Keep the cute around-the-house lane, but make it premium-hot:
- fitted black crop top with tiny lounge shorts in a bedroom doorway, cleavage visible, hand on hip
- oversized tee pulled high enough to tease lingerie or sleep shorts
- casual bralette under an open cardigan on the couch
- soft robe open over cute underwear by a bathroom vanity
- kitchen counter, laundry room, couch, hallway, bedroom doorway, curtain light, or lived-in apartment moments with stronger sex appeal

Across the full set, include a strong mix of:
- Ava-coded coastal/country/home wardrobe such as black lace lingerie, matching lingerie set, sheer robe, satin robe, fishnet stockings, thigh-high stockings, spiked heels, miniskirt, barely-there dress, tiny bikini, bikini top with visible cup fill, tiny denim Daisy Duke shorts, fitted crop top, low-cut tight tank top, tiny lounge shorts, high-waisted soft shorts, fitted black tee, soft cropped tee, wet white shirt, cutoff shorts, body-hugging bodysuit, towel styling, fitted sleepwear, bralette under a cardigan, or swimwear
- lifestyle settings such as beach, boat day, dock, lake house porch, cabin, pool, outdoor shower, hotel balcony, couch, kitchen island, bathroom vanity, hallway mirror area without a visible phone, bedroom doorway, curtain window light, laundry room, cozy bed edge, or private vacation room
- medium-close creator framing such as waist-up, head-to-hips, head-to-upper-thigh portrait crop, upper-thigh portrait crop, or seated portrait framing, always with her full head visible and clean background space above loose hair
- if the concept is too tight to include her full head, bust, waist, and hips, pull the camera back slightly rather than crowding her face or hair against the top edge
- Ava-coded expression and energy such as cute teasing smile, playful confidence, warm eye contact, private gaze, relaxed smirk, half-lidded flirt, subtle parted lips, casual girlfriend energy, approachable hot girl next door energy
- sensual but non-explicit body language such as one hand on hip, slight torso twist, relaxed doorway lean, soft waist emphasis, shoulder angled toward camera, chest-forward posture, hips angled, hand brushing hair, playful strap adjustment, or natural close creator-photo stance
- hair continuity: long dark hair worn down, soft center part or natural side part, smooth flat natural top, loose flowing hair lying over her shoulders or down her back
- premium visual hooks such as visible cleavage, realistic fabric tension across the bust, thigh-high stockings, heels, legs emphasized, hip curve, waist curve, robe slipping off shoulder, low neckline, underboob when clothed, or tiny wardrobe coverage
- body continuity tags: full natural D-cup bust, feminine hourglass body, same waist-to-hip proportions, same natural sun-kissed skin tone as the reference image

Avoid:
- repeating the same location, outfit, furniture, or pose structure across the batch
- cropped-off forehead, missing top of head, or a composition that slices through her hair
- face pressed against the top edge, hair touching the top border, extreme close-up crops, or no clean background space above loose hair
- tall hair shapes, lifted tied hair, piled hair, knot-like hair silhouettes, or large hair clumps above the scalp
- making private bedroom, bed, or warm lamplight the default concept
- making every concept the same lingerie, silk robe, heel, or hotel bedroom setup
- plain social-safe outfits with no premium visual hook, such as basic tank top and denim shorts without cleavage, lingerie, teasing fabric tension, heels, stockings, or fantasy styling
- nude, topless, naked, bare breasts, visible nipples, explicit genital focus, or full NSFW paid-content concepts unless the user explicitly asks for them
- boat, lake, dock, marina, railing, or reference-background concepts copied from the reference image accidentally; only use those when chosen as a deliberate new Wall-content concept
- phone/selfie/mirror-device concepts unless you deliberately choose a mirror concept
- explicit sex acts, penetration, dildo/toy, masturbation, fluids, or graphic genital focus
- sex toys, dildo/toy, masturbation, insertion, penetration, fluids, explicit sex acts, spread-open poses, or graphic genital focus
- cold model posing, generic performer energy, or emotionless glamour

OUTPUT FORMAT:
Return exactly {prompt_count} lines.
Each line must be one comma-separated tag concept.
No numbering.
No bullets.
No markdown.
No explanation.
""".strip()

    return _generate_lucky_tags(prompt)


def generate_lucky_explicit_tags(prompt_count: int = 10):
    prompt = f"""
You are the Explicit Premium Creative Director for Ava Blackthorne.

Generate {prompt_count} distinct explicit-ready adult premium creator-content tag concepts for Ava.

{AVA_PERSONALITY_PROFILE}

{AVA_PREMIUM_CONTENT_FEEL}

{AVA_REFERENCE_USAGE_RULES}

Create explicit-ready tags that are very sexy, intimate, adult, and subscriber-focused while keeping Ava's playful hot-girl-next-door character.

Each line must be its own separate photo concept. Do not make every concept a bedroom or bed concept.

Across the full set, include a strong mix of:
- explicit adult state or wardrobe state such as nude, topless, bare breasts, shower nude, bed nude, robe open, lingerie removal, wet skin, wet hair, or intimate bathroom/bedroom setting
- seductive body language such as arched back, chest-forward posture, hips angled, hand on hip, thighs angled, torso twist, intimate seated pose, or close viewer-facing body language
- seductive facial energy such as half-lidded bedroom eyes, teasing eye contact, parted lips, playful aroused expression, relaxed mischievous smirk, warm seductive gaze
- close explicit framing such as tight head-to-upper-thigh crop, waist-up nude crop, upper-thigh intimate crop, close-medium shower framing
- hair continuity: long dark hair worn down, soft center part or natural side part, smooth flat natural top, loose flowing hair lying over her shoulders or down her back
- full-head framing: full forehead, hairline, crown, and smooth natural hair top visible with clean background space above loose hair
- body continuity tags: full natural D-cup bust, feminine hourglass body, same waist-to-hip proportions, same natural sun-kissed skin tone as the reference image

Avoid:
- repeating the same location, outfit, furniture, or pose structure across the batch
- making private bedroom, bed, or warm lamplight the default concept
- boat, lake, dock, marina, railing, or reference-background concepts unless they are the main creative idea
- buns, hairbuns, topknots, ponytails, updos, lifted tied hair, piled hair, messy crowns, tall hair shapes, or large clumps of hair above the scalp
- cropped-off forehead, missing top of head, face pressed against the top edge, hair touching the top border, or no clean background space above loose hair
- underage appearance
- cartoonish or unrealistic anatomy
- generic porn-performer energy
- repeating one single pose idea too many times

OUTPUT FORMAT:
Return exactly {prompt_count} lines.
Each line must be one comma-separated tag concept.
No numbering.
No bullets.
No markdown.
No explanation.
""".strip()

    return _generate_lucky_tags(prompt)
