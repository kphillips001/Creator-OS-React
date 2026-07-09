import os
import re

from dotenv import load_dotenv

from app.services.wavespeed_grok_service import generate_prompts_with_grok


GROK_ASSISTANT_PROMPT_COUNT = 10

LANE_LABELS = {
    "social": "Social Safe",
    "premium": "Premium",
    "explicit": "Explicit",
}


SHOT_CARD_FRAMING_RULES = """
Close creator-feed framing:
- Use intimate close-camera creator perspective, as if the viewer is right there with her.
- The camera should feel handheld and casual, but never show a phone, camera, phone screen, phone frame, phone UI, selfie device, hands holding a phone, or mirror-phone composition unless the user explicitly asks for a mirror selfie.
- Prefer vertical 4:5 social feed composition.
- Keep her face clearly visible and important, with direct eye contact or a strong viewer connection whenever it fits the scene.
- Make foreground body geometry part of the shot: arms, shoulders, bust, waist, hips, thighs, railing, pool edge, counter, couch, bed, window, or water line should create depth toward the camera.
- Keep the environment as mood and context only; she must remain the visual subject.
- Keep her full head, forehead, hairline, crown, and loose hair fully inside frame with clean breathing room above her hair.
- Avoid cropped-off head, cut-off face, face pressed into the top edge, buns, ponytails, topknots, lifted tied hair, or tall messy hair shapes.
""".strip()


def sanitize_reference_name(prompt):
    cleaned_prompt = str(prompt or "").strip()

    cleaned_prompt = re.sub(
        r"\bAva\s+Blackthorne(?:'s|’s)\b",
        "the reference woman's",
        cleaned_prompt,
        flags=re.IGNORECASE,
    )

    cleaned_prompt = re.sub(
        r"\bAva(?:'s|’s)\b",
        "the reference woman's",
        cleaned_prompt,
        flags=re.IGNORECASE,
    )

    cleaned_prompt = re.sub(
        r"\bAva\s+Blackthorne\b",
        "the reference woman",
        cleaned_prompt,
        flags=re.IGNORECASE,
    )

    cleaned_prompt = re.sub(
        r"\bAva\b",
        "the reference woman",
        cleaned_prompt,
        flags=re.IGNORECASE,
    )

    cleaned_prompt = re.sub(
        r"\bthe reference woman's\s+(sits|stands|leans|lounges|kneels|poses|reclines|wears|features|has|is)\b",
        r"the reference woman \1",
        cleaned_prompt,
        flags=re.IGNORECASE,
    )

    cleaned_prompt = re.sub(
        r"\bthe reference woman\s+the reference woman\b",
        "the reference woman",
        cleaned_prompt,
        flags=re.IGNORECASE,
    )

    return re.sub(r"\s+", " ", cleaned_prompt).strip()


def split_numbered_prompt_candidates(raw_response):
    if not raw_response:
        return []

    if isinstance(raw_response, list):
        return [
            str(item).strip()
            for item in raw_response
            if str(item).strip()
        ]

    parts = re.split(
        r"\n\s*\d+[\.\)]\s+",
        "\n" + str(raw_response).strip(),
    )

    return [
        sanitize_reference_name(
            re.sub(r"\s+", " ", part).strip(" -")
        )
        for part in parts
        if part.strip()
    ]


def build_grok_prompt_assistant_instruction(
    user_request,
    lane,
    prompt_count=GROK_ASSISTANT_PROMPT_COUNT,
):
    lane = lane if lane in LANE_LABELS else "premium"
    lane_label = LANE_LABELS[lane]

    lane_rules = {
        "social": """
Social Safe lane:
- Make prompts platform-safe, cute, flirty, polished, and lifestyle-oriented.
- No nudity, no explicit sexual content, no visible nipples, no exposed genitals, no sex toys.
- Wardrobe can include fitted outfits, crop tops, shorts, dresses, swimwear, jeans, athleisure, pajamas, or cozy home looks.
- Keep the energy attractive and engaging without becoming premium or explicit.
""",
        "premium": """
Premium lane:
- Make prompts sexy, teasing, alluring, and private-content coded, one step before explicit.
- Lingerie, sheer robes, stockings, miniskirts, heels, cleavage, barely-there outfits, playful garment teasing, bedroom/couch/balcony/bathroom settings are allowed.
- Avoid explicit sex acts, visible genitals, graphic masturbation, insertion, or sex toys.
- Tasteful topless or implied nudity may appear only if the user clearly asks for it.
""",
        "explicit": """
Explicit lane:
- Make prompts adult NSFW and explicit when the user asks for that direction.
- Nudity, toplessness, visible nipples, explicit body positioning, masturbation, wetness, toys, and direct sexual framing may be included when consistent with the user's request.
- Keep anatomy realistic and intimate, not cartoonish or exaggerated.
- Keep the subject solo unless the user explicitly requests otherwise.
""",
    }[lane]

    return f"""
You are helping brainstorm shot-direction cards for image generation.

User request:
{user_request}

Selected lane: {lane_label}

Shot-card goal:
- Return creative scene cards only. Do not write final renderer prompts.
- Each card should describe setting, wardrobe, pose, expression/mood, lighting, camera distance, and composition.
- The app will add identity lock, body lock, face lock, and renderer-safe framing later.
- Think like a photographer/director planning premium creator-content shots, not like a prompt engineer writing a huge final prompt.
- If the user gives only keywords, expand those keywords into complete varied shot cards while preserving the requested vibe and wardrobe details.

{lane_rules}

{SHOT_CARD_FRAMING_RULES}

Output requirements:
- Return exactly {prompt_count} shot cards.
- Number each shot card 1 through {prompt_count}.
- Each shot card must be one compact paragraph, ideally 35 to 70 words.
- Each shot card may start with a short title followed by a colon.
- Make each shot card distinct in setting, pose, wardrobe, lighting, and mood.
- Do not use the name Ava, Ava Blackthorne, or any character/person name in the returned prompts.
- Refer to the subject as "she" whenever possible.
- Do not repeat identity-lock phrases like "same woman from the reference image", "exact face", "same identity", or body preservation language.
- Do not include visible phones, phone screens, phone frames, phone UI, hands holding a phone, or mirror-phone selfies unless the user explicitly requests a mirror selfie or visible phone.
- Do not include markdown headings, commentary, notes, or explanations.
- Do not wrap prompts in quotation marks.
""".strip()


