import json
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()

client = OpenAI()


def _normalize_json_field(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
            return [str(parsed)]
        except Exception:
            return [value]

    return [str(value)]


def generate_tease_caption_from_content(content: dict, user_memory: dict | None = None) -> str:
    """
    Generates a short image-aware TEASE caption using stored content metadata.
    Used for image + caption outreach / light engagement.
    """

    user_memory = user_memory or {}

    detected_themes = _normalize_json_field(content.get("detected_themes"))
    suggested_tags = _normalize_json_field(content.get("suggested_tags"))

    prompt = f"""
You are generating a VERY short Fanvue outreach caption to send WITH a teaser image.

GOAL:
Use the image context to spark a reply.

IMPORTANT:
This is NOT a PPV sales caption.
This caption is attached to a free teaser image.

CONTENT:
Classification: {content.get("classification")}
Detected themes: {detected_themes}
Suggested tags: {suggested_tags}
Summary: {content.get("summary")}

USER CONTEXT:
User type: {user_memory.get("user_type", "unknown")}
Value tier: {user_memory.get("user_value_tier", "unknown")}
Attention tier: {user_memory.get("attention_tier", "unknown")}

STYLE:
- short
- casual
- flirty
- inviting
- natural texting style
- should match the image
- should feel like a real creator sent it with the photo

RULES:
- 4 to 12 words only
- 1 sentence only
- 0 or 1 emoji max
- no hashtags
- no sales language
- no mention of AI
- no mention of PPV
- no mention of unlock
- no explicit sexual acts
- no hardcore wording
- ask or imply a reply

GOOD EXAMPLES:
"come keep me company on the couch?"
"i saved you a spot next to me 👀"
"movie night… are you joining me?"
"would this distract you?"
"be honest… cozy or dangerous?"
"should I keep this one?"
"you sitting next to me or behaving?"

BAD EXAMPLES:
"buy this now"
"unlock this"
"I uploaded a new PPV"
"caught you staring"
"hardcore sexual captions"
"giant erotic paragraphs"

Return only the caption.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text.strip()

def generate_text_outreach_opener(user_memory: dict | None = None) -> str:
    """
    Generates a short text-only outreach opener.

    PURPOSE:
    Spark replies from followers / low-tier users without selling.
    This is NOT a PPV caption and has NO image attached.
    """
    user_memory = user_memory or {}

    prompt = f"""
You are generating a VERY short text-only Fanvue outreach opener.

GOAL:
Spark a reply from a follower or low-tier user.

IMPORTANT:
There is NO image attached to this message.
Do NOT reference looking, staring, photos, outfits, poses, or content.

This is NOT a PPV sales message.
Do NOT ask them to buy anything.
Do NOT mention content, unlocks, PPVs, prices, or subscriptions.

PURPOSE:
- get a reply
- create curiosity
- feel playful
- feel lightly flirty
- feel like casual creator texting
- start a low-pressure conversation

USER CONTEXT:
User type: {user_memory.get("user_type", "unknown")}
Value tier: {user_memory.get("user_value_tier", "unknown")}
Attention tier: {user_memory.get("attention_tier", "unknown")}
Outreach attempts: {user_memory.get("outreach_attempts", 0)}
Ignore count: {user_memory.get("outreach_ignore_count", 0)}

STYLE:
- short
- casual
- playful
- lightly naughty
- confident
- conversational
- reply-bait energy

RULES:
- 4 to 12 words only
- 1 sentence only
- use 0 or 1 emoji max
- no hashtags
- no sales language
- no explicit sexual acts
- no nudity descriptions
- no mention of AI
- no visual/image references
- no formal wording
- no generic customer-service tone
- no direct PPV references
- no “I uploaded something”
- no “buy”
- no “unlock”

GOOD EXAMPLES:
"you seem like trouble 👀"
"why do I feel like you’d flirt back?"
"you’ve been way too quiet"
"should I be worried about you tonight?"
"do you always behave this well?"
"are you always this dangerous?"
"something tells me you’re not innocent"
"you better not distract me tonight"

BAD EXAMPLES:
"caught you staring"
"what do you think of this pic"
"would this get your attention"
"hey how’s your day"
"want to buy my content?"
"I uploaded a new PPV"
"check out my new post"

Return only the opener.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text.strip()

def generate_vip_caption_from_content(content: dict, user_memory: dict | None = None) -> str:
    """
    Generates a VIP-level caption (more suggestive, builds tension).
    """

    user_memory = user_memory or {}

    detected_themes = _normalize_json_field(content.get("detected_themes"))
    suggested_tags = _normalize_json_field(content.get("suggested_tags"))

    prompt = f"""
You are generating a VIP caption for a locked Fanvue image.

GOAL:
Make the user want to unlock this content.

IMPORTANT:
This is a SINGLE piece of content, not part of a sequence.
Do NOT imply there is more coming or continuation.

CONTENT:
Classification: {content.get("classification")}
Detected themes: {detected_themes}
Suggested tags: {suggested_tags}

STYLE:
- natural texting style
- low effort
- casual confidence
- slightly flirty

RULES:
- 5 to 10 words
- 1 sentence only
- no emojis
- no hashtags
- no AI mention
- no poetic language
- no “perfect wording”
- no sales tone
- MUST feel like a quick DM, not a caption
- SHOULD feel slightly careless / effortless
- DO NOT sound like marketing or ads

GOOD EXAMPLES:
"this one’s hard to ignore"
"you might like this one"
"this one’s kinda addictive"
"this one just feels different"
"this one’s been on my mind"

Return only the caption.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text.strip()

def generate_premium_caption_from_content(content: dict, user_memory: dict | None = None) -> str:
    """
    Generates a PREMIUM caption (stronger, more direct, still GPT-safe).
    """

    user_memory = user_memory or {}

    detected_themes = _normalize_json_field(content.get("detected_themes"))
    suggested_tags = _normalize_json_field(content.get("suggested_tags"))

    prompt = f"""
You are generating a PREMIUM Fanvue caption.

GOAL:
Drive a purchase for high-value content.

IMPORTANT:
This is a SINGLE premium piece of content.
Do NOT imply continuation or “next part” behavior.

CONTENT:
Classification: {content.get("classification")}
Detected themes: {detected_themes}
Suggested tags: {suggested_tags}

STYLE:
- natural texting style
- confident
- slightly dominant
- low effort (NOT polished)

RULES:
- 5 to 10 words
- 1 sentence only
- no emojis
- no hashtags
- no AI mention
- no poetic language
- no “creative writing”
- DO NOT sound like a product description
- DO NOT use phrases like "blend", "experience", "journey"
- MUST feel like a real person texting casually
- SHOULD feel slightly blunt / direct

GOOD EXAMPLES:
"this one’s on another level"
"this one hits way harder"
"this one’s something else"
"this one just feels different"
"this one’s not for everyone"

Return only the caption.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    return response.output_text.strip()