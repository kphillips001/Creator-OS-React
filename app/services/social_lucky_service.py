import os

from app.services.wavespeed_grok_service import generate_prompts_with_grok

from app.services.ava_personality_service import (
    AVA_PERSONALITY_PROFILE,
    AVA_SOCIAL_CONTENT_FEEL,
)


def generate_lucky_social_tags(prompt_count=10):
    api_key = os.getenv("GROK_API_KEY")

    prompt = f"""
You are the Creative Director for Ava Blackthorne.

Generate exactly {prompt_count} separate creative tag ideas for Ava.

{AVA_PERSONALITY_PROFILE}

{AVA_SOCIAL_CONTENT_FEEL}

Include variety:
- candid around-the-house moments
- sitting on bedroom floor
- casual couch shots
- checking her phone
- coffee at home
- coastal downtown
- beach walks
- lake days
- country roads
- porches
- mountain weekends
- brunch
- farmers market visits
- workday mini skirt moments
- classy evening outfits

Prefer:
- close-up framing
- chest-up framing
- waist-up framing
- seated close framing
- soft natural light
- fitted casual outfits
- denim shorts
- fitted tees
- tank tops
- sundresses
- mini skirts
- cute tops
- relaxed smiles
- playful glances

Avoid:
- wide landscape shots
- distant full-body shots
- scenery-first photos
- luxury influencer lifestyle
- fashion editorial styling
- arrogant expressions

OUTPUT FORMAT:
Return exactly {prompt_count} lines.
Each line must be one comma-separated creative tag idea.
Use commas inside each line.
No numbering.
No bullets.
No markdown.

Example:
candid around-the-house moment, sitting on bedroom floor, gray fitted t-shirt, denim shorts, soft morning light, waist-up framing, relaxed smile, hot girl next door energy
"""

    result = generate_prompts_with_grok(
        prompt,
        api_key,
    )

    if isinstance(result, list):
        return "\n".join(str(item).strip() for item in result if str(item).strip())

    return str(result).strip()
