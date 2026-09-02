import os
import re
import json
import logging
from dataclasses import asdict, dataclass
from dotenv import load_dotenv
from app.services.explicit_editorial_guidance import ExplicitEditorialGuidance
from app.services.explicit_expression_profile import (
    EXPLICIT_EXPRESSION_SECTION,
    ExplicitExpressionProfile,
    ExplicitExpressionProfileService,
)
from app.services.wavespeed_grok_service import generate_prompts_with_grok

LOGGER = logging.getLogger("creator_os.canonical_planner")

load_dotenv()

# ==================== QUALITY & REALISM ====================
QUALITY_SUFFIX = (
    "photorealistic, ultra-realistic 8k raw photo, natural skin texture with visible pores, "
    "realistic anatomy and proportions, natural lighting with subtle shadows, "
    "candid intimate atmosphere, film grain, natural body, masterpiece, best quality"
)

EDITORIAL_DIRECTION_FIELDS = (
    "emotional_tone",
    "facial_expression",
    "eye_contact",
    "body_language",
    "editorial_energy",
    "visual_storytelling",
    "subject_awareness",
    "camera_engagement",
)

EXPLICIT_EDITORIAL_GUIDANCE = ExplicitEditorialGuidance()


@dataclass(frozen=True)
class EditorialDirection:
    emotional_tone: str
    facial_expression: str
    eye_contact: str
    body_language: str
    editorial_energy: str
    visual_storytelling: str
    subject_awareness: str
    camera_engagement: str

    def as_metadata(self) -> dict[str, str]:
        return asdict(self)

    def render(self) -> str:
        labels = {
            "emotional_tone": "Emotional tone",
            "facial_expression": "Facial expression",
            "eye_contact": "Eye contact",
            "body_language": "Body language",
            "editorial_energy": "Editorial energy",
            "visual_storytelling": "Visual storytelling",
            "subject_awareness": "Subject awareness",
            "camera_engagement": "Camera engagement",
        }
        return "\n".join(
            f"{labels[field]}: {getattr(self, field)}"
            for field in EDITORIAL_DIRECTION_FIELDS
        )


def build_editorial_direction_instruction(concept: str) -> str:
    return f"""
Analyze the selected visual concept and derive its editorial direction naturally.
Do not use a fixed mood mapping or default to cheerful, friendly, smiling,
commercial portrait, or lifestyle-influencer energy.

SELECTED SCENE
{concept}

{EXPLICIT_EDITORIAL_GUIDANCE.planning_instruction()}

Return one JSON object with exactly these string fields:
{", ".join(EDITORIAL_DIRECTION_FIELDS)}

Each value must describe only the emotional or visual performance implied by
the scene. Preserve explicit expression, gaze, posture, viewer engagement, or
focus on another activity when supplied. Do not add scene, wardrobe, identity,
quality, safety, or provider instructions. No markdown or commentary.
""".strip()


def parse_editorial_direction(value: str, concept: str) -> EditorialDirection:
    cleaned = str(value or "").strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    data = {}
    if match:
        try:
            candidate = json.loads(match.group(0))
            if isinstance(candidate, dict):
                data = candidate
        except (TypeError, ValueError, json.JSONDecodeError):
            data = {}
    fallback = (
        "Preserve the direction naturally implied by the selected scene; "
        "do not impose a commercial portrait expression"
    )
    return EditorialDirection(
        **{
            field: str(data.get(field) or fallback).strip()
            for field in EDITORIAL_DIRECTION_FIELDS
        }
    )


def derive_editorial_direction(concept: str, api_key: str) -> EditorialDirection:
    response = generate_prompts_with_grok(
        build_editorial_direction_instruction(concept),
        api_key,
    )
    return parse_editorial_direction(response, concept)


def extract_editorial_direction(prompt: str) -> dict[str, str]:
    text = str(prompt or "")
    match = re.search(
        r"EDITORIAL DIRECTION\s*\n(?P<body>.*?)(?:\n\n[A-Z][A-Z ]+\n|\Z)",
        text,
        flags=re.DOTALL,
    )
    if not match:
        return {}
    labels = {
        "emotional tone": "emotional_tone",
        "facial expression": "facial_expression",
        "eye contact": "eye_contact",
        "body language": "body_language",
        "editorial energy": "editorial_energy",
        "visual storytelling": "visual_storytelling",
        "subject awareness": "subject_awareness",
        "camera engagement": "camera_engagement",
    }
    result = {}
    for line in match.group("body").splitlines():
        label, separator, value = line.partition(":")
        field = labels.get(label.strip().lower())
        if separator and field and value.strip():
            result[field] = value.strip()
    return result

MAX_ENHANCED_EXPLICIT_TAGS_PER_LINE = 16
MAX_ENHANCED_EXPLICIT_TAG_WORDS = 14

# ==================== REALISTIC & INTIMATE EXPLICIT RULES ====================
EXPLICIT_ACTION_RULES = """
EXPLICIT ACTION RULES - REALISTIC CREATOR PPV / INTIMATE STYLE

This lane is for paid NSFW PPV content. Preserve sexual explicitness; do not soften hardcore
intent into soft teasing, lingerie editorial, or tasteful almost-nude framing.

Only include a dildo or toy if the user explicitly mentions "dildo", "toy", "insertion", "riding", or similar terms.
When a dildo is mentioned:
- Use a thick but realistically proportioned dildo (natural human size, not oversized)
- Do not force purple color unless the user specifically says "purple". Use any realistic color.
- Show believable natural vaginal insertion with realistic stretching and tight fit (avoid extreme gaping)

For general masturbation, touching, or spreading prompts (without mentioning a toy):
- Focus only on manual stimulation, fingers, rubbing, grinding, etc.
- Do NOT add any dildo or toy

General rules:
- Sexual fluids are opt-in only. Do NOT invent dripping, squirting, juices, creamy discharge,
  soaked genitals, wet-arousal trails, oil/lube pools, or shiny liquid running down the body.
- Include glistening fluids / wet arousal ONLY if the operator explicitly requested wetness with
  words such as wet, dripping, creamy, soaked, squirt, juices, lube, or oil.
- If wetness was not requested, keep skin dry and photorealistic (normal shower water is allowed
  only when the scene is actually a shower/bath environment).
- Prefer sellable hardcore poses with face + body + sexual action readable together.
  Avoid escalating into medical crotch-macro framing unless the concept already requires it.
- Natural anatomy: photorealistic proportions; avoid deformed or diagram-like genitals
- When the user/inspiration already names pussy, clit, labia, fingering, spreading, ass up,
  oral tease, masturbation, or similar sexual acts, keep that sexual act and those anatomical
  words — do not rewrite them into vague "sensual pose" or "state of undress" language
- Keep poses natural and intimate like private paid-for creator photos for the viewer
- Focus on realistic intimate sexual posing rather than cartoon gonzo exaggeration
"""

