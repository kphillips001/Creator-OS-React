import os
import re

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_client = None


def get_grok_client():
    global _client

    if _client is None:
        api_key = os.getenv("GROK_API_KEY", "")
        if not api_key:
            raise RuntimeError("Grok API key is not configured.")

        _client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("GROK_BASE_URL"),
        )

    return _client


PREMIUM_INTIMACY_TAG_RULES = """
Premium intimacy rules to inherit from the explicit prompt path, without becoming hardcore:
- preserve exact reference identity, face, hair, body, bust size, waist-to-hip proportions, and same natural sun-kissed skin tone
- keep the subject large in frame, with the environment secondary
- favor medium-close, waist-up, head-to-hips, head-to-upper-thigh, and upper-thigh portrait creator framing, always with full face and full head visible
- keep her full head in frame, with her smooth natural hair top visible and a little clean background space above her hair
- if the composition is too tight to include her full head and body cues, pull the camera back slightly rather than crowding her face or hair against the top edge
- preserve long dark hair worn down, soft center part or natural side part, smooth flat natural top, loose flowing hair lying over her shoulders or down her back
- avoid tall hair shapes, lifted tied hair, piled hair, knot-like hair silhouettes, or large hair clumps above the scalp
- include emotionally alive expression language: warm eye contact, teasing smile, playful confidence, private gaze, relaxed smirk, subtle parted lips
- include seductive but non-graphic body-language tags: chest-forward posture, hips angled, torso twist, flattering posture, natural hand placement, relaxed shoulders
- include cute around-the-house premium options when appropriate: bedroom doorway, couch, kitchen counter, bathroom vanity, hallway mirror area without visible phone, laundry room, curtain window light, cozy lived-in apartment
- include risqué premium wardrobe when appropriate: black lace lingerie, matching lingerie set, sheer robe, satin robe, fishnet stockings, thigh-high stockings, spiked heels, miniskirt, barely-there dress, low-cut fitted tank top, tiny bikini, wet white shirt, body-hugging bodysuit
- include casual sexy wardrobe when appropriate: fitted crop top, tight tank top, fitted black tee, tiny lounge shorts, high-waisted soft shorts, oversized tee lifted enough to tease, cute sleepwear, robe over underwear, bralette under cardigan
- include premium visual hooks: visible cleavage, realistic fabric tension across the bust, legs emphasized, hip curve, waist curve, robe slipping off shoulder, low neckline, underboob when clothed, tiny wardrobe coverage, alluring private eye contact
- treat Premium as the one-step-before-Explicit lane: anything sexy, teasing, alluring, suggestive, and fantasy-charged that stops before explicit nudity, sex toys, masturbation, penetration, fluids, or graphic genital focus
- keep home concepts believable, warm, playful, girlfriend-coded, and clearly paywall-teaser sexy without turning them into nude or hardcore scenes
- include private creator-content realism, natural lighting, realistic skin texture, believable fabric texture, and candid intimate atmosphere
- avoid blank model stare, stiff catalog posing, professional studio energy, detached fashion posing, and scenery-first composition
- avoid cropped-off forehead, missing top of head, face pressed against the top edge, hair touching the top border, extreme close-up crops, or a composition that slices through her hair
"""