def build_wavespeed_prompt_from_shot_card(
    shot_card,
    lane="premium",
):
    lane = lane if lane in LANE_LABELS else "premium"
    scene_text = sanitize_reference_name(shot_card)

    lane_style = {
        "social": (
            "Keep the result platform-safe, cute, flirty, polished, and lifestyle-oriented. "
            "No nudity, no explicit sexual content, no visible nipples, no exposed genitals, and no sex toys."
        ),
        "premium": (
            "Keep the result sexy, teasing, alluring, and private-content coded, one step before explicit. "
            "Lingerie, sheer robes, stockings, miniskirts, heels, cleavage, barely-there outfits, and playful garment teasing are allowed. "
            "Avoid explicit sex acts, visible genitals, graphic masturbation, insertion, or sex toys."
        ),
        "explicit": (
            "Keep the result adult NSFW when the shot card calls for it, with realistic solo adult creator-content framing. "
            "Nudity, toplessness, visible nipples, explicit body positioning, masturbation, wetness, toys, and direct sexual framing may be included when consistent with the selected shot card."
        ),
    }[lane]

    return f"""
Using the selected reference image as the identity anchor, create a photorealistic creator-content image of the same woman.

Preserve her exact face, facial structure, eyes, nose, lips, jawline, cheekbones, natural facial proportions, long dark loose hair, natural sun-kissed skin tone, feminine hourglass body shape, full natural D-cup bust, waist-to-hip proportions, hips, thighs, shoulders, and overall body scale from the reference image.

Scene direction:
{scene_text}

Lane direction:
{lane_style}

Framing direction:
{SHOT_CARD_FRAMING_RULES}
- Make her face, eyes, upper body, bust, waist, hip angle, thighs, or water/railing/counter foreground visually dominant depending on the shot.
- If the composition cannot fit her full face, smooth natural hair top, bust, waist, and hips at the requested distance, pull the camera back slightly.
- Avoid wide room shots, distant full-body shots, scenery-dominant pool/lake/landscape shots, or any composition where furniture, water, room decor, or background becomes more important than her.

Hair lock:
Her long dark hair must be worn down naturally with a soft center part or natural side part, smooth flat natural top, and loose flowing hair over her shoulders or down her back. No bun, ponytail, updo, top knot, lifted tied hair, tall hair shape, or messy crown.

Style:
Realistic creator-content photography with a natural handheld feel, believable natural skin texture, flattering natural or warm indoor light, realistic fabric tension, soft depth of field, intimate viewer connection, no visible phone, no phone screen, no phone frame, no selfie device, no platform UI, no captions, no watermarks, no browser chrome.
""".strip()


def ask_grok_for_prompt_candidates(
    user_request,
    lane,
    prompt_count=GROK_ASSISTANT_PROMPT_COUNT,
):
    load_dotenv()

    api_key = os.getenv("GROK_API_KEY")

    if not api_key:
        raise ValueError("Missing GROK_API_KEY in .env")

    if not user_request or not user_request.strip():
        raise ValueError("Enter prompt guidance before asking Grok.")

    instruction = build_grok_prompt_assistant_instruction(
        user_request=user_request.strip(),
        lane=lane,
        prompt_count=prompt_count,
    )

    raw_response = generate_prompts_with_grok(
        instruction,
        api_key,
    )

    prompts = split_numbered_prompt_candidates(raw_response)

    return prompts[:prompt_count]