# Sexual-fluid language is opt-in only (operator-prompted). Inspire Me must not invent it.
_FLUID_OPT_IN_RE = re.compile(
    r"\b(?:wet|dripping|drips|drip|creamy|soaked|sopping|drenched|squirt(?:ing|ed|s)?|"
    r"juices?|fluids?|lube|lubricant|slick)\b",
    re.IGNORECASE,
)
_FLUID_STRIP_PATTERNS = (
    r"\b(?:glistening|shiny|slick|creamy|thick)?\s*(?:juices?|fluids?|discharge)\b",
    r"\b(?:squirting|squirted|squirts)\b",
    r"\b(?:dripping|drips|drip|drooling)\b",
    r"\b(?:soaked|sopping|drenched)\b",
    r"\bwet\s+(?:arousal|pussy|cunt|slit|lips|thighs|ass|asshole)\b",
    r"\b(?:trail|string|strings|stream|streams)\s+of\s+(?:slick|wetness|juices?|fluids?)\b",
    r"\b(?:oil|lube|lubricant)\s+(?:on|across|down|pooling|pools?)\b",
    r"\b(?:arousal|pussy|cunt)\s+(?:juices?|fluids?|slick)\b",
    r"\b(?:running|runs|run)\s+down\s+(?:her\s+)?(?:thighs?|legs?|ass|asshole|pussy)\b",
    r"\bleaving\s+a\s+visible\s+trail\s+of\s+slick\b",
)


def operator_requested_fluids(*parts: str | None) -> bool:
    blob = " ".join(str(part or "") for part in parts)
    return bool(_FLUID_OPT_IN_RE.search(blob))


def strip_unsolicited_fluids(text: str) -> str:
    raw = str(text or "")
    if not raw.strip():
        return ""
    # Preserve newlines/structure used by SCENE / provider sections.
    # Only remove fluid phrases; do not strip legitimate punctuation.
    lines = []
    for line in raw.splitlines():
        cleaned = line
        for pattern in _FLUID_STRIP_PATTERNS:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r" +([,.;:])", r"\1", cleaned)
        cleaned = re.sub(r"([,.;:]){2,}", r"\1", cleaned)
        cleaned = re.sub(r"[ \t]+$", "", cleaned)
        cleaned = re.sub(r"^[ \t]+", "", cleaned)
        lines.append(cleaned)
    return "\n".join(lines).strip()

IDENTITY_LOCK_RULES = """
REFERENCE IDENTITY LOCK
Use the reference image for identity, face, hair, skin tone, body shape, and bust-size continuity only.
Every generated prompt must preserve the reference woman exactly:
- same face
- same facial structure
- same hair color
- same long dark hair worn down
- same smooth flat natural hair top
- same loose flowing hair over her shoulders or down her back
- same natural sun-kissed skin tone as the reference image
- same body
- same body proportions
- same bust size
- full natural D-cup breast proportions
- full natural D-cup breast volume
- same feminine hourglass body
- same waist-to-hip proportions
- same overall identity from the reference image
Do not change her hair color.
Do not put her hair in a bun, topknot, ponytail, updo, piled style, lifted tied hairstyle, messy crown, or any tall hair shape.
Do not copy or inherit the reference image's setting, background, boat, dock, railing, lake, natural water, trees, cabin, furniture, outfit, pose, lighting, camera angle, or props unless the user's Explicit Tags or Optional Setting explicitly request those exact elements.
The user's Explicit Tags, Enhanced Explicit Tags, and Optional Setting / Direction are the only source of truth for setting, wardrobe, nudity state, pose, activity, lighting, and background.
If the user asks for shower, bathroom, bedroom, hotel, couch, pool, city, beach, or any non-boat scene, do not include boat, lake, dock, marina, railing, or outdoor natural-water elements from the reference image.
"""

HAIR_CONTINUITY_RULES = """
EXPLICIT HAIR CONTINUITY LOCK
Explicit prompts must preserve the same Premium Studio hair identity:
- long dark hair worn down naturally
- soft center part or natural side part
- smooth flat natural top
- loose flowing hair over her shoulders, around her face, or down her back
- full forehead, hairline, crown, and smooth hair top visible with clean breathing room above the hair

Avoid every tied-up or tall-hair variant:
- no bun
- no hairbun
- no topknot
- no ponytail
- no updo
- no piled hair
- no lifted tied hair
- no messy crown
- no large hair clump above the scalp

If wet hair is requested, keep it worn down as loose wet hair, not tied up.
"""

BODY_AND_FRAMING_LOCK_RULES = """
BODY, SKIN TONE, AND FRAMING CONTINUITY LOCK
Every generated prompt must explicitly preserve:
- same natural sun-kissed skin tone as the reference image
- same full natural D-cup bust
- same feminine hourglass body
- same waist-to-hip proportions
- same visible body size and recognizable body structure from the reference image

Bust visibility rules:
- preserve visibly full natural D-cup breast volume, not a petite or minimized bust
- do not reduce, flatten, minimize, shrink, hide, or soften her bust size
- make cleavage, bust projection, rounded lower-breast fullness, upper-breast fullness, and cup fill clearly visible whenever framing and wardrobe allow it
- when wearing a bikini, lingerie, bra, crop top, fitted shirt, dress, bodysuit, swimwear, or any tight clothing, show realistic fabric tension from full D-cup volume
- use torso angle, chest-forward posture, side angle, three-quarter angle, seated lean, or close upper-body crop to make bust size obvious
- avoid loose clothing, straight-on flat posture, hair coverage, arm coverage, shadows, or crops that hide or visually reduce bust volume
- if a bikini top or bra is present, the cups must look visibly filled and slightly tensioned by full natural D-cup volume

Skin tone rules:
- keep the skin tone natural, even, sun-kissed, and photorealistic
- preserve the same reference skin tone across face, chest, arms, waist, hips, and legs when visible
- do not make her pale, washed out, overly dark, over-tanned, red-haired, or a different ethnicity

Framing rules:
- MANDATORY: use tight creator framing unless the user explicitly asks for a wide shot
- use close-up, close-medium, waist-up, head-to-hips, head-to-upper-thigh, upper-thigh, or intimate seated close framing
- make her face, upper body, torso, bust, waist, and hip angle visually dominant in the composition
- keep her full face and full head inside the frame, including forehead, hairline, and crown, with a small amount of breathing room above her hair
- keep the camera close enough that her full natural D-cup bust, hourglass waist, and reference skin tone are obvious
- keep her body large in frame, with the background supporting the scene rather than dominating it
- avoid wide bed shots, wide room shots, distant mattress compositions, distant full-body shots, scenery-dominant lake/pool/landscape shots, or any framing where the bed/furniture/room/water/landscape is more visually important than her body
- avoid distant full-body compositions unless the user explicitly asks for a wide shot
- avoid cropped-off forehead, cropped hairline, cut-off crown, missing top of head, or a composition that slices through her hair
- do not crop out the body cues needed to preserve her D-cup bust, hourglass shape, and reference skin tone
- write the crop explicitly using phrases like "tight waist-up creator crop with full head in frame", "head-to-upper-thigh close crop with headroom above hair", "close-medium upper-body framing with full face and crown visible", or "upper-thigh intimate crop with full head visible"
- do not use side/rear all-fours angles that hide or minimize the bust; if using side/rear body orientation, keep the chest/bust still visible and prominent
"""