PREMIUM_CLOTHING_PRESERVATION_RULES = """
Premium clothing preservation rules:
- if the user asks for clothing, wardrobe, bikini, denim shorts, lingerie, dress, robe, bodysuit, crop top, shorts, jeans, skirt, or swimwear, preserve those garments as mandatory premium wardrobe tags
- treat broad wardrobe phrases as categories, not as one fixed outfit; examples include crop top, micro crop top, tank top, tight shorts, micro-shorts, dress, skirt, bikini, jeans, and lingerie
- preserve broad wardrobe phrases using the user's own level of specificity so the prompt generator can vary unspecified color, fabric, cut, neckline, trim, and garment construction across the Content Studio batch
- do not invent a single color, fabric, cut, neckline, trim, or construction for a broad wardrobe phrase unless the user explicitly supplied that detail
- if the user explicitly supplies a wardrobe detail such as black, white, red, leather, denim, lace, satin, halter, racerback, tied-front, scoop-neck, high-waisted, or low-rise, preserve that exact requested detail
- if the user gives a broad wardrobe category such as "lingerie", preserve it as a broad category and expand it into variety instead of choosing one default style
- for broad "lingerie" input, include a mixed lingerie palette such as satin lingerie, lace bralette and panties, sheer mesh set, strappy lingerie, balconette bra set, bodysuit/teddy, corset-style lingerie, garter belt, thigh-high stockings, fishnets, silk robe over lingerie, neutral tones, white, champagne, blush pink, red, emerald, navy, and black; do not default every result to black lace lingerie
- if the user asks for cute, casual, around the house, at home, lounge, doorway, couch, kitchen, bedroom, bathroom, or morning light, keep it casual-home premium but add paywall-teaser heat through cleavage, fitted fabric, tiny shorts, bralette, robe, stockings, heels, teasing pose, or private eye contact
- if the user gives any mild idea, make it Premium by adding a sexy non-explicit tease, not necessarily lingerie: low neckline, wet fabric, towel held loosely, skirt hem tease, robe slipping, strap adjustment, legs emphasized, hip curve, waist curve, private gaze, or fantasy tension
- do not escalate clothed concepts into nude, topless, naked, bare-breasted, no top, no bottoms, or unclothed imagery unless the user explicitly asks for nude, topless, naked, bare breasts, or no clothing
- for revealing clothed concepts like bikini top, underboob, very short shorts, thong, or lingerie, keep the requested garments visible and describe fit, fabric tension, cleavage, silhouette, and placement instead of removing the garment
"""


def split_tag_list(raw_tags: str) -> list[str]:
    if not raw_tags:
        return []

    cleaned_text = re.sub(
        r"\n\s*\d+[\.\)]\s*",
        ", ",
        str(raw_tags),
    )
    cleaned_text = re.sub(
        r"\s*[\n;]\s*",
        ", ",
        cleaned_text,
    )

    return [tag.strip() for tag in cleaned_text.split(",") if tag.strip()]


def normalize_tag_key(tag: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        re.sub(r"[^a-z0-9]+", " ", tag.lower()),
    ).strip()


def dedupe_premium_tags(raw_tags) -> str:
    if not raw_tags:
        return ""

    if isinstance(raw_tags, list):
        tag_candidates = [
            tag
            for item in raw_tags
            for tag in split_tag_list(str(item))
        ]
    else:
        tag_candidates = split_tag_list(str(raw_tags))

    unique_tags = []
    seen_keys = set()

    for tag in tag_candidates:
        cleaned_tag = tag.strip(" ,.-")
        if not cleaned_tag:
            continue

        tag_key = normalize_tag_key(cleaned_tag)
        if not tag_key or tag_key in seen_keys:
            continue

        seen_keys.add(tag_key)
        unique_tags.append(cleaned_tag)

    return ", ".join(unique_tags)


def has_multiple_tag_lines(raw_tags: str) -> bool:
    if not raw_tags:
        return False

    return len([line for line in str(raw_tags).splitlines() if line.strip()]) > 1


def dedupe_premium_tag_lines(raw_tags) -> str:
    if not raw_tags:
        return ""

    if isinstance(raw_tags, list):
        raw_lines = [str(item).strip() for item in raw_tags if str(item).strip()]
    else:
        raw_lines = [
            line.strip()
            for line in str(raw_tags).splitlines()
            if line.strip()
        ]

    cleaned_lines = []
    seen_lines = set()

    for line in raw_lines:
        cleaned_line = re.sub(r"^\s*(?:\d+[\.\)]|[-*])\s*", "", line).strip()
        deduped_line = dedupe_premium_tags(cleaned_line)
        if not deduped_line:
            continue

        line_key = normalize_tag_key(deduped_line)
        if not line_key or line_key in seen_lines:
            continue

        seen_lines.add(line_key)
        cleaned_lines.append(deduped_line)

    return "\n".join(cleaned_lines)


