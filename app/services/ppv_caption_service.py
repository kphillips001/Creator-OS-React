import os
from dotenv import load_dotenv
from openai import OpenAI

from app.services.caption_prompt_guidance import natural_emoji_instruction_bullet


class PPVCaptionService:

    def __init__(self):
        load_dotenv()

        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("OPENAI_API_KEY is missing from .env")

        self.client = OpenAI(api_key=api_key)

    def generate_context_aware_caption(
        self,
        chat_history: list,
        content_metadata: dict,
    ) -> str:

        # ------------------------------------------
        # SESSION TONE (STEP-BASED CONTROL)
        # ------------------------------------------
        session_tone = content_metadata.get("session_tone", "default")

        tone_instruction = ""

        if session_tone == "soft_tease":
            tone_instruction = """
TONE:
- Light, playful, slightly flirty
- Focus on curiosity and intrigue
- Do NOT push hard
- Make them WANT to see more
"""

        elif session_tone == "playful_push":
            tone_instruction = """
TONE:
- More confident and teasing
- Slightly more direct
- Hint at what they're missing
- Create tension and desire
"""

        elif session_tone == "high_intent":
            tone_instruction = """
TONE:
- Confident, seductive, and assertive
- Assume strong interest
- Lean into desire and urgency
- Make it feel irresistible
"""

        else:
            tone_instruction = """
TONE:
- Casual, conversational, lightly flirty
"""

        # ------------------------------------------
        # SYSTEM PROMPT
        # ------------------------------------------
        system_prompt = f"""
You are writing the NEXT message in a private Fanvue conversation.

CRITICAL:
- Continue directly from the LAST message
- Make it feel like a real person texting
- Do NOT sound like a bot or marketer

{tone_instruction}

RULES:
- 1 sentence ONLY
{natural_emoji_instruction_bullet()}
- No explicit descriptions
- No hashtags
- No long sentences
- No generic phrases
- Create curiosity gap
- Feel natural and human
"""

        # ------------------------------------------
        # METADATA PROMPT
        # ------------------------------------------
        metadata_prompt = f"""
Content metadata:
- classification: {content_metadata.get("classification")}
- tier: {content_metadata.get("tier")}
- tags: {content_metadata.get("tags")}
- summary: {content_metadata.get("summary")}

Task:
Write the paid PPV message that continues the conversation and leads into this locked content.
"""

        # ------------------------------------------
        # BUILD MESSAGES
        # ------------------------------------------
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": metadata_prompt})

        print("\n[PPV CAPTION SERVICE]")
        print(f"Messages sent to GPT: {len(messages)}")
        print(f"[SESSION TONE] {session_tone}")

        # ------------------------------------------
        # GPT CALL
        # ------------------------------------------
        completion = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            temperature=0.95,
            max_tokens=80,
        )

        return completion.choices[0].message.content.strip()