TOPLESS_VISIBILITY_RULES = """
TOPLESS / NUDE VISIBILITY RULES
If topless, bare breasts, nude, naked, or upper body uncovered content is requested:
- every topless prompt must clearly preserve bare breasts
- nipples must be visible
- nipples must be perky and visible
- keep nipple size, placement, symmetry, and perkiness consistent across the batch
- nipples should look natural, centered on each breast, proportionate to her full natural D-cup bust, and clearly visible when breasts are exposed
- do not hide nipples with hair, arms, hands, furniture, sheets, pillows, or props
- preserve full natural D-cup breast proportions and volume
- preserve rounded upper and lower breast fullness, natural breast projection, and consistent nipple placement
"""

NUDITY_GROOMING_RULES = """
NUDITY GROOMING RULES
If nude, naked, fully nude, lower body visible, or pubic area visible content is requested:
- no pubic hair under any circumstances
- keep the pubic area fully smooth and clean-shaven
- do not add a landing strip, stubble, trimmed hair, shadow hair, peach fuzz, or any visible pubic hair texture
- if the pubic area is visible, it must remain completely hairless and smooth
"""

USER_TAG_PRESERVATION_RULES = """
USER TAG PRESERVATION RULES
All user-supplied Explicit Tags are mandatory anchor concepts.
The AI may expand and enrich them but must not ignore or replace them.
For single-line tags, every final prompt must preserve the user's core explicit intent, environment, time, nudity/wardrobe state, body state, and sexual action.
For multi-line tags, every final prompt must preserve every concrete tag from its matching concept line only.
If the matching tags include environment, time, wardrobe state, nudity state, body state, wetness, or sexual action, that prompt must include those concepts.
Do not treat the core explicit idea as optional inspiration.
Vary activity, pose, camera angle, hand placement, lighting nuance, body orientation, framing, and micro-story without changing immutable environment, time, clothing, or nudity requirements.
"""

SETTING_RULES = """
ENVIRONMENT AND SETTING RULES
If the user supplied an environment tag, that environment is immutable.
Do not reinterpret an immutable environment as a nearby luxury architecture scene, indoor scene, balcony scene, patio scene, rooftop scene, hotel scene, deck scene, or pool scene unless that substitute environment was explicitly requested.
If the Optional Setting / Direction field is blank, still preserve any environment and time found in Explicit Tags or Enhanced Explicit Tags.
If the Optional Setting / Direction field is supplied, treat it as mandatory creative direction and merge it with the immutable requirements.
Generate diversity only inside the requested environment through activity, pose, body orientation, camera angle, framing, foreground texture, lighting nuance, weather, emotion, and micro-story.
Do not make the batch look like one repeated pose, but never change the requested environment to create variety.
If framing language such as full body, wide shot, environmental shot, mirror selfie, waist-up, close-up, medium shot, or upper-thigh framing is supplied, follow that framing direction even when it differs from the default close-framing preference.
Still preserve her full natural D-cup bust, feminine hourglass body, same waist-to-hip proportions, same natural sun-kissed skin tone as the reference image, and recognizable body structure.
"""

PROMPT_DIVERSITY_RULES = """
PROMPT DIVERSITY RULES
For every batch of prompts:
- Create natural variety within the immutable environment when one is supplied.
- Vary poses, camera angles, framing, and scene rhythm.
- Prefer chest-forward, upper-body-forward, tight medium crops over wide bedroom or wide bed compositions.
- Avoid repeatedly using wide beds, large mattresses, broad room descriptions, or distant all-fours shots that make the body continuity less visible.
- Generate the feeling of authentic, private, "in the moment" intimate scenes rather than a uniform photoshoot.
- Maintain the same woman, core body continuity, immutable environment, immutable time, and immutable wardrobe/nudity state.
- Do not repeat the same location type more than twice in a batch of 10.
- Do not let "bed", "hotel room", or "bathroom" dominate the whole batch unless the user explicitly asks for that.
"""

EXPRESSION_PERSONALITY_RULES = """
FACIAL EXPRESSION PIPELINE
Do not invent or modify facial-expression wording inside the generated scene.
The canonical Explicit Expression Profile is the sole facial-expression authority
and is applied after Editorial Direction.
Keep scene, pose, activity, wardrobe, lighting, camera distance, and composition
complete without competing with that profile.
"""

EXPLICIT_BODY_POSE_RULES = """
EXPLICIT BODY POSE RULES
For explicit Fanvue content, lean into realistic viewer connection through hands, hips, torso angle, body orientation, camera distance, and body language.

Every explicit prompt should include concrete adult body pose direction, such as:
- arched back to emphasize chest, waist, hips, and thighs
- hips rolled forward or angled toward the camera
- chest pushed forward with shoulders relaxed
- one hand gripping fabric, sheets, thigh, hip, waist, or breast when appropriate
- thighs parted or knees angled to create a more intimate pose when consistent with the user tags
- torso twisted three-quarter toward camera so face, bust, waist, and hips stay visible
- seated, kneeling, reclining, couch-edge, bed-edge, mirror, shower, or counter poses with intentional adult body language
- close creator framing that captures face, torso, hands, hips, and thighs together

Keep the body language realistic, adult, and intimate rather than theatrical or exaggerated.
Do not use blank model posing, stiff fashion posing, detached body language, or generic beauty-shot language.
Vary body pose across the batch.
"""

# ==================== HELPER FUNCTIONS ====================
TOPLESS_TERMS = ["topless", "bare breasts", "bare breast", "nude", "nudity", "naked", "upper body uncovered", "no upper-body clothing", "no bra", "no top"]
NUDE_LOWER_BODY_TERMS = ["nude", "nudity", "naked", "fully nude", "completely nude", "bare body", "lower body visible", "pubic area"]

NIPPLE_VISIBILITY_PHRASE = (
    "topless with bare breasts and perky visible nipples unobstructed, "
    "consistent natural nipple size and placement, symmetrical perky nipples, "
    "no bra, no bikini top, no lingerie top, no swimsuit top, no shirt, "
    "no crop top, no upper-body clothing"
)
NUDITY_GROOMING_PHRASE = (
    "no pubic hair under any circumstances, fully smooth clean-shaven pubic area, "
    "no landing strip, no stubble, no trimmed hair, no visible pubic hair texture"
)
BODY_CONTINUITY_PHRASE = (
    "same natural sun-kissed skin tone as the reference image, full natural D-cup bust, feminine hourglass body, "
    "same waist-to-hip proportions, tight medium head-to-upper-thigh creator framing, "
    "upper body and torso dominant, chest and bust clearly visible, body large in frame, "
    "no wide room or wide bed composition"
)
EXPLICIT_ANCHOR_TAGS = [
    "full natural D-cup bust",
    "consistent perky visible nipples when breasts are exposed",
    "fully smooth clean-shaven pubic area when visible",
    "no pubic hair under any circumstances",
    "feminine hourglass body",
    "same waist-to-hip proportions",
    "same natural sun-kissed skin tone as the reference image",
    "long dark hair worn down with smooth flat natural top",
    "no bun/topknot/ponytail/updo",
    "full head visible with clean headroom above hair",
    "tight head-to-upper-thigh creator framing",
]