def is_broad_lingerie_request(simple_tags: str) -> bool:
    tag_keys = [
        normalize_tag_key(tag)
        for tag in split_tag_list(str(simple_tags or ""))
    ]

    if not tag_keys:
        return False

    specific_lingerie_terms = {
        "black lace",
        "white lace",
        "red lace",
        "satin",
        "mesh",
        "strappy",
        "corset",
        "teddy",
        "bodysuit",
        "bralette",
        "balconette",
        "garter",
        "stockings",
        "fishnets",
        "robe",
    }

    has_lingerie = any(
        tag_key == "lingerie" or " lingerie" in f" {tag_key}"
        for tag_key in tag_keys
    )

    has_specific_style = any(
        specific_term in tag_key
        for tag_key in tag_keys
        for specific_term in specific_lingerie_terms
    )

    return has_lingerie and not has_specific_style


def ensure_lingerie_variety_tags(simple_tags: str, enhanced_tags: str) -> str:
    if not is_broad_lingerie_request(simple_tags):
        return enhanced_tags

    variety_tags = (
        "varied lingerie wardrobe palette, satin lingerie set, lace bralette and panties, "
        "sheer mesh lingerie set, strappy lingerie, balconette bra set, corset-style teddy, "
        "garter belt, thigh-high stockings, fishnets, silk robe over lingerie, matching bra-and-panty set, "
        "champagne lingerie, blush pink lingerie, white lingerie, red lingerie, emerald lingerie, navy lingerie"
    )

    return dedupe_premium_tags(
        f"{variety_tags}, {enhanced_tags}"
    )