ENVIRONMENT_PROFILES = {
    "beach": {
        "aliases": [
            "beach",
            "sand",
            "shoreline",
            "surf",
            "waves",
            "ocean water",
            "dunes",
        ],
        "forbidden": [
            "balcony",
            "patio",
            "rooftop",
            "hotel",
            "veranda",
            "deck",
            "courtyard",
        ],
        "fallback": (
            "true beach setting with visible sand, shoreline, waves, "
            "and ocean water"
        ),
        "replacement": "beach shoreline",
    },
    "pool": {
        "aliases": [
            "pool",
            "pool edge",
            "pool water",
            "pool steps",
            "poolside",
        ],
        "forbidden": [
            "beach",
            "shoreline",
            "ocean",
            "waves",
            "sand",
            "hotel room",
            "bedroom",
        ],
        "fallback": "true pool setting with visible pool water",
        "replacement": "pool edge",
    },
    "bedroom": {
        "aliases": [
            "bedroom",
            "bed",
            "bedsheets",
            "bedding",
            "headboard",
        ],
        "forbidden": [
            "beach",
            "pool",
            "balcony",
            "rooftop",
            "patio",
            "shoreline",
        ],
        "fallback": "true bedroom setting with visible bed and bedding",
        "replacement": "bedroom",
    },
    "bathroom": {
        "aliases": [
            "bathroom",
            "vanity",
            "mirror",
            "tile",
            "bathtub",
        ],
        "forbidden": [
            "beach",
            "pool",
            "bedroom",
            "balcony",
            "rooftop",
            "patio",
        ],
        "fallback": "true bathroom setting with visible tile and vanity",
        "replacement": "bathroom vanity",
    },
    "shower": {
        "aliases": [
            "shower",
            "shower stall",
            "shower glass",
            "wet tile",
            "running water",
        ],
        "forbidden": [
            "beach",
            "pool",
            "bedroom",
            "balcony",
            "rooftop",
            "patio",
        ],
        "fallback": "true shower setting with visible shower water and wet tile",
        "replacement": "shower",
    },
    "hotel": {
        "aliases": [
            "hotel",
            "hotel suite",
            "hotel room",
            "suite",
        ],
        "forbidden": [
            "beach",
            "pool",
            "rooftop",
            "patio",
            "courtyard",
        ],
        "fallback": "true hotel suite setting",
        "replacement": "hotel suite",
    },
    "balcony": {
        "aliases": [
            "balcony",
            "balcony railing",
            "terrace railing",
        ],
        "forbidden": [
            "beach",
            "pool",
            "bedroom",
            "bathroom",
            "hotel room",
        ],
        "fallback": "true balcony setting with visible balcony railing",
        "replacement": "balcony railing",
    },
    "rooftop": {
        "aliases": [
            "rooftop",
            "roof terrace",
            "roof deck",
        ],
        "forbidden": [
            "beach",
            "pool",
            "bedroom",
            "bathroom",
            "hotel room",
        ],
        "fallback": "true rooftop setting with visible rooftop edge",
        "replacement": "rooftop",
    },
    "patio": {
        "aliases": [
            "patio",
            "private patio",
            "paved patio",
        ],
        "forbidden": [
            "beach",
            "pool",
            "bedroom",
            "bathroom",
            "rooftop",
        ],
        "fallback": "true patio setting with visible patio surface",
        "replacement": "patio",
    },
    "couch": {
        "aliases": [
            "couch",
            "sofa",
            "sectional",
        ],
        "forbidden": [
            "beach",
            "pool",
            "rooftop",
            "patio",
            "balcony",
        ],
        "fallback": "true couch setting with visible couch cushions",
        "replacement": "couch",
    },
    "kitchen": {
        "aliases": [
            "kitchen",
            "kitchen counter",
            "kitchen island",
        ],
        "forbidden": [
            "beach",
            "pool",
            "bedroom",
            "bathroom",
            "rooftop",
        ],
        "fallback": "true kitchen setting with visible kitchen counter",
        "replacement": "kitchen counter",
    },
    "lake": {
        "aliases": [
            "lake",
            "lakeside",
            "lake water",
            "dock",
        ],
        "forbidden": [
            "beach",
            "ocean",
            "pool",
            "hotel",
            "rooftop",
        ],
        "fallback": "true lakeside setting with visible lake water",
        "replacement": "lakeside",
    },
}

TIME_TAGS = [
    "night",
    "midnight",
    "evening",
    "dusk",
    "sunset",
    "sunrise",
    "morning",
    "afternoon",
    "daylight",
    "golden hour",
    "blue hour",
]

CLOTHING_NUDITY_TAGS = [
    "topless",
    "nude",
    "naked",
    "bare breasts",
    "visible nipples",
    "thong",
    "panties",
    "lingerie",
    "bra",
    "robe",
    "bikini",
    "swimsuit",
    "shirt",
    "crop top",
    "shorts",
    "dress",
    "skirt",
]

MOOD_TAGS = [
    "romantic",
    "intimate",
    "playful",
    "teasing",
    "confident",
    "moody",
    "soft",
    "candid",
    "private",
]

ACTIVITY_TAGS = [
    "standing",
    "sitting",
    "kneeling",
    "reclining",
    "lying",
    "walking",
    "leaning",
    "touching",
    "posing",
    "arching",
]

STYLE_TAGS = [
    "photorealistic",
    "selfie",
    "mirror selfie",
    "creator",
    "cinematic",
    "raw photo",
    "editorial",
    "glamour",
    "lifestyle",
]

def normalize_prompt_suffix(prompt: str, suffix: str = QUALITY_SUFFIX) -> str:
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt:
        return ""
    cleaned_prompt = cleaned_prompt.rstrip(" ,.")
    normalized_suffix = suffix.strip().rstrip(" ,.")
    cleaned_prompt = re.sub(
        re.escape(normalized_suffix),
        "",
        cleaned_prompt,
        flags=re.IGNORECASE,
    ).rstrip(" ,.")
    if cleaned_prompt.lower().endswith(normalized_suffix.lower()):
        return cleaned_prompt
    return f"{cleaned_prompt}, {normalized_suffix}"

def references_topless_content(text: str) -> bool:
    text_lower = (text or "").lower()
    return any(term in text_lower for term in TOPLESS_TERMS)

def references_nude_lower_body_content(text: str) -> bool:
    text_lower = (text or "").lower()
    return any(term in text_lower for term in NUDE_LOWER_BODY_TERMS)

def normalize_topless_visibility(prompt: str) -> str:
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt or not references_topless_content(cleaned_prompt):
        return cleaned_prompt
    prompt_lower = cleaned_prompt.lower()
    if (
        "visible nipple" in prompt_lower
        and "perky" in prompt_lower
        and "consistent" in prompt_lower
    ):
        return cleaned_prompt
    cleaned_prompt = cleaned_prompt.rstrip(" ,.")
    return f"{cleaned_prompt}, {NIPPLE_VISIBILITY_PHRASE}"

def normalize_nudity_grooming(prompt: str) -> str:
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt or not references_nude_lower_body_content(cleaned_prompt):
        return cleaned_prompt
    prompt_lower = cleaned_prompt.lower()
    if (
        "no pubic hair" in prompt_lower
        and "smooth" in prompt_lower
        and ("clean-shaven" in prompt_lower or "hairless" in prompt_lower)
    ):
        return cleaned_prompt
    cleaned_prompt = cleaned_prompt.rstrip(" ,.")
    return f"{cleaned_prompt}, {NUDITY_GROOMING_PHRASE}"