def build_premium_tag_enhancer_prompt(simple_tags: str) -> str:
    line_count = len([line for line in str(simple_tags).splitlines() if line.strip()])
    multi_line_rules = ""

    if line_count > 1:
        multi_line_rules = f"""
MULTI-LINE USER TAG RULE:
The user supplied {line_count} separate premium concepts, one concept per line.
Preserve that structure exactly.
Return exactly {line_count} lines.
Each returned line must enhance only the matching input line.
Do not merge lines together.
Do not let one line's setting, outfit, furniture, lighting, or pose leak into another line.
Vary the setting, outfit, and premium moment across the batch.
Do not make every line a bedroom, bed, robe, or warm-lamplight concept unless the input lines already require that.
Each line should remain a comma-separated tag concept, not a full prompt.
"""

    return f"""
You are a Premium Creator Content Tag Enhancer.

The user gives simple creative tags.

Your job is to expand them into premium, image-generation-ready visual tags.

Keep the user's original idea, but make it richer, more specific, and more visually useful.

Focus on:
- wardrobe and styling
- cute casual home styling when the input points that way
- risqué premium teaser styling rather than social-safe styling
- required clothing or nudity tags
- reference body continuity
- full natural D-cup bust continuity
- feminine hourglass body continuity
- same natural sun-kissed reference skin tone continuity
- broad location theme
- lighting mood
- textures
- atmosphere
- realistic premium visual detail

{PREMIUM_INTIMACY_TAG_RULES}
{PREMIUM_CLOTHING_PRESERVATION_RULES}
{multi_line_rules}

Do NOT lock the prompt into one specific pose, furniture item, or exact scene.

Avoid adding:
- specific poses
- specific furniture
- specific body positions
- exact camera angles
- one fixed location inside the environment
- wardrobe colors the user did not request
- wardrobe fabrics the user did not request
- garment cuts, necklines, trim, or construction the user did not request
- cellphone selfie tags
- phone-in-frame tags
- mirror selfie tags
- outstretched-arm selfie tags

Examples to avoid:
- reclining on lounge chair
- standing in shallow end
- sitting on tiled pool steps
- leaning against railing
- arched back pose
- lying on couch
- sitting on fireplace hearth
- phone selfie
- mirror selfie
- holding a phone
- arm stretched toward the camera

Keep enhanced tags flexible so the prompt builder can create multiple different scenes.

CONTENT STUDIO WARDROBE VARIATION:
- Content Studio creates independent variations, not one continuous photoshoot
- keep broad user wardrobe categories broad in the enhanced tags
- expand scene, lighting, mood, atmosphere, environment, expression, and premium styling without collapsing a broad garment category into one exact outfit
- example: "tight shorts, micro crop top" must remain "tight shorts, micro crop top"; do not turn it into one coral halter top with white high-waisted shorts
- example: "black leather mini skirt" must remain black, leather, and a mini skirt because those details came from the user
- AI-added wardrobe ideas are suggestions for the later batch, not new fixed requirements

Do NOT choose a specific outdoor setting.

If the user says:

outdoors

return:

outdoors

NOT:

forest
woods
meadow
garden
trail
greenery
jungle

Allow the prompt generator to decide.

If the user provides a broad location:

- outdoors
- beach
- lake
- mountain
- city
- apartment
- cabin

keep the location broad.

Do not narrow it into one specific scene.

Important rules:
- For a single input concept, return ONLY one comma-separated tag list.
- For multi-line input, return one comma-separated tag concept per line.
- Do NOT write a full prompt.
- Do NOT write sentences.
- Do NOT explain anything.
- Do NOT use bullets or numbering.
- Do NOT make it vague or conceptual.
- Prefer concrete visual tags over abstract phrases.
- Always include body continuity tags: full natural D-cup bust, feminine hourglass body, same waist-to-hip proportions, same natural sun-kissed skin tone as the reference image.
- Do NOT soften the D-cup requirement into generic words like curvy, attractive, or feminine.
- Do NOT add phone, cellphone, smartphone, selfie, mirror selfie, arm-length selfie, or visible device concepts unless the user explicitly asks for them.
- Do NOT add explicit sex acts, masturbation, dildo/toy, penetration, fluids, genital detail, or hardcore NSFW concepts. Those belong in Explicit Tags only.
- Do NOT make Premium tags read like Social Content Studio; include at least one premium visual hook such as lingerie, sheer robe, fishnets, heels, miniskirt, visible cleavage, wet fabric, towel tease, robe slipping, strap adjustment, underboob while clothed, tiny shorts, low neckline, legs emphasized, hip curve, or private fantasy tension.
- If the user input is exactly or broadly "lingerie", do NOT return only black lace lingerie. Return a broad lingerie wardrobe palette with several distinct colors, materials, and garment types for the prompt generator to vary.
- Do NOT include sex toys, dildo/toy, masturbation, insertion, penetration, fluids, explicit sex acts, spread-open poses, or graphic genital focus.
- Keep hair worn down with a smooth flat natural top and loose flowing hair over shoulders or down back.

Example input:
around the house, cute, crop top, shorts

Example output:
cozy bedroom doorway, fitted black crop top with visible cleavage, high-waisted tiny lounge shorts, black lace bralette edge peeking subtly, cute teasing smile, warm curtain window light, relaxed hand on hip, soft torso twist, medium-close portrait framing with full head visible and clean space above loose hair, casual girlfriend-coded paywall-teaser mood, realistic fabric tension across the bust, intimate creator-content framing, full natural D-cup bust, feminine hourglass body, same waist-to-hip proportions, same natural sun-kissed skin tone as the reference image

Example input:
lingerie, heels, bedroom doorway

Example output:
bedroom doorway, varied lingerie wardrobe palette, satin lingerie set, sheer mesh bralette and panties, lace balconette bra set, strappy lingerie, corset-style teddy, garter belt, thigh-high stockings, spiked heels, silk robe slipping off one shoulder, visible cleavage, chest-forward posture, hips angled, private teasing eye contact, warm low bedroom light, medium-close portrait framing with full head visible and clean space above loose hair, intimate paywall-teaser mood, realistic lace satin and mesh texture, realistic fabric tension across the bust, full natural D-cup bust, feminine hourglass body, same waist-to-hip proportions, same natural sun-kissed skin tone as the reference image

Example input:
boat, water, lake, cabin

Example output:
lake, boat, cabin, summer, tiny bikini, wet hair, sun-kissed skin, golden hour sunlight, sparkling water reflections, warm outdoor atmosphere, realistic skin texture, shallow depth of field, intimate creator-content mood, natural close creator-photo realism
USER TAGS:
{simple_tags}
"""


def build_premium_surprise_tags_prompt(simple_tags: str) -> str:
    line_count = len([line for line in str(simple_tags).splitlines() if line.strip()])
    multi_line_rules = ""

    if line_count > 1:
        multi_line_rules = f"""
MULTI-LINE USER TAG RULE:
The user supplied {line_count} separate premium concepts, one concept per line.
Preserve that structure exactly.
Return exactly {line_count} lines.
Each returned line must create a stronger version of only the matching input line.
Do not merge lines together.
Do not let one line's setting, outfit, furniture, lighting, or pose leak into another line.
Make the batch feel varied across setting, outfit, body language, and mood.
Do not make every line a bedroom, bed, robe, or warm-lamplight concept unless the input lines already require that.
Each line should remain a comma-separated tag concept, not a full prompt.
"""

    return f"""
You are a Premium Creator Content Creative Director.

The user gives simple creative tags.

Your job is to create a more imaginative premium-ready comma-separated visual tag list.

Keep the user's original idea, but add a stronger creative direction with richer image-generation details.

Focus on:
- unexpected but realistic setting details
- cute casual home styling when the input points that way
- risqué premium teaser styling rather than social-safe styling
- wardrobe and styling
- reference body continuity
- full natural D-cup bust continuity
- feminine hourglass body continuity
- same natural sun-kissed reference skin tone continuity
- pose and body positioning
- environment details
- props
- lighting
- camera framing
- textures
- atmosphere
- luxury lifestyle details
- cinematic visual energy

{PREMIUM_INTIMACY_TAG_RULES}
{PREMIUM_CLOTHING_PRESERVATION_RULES}
{multi_line_rules}

Important rules:
- For a single input concept, return ONLY one comma-separated tag list.
- For multi-line input, return one comma-separated tag concept per line.
- Do NOT write a full prompt.
- Do NOT write sentences.
- Do NOT explain anything.
- Do NOT use bullets or numbering.
- Do NOT make it vague or conceptual.
- Prefer concrete visual tags over abstract phrases.
- Always include body continuity tags: full natural D-cup bust, feminine hourglass body, same waist-to-hip proportions, same natural sun-kissed skin tone as the reference image.
- Do NOT soften the D-cup requirement into generic words like curvy, attractive, or feminine.
- Do NOT add phone, cellphone, smartphone, selfie, mirror selfie, arm-length selfie, or visible device concepts unless the user explicitly asks for them.
- Do NOT add explicit sex acts, masturbation, dildo/toy, penetration, fluids, genital detail, or hardcore NSFW concepts. Those belong in Explicit Tags only.
- Do NOT make Premium tags read like Social Content Studio; include at least one premium visual hook such as lingerie, sheer robe, fishnets, heels, miniskirt, visible cleavage, wet fabric, towel tease, robe slipping, strap adjustment, underboob while clothed, tiny shorts, low neckline, legs emphasized, hip curve, or private fantasy tension.
- If the user input is exactly or broadly "lingerie", do NOT return only black lace lingerie. Return a broad lingerie wardrobe palette with several distinct colors, materials, and garment types for the prompt generator to vary.
- Do NOT include sex toys, dildo/toy, masturbation, insertion, penetration, fluids, explicit sex acts, spread-open poses, or graphic genital focus.
- Keep hair worn down with a smooth flat natural top and loose flowing hair over shoulders or down back.

Example input:
around the house, cute, crop top, shorts

Example output:
sunlit bedroom doorway, fitted black crop top with visible cleavage, high-waisted charcoal micro lounge shorts, lace bralette edge peeking subtly, curtain-filtered morning light, full-length wall mirror in background without visible phone, relaxed hand on hip, soft torso twist, cute teasing smile, warm private eye contact, lived-in apartment intimacy, head-to-upper-thigh portrait framing with full head visible and clean space above loose hair, realistic cotton fabric tension across the bust, casual girlfriend-coded paywall-teaser mood, full natural D-cup bust, feminine hourglass body, same waist-to-hip proportions, same natural sun-kissed skin tone as the reference image

Example input:
lingerie, heels, bedroom doorway

Example output:
bedroom doorway, varied lingerie wardrobe palette, champagne satin lingerie, blush lace bralette set, sheer black mesh set, red strappy lingerie, emerald corset-style teddy, garter belt, thigh-high stockings, fishnets, spiked heels, silk robe slipping off one shoulder, visible cleavage, chest-forward posture, hips angled, private teasing eye contact, warm low bedroom light, head-to-upper-thigh portrait framing with full head visible and clean space above loose hair, realistic lace satin mesh and strap texture, realistic fabric tension across the bust, seductive but non-explicit paywall-teaser mood, full natural D-cup bust, feminine hourglass body, same waist-to-hip proportions, same natural sun-kissed skin tone as the reference image

Example input:
boat, water, lake, cabin

Example output:
private lake house dock, polished wooden speedboat, emerald lake water, secluded cabin porch, tiny white bikini, oversized sunhat, wet skin glow, soft wind in hair, sunset reflections, champagne glass prop, barefoot pose, close-up portrait framing, cinematic summer escape, shallow depth of field, luxury vacation realism

USER TAGS:
{simple_tags}
"""