def normalize_body_continuity(prompt: str) -> str:
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt:
        return ""

    prompt_lower = cleaned_prompt.lower()
    required_fragments = [
        (
            "same natural sun-kissed skin tone as the reference image",
            "same natural sun-kissed skin tone as the reference image",
        ),
        ("full natural d-cup bust", "full natural D-cup bust"),
        ("feminine hourglass body", "feminine hourglass body"),
        ("same waist-to-hip proportions", "same waist-to-hip proportions"),
        ("tight medium", "tight medium head-to-upper-thigh creator framing"),
        ("upper body", "upper body and torso dominant"),
        ("body large in frame", "body large in frame"),
        ("wide room", "no wide room or wide bed composition"),
    ]

    missing_fragments = [
        fragment
        for term, fragment in required_fragments
        if term not in prompt_lower
    ]

    if not missing_fragments:
        return cleaned_prompt

    cleaned_prompt = cleaned_prompt.rstrip(" ,.")
    return f"{cleaned_prompt}, {', '.join(missing_fragments)}"

def normalize_hair_continuity(prompt: str) -> str:
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt:
        return ""

    prompt_lower = cleaned_prompt.lower()
    required_fragments = [
        ("long dark hair", "long dark hair worn down naturally"),
        ("smooth flat natural", "smooth flat natural hair top"),
        ("no bun", "no bun/topknot/ponytail/updo, no piled hair, no lifted tied hair, no tall hair shape"),
        ("headroom above", "full forehead, hairline, crown, and smooth hair top visible with clean headroom above hair"),
    ]

    missing_fragments = [
        fragment
        for term, fragment in required_fragments
        if term not in prompt_lower
    ]

    if not missing_fragments:
        return cleaned_prompt

    cleaned_prompt = cleaned_prompt.rstrip(" ,.")
    return f"{cleaned_prompt}, {', '.join(missing_fragments)}"


def enforce_explicit_concept_fidelity(
    prompt: str,
    concept: str,
    editorial_direction: EditorialDirection,
    expression_profile: ExplicitExpressionProfile,
) -> str:
    """Layer canonical enrichment on top of the immutable selected concept."""
    cleaned_prompt = (prompt or "").strip()
    cleaned_concept = (concept or "").strip()
    if not cleaned_prompt or not cleaned_concept:
        return cleaned_prompt
    return "\n\n".join(
        (
            f"SCENE\n{cleaned_concept.rstrip(' .')}.",
            (
                "EXPLICIT EDITORIAL GUIDANCE\n"
                f"{EXPLICIT_EDITORIAL_GUIDANCE.provider_section()}"
            ),
            f"EDITORIAL DIRECTION\n{editorial_direction.render()}",
            f"{EXPLICIT_EXPRESSION_SECTION}\n{expression_profile.render()}",
            (
                "WARDROBE\nPreserve the exact wardrobe and state of undress "
                "specified by the Scene; do not substitute or cover it."
            ),
            (
                "CREATOR IDENTITY\nPreserve reference face, body, skin tone, "
                "hair, and proportions without importing its scene."
            ),
            f"VISUAL QUALITY\n{cleaned_prompt}",
        )
    )


def split_user_tags(raw_tags: str) -> list[str]:
    if not raw_tags:
        return []
    return [tag.strip() for tag in raw_tags.split(",") if tag.strip()]

def _contains_tag_term(text: str, term: str) -> bool:
    normalized_text = f" {re.sub(r'[^a-z0-9]+', ' ', text.lower())} "
    normalized_term = f" {re.sub(r'[^a-z0-9]+', ' ', term.lower()).strip()} "
    return normalized_term in normalized_text


def _matching_terms(text: str, terms: list[str]) -> list[str]:
    return [
        term
        for term in terms
        if _contains_tag_term(text, term)
    ]


def categorize_explicit_tags(
    tags: str,
    optional_setting: str | None = None,
) -> dict[str, list[str]]:
    combined_text = ", ".join(
        part
        for part in [
            tags or "",
            optional_setting or "",
        ]
        if part
    )

    environment = [
        environment_name
        for environment_name, profile in ENVIRONMENT_PROFILES.items()
        if _matching_terms(combined_text, profile["aliases"])
    ]

    return {
        "environment": environment,
        "time": _matching_terms(combined_text, TIME_TAGS),
        "clothing_nudity": _matching_terms(combined_text, CLOTHING_NUDITY_TAGS),
        "mood": _matching_terms(combined_text, MOOD_TAGS),
        "activity": _matching_terms(combined_text, ACTIVITY_TAGS),
        "style": _matching_terms(combined_text, STYLE_TAGS),
    }


def _format_category_items(items: list[str]) -> str:
    return ", ".join(items) if items else "none detected"


def build_environment_preservation_rules(categories: dict[str, list[str]]) -> str:
    requested_environments = categories.get("environment", [])

    if not requested_environments:
        return (
            "No immutable environment was detected. You may choose varied "
            "settings that fit the explicit concept."
        )

    rules = []
    for environment_name in requested_environments:
        profile = ENVIRONMENT_PROFILES[environment_name]
        aliases = ", ".join(profile["aliases"])
        forbidden = [
            term
            for term in profile["forbidden"]
            if term not in requested_environments
        ]
        forbidden_text = ", ".join(forbidden) if forbidden else "none"
        rules.append(
            f"- {environment_name.upper()} is immutable. Every generated "
            f"prompt must clearly remain a true {environment_name} scene and "
            f"must include at least one of: {aliases}. Do not substitute: "
            f"{forbidden_text}, unless explicitly requested as a separate "
            "immutable environment."
        )

    return "\n".join(rules)


def build_immutable_requirements_context(
    tags: str,
    optional_setting: str | None = None,
) -> str:
    categories = categorize_explicit_tags(
        tags=tags,
        optional_setting=optional_setting,
    )

    return f"""
IMMUTABLE REQUIREMENTS
Environment: {_format_category_items(categories["environment"])}
Time: {_format_category_items(categories["time"])}
Clothing/Nudity: {_format_category_items(categories["clothing_nudity"])}

Environment preservation rules:
{build_environment_preservation_rules(categories)}

Never reinterpret immutable requirements. If an environment, time, clothing item, or nudity state appears above, every prompt must preserve it literally.

CREATIVE FREEDOM
Mood: {_format_category_items(categories["mood"])}
Activity: {_format_category_items(categories["activity"])}
Style: {_format_category_items(categories["style"])}

Use creative freedom only to enrich details the selected concept did not specify.
Environment, story premise, wardrobe/undress state, framing, camera angle, body
position/composition, lighting, mood, explicit activity, requested visibility,
and scene progression are immutable whenever the selected concept specifies them.
Do not create diversity by changing or replacing any specified concept field.
""".strip()