def _call_grok(prompt: str) -> str:
    response = get_grok_client().chat.completions.create(
        model=os.getenv("GROK_MODEL"),
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0.9,
    )

    return response.choices[0].message.content.strip()


def enhance_premium_tags(simple_tags: str) -> str:
    prompt = build_premium_tag_enhancer_prompt(
        simple_tags=simple_tags,
    )

    raw_enhanced_tags = _call_grok(prompt)
    enhanced_tags = (
        dedupe_premium_tag_lines(raw_enhanced_tags)
        if has_multiple_tag_lines(simple_tags) or has_multiple_tag_lines(raw_enhanced_tags)
        else dedupe_premium_tags(raw_enhanced_tags)
    )

    if enhanced_tags:
        return ensure_lingerie_variety_tags(
            simple_tags,
            enhanced_tags,
        )

    fallback_tags = (
        dedupe_premium_tag_lines(simple_tags)
        if has_multiple_tag_lines(simple_tags)
        else dedupe_premium_tags(simple_tags)
    )

    return ensure_lingerie_variety_tags(
        simple_tags,
        fallback_tags,
    )


def surprise_premium_tags(simple_tags: str) -> str:
    prompt = build_premium_surprise_tags_prompt(
        simple_tags=simple_tags,
    )

    raw_surprise_tags = _call_grok(prompt)
    surprise_tags = (
        dedupe_premium_tag_lines(raw_surprise_tags)
        if has_multiple_tag_lines(simple_tags) or has_multiple_tag_lines(raw_surprise_tags)
        else dedupe_premium_tags(raw_surprise_tags)
    )

    if surprise_tags:
        return ensure_lingerie_variety_tags(
            simple_tags,
            surprise_tags,
        )

    fallback_tags = (
        dedupe_premium_tag_lines(simple_tags)
        if has_multiple_tag_lines(simple_tags)
        else dedupe_premium_tags(simple_tags)
    )

    return ensure_lingerie_variety_tags(
        simple_tags,
        fallback_tags,
    )