def enforce_prompt_environment_preservation(
    prompt: str,
    categories: dict[str, list[str]],
) -> str:
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt:
        return ""

    prompt_lower = cleaned_prompt.lower()
    requested_environments = categories.get("environment", [])

    for environment_name in requested_environments:
        profile = ENVIRONMENT_PROFILES[environment_name]
        requested_aliases = profile["aliases"]
        forbidden_terms = [
            term
            for term in profile["forbidden"]
            if term not in requested_environments
        ]

        for forbidden_term in forbidden_terms:
            cleaned_prompt = re.sub(
                rf"\b{re.escape(forbidden_term)}\b",
                profile["replacement"],
                cleaned_prompt,
                flags=re.IGNORECASE,
            )

        prompt_lower = cleaned_prompt.lower()
        if not any(
            _contains_tag_term(prompt_lower, alias)
            for alias in requested_aliases
        ):
            cleaned_prompt = (
                f"{cleaned_prompt.rstrip(' ,.')}, "
                f"{profile['fallback']}"
            )

    return cleaned_prompt


def normalize_tag_key(tag: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        re.sub(r"[^a-z0-9]+", " ", tag.lower()),
    ).strip()

def dedupe_explicit_tags(raw_tags) -> str:
    if not raw_tags:
        return ""

    if isinstance(raw_tags, list):
        tag_candidates = [
            tag
            for item in raw_tags
            for tag in split_user_tags(str(item))
        ]
    else:
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
        tag_candidates = split_user_tags(cleaned_text)

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

def dedupe_explicit_tag_lines(raw_tags) -> str:
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
        deduped_line = dedupe_explicit_tags(cleaned_line)
        if not deduped_line:
            continue

        line_key = normalize_tag_key(deduped_line)
        if not line_key or line_key in seen_lines:
            continue

        seen_lines.add(line_key)
        cleaned_lines.append(deduped_line)

    return "\n".join(cleaned_lines)

def is_compact_explicit_tag(tag: str) -> bool:
    cleaned_tag = (tag or "").strip()
    if not cleaned_tag:
        return False

    word_count = len(re.findall(r"\b\w+\b", cleaned_tag))
    if word_count <= MAX_ENHANCED_EXPLICIT_TAG_WORDS:
        return True

    tag_lower = cleaned_tag.lower()
    keep_long_terms = [
        "sun-kissed skin tone",
        "long dark hair worn down",
        "headroom above hair",
        "head-to-upper-thigh",
        "visible nipples",
        "fully smooth pubic",
    ]
    return any(term in tag_lower for term in keep_long_terms)

def append_unique_tag(tags: list[str], tag: str, seen_keys: set[str]) -> None:
    cleaned_tag = (tag or "").strip(" ,.-")
    if not cleaned_tag:
        return

    tag_key = normalize_tag_key(cleaned_tag)
    if not tag_key or tag_key in seen_keys:
        return

    seen_keys.add(tag_key)
    tags.append(cleaned_tag)

def compact_explicit_anchor_line(
    enhanced_line: str,
    raw_line: str | None = None,
) -> str:
    compact_tags = []
    seen_keys = set()

    combined_text = f"{raw_line or ''}, {enhanced_line or ''}"

    # A selected inspiration concept is an immutable creative brief, not merely
    # a source of short tags. Keep it intact even when it is a full sentence.
    if raw_line:
        append_unique_tag(compact_tags, raw_line, seen_keys)

    anchor_tags = list(EXPLICIT_ANCHOR_TAGS)

    if references_topless_content(combined_text):
        anchor_tags.insert(0, "perky visible nipples unobstructed")
        anchor_tags.insert(1, "consistent natural nipple size and placement")

    if references_nude_lower_body_content(combined_text):
        anchor_tags.insert(0, "fully smooth clean-shaven pubic area")
        anchor_tags.insert(1, "no pubic hair under any circumstances")

    for anchor_tag in anchor_tags:
        if len(compact_tags) >= MAX_ENHANCED_EXPLICIT_TAGS_PER_LINE:
            break
        append_unique_tag(compact_tags, anchor_tag, seen_keys)

    for tag in split_user_tags(enhanced_line or ""):
        if len(compact_tags) >= MAX_ENHANCED_EXPLICIT_TAGS_PER_LINE:
            break
        if not is_compact_explicit_tag(tag):
            continue
        append_unique_tag(compact_tags, tag, seen_keys)

    return ", ".join(compact_tags)

def compact_enhanced_explicit_tags(
    enhanced_tags: str,
    raw_explicit_tags: str | None = None,
) -> str:
    if not enhanced_tags:
        return ""

    enhanced_lines = [
        line.strip()
        for line in str(enhanced_tags).splitlines()
        if line.strip()
    ]
    raw_lines = [
        line.strip()
        for line in str(raw_explicit_tags or "").splitlines()
        if line.strip()
    ]

    if not enhanced_lines:
        return ""

    compact_lines = []
    for index, enhanced_line in enumerate(enhanced_lines):
        raw_line = raw_lines[index] if index < len(raw_lines) else raw_explicit_tags
        compact_line = compact_explicit_anchor_line(
            enhanced_line=enhanced_line,
            raw_line=raw_line,
        )
        if compact_line:
            compact_lines.append(compact_line)

    return "\n".join(compact_lines)

def split_numbered_prompts(raw_text) -> list[str]:
    if not raw_text:
        return []
    if isinstance(raw_text, list):
        return [str(item).strip() for item in raw_text if str(item).strip()]
    parts = re.split(r"\n\s*\d+[\.\)]\s+", "\n" + str(raw_text).strip())
    return [part.strip() for part in parts if part.strip()]

# ==================== INSTRUCTIONS ====================
def build_explicit_enhancer_instruction(
    raw_explicit_tags: str,
    optional_setting: str | None = None,
) -> str:
    setting_text = (optional_setting or "").strip()
    immutable_requirements_context = build_immutable_requirements_context(
        tags=raw_explicit_tags,
        optional_setting=optional_setting,
    )
    categories = categorize_explicit_tags(
        tags=raw_explicit_tags,
        optional_setting=optional_setting,
    )
    line_count = len([line for line in str(raw_explicit_tags).splitlines() if line.strip()])
    if setting_text:
        setting_instruction = (
            f"The user supplied this optional setting/framing direction: {setting_text}. "
            "Preserve it as a mandatory creative direction."
        )
    elif categories["environment"]:
        setting_instruction = (
            "No optional setting was supplied, but the user supplied an "
            "immutable environment in Explicit Tags. Preserve that exact "
            "environment in the enhanced tags."
        )
    else:
        setting_instruction = (
            "No setting was supplied. You may choose varied settings that "
            "fit the explicit concept."
        )
    multi_line_instruction = ""
    if line_count > 1:
        multi_line_instruction = f"""
The user supplied {line_count} separate explicit concepts, one concept per line.
Preserve that structure exactly.
Return exactly {line_count} lines.
Each returned line must enhance only the matching input line.
Do not merge lines into one tag list.
Do not let one line's setting, outfit, furniture, lighting, pose, or body state leak into another line.
Do not make every line a bedroom, bed, robe, or warm-lamplight concept unless the input lines already require that.
Each returned line must be one comma-separated explicit tag concept.
"""

    return f"""
You are an expert at creating compact explicit anchor tags for Seedream 4.5.
Raw user tags:
{raw_explicit_tags}
{immutable_requirements_context}
{setting_instruction}
{multi_line_instruction}
{USER_TAG_PRESERVATION_RULES}
{IDENTITY_LOCK_RULES}
{HAIR_CONTINUITY_RULES}
{BODY_AND_FRAMING_LOCK_RULES}
{EXPLICIT_ACTION_RULES}
{EXPLICIT_BODY_POSE_RULES}
{TOPLESS_VISIBILITY_RULES}
{NUDITY_GROOMING_RULES}
The enhancer is NOT the final prompt writer.
Return compact anchor tags only. The next step will expand these into full prompts.
For single-concept input, return ONLY one comma-separated tag list with 10 to 16 short tags.
For multi-line input, return one comma-separated tag concept per line, with 10 to 16 short tags per line.
Each tag should usually be 1 to 8 words.
Preserve the user's concrete NSFW anchors, location, time, body state, wardrobe/nudity state, wetness, and mood.
Add only the minimum reference/body/hair/framing anchors needed for continuity.
Do not write a paragraph.
Do not write full scene prose.
Do not include multiple alternate micro-scenes in one tag list.
Do not include detailed lighting stories, repeated pose chains, or multiple camera angles.
No explanations. No numbering.
Do not create repeated scene blocks.
Do not repeat any tag, phrase, anchor concept, body-continuity phrase, expression, pose detail, lighting phrase, or setting phrase.
Keep each concept once.
Make it compact and non-repetitive.
""".strip()


def build_explicit_prompt_instruction(
    enhanced_explicit_tags: str,
    prompt_count: int,
    optional_setting: str | None = None,
    editorial_directions: tuple[EditorialDirection, ...] = (),
) -> str:
    setting_text = (optional_setting or "").strip()
    immutable_requirements_context = build_immutable_requirements_context(
        tags=enhanced_explicit_tags,
        optional_setting=optional_setting,
    )
    categories = categorize_explicit_tags(
        tags=enhanced_explicit_tags,
        optional_setting=optional_setting,
    )
    line_count = len([line for line in str(enhanced_explicit_tags).splitlines() if line.strip()])
    multi_line_instruction = ""
    if line_count > 1:
        if setting_text:
            setting_instruction = (
                f"Optional setting/framing direction supplied by user: {setting_text}. "
                "Treat this as mandatory for every generated prompt. If it includes camera distance or framing instructions, follow them."
            )
        elif categories["environment"]:
            setting_instruction = (
                "No optional setting supplied by user, but Enhanced Explicit Tags "
                "contain an immutable environment. Preserve that exact environment "
                "in every generated prompt while varying pose, activity, framing, "
                "lighting, and micro-location within it."
            )
        else:
            setting_instruction = (
                "No optional setting supplied by user and no immutable environment "
                "was detected. Treat each concept line as explicit creative "
                "direction, and vary the final setting, pose, lighting, camera "
                "angle, and visual setup across the batch."
            )
        multi_line_instruction = f"""
MULTI-LINE EXPLICIT CONCEPT RULE:
Enhanced Explicit Tags contain {line_count} separate concepts, one concept per line.
Do not merge the lines into one scene.
Prompt 1 should follow line 1, prompt 2 should follow line 2, and continue matching prompt number to concept line until one side runs out.
For each prompt, only the concrete tags from that prompt's matching line are mandatory.
Do not carry a location, outfit, furniture item, lighting setup, pose, or body state from one line into another line.
If there are fewer concept lines than requested prompts, create additional distinct Ava-coded explicit concepts that preserve immutable requirements and vary body state, pose, lighting, and mood.
Do not make every prompt a bedroom, bed, robe, or warm-lamplight scene unless Optional Setting / Direction explicitly requires that.
"""
    else:
        if setting_text:
            setting_instruction = (
                f"Optional setting/framing direction supplied by user: {setting_text}. "
                "Treat this as mandatory. If it includes camera distance or framing instructions, follow them."
            )
        elif categories["environment"]:
            setting_instruction = (
                "No optional setting supplied by user, but Enhanced Explicit Tags "
                "contain an immutable environment. This is Premium Studio, not "
                "the Photoshoot Queue. Preserve the core explicit idea, the exact "
                "environment, time, nudity/wardrobe state, body state, wetness, "
                "and sexual action, while varying pose, lighting, camera angle, "
                "foreground texture, and micro-location inside the requested environment."
            )
        else:
            setting_instruction = (
                "No optional setting supplied by user and no immutable environment "
                "was detected. This is Premium Studio, not the Photoshoot Queue. "
                "Preserve the core explicit idea, nudity/wardrobe state, body "
                "state, wetness, and sexual action, but deliberately vary the "
                "final setting, pose, lighting, camera angle, furniture/background, "
                "and visual setup across the batch."
            )

    editorial_context = "\n\n".join(
        f"CONCEPT {index} EDITORIAL DIRECTION — IMMUTABLE\n{direction.render()}"
        for index, direction in enumerate(editorial_directions, 1)
    )

    return f"""
You are an expert at creating highly realistic, intimate NSFW image prompts for Seedream 4.5.

Enhanced tags:
{enhanced_explicit_tags}

{EXPLICIT_EDITORIAL_GUIDANCE.planning_instruction()}

{editorial_context}

Editorial Direction owns body language, editorial energy, visual storytelling,
subject awareness, and camera engagement. The canonical Explicit Expression
Profile applied after this planning step is the sole authority for facial
expression, emotional presentation, and eye contact. Do not invent a competing
smile, tongue, playful performance, or commercial portrait direction.

{immutable_requirements_context}

{setting_instruction}
{multi_line_instruction}

{IDENTITY_LOCK_RULES}
{HAIR_CONTINUITY_RULES}
{BODY_AND_FRAMING_LOCK_RULES}
{EXPLICIT_ACTION_RULES}
{EXPLICIT_BODY_POSE_RULES}
{TOPLESS_VISIBILITY_RULES}
{NUDITY_GROOMING_RULES}
{USER_TAG_PRESERVATION_RULES}
{SETTING_RULES}
{PROMPT_DIVERSITY_RULES}
{EXPRESSION_PERSONALITY_RULES}

Output requirements:
- Generate exactly {prompt_count} numbered prompts (1., 2., 3. etc.)
- Each prompt must be one detailed, flowing paragraph
- Prioritize extreme photorealism and natural body proportions at all times
- Every prompt must explicitly include same natural sun-kissed skin tone as the reference image
- Every prompt must explicitly include full natural D-cup bust
- Every prompt must include concrete bust visibility details such as natural cleavage, bust projection, rounded lower-breast fullness, visible cup fill, or realistic fabric tension from full D-cup volume
- Every prompt must explicitly include feminine hourglass body
- Every prompt must explicitly include same waist-to-hip proportions
- For single-line tags, every prompt must preserve the core explicit idea, nudity/topless/wardrobe state, body state, wetness, and sexual action from the Enhanced Explicit Tags
- For single-line tags, preserve every specified location, room, furniture, time of day, lighting setup, environmental anchor, pose, framing, camera angle, wardrobe/undress state, explicit activity, requested visibility, and scene progression in every prompt; vary only unspecified details
- For multi-line tags, each prompt must preserve every concrete Enhanced Explicit Tag from its matching concept line only
- Across the batch, each prompt should feel like a different standalone Premium Studio image with different pose, camera angle, lighting, foreground texture, activity, emotion, and visual setup inside the immutable environment
- Do not generate a continuation of one exact scene; that belongs in Photoshoot Queue, not Premium Studio
- Do not repeat bed/bedroom/pillow/mattress framing across the batch unless Optional Setting / Direction explicitly requests a bed-focused batch
- Every prompt must use tight creator framing by default: close-up, close-medium, waist-up, head-to-hips, head-to-upper-thigh, upper-thigh, or intimate seated close framing, unless the user specifically asks for a different framing style in the Optional Setting / Direction field or explicit tags
- Every prompt must include a literal crop phrase such as "tight waist-up creator crop with full head in frame", "head-to-upper-thigh close crop with headroom above hair", "close-medium upper-body framing with full face and crown visible", or "upper-thigh intimate crop with full head visible"
- Every prompt must preserve her long dark hair worn down naturally with a smooth flat natural top, loose flowing hair, and no bun/topknot/ponytail/updo/tall hair shape
- Every prompt must make her face, upper body, torso, bust, waist, and hip angle visually dominant
- Every prompt must keep her full face and full head visible, including forehead, hairline, and crown, with a small amount of breathing room above her hair
- Every prompt must keep her full natural D-cup bust visibly prominent and unobstructed when the upper body is visible
- Every prompt must keep her body large in frame
- Every prompt must avoid wide room shots, wide bed shots, distant mattress compositions, distant full-body shots, scenery-dominant lake/pool/landscape shots, and background-dominant framing
- Create the feeling of private, "in the moment" intimate photos taken just for the viewer
- Use natural, believable lighting in every prompt
- Feature realistic dildo insertion and arousal when relevant
- Maintain natural anatomy and realistic body language
- Do not add a competing facial-expression lock; the canonical Explicit Expression Profile is applied after Editorial Direction
- Every prompt must include one concrete adult body pose detail
- Every prompt must make the pose feel intentionally adult through hips, torso angle, hand placement, thigh position, chest-forward posture, or close viewer-facing body language
- Avoid generic beauty-shot language, blank model posing, and overacted body performance
- End every single prompt with: , {QUALITY_SUFFIX}

Keep the tone sensual and realistic. Avoid cartoonish exaggeration or overly vulgar language.
No commentary.
""".strip()


# ==================== PUBLIC FUNCTIONS ====================
def get_grok_api_key() -> str:
    api_key = os.getenv("GROK_API_KEY")
    if not api_key:
        raise ValueError("Missing GROK_API_KEY in .env")
    return api_key


def enhance_explicit_tags(
    raw_explicit_tags: str,
    optional_setting: str | None = None,
) -> str:
    if not raw_explicit_tags or not raw_explicit_tags.strip():
        raise ValueError("Explicit Tags are required.")
    instruction = build_explicit_enhancer_instruction(
        raw_explicit_tags=raw_explicit_tags,
        optional_setting=optional_setting,
    )
    response = generate_prompts_with_grok(instruction, get_grok_api_key())
    enhanced_tags = (
        dedupe_explicit_tag_lines(response)
        if has_multiple_tag_lines(raw_explicit_tags) or has_multiple_tag_lines(response)
        else dedupe_explicit_tags(response)
    )

    if enhanced_tags:
        return compact_enhanced_explicit_tags(
            enhanced_tags=enhanced_tags,
            raw_explicit_tags=raw_explicit_tags,
        )

    fallback_tags = (
        dedupe_explicit_tag_lines(raw_explicit_tags)
        if has_multiple_tag_lines(raw_explicit_tags)
        else dedupe_explicit_tags(raw_explicit_tags)
    )
    return compact_enhanced_explicit_tags(
        enhanced_tags=fallback_tags,
        raw_explicit_tags=raw_explicit_tags,
    )


def generate_explicit_prompts(
    enhanced_explicit_tags: str,
    prompt_count: int,
    optional_setting: str | None = None,
    original_source: str | None = None,
    concept_tier: str | None = None,
    operator_expression: str | None = None,
    freeflow_expression: bool = False,
) -> list[str]:
    if not enhanced_explicit_tags or not enhanced_explicit_tags.strip():
        raise ValueError("Enhanced Explicit Tags are required.")

    api_key = get_grok_api_key()
    concept_lines = [
        line.strip()
        for line in str(enhanced_explicit_tags).splitlines()
        if line.strip()
    ]
    original_lines = [
        line.strip()
        for line in str(original_source or enhanced_explicit_tags).splitlines()
        if line.strip()
    ]
    LOGGER.info(
        "[Planner] Explicit concept selection concepts=%s prompt_count=%s",
        len(concept_lines), prompt_count,
    )
    editorial_directions = tuple(
        derive_editorial_direction(concept, api_key)
        for concept in concept_lines
    )
    expression_profile = ExplicitExpressionProfileService.build(
        concept_tier=concept_tier,
        operator_expression=operator_expression,
        freeflow_expression=freeflow_expression,
    )
    instruction = build_explicit_prompt_instruction(
        enhanced_explicit_tags=enhanced_explicit_tags,
        prompt_count=prompt_count,
        optional_setting=optional_setting,
        editorial_directions=editorial_directions,
    )

    raw_response = generate_prompts_with_grok(
        instruction,
        api_key,
    )
    prompts = split_numbered_prompts(raw_response)

    immutable_source = str(original_source or enhanced_explicit_tags).strip()
    force_topless_visibility = references_topless_content(immutable_source)
    force_nudity_grooming = references_nude_lower_body_content(immutable_source)
    immutable_categories = categorize_explicit_tags(
        tags=immutable_source,
        optional_setting=optional_setting,
    )

    # Fluids are opt-in only. Keep them when the operator typed wetness terms in
    # Optional Setting or in the original concept/tags. Inspire Me hardcore strips
    # unsolicited fluids before handoff so AI concepts do not count as opt-in.
    allow_fluids = operator_requested_fluids(optional_setting, original_source)

    normalized_prompts = []
    for index, prompt in enumerate(prompts):
        if not prompt.strip():
            continue
        concept = original_lines[min(index, len(original_lines) - 1)]
        if not allow_fluids:
            concept = strip_unsolicited_fluids(concept)
        editorial_direction = editorial_directions[
            min(index, len(editorial_directions) - 1)
        ]
        prompt = enforce_explicit_concept_fidelity(
            prompt,
            concept,
            editorial_direction,
            expression_profile,
        )
        if not allow_fluids:
            prompt = strip_unsolicited_fluids(prompt)

        if force_topless_visibility:
            prompt = (
                normalize_topless_visibility(prompt)
                if references_topless_content(prompt)
                else f"{prompt.rstrip(' ,.')}, {NIPPLE_VISIBILITY_PHRASE}"
            )
        else:
            prompt = normalize_topless_visibility(prompt)

        if force_nudity_grooming:
            prompt = (
                normalize_nudity_grooming(prompt)
                if references_nude_lower_body_content(prompt)
                else f"{prompt.rstrip(' ,.')}, {NUDITY_GROOMING_PHRASE}"
            )
        else:
            prompt = normalize_nudity_grooming(prompt)

        prompt = normalize_hair_continuity(prompt)
        prompt = normalize_body_continuity(prompt)
        prompt = enforce_prompt_environment_preservation(
            prompt,
            immutable_categories,
        )
        normalized_prompts.append(normalize_prompt_suffix(prompt))

    return normalized_prompts[:prompt_count]
